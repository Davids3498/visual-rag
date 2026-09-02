"""Round-trip test for the vector store. Skipped when the container isn't running."""

from __future__ import annotations

import numpy as np
import pytest

psycopg = pytest.importorskip("psycopg")

from visual_rag import pgvector_store  # noqa: E402

TABLE = pgvector_store.VectorTable("test_vectors_roundtrip", 8)


@pytest.fixture()
def conn():
    try:
        with pgvector_store.connect() as connection:
            yield connection
            connection.execute(f"DROP TABLE IF EXISTS {TABLE.name}")
    except psycopg.OperationalError as exc:
        pytest.skip(f"pgvector not reachable ({exc.__class__.__name__}) — run `make db-up`")


def _unit(vector) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    return array / np.linalg.norm(array)


def test_insert_and_search_returns_nearest_first(conn):
    pgvector_store.create_table(conn, TABLE, drop=True)
    vectors = np.stack(
        [
            _unit([1, 0, 0, 0, 0, 0, 0, 0]),
            _unit([0.9, 0.1, 0, 0, 0, 0, 0, 0]),
            _unit([0, 1, 0, 0, 0, 0, 0, 0]),
        ]
    )
    pgvector_store.insert_pages(
        conn, TABLE, [1, 2, 3], ["d", "d", "d"], [1, 2, 3], [10, 10, 10], vectors
    )
    assert pgvector_store.count(conn, TABLE) == 3

    hits = pgvector_store.search(conn, TABLE, vectors[0], k=3)
    assert [cid for cid, _ in hits] == [1, 2, 3]
    assert hits[0][1] == pytest.approx(1.0, abs=1e-5)  # cosine similarity with itself


def test_dimension_mismatch_is_caught_before_the_database(conn):
    pgvector_store.create_table(conn, TABLE, drop=True)
    with pytest.raises(ValueError):
        pgvector_store.insert_pages(
            conn, TABLE, [1], ["d"], [1], [1], np.zeros((1, 4), dtype=np.float32)
        )


def test_exact_search_agrees_with_the_index(conn):
    """If ANN and exact disagree on a tiny corpus, the index is misconfigured, not just lossy."""
    pgvector_store.create_table(conn, TABLE, drop=True)
    rng = np.random.default_rng(0)
    vectors = np.stack([_unit(rng.normal(size=8)) for _ in range(50)])
    ids = list(range(1, 51))
    pgvector_store.insert_pages(conn, TABLE, ids, ["d"] * 50, ids, [10] * 50, vectors)
    pgvector_store.create_hnsw_index(conn, TABLE)
    query = _unit(rng.normal(size=8))
    approx = [cid for cid, _ in pgvector_store.search(conn, TABLE, query, k=5, ef_search=64)]
    exact = [cid for cid, _ in pgvector_store.search(conn, TABLE, query, k=5, exact=True)]
    assert approx == exact


def test_unsafe_table_names_are_rejected():
    with pytest.raises(ValueError):
        pgvector_store.VectorTable("pages; DROP TABLE users", 8)


CENTROIDS = pgvector_store.VectorTable("test_centroids_roundtrip", 8)


def test_centroid_search_unions_pages_across_query_tokens(conn):
    """Stage-1 candidate generation: each query token retrieves, pages are unioned."""
    pgvector_store.create_centroid_table(conn, CENTROIDS, drop=True)
    # page 1's two centroids each match a different query token; page 2 matches neither.
    centroids = np.stack(
        [
            np.stack([_unit([1, 0, 0, 0, 0, 0, 0, 0]), _unit([0, 1, 0, 0, 0, 0, 0, 0])]),
            np.stack([_unit([0, 0, 1, 0, 0, 0, 0, 0]), _unit([0, 0, 0, 1, 0, 0, 0, 0])]),
        ]
    )
    pgvector_store.insert_centroids(conn, CENTROIDS, [1, 2], centroids)
    assert pgvector_store.count(conn, CENTROIDS) == 4

    query = np.stack([_unit([1, 0, 0, 0, 0, 0, 0, 0]), _unit([0, 1, 0, 0, 0, 0, 0, 0])])
    hits = pgvector_store.search_centroids(conn, CENTROIDS, query, per_token_k=1, limit=10)
    assert hits[0][0] == 1
    assert hits[0][1] == pytest.approx(2.0, abs=1e-4)  # both tokens matched page 1 exactly
    conn.execute(f"DROP TABLE IF EXISTS {CENTROIDS.name}")


def test_centroid_shape_is_validated(conn):
    pgvector_store.create_centroid_table(conn, CENTROIDS, drop=True)
    with pytest.raises(ValueError):
        pgvector_store.insert_centroids(conn, CENTROIDS, [1], np.zeros((1, 2, 4), dtype=np.float32))
    conn.execute(f"DROP TABLE IF EXISTS {CENTROIDS.name}")
