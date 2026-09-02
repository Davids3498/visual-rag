"""Unit tests for the eval-set construction, plus invariants on the built artifacts."""

from __future__ import annotations

import pandas as pd
import pytest

from visual_rag import config, data


def test_check_row_counts_accepts_the_card():
    assert data.check_row_counts(dict(config.EXPECTED_ROWS)) == []


def test_check_row_counts_reports_every_drift():
    counts = dict(config.EXPECTED_ROWS)
    counts["corpus"] += 1
    del counts["qrels"]
    problems = data.check_row_counts(counts)
    assert len(problems) == 2
    assert any("corpus" in p for p in problems)


def test_gold_maps_query_to_graded_pages():
    eval_set = data.EvalSet(
        queries=pd.DataFrame({"query_id": [1, 2]}),
        qrels=pd.DataFrame({"query_id": [1, 1, 2], "corpus_id": [10, 11, 12], "score": [2, 1, 1]}),
        corpus=pd.DataFrame(),
        documents=pd.DataFrame(),
    )
    assert eval_set.gold() == {1: {10: 2, 11: 1}, 2: {12: 1}}


def test_gold_keeps_queries_that_somehow_lost_their_judgements():
    eval_set = data.EvalSet(
        queries=pd.DataFrame({"query_id": [1, 2]}),
        qrels=pd.DataFrame({"query_id": [1], "corpus_id": [10], "score": [2]}),
        corpus=pd.DataFrame(),
        documents=pd.DataFrame(),
    )
    assert eval_set.gold()[2] == {}


# --- invariants on the artifacts `make data` writes (skipped until it has been run) --------


@pytest.fixture(scope="module")
def built() -> data.EvalSet:
    try:
        return data.load_eval_set()
    except FileNotFoundError:
        pytest.skip("eval set not built yet — run `make data`")


def test_every_eval_query_has_at_least_one_relevant_page(built):
    judged = set(built.qrels["query_id"])
    assert set(built.query_ids) == judged


def test_gold_pages_exist_in_the_corpus(built):
    assert set(built.qrels["corpus_id"]) <= set(built.corpus["corpus_id"])


def test_scores_are_graded_positives(built):
    assert set(built.qrels["score"].unique()) <= {1, 2}
    assert built.qrels["score"].min() >= config.MIN_RELEVANT_SCORE


def test_corpus_is_the_full_benchmark_not_just_the_gold_pages(built):
    # Retrieval must run against all 5,244 pages; scoring only the gold pages would be a
    # silently trivial benchmark.
    assert len(built.corpus) == config.EXPECTED_ROWS["corpus"]


def test_queries_are_the_full_english_slice(built):
    assert (built.queries["language"] == config.EVAL_LANGUAGE).all()
    # Both provenances are kept and reported as slices; filtering either one out up front
    # would silently change what the headline number means.
    generators = set(built.queries["query_generator"])
    assert generators == {"human", "sdg"}


def test_slices_partition_the_eval_set_by_provenance(built):
    slices = data.query_slices(built.queries)
    assert len(slices["human_written"]) + len(slices["synthetic"]) == len(built.queries)
    assert set(slices["human_written"]) & set(slices["synthetic"]) == set()
