"""Ensure audit requests cannot carry RAG context or grading material."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "no_context_audit", Path(__file__).resolve().parents[1] / "scripts/13_no_context_audit.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_request_contains_only_neutral_instruction_and_current_question():
    payload = audit.build_payload("Why did the watchdog reset?", "test-model")
    assert payload["messages"] == [
        {"role": "system", "content": audit.SYSTEM_PROMPT},
        {"role": "user", "content": "Why did the watchdog reset?"},
    ]
    assert "tools" not in payload
    assert "NOT_IN_PAGES" not in audit.SYSTEM_PROMPT
    assert payload["temperature"] == 0


def test_requests_do_not_share_conversation_history():
    first = audit.build_payload("First question", "test-model")
    first["messages"].append({"role": "assistant", "content": "A previous answer"})
    second = audit.build_payload("Second question", "test-model")
    assert len(second["messages"]) == 2
    assert second["messages"][-1]["content"] == "Second question"
