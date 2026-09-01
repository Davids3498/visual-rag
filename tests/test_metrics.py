"""The metrics decide whether the whole project's headline claim is true, so they get tested
against the reference implementation rather than eyeballed."""

from __future__ import annotations

import random

import pytest

from visual_rag import metrics

pytrec_eval = pytest.importorskip("pytrec_eval")


def test_perfect_ranking_scores_one():
    gold = {1: {10: 2, 11: 1}}
    run = {1: {10: 0.9, 11: 0.8, 12: 0.7}}
    assert metrics.evaluate(run, gold, ks=(10,))["ndcg@10"] == 1.0


def test_grading_rewards_the_full_answer_page_first():
    gold = {1: {10: 2, 11: 1}}
    good = metrics.evaluate({1: {10: 0.9, 11: 0.8}}, gold, ks=(10,))["ndcg@10"]
    swapped = metrics.evaluate({1: {11: 0.9, 10: 0.8}}, gold, ks=(10,))["ndcg@10"]
    assert good > swapped


def test_empty_run_scores_zero_rather_than_being_skipped():
    gold = {1: {10: 2}, 2: {20: 1}}
    scored = metrics.evaluate({1: {10: 0.9}}, gold, ks=(10,))
    assert scored["ndcg@10"] == 0.5  # query 2 counts as a zero


def test_cutoff_is_respected():
    gold = {1: {10: 2}}
    run = {1: {i: 1.0 - i / 100 for i in range(20)}}  # gold page sits at rank 11
    assert metrics.evaluate(run, gold, ks=(10,))["ndcg@10"] == 0.0
    assert metrics.evaluate(run, gold, ks=(20,))["ndcg@20"] > 0.0


def test_ties_break_deterministically():
    run = {1: {10: 0.5, 11: 0.5, 12: 0.5}}
    assert metrics.rank(run[1]) == [10, 11, 12]


@pytest.mark.parametrize("seed", range(5))
def test_agrees_with_trec_eval_on_random_runs(seed):
    """The leaderboard scores with trec_eval; my implementation must not quietly differ."""
    rng = random.Random(seed)
    gold = {
        qid: {rng.randrange(200): rng.choice([1, 1, 2]) for _ in range(rng.randint(1, 8))}
        for qid in range(20)
    }
    run = {
        qid: {rng.randrange(200): rng.random() for _ in range(rng.randint(0, 30))} for qid in gold
    }
    # make some queries actually retrieve their gold pages, so scores aren't all zero
    for qid, rels in gold.items():
        for doc in list(rels)[: rng.randint(0, len(rels))]:
            run[qid][doc] = rng.random()

    mine = metrics.evaluate(run, gold, ks=(1, 5, 10))
    theirs = metrics.evaluate_pytrec(run, gold, ks=(1, 5, 10))
    for k in (1, 5, 10):
        assert mine[f"ndcg@{k}"] == pytest.approx(theirs[f"ndcg_cut_{k}"], abs=1e-4)
        assert mine[f"recall@{k}"] == pytest.approx(theirs[f"recall_{k}"], abs=1e-4)
    assert mine["map"] == pytest.approx(theirs["map"], abs=1e-4)


def test_default_gain_is_the_trec_eval_convention():
    # trec_eval's ndcg_cut uses linear gains; the exponential variant is kept only for
    # comparison with papers that report it.
    gold = {1: {10: 2, 11: 1}}
    run = {1: {11: 0.9, 10: 0.8}}
    linear = metrics.evaluate(run, gold, ks=(10,), gain="linear")["ndcg@10"]
    exponential = metrics.evaluate(run, gold, ks=(10,), gain="exponential")["ndcg@10"]
    reference = metrics.evaluate_pytrec(run, gold, ks=(10,))["ndcg_cut_10"]
    assert linear == pytest.approx(reference, abs=1e-4)
    assert exponential != pytest.approx(reference, abs=1e-4)
