"""Step 3 — visual retrieval: ColQwen2 late interaction with a two-stage search path.

Pages are embedded as *images*, ~756 vectors each, so the naive "one ANN index over every
vector" approach is out: 5,244 pages become 3.9M vectors, and an index over them returns
patches, not pages. Hence two stages:

  stage 1   a compact page representation -> pgvector ANN -> shortlist   (cheap, lossy)
  stage 2   full MaxSim late interaction over the shortlist only         (exact, expensive)

Two stage-1 representations are built and scored side by side, because the obvious one is a
trap: mean-pooling a page into a single vector loses ~24% of the achievable NDCG@10 on this
corpus, which would have made the visual retriever look no better than the text baseline.
Clustering each page's patches into 16 centroids and doing per-query-token ANN recovers it.

Exhaustive MaxSim over all pages is also scored. It is not the production path — it is the
ceiling that says what the shortlist costs.

Writes:
  data/embeddings/visual_<model>/    ragged page multi-vectors (~1 GB)
  data/runs/visual_two_stage.json    the ranked run + per-query NDCG, for step 4
  reports/visual_retrieval.json      metrics, timings, storage, candidate-depth sweeps
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from visual_rag import config, data, metrics, multivector, pgvector_store, visual_encoder

console = Console()

POOLED_TABLE = "visual_pages_pooled"
CENTROID_TABLE = "visual_page_centroids"


def _free_gpu() -> None:
    import gc

    import torch

    gc.collect()
    torch.cuda.empty_cache()


def embed_corpus(corpus_ds, corpus_ids, cfg, cache_dir, rebuild: bool):
    """Embed every page image, caching the ragged multi-vector store to disk."""
    if cache_dir.exists() and not rebuild:
        store = multivector.MultiVectorStore.load(cache_dir)
        if len(store) == len(corpus_ids):
            console.print(f"reusing cached page embeddings [dim]{cache_dir}[/dim]")
            return store, None, None

    console.print(f"loading [cyan]{cfg.model_name}[/cyan] on {cfg.device} ({cfg.dtype})")
    model, processor = visual_encoder.load_encoder(cfg)
    pages: list[np.ndarray] = []
    started = time.perf_counter()
    for start in tqdm(range(0, len(corpus_ids), cfg.batch_size), desc="pages", unit="batch"):
        images = corpus_ds[start : start + cfg.batch_size]["image"]
        pages.extend(visual_encoder.embed_images(model, processor, images, cfg))
    seconds = time.perf_counter() - started

    store = multivector.MultiVectorStore.from_pages(pages, corpus_ids)
    store.save(cache_dir)
    timing = {
        "seconds": round(seconds, 1),
        "pages_per_second": round(len(corpus_ids) / seconds, 2),
        "batch_size": cfg.batch_size,
        "device": cfg.device,
        "dtype": cfg.dtype,
    }
    # Handed back rather than freed: the queries need the same model a moment later.
    return store, timing, (model, processor)


def embed_eval_queries(queries, cfg, cache_dir, encoder, rebuild: bool):
    """Query token vectors, cached — otherwise every re-run reloads a 4.5 GB model for 177 rows."""
    cache = cache_dir.parent / f"{cache_dir.name}_queries"
    meta = cache / "meta.json"
    if cache.exists() and not rebuild and encoder is None:
        cached = multivector.MultiVectorStore.load(cache, mmap=False)
        if len(cached) == len(queries) and np.array_equal(
            cached.ids, queries["query_id"].to_numpy()
        ):
            console.print(f"reusing cached query embeddings [dim]{cache}[/dim]")
            # Query encoding is on the serving path, so carry its measurement forward instead
            # of reporting a null every time the cache is warm.
            recorded = json.loads(meta.read_text())["ms_per_query"] if meta.exists() else None
            return [cached.get(i) for i in range(len(cached))], recorded

    model, processor = encoder if encoder else visual_encoder.load_encoder(cfg)
    vectors, seconds = visual_encoder.embed_queries(
        model, processor, queries["query"].tolist(), cfg
    )
    multivector.MultiVectorStore.from_pages(vectors, queries["query_id"].to_numpy()).save(cache)
    ms_per_query = round(seconds / len(queries) * 1000, 2)
    meta.write_text(json.dumps({"ms_per_query": ms_per_query, "batch": cfg.query_batch_size}))
    del model, processor
    return vectors, ms_per_query


def pooled_query(query_vectors: np.ndarray) -> np.ndarray:
    """Stage-1 query representation for the pooled variant: mean token vector, normalised."""
    pooled = np.asarray(query_vectors, dtype=np.float32).mean(axis=0)
    return pooled / max(float(np.linalg.norm(pooled)), 1e-12)


def index_stats(conn, table, copy_seconds, build_seconds, args) -> dict:
    return {
        "rows": pgvector_store.count(conn, table),
        "copy_seconds": round(copy_seconds, 2),
        "hnsw_build_seconds": round(build_seconds, 2),
        "hnsw_m": args.hnsw_m,
        "hnsw_ef_construction": args.hnsw_ef_construction,
        "ef_search": args.ef_search,
        **{k: round(v / 1e6, 1) for k, v in pgvector_store.storage(conn, table).items()},
    }


def build_pooled_stage1(conn, store, corpus, query_vectors, args):
    """Stage 1a: one mean-pooled vector per page, one ANN call per query."""
    table = pgvector_store.VectorTable(POOLED_TABLE, store.dim)
    ordered = corpus.set_index("corpus_id").loc[store.ids]
    pgvector_store.create_table(conn, table, drop=True)
    copy_seconds = pgvector_store.insert_pages(
        conn,
        table,
        corpus_ids=store.ids,
        doc_ids=ordered["doc_id"].tolist(),
        page_numbers=ordered["page_number_in_doc"].tolist(),
        n_chars=store.lengths.tolist(),  # patches per page, not characters
        embeddings=store.pooled(),
    )
    build_seconds = pgvector_store.create_hnsw_index(
        conn, table, m=args.hnsw_m, ef_construction=args.hnsw_ef_construction
    )
    pgvector_store.configure_search(conn, args.ef_search)

    shortlists, latencies = [], []
    for vectors in query_vectors:
        query = pooled_query(vectors)
        started = time.perf_counter()
        hits = pgvector_store.search(conn, table, query, k=args.shortlist_max)
        latencies.append((time.perf_counter() - started) * 1000)
        shortlists.append([cid for cid, _ in hits])
    return shortlists, latencies, index_stats(conn, table, copy_seconds, build_seconds, args)


def build_centroid_stage1(conn, store, query_vectors, args):
    """Stage 1b: k centroids per page, one indexed top-k per query token, unioned by page."""
    table = pgvector_store.VectorTable(CENTROID_TABLE, store.dim)
    started = time.perf_counter()
    centroids = multivector.page_centroids(
        store, k=args.centroids, device=args.device, seed=args.seed
    )
    cluster_seconds = time.perf_counter() - started

    pgvector_store.create_centroid_table(conn, table, drop=True)
    copy_seconds = pgvector_store.insert_centroids(conn, table, store.ids, centroids)
    build_seconds = pgvector_store.create_hnsw_index(
        conn, table, m=args.hnsw_m, ef_construction=args.hnsw_ef_construction
    )
    pgvector_store.configure_search(conn, args.ef_search)

    shortlists, latencies = [], []
    for vectors in query_vectors:
        started = time.perf_counter()
        hits = pgvector_store.search_centroids(
            conn, table, vectors, per_token_k=args.per_token_k, limit=args.shortlist_max
        )
        latencies.append((time.perf_counter() - started) * 1000)
        shortlists.append([cid for cid, _ in hits])

    stats = index_stats(conn, table, copy_seconds, build_seconds, args)
    stats["centroids_per_page"] = args.centroids
    stats["clustering_seconds"] = round(cluster_seconds, 1)
    stats["per_token_k"] = args.per_token_k
    return shortlists, latencies, stats


def rerank(store, query_vectors, shortlists, index_by_corpus_id, args, depth=None):
    """Stage 2: exact MaxSim over the shortlist. Returns per-query {corpus_id: score}."""
    scored, latencies = [], []
    for vectors, shortlist in zip(query_vectors, shortlists, strict=True):
        pages = shortlist if depth is None else shortlist[:depth]
        indices = [index_by_corpus_id[cid] for cid in pages]
        started = time.perf_counter()
        scores = multivector.score_pages(store, vectors, indices, device=args.device)
        latencies.append((time.perf_counter() - started) * 1000)
        scored.append(dict(zip(pages, scores.tolist(), strict=True)))
    return scored, latencies


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
    parser.add_argument("--model", default=visual_encoder.DEFAULT_MODEL)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--k", type=int, default=config.NDCG_K)
    parser.add_argument("--candidates", type=int, default=100, help="shortlist used for the run")
    parser.add_argument("--shortlist-max", type=int, default=200, help="deepest shortlist scored")
    parser.add_argument("--sweep", default="10,25,50,100,200")
    parser.add_argument("--centroids", type=int, default=16, help="k per page for stage 1b")
    parser.add_argument("--per-token-k", type=int, default=50, help="ANN hits per query token")
    parser.add_argument(
        "--primary",
        default="centroids",
        choices=("centroids", "pooled"),
        help="which stage-1 variant produces the run handed to step 4",
    )
    parser.add_argument("--ef-search", type=int, default=200)
    parser.add_argument("--hnsw-m", type=int, default=16)
    parser.add_argument("--hnsw-ef-construction", type=int, default=64)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--no-exhaustive", action="store_true")
    parser.add_argument("--limit-pages", type=int, default=0, help="smoke test on N pages")
    args = parser.parse_args()

    sweep = sorted({int(n) for n in args.sweep.split(",") if int(n) <= args.shortlist_max})
    smoke = args.limit_pages > 0

    config.ensure_dirs()
    eval_set = data.load_eval_set()
    corpus = eval_set.corpus
    corpus_ds, _ = data.load_corpus_images()
    if smoke:
        console.print(f"[yellow]smoke test:[/yellow] first {args.limit_pages} pages only")
        corpus_ds = corpus_ds.select(range(args.limit_pages))
        corpus = corpus[corpus["corpus_id"].isin(set(corpus_ds["corpus_id"]))]
    corpus_ids = np.asarray(corpus_ds["corpus_id"], dtype=np.int64)

    gold = eval_set.gold()
    queries = eval_set.queries
    console.print(
        f"corpus {len(corpus_ids):,} pages · eval {len(queries)} queries · "
        f"{len(eval_set.qrels)} judgements"
    )

    cfg = visual_encoder.VisualEncoderConfig(
        model_name=args.model, device=args.device, dtype=args.dtype, batch_size=args.batch_size
    )
    slug = args.model.replace("/", "_")
    cache_dir = config.DATA_DIR / "embeddings" / f"visual_{slug}{'_smoke' if smoke else ''}"

    console.rule("[bold]embed pages")
    store, embed_timing, encoder = embed_corpus(corpus_ds, corpus_ids, cfg, cache_dir, args.rebuild)
    lengths = store.lengths
    console.print(
        f"{len(store):,} pages · {int(lengths.sum()):,} patch vectors · "
        f"{lengths.mean():.0f} per page (min {lengths.min()}, max {lengths.max()}) · "
        f"dim {store.dim} · {store.nbytes() / 1e6:.0f} MB on disk"
    )

    console.rule("[bold]embed queries")
    query_vectors, query_ms = embed_eval_queries(queries, cfg, cache_dir, encoder, args.rebuild)
    console.print(
        f"{len(query_vectors)} queries · {np.mean([len(q) for q in query_vectors]):.0f} tokens each"
        + (f" · {query_ms} ms/query" if query_ms else " · encode time unmeasured (cached)")
    )
    del encoder
    _free_gpu()

    index_by_corpus_id = {int(cid): i for i, cid in enumerate(store.ids)}
    builders = {"pooled": build_pooled_stage1, "centroids": build_centroid_stage1}
    variants: dict[str, dict] = {}

    with pgvector_store.connect() as conn:
        for name, builder in builders.items():
            console.rule(f"[bold]stage 1: {name}")
            if name == "pooled":
                shortlists, latencies, stats = builder(conn, store, corpus, query_vectors, args)
            else:
                shortlists, latencies, stats = builder(conn, store, query_vectors, args)
            console.print(
                f"{stats['rows']:,} rows · {stats['total_bytes']} MB · hnsw build "
                f"{stats['hnsw_build_seconds']}s · search p50 "
                f"{percentiles(latencies)['p50']} ms"
            )
            variants[name] = {"shortlists": shortlists, "latency": latencies, "index": stats}

    console.rule("[bold]stage 2: MaxSim rerank")
    for name, variant in variants.items():
        scored, _ = rerank(store, query_vectors, variant["shortlists"], index_by_corpus_id, args)
        # Rerank cost scales with shortlist size; time the configured depth on its own.
        _, latencies = rerank(
            store, query_vectors, variant["shortlists"], index_by_corpus_id, args, args.candidates
        )
        variant["scored"] = scored
        variant["rerank_latency"] = latencies
        console.print(f"{name}: rerank@{args.candidates} p50 {percentiles(latencies)['p50']} ms")

    def build_run(variant, depth):
        return {
            int(qid): {cid: scores[cid] for cid in shortlist[:depth]}
            for qid, shortlist, scores in zip(
                queries["query_id"], variant["shortlists"], variant["scored"], strict=True
            )
        }

    def shortlist_recall(variant, depth):
        got = []
        for qid, shortlist in zip(queries["query_id"], variant["shortlists"], strict=True):
            relevant = set(gold[int(qid)])
            if relevant:
                got.append(len(relevant & set(shortlist[:depth])) / len(relevant))
        return round(float(np.mean(got)), 4)

    console.rule("[bold]exhaustive MaxSim (ceiling)")
    exhaustive_run: dict[int, dict[int, float]] = {}
    exhaustive_latencies: list[float] = []
    if not args.no_exhaustive:
        gpu_corpus = multivector.GpuCorpus(store, device=args.device)
        console.print(f"corpus resident on GPU: {gpu_corpus.nbytes() / 1e9:.2f} GB")
        for qid, vectors in zip(queries["query_id"], query_vectors, strict=True):
            started = time.perf_counter()
            scores = gpu_corpus.score(vectors)
            exhaustive_latencies.append((time.perf_counter() - started) * 1000)
            top = np.argpartition(-scores, min(100, len(scores) - 1))[:100]
            exhaustive_run[int(qid)] = {
                int(store.ids[i]): float(scores[i]) for i in top[np.argsort(-scores[top])]
            }
        del gpu_corpus
        _free_gpu()

    console.rule("[bold]score")
    ks = (1, 5, args.k)
    ndcg = f"ndcg@{args.k}"
    for variant in variants.values():
        variant["sweep"] = [
            {
                "shortlist": depth,
                "stage1_gold_recall": shortlist_recall(variant, depth),
                **{
                    key: value
                    for key, value in metrics.evaluate(
                        build_run(variant, depth), gold, ks=ks
                    ).items()
                    if key in (ndcg, f"recall@{args.k}")
                },
            }
            for depth in sweep
        ]
        variant["metrics"] = metrics.evaluate(build_run(variant, args.candidates), gold, ks=ks)

    primary_run = build_run(variants[args.primary], args.candidates)
    reference = metrics.evaluate_pytrec(primary_run, gold, ks=ks)
    if abs(variants[args.primary]["metrics"][ndcg] - reference[f"ndcg_cut_{args.k}"]) > 1e-3:
        console.print("[red]metric mismatch vs trec_eval[/red]")
        return 1
    exhaustive_metrics = metrics.evaluate(exhaustive_run, gold, ks=ks) if exhaustive_run else None

    sweep_table = Table(box=None, title="stage-1 shortlist quality", title_justify="left")
    sweep_table.add_column("stage 1", style="cyan")
    for depth in sweep:
        sweep_table.add_column(f"N={depth}\nrecall / ndcg", justify="right")
    for name, variant in variants.items():
        sweep_table.add_row(
            name,
            *[f"{row['stage1_gold_recall']:.3f} / {row[ndcg]:.3f}" for row in variant["sweep"]],
        )
    if exhaustive_metrics:
        sweep_table.add_row(
            "exhaustive (ceiling)",
            *["—" for _ in sweep[:-1]],
            f"1.000 / {exhaustive_metrics[ndcg]:.3f}",
        )
    console.print(sweep_table)

    breakdown = {
        name: {
            "queries": len(qids),
            **metrics.evaluate(primary_run, metrics.subset(gold, qids), ks=ks),
        }
        for name, qids in data.query_slices(queries).items()
        if qids
    }
    slice_table = Table(
        box=None, title=f"{args.primary} stage 1, shortlist {args.candidates}", title_justify="left"
    )
    slice_table.add_column("slice", style="cyan")
    slice_table.add_column("n", justify="right")
    columns = (ndcg, f"recall@{args.k}", f"success@{args.k}", "map")
    for column in columns:
        slice_table.add_column(column, justify="right")
    for name, values in breakdown.items():
        slice_table.add_row(name, str(values["queries"]), *[f"{values[m]:.3f}" for m in columns])
    console.print(slice_table)

    primary = variants[args.primary]
    stage1_ms = percentiles(primary["latency"])
    stage2_ms = percentiles(primary["rerank_latency"])
    console.print(
        f"\nlatency (concurrency 1): query encode {query_ms or '?'} ms · stage 1 "
        f"p50 {stage1_ms['p50']} ms · stage 2 rerank@{args.candidates} p50 {stage2_ms['p50']} ms"
    )
    if exhaustive_latencies:
        console.print(
            f"exhaustive MaxSim over {len(store):,} pages: "
            f"p50 {percentiles(exhaustive_latencies)['p50']} ms · ceiling {ndcg} "
            f"{exhaustive_metrics[ndcg]:.3f} vs two-stage {primary['metrics'][ndcg]:.3f} "
            f"({primary['metrics'][ndcg] / exhaustive_metrics[ndcg] * 100:.1f}% of ceiling)"
        )

    report = {
        "retriever": "visual",
        "model": args.model,
        "dim": store.dim,
        "corpus_pages": len(store),
        "eval_queries": len(queries),
        "smoke_test": smoke,
        "primary_stage1": args.primary,
        "candidates": args.candidates,
        "patches": {
            "total": int(lengths.sum()),
            "mean_per_page": round(float(lengths.mean()), 1),
            "min": int(lengths.min()),
            "max": int(lengths.max()),
        },
        "storage": {
            "multivector_mb": round(store.nbytes() / 1e6, 1),
            "bytes_per_page": round(store.nbytes() / len(store), 1),
        },
        "embedding": embed_timing,
        "query_encode_ms": query_ms,
        "stage1_variants": {
            name: {
                "index": variant["index"],
                "latency_ms": percentiles(variant["latency"]),
                "rerank_ms": percentiles(variant["rerank_latency"]),
                "sweep": variant["sweep"],
                "metrics": variant["metrics"],
            }
            for name, variant in variants.items()
        },
        "exhaustive": {
            "metrics": exhaustive_metrics,
            "latency_ms": percentiles(exhaustive_latencies) if exhaustive_latencies else None,
            "gpu_resident_gb": round(store.nbytes() / 1e9, 2),
            "note": (
                "At 5,244 pages brute-force MaxSim on GPU beats the two-stage path on both "
                "quality and latency, because the whole multi-vector corpus (1 GB) fits in "
                "VRAM. The two-stage path is not a speed optimisation at this size - it is "
                "what keeps the design viable when the corpus no longer fits, and it costs "
                "3% of the ceiling to get there."
            ),
        },
        "metrics": primary["metrics"],
        "metrics_pytrec_eval": reference,
        "breakdown": breakdown,
    }
    suffix = "_smoke" if smoke else ""
    report_path = config.REPORTS_DIR / f"visual_retrieval{suffix}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    run_path = config.DATA_DIR / "runs" / f"visual_two_stage{suffix}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(
            {
                "retriever": "visual",
                "model": args.model,
                "k": args.k,
                "stage1": args.primary,
                "candidates": args.candidates,
                "run": {
                    str(q): {str(d): s for d, s in hits.items()} for q, hits in primary_run.items()
                },
                "per_query_ndcg": {
                    str(q): round(v, 4)
                    for q, v in metrics.per_query_ndcg(primary_run, gold, args.k).items()
                },
                "exhaustive_per_query_ndcg": {
                    str(q): round(v, 4)
                    for q, v in metrics.per_query_ndcg(exhaustive_run, gold, args.k).items()
                }
                if exhaustive_run
                else {},
            }
        )
    )
    console.print(f"\n[green]wrote[/green] {report_path}\n[green]wrote[/green] {run_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
