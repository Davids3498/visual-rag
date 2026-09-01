"""Step 1 — load the four ViDoRe V3 subsets, verify them, and build the eval set.

Downloads ~2 GB into the HF cache on first run. Produces:
  data/eval/eval_queries.parquet   the strict English+human query slice
  data/eval/eval_qrels.parquet     graded relevance judgements for those queries
  data/eval/corpus_meta.parquet    page metadata + OCR markdown (no images)
  data/eval/documents_metadata.parquet
  reports/dataset_stats.json       everything printed below, machine-readable

Steps 2 and 3 both score against these files, so the text and visual retrievers can never
drift onto different ground.
"""

from __future__ import annotations

import argparse
import json
import textwrap

from rich.console import Console
from rich.table import Table

from visual_rag import config, data

console = Console()


def kv_table(title: str, rows: dict) -> Table:
    table = Table(title=title, title_justify="left", show_header=False, box=None, pad_edge=False)
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    for key, value in rows.items():
        table.add_row(str(key), str(value))
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-save", action="store_true", help="inspect only, write nothing")
    parser.add_argument(
        "--allow-count-mismatch",
        action="store_true",
        help="continue even if row counts differ from the dataset card",
    )
    parser.add_argument("--examples", type=int, default=3, help="example queries to print")
    parser.add_argument(
        "--language",
        default=config.EVAL_LANGUAGE,
        help="query language for the eval slice (the other 5 are translations of the English set)",
    )
    parser.add_argument(
        "--generator",
        default=config.EVAL_QUERY_GENERATOR,
        help="'human' for the strict slice, 'sdg' for the synthetic queries, 'any' for both",
    )
    args = parser.parse_args()

    config.ensure_dirs()

    # --- 1. pull the subsets and check them against the card
    console.rule("[bold]subsets")
    counts = data.row_counts()
    table = Table(box=None)
    table.add_column("subset", style="cyan")
    table.add_column("rows", justify="right")
    table.add_column("expected", justify="right")
    table.add_column("")
    for name in config.SUBSETS:
        expected = config.EXPECTED_ROWS[name]
        ok = counts[name] == expected
        table.add_row(
            name,
            f"{counts[name]:,}",
            f"{expected:,}",
            "[green]ok[/green]" if ok else "[red]MISMATCH[/red]",
        )
    console.print(table)

    mismatches = data.check_row_counts(counts)
    if mismatches:
        for line in mismatches:
            console.print(f"[red]row count mismatch:[/red] {line}")
        console.print(
            "the dataset revision differs from the one this eval was written against; "
            "re-check the card before trusting any score"
        )
        if not args.allow_count_mismatch:
            return 1

    # --- 2. build the eval slice
    console.rule("[bold]eval set")
    eval_set = data.build_eval_set(language=args.language, generator=args.generator)
    stats = eval_set.stats

    console.print(kv_table("raw dataset", stats["raw"]))
    console.print()
    console.print(
        kv_table(
            f"eval slice ({args.language} + query_generator={args.generator})",
            stats["eval"],
        )
    )
    console.print()
    console.print(kv_table("visual dependency of the gold evidence", stats["visual_dependency"]))
    console.print()
    console.print(kv_table("text-baseline inputs (markdown column)", stats["text_baseline_inputs"]))

    # --- 3. eyeball a few joined rows: query -> gold pages -> reference answer
    console.rule("[bold]examples")
    sample = eval_set.queries.sample(
        min(args.examples, len(eval_set.queries)), random_state=0
    ).sort_values("query_id")
    for row in sample.itertuples():
        gold = eval_set.qrels[eval_set.qrels["query_id"] == row.query_id]
        console.print(f"[cyan]query {row.query_id}[/cyan] ({', '.join(row.query_types)})")
        console.print(textwrap.fill(row.query, 96, initial_indent="  ", subsequent_indent="  "))
        for g in gold.itertuples():
            console.print(
                f"  [green]gold[/green] corpus_id={g.corpus_id} score={g.score} "
                f"doc={g.doc_id} p{g.page_number_in_doc} content={', '.join(g.content_type)}"
            )
        answer = (row.answer or "").strip().replace("\n", " ")
        console.print(
            textwrap.fill(
                f"answer: {answer[:280]}{'...' if len(answer) > 280 else ''}",
                96,
                initial_indent="  ",
                subsequent_indent="  ",
            )
        )
        console.print()

    # --- 4. persist
    if args.no_save:
        console.print("[yellow]--no-save:[/yellow] nothing written")
        return 0

    written = data.save_eval_set(eval_set)
    stats_path = config.REPORTS_DIR / "dataset_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2) + "\n")

    console.rule("[bold]written")
    for name, path in written.items():
        console.print(f"  {name:<10} {path}")
    console.print(f"  {'stats':<10} {stats_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
