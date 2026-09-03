"""Step 10 — render the manifest's selected pages into images, and write the page table.

The corpus becomes a list of pages here, because the page is the retrieval unit: one page is
one row in the index and one score at ranking time. Whole datasheets and errata, only the
chosen chapters of the reference manuals.

    make pages            # render what is missing, rewrite the page table
    make pages-rebuild    # re-render everything (after changing the resolution, say)

Produces:
  data/mcu/pages/<doc_id>/pNNNN.png   one image per selected page
  data/mcu/pages.parquet              page_id -> document, page number, size, source revision
  reports/mcu_pages.json              the same, summarised
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from visual_rag import config, corpus, ingest

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=config.MCU_MANIFEST)
    parser.add_argument("--pdf-dir", type=Path, default=config.MCU_PDF_DIR)
    parser.add_argument("--pages-dir", type=Path, default=config.MCU_PAGES_DIR)
    parser.add_argument("--doc-id", nargs="+", help="limit to these document ids")
    parser.add_argument("--vendor", nargs="+", help="limit to these vendors")
    parser.add_argument(
        "--target-pixels",
        type=int,
        default=config.MCU_TARGET_PIXELS,
        help="pixels per rendered page (default: the 1.2 MP figure step 5 measured)",
    )
    parser.add_argument("--rebuild", action="store_true", help="re-render pages already on disk")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, render nothing")
    args = parser.parse_args()

    config.ensure_dirs()
    manifest = corpus.load_manifest(args.manifest)
    problems = manifest.problems()
    if problems:
        for line in problems:
            console.print(f"[red]invalid manifest:[/red] {line}")
        return 1

    docs = manifest.select(args.doc_id, args.vendor)
    if not docs:
        console.print("[yellow]no documents matched the filters[/yellow]")
        return 1

    # --- 1. the plan: every document must be pinned and have its ranges chosen
    console.rule("[bold]plan")
    plan_table = Table(box=None)
    for column, justify in [
        ("document", "left"),
        ("mode", "left"),
        ("of", "right"),
        ("pages", "right"),
        ("state", "left"),
    ]:
        plan_table.add_column(column, justify=justify, style="cyan" if column == "document" else "")
    blocked: list[str] = []
    planned = {}
    for doc in docs:
        try:
            refs = ingest.page_refs(doc, ingest.doc_ordinals(manifest)[doc.doc_id])
            planned[doc.doc_id] = refs
            state = "[green]ready[/green]"
            count = f"{len(refs):,}"
        except ValueError as exc:
            blocked.append(f"{doc.doc_id}: {exc}")
            state, count = f"[red]{exc}[/red]", "-"
        plan_table.add_row(doc.doc_id, doc.pages.mode, f"{doc.page_count or 0:,}", count, state)
    console.print(plan_table)
    if blocked:
        return 1

    total = sum(len(r) for r in planned.values())
    console.print(f"\n{total:,} pages at ~{args.target_pixels / 1e6:.1f} MP each")
    if args.dry_run:
        return 0

    # --- 2. render
    console.rule("[bold]rendering")
    with console.status("") as status:

        def tick(doc, refs):
            status.update(f"{doc.doc_id}: {len(refs):,} pages")

        rows, seconds = ingest.render_corpus(
            manifest,
            args.pdf_dir,
            args.pages_dir,
            documents=docs,
            target_pixels=args.target_pixels,
            overwrite=args.rebuild,
            progress=tick,
        )
    fresh = sum(1 for r in rows if r.rendered)
    rate = f"{fresh / seconds:.1f} pages/s" if fresh and seconds else "-"
    console.print(
        f"{len(rows):,} pages: [green]{fresh:,} rendered[/green] ({rate}), "
        f"{len(rows) - fresh:,} already on disk, {seconds:.1f}s"
    )

    # --- 3. the table, and the invariants the retrieval steps depend on
    table = ingest.page_table(rows)
    problems = ingest.table_problems(table, manifest)
    for line in problems:
        console.print(f"[red]{line}[/red]")

    summary = ingest.summarise(table)
    console.rule("[bold]corpus")
    out = Table(box=None, show_header=False)
    out.add_column(style="cyan", no_wrap=True)
    out.add_column()
    out.add_row("pages", f"{summary['pages']:,} from {summary['documents']} documents")
    out.add_row("images", f"{summary['bytes'] / 1e6:.0f} MB on disk")
    out.add_row(
        "resolution",
        f"{summary['megapixels_mean']:.2f} MP mean "
        f"({summary['megapixels_min']:.2f}-{summary['megapixels_max']:.2f})",
    )
    for key, label in (("by_doc_type", "by type"), ("by_vendor", "by vendor")):
        out.add_row(label, ", ".join(f"{k} {v:,}" for k, v in sorted(summary[key].items())))
    # ~4.5 pages/s was Part 1's measured ColQwen2 throughput on this card.
    out.add_row("embed time", f"~{summary['pages'] / 4.5 / 60:.0f} min at 4.5 pages/s")
    console.print(out)

    if args.doc_id or args.vendor:
        console.print("\n[yellow]partial run:[/yellow] page table not written (filters were used)")
        return 1 if problems else 0

    path = ingest.save_page_table(table)
    report = config.REPORTS_DIR / "mcu_pages.json"
    report.write_text(
        json.dumps(
            {
                "page_table": str(path),
                "pages_dir": str(args.pages_dir),
                "target_pixels": args.target_pixels,
                "render_seconds": round(seconds, 1),
                "problems": problems,
                **summary,
            },
            indent=2,
        )
        + "\n"
    )
    console.print(f"\nwritten {path}\nwritten {report}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
