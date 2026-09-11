"""Regression tests for graded retrieval, baseline lookup and semantic review binding."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "mcu_eval", Path(__file__).resolve().parents[1] / "scripts/12_mcu_evaluation.py"
)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


@pytest.fixture
def inputs():
    question = {
        "question_id": "q1",
        "question": "What is required?",
        "core_required_facts": ["Wait before Stop."],
        "gold_pages": [
            {"doc_id": "errata", "page_number": 1, "grade": 2},
            {"doc_id": "errata", "page_number": 2, "grade": 1},
        ],
        "supporting_pages": [{"doc_id": "manual", "page_number": 1}],
    }
    table = pd.DataFrame(
        [
            {"page_id": 1, "doc_id": "errata", "page_number": 1},
            {"page_id": 2, "doc_id": "errata", "page_number": 2},
            {"page_id": 3, "doc_id": "manual", "page_number": 1},
        ]
    )
    record = {
        "question_id": "q1",
        "question": question["question"],
        "retrieved_pages": [{"corpus_id": 3, "doc_id": "manual", "page_number": 1}],
        "generation": {"answer": "Wait before Stop.", "shown_pages": [3]},
    }
    baseline = {
        "questions": [
            {
                "question_id": "q1",
                "frozen_question": question["question"],
                "core_required_facts": question["core_required_facts"],
                "grading": {"verdict": "incorrect", "core_fact_checks": []},
            }
        ]
    }
    return question, table, record, baseline


def test_gold_preserves_grades_and_excludes_supporting_pages(inputs):
    q, table, _, _ = inputs
    assert evaluation.resolve_gold(q, table) == {1: 2, 2: 1}


def test_unresolved_gold_fails_instead_of_disappearing(inputs):
    q, table, _, _ = inputs
    q["gold_pages"][0]["page_number"] = 999
    with pytest.raises(ValueError, match="Invalid gold"):
        evaluation.resolve_gold(q, table)


def test_zero_hits_score_zero_and_missing_review_never_auto_grades(inputs):
    q, table, r, baseline = inputs
    out = evaluation.rescore({"per_question": [r]}, [q], baseline, table)
    scored = out["per_question"][0]
    assert scored["retrieval_metrics"]["ndcg_at_10"] == 0
    assert scored["assessment"]["verdict"] == "pending_review"
    assert scored["assessment"]["no_context_verdict"] == "incorrect"
    assert scored["assessment"]["improved_from_no_context"] is None
    assert scored["generation"]["finish_reason"] is None
    assert scored["generation"]["truncation_verified"] is False


def test_missing_relevant_page_is_in_ideal_denominator(inputs):
    q, table, r, baseline = inputs
    r["retrieved_pages"] = [{"corpus_id": 1, "doc_id": "errata", "page_number": 1}]
    r["generation"]["shown_pages"] = [1]
    out = evaluation.rescore({"per_question": [r]}, [q], baseline, table)
    assert 0 < out["retrieval_metrics"]["ndcg_at_10"]["mean"] < 1
    assert out["retrieval_metrics"]["recall_at_10"]["mean"] == 0.5


def test_unknown_baseline_cannot_silently_count_as_no_improvement():
    with pytest.raises(ValueError, match="Unknown baseline"):
        evaluation.compare_verdicts("unknown", "correct")
    assert evaluation.compare_verdicts("incorrect", "partial") is True
    assert evaluation.compare_verdicts("partial", "correct") is True
    assert evaluation.compare_verdicts("partial", "partial") is False


def test_invalid_physical_page_label_is_not_silently_accepted():
    out = evaluation.citation_labels("See [Page 18] and [Page 1].", [20018, 20019, 20009])
    assert out["invalid_labels"] == [18]
    assert out["resolved_page_ids"] == [20018]


def test_review_rejected_when_answer_changes_even_by_negation(inputs):
    q, _, r, _ = inputs
    review = {
        "question": q["question"],
        "answer": "Do not wait before Stop.",
        "shown_pages": [3],
        "core_required_facts": q["core_required_facts"],
    }
    with pytest.raises(ValueError, match="exact answer"):
        evaluation.validate_review(review, r, q)


def test_no_review_can_be_reused_after_context_changes(inputs):
    q, _, r, _ = inputs
    review = {
        "question": q["question"],
        "answer": r["generation"]["answer"],
        "shown_pages": [1],
        "core_required_facts": deepcopy(q["core_required_facts"]),
    }
    with pytest.raises(ValueError, match="exact answer"):
        evaluation.validate_review(review, r, q)
