"""Protect page identity and pinning in native-text extraction."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "mcu_text", Path(__file__).resolve().parents[1] / "scripts/14_mcu_text_baseline.py"
)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def test_extracts_physical_pages_in_input_order_and_retains_empty(monkeypatch):
    table = pd.DataFrame(
        [
            {"page_id": 12, "doc_id": "d", "page_number": 2, "doc_sha256": "pinned"},
            {"page_id": 11, "doc_id": "d", "page_number": 1, "doc_sha256": "pinned"},
        ]
    )
    monkeypatch.setattr(baseline.corpus, "sha256_file", lambda _: "pinned")
    monkeypatch.setattr(
        baseline,
        "PdfReader",
        lambda _: SimpleNamespace(
            pages=[
                SimpleNamespace(extract_text=lambda: "first page"),
                SimpleNamespace(extract_text=lambda: None),
            ]
        ),
    )
    result = baseline.extract_pages(table)
    assert result.page_id.tolist() == [12, 11]
    assert result.text.tolist() == ["", "first page"]


def test_refuses_unpinned_pdf_before_extraction(monkeypatch):
    table = pd.DataFrame(
        [
            {"page_id": 11, "doc_id": "d", "page_number": 1, "doc_sha256": "pinned"},
        ]
    )
    monkeypatch.setattr(baseline.corpus, "sha256_file", lambda _: "changed")
    with pytest.raises(ValueError, match="Source hash mismatch"):
        baseline.extract_pages(table)
