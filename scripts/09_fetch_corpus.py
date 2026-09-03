"""Step 9 — rebuild the Part 2 MCU corpus from `corpus/mcu_manifest.json`.

The manifest is the corpus: URL, content hash, page selection and licence status per
document. This script fetches what is missing into `data/mcu/pdfs/`, re-verifies every
document against its recorded hash, and reports the page budget.

    make corpus-record   # first collect: download and pin each document's hash
    make corpus          # every run after: verify the pins, fetch anything missing
    make corpus-verify   # offline: hash what is on disk, touch the network never

A hash mismatch is a hard failure, not a warning. Vendors supersede documents in place
(an STM32 datasheet goes Rev 4 -> Rev 5 at the same URL), which would silently change the
ground the retrieval numbers were measured on. The mismatching download is parked next to
the corpus for inspection rather than installed.

Writes reports/corpus_mcu.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from visual_rag import config, corpus

console = Console()

STATUS_STYLE = {
    "cached": "green",
    "downloaded": "green",
    "recorded": "cyan",
    "hash-mismatch": "red",
    "unpinned": "yellow",
    "missing": "yellow",
    "manual-missing": "yellow",
    "identity-mismatch": "red",
    "error": "red",
}


def results_table(results: list[corpus.SyncResult], manifest: corpus.Manifest) -> Table:
    table = Table(box=None)
    table.add_column("document", style="cyan", no_wrap=True)
    table.add_column("type")
    table.add_column("pages", justify="right")
    table.add_column("selected", justify="right")
    table.add_column("MB", justify="right")
    table.add_column("sha256")
    table.add_column("status")
    for res in results:
        doc = manifest.by_id(res.doc_id)
        style = STATUS_STYLE.get(res.status, "")
        selected = "?" if res.selected_pages is None else f"{res.selected_pages:,}"
        table.add_row(
            res.doc_id,
            doc.doc_type,
            f"{res.page_count:,}" if res.page_count else "-",
            selected,
            f"{res.bytes / 1e6:.1f}" if res.bytes else "-",
            res.sha256[:12] if res.sha256 else "-",
            f"[{style}]{res.status}[/{style}]" if style else res.status,
        )
    return table


def budget_table(budget: dict) -> Table:
    low, high = config.MCU_PAGE_TARGET
    selected = budget["selected_pages"]
    verdict = (
        "in target"
        if low <= selected <= high
        else ("under target" if selected < low else "over target")
    )
    table = Table(box=None, show_header=False)
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    table.add_row("documents", f"{budget['documents']:,}")
    table.add_row("physical pages", f"{budget['physical_pages']:,}")
    table.add_row("selected pages", f"{selected:,}  ({verdict}: {low:,}-{high:,})")
    table.add_row("PDF bytes", f"{budget['bytes'] / 1e6:.0f} MB")
    for key, label in (("by_doc_type", "by type"), ("by_vendor", "by vendor")):
        parts = ", ".join(f"{k} {v:,}" for k, v in sorted(budget[key].items()))
        table.add_row(label, parts or "-")
    if budget["pending_documents"]:
        table.add_row(
            "[yellow]slices pending[/yellow]",
            ", ".join(budget["pending_documents"]),
        )
    # ~4.5 pages/s was Part 1's measured ColQwen2 throughput, so this is what one reindex
    # of the corpus costs in wall-clock time.
    if selected:
        table.add_row("embed time @4.5 pages/s", f"~{selected / 4.5 / 60:.0f} min per reindex")
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=config.MCU_MANIFEST)
    parser.add_argument("--out", type=Path, default=config.MCU_PDF_DIR, help="PDF directory")
    parser.add_argument(
        "--record",
        action="store_true",
        help="write the hash, size and page count of newly fetched documents into the manifest",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with --record, re-pin a document whose hash already differs (the vendor "
        "superseded it) — deliberate act, invalidates the index built on the old revision",
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="hash local files, make no network requests"
    )
    parser.add_argument(
        "--try-manual",
        action="store_true",
        help="attempt HTTP even for fetch_mode=manual documents — they are marked that way "
        "because the vendor's edge refused this client, so try it if your network differs",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    parser.add_argument("--doc-id", nargs="+", help="limit to these document ids")
    parser.add_argument("--vendor", nargs="+", help="limit to these vendors")
    parser.add_argument("--doc-type", nargs="+", choices=corpus.DOC_TYPES, help="limit by type")
    parser.add_argument("--no-save-report", action="store_true")
    args = parser.parse_args()

    if args.force and not args.record:
        parser.error("--force only means something with --record")

    config.ensure_dirs()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = corpus.load_manifest(args.manifest)

    # --- 1. the manifest has to be internally valid before it is worth fetching anything
    console.rule("[bold]manifest")
    problems = manifest.problems()
    if problems:
        for line in problems:
            console.print(f"[red]invalid:[/red] {line}")
        return 1
    pinned = sum(1 for d in manifest.documents if d.pinned)
    console.print(
        f"{args.manifest.name}: [green]valid[/green] — {len(manifest.documents)} documents, "
        f"{pinned} pinned, {len(manifest.licenses)} vendor licences"
    )

    docs = manifest.select(args.doc_id, args.vendor, args.doc_type)
    if not docs:
        console.print("[yellow]no documents matched the filters[/yellow]")
        return 1

    if args.dry_run:
        console.rule("[bold]plan")
        for doc in docs:
            path = doc.path(args.out)
            if path.exists():
                action = "verify"
            elif args.verify_only:
                action = "skip (--verify-only)"
            elif doc.fetch_mode == "manual" and not args.try_manual:
                action = "browser download"
            else:
                action = "download"
            pin = doc.sha256[:12] if doc.sha256 else "[yellow]unpinned[/yellow]"
            console.print(f"  {doc.doc_id:<34} {action:<18} pin={pin}")
        return 0

    # --- 2. fetch / verify, one document at a time so an interrupted --record keeps its pins
    console.rule("[bold]documents")
    fetcher = None if args.verify_only else corpus.Fetcher(manifest.fetch)
    results: list[corpus.SyncResult] = []
    for doc in docs:
        result, updated = corpus.sync_document(
            doc,
            args.out,
            fetcher,
            record=args.record,
            force=args.force,
            verify_only=args.verify_only,
            try_manual=args.try_manual,
        )
        results.append(result)
        if updated is not doc:
            manifest.replace_document(updated)
            corpus.save_manifest(manifest, args.manifest)
        style = STATUS_STYLE.get(result.status, "")
        console.print(
            f"  {doc.doc_id:<34} [{style}]{result.status}[/{style}]"
            + (f"  {result.message}" if result.message else "")
        )

    console.rule("[bold]corpus")
    console.print(results_table(results, manifest))

    budget = corpus.page_budget(results, manifest)
    console.rule("[bold]page budget")
    console.print(budget_table(budget))

    # --- 3. persist, then fail loudly if anything is not reproducible
    failures = [r for r in results if not r.ok]
    if not args.no_save_report:
        report = {
            "manifest": str(args.manifest),
            "pdf_dir": str(args.out),
            "mode": "verify-only" if args.verify_only else ("record" if args.record else "verify"),
            "page_target": list(config.MCU_PAGE_TARGET),
            "budget": budget,
            "documents": [r.to_json_dict() for r in results],
            "failures": [r.doc_id for r in failures],
            "http_requests": fetcher.requests_made if fetcher else 0,
        }
        report_path = config.REPORTS_DIR / "corpus_mcu.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        console.print(f"\nwritten {report_path}")

    manual = corpus.manual_downloads(results, manifest, args.out)
    if manual:
        console.rule("[bold yellow]download these in a browser")
        console.print(
            "These vendors' edges refuse scripted clients. Fetch each URL in a browser and "
            "save it to the path beside it, then re-run with --record to pin the hash — after "
            "which every later run verifies it like any other document.\n"
        )
        for url, dest in manual:
            console.print(f"  [cyan]{dest}[/cyan]\n    {url}")

    if failures:
        console.rule("[bold red]corpus incomplete")
        # manual documents are already listed above, with their destinations — don't repeat
        for res in failures:
            if res.status != "manual-missing":
                console.print(f"[red]{res.status}[/red] {res.doc_id}: {res.message}")
        if manual:
            console.print(
                f"[yellow]{len(manual)}[/yellow] document(s) await a browser download "
                "(listed above), then: make corpus-record"
            )
        return 1

    if budget["pending_documents"]:
        console.print(
            "\n[yellow]next:[/yellow] read each errata, then fill in the slice ranges for "
            + ", ".join(budget["pending_documents"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
