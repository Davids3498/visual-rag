"""The served retriever must be the retriever that was calibrated.

Steps 5-7 serve `visual_rag.retrieval`, while the NDCG numbers in the README came from
`scripts/04_visual_retrieval.py`. If those two paths drift apart, the system in production is
not the system the benchmark blessed — so this test pins one to the other.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from visual_rag import config, multivector

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("torch")

from visual_rag import pgvector_store, retrieval  # noqa: E402

CACHE = config.DATA_DIR / "embeddings" / "visual_vidore_colqwen2-v1.0"
RUN = config.DATA_DIR / "runs" / "visual_two_stage.json"


@pytest.fixture(scope="module")
def served():
    if not CACHE.exists() or not RUN.exists():
        pytest.skip("visual embeddings/run not built — run `make visual`")
    store = multivector.MultiVectorStore.load(CACHE)
    queries = multivector.MultiVectorStore.load(CACHE.parent / f"{CACHE.name}_queries", mmap=False)
    try:
        with pgvector_store.connect() as conn:
            if (
                pgvector_store.count(conn, pgvector_store.VectorTable("visual_page_centroids", 128))
                == 0
            ):
                pytest.skip("centroid index empty — run `make visual`")
            yield retrieval.TwoStageRetriever(store, conn), queries, json.loads(RUN.read_text())
    except psycopg.OperationalError:
        pytest.skip("pgvector not reachable — run `make db-up`")
    except psycopg.errors.UndefinedTable:
        pytest.skip("centroid table missing — run `make visual`")


def test_serving_path_reproduces_the_scored_run(served):
    retriever, queries, run = served
    scored = run["run"]
    checked = 0
    for i, query_id in enumerate(queries.ids[:15]):
        expected = sorted(scored[str(int(query_id))].items(), key=lambda kv: -kv[1])[:5]
        expected_ids = [int(doc) for doc, _ in expected]
        got = retriever.retrieve(queries.get(i), k=5).corpus_ids
        # Stage 1 is an ANN over an HNSW graph, so an occasional swap deep in the list is
        # expected; the top hit and the bulk of the ranking must not move.
        assert got[0] == expected_ids[0], f"query {query_id}: top hit changed"
        assert len(set(got) & set(expected_ids)) >= 4, f"query {query_id}: {got} vs {expected_ids}"
        checked += 1
    assert checked == 15


def test_retrieve_reports_stage_timings(served):
    retriever, queries, _ = served
    result = retriever.retrieve(queries.get(0), k=10)
    assert len(result.pages) == 10
    assert result.stage1_ms > 0 and result.stage2_ms > 0
    assert result.encode_ms == 0.0  # pre-encoded query: no model loaded, no VRAM held
    assert result.total_ms == pytest.approx(result.encode_ms + result.stage1_ms + result.stage2_ms)


def test_scores_are_descending(served):
    retriever, queries, _ = served
    scores = [score for _, score in retriever.retrieve(queries.get(3), k=10).pages]
    assert scores == sorted(scores, reverse=True)
    assert not np.isnan(scores).any()
