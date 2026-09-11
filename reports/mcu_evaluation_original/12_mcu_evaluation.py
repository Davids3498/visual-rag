"""MCU errata evaluation -- 12 approved questions through the visual RAG pipeline."""

from __future__ import annotations

import json
import time
import base64
import io
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from rich.console import Console
import requests

from visual_rag import config, multivector, pgvector_store, retrieval

console = Console()

ERRATA_PATH = config.CORPUS_DIR / "questions" / "errata_candidates.json"
NO_CONTEXT_AUDIT = (
    config.CORPUS_DIR / "questions" / "no_context_audits" / "20260908T134053918802Z.json"
)
MCU_PAGE_TABLE = config.MCU_PAGE_TABLE
MCU_EMBEDDINGS = config.DATA_DIR / "embeddings" / "mcu_vidore_colqwen2-v1.0"
MCU_CENTROID_TABLE = config.MCU_CENTROID_TABLE
REPORTS_DIR = config.REPORTS_DIR

VLLM_URL = "http://localhost:8000/v1"
SYSTEM_PROMPT = (
    "You answer questions about pages from technical manuals. You are given page images, each "
    "labelled 'Page N'. Answer only from what is visible in those pages -- tables, diagrams and "
    "text all count as visible.\n"
    "Rules:\n"
    "1. Cite every claim inline as [Page N], using the labels given.\n"
    "2. If the pages do not contain the answer, reply exactly: NOT_IN_PAGES\n"
    "3. Be specific: quote the exact values, part numbers and units shown, not paraphrases.\n"
    "4. Keep the answer under 120 words."
)
CITATION_RE = re.compile(r"\[?[Pp]age\s+(\d+)\]?")

MAX_PAGES = 3
MAX_TOKENS = 400
TEMPERATURE = 0.0
JPEG_QUALITY = 85
MAX_PIXELS = 1_200_000


def downscale(image, max_pixels):
    pixels = image.width * image.height
    if not max_pixels or pixels <= max_pixels:
        return image
    scale = (max_pixels / pixels) ** 0.5
    return image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))


def encode_image(image, quality=85, max_pixels=0):
    buffer = io.BytesIO()
    downscale(image, max_pixels).convert("RGB").save(buffer, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def vllm_health():
    try:
        response = requests.get(VLLM_URL.replace("/v1", "/health"), timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def vllm_answer(question, pages):
    content = []
    for position, page in enumerate(pages[:MAX_PAGES], start=1):
        content.append({
            "type": "text",
            "text": f"Page {position} (document {page['doc_id']}, page {page['page_number']}):",
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": encode_image(page["image"], JPEG_QUALITY, MAX_PIXELS)},
        })
    content.append({"type": "text", "text": f"Question: {question}"})
    payload = {
        "model": "qwen2.5-vl-7b-awq",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }
    started = time.perf_counter()
    response = requests.post(f"{VLLM_URL}/chat/completions", json=payload, timeout=180.0)
    response.raise_for_status()
    body = response.json()
    latency_ms = (time.perf_counter() - started) * 1000

    text = body["choices"][0]["message"]["content"].strip()
    shown = [page["corpus_id"] for page in pages[:MAX_PAGES]]
    cited = []
    for match in CITATION_RE.finditer(text):
        index = int(match.group(1)) - 1
        if 0 <= index < len(shown) and shown[index] not in cited:
            cited.append(shown[index])

    return {
        "text": text,
        "cited_pages": cited,
        "shown_pages": shown,
        "refused": "NOT_IN_PAGES" in text,
        "latency_ms": round(latency_ms, 1),
        "usage": body.get("usage", {}),
    }


def load_approved_questions():
    data = json.loads(ERRATA_PATH.read_text())
    approved = [
        q
        for q in data["questions"]
        if q.get("human_review", {}).get("status") == "approved"
    ]
    console.print(f"[cyan]Loaded {len(approved)} approved questions[/cyan]")
    return approved


def ndcg_at_k(relevance, k):
    dcg = 0.0
    for i, rel in enumerate(relevance[:k]):
        dcg += (2**rel - 1) / np.log2(i + 2)
    sorted_rel = sorted(relevance, reverse=True)
    idcg = 0.0
    for i, rel in enumerate(sorted_rel[:k]):
        idcg += (2**rel - 1) / np.log2(i + 2)
    if idcg == 0:
        return 1.0 if dcg == 0 else 0.0
    return dcg / idcg


def recall_at_k(retrieved_ids, gold_ids, k):
    hit = len(set(retrieved_ids[:k]) & gold_ids) / max(len(gold_ids), 1)
    return hit


def assess_answer(answer_text, core_required_facts, supporting_details,
                  no_context_verdict, no_context_checks):
    fact_checks = []
    met = 0
    missing = 0
    contradicted = 0
    partially_met = 0

    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "to", "of", "in", "for", "on",
        "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "and", "or", "not",
        "no", "nor", "but", "if", "then", "than", "that", "this", "it",
        "its", "what", "which", "who", "how", "all", "each", "every",
        "both", "few", "many", "more", "most", "other", "some", "such",
        "only", "own", "same", "so", "up", "out", "just", "also", "very",
        "too", "about", "can", "cannot", "must", "need", "refers", "states",
        "explains", "identifies", "rejects", "restricts", "gives", "names",
        "requires", "specifies", "uses", "allows", "disallows", "wording",
        "describes",
    }

    for i, fact in enumerate(core_required_facts):
        answer_lower = answer_text.lower()
        fact_lower = fact.lower()

        key_terms = [
            w for w in fact_lower.replace(",", " ").replace(".", " ").split()
            if len(w) > 2 and w not in stop_words
        ]

        found_terms = [t for t in key_terms if t in answer_lower]
        term_ratio = len(found_terms) / max(len(key_terms), 1)

        if term_ratio >= 0.5 and len(found_terms) >= 2:
            status = "met"
            met += 1
        elif term_ratio >= 0.25 or len(found_terms) >= 1:
            status = "partially_met"
            partially_met += 1
        elif "not_in_pages" in answer_text.lower():
            status = "missing"
            missing += 1
        else:
            contradiction_indicators = [
                "should disable", "should not", "is not", "does not",
                "incorrect", "wrong", "avoid", "should not use",
            ]
            is_contradicted = any(c in answer_lower for c in contradiction_indicators)
            if is_contradicted and term_ratio < 0.1:
                status = "contradicted"
                contradicted += 1
            else:
                status = "missing"
                missing += 1

        fact_checks.append({
            "fact": fact,
            "status": status,
            "key_terms_found": found_terms,
            "term_ratio": round(term_ratio, 2),
        })

    if met == len(core_required_facts):
        verdict = "correct"
    elif met > 0 and contradicted == 0:
        verdict = "partial"
    elif contradicted > 0:
        verdict = "incorrect"
    elif "not_in_pages" in answer_text.lower() or answer_text.strip() == "":
        verdict = "abstained"
    else:
        verdict = "incorrect"

    no_context_improved = False
    improvement_reason = ""
    if no_context_verdict in ("incorrect", "abstained"):
        if verdict in ("correct", "partial"):
            no_context_improved = True
            improvement_reason = (
                f"Improved from '{no_context_verdict}' to '{verdict}' with retrieved context"
            )
    elif no_context_verdict == "partial":
        if verdict == "correct":
            no_context_improved = True
            improvement_reason = (
                f"Improved from '{no_context_verdict}' to '{verdict}' with retrieved context"
            )

    return {
        "fact_checks": fact_checks,
        "core_facts_met": met,
        "core_facts_total": len(core_required_facts),
        "verdict": verdict,
        "improved_from_no_context": no_context_improved,
        "improvement_reason": improvement_reason,
        "no_context_verdict": no_context_verdict,
        "no_context_met": sum(1 for c in no_context_checks if c.get("status") == "met"),
        "no_context_total": len(no_context_checks),
    }


def main():
    console.rule("[bold]MCU RAG Evaluation[/bold]")
    started_at = datetime.now(timezone.utc)

    questions = load_approved_questions()
    assert len(questions) == 12, f"Expected 12 approved questions, got {len(questions)}"

    page_table = pd.read_parquet(MCU_PAGE_TABLE)
    console.print(f"[cyan]Page table: {len(page_table)} pages[/cyan]")

    store = multivector.MultiVectorStore.load(MCU_EMBEDDINGS)
    console.print(f"[cyan]MultiVectorStore: {len(store)} pages, dim={store.dim}[/cyan]")

    store_ids = set(store.ids.tolist())
    table_ids = set(page_table["page_id"].tolist())
    assert store_ids == table_ids, (
        f"ID mismatch: store has {len(store_ids)}, table has {len(table_ids)}, "
        f"diff={store_ids ^ table_ids}"
    )

    with pgvector_store.connect() as conn:
        centroid_count = conn.execute(
            f"SELECT count(*) FROM {MCU_CENTROID_TABLE}"
        ).fetchone()[0]
    expected_centroids = len(store) * 16
    assert centroid_count == expected_centroids, (
        f"Centroid count {centroid_count} != {len(store)} * 16 = {expected_centroids}"
    )
    console.print(
        f"[green]Index verified: {len(store)} pages, {centroid_count} centroids (16/page)[/green]"
    )

    by_page_id = page_table.set_index("page_id")

    def lookup_page_id(doc_id, page_number):
        row = page_table[(page_table["doc_id"] == doc_id) & (page_table["page_number"] == page_number)]
        if len(row) == 1:
            return int(row.iloc[0]["page_id"])
        return None

    def resolve_gold_pages(gold_pages):
        ids = []
        for gp in gold_pages:
            if isinstance(gp, int):
                ids.append(gp)
            elif isinstance(gp, dict):
                pid = lookup_page_id(gp["doc_id"], gp["page_number"])
                if pid is not None:
                    ids.append(pid)
        return set(ids)

    no_context_data = json.loads(NO_CONTEXT_AUDIT.read_text())
    no_context_by_id = {}
    for qc in no_context_data["questions"]:
        no_context_by_id[qc["question_id"]] = qc

    console.rule("[bold]Setting up retriever[/bold]")
    with pgvector_store.connect() as conn:
        retriever_cfg = retrieval.RetrievalConfig(
            centroid_table=MCU_CENTROID_TABLE,
            per_token_k=50,
            candidates=100,
            ef_search=200,
        )
        retriever = retrieval.TwoStageRetriever(store, conn, retriever_cfg)
        warm_ms = retriever.warm()
        console.print(f"[dim]Warmed store in {warm_ms:.0f} ms[/dim]")

        if not vllm_health():
            console.print("[red]vLLM server not healthy -- aborting[/red]")
            return 1

        records = []
        for q_idx, q_data in enumerate(questions, 1):
            qid = q_data["question_id"]
            question = q_data["question"]
            gold_pages = q_data["gold_pages"]
            core_required = q_data["core_required_facts"]
            supporting = q_data.get("supporting_details", [])
            reference_answer = q_data.get("reference_answer", "")

            console.rule(f"[bold]Question {q_idx}/12: {qid}[/bold]")
            console.print(f"[cyan]Question: {question[:120]}...[/cyan]")

            retrieval_start = time.perf_counter()
            result = retriever.retrieve(question, k=10)
            retrieval_elapsed = (time.perf_counter() - retrieval_start) * 1000

            retrieved_pages = []
            for corpus_id, score in result.pages:
                row = by_page_id.loc[corpus_id]
                retrieved_pages.append({
                    "corpus_id": int(corpus_id),
                    "doc_id": row["doc_id"],
                    "page_number": int(row["page_number"]),
                    "score": round(float(score), 4),
                    "image": Image.open(row["path"]).convert("RGB"),
                })

            console.print(
                f"[dim]Retrieved {len(result.pages)} pages in "
                f"{retrieval_elapsed:.0f} ms "
                f"(encode {result.encode_ms:.0f}, stage1 {result.stage1_ms:.0f}, "
                f"stage2 {result.stage2_ms:.0f})[/dim]"
            )

            shown_pages = retrieved_pages[:MAX_PAGES]
            answer_result = vllm_answer(question, shown_pages)

            console.print(
                f"[dim]Answer: {answer_result['text'][:150]}...[/dim]"
            )
            console.print(
                f"[dim]Cited pages: {answer_result['cited_pages']}, "
                f"latency: {answer_result['latency_ms']:.0f} ms[/dim]"
            )

            gold_page_ids = resolve_gold_pages(gold_pages)
            retrieved_ids = [p["corpus_id"] for p in retrieved_pages]
            relevance = []
            for rp in retrieved_pages:
                if rp["corpus_id"] in gold_page_ids:
                    relevance.append(2)
                else:
                    relevance.append(0)
            ndcg10 = round(ndcg_at_k(relevance, 10), 4)
            recall10 = round(recall_at_k(retrieved_ids, gold_page_ids, 10), 4)

            console.print(f"[dim]NDCG@10: {ndcg10}, Recall@10: {recall10}[/dim]")

            no_ctx_q = no_context_by_id.get(qid, {})
            no_ctx_verdict = no_ctx_q.get("human_review", {}).get("verdict", "unknown")
            no_ctx_checks = no_ctx_q.get("fact_checks", [])

            assessment = assess_answer(
                answer_result["text"], core_required, supporting,
                no_ctx_verdict, no_ctx_checks
            )

            record = {
                "question_id": qid,
                "question": question,
                "gold_pages": gold_pages,
                "retrieved_pages": [
                    {
                        "corpus_id": p["corpus_id"],
                        "doc_id": p["doc_id"],
                        "page_number": p["page_number"],
                        "score": p["score"],
                    }
                    for p in retrieved_pages
                ],
                "retrieval_timing_ms": round(retrieval_elapsed, 1),
                "retrieval_stages": {
                    "encode_ms": round(result.encode_ms, 1),
                    "stage1_ms": round(result.stage1_ms, 1),
                    "stage2_ms": round(result.stage2_ms, 1),
                },
                "generation": {
                    "answer": answer_result["text"],
                    "cited_pages": answer_result["cited_pages"],
                    "shown_pages": answer_result["shown_pages"],
                    "refused": answer_result["refused"],
                    "latency_ms": answer_result["latency_ms"],
                    "usage": answer_result["usage"],
                },
                "retrieval_metrics": {
                    "ndcg_at_10": ndcg10,
                    "recall_at_10": recall10,
                },
                "assessment": assessment,
                "model_settings": {
                    "model": "qwen2.5-vl-7b-awq",
                    "max_tokens": MAX_TOKENS,
                    "temperature": TEMPERATURE,
                },
                "prompts": {
                    "system_prompt": SYSTEM_PROMPT,
                    "user_question": question,
                },
            }
            records.append(record)

            console.rule(f"[bold]Question {q_idx}/12 complete[/bold]")
            console.print(f"[green]Verdict: {assessment['verdict']}[/green]")
            console.print(f"[dim]Core facts: {assessment['core_facts_met']}/{assessment['core_facts_total']}[/dim]")
            if assessment["improved_from_no_context"]:
                console.print(f"[yellow]Improvement: {assessment['improvement_reason']}[/yellow]")

        total_elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

        # Summary
        all_ndcg = [r["retrieval_metrics"]["ndcg_at_10"] for r in records]
        all_recall = [r["retrieval_metrics"]["recall_at_10"] for r in records]
        all_verdicts = [r["assessment"]["verdict"] for r in records]
        improved_count = sum(1 for r in records if r["assessment"]["improved_from_no_context"])

        summary = {
            "evaluation_timestamp": started_at.isoformat(),
            "total_questions": len(records),
            "total_elapsed_seconds": round(total_elapsed, 1),
            "retrieval_metrics": {
                "ndcg_at_10": {
                    "mean": round(np.mean(all_ndcg), 4),
                    "median": round(np.median(all_ndcg), 4),
                    "min": round(min(all_ndcg), 4),
                    "max": round(max(all_ndcg), 4),
                },
                "recall_at_10": {
                    "mean": round(np.mean(all_recall), 4),
                    "median": round(np.median(all_recall), 4),
                    "min": round(min(all_recall), 4),
                    "max": round(max(all_recall), 4),
                },
            },
            "answer_verdicts": {
                "correct": all_verdicts.count("correct"),
                "partial": all_verdicts.count("partial"),
                "incorrect": all_verdicts.count("incorrect"),
                "abstained": all_verdicts.count("abstained"),
            },
            "improved_from_no_context": improved_count,
            "per_question": records,
        }

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        json_path = REPORTS_DIR / "mcu_evaluation.json"
        json_path.write_text(json.dumps(summary, indent=2, default=str))
        console.print(f"\n[dim]JSON report saved to {json_path}[/dim]")

        # Markdown report
        md_lines = []
        md_lines.append("# MCU RAG Evaluation Report\n")
        md_lines.append(f"Generated: {started_at.isoformat()}")
        md_lines.append(f"Questions: {len(records)}")
        md_lines.append(f"Elapsed: {total_elapsed:.1f}s\n")

        md_lines.append("## Summary\n")
        md_lines.append(f"| Metric | Mean | Median | Min | Max |")
        md_lines.append(f"|--------|------|--------|-----|-----|")
        md_lines.append(f"| NDCG@10 | {np.mean(all_ndcg):.4f} | {np.median(all_ndcg):.4f} | {min(all_ndcg):.4f} | {max(all_ndcg):.4f} |")
        md_lines.append(f"| Recall@10 | {np.mean(all_recall):.4f} | {np.median(all_recall):.4f} | {min(all_recall):.4f} | {max(all_recall):.4f} |")
        md_lines.append(f"\nAnswer verdicts: {summary['answer_verdicts']}")
        md_lines.append(f"Improved from no-context: {improved_count}/12\n")
        md_lines.append("---\n")

        for r in records:
            md_lines.append(f"## {r['question_id']}\n")
            md_lines.append(f"**Question:** {r['question']}\n")
            md_lines.append(f"**Gold pages:** {r['gold_pages']}\n")

            md_lines.append("### Retrieval Results\n")
            md_lines.append("| # | Page ID | Doc ID | Page # | Score |")
            md_lines.append("|---|---------|--------|--------|-------|")
            for i, p in enumerate(r["retrieved_pages"]):
                md_lines.append(f"| {i+1} | {p['corpus_id']} | {p['doc_id']} | {p['page_number']} | {p['score']:.4f} |")
            md_lines.append(f"\nNDCG@10: {r['retrieval_metrics']['ndcg_at_10']} | Recall@10: {r['retrieval_metrics']['recall_at_10']}")
            md_lines.append(f"\nRetrieval time: {r['retrieval_timing_ms']:.1f} ms\n")

            md_lines.append("### Answer\n")
            md_lines.append(f"**{r['generation']['answer']}**\n")
            md_lines.append(f"Cited pages: {r['generation']['cited_pages']}")
            md_lines.append(f"Latency: {r['generation']['latency_ms']:.0f} ms\n")

            md_lines.append("### Assessment\n")
            md_lines.append(f"**Verdict:** {r['assessment']['verdict']}\n")
            md_lines.append(f"Core facts met: {r['assessment']['core_facts_met']}/{r['assessment']['core_facts_total']}\n")

            if r['assessment']['improved_from_no_context']:
                md_lines.append(f"**Improvement:** {r['assessment']['improvement_reason']}\n")

            md_lines.append("| Fact | Status | Key Terms Found | Term Ratio |")
            md_lines.append("|------|--------|-----------------|------------|")
            for fc in r['assessment']['fact_checks']:
                md_lines.append(f"| {fc['fact'][:80]} | {fc['status']} | {fc['key_terms_found']} | {fc['term_ratio']} |")
            md_lines.append("\n---\n")

        md_path = REPORTS_DIR / "mcu_evaluation.md"
        md_path.write_text("\n".join(md_lines))
        console.print(f"[dim]Markdown report saved to {md_path}[/dim]")

        console.rule("[bold]Evaluation complete[/bold]")
        console.print(f"[green]Summary: {summary['answer_verdicts']}[/green]")
        console.print(f"[green]NDCG@10: mean={np.mean(all_ndcg):.4f}, recall@10: mean={np.mean(all_recall):.4f}[/green]")
        console.print(f"[green]Improved from no-context: {improved_count}/12[/green]")

        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
