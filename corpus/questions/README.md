# MCU question pilot

`errata_candidates.json` contains 12 assistant-authored draft questions: four each for
STM32F103, STM32F407 and ESP32. Five currently require multiple documents; seven use a
single document, sometimes across pages. Raspberry Pi coverage and independently collected
engineer questions remain future work. This batch establishes a review process, not the final
60–80-question dataset.

These scenarios were written while reading errata, with selected implementation details
looked up in reference manuals. They are not verbatim questions from engineers and should
not be presented as independently collected demand. Adding register lookups changes question
selection; record that choice when reporting results. No retrieval rankings were used to
choose the draft gold pages. A table/register-map label describes evidence, not proof that
OCR fails or visual retrieval wins.

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
2. Read the linked page images. Verify every required answer fact, including units, binary
   encodings, revision applicability and multi-page continuations. Reference answers are
   paraphrases, not vendor quotations. Flag source contradictions rather than silently
   repairing them; draft 005 explicitly normalizes ambiguous errata notation using RM0090.
3. Check whether each question needs all the claimed documents. A supporting manual page
   does not automatically make a question cross-document. Draft 003 has a substantive
   manual/errata conflict; other cross-document questions add register implementation detail.
4. Review grades: 2 means a page independently answers the entire question; 1 means it
   supplies part of the answer. The lists are provisional and not exhaustive. Search for
   alternate answering pages and equivalent evidence sets before freezing qrels. A contents
   page that only names the issue is not answering evidence. For multi-document questions,
   later report complete-evidence coverage alongside NDCG; ranking several partial pages
   from one document does not establish that all required facts were retrieved.
5. Record the reviewer and decision in the source JSON; the generated Markdown checkboxes
   are a reading aid and are overwritten when rebuilt. Unresolved or ambiguous candidates
   should be revised or excluded before inference.

## Planned no-context audit (not run)

Freeze reviewed wording and required facts before asking the deployed Qwen2.5-VL generator
each question in an independent request containing only the question and a neutral instruction
to answer or state uncertainty. Do not include documents, source sections, answers, earlier
questions, or retrieval results. Do not reuse the RAG instruction that requires page citations:
that could cause automatic refusals when pages are absent. Record the exact model/revision,
quantization, prompt, decoding parameters, timestamp and raw response.

Judge responses against all required facts. Label them `correct`, `partial`, `incorrect`,
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
