# MCU question pilot

`errata_candidates.json` contains 12 assistant-authored draft questions: four each for
STM32F103, STM32F407 and ESP32. All 12 are single-document questions under their core-answer
rubrics; five retain optional reference-manual pages separately from scored gold. Question 010
requires two pages of the same errata; question 007 has a full-answer page plus a partial page.
Raspberry Pi coverage and independently collected
engineer questions remain future work. This batch establishes a review process, not the final
60–80-question dataset.

These scenarios were written while reading errata and phrased as concise troubleshooting
questions, with selected implementation details looked up in reference manuals. They are not
verbatim questions from engineers and should
not be presented as independently collected demand. Adding register lookups changes question
selection; record that choice when reporting results. No retrieval rankings were used to
choose the draft gold pages. A table/register-map label describes evidence, not proof that
OCR fails or visual retrieval wins.

An assistant source review on 2026-09-08 checked the cited PDF text and rendered evidence,
corrected wording, answers, scope and grades, and recorded the outcome in `assistant_review`.
This is separate from `human_review` and `no_context_audit`. Existing Markdown
approvals for questions 001 and 002 are preserved in `human_review.prior_review`. The user
approved all 12 revised questions on 2026-09-08 before the first no-context audit.
The retrieval annotations are still provisional, including
alternate answering pages outside the checked references.

## Reproduce the review

After fetching and rendering the corpus:

```bash
.venv/bin/python scripts/12_prepare_questions.py
```

This verifies local PDF hashes, checks that cited pages belong to the selected corpus,
extracts the three standalone errata documents into `reports/mcu_errata_pages.jsonl`, and
builds `reports/mcu_question_review.md` with links to the rendered evidence pages. Extracted
vendor text stays gitignored. The script does not download documents, run a model, or score
retrieval. RP2040's embedded errata appendix is not included in this first extraction.

Source hashes are frozen in the candidate file; source URLs remain in `../mcu_manifest.json`.
References use `doc_id` plus **physical, 1-based PDF page number**, not printed page labels.
For example, ESP32 physical p16 is printed p13. Resolve retrieval `page_id` values from the
current `pages.parquet` only when exporting approved annotations; document ordinals can change.

## Review before the no-context audit

1. Read each question without its answer. Check that part, package, silicon revision and
   operating conditions are sufficient, and that the requested details form a plausible task.
2. Read the linked page images. Verify every core required fact and every supporting detail,
   including units, binary encodings, revision applicability and multi-page continuations.
   Only `core_required_facts` are mandatory when judging answer correctness;
   `supporting_details` add sourced implementation detail but their omission is not an error.
   Reference answers are
   paraphrases, not vendor quotations. Flag source contradictions rather than silently
   repairing them; draft 005 explicitly normalizes ambiguous errata notation using RM0090.
3. Check whether each question needs all the claimed documents. A supporting manual page
   does not automatically make a question cross-document. Draft 003 has a substantive
   manual/errata conflict, but discussing it is optional for the current question. All 12
   currently have single-document scope. `supporting_pages` holds optional evidence without
   relevance grades; it does not contribute to scope or qrels. `gold_pages` grades and
   `evidence_type` describe the core answer, not optional embellishments: drafts 009 and 012
   have prose core evidence even though their pages also contain a table or equation.
4. Review grades: 2 means a page independently answers the entire question; 1 means it
   supplies part of the answer. The lists are provisional and not exhaustive. Search for
   alternate answering pages and equivalent evidence sets before freezing qrels. A contents
   page that only names the issue is not answering evidence. For multi-document questions,
   later report complete-evidence coverage alongside NDCG; ranking several partial pages
   from one document does not establish that all required facts were retrieved.
5. Record the reviewer and decision in the source JSON; the generated Markdown checkboxes
   reflect `human_review.status` (`approved` checks both boxes) and are overwritten when rebuilt.
   Assistant source checks never imply human approval. Unresolved or ambiguous candidates
   should be revised or excluded before inference.

## No-context audit

The subsequent visual RAG run has been rescored using the shared linear-gain retrieval
metrics and explicit semantic answer review. See `reports/mcu_evaluation.md` and
`reports/mcu_evaluation.json`: NDCG@10 0.9369, recall@10 1.0, 3 correct, 8 partial,
1 incorrect, and 7 improved verdicts over the no-context baseline. Complete core evidence
was shown for 11/12 questions; question 003's gold page ranked sixth and was not shown.
The answer judgments and per-fact context coverage are recorded in
`rag_answer_review_20260908T161223.json`, bound to exact answer text, question, rubric
and shown pages. These are assistant judgments; missing optional details are not errors.
The original run lacked full API responses, so truncation cannot be retrospectively verified.

To rescore without model calls, run:

```bash
.venv/bin/python scripts/12_mcu_evaluation.py \
  --rescore reports/mcu_evaluation_original/mcu_evaluation.json \
  --reviews corpus/questions/rag_answer_review_20260908T161223.json \
  --output-dir reports/mcu_evaluation_rescored_new
```

Without `--rescore`, this entry point collects a new visual RAG run with exact image
requests and raw API responses. Without a matching `--reviews` file, answer judgments
remain pending; they are never inferred from keyword overlap. Output directories must
be new. The initial erroneous reports and script are preserved in
`reports/mcu_evaluation_original/`.

## MCU text-versus-visual comparison

The comparison uses the fresh visual run `reports/mcu_rag_20260908T165429Z/reviewed/`
and text run `reports/mcu_text_20260908T180110Z/reviewed/`. All 24 API responses ended
with `stop`; exact image requests and raw responses are preserved. The text run uses
native pypdf text from all 1,201 hash-verified selected pages, BGE-M3 fp16, batch size 16,
4096 tokens, and a separate database table. Three non-gold pages were truncated; no gold
page was truncated and no extracted page was empty. Both paths send top-3 page images
to the same generator configuration. This compares retrievers, not text-only versus
image-based answer generation.

`reports/mcu_text_vs_visual.md` and `.json` report NDCG@10 0.6132 versus 0.9369 and
recall@10 0.7917 versus 1.0 (text then visual). Core evidence coverage is 7/12 versus
11/12. Correct/partial/incorrect answer counts are 4/4/4 versus 3/8/1, based on explicit
semantic review in `text_rag_answer_review_20260908T180110.json` and
`rag_answer_review_20260908T165429.json`. The visual path does not have a higher
fully-correct answer count in these single runs. Do not claim OCR failure, a demonstrated
visual-layout advantage, or general significance from this 12-question prose pilot.

`scripts/14_mcu_text_baseline.py` collects a new text run in unique data/report directories
and a unique database table; it never overwrites the visual index. It requires running
Postgres/vLLM and leaves semantic judgments pending. To regenerate the comparison from
the reviewed runs:

```bash
.venv/bin/python scripts/15_compare_mcu_retrieval.py \
  --text reports/mcu_text_20260908T180110Z/reviewed/mcu_evaluation.json \
  --visual reports/mcu_rag_20260908T165429Z/reviewed/mcu_evaluation.json \
  --output reports/mcu_text_vs_visual
```

## Original no-context results

The first run, `20260908T134053918802Z`, is complete: **0 correct, 5 partial, 5 incorrect,
2 abstained** under assistant review of the core facts. All 12 remain in the retrieval-dependent
answer subset; no responses were truncated. The immutable
[audit record](no_context_audits/20260908T134053918802Z.json) includes the frozen questions,
rubrics, exact requests, raw responses, runtime metadata and fact-by-fact judgments.
The readable response review is `reports/mcu_no_context_review.md`. Candidate JSON also
contains each verdict and response. Abstention includes deferral to documentation without
a concrete answer; it does not certify the truth of surrounding claims.

With the model server running, `.venv/bin/python scripts/13_no_context_audit.py` collects a
**new** run in a unique report directory. It does not grade responses or overwrite existing
audit results. The first run used temperature 0, top_p 1, seed 0 and max_tokens 1536.
The server identifies Qwen2.5-VL-7B-Instruct-AWQ; the recorded cached commit is not proof
of the loaded revision because the running server command did not pin a commit.

Protocol used for this run:

Freeze reviewed wording, core required facts and supporting details before asking the deployed
Qwen2.5-VL generator each question in an independent request containing only the question and a neutral instruction
to answer or state uncertainty. Do not include documents, source sections, answers, earlier
questions, or retrieval results. Do not reuse the RAG instruction that requires page citations:
that could cause automatic refusals when pages are absent. Record the exact model/revision,
quantization, prompt, decoding parameters, timestamp and raw response.

Judge responses against all core required facts. Do not penalize omission of supporting details
that the question did not request. Label responses `correct`, `partial`, `incorrect`,
`abstained`, or `uncertain`; an uncertain judgment requires review. Correct paraphrases count.
Exclude fully correct unaided answers from the retrieval-dependent answer subset, while
retaining every candidate and response in the audit record. Partial responses do not count
as fully correct. Do not tune prompts until a desired rejection rate appears: discarding more
than half is an expectation in the original plan, not a target or acceptance criterion.

A failed no-context answer only shows that this model under this protocol failed to answer;
it does not prove the fact is absent from its weights. Filtering creates a model-dependent
subset. Retrieval-only NDCG already measures page ranking independently of generator knowledge;
publish the selection method and preferably retrieval scores for both the complete reviewed
set and the audited subset. Do not claim a text-vs-visual win before measuring it.

Refusal-threshold calibration and held-out evaluation come later. These 12 answerable pilot
questions do not constitute a refusal evaluation set or justify any threshold.
