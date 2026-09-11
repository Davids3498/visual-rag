"""Collect MCU visual-RAG answers, or rescore a saved run without inference.

Answer judgments come from an explicit semantic-review file bound to the exact answers
and rubrics. New runs remain pending review. No keyword-based correctness scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from PIL import Image

from visual_rag import config, generation, metrics, multivector, pgvector_store, retrieval

QUESTIONS = config.CORPUS_DIR / "questions/errata_candidates.json"
BASELINE = config.CORPUS_DIR / "questions/no_context_audits/20260908T134053918802Z.json"


def read_json(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_gold(question, page_table):
    gold = {}
    for page in question["gold_pages"]:
        rows = page_table[
            (page_table.doc_id == page["doc_id"]) & (page_table.page_number == page["page_number"])
        ]
        if len(rows) != 1 or page["grade"] not in (1, 2):
            raise ValueError(f"Invalid gold reference: {page}")
        gold[int(rows.iloc[0].page_id)] = page["grade"]
    return gold


def citation_labels(answer, shown):
    labels = [int(m.group(1)) for m in generation.CITATION.finditer(answer)]
    return {
        "labels": labels,
        "invalid_labels": [n for n in labels if not 1 <= n <= len(shown)],
        "resolved_page_ids": list(
            dict.fromkeys(shown[n - 1] for n in labels if 1 <= n <= len(shown))
        ),
        "note": "Valid local labels do not establish that the cited page supports the claim.",
    }


def compare_verdicts(before, after):
    if before not in {"correct", "partial", "incorrect", "abstained", "uncertain"}:
        raise ValueError(f"Unknown baseline verdict: {before}")
    if before == "uncertain" or after in {"pending_review", "uncertain"}:
        return None
    return (before in {"incorrect", "abstained"} and after in {"partial", "correct"}) or (
        before == "partial" and after == "correct"
    )


def validate_review(review, record, question):
    expected = {
        "question": question["question"],
        "answer": record["generation"]["answer"],
        "shown_pages": record["generation"]["shown_pages"],
        "core_required_facts": question["core_required_facts"],
    }
    if any(review.get(k) != v for k, v in expected.items()):
        raise ValueError("Semantic review does not match the exact answer, context and rubric")
    checks = review["core_fact_checks"]
    if [c["fact"] for c in checks] != question["core_required_facts"]:
        raise ValueError("Incomplete fact review")
    if review["verdict"] == "correct" and any(c["status"] != "met" for c in checks):
        raise ValueError("Correct verdict requires every core fact")
    coverage = review["context_fact_coverage"]
    if [c["fact"] for c in coverage] != question["core_required_facts"]:
        raise ValueError("Incomplete context review")
    for fact in coverage:
        if not set(fact["evidence_page_ids"]) <= set(expected["shown_pages"]):
            raise ValueError("Context coverage cites an unshown page")
        if fact["covered"] and not fact["evidence_page_ids"]:
            raise ValueError("Covered fact has no evidence")
    if review["complete_core_evidence_shown"] != all(c["covered"] for c in coverage):
        raise ValueError("Inconsistent context coverage")


def rescore(run, questions, baseline, table, reviews=None):
    original = json.loads(json.dumps(run))
    base = {q["question_id"]: q for q in baseline["questions"]}
    approved = {q["question_id"]: q for q in questions}
    review_by_id = {q["question_id"]: q for q in (reviews or {}).get("questions", [])}
    records = original["per_question"]
    ids = [r["question_id"] for r in records]
    if len(ids) != len(set(ids)) or set(ids) != set(approved):
        raise ValueError("Run must contain exactly the approved questions once each")
    for r in records:
        qid = r["question_id"]
        q, b = approved[qid], base[qid]
        if r["question"] != q["question"] or b["frozen_question"] != q["question"]:
            raise ValueError("Question changed since baseline")
        if b["core_required_facts"] != q["core_required_facts"]:
            raise ValueError("Rubric changed since baseline")
        gold = resolve_gold(q, table)
        ranked = [p["corpus_id"] for p in r["retrieved_pages"]]
        if len(ranked) != len(set(ranked)):
            raise ValueError("Duplicate retrieved page")
        by_id = table.set_index("page_id")
        for page in r["retrieved_pages"]:
            row = by_id.loc[page["corpus_id"]]
            if (row.doc_id, int(row.page_number)) != (page["doc_id"], page["page_number"]):
                raise ValueError("Retrieved page identity mismatch")
        shown = r["generation"]["shown_pages"]
        if shown != ranked[:3]:
            raise ValueError("Shown context is not top three retrieved pages")
        r["retrieval_metrics"] = {
            "ndcg_at_10": metrics.ndcg_at_k(ranked, gold, 10),
            "recall_at_10": metrics.recall_at_k(ranked, gold, 10),
            "recall_at_3": metrics.recall_at_k(ranked, gold, 3),
        }
        r["citation_check"] = citation_labels(r["generation"]["answer"], shown)
        r["generation"]["finish_reason"] = (
            r["generation"].get("raw_response", {}).get("choices", [{}])[0].get("finish_reason")
        )
        r["generation"]["truncation_verified"] = r["generation"]["finish_reason"] is not None
        review = review_by_id.get(qid)
        if review:
            validate_review(review, r, q)
            r["assessment"] = {
                k: review[k]
                for k in (
                    "verdict",
                    "core_fact_checks",
                    "rationale",
                    "citation_assessment",
                    "context_fact_coverage",
                    "complete_core_evidence_shown",
                )
            }
            r["assessment"]["reviewer"] = reviews["reviewer"]
        else:
            r["assessment"] = {"verdict": "pending_review", "complete_core_evidence_shown": None}
        r["assessment"]["no_context_verdict"] = b["grading"]["verdict"]
        r["assessment"]["no_context_checks"] = b["grading"]["core_fact_checks"]
        r["assessment"]["improved_from_no_context"] = compare_verdicts(
            b["grading"]["verdict"], r["assessment"]["verdict"]
        )
    original["retrieval_metrics"] = {}
    for key in ("ndcg_at_10", "recall_at_10", "recall_at_3"):
        values = [r["retrieval_metrics"][key] for r in records]
        original["retrieval_metrics"][key] = {
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "min": min(values),
            "max": max(values),
        }
    counts = Counter(r["assessment"]["verdict"] for r in records)
    original["answer_verdicts"] = {
        name: counts[name] for name in ("correct", "partial", "incorrect", "abstained", "uncertain")
    }
    if counts["pending_review"]:
        original["answer_verdicts"]["pending_review"] = counts["pending_review"]
    # Scores may have been rounded in a legacy report. Preserve its explicit rank order
    # when validating the metric formula rather than reordering rounded ties.
    trec_run = {
        i: {
            p["corpus_id"]: float(len(r["retrieved_pages"]) - rank)
            for rank, p in enumerate(r["retrieved_pages"])
        }
        for i, r in enumerate(records)
    }
    trec_gold = {i: resolve_gold(approved[r["question_id"]], table) for i, r in enumerate(records)}
    try:
        independent = metrics.evaluate_pytrec(trec_run, trec_gold, ks=(3, 10))
    except ImportError:
        original["metric_validation"] = {"status": "pytrec_eval_unavailable"}
    else:
        for name, trec_name in (
            ("ndcg_at_10", "ndcg_cut_10"),
            ("recall_at_10", "recall_10"),
            ("recall_at_3", "recall_3"),
        ):
            if abs(original["retrieval_metrics"][name]["mean"] - independent[trec_name]) > 1e-4:
                raise ValueError("Metric disagrees with trec_eval")
        original["metric_validation"] = {
            "status": "passed",
            "method": "pytrec_eval with saved rank order",
            "values": independent,
        }
    transitions = [r["assessment"]["improved_from_no_context"] for r in records]
    original["improved_from_no_context"] = (
        sum(value is True for value in transitions)
        if all(v is not None for v in transitions)
        else None
    )
    original["improvement_definition"] = (
        "Verdict transitions only: incorrect/abstained to partial/correct, or partial to correct. "
        "Additional facts within an unchanged partial verdict are not counted."
    )
    original["complete_core_evidence_shown"] = (
        sum(r["assessment"]["complete_core_evidence_shown"] is True for r in records)
        if len(review_by_id) == len(records)
        else None
    )
    original["review_method"] = (reviews or {}).get("method", "Pending semantic review")
    original["limitations"] = (
        [
            "Original legacy run did not save full API responses or exact image requests; "
            "finish reason and absence of truncation cannot be retrospectively verified.",
            "Gold annotations are provisional. No-context and RAG prompts differ, so this is "
            "a comparison of workflows, not an isolated causal estimate of context alone.",
            "Semantic judgments are by an assistant and can be reviewed by a human.",
            "This is visual retrieval only; no MCU text-baseline comparison has been run here.",
        ]
        if any(not r["generation"].get("raw_response") for r in records)
        else ["Gold annotations are provisional; answer judgments require semantic review."]
    )
    return original


def markdown(report):
    lines = [
        "# MCU RAG evaluation — corrected",
        "",
        f"Original run: {report['evaluation_timestamp']}",
        "",
        f"Verdicts: {report['answer_verdicts']}",
        f"Improved verdicts: {report['improved_from_no_context']}/12",
        f"Complete core evidence shown: {report['complete_core_evidence_shown']}/12",
        "",
    ]
    for key, value in report["retrieval_metrics"].items():
        lines.append(f"- {key}: {value['mean']:.6f} (mean)")
    lines += ["", report["improvement_definition"], "", "## Limitations", ""]
    lines += [f"- {v}" for v in report["limitations"]]
    for r in report["per_question"]:
        a = r["assessment"]
        lines += [
            "",
            f"## {r['question_id']} — {a['verdict']}",
            "",
            r["question"],
            "",
            f"Baseline: {a['no_context_verdict']}; improved: {a['improved_from_no_context']}",
            f"Shown page IDs: {r['generation']['shown_pages']}",
            "",
            "### Saved model answer",
            "",
            r["generation"]["answer"],
            "",
            "### Assessment",
            "",
            a.get("rationale", "Pending review"),
            "",
        ]
        for fact in a.get("core_fact_checks", []):
            lines.append(f"- {fact['status']}: {fact['fact']} {fact['assessment']}")
        lines += [
            "",
            f"Citations: {r['citation_check']}",
            "",
            a.get("citation_assessment", ""),
            "",
            f"Complete evidence shown: {a['complete_core_evidence_shown']}",
            "",
            "### Retrieved pages",
            "",
        ]
        for i, p in enumerate(r["retrieved_pages"], 1):
            lines.append(
                f"- {i}. {p['doc_id']} p{p['page_number']} "
                f"(ID {p['corpus_id']}, score {p['score']})"
            )
    return "\n".join(lines) + "\n"


def collect(questions, table, output):
    """Collect only; gold/rubric data never enter the retrieval or generation request."""
    store = multivector.MultiVectorStore.load(
        config.DATA_DIR / "embeddings/mcu_vidore_colqwen2-v1.0"
    )
    if set(store.ids) != set(table.page_id):
        raise ValueError("Embedding IDs do not match MCU page table")
    cfg = generation.VLMConfig()
    response = requests.get(f"{cfg.base_url}/models", timeout=20)
    response.raise_for_status()
    served_models = response.json()
    records = []
    started = datetime.now(UTC).isoformat()
    by_id = table.set_index("page_id")
    with pgvector_store.connect() as conn:
        counts = dict(
            conn.execute(
                f"SELECT corpus_id, count(*) FROM {config.MCU_CENTROID_TABLE} GROUP BY corpus_id"
            ).fetchall()
        )
        if set(counts) != set(store.ids) or set(counts.values()) != {16}:
            raise ValueError("MCU index page identities or centroid counts do not match")
        retriever = retrieval.TwoStageRetriever(
            store, conn, retrieval.RetrievalConfig(centroid_table=config.MCU_CENTROID_TABLE)
        )
        retriever.warm()
        for q in questions:
            result = retriever.retrieve(q["question"], k=10)
            ranked = [
                {
                    "corpus_id": int(pid),
                    "doc_id": by_id.loc[pid].doc_id,
                    "page_number": int(by_id.loc[pid].page_number),
                    "score": float(score),
                }
                for pid, score in result.pages
            ]
            pages = []
            try:
                for page in ranked[:3]:
                    with Image.open(by_id.loc[page["corpus_id"]].path) as im:
                        pages.append({**page, "image": im.convert("RGB")})
                payload = {
                    "model": cfg.model,
                    "messages": generation.build_messages(q["question"], pages, cfg),
                    "temperature": cfg.temperature,
                    "max_tokens": cfg.max_tokens,
                }
            finally:
                for page in pages:
                    page["image"].close()
            request_started = time.perf_counter()
            response = requests.post(
                f"{cfg.base_url}/chat/completions", json=payload, timeout=cfg.timeout
            )
            response.raise_for_status()
            body = response.json()
            record = {
                "question_id": q["question_id"],
                "question": q["question"],
                "retrieved_pages": ranked,
                "retrieval_stages": {
                    "encode_ms": result.encode_ms,
                    "stage1_ms": result.stage1_ms,
                    "stage2_ms": result.stage2_ms,
                },
                "generation": {
                    "answer": body["choices"][0]["message"]["content"],
                    "shown_pages": [p["corpus_id"] for p in ranked[:3]],
                    "raw_response": body,
                    "latency_ms": (time.perf_counter() - request_started) * 1000,
                },
                "request": payload,
            }
            (output / f"{q['question_id']}.json").write_text(json.dumps(record, indent=2))
            records.append(record)
    return {
        "evaluation_timestamp": started,
        "per_question": records,
        "total_questions": len(records),
        "served_models": served_models,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rescore", type=Path, help="Saved run; no inference")
    parser.add_argument("--reviews", type=Path, help="Semantic judgments for these exact answers")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="New directory; never overwrite"
    )
    args = parser.parse_args()
    questions = [
        q for q in read_json(QUESTIONS)["questions"] if q["human_review"]["status"] == "approved"
    ]
    if len(questions) != 12:
        raise ValueError("Expected 12 approved MCU questions")
    table = pd.read_parquet(config.MCU_PAGE_TABLE)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    run = read_json(args.rescore) if args.rescore else collect(questions, table, args.output_dir)
    report = rescore(
        run,
        questions,
        read_json(BASELINE),
        table,
        read_json(args.reviews) if args.reviews else None,
    )
    report["provenance"] = {
        "rescored_at": datetime.now(UTC).isoformat(),
        "source_run": str(args.rescore) if args.rescore else None,
        "source_sha256": digest(args.rescore) if args.rescore else None,
        "baseline_sha256": digest(BASELINE),
        "questions_sha256": digest(QUESTIONS),
        "review_sha256": digest(args.reviews) if args.reviews else None,
    }
    (args.output_dir / "mcu_evaluation.json").write_text(json.dumps(report, indent=2))
    (args.output_dir / "mcu_evaluation.md").write_text(markdown(report))
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "retrieval_metrics",
                    "answer_verdicts",
                    "improved_from_no_context",
                    "complete_core_evidence_shown",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
