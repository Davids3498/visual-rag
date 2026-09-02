"""pgvector-backed single-vector ANN index.

Step 2 stores one embedding per page here. Step 3 reuses the same table shape for ColQwen2's
*pooled* page vector — the cheap first stage of the two-stage search — so the schema is
parameterised rather than hard-coded to the text baseline.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

DEFAULT_DSN = os.environ.get("VRAG_PG_DSN", "postgresql://vrag:vrag@localhost:5434/vrag")


@dataclass(frozen=True)
class VectorTable:
    """A page-level vector table. `dim` must match the encoder that fills it."""

    name: str
    dim: int

    def __post_init__(self):
        if not self.name.isidentifier():
            raise ValueError(f"unsafe table name {self.name!r}")


TEXT_PAGES = VectorTable("text_pages", 1024)  # BAAI/bge-m3 dense


@contextmanager
def connect(dsn: str | None = None):
    """Autocommit connection with the pgvector type adapters registered."""
    with psycopg.connect(dsn or DEFAULT_DSN, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        yield conn


def create_table(conn: psycopg.Connection, table: VectorTable, drop: bool = False) -> None:
    if drop:
        conn.execute(f"DROP TABLE IF EXISTS {table.name}")
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table.name} (
            corpus_id   INTEGER PRIMARY KEY,
            doc_id      TEXT NOT NULL,
            page_number INTEGER,
            n_chars     INTEGER,
            embedding   vector({table.dim}) NOT NULL
        )
        """
    )


def create_centroid_table(conn: psycopg.Connection, table: VectorTable, drop: bool = False) -> None:
    """Schema for several vectors per page — the multi-vector stage-1 index.

    One row per (page, centroid) instead of one per page, because a page that contains both a
    pin table and a wiring diagram is two different things to a query, and a single averaged
    vector represents neither.
    """
    if drop:
        conn.execute(f"DROP TABLE IF EXISTS {table.name}")
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table.name} (
            corpus_id   INTEGER NOT NULL,
            centroid_id SMALLINT NOT NULL,
            embedding   vector({table.dim}) NOT NULL,
            PRIMARY KEY (corpus_id, centroid_id)
        )
        """
    )


def insert_centroids(
    conn: psycopg.Connection,
    table: VectorTable,
    corpus_ids: Sequence[int],
    centroids: np.ndarray,
) -> float:
    """Binary COPY `[n_pages, k, dim]` centroids in. Returns seconds elapsed."""
    if centroids.ndim != 3 or centroids.shape[2] != table.dim:
        raise ValueError(f"expected (n, k, {table.dim}), got {centroids.shape}")
    started = time.perf_counter()
    with (
        conn.cursor() as cur,
        cur.copy(
            f"COPY {table.name} (corpus_id, centroid_id, embedding) FROM STDIN WITH (FORMAT BINARY)"
        ) as copy,
    ):
        copy.set_types(["integer", "smallint", "vector"])
        for cid, page in zip(corpus_ids, centroids, strict=True):
            for centroid_id, vector in enumerate(page):
                copy.write_row([int(cid), centroid_id, vector])
    return time.perf_counter() - started


def search_centroids(
    conn: psycopg.Connection,
    table: VectorTable,
    query_vectors: np.ndarray,
    per_token_k: int = 20,
    limit: int = 100,
) -> list[tuple[int, float]]:
    """Late-interaction candidate generation: ANN per query token, then union by page.

    One round trip: the query tokens go in as a `vector[]` and a LATERAL join runs one indexed
    top-k per token. Pages are ranked by the sum of the token similarities they were retrieved
    for — an approximation that only has to get *membership* right, since stage 2 rescores the
    shortlist exactly.
    """
    vectors = [np.asarray(v, dtype=np.float32) for v in query_vectors]
    rows = conn.execute(
        f"""
        SELECT corpus_id, sum(sim) AS score
        FROM unnest(%s::vector[]) AS q(v)
        CROSS JOIN LATERAL (
            SELECT corpus_id, 1 - (embedding <=> q.v) AS sim
            FROM {table.name}
            ORDER BY embedding <=> q.v
            LIMIT %s
        ) AS hits
        GROUP BY corpus_id
        ORDER BY score DESC
        LIMIT %s
        """,
        (vectors, int(per_token_k), int(limit)),
    ).fetchall()
    return [(int(cid), float(score)) for cid, score in rows]


def count(conn: psycopg.Connection, table: VectorTable) -> int:
    return conn.execute(f"SELECT count(*) FROM {table.name}").fetchone()[0]


def insert_pages(
    conn: psycopg.Connection,
    table: VectorTable,
    corpus_ids: Sequence[int],
    doc_ids: Sequence[str],
    page_numbers: Sequence[int],
    n_chars: Sequence[int],
    embeddings: np.ndarray,
) -> float:
    """Binary COPY the whole corpus in. Returns seconds elapsed."""
    if embeddings.shape != (len(corpus_ids), table.dim):
        raise ValueError(f"expected ({len(corpus_ids)}, {table.dim}), got {embeddings.shape}")
    started = time.perf_counter()
    columns = "corpus_id, doc_id, page_number, n_chars, embedding"
    with (
        conn.cursor() as cur,
        cur.copy(f"COPY {table.name} ({columns}) FROM STDIN WITH (FORMAT BINARY)") as copy,
    ):
        copy.set_types(["integer", "text", "integer", "integer", "vector"])
        for cid, doc, page, chars, vec in zip(
            corpus_ids, doc_ids, page_numbers, n_chars, embeddings, strict=True
        ):
            copy.write_row([int(cid), str(doc), int(page), int(chars), vec])
    return time.perf_counter() - started


def create_hnsw_index(
    conn: psycopg.Connection,
    table: VectorTable,
    m: int = 16,
    ef_construction: int = 64,
) -> float:
    """Build the cosine HNSW index. Returns build seconds.

    Built *after* the bulk load on purpose: incremental inserts into an existing HNSW graph
    are far slower than one bulk build.
    """
    started = time.perf_counter()
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS {table.name}_hnsw ON {table.name} "
        f"USING hnsw (embedding vector_cosine_ops) WITH (m = {int(m)}, "
        f"ef_construction = {int(ef_construction)})"
    )
    conn.execute(f"ANALYZE {table.name}")
    return time.perf_counter() - started


def storage(conn: psycopg.Connection, table: VectorTable) -> dict[str, int]:
    row = conn.execute(
        "SELECT pg_total_relation_size(%s), pg_relation_size(%s), "
        "COALESCE(pg_relation_size(%s), 0)",
        (table.name, table.name, f"{table.name}_hnsw"),
    ).fetchone()
    return {"total_bytes": row[0], "table_bytes": row[1], "index_bytes": row[2]}


def configure_search(conn: psycopg.Connection, ef_search: int | None = None) -> None:
    """Set the HNSW search-effort GUC once per connection.

    Postgres does not accept bound parameters in SET, and issuing it per query would add a
    round trip to every measured latency, so it is a separate session-level call.
    """
    if ef_search is not None:
        conn.execute(f"SET hnsw.ef_search = {int(ef_search)}")


def search(
    conn: psycopg.Connection,
    table: VectorTable,
    query: np.ndarray,
    k: int = 10,
    ef_search: int | None = None,
    exact: bool = False,
) -> list[tuple[int, float]]:
    """Top-k pages for one query vector, as (corpus_id, cosine similarity).

    `exact=True` forces a full scan, which is how the ANN recall in the report is measured:
    an index that quietly drops relevant pages would otherwise be indistinguishable from a
    weak retriever.
    """
    with conn.cursor() as cur:
        if exact:
            cur.execute("SET enable_indexscan = off")
            cur.execute("SET enable_bitmapscan = off")
        elif ef_search is not None:
            cur.execute(f"SET hnsw.ef_search = {int(ef_search)}")
        try:
            cur.execute(
                f"SELECT corpus_id, 1 - (embedding <=> %s) AS score FROM {table.name} "
                f"ORDER BY embedding <=> %s LIMIT %s",
                (query, query, int(k)),
            )
            rows = cur.fetchall()
        finally:
            if exact:
                cur.execute("RESET enable_indexscan")
                cur.execute("RESET enable_bitmapscan")
    return [(int(cid), float(score)) for cid, score in rows]


def explain(conn: psycopg.Connection, table: VectorTable, query: np.ndarray, k: int = 10) -> str:
    """Query plan — the cheap way to prove the HNSW index is actually being used."""
    rows = conn.execute(
        f"EXPLAIN (ANALYZE, BUFFERS) SELECT corpus_id FROM {table.name} "
        f"ORDER BY embedding <=> %s LIMIT %s",
        (query, int(k)),
    ).fetchall()
    return "\n".join(row[0] for row in rows)
