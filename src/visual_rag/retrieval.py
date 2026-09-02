"""The serving-path visual retriever: query in, ranked pages out.

`scripts/04_visual_retrieval.py` is the *experiment* harness — it builds two stage-1 variants,
sweeps shortlist depths and reports a ceiling. This module is the single path that actually
serves traffic in steps 5-7, with the configuration that step 4 calibrated:

    16 centroids/page -> indexed top-50 per query token -> union -> MaxSim rerank of 100.

`tests/test_retrieval.py` asserts this reproduces the ranking of the scored run, so the served
system cannot quietly drift away from the one the benchmark blessed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from . import multivector, pgvector_store, visual_encoder


@dataclass
class RetrievalConfig:
    centroid_table: str = "visual_page_centroids"
    per_token_k: int = 50
    candidates: int = 100
    ef_search: int = 200
    device: str = "cuda:0"
    encoder: visual_encoder.VisualEncoderConfig = field(
        default_factory=visual_encoder.VisualEncoderConfig
    )


@dataclass
class Retrieved:
    pages: list[tuple[int, float]]  # (corpus_id, MaxSim score), best first
    encode_ms: float = 0.0
    stage1_ms: float = 0.0
    stage2_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return self.encode_ms + self.stage1_ms + self.stage2_ms

    @property
    def corpus_ids(self) -> list[int]:
        return [corpus_id for corpus_id, _ in self.pages]


class TwoStageRetriever:
    """Stage 1 in pgvector, stage 2 on the GPU. The model is loaded only if a text query
    arrives — with pre-encoded query vectors this holds no VRAM at all, which is what lets it
    share a 24 GB card with the generator."""

    def __init__(
        self, store: multivector.MultiVectorStore, conn, cfg: RetrievalConfig | None = None
    ):
        self.store = store
        self.conn = conn
        self.cfg = cfg or RetrievalConfig()
        self.table = pgvector_store.VectorTable(self.cfg.centroid_table, store.dim)
        self.index_by_corpus_id = {int(cid): i for i, cid in enumerate(store.ids)}
        self._encoder = None
        pgvector_store.configure_search(conn, self.cfg.ef_search)

    def warm(self) -> float:
        """Page the multi-vector store into memory before serving traffic.

        The store is memory-mapped, so a cold process pays disk latency on the first queries
        that touch a given page: measured p50 for stage 2 was 435 ms cold against 6 ms warm.
        A server that skips this reports its own warm-up as its latency.
        """
        started = time.perf_counter()
        float(np.asarray(self.store.vectors[::64]).sum())
        return (time.perf_counter() - started) * 1000

    def load_encoder(self) -> None:
        if self._encoder is None:
            self._encoder = visual_encoder.load_encoder(self.cfg.encoder)

    def encode(self, query: str) -> tuple[np.ndarray, float]:
        self.load_encoder()
        model, processor = self._encoder
        vectors, seconds = visual_encoder.embed_queries(model, processor, [query], self.cfg.encoder)
        return vectors[0], seconds * 1000

    def retrieve(self, query, k: int = 10) -> Retrieved:
        """`query` is either the question text or its pre-computed token vectors."""
        encode_ms = 0.0
        if isinstance(query, str):
            query_vectors, encode_ms = self.encode(query)
        else:
            query_vectors = np.asarray(query)

        started = time.perf_counter()
        shortlist = pgvector_store.search_centroids(
            self.conn,
            self.table,
            query_vectors,
            per_token_k=self.cfg.per_token_k,
            limit=self.cfg.candidates,
        )
        stage1_ms = (time.perf_counter() - started) * 1000

        candidates = [corpus_id for corpus_id, _ in shortlist]
        indices = [self.index_by_corpus_id[corpus_id] for corpus_id in candidates]
        started = time.perf_counter()
        scores = multivector.score_pages(self.store, query_vectors, indices, device=self.cfg.device)
        stage2_ms = (time.perf_counter() - started) * 1000

        order = np.argsort(-scores)[:k]
        return Retrieved(
            pages=[(candidates[i], float(scores[i])) for i in order],
            encode_ms=encode_ms,
            stage1_ms=stage1_ms,
            stage2_ms=stage2_ms,
        )
