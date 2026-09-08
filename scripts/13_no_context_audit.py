"""Collect independent, document-free answers; verdicts require a separate review.

Each run preserves its exact input snapshot and raw API responses in a new report directory.
This script never sends references, rubrics, source metadata, or previous answers to the model.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import requests

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT = "Answer the question clearly and directly. If you are unsure, say so."


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def build_payload(question: str, model: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 1536,
        "seed": 0,
        "stream": False,
    }


def main() -> None:
    source = ROOT / "corpus/questions/errata_candidates.json"
    snapshot = source.read_bytes()
    candidates = json.loads(snapshot)
    if any(q["human_review"]["status"] != "approved" for q in candidates["questions"]):
        raise ValueError("All questions must be reviewed before the audit")
    base_url = os.environ.get("VRAG_VLLM_URL", "http://localhost:8000/v1").rstrip("/")
    response = requests.get(f"{base_url}/models", timeout=20)
    response.raise_for_status()
    models = response.json()
    model = "qwen2.5-vl-7b-awq"
    served = next(m for m in models["data"] if m["id"] == model)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "reports" / f"mcu_no_context_{run_id}"
    output.mkdir(exist_ok=False)
    (output / "questions_snapshot.json").write_bytes(snapshot)
    cache = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-VL-7B-Instruct-AWQ"
    revision = cache / "refs/main"
    try:
        container = subprocess.run(
            ["docker", "inspect", "vrag-vllm", "--format", "{{json .Config.Cmd}} {{.Image}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        container = None
    metadata = {
        "run_id": run_id,
        "started_at": utc_now(),
        "status": "running",
        "protocol": (
            "One independent request per question; no documents, tools, or conversation history."
        ),
        "candidate_sha256": hashlib.sha256(snapshot).hexdigest(),
        "base_url": base_url,
        "served_model": served,
        "quantization": "AWQ int4 (served model repository)",
        "cached_model_revision": revision.read_text().strip() if revision.exists() else None,
        "revision_note": (
            "Local cache ref; server API does not attest the loaded commit. "
            "Container command is not revision-pinned."
        ),
        "container_command_and_image": container,
        "request_template": build_payload("<question>", model),
        "question_count": len(candidates["questions"]),
        "grading": (
            "Not performed by this collection script. Review every core required fact separately."
        ),
    }
    metadata_path = output / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Audit directory: {output}", flush=True)
    try:
        for question in candidates["questions"]:
            payload = build_payload(question["question"], model)
            started = utc_now()
            timer = perf_counter()
            response = requests.post(f"{base_url}/chat/completions", json=payload, timeout=240)
            response.raise_for_status()
            raw = response.json()
            result = {
                "question_id": question["question_id"],
                "started_at": started,
                "finished_at": utc_now(),
                "latency_seconds": perf_counter() - timer,
                "request": payload,
                "raw_response": raw,
            }
            (output / f"{question['question_id']}.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            )
            choice = raw["choices"][0]
            print(
                f"{question['question_id']}: {choice['finish_reason']}, "
                f"{raw.get('usage', {}).get('completion_tokens')} tokens",
                flush=True,
            )
        metadata["status"] = "collected_pending_review"
    except Exception as exc:
        metadata["status"] = "collection_failed"
        metadata["error"] = str(exc)
        raise
    finally:
        metadata["finished_at"] = utc_now()
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
