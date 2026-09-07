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


def test_repin_requires_question_review(draft):
    next(iter(draft["source_documents"].values()))["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Stale source pin"):
        prepare.validate(draft, corpus.load_manifest())


def test_evidence_in_an_excluded_manual_page_is_rejected(draft):
    # The manual exists, but its cover was not rendered/indexed.
    draft["questions"][0]["gold_pages"][1]["page_number"] = 1
    with pytest.raises(ValueError, match="out-of-corpus"):
        prepare.validate(draft, corpus.load_manifest())


def test_duplicate_question_ids_are_rejected(draft):
    draft["questions"].append(deepcopy(draft["questions"][0]))
    with pytest.raises(ValueError, match="Duplicate question"):
        prepare.validate(draft, corpus.load_manifest())


def test_a_manual_reference_does_not_silently_change_scope(draft):
    draft["questions"][0]["retrieval_scope"] = "single_document"
    with pytest.raises(ValueError, match="scope disagrees"):
        prepare.validate(draft, corpus.load_manifest())


def test_review_links_use_physical_pages(draft):
    rendered = prepare.review_markdown(draft)
    # ESP32 physical p16 is printed p13; never link using the printed label.
    assert "../data/mcu/pages/espressif_esp32_errata/p0016.png" in rendered
    assert "no no-context audit run" in rendered
