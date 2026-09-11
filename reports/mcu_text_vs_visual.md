# MCU text versus visual retrieval — 12-question pilot

Both paths retrieve from the same 1,201 pages and pass the top 3 page images to Qwen2.5-VL-7B-AWQ using the same grounded prompt and decoding settings.

| Metric | Native text / BGE-M3 | Visual / ColQwen2 |
|---|---:|---:|
| ndcg_at_10 | 0.6132 | 0.9369 |
| recall_at_10 | 0.7917 | 1.0000 |
| recall_at_3 | 0.5417 | 0.8750 |
| Complete core evidence in shown pages | 7/12 | 11/12 |
| Answers: correct | 4 | 3 |
| Answers: partial | 4 | 8 |
| Answers: incorrect | 4 | 1 |
| Answers: abstained | 0 | 0 |

Visual minus text NDCG@10: **+0.3238**.

Visual retrieval ranks the annotated evidence better on this pilot. It does not produce more fully correct answers in these single runs.

The text path answers question 009 correctly for both registers, while the visual path imports an unrelated FIFO-read workaround for GPIO. Retrieval quality and answer correctness therefore need separate reporting.

Text extraction: pypdf native text, default extraction. BGE-M3 fp16, batch 16, 4096 tokens, normalized dense vectors. Three non-gold pages exceed 4096 tokens; all gold pages fit (maximum 706 tokens). No page has empty extracted text.

A separate HNSW index was built (m=16, ef_construction=64, ef_search=100). The sampled query plan chose an exact sequential scan on this small corpus. Search matched forced exact top-10 on all 12 questions; do not call this an ANN speed result.

## Per-question comparison

| Question | Text NDCG@10 | Visual NDCG@10 | Text answer | Visual answer |
|---|---:|---:|---|---|
| mcu-draft-001 | 0.0000 | 1.0000 | incorrect | partial |
| mcu-draft-002 | 1.0000 | 1.0000 | correct | correct |
| mcu-draft-003 | 0.0000 | 0.3562 | incorrect | incorrect |
| mcu-draft-004 | 0.4307 | 1.0000 | incorrect | partial |
| mcu-draft-005 | 0.3155 | 1.0000 | incorrect | partial |
| mcu-draft-006 | 0.3010 | 1.0000 | partial | partial |
| mcu-draft-007 | 0.7602 | 0.8869 | partial | partial |
| mcu-draft-008 | 1.0000 | 1.0000 | correct | correct |
| mcu-draft-009 | 1.0000 | 1.0000 | correct | partial |
| mcu-draft-010 | 0.9197 | 1.0000 | partial | partial |
| mcu-draft-011 | 1.0000 | 1.0000 | partial | partial |
| mcu-draft-012 | 0.6309 | 1.0000 | correct | correct |

## Limitations

- 12 assistant-authored prose-answer questions; provisional gold labels.
- Native pypdf text extraction, not OCR; result does not isolate an OCR failure or a visual-layout advantage from encoder/architecture differences.
- Same generator configuration, but single runs do not eliminate output variability. No generator superiority or significance claim.
- Answer judgments are assistant semantic reviews. Partial can include materially wrong advice; these are not all usable answers.
- No-context and grounded prompts differ; comparison measures workflows.

## Reviewed answers

- [Text-run answers](../reports/mcu_text_20260908T180110Z/reviewed/mcu_evaluation.md)
- [Visual-run answers](../reports/mcu_rag_20260908T165429Z/reviewed/mcu_evaluation.md)
