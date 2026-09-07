"""Extract local errata text and render the pilot question review; no model calls.

Run with `.venv/bin/python scripts/12_prepare_questions.py` after corpus ingestion.
Vendor text stays in gitignored reports/. Candidate annotations stay under corpus/questions/.
This deliberately does not export qrels or imply that draft questions passed an audit.
"""

from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

from visual_rag import corpus, ingest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "corpus/questions/errata_candidates.json"


def validate(data: dict, manifest: corpus.Manifest) -> None:
    """Reject stale source pins, invalid evidence references and inconsistent draft labels."""
    if data["status"] != "draft_not_for_scoring":
        raise ValueError("This preparation script accepts drafts only")
    selected = {(p.doc_id, p.page_number) for p in ingest.plan_pages(manifest)}
    documents = {d.doc_id: d for d in manifest.documents}
    for doc_id, source in data["source_documents"].items():
        if source["sha256"] != documents[doc_id].sha256:
            raise ValueError(f"Stale source pin: {doc_id}")
    ids = set()
    for question in data["questions"]:
        qid = question["question_id"]
        if qid in ids:
            raise ValueError(f"Duplicate question: {qid}")
        ids.add(qid)
        for field in ("question", "reference_answer", "required_answer_facts", "gold_pages"):
            if not question[field]:
                raise ValueError(f"{qid}: empty {field}")
        source = question["source_errata"]
        if documents[source["doc_id"]].doc_type != "errata":
            raise ValueError(f"{qid}: source is not an errata document")
        if documents[source["doc_id"]].family != question["family"]:
            raise ValueError(f"{qid}: wrong source family")
        refs = [(source["doc_id"], n) for n in source["page_numbers"]]
        evidence = [(e["doc_id"], e["page_number"]) for e in question["gold_pages"]]
        if len(evidence) != len(set(evidence)):
            raise ValueError(f"{qid}: duplicate gold page")
        for doc_id, number in refs + evidence:
            if doc_id not in data["source_documents"] or (doc_id, number) not in selected:
                raise ValueError(f"{qid}: unpinned or out-of-corpus page {doc_id}:{number}")
        if any(e["grade"] not in (1, 2) for e in question["gold_pages"]):
            raise ValueError(f"{qid}: invalid relevance grade")
        cross = len({doc for doc, _ in evidence}) > 1
        if cross != (question["retrieval_scope"] == "cross_document"):
            raise ValueError(f"{qid}: document scope disagrees with evidence")
        if question["annotation_status"] != "draft":
            raise ValueError(f"{qid}: expected draft annotation")


def image_link(doc_id: str, number: int) -> str:
    return f"../data/mcu/pages/{doc_id}/p{number:04d}.png"


def review_markdown(data: dict) -> str:
    lines = [
        "# MCU errata question pilot — review copy",
        "",
        "Draft annotations, no no-context audit run, not ready for scoring.",
        "All page numbers below are physical PDF pages, starting at 1.",
        "See ../corpus/questions/README.md for review and audit rules.",
        "",
        data["provenance_note"],
        "",
    ]
    for q in data["questions"]:
        lines += [f"## {q['question_id']} — {q['family']}", "", q["question"], ""]
        lines += [f"Scope: {q['part_scope']}; {q['retrieval_scope']}.", ""]
        lines += ["Reference answer: " + q["reference_answer"], "", "Required facts:", ""]
        lines += [f"- {fact}" for fact in q["required_answer_facts"]]
        source = q["source_errata"]
        links = [f"[p{n}]({image_link(source['doc_id'], n)})" for n in source["page_numbers"]]
        lines += [
            "",
            f"Source: {source['doc_id']}, {source['section']}, " + ", ".join(links),
            "",
            "Provisional gold pages (1 = partial, 2 = full answer):",
            "",
        ]
        for e in q["gold_pages"]:
            label = f"{e['doc_id']} p{e['page_number']}"
            link = image_link(e["doc_id"], e["page_number"])
            lines.append(
                f"- [{label}]({link}) — grade {e['grade']}, {e['evidence_type']}: {e['support']}"
            )
        lines += ["", "Review note: " + q["review_notes"], ""]
        lines += ["- [ ] Wording and scope approved", "- [ ] Answer and evidence approved", ""]
    return "\n".join(lines)


def main() -> None:
    manifest = corpus.load_manifest()
    data = json.loads(CANDIDATES.read_text())
    validate(data, manifest)
    # Verify actual bytes before extracting or presenting annotations about a pinned revision.
    relevant = set(data["source_documents"]) | {
        d.doc_id for d in manifest.documents if d.doc_type == "errata"
    }
    for doc in manifest.documents:
        if doc.doc_id in relevant:
            path = ROOT / "data/mcu/pdfs" / f"{doc.doc_id}.pdf"
            if corpus.sha256_file(path) != doc.sha256:
                raise ValueError(f"Local PDF hash mismatch: {doc.doc_id}")
    extracted = []
    for doc in manifest.documents:
        if doc.doc_type != "errata":
            continue
        reader = PdfReader(ROOT / "data/mcu/pdfs" / f"{doc.doc_id}.pdf")
        for number in doc.pages.page_numbers(len(reader.pages)):
            extracted.append(
                {
                    "doc_id": doc.doc_id,
                    "sha256": doc.sha256,
                    "page_number": number,
                    "text": reader.pages[number - 1].extract_text(),
                }
            )
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "mcu_errata_pages.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in extracted)
    )
    (reports / "mcu_question_review.md").write_text(review_markdown(data))
    print(f"Extracted {len(extracted)} errata pages; validated {len(data['questions'])} drafts.")
    print("Review: reports/mcu_question_review.md (no audit or scoring performed)")


if __name__ == "__main__":
    main()
