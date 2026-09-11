"""Compare reviewed text and visual MCU runs without inference or regrading."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def validate_pair(text, visual):
    if text["question"] != visual["question"]:
        raise ValueError("Questions differ")
    for field in ("model", "temperature", "max_tokens"):
        if text["request"][field] != visual["request"][field]:
            raise ValueError(f"Generation setting differs: {field}")
    for key in ("core_fact_checks",):
        if [x["fact"] for x in text["assessment"][key]] != [
            x["fact"] for x in visual["assessment"][key]
        ]:
            raise ValueError("Rubrics differ")
    if text["request"]["messages"][0] != visual["request"]["messages"][0]:
        raise ValueError("System prompts differ")
    image_hashes = {}
    for record in (text, visual):
        if record["assessment"]["verdict"] == "pending_review":
            raise ValueError("Unreviewed answer")
        if record["generation"]["finish_reason"] != "stop":
            raise ValueError("Response did not finish normally")
        content = record["request"]["messages"][1]["content"]
        if content[-1] != {"type": "text", "text": f"Question: {record['question']}"}:
            raise ValueError("Unexpected question payload")
        if len(content) != 7:
            raise ValueError("Expected exactly 3 page labels/images and a question")
        for i, page_id in enumerate(record["generation"]["shown_pages"]):
            image = content[2 * i + 1]["image_url"]["url"]
            checksum = hashlib.sha256(image.encode()).hexdigest()
            if page_id in image_hashes and image_hashes[page_id] != checksum:
                raise ValueError("Shared page was encoded differently")
            image_hashes[page_id] = checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", type=Path, required=True)
    parser.add_argument("--visual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text, visual = read(args.text), read(args.visual)
    t = {r["question_id"]: r for r in text["per_question"]}
    v = {r["question_id"]: r for r in visual["per_question"]}
    if set(t) != set(v) or len(t) != 12:
        raise ValueError("Expected the same 12 questions")
    pairs = []
    for qid in sorted(t):
        validate_pair(t[qid], v[qid])
        pairs.append(
            {
                "question_id": qid,
                "text_ndcg": t[qid]["retrieval_metrics"]["ndcg_at_10"],
                "visual_ndcg": v[qid]["retrieval_metrics"]["ndcg_at_10"],
                "text_verdict": t[qid]["assessment"]["verdict"],
                "visual_verdict": v[qid]["assessment"]["verdict"],
            }
        )
    summaries = {}
    for name, report in (("text", text), ("visual", visual)):
        summaries[name] = {
            "metrics": report["retrieval_metrics"],
            "verdicts": report["answer_verdicts"],
            "complete_evidence_shown": report["complete_core_evidence_shown"],
            "improved_vs_no_context": report["improved_from_no_context"],
        }
    delta = (
        summaries["visual"]["metrics"]["ndcg_at_10"]["mean"]
        - summaries["text"]["metrics"]["ndcg_at_10"]["mean"]
    )
    result = {
        "question_count": 12,
        "runs": {"text": str(args.text), "visual": str(args.visual)},
        "input_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (("text", args.text), ("visual", args.visual))
        },
        "summaries": summaries,
        "visual_minus_text_ndcg": delta,
        "per_question": pairs,
        "checks": "Same questions, rubrics, system prompt, model alias, decoding parameters; "
        "3 images/request; shared images byte-identical; all finish reasons stop.",
        "interpretation": "Visual retrieval ranks the annotated evidence better on this pilot. "
        "It does not produce more fully correct answers in these single runs.",
        "limitations": [
            "12 assistant-authored prose-answer questions; provisional gold labels.",
            "Native pypdf text extraction, not OCR; result does not isolate an OCR "
            "failure or a visual-layout advantage from encoder/architecture differences.",
            "Same generator configuration, but single runs do not eliminate output "
            "variability. No generator superiority or significance claim.",
            "Answer judgments are assistant semantic reviews. Partial can include "
            "materially wrong advice; these are not all usable answers.",
            "No-context and grounded prompts differ; comparison measures workflows.",
        ],
    }
    lines = [
        "# MCU text versus visual retrieval — 12-question pilot",
        "",
        "Both paths retrieve from the same 1,201 pages and pass the top 3 page images to "
        "Qwen2.5-VL-7B-AWQ using the same grounded prompt and decoding settings.",
        "",
        "| Metric | Native text / BGE-M3 | Visual / ColQwen2 |",
        "|---|---:|---:|",
    ]
    for metric in ("ndcg_at_10", "recall_at_10", "recall_at_3"):
        lines.append(
            f"| {metric} | {summaries['text']['metrics'][metric]['mean']:.4f} | "
            f"{summaries['visual']['metrics'][metric]['mean']:.4f} |"
        )
    lines.append(
        f"| Complete core evidence in shown pages | {text['complete_core_evidence_shown']}/12 "
        f"| {visual['complete_core_evidence_shown']}/12 |"
    )
    for verdict in ("correct", "partial", "incorrect", "abstained"):
        lines.append(
            f"| Answers: {verdict} | {text['answer_verdicts'][verdict]} "
            f"| {visual['answer_verdicts'][verdict]} |"
        )
    lines += [
        "",
        f"Visual minus text NDCG@10: **{delta:+.4f}**.",
        "",
        result["interpretation"],
        "",
        "The text path answers question 009 correctly for both registers, while the visual "
        "path imports an unrelated FIFO-read workaround for GPIO. Retrieval quality and "
        "answer correctness therefore need separate reporting.",
        "",
        "Text extraction: pypdf native text, default extraction. BGE-M3 fp16, batch 16, "
        "4096 tokens, normalized dense vectors. Three non-gold pages exceed 4096 tokens; "
        "all gold pages fit (maximum 706 tokens). No page has empty extracted text.",
        "",
        "A separate HNSW index was built (m=16, ef_construction=64, ef_search=100). The "
        "sampled query plan chose an exact sequential scan on this small corpus. Search "
        "matched forced exact top-10 on all 12 questions; do not call this an ANN speed result.",
        "",
        "## Per-question comparison",
        "",
        "| Question | Text NDCG@10 | Visual NDCG@10 | Text answer | Visual answer |",
        "|---|---:|---:|---|---|",
    ]
    for p in pairs:
        lines.append(
            f"| {p['question_id']} | {p['text_ndcg']:.4f} | {p['visual_ndcg']:.4f} "
            f"| {p['text_verdict']} | {p['visual_verdict']} |"
        )
    lines += ["", "## Limitations", ""] + [f"- {x}" for x in result["limitations"]]
    lines += [
        "",
        "## Reviewed answers",
        "",
        f"- [Text-run answers](../{args.text.with_suffix('.md')})",
        f"- [Visual-run answers](../{args.visual.with_suffix('.md')})",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(result, indent=2))
    args.output.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
