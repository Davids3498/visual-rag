"""Late-interaction scoring tests.

MaxSim is the whole visual retriever; a subtle bug here (padding counted as a real patch, a
transposed einsum) produces plausible-looking numbers rather than a crash, so it is checked
against colpali-engine's own scorer as well as a naive reference.
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from visual_rag import multivector  # noqa: E402

DIM = 16


def random_store(seed: int = 0, n_pages: int = 12, dim: int = DIM):
    rng = np.random.default_rng(seed)
    pages = []
    for _ in range(n_pages):
        vectors = rng.normal(size=(rng.integers(5, 20), dim)).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        pages.append(vectors.astype(np.float16))
    ids = np.arange(100, 100 + n_pages, dtype=np.int64)
    return multivector.MultiVectorStore.from_pages(pages, ids), pages


def naive_maxsim(query: np.ndarray, page: np.ndarray) -> float:
    """Sum over query tokens of the best matching patch — the definition, written out."""
    return float(sum((query.astype(np.float32) @ page.astype(np.float32).T).max(axis=1)))


def test_ragged_storage_round_trips(tmp_path):
    store, pages = random_store()
    store.save(tmp_path)
    loaded = multivector.MultiVectorStore.load(tmp_path)
    assert len(loaded) == len(pages)
    assert np.array_equal(loaded.lengths, np.array([len(p) for p in pages]))
    for i, page in enumerate(pages):
        assert np.array_equal(loaded.get(i), page)


def test_pooled_vectors_are_unit_length():
    store, _ = random_store()
    pooled = store.pooled()
    assert pooled.shape == (len(store), DIM)
    assert np.allclose(np.linalg.norm(pooled, axis=1), 1.0, atol=1e-5)


def test_score_pages_matches_the_definition():
    store, pages = random_store()
    rng = np.random.default_rng(1)
    query = rng.normal(size=(7, DIM)).astype(np.float32)
    query /= np.linalg.norm(query, axis=1, keepdims=True)

    scores = multivector.score_pages(store, query, range(len(store)), device="cpu", dtype="float32")
    expected = [naive_maxsim(query, page) for page in pages]
    assert scores == pytest.approx(expected, abs=1e-2)


def test_padding_cannot_win_the_max():
    """A short page must not be rewarded for its padding when every real patch scores < 0."""
    long_page = np.full((10, DIM), -0.5, dtype=np.float16)
    short_page = np.full((2, DIM), -0.5, dtype=np.float16)
    store = multivector.MultiVectorStore.from_pages(
        [long_page, short_page], np.array([1, 2], dtype=np.int64)
    )
    query = np.ones((3, DIM), dtype=np.float32)
    scores = multivector.score_pages(store, query, [0, 1], device="cpu", dtype="float32")
    # Both pages are identical apart from length, so their scores must match exactly; a zero
    # pad would give the short page a max of 0 per query token instead of a negative one.
    assert scores[0] == pytest.approx(scores[1], abs=1e-3)
    assert scores[0] < 0


def test_agrees_with_colpali_engine_scorer():
    """Cross-check against the reference implementation the ViDoRe results come from."""
    processing = pytest.importorskip("colpali_engine.utils.processing_utils")
    store, pages = random_store(seed=3)
    rng = np.random.default_rng(4)
    queries = [rng.normal(size=(n, DIM)).astype(np.float32) for n in (5, 9)]
    queries = [q / np.linalg.norm(q, axis=1, keepdims=True) for q in queries]

    reference = processing.BaseVisualRetrieverProcessor.score_multi_vector(
        [torch.tensor(q, dtype=torch.float32) for q in queries],
        [torch.tensor(p.astype(np.float32)) for p in pages],
        device="cpu",
    )
    for i, query in enumerate(queries):
        mine = multivector.score_pages(
            store, query, range(len(store)), device="cpu", dtype="float32"
        )
        assert mine == pytest.approx(reference[i].numpy(), abs=1e-2)


def test_two_stage_over_the_whole_corpus_equals_exhaustive():
    """With no shortlist truncation the two-stage path must reproduce brute force exactly."""
    store, pages = random_store(seed=5, n_pages=20)
    rng = np.random.default_rng(6)
    query = rng.normal(size=(6, DIM)).astype(np.float32)

    everything = multivector.score_pages(
        store, query, range(len(store)), device="cpu", dtype="float32"
    )
    shortlist = list(np.argsort(-everything)[:8])
    reranked = multivector.score_pages(store, query, shortlist, device="cpu", dtype="float32")
    assert list(np.array(shortlist)[np.argsort(-reranked)]) == list(np.argsort(-everything)[:8])


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a GPU")
def test_gpu_corpus_matches_chunked_scoring():
    store, _ = random_store(seed=7, n_pages=30)
    rng = np.random.default_rng(8)
    query = rng.normal(size=(5, DIM)).astype(np.float32)
    gpu = multivector.GpuCorpus(store, device="cuda:0", dtype="float16")
    assert gpu.score(query) == pytest.approx(
        multivector.score_pages(store, query, range(len(store)), device="cuda:0"), abs=5e-2
    )


def test_centroids_are_unit_length_and_shaped_per_page():
    store, _ = random_store(seed=11, n_pages=6)
    centroids = multivector.page_centroids(store, k=4, iterations=5, device="cpu")
    assert centroids.shape == (len(store), 4, DIM)
    assert np.allclose(np.linalg.norm(centroids, axis=2), 1.0, atol=1e-4)


def test_centroids_represent_a_page_better_than_its_mean():
    """The whole reason stage 1 uses centroids: one averaged vector represents nothing well."""
    rng = np.random.default_rng(12)
    # A page with two clearly distinct regions - a table and a diagram, in effect.
    region_a = rng.normal(loc=[3.0] + [0.0] * (DIM - 1), scale=0.05, size=(40, DIM))
    region_b = rng.normal(loc=[0.0, 3.0] + [0.0] * (DIM - 2), scale=0.05, size=(40, DIM))
    page = np.concatenate([region_a, region_b]).astype(np.float32)
    page /= np.linalg.norm(page, axis=1, keepdims=True)
    store = multivector.MultiVectorStore.from_pages(
        [page.astype(np.float16)], np.array([1], dtype=np.int64)
    )

    centroids = multivector.page_centroids(store, k=2, iterations=10, device="cpu")[0]
    pooled = store.pooled()[0]
    # A query that looks like one region should match a centroid far better than the mean.
    query = page[0]
    assert float(np.max(centroids @ query)) > float(pooled @ query)
