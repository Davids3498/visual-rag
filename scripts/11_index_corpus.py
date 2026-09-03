"""Step 11 — embed the MCU pages with ColQwen2 and build the stage-1 index.

Nothing new is invented here: this is the exact retrieval path step 4 calibrated (16 centroids
per page, indexed per query token, MaxSim rerank of the shortlist), pointed at the corpus built
in steps 9 and 10. That is the point — the pipeline was validated on a public benchmark, and
Part 2 changes only the data underneath it.

    make index            # embed, cluster, index, smoke-test
    make index-rebuild    # re-embed from scratch (after re-rendering, say)

Produces:
  data/embeddings/mcu_<model>/   ragged page multi-vectors (~230 MB)
  mcu_page_centroids (pgvector)  16 centroids per page + HNSW
  reports/mcu_index.json         counts, storage, timings
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from visual_rag import config, corpus, ingest, multivector, pgvector_store, visual_encoder

console = Console()

# Three questions of the kind Part 2 is about: specific, page-localised, and answerable only
# from a table or a register map. Used as a smoke test, never as a metric.
SMOKE_QUERIES = [
    "Which GPIO pins can be used for I2C1 SDA?",
    "What is the maximum current sunk by an I/O pin?",
    "What is the workaround for the I2C analog filter limitation?",
]


def embed_pages(table, cfg, cache_dir: Path, rebuild: bool):
    """Embed every page image into ragged multi-vectors, caching the store on disk."""
    page_ids = table["page_id"].to_numpy(dtype=np.int64)
    if cache_dir.exists() and not rebuild:
        store = multivector.MultiVectorStore.load(cache_dir)
        if len(store) == len(page_ids) and np.array_equal(store.ids, page_ids):
            console.print(f"reusing cached page embeddings [dim]{cache_dir}[/dim]")
            return store, None
        console.print("[yellow]cached embeddings do not match the page table — re-embedding")

    console.print(f"loading [cyan]{cfg.model_name}[/cyan] on {cfg.device} ({cfg.dtype})")
    model, processor = visual_encoder.load_encoder(cfg)
    paths = list(table["path"])
    pages: list[np.ndarray] = []
    started = time.perf_counter()
    for start in tqdm(range(0, len(paths), cfg.batch_size), desc="embedding", unit="batch"):
        batch = paths[start : start + cfg.batch_size]
        images = [Image.open(p).convert("RGB") for p in batch]
        try:
            pages.extend(visual_encoder.embed_images(model, processor, images, cfg))
        finally:
            for image in images:
                image.close()
    seconds = time.perf_counter() - started

    del model, processor
    _free_gpu()
    store = multivector.MultiVectorStore.from_pages(pages, page_ids)
    store.save(cache_dir)
    return store, seconds


def _free_gpu() -> None:
    import gc

    import torch

    gc.collect()
    torch.cuda.empty_cache()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=visual_encoder.DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=8, help="8 measured fastest on a 3090")
    parser.add_argument("--centroids", type=int, default=16, help="stage-1 vectors per page")
    parser.add_argument("--rebuild", action="store_true", help="re-embed even if cached")
    parser.add_argument("--keep-index", action="store_true", help="do not drop the existing table")
    parser.add_argument("--no-smoke", action="store_true", help="skip the sample queries")
    args = parser.parse_args()

    config.ensure_dirs()
    manifest = corpus.load_manifest()
    table = ingest.load_page_table()
    problems = ingest.table_problems(table, manifest)
    for line in problems:
        console.print(f"[red]{line}[/red]")
    if problems:
        return 1

    console.rule("[bold]corpus")
    console.print(
        f"{len(table):,} pages from {table['doc_id'].nunique()} documents, "
        f"{table['bytes'].sum() / 1e6:.0f} MB of images"
    )

    # --- 1. embed
    console.rule("[bold]embedding")
    cfg = visual_encoder.VisualEncoderConfig(model_name=args.model, batch_size=args.batch_size)
    slug = args.model.replace("/", "_")
    cache_dir = config.DATA_DIR / "embeddings" / f"mcu_{slug}"
    store, embed_seconds = embed_pages(table, cfg, cache_dir, args.rebuild)
    patches = store.lengths
    if embed_seconds:
        console.print(
            f"{len(store):,} pages in {embed_seconds:.0f}s "
            f"([green]{len(store) / embed_seconds:.1f} pages/s[/green])"
        )

    # --- 2. cluster into the stage-1 representation
    console.rule("[bold]stage-1 centroids")
    started = time.perf_counter()
    centroids = multivector.page_centroids(store, k=args.centroids)
    centroid_seconds = time.perf_counter() - started
    console.print(
        f"{args.centroids} centroids/page in {centroid_seconds:.0f}s "
        f"({centroids.shape[0] * centroids.shape[1]:,} index rows)"
    )
    _free_gpu()

    # --- 3. load into pgvector and build the index
    console.rule("[bold]index")
    vector_table = pgvector_store.VectorTable(config.MCU_CENTROID_TABLE, store.dim)
    with pgvector_store.connect() as conn:
        pgvector_store.create_centroid_table(conn, vector_table, drop=not args.keep_index)
        insert_seconds = pgvector_store.insert_centroids(conn, vector_table, store.ids, centroids)
        index_seconds = pgvector_store.create_hnsw_index(conn, vector_table)
        rows = pgvector_store.count(conn, vector_table)
        storage = pgvector_store.storage(conn, vector_table)
        console.print(
            f"{rows:,} rows loaded in {insert_seconds:.1f}s, HNSW built in {index_seconds:.1f}s, "
            f"{storage['total_bytes'] / 1e6:.0f} MB in postgres"
        )

        # --- 4. smoke test: does a question actually land on a plausible page?
        results = []
        if not args.no_smoke:
            console.rule("[bold]smoke queries")
            from visual_rag import retrieval

            retriever = retrieval.TwoStageRetriever(
                store, conn, retrieval.RetrievalConfig(centroid_table=vector_table.name)
            )
            retriever.warm()
            by_id = table.set_index("page_id")
            for query in SMOKE_QUERIES:
                hits = retriever.retrieve(query, k=5)
                out = Table(box=None, title=query, title_justify="left", title_style="cyan")
                out.add_column("page")
                out.add_column("document", style="cyan")
                out.add_column("score", justify="right")
                for page_id, score in hits.pages:
                    row = by_id.loc[page_id]
                    out.add_row(f"p{row['page_number']}", row["doc_id"], f"{score:.1f}")
                console.print(out)
                console.print(
                    f"  [dim]encode {hits.encode_ms:.0f} ms, stage1 {hits.stage1_ms:.0f} ms, "
                    f"stage2 {hits.stage2_ms:.0f} ms[/dim]\n"
                )
                results.append(
                    {
                        "query": query,
                        "pages": [
                            {
                                "page_id": int(pid),
                                "doc_id": by_id.loc[pid]["doc_id"],
                                "page_number": int(by_id.loc[pid]["page_number"]),
                                "score": round(float(score), 2),
                            }
                            for pid, score in hits.pages
                        ],
                        "encode_ms": round(hits.encode_ms, 1),
                        "stage1_ms": round(hits.stage1_ms, 1),
                        "stage2_ms": round(hits.stage2_ms, 1),
                    }
                )

    report = {
        "model": args.model,
        "pages": len(store),
        "dim": store.dim,
        "patches_total": int(patches.sum()),
        "patches_per_page_mean": round(float(patches.mean()), 1),
        "embeddings_dir": str(cache_dir),
        "embeddings_bytes": store.nbytes(),
        "embed_seconds": round(embed_seconds, 1) if embed_seconds else None,
        "centroids_per_page": args.centroids,
        "centroid_seconds": round(centroid_seconds, 1),
        "index_rows": rows,
        "index_insert_seconds": round(insert_seconds, 1),
        "index_build_seconds": round(index_seconds, 1),
        "postgres": storage,
        "smoke_queries": results,
    }
    path = config.REPORTS_DIR / "mcu_index.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    console.print(f"written {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
