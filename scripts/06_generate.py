"""Step 5 — generation on a self-hosted, quantized VLM.

Retrieve pages with the calibrated visual retriever, hand the page *images* to Qwen2.5-VL-7B
(AWQ int4, served by vLLM on the same 24 GB card), and require the answer to cite the pages it
used. No OCR text reaches the generator: it reads the same pixels the retriever ranked.

What this measures is grounding, not answer prose: does the model cite pages that are actually
relevant, and does it decline when retrieval handed it nothing useful. Answer-quality judging is
deliberately out of scope here — Part 2's no-context audit is where that gets done properly.

Writes reports/generation.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess

import numpy as np
from rich.console import Console
from rich.table import Table

from visual_rag import config, data, generation, multivector

console = Console()


def gpu_memory_mb() -> int:
    """Whole-card usage, so the retriever+generator coexistence is measured, not assumed."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return 0


def percentiles(values: list[float]) -> dict[str, float]:
    array = np.array(values)
    return {
        "mean": round(float(array.mean()), 1),
        "p50": round(float(np.percentile(array, 50)), 1),
        "p95": round(float(np.percentile(array, 95)), 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=40, help="eval queries to answer")
    parser.add_argument("--pages", type=int, default=3, help="retrieved pages shown per query")
    parser.add_argument(
        "--source",
        default="run",
        choices=("run", "live"),
        help="'run' replays the scored step-3 ranking; 'live' retrieves through the serving path",
    )
    parser.add_argument("--base-url", default=generation.DEFAULT_BASE_URL)
    parser.add_argument("--model", default=generation.DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--examples", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--cold",
        action="store_true",
        help="skip warming the memory-mapped store, to measure the cold-start penalty",
    )
    args = parser.parse_args()

    cfg = generation.VLMConfig(
        base_url=args.base_url,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        max_pages=args.pages,
    )
    if not generation.health(cfg):
        console.print(
            f"[red]no vLLM server at {cfg.base_url}[/red]\n"
            "start it with:  docker compose --profile serving up -d vllm"
        )
        return 1

    config.ensure_dirs()
    eval_set = data.load_eval_set()
    gold = eval_set.gold()
    corpus_ds, id_to_row = data.load_corpus_images()
    corpus_meta = eval_set.corpus.set_index("corpus_id")

    rng = np.random.default_rng(args.seed)
    queries = eval_set.queries.iloc[
        rng.choice(
            len(eval_set.queries), size=min(args.sample, len(eval_set.queries)), replace=False
        )
    ].sort_values("query_id")

    baseline_mb = gpu_memory_mb()
    console.print(f"GPU in use before retrieval loads: {baseline_mb} MiB (vLLM resident)")

    # --- retrieval
    if args.source == "run":
        run_path = config.DATA_DIR / "runs" / "visual_two_stage.json"
        run = json.loads(run_path.read_text())["run"]
        shortlists = {
            int(qid): [
                int(doc)
                for doc, _ in sorted(run[str(qid)].items(), key=lambda kv: -kv[1])[: args.pages]
            ]
            for qid in queries["query_id"]
        }
        retrieval_ms = {}
        peak_mb = baseline_mb
    else:
        from visual_rag import pgvector_store
        from visual_rag import retrieval as retrieval_module

        cache = config.DATA_DIR / "embeddings" / "visual_vidore_colqwen2-v1.0"
        store = multivector.MultiVectorStore.load(cache)
        shortlists, retrieval_ms = {}, {}
        with pgvector_store.connect() as conn:
            retriever = retrieval_module.TwoStageRetriever(store, conn)
            if not args.cold:
                warm_ms = retriever.warm()
                console.print(f"warmed the multi-vector store in {warm_ms:.0f} ms")
            for query_id, question in zip(queries["query_id"], queries["query"], strict=True):
                result = retriever.retrieve(question, k=args.pages)
                shortlists[int(query_id)] = result.corpus_ids
                retrieval_ms[int(query_id)] = {
                    "encode_ms": round(result.encode_ms, 1),
                    "stage1_ms": round(result.stage1_ms, 1),
                    "stage2_ms": round(result.stage2_ms, 1),
                    "total_ms": round(result.total_ms, 1),
                }
            peak_mb = gpu_memory_mb()
        console.print(
            f"GPU with ColQwen2 + vLLM both resident: {peak_mb} MiB of 24576 "
            f"— the coexistence the serving design has to survive"
        )

    # --- generation
    console.rule(f"[bold]generating ({args.source} retrieval, {args.pages} pages/query)")
    records = []
    for query_id, question in zip(queries["query_id"], queries["query"], strict=True):
        page_ids = shortlists[int(query_id)]
        pages = [
            {
                "corpus_id": corpus_id,
                "image": corpus_ds[id_to_row[corpus_id]]["image"],
                "doc_id": corpus_meta.loc[corpus_id, "doc_id"],
                "page_number": int(corpus_meta.loc[corpus_id, "page_number_in_doc"]),
            }
            for corpus_id in page_ids
        ]
        result = generation.answer(question, pages, cfg)
        relevant = set(gold[int(query_id)])
        records.append(
            {
                "query_id": int(query_id),
                "query": question,
                "shown_pages": result.shown_pages,
                "gold_shown": sorted(set(result.shown_pages) & relevant),
                "cited_pages": result.cited_pages,
                "cited_gold": sorted(set(result.cited_pages) & relevant),
                "refused": result.refused,
                "answer": result.text,
                "reference_answer": (queries.loc[queries.query_id == query_id, "answer"].iloc[0]),
                "latency_ms": round(result.latency_ms, 1),
                "prompt_tokens": result.usage.get("prompt_tokens"),
                "completion_tokens": result.usage.get("completion_tokens"),
                "retrieval": retrieval_ms.get(int(query_id)),
            }
        )
        console.print(
            f"  q{query_id:<5d} {'REFUSED' if result.refused else 'answered'} · "
            f"cited {result.cited_pages or '—'} · gold shown {records[-1]['gold_shown'] or '—'} · "
            f"{result.latency_ms:.0f} ms"
        )

    # --- what the numbers mean
    answered = [r for r in records if not r["refused"]]
    with_gold = [r for r in records if r["gold_shown"]]
    without_gold = [r for r in records if not r["gold_shown"]]
    cited = [r for r in answered if r["cited_pages"]]
    latencies = [r["latency_ms"] for r in records]
    completion_tokens = [r["completion_tokens"] or 0 for r in records]

    summary = {
        "queries": len(records),
        "pages_per_query": args.pages,
        "retrieval_hit_rate": round(len(with_gold) / len(records), 3),
        "answered": len(answered),
        "refused": len(records) - len(answered),
        "citation_rate": round(len(cited) / max(len(answered), 1), 3),
        "citation_precision": round(
            float(np.mean([len(r["cited_gold"]) / len(r["cited_pages"]) for r in cited])), 3
        )
        if cited
        else None,
        "grounded_answer_rate": round(
            sum(1 for r in answered if r["cited_gold"]) / max(len(answered), 1), 3
        ),
        "refusal_when_no_gold_page": round(
            sum(1 for r in without_gold if r["refused"]) / max(len(without_gold), 1), 3
        )
        if without_gold
        else None,
        "refusal_when_gold_page_shown": round(
            sum(1 for r in with_gold if r["refused"]) / max(len(with_gold), 1), 3
        )
        if with_gold
        else None,
        "latency_ms": percentiles(latencies),
        "completion_tokens_mean": round(float(np.mean(completion_tokens)), 1),
        "output_tokens_per_second": round(
            float(np.sum(completion_tokens) / (np.sum(latencies) / 1000)), 1
        ),
    }

    console.rule("[bold]grounding")
    table = Table(box=None, show_header=False)
    table.add_column(style="cyan")
    table.add_column(justify="right")
    table.add_row("queries answered", f"{summary['answered']} / {summary['queries']}")
    table.add_row("refused (NOT_IN_PAGES)", str(summary["refused"]))
    table.add_row("a gold page was actually shown", f"{summary['retrieval_hit_rate']:.0%}")
    table.add_row("answers carrying a citation", f"{summary['citation_rate']:.0%}")
    table.add_row(
        "cited pages that are gold",
        f"{summary['citation_precision']:.0%}"
        if summary["citation_precision"] is not None
        else "—",
    )
    table.add_row("answers citing a gold page", f"{summary['grounded_answer_rate']:.0%}")
    if summary["refusal_when_no_gold_page"] is not None:
        table.add_row(
            "refused when no gold page shown", f"{summary['refusal_when_no_gold_page']:.0%}"
        )
    if summary["refusal_when_gold_page_shown"] is not None:
        table.add_row(
            "refused despite a gold page", f"{summary['refusal_when_gold_page_shown']:.0%}"
        )
    console.print(table)
    console.print(
        f"\nlatency p50 {summary['latency_ms']['p50']} ms · p95 {summary['latency_ms']['p95']} ms "
        f"· {summary['completion_tokens_mean']:.0f} output tokens avg · "
        f"{summary['output_tokens_per_second']:.1f} tok/s at concurrency 1"
    )

    console.rule("[bold]examples")
    for record in records[: args.examples]:
        console.print(f"[cyan]q{record['query_id']}[/cyan] {record['query']}")
        console.print(f"  [green]model[/green]: {record['answer'][:400]}")
        console.print(f"  [dim]reference[/dim]: {(record['reference_answer'] or '')[:240]}")
        console.print(
            f"  [dim]shown {record['shown_pages']} · gold among them "
            f"{record['gold_shown'] or 'none'}[/dim]\n"
        )

    retrieval_totals = [r["retrieval"]["total_ms"] for r in records if r["retrieval"]]
    if retrieval_totals:
        summary["retrieval_ms"] = percentiles(retrieval_totals)
        for stage in ("encode_ms", "stage1_ms", "stage2_ms"):
            summary[f"retrieval_{stage}"] = percentiles(
                [r["retrieval"][stage] for r in records if r["retrieval"]]
            )
        summary["end_to_end_ms"] = round(
            summary["retrieval_ms"]["p50"] + summary["latency_ms"]["p50"], 1
        )
        console.print(
            f"retrieval p50 {summary['retrieval_ms']['p50']} ms "
            f"(encode {summary['retrieval_encode_ms']['p50']}, "
            f"stage1 {summary['retrieval_stage1_ms']['p50']}, "
            f"stage2 {summary['retrieval_stage2_ms']['p50']}) "
            f"-> end-to-end p50 {summary['end_to_end_ms']} ms"
        )

    report = {
        "generator": {
            "model": args.model,
            "quantization": "AWQ int4",
            "server": "vLLM (OpenAI-compatible)",
            "base_url": args.base_url,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        },
        "retrieval_source": args.source,
        "gpu_memory_mb": {"before_retriever": baseline_mb, "peak": peak_mb, "total": 24576},
        "summary": summary,
        "records": records,
    }
    suffix = "_live" if args.source == "live" else ""
    path = config.REPORTS_DIR / f"generation{suffix}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    console.print(f"[green]wrote[/green] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
