"""Step 4 — the calibration checkpoint.

The gate for Part 1's retrieval half: are my two NDCG@10 numbers *plausible* against what
ViDoRe V3 publishes for this exact corpus, and does the text-vs-visual delta reproduce?

Not "am I state of the art" — the benchmark is here to catch bugs, and a number that is wildly
off means I have one. Every comparison below is against the **industrial** subset specifically
(the hardest of the ten, and the only one this repo runs), scored the way the leaderboard scores
it: all English queries, human-written and synthetic together, graded NDCG@10.

Writes reports/calibration.json.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from rich.console import Console
from rich.table import Table

from visual_rag import config, data, metrics

console = Console()

# Published NDCG@10 on the ViDoRe V3 *industrial* subset, English queries. This subset scores
# far below the benchmark's cross-dataset average (~0.65 English), which is the number the
# project plan quoted — using that as the target would have made a correct pipeline look broken.
PUBLISHED = [
    {
        "model": "nemo-colembed-3b",
        "ndcg@10": 0.570,
        "note": "best model at benchmark launch; industrial was the lowest-scoring public set",
        "source": "https://huggingface.co/blog/QuentinJG/introducing-vidore-v3",
    },
    {
        "model": "nemotron-colembed-vl-8b-v2",
        "ndcg@10": 0.5603,
        "note": "leaderboard #1 overall (0.6342 across all 10 datasets)",
        "source": "https://arxiv.org/html/2602.03992v2",
    },
    {
        "model": "tomoro-colqwen3-embed-8b",
        "ndcg@10": 0.5441,
        "source": "https://arxiv.org/html/2602.03992v2",
    },
    {
        "model": "nemotron-colembed-vl-4b-v2",
        "ndcg@10": 0.5391,
        "source": "https://arxiv.org/html/2602.03992v2",
    },
]
# colqwen2-v1.0 — the retriever this repo runs — is not on the V3 leaderboard, so there is no
# like-for-like published figure. The frontier band below is what my number is judged against.
FRONTIER = (0.539, 0.570)
CONTEXT_ENGLISH_AVERAGE = 0.65  # across all 10 ViDoRe V3 datasets, not this one


def load_run(path):
    payload = json.loads(path.read_text())
    return {
        int(qid): {int(doc): score for doc, score in hits.items()}
        for qid, hits in payload["run"].items()
    }, payload


def summarise(name, per_query, seed):
    low, high = metrics.bootstrap_ci(list(per_query.values()), seed=seed)
    return {
        "system": name,
        "ndcg@10": round(float(np.mean(list(per_query.values()))), 4),
        "ci95": [round(low, 4), round(high, 4)],
        "queries": len(per_query),
    }


def compare(name, a, b, seed):
    """Paired comparison of two systems over the same queries."""
    keys = sorted(set(a) & set(b))
    left = [a[k] for k in keys]
    right = [b[k] for k in keys]
    delta, (low, high) = metrics.paired_delta_ci(left, right, seed=seed)
    return {
        "comparison": name,
        "delta": round(delta, 4),
        "ci95": [round(low, 4), round(high, 4)],
        "p_value": round(metrics.permutation_p_value(left, right, seed=seed), 5),
        "queries": len(keys),
        "significant": low > 0 or high < 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=config.NDCG_K)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    config.ensure_dirs()
    eval_set = data.load_eval_set()
    gold = eval_set.gold()
    queries = eval_set.queries

    runs_dir = config.DATA_DIR / "runs"
    text_run, _ = load_run(runs_dir / "text_baseline.json")
    visual_run, visual_payload = load_run(runs_dir / "visual_two_stage.json")
    exhaustive_per_query = {
        int(qid): value
        for qid, value in visual_payload.get("exhaustive_per_query_ndcg", {}).items()
    }

    per_query = {
        "text": metrics.per_query_ndcg(text_run, gold, args.k),
        "visual_two_stage": metrics.per_query_ndcg(visual_run, gold, args.k),
    }
    if exhaustive_per_query:
        per_query["visual_exhaustive"] = exhaustive_per_query

    console.rule("[bold]my numbers (ViDoRe V3 industrial, English, NDCG@10)")
    systems = [summarise(name, values, args.seed) for name, values in per_query.items()]
    by_system = {row["system"]: row for row in systems}
    table = Table(box=None)
    table.add_column("system", style="cyan")
    table.add_column("NDCG@10", justify="right")
    table.add_column("95% CI", justify="right")
    for row in systems:
        table.add_row(
            row["system"], f"{row['ndcg@10']:.3f}", f"[{row['ci95'][0]:.3f}, {row['ci95'][1]:.3f}]"
        )
    console.print(table)

    console.rule("[bold]published, same subset")
    published_table = Table(box=None)
    published_table.add_column("model", style="cyan")
    published_table.add_column("NDCG@10", justify="right")
    published_table.add_column("note")
    for entry in PUBLISHED:
        published_table.add_row(entry["model"], f"{entry['ndcg@10']:.3f}", entry.get("note", ""))
    published_table.add_row(
        "[dim]mine: colqwen2-v1.0 (2B, 2024)[/dim]",
        f"[dim]{by_system['visual_two_stage']['ndcg@10']:.3f}[/dim]",
        "[dim]not on the V3 leaderboard — no like-for-like published figure[/dim]",
    )
    console.print(published_table)

    console.rule("[bold]paired comparisons")
    comparisons = [
        compare("visual − text", per_query["visual_two_stage"], per_query["text"], args.seed)
    ]
    if "visual_exhaustive" in per_query:
        comparisons.append(
            compare(
                "exhaustive − two_stage",
                per_query["visual_exhaustive"],
                per_query["visual_two_stage"],
                args.seed,
            )
        )
    comparison_table = Table(box=None)
    comparison_table.add_column("comparison", style="cyan")
    comparison_table.add_column("Δ NDCG@10", justify="right")
    comparison_table.add_column("95% CI", justify="right")
    comparison_table.add_column("p", justify="right")
    for row in comparisons:
        comparison_table.add_row(
            row["comparison"],
            f"{row['delta']:+.3f}",
            f"[{row['ci95'][0]:+.3f}, {row['ci95'][1]:+.3f}]",
            f"{row['p_value']:.4f}",
        )
    console.print(comparison_table)

    console.rule("[bold]delta by slice")
    slice_rows = []
    slice_table = Table(box=None)
    slice_table.add_column("slice", style="cyan")
    slice_table.add_column("n", justify="right")
    slice_table.add_column("text", justify="right")
    slice_table.add_column("visual", justify="right")
    slice_table.add_column("Δ", justify="right")
    slice_table.add_column("95% CI", justify="right")
    for name, qids in data.query_slices(queries).items():
        keys = [q for q in qids if q in per_query["text"]]
        text_scores = [per_query["text"][q] for q in keys]
        visual_scores = [per_query["visual_two_stage"][q] for q in keys]
        delta, (low, high) = metrics.paired_delta_ci(visual_scores, text_scores, seed=args.seed)
        row = {
            "slice": name,
            "queries": len(keys),
            "text": round(float(np.mean(text_scores)), 4),
            "visual": round(float(np.mean(visual_scores)), 4),
            "delta": round(delta, 4),
            "ci95": [round(low, 4), round(high, 4)],
            "significant": low > 0,
        }
        slice_rows.append(row)
        slice_table.add_row(
            name,
            str(row["queries"]),
            f"{row['text']:.3f}",
            f"{row['visual']:.3f}",
            f"{row['delta']:+.3f}",
            f"[{low:+.3f}, {high:+.3f}]",
        )
    console.print(slice_table)

    # --- the gate ---------------------------------------------------------------------------
    visual = by_system["visual_two_stage"]
    ceiling = by_system.get("visual_exhaustive", visual)
    text = by_system["text"]
    delta_row = comparisons[0]

    checks = [
        {
            "check": "visual beats text, and the interval excludes zero",
            "expected": "Δ > 0, CI excludes 0",
            "observed": (
                f"Δ={delta_row['delta']:+.3f}, CI={delta_row['ci95']}, p={delta_row['p_value']}"
            ),
            "pass": delta_row["delta"] > 0 and delta_row["ci95"][0] > 0,
        },
        {
            "check": "visual lands below the published frontier but within reach of it",
            "expected": (
                f"{FRONTIER[0] - 0.15:.2f} <= ndcg <= {FRONTIER[1]:.2f}, frontier {FRONTIER}"
            ),
            "observed": f"{ceiling['ndcg@10']:.3f} (exhaustive), {visual['ndcg@10']:.3f} (served)",
            "pass": FRONTIER[0] - 0.15 <= ceiling["ndcg@10"] <= FRONTIER[1],
        },
        {
            "check": "text baseline is a real baseline, not broken and not implausible",
            "expected": "0.20 ≤ ndcg < visual",
            "observed": f"{text['ndcg@10']:.3f}",
            "pass": 0.20 <= text["ndcg@10"] < visual["ndcg@10"],
        },
        {
            "check": "the two-stage shortlist costs little against its own ceiling",
            "expected": "two_stage ≥ 90% of exhaustive",
            "observed": f"{visual['ndcg@10'] / ceiling['ndcg@10'] * 100:.1f}%",
            "pass": visual["ndcg@10"] >= 0.9 * ceiling["ndcg@10"],
        },
    ]
    verdict = "PASS" if all(check["pass"] for check in checks) else "FAIL"

    console.rule("[bold]gate")
    gate_table = Table(box=None)
    gate_table.add_column("", width=4)
    gate_table.add_column("check", style="cyan")
    gate_table.add_column("observed")
    for check in checks:
        gate_table.add_row(
            "[green]ok[/green]" if check["pass"] else "[red]FAIL[/red]",
            check["check"],
            check["observed"],
        )
    console.print(gate_table)
    console.print(
        f"\n[bold]{verdict}[/bold] — "
        + (
            "pipeline is calibrated; stop tuning retrieval and move to serving."
            if verdict == "PASS"
            else "investigate before building on these numbers."
        )
    )

    report = {
        "dataset": config.DATASET_ID,
        "protocol": {
            "queries": int(len(queries)),
            "language": config.EVAL_LANGUAGE,
            "generators": {
                str(k): int(v) for k, v in queries["query_generator"].value_counts().items()
            },
            "metric": f"ndcg@{args.k}",
            "graded_relevance": True,
            "note": (
                "Matches the published protocol: the leaderboard reports NDCG@10 per dataset "
                "over the English queries, human-written and synthetic together."
            ),
        },
        "systems": systems,
        "comparisons": comparisons,
        "by_slice": slice_rows,
        "published_reference": PUBLISHED,
        "frontier_band": list(FRONTIER),
        "context": {
            "vidore_v3_english_average_all_datasets": CONTEXT_ENGLISH_AVERAGE,
            "note": (
                "The ~0.65 figure quoted in the project plan is the cross-dataset English "
                "average. Industrial is the hardest of the ten subsets; judging this corpus "
                "against 0.65 would flag a correct pipeline as broken."
            ),
        },
        "gate": {"checks": checks, "verdict": verdict},
    }
    path = config.REPORTS_DIR / "calibration.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    console.print(f"\n[green]wrote[/green] {path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
