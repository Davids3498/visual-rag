"""MCU native-PDF-text/BGE-M3 retrieval, followed by the shared image generator."""

from __future__ import annotations

import gc
import importlib.util
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pypdf
import requests
from PIL import Image
from pypdf import PdfReader

from visual_rag import config, corpus, generation, ingest, pgvector_store, text_encoder

spec = importlib.util.spec_from_file_location(
    "mcu_eval", Path(__file__).with_name("12_mcu_evaluation.py")
)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def extract_pages(table):
    records = []
    for doc_id, group in table.groupby("doc_id", sort=True):
        path = config.MCU_PDF_DIR / f"{doc_id}.pdf"
        if set(group.doc_sha256) != {corpus.sha256_file(path)}:
            raise ValueError(f"Source hash mismatch: {doc_id}")
        pdf = PdfReader(path)
        for row in group.itertuples():
            records.append(
                {
                    "page_id": int(row.page_id),
                    "doc_id": doc_id,
                    "page_number": int(row.page_number),
                    "doc_sha256": row.doc_sha256,
                    "text": pdf.pages[row.page_number - 1].extract_text() or "",
                }
            )
    return pd.DataFrame(records).set_index("page_id").loc[table.page_id].reset_index()


def main():
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = config.REPORTS_DIR / f"mcu_text_{run_id}"
    output.mkdir(exist_ok=False)
    cache = config.MCU_DIR / f"text_baseline_{run_id}"
    cache.mkdir(exist_ok=False)
    print(f"Run directory: {output}", flush=True)
    table = pd.read_parquet(config.MCU_PAGE_TABLE)
    problems = ingest.table_problems(table, corpus.load_manifest())
    if problems:
        raise ValueError(problems)
    questions = [
        q
        for q in evaluation.read_json(evaluation.QUESTIONS)["questions"]
        if q["human_review"]["status"] == "approved"
    ]
    if len(questions) != 12:
        raise ValueError("Expected 12 approved questions")
    texts = extract_pages(table)
    texts.to_parquet(cache / "pages_text.parquet", index=False)
    print(
        f"Extracted {len(texts)} pinned pages; empty: {(texts.text.str.len() == 0).sum()}",
        flush=True,
    )
    cfg = text_encoder.EncoderConfig()
    model = text_encoder.load_encoder(cfg)
    stats = text_encoder.token_stats(model, texts.text.tolist(), cfg.max_seq_length)
    vectors, embed_seconds = text_encoder.encode(model, texts.text.tolist(), cfg)
    query_vectors, query_seconds = text_encoder.encode(
        model, [q["question"] for q in questions], cfg, show_progress=False
    )
    np.savez(
        cache / "embeddings.npz",
        page_ids=texts.page_id.to_numpy(),
        embeddings=vectors,
        query_vectors=query_vectors,
    )
    del model
    gc.collect()
    import torch

    torch.cuda.empty_cache()
    vector_table = pgvector_store.VectorTable(f"mcu_text_pages_{run_id.lower()}", vectors.shape[1])
    rankings = []
    with pgvector_store.connect() as conn:
        if conn.execute("SELECT to_regclass(%s)", (vector_table.name,)).fetchone()[0] is not None:
            raise ValueError("Refusing to overwrite an existing table")
        pgvector_store.create_table(conn, vector_table)
        pgvector_store.insert_pages(
            conn,
            vector_table,
            texts.page_id.tolist(),
            texts.doc_id.tolist(),
            texts.page_number.tolist(),
            texts.text.str.len().tolist(),
            vectors,
        )
        pgvector_store.create_hnsw_index(conn, vector_table, m=16, ef_construction=64)
        pgvector_store.configure_search(conn, 100)
        overlaps = []
        for q, v in zip(questions, query_vectors, strict=True):
            start = time.perf_counter()
            hits = pgvector_store.search(conn, vector_table, v, k=10)
            ms = (time.perf_counter() - start) * 1000
            exact = pgvector_store.search(conn, vector_table, v, k=10, exact=True)
            overlaps.append(len({p for p, _ in hits} & {p for p, _ in exact}) / 10)
            rankings.append((q, hits, ms))
        plan = pgvector_store.explain(conn, vector_table, query_vectors[0], k=10)
    vlm = generation.VLMConfig()
    response = requests.get(f"{vlm.base_url}/models", timeout=20)
    response.raise_for_status()
    run = {
        "evaluation_timestamp": datetime.now(UTC).isoformat(),
        "total_questions": 12,
        "served_models": response.json(),
        "per_question": [],
        "text_baseline": {
            "extraction": "pypdf native text, default extraction; not OCR",
            "pypdf_version": pypdf.__version__,
            "encoder": asdict(cfg),
            "token_stats": stats,
            "page_count": len(texts),
            "cache_path": str(cache),
            "index_table": vector_table.name,
            "hnsw_m": 16,
            "ef_construction": 64,
            "ef_search": 100,
            "embedding_seconds": embed_seconds,
            "query_embedding_seconds": query_seconds,
            "ann_recall_vs_exact_at_10": float(np.mean(overlaps)),
            "query_plan": plan,
        },
        "question_snapshot": questions,
    }
    by_id = table.set_index("page_id")
    for q, hits, search_ms in rankings:
        ranked = [
            {
                "corpus_id": int(pid),
                "doc_id": by_id.loc[pid].doc_id,
                "page_number": int(by_id.loc[pid].page_number),
                "score": float(score),
            }
            for pid, score in hits
        ]
        pages = []
        try:
            for p in ranked[:3]:
                with Image.open(by_id.loc[p["corpus_id"]].path) as im:
                    pages.append({**p, "image": im.convert("RGB")})
            payload = {
                "model": vlm.model,
                "messages": generation.build_messages(q["question"], pages, vlm),
                "max_tokens": vlm.max_tokens,
                "temperature": vlm.temperature,
            }
        finally:
            for p in pages:
                p["image"].close()
        start = time.perf_counter()
        response = requests.post(
            f"{vlm.base_url}/chat/completions", json=payload, timeout=vlm.timeout
        )
        response.raise_for_status()
        raw = response.json()
        record = {
            "question_id": q["question_id"],
            "question": q["question"],
            "retrieved_pages": ranked,
            "request": payload,
            "retrieval_timing_ms": search_ms,
            "generation": {
                "answer": raw["choices"][0]["message"]["content"],
                "raw_response": raw,
                "shown_pages": [p["corpus_id"] for p in ranked[:3]],
                "latency_ms": (time.perf_counter() - start) * 1000,
            },
        }
        (output / f"{q['question_id']}.json").write_text(json.dumps(record, indent=2))
        run["per_question"].append(record)
        print(f"{q['question_id']}: {raw['choices'][0]['finish_reason']}", flush=True)
    report = evaluation.rescore(run, questions, evaluation.read_json(evaluation.BASELINE), table)
    (output / "mcu_evaluation.json").write_text(json.dumps(report, indent=2))
    (output / "mcu_evaluation.md").write_text(evaluation.markdown(report))
    print(json.dumps(report["retrieval_metrics"], indent=2), flush=True)


if __name__ == "__main__":
    main()
