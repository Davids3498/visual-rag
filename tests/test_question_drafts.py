"""Protect pilot provenance and in-corpus evidence before human review."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from visual_rag import corpus

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "prepare_questions", ROOT / "scripts/12_prepare_questions.py"
)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


@pytest.fixture
def draft():
    return json.loads(prepare.CANDIDATES.read_text())


def test_committed_draft_references_current_selected_corpus(draft):
    prepare.validate(draft, corpus.load_manifest())


def test_question_schema_separates_required_and_supporting_facts(draft):
    assert draft["schema_version"] == 2
    for question in draft["questions"]:
        assert question["core_required_facts"]
        assert isinstance(question["supporting_details"], list)
        assert "required_answer_facts" not in question


def test_repin_requires_question_review(draft):
    next(iter(draft["source_documents"].values()))["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Stale source pin"):
        prepare.validate(draft, corpus.load_manifest())


def test_evidence_in_an_excluded_manual_page_is_rejected(draft):
    # The manual exists, but its cover was not rendered/indexed.
    draft["questions"][0]["supporting_pages"][0]["page_number"] = 1
    with pytest.raises(ValueError, match="out-of-corpus"):
        prepare.validate(draft, corpus.load_manifest())


def test_duplicate_question_ids_are_rejected(draft):
    draft["questions"].append(deepcopy(draft["questions"][0]))
    with pytest.raises(ValueError, match="Duplicate question"):
        prepare.validate(draft, corpus.load_manifest())


def test_a_manual_reference_does_not_silently_change_scope(draft):
    draft["questions"][0]["retrieval_scope"] = "cross_document"
    with pytest.raises(ValueError, match="scope disagrees"):
        prepare.validate(draft, corpus.load_manifest())


def test_optional_manual_pages_are_not_scored(draft):
    question = draft["questions"][0]
    assert question["supporting_pages"]
    assert question["retrieval_scope"] == "single_document"
    prepare.validate(draft, corpus.load_manifest())
    question["supporting_pages"][0]["grade"] = 1
    with pytest.raises(ValueError, match="must not have relevance grades"):
        prepare.validate(draft, corpus.load_manifest())


def test_cross_document_scope_cannot_have_a_full_answer_page(draft):
    question = draft["questions"][0]
    page = question["supporting_pages"].pop()
    page["grade"] = 1
    question["gold_pages"].append(page)
    question["retrieval_scope"] = "cross_document"
    with pytest.raises(ValueError, match="full-answer page"):
        prepare.validate(draft, corpus.load_manifest())


def test_review_preserves_history_without_claiming_current_human_approval(draft):
    for question in draft["questions"]:
        question["human_review"]["status"] = "pending"
    rendered = prepare.review_markdown(draft)
    assert "Prior human review:" in rendered
    assert "- [x]" not in rendered
    draft["questions"][0]["human_review"]["status"] = "approved"
    rendered = prepare.review_markdown(draft)
    assert rendered.count("- [x]") == 2


def test_review_links_use_physical_pages(draft):
    rendered = prepare.review_markdown(draft)
    # ESP32 physical p16 is printed p13; never link using the printed label.
    assert "../data/mcu/pages/espressif_esp32_errata/p0016.png" in rendered
    assert "No-context audit completed for 12/12 questions." in rendered
    assert "Core required facts:" in rendered
    assert "Supporting details (useful, not required for correctness):" in rendered
    assert "Supporting pages (optional; excluded from scored gold):" in rendered
    assert "../data/mcu/pages/st_stm32f103_refman_rm0008/p0185.png" in rendered


def test_unrun_audit_is_not_reported_as_completed(draft):
    for question in draft["questions"]:
        question["no_context_audit"] = {"status": "not_run"}
    rendered = prepare.review_markdown(draft)
    assert "No no-context audit run." in rendered
    assert "No-context audit completed" not in rendered
