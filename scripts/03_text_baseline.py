"""Step 2 — the text baseline: BGE-M3 over the OCR markdown, pgvector ANN, NDCG@10.

One dense vector per page, a plain single-vector HNSW index, and the same scoring harness the
visual retriever will use in step 3. This is deliberately the *simple* system: it exists to be
a fair comparison point, and to have a working end-to-end pipeline on day one.

Writes:
  data/embeddings/text_<model>.npz   cached page vectors (skip re-embedding on re-runs)
  data/runs/text_baseline.json       the ranked run + per-query NDCG, for step 4
  reports/text_baseline.json         metrics, timings, index size, ANN recall
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
from rich.console import Console
from rich.table import Table

from visual_rag import config, data, metrics, pgvector_store, text_encoder

console = Console()


def embed_corpus(corpus, cfg: text_encoder.EncoderConfig, cache_path, rebuild: bool):
    """Encode every page's markdown, caching to disk so re-runs are index-only."""
    if cache_path.exists() and not rebuild:
        cached = np.load(cache_path, allow_pickle=False)
        if len(cached["corpus_ids"]) == len(corpus):
            console.print(f"reusing cached embeddings [dim]{cache_path}[/dim]")
            return cached["embeddings"], cached["corpus_ids"], None, None

    console.print(f"loading encoder [cyan]{cfg.model_name}[/cyan] on {cfg.device} ({cfg.dtype})")
    model = text_encoder.load_encoder(cfg)
    texts = corpus["markdown"].fillna("").tolist()
    stats = text_encoder.token_stats(model, texts, cfg.max_seq_length)
    console.print(
        f"tokens: mean {stats['tokens_mean']}, p95 {stats['tokens_p95']}, "
        f"max {stats['tokens_max']} — truncated pages: {stats['pages_truncated']}"
    )

    embeddings, seconds = text_encoder.encode(model, texts, cfg)
    corpus_ids = corpus["corpus_id"].to_numpy()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache_path, embeddings=embeddings, corpus_ids=corpus_ids)

    timing = {
        "seconds": round(seconds, 1),
        "pages_per_second": round(len(texts) / seconds, 1),
        "batch_size": cfg.batch_size,
        "device": cfg.device,
        "dtype": cfg.dtype,
    }
    del model
    return embeddings, corpus_ids, timing, stats


def build_index(conn, table, corpus, embeddings, corpus_ids, args) -> dict:
    pgvector_store.create_table(conn, table, drop=True)
    by_id = corpus.set_index("corpus_id")
    ordered = by_id.loc[corpus_ids]
    load_seconds = pgvector_store.insert_pages(
        conn,
        table,
        corpus_ids=corpus_ids,
        doc_ids=ordered["doc_id"].tolist(),
        page_numbers=ordered["page_number_in_doc"].tolist(),
        n_chars=ordered["markdown"].fillna("").str.len().tolist(),
        embeddings=embeddings,
    )
    index_seconds = pgvector_store.create_hnsw_index(
        conn, table, m=args.hnsw_m, ef_construction=args.hnsw_ef_construction
    )
    return {
        "rows": pgvector_store.count(conn, table),
        "copy_seconds": round(load_seconds, 2),
        "hnsw_build_seconds": round(index_seconds, 2),
        "hnsw_m": args.hnsw_m,
        "hnsw_ef_construction": args.hnsw_ef_construction,
        "ef_search": args.ef_search,
        **{k: round(v / 1e6, 1) for k, v in pgvector_store.storage(conn, table).items()},
    }


def run_search(conn, table, query_vectors, query_ids, k: int) -> tuple[dict, list[float]]:
    """Search every eval query at depth `k`, returning the run and per-query latencies."""
    run: dict[int, dict[int, float]] = {}
    latencies: list[float] = []
    for qid, vector in zip(query_ids, query_vectors, strict=True):
        started = time.perf_counter()
        hits = pgvector_store.search(conn, table, vector, k=k)
        latencies.append((time.perf_counter() - started) * 1000)
        run[int(qid)] = dict(hits)
    return run, latencies


def ann_recall(conn, table, query_vectors, args, sample: int) -> float:
    """Fraction of the exact top-k the HNSW index actually returns."""
    rng = np.random.default_rng(0)
    picks = rng.choice(len(query_vectors), size=min(sample, len(query_vectors)), replace=False)
    overlaps = []
    for i in picks:
        vector = query_vectors[i]
        approx = {cid for cid, _ in pgvector_store.search(conn, table, vector, k=args.k)}
        exact = {cid for cid, _ in pgvector_store.search(conn, table, vector, k=args.k, exact=True)}
        overlaps.append(len(approx & exact) / max(len(exact), 1))
    return round(float(np.mean(overlaps)), 4)


def percentiles(values: list[float]) -> dict[str, float]:
    array = np.array(values)
    return {
        "mean": round(float(array.mean()), 2),
        "p50": round(float(np.percentile(array, 50)), 2),
        "p95": round(float(np.percentile(array, 95)), 2),
        "p99": round(float(np.percentile(array, 99)), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=text_encoder.DEFAULT_MODEL)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", default="float16")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--k", type=int, default=config.NDCG_K, help="headline metric cutoff")
    parser.add_argument("--depth", type=int, default=100, help="how deep to retrieve per query")
    parser.add_argument("--ef-search", type=int, default=100)
    parser.add_argument("--hnsw-m", type=int, default=16)
    parser.add_argument("--hnsw-ef-construction", type=int, default=64)
    parser.add_argument("--rebuild", action="store_true", help="re-embed instead of using cache")
    parser.add_argument("--exact-sample", type=int, default=30, help="queries for ANN recall")
    args = parser.parse_args()

    config.ensure_dirs()
    eval_set = data.load_eval_set()
    corpus = eval_set.corpus
    gold = eval_set.gold()
    console.print(
        f"corpus {len(corpus):,} pages · eval {len(eval_set.queries)} queries "
        f"· {len(eval_set.qrels)} judgements"
    )

    cfg = text_encoder.EncoderConfig(
        model_name=args.model,
        device=args.device,
        dtype=args.dtype,
        max_seq_length=args.max_seq_length,
        batch_size=args.batch_size,
    )
    slug = args.model.replace("/", "_")
    cache_path = config.DATA_DIR / "embeddings" / f"text_{slug}.npz"

    console.rule("[bold]embed corpus")
    embeddings, corpus_ids, embed_timing, token_info = embed_corpus(
        corpus, cfg, cache_path, args.rebuild
    )
    table = pgvector_store.VectorTable("text_pages", int(embeddings.shape[1]))

    console.rule("[bold]index")
    with pgvector_store.connect() as conn:
        index_info = build_index(conn, table, corpus, embeddings, corpus_ids, args)
        console.print(
            f"{index_info['rows']:,} rows · copy {index_info['copy_seconds']}s · "
            f"hnsw build {index_info['hnsw_build_seconds']}s · "
            f"{index_info['total_bytes']} MB total ({index_info['index_bytes']} MB index)"
        )

        console.rule("[bold]search")
        model = text_encoder.load_encoder(cfg)
        queries = eval_set.queries
        query_vectors, query_embed_seconds = text_encoder.encode(
            model, queries["query"].tolist(), cfg, prefix=cfg.query_prefix, show_progress=False
        )
        del model

        # ef_search is a session GUC, set once, so the measured latency is the query alone.
        pgvector_store.configure_search(conn, args.ef_search)
        query_ids = queries["query_id"].tolist()

        # Scoring needs depth (step 4 wants recall@100); the serving-relevant latency is the
        # top-k path, and on a corpus this small the planner treats the two very differently.
        run, depth_latencies = run_search(conn, table, query_vectors, query_ids, args.depth)
        _, k_latencies = run_search(conn, table, query_vectors, query_ids, args.k)

        recall_vs_exact = ann_recall(conn, table, query_vectors, args, args.exact_sample)
        plans = {
            f"k={depth}": pgvector_store.explain(conn, table, query_vectors[0], k=depth)
            for depth in (args.k, args.depth)
        }
        index_used = {name: "Index Scan" in plan for name, plan in plans.items()}

    console.rule("[bold]score")
    ks = (1, 5, args.k)
    overall = metrics.evaluate(run, gold, ks=ks)
    overall_pytrec = metrics.evaluate_pytrec(run, gold, ks=ks)
    ndcg_gap = abs(overall[f"ndcg@{args.k}"] - overall_pytrec[f"ndcg_cut_{args.k}"])
    if ndcg_gap > 1e-3:
        console.print(f"[red]metric mismatch vs trec_eval: {ndcg_gap:.4f}[/red]")
        return 1

    breakdown = {
        name: {"queries": len(qids), **metrics.evaluate(run, metrics.subset(gold, qids), ks=ks)}
        for name, qids in data.query_slices(eval_set.queries).items()
        if qids
    }

    table_out = Table(box=None)
    table_out.add_column("slice", style="cyan")
    table_out.add_column("n", justify="right")
    for name in (f"ndcg@{args.k}", f"recall@{args.k}", f"success@{args.k}", "map"):
        table_out.add_column(name, justify="right")
    for name, values in breakdown.items():
        table_out.add_row(
            name,
            str(values["queries"]),
            *[
                f"{values[m]:.3f}"
                for m in (f"ndcg@{args.k}", f"recall@{args.k}", f"success@{args.k}", "map")
            ],
        )
    console.print(table_out)
    at_k, at_depth = percentiles(k_latencies), percentiles(depth_latencies)
    console.print(
        f"\nsearch latency (concurrency 1) — top-{args.k}: p50 {at_k['p50']} ms, "
        f"p95 {at_k['p95']} ms · top-{args.depth}: p50 {at_depth['p50']} ms · "
        f"query embed {query_embed_seconds / len(queries) * 1000:.1f} ms"
    )
    console.print(
        f"plan: k={args.k} -> {'hnsw index scan' if index_used[f'k={args.k}'] else 'seq scan'}, "
        f"k={args.depth} -> "
        f"{'hnsw index scan' if index_used[f'k={args.depth}'] else 'seq scan'} "
        f"(the planner drops the index once the beam approaches the corpus size)"
    )
    console.print(
        f"ANN recall@{args.k} vs exact: {recall_vs_exact:.3f} (ef_search={args.ef_search})"
    )

    report = {
        "retriever": "text",
        "model": args.model,
        "dim": int(embeddings.shape[1]),
        "corpus_pages": int(len(corpus)),
        "eval_queries": int(len(eval_set.queries)),
        "embedding": embed_timing,
        "tokens": token_info,
        "index": index_info,
        "search": {
            "k": args.k,
            "depth": args.depth,
            "hnsw_index_used": index_used,
            "ann_recall_vs_exact": recall_vs_exact,
            "latency_ms_top_k": at_k,
            "latency_ms_top_depth": at_depth,
            "query_embed_ms": round(query_embed_seconds / len(queries) * 1000, 2),
            "note": (
                "5,244 pages is small enough that Postgres prefers a sequential scan once the "
                "requested depth approaches the corpus size; the top-k path does use the HNSW "
                "index. ANN matters at Part 2 / production scale, not at this one."
            ),
        },
        "metrics": overall,
        "metrics_pytrec_eval": overall_pytrec,
        "breakdown": breakdown,
    }
    report_path = config.REPORTS_DIR / "text_baseline.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    run_path = config.DATA_DIR / "runs" / "text_baseline.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(
            {
                "retriever": "text",
                "model": args.model,
                "k": args.k,
                "run": {str(q): {str(d): s for d, s in hits.items()} for q, hits in run.items()},
                "per_query_ndcg": {
                    str(q): round(v, 4)
                    for q, v in metrics.per_query_ndcg(run, gold, args.k).items()
                },
            }
        )
    )
    console.print(f"\n[green]wrote[/green] {report_path}\n[green]wrote[/green] {run_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
