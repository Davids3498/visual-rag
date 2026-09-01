# Visual RAG — self-hosted, calibrated on ViDoRe V3

A visual-document RAG system: page *images* embedded directly with a late-interaction
vision-language retriever (ColQwen2), compared head-to-head against an OCR-text baseline on
identical ground, then served on GPU with real latency/throughput/cost numbers.

- **Part 1** (this repo, in progress) — build the pipeline and calibrate it against the public
  [`vidore/vidore_v3_industrial`](https://huggingface.co/datasets/vidore/vidore_v3_industrial)
  benchmark. The benchmark is a *correctness gate*, not the product.
- **Part 2** — same pipeline, pointed at a microcontroller-datasheet corpus built from scratch.

Plan documents: [part1-pipeline-and-serving.md](part1-pipeline-and-serving.md),
[part2-own-corpus-and-contribution.md](part2-own-corpus-and-contribution.md).

## Status

| step | what | state |
|---|---|---|
| 0 | Environment (uv, pinned, GPU check) | done |
| 1 | Load + inspect ViDoRe V3, build eval set | done — 177-query eval slice, counts verified |
| 2 | Text baseline (BGE-M3 + pgvector, NDCG@10) | done — **NDCG@10 0.464** |
| 3 | Visual retrieval (ColQwen2, two-stage ANN → MaxSim rerank) | todo |
| 4 | Calibration checkpoint vs published ballpark | todo |
| 5 | Generation on self-hosted quantized Qwen2.5-VL (vLLM) | todo |
| 6 | Serving on k3s with GPU scheduling | todo |
| 7 | Latency / throughput / GPU-util / cost-per-1k | todo |

## Results

_Calibration and serving numbers land here once steps 2-7 are done._

177 English human-written queries, 5,244-page corpus, graded relevance. Scored with
`pytrec_eval` (the trec_eval C implementation the leaderboard uses).

| retriever | NDCG@10 | recall@10 | success@10 | MAP |
|---|---|---|---|---|
| text — BGE-M3 over OCR markdown | **0.464** | 0.517 | 0.802 | 0.383 |
| visual — ColQwen2, two-stage | — | — | — | — |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and an NVIDIA GPU (developed on a 24 GB RTX 3090).
Python version is pinned in `.python-version`; exact package versions are pinned in `uv.lock`.

```bash
uv sync                       # Part 0-1: data plumbing only
uv sync --extra retrieval     # adds torch / colpali-engine / sentence-transformers (steps 2-3)
export HF_TOKEN=hf_...        # dataset is public; a token avoids anonymous rate limits
docker compose up -d          # pgvector on :5434 (5432/5433 were already taken on my box)
```

The Postgres DSN is `postgresql://vrag:vrag@localhost:5434/vrag`, overridable with `VRAG_PG_DSN`.

## Running

```bash
make env        # environment + GPU report               -> reports/env_report.json
make data       # download the 4 subsets, build eval set -> data/eval/*.parquet
make sanity     # render sample pages + gold spans       -> reports/sanity/*.png
make db-up      # pgvector container
make baseline   # step 2: embed, index, score NDCG@10    -> reports/text_baseline.json
```

Each of those is a plain script under `scripts/` if you'd rather skip `make`.

## Layout

```
src/visual_rag/      importable package (config, dataset loading, eval-set construction)
scripts/             numbered entry points, one per build step
data/                HF cache-backed artifacts (gitignored)
reports/             generated reports, stats, sanity renders (gitignored)
```

## Dataset notes — what step 1 actually measured

`vidore/vidore_v3_industrial` — 5,244 pages from 27 US Air Force technical manuals, with
**graded** relevance judgements (2 = page fully answers, 1 = partial) and per-annotator bounding
boxes. All four subsets matched the dataset card exactly (5,244 / 1,698 / 9,684 / 27).

The eval slice (`language == english`, `query_generator == human`):

| | |
|---|---|
| queries | **177** |
| relevance judgements | 903 (684 partial, 219 full-answer) |
| relevant pages per query | mean 5.1, median 3, max 26 |
| queries needing >1 document | 11 |
| distinct gold pages | 670 across 22 of the 27 documents |
| gold spans tagged non-text | 276 / 903 (Table 154, Infographic 95, Image 24) |
| queries with any non-text gold | 81; entirely non-text: **20** |

Two numbers in the plan doc did not survive contact with the data, and both are worth knowing
before scoring anything:

- **177 eval queries, not 283.** There are 283 English queries, but only 177 have
  `query_generator == human`; the other 106 are synthetic (`sdg`). The five other languages are
  translations of the same 283. `--generator any` builds the wider 283-query slice if needed.
- **~5.1 relevant pages per query, not 1.8.** Across all 1,698 queries it is 5.7. This makes the
  choice of NDCG@10 more important, not less: with a median of 3 relevant pages, plain recall@10
  would be nearly saturated and would hide the text-vs-visual difference.

Two facts that shape the comparison itself:

- **No gold page has empty OCR** (205 of 5,244 corpus pages do, but none of the 903 gold pages).
  The text baseline is therefore not handicapped by missing input — if it loses, it loses on
  layout, not on absent text. That keeps the headline delta honest.
- The `visual_only` column on `eval_queries.parquet` marks the 20 queries whose evidence is
  *entirely* table/diagram/image. Step 4 reports the delta on that subset as well as overall.

`reports/sanity/` shows why: on `q0162` the gold evidence is a 13-row equipment/stock-number
table, and the OCR beside it flattens the table into pipe-delimited text with the words of one
cell scrambled into another. On `q0122` a two-column page interleaves an acronym list with an
unrelated publications table, so the row a query needs is split across the linear text.

## Step 2 — the text baseline

One BGE-M3 dense vector per page over the corpus `markdown` column, a plain HNSW index in
pgvector, cosine similarity. Deliberately the simple system: it exists to be a fair comparison
point for step 3, not to be good.

| | |
|---|---|
| embedding | 5,244 pages in 78 s (67 pages/s), fp16 on an RTX 3090, batch 16 |
| truncation | 0 pages (max page is 2,646 tokens, limit 4,096) |
| index | HNSW m=16, ef_construction=64, built in 0.9 s · 71 MB total (41.5 MB index) |
| search, top-10 | p50 **0.78 ms**, p95 1.24 ms — HNSW index scan |
| search, top-100 | p50 15.6 ms — sequential scan (see below) |
| query embedding | 2.5 ms/query |
| ANN recall@10 vs exact | 0.98 at ef_search=100 |

### Per-slice results, and why they are not comparable to each other

| slice | n | NDCG@10 | recall@10 | mean gold pages |
|---|---|---|---|---|
| all | 177 | 0.464 | 0.517 | 5.1 |
| visual_only (gold is entirely table/diagram) | 20 | 0.588 | 0.725 | 1.4 |
| any visual gold | 81 | 0.453 | 0.448 | 7.2 |
| text-only gold | 96 | 0.473 | 0.575 | 3.4 |
| multi-document | 11 | 0.151 | 0.100 | 12.6 |

The `visual_only` slice scoring *higher* is not evidence that OCR handles tables well — those
queries average 1.4 gold pages while the text-only slice averages 3.4, and NDCG is far easier
to satisfy when there is one right answer than when there are twelve. **Slice-to-slice
comparison within one retriever is confounded by gold-page count.** The comparison that is
valid is text vs visual *on the same slice*, per query, which is what step 4 does.

The multi-document slice (NDCG 0.151, recall@10 0.100) is the honest weak spot: single-vector
retrieval of one page at a time has no mechanism for "one page from each of two manuals".

### The ANN result worth knowing

At the metric cutoff (k=10) Postgres uses the HNSW index and answers in 0.78 ms. At depth 100
the planner **drops the index and sequentially scans** all 5,244 rows — on a corpus this small
an exact scan is cheaper than a wide-beam graph traversal, and the two paths return the same
thing. So the ANN machinery is not what makes this fast *here*; it is in place because Part 2
and the two-stage visual path in step 3 need it to hold up at a scale where it does matter.
Reporting the 15.6 ms depth-100 number as "ANN latency" would have been wrong.

The scorer is checked against `pytrec_eval` on every run and the script aborts if the two
disagree by more than 1e-3 — a metric bug and a retrieval result look identical otherwise.

## Development

```bash
make lint    # ruff check + format check
make test    # pytest (unit tests + invariants on the built eval set)
```
