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
| 1 | Load + inspect ViDoRe V3, build eval set | done — 283-query eval slice, counts verified |
| 2 | Text baseline (BGE-M3 + pgvector, NDCG@10) | done — **NDCG@10 0.390** |
| 3 | Visual retrieval (ColQwen2, two-stage ANN → MaxSim rerank) | done — **NDCG@10 0.500** |
| 4 | Calibration checkpoint vs published ballpark | done — **PASS** |
| 5 | Generation on self-hosted quantized Qwen2.5-VL (vLLM) | done — AWQ int4, 14.3 GB |
| 6 | Serving on k3s with GPU scheduling | done — **verified on k3s**, `reports/k8s.json` |
| 7 | Latency / throughput / GPU-util / cost-per-1k | done — **$0.58/1k vs $5.39 hosted** |

## Results

_Retrieval is calibrated and closed; serving numbers are in [step 7](#step-7--the-serving-numbers)._

All **283 English queries**, 5,244-page corpus, graded relevance. Scored with `pytrec_eval`
(the trec_eval C implementation the leaderboard uses).

| retriever | NDCG@10 | recall@10 | success@10 | MAP |
|---|---|---|---|---|
| text — BGE-M3 over OCR markdown | 0.390 | 0.444 | 0.742 | 0.320 |
| visual — ColQwen2, two-stage | **0.500** | 0.497 | 0.799 | 0.434 |
| visual — exhaustive MaxSim (ceiling, not a serving path) | 0.519 | 0.528 | 0.834 | 0.460 |

**The delta reproduces: +0.110 NDCG@10 for visual over text**, and it widens to **+0.194** on the
queries an annotator wrote while looking at a page — see [where the delta lives](#where-the-delta-lives)
below, which is the most useful result in this half of the project.

The 283 queries split into 177 written by human annotators and 106 generated from document
summaries. Both are scored, always as slices of the same run:

| slice | n | text | visual | delta |
|---|---|---|---|---|
| all English queries | 283 | 0.390 | **0.500** | +0.110 |
| human-written | 177 | 0.464 | **0.622** | +0.158 |
| synthetic (`sdg`) | 106 | 0.268 | **0.298** | +0.030 |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and an NVIDIA GPU (developed on a 24 GB RTX 3090).
Python version is pinned in `.python-version`; exact package versions are pinned in `uv.lock`.

```bash
uv sync                       # Part 0-1: data plumbing only
uv sync --extra retrieval     # adds torch / colpali-engine / sentence-transformers (steps 2-3)
export HF_TOKEN=hf_...        # dataset is public; a token avoids anonymous rate limits
docker compose up -d          # pgvector on :5434 (5432/5433 were already taken on my box)
```

The Postgres DSN is `postgresql://vrag:vrag@localhost:5434/vrag`, overridable with `VRAG_PG_DSN`
— point it at `…@127.0.0.1:30434/vrag` to run the scripts and tests against the cluster's
pgvector instead of the Compose one. k3s writes its kubeconfig root-only, so
`sudo install -o $USER -g $USER -m 600 /etc/rancher/k3s/k3s.yaml ~/.kube/k3s.yaml` and
`export KUBECONFIG=~/.kube/k3s.yaml`.

## Running

```bash
make env        # environment + GPU report               -> reports/env_report.json
make data       # download the 4 subsets, build eval set -> data/eval/*.parquet
make sanity     # render sample pages + gold spans       -> reports/sanity/*.png
make db-up      # pgvector container
make baseline   # step 2: embed, index, score NDCG@10    -> reports/text_baseline.json
make visual     # step 3: ColQwen2 two-stage retrieval    -> reports/visual_retrieval.json
make calibrate  # step 4: gate vs published numbers       -> reports/calibration.json
make serve-up   # step 5: Qwen2.5-VL (AWQ) on vLLM        -> http://localhost:8000
make generate   # step 5: grounded answers with citations -> reports/generation.json
make k8s-up     # step 6: deploy to the cluster           (OVERLAY=minikube|k3s)
make k8s-verify # step 6: prove GPU scheduling + serving  -> reports/k8s.json
make bench      # step 7: latency/throughput/cost         -> reports/serving.json
make corpus     # step 9: fetch the Part 2 MCU corpus     -> reports/corpus_mcu.json
```

Each of those is a plain script under `scripts/` if you'd rather skip `make`.

## Layout

```
src/visual_rag/      importable package (config, dataset loading, eval-set construction)
scripts/             numbered entry points, one per build step
corpus/              Part 2 corpus *definition*: URLs, content hashes, page selection
data/                HF cache-backed artifacts and fetched PDFs (gitignored)
reports/             generated reports, stats, sanity renders (gitignored)
```

The split between `corpus/` and `data/` is deliberate: vendor documentation is not
redistributable, so the repository carries only the manifest that identifies each document
(URL, sha256, revision, which pages are in scope) and `make corpus` rebuilds `data/mcu/pdfs/`
from the vendors' own copies. A hash mismatch fails the run rather than quietly re-scoring
the retriever against a revision that changed underneath it.

## Dataset notes — what step 1 actually measured

`vidore/vidore_v3_industrial` — 5,244 pages from 27 US Air Force technical manuals, with
**graded** relevance judgements (2 = page fully answers, 1 = partial) and per-annotator bounding
boxes. All four subsets matched the dataset card exactly (5,244 / 1,698 / 9,684 / 27).

The eval slice is **all 283 English queries**. The other 1,415 rows are those same 283 questions
translated into five languages, so this is the complete English benchmark rather than a sample.

| | |
|---|---|
| queries | **283** (177 human-written, 106 generated from summaries) |
| relevance judgements | 1,614 (1,240 partial, 374 full-answer) |
| relevant pages per query | mean 5.7, median 3, max 34 |
| queries needing >1 document | 23 |
| distinct gold pages | 1,000 across 26 of the 27 documents |
| gold spans tagged non-text | 448 / 1,614 (Table 207, Infographic 201, Image 44) |
| queries with any non-text gold | 126; entirely non-text: **23** |

One number in the plan doc did not survive contact with the data: **~5.7 relevant pages per
query, not 1.8**. That makes the choice of NDCG@10 more important, not less — with a median of 3
relevant pages, plain recall@10 would be near-saturated and would hide the effect being measured.

Two facts that shape the comparison itself:

- **No gold page has empty OCR** (205 of 5,244 corpus pages do, but none of the 1,614 gold
  pages). The text baseline is therefore not handicapped by missing input — if it loses, it
  loses on layout, not on absent text. That keeps the headline delta honest.
- The `visual_only` column on `eval_queries.parquet` marks the 23 queries whose evidence is
  *entirely* table/diagram/image, and `query_generator` separates human from synthetic. Every
  result below is reported on those slices, from one run.

`reports/sanity/` shows why layout matters: on `q0162` the gold evidence is a 13-row
equipment/stock-number table, and the OCR beside it flattens the table into pipe-delimited text
with the words of one cell scrambled into another. On `q0122` a two-column page interleaves an
acronym list with an unrelated publications table, so the row a query needs is split across the
linear text.

## Step 2 — the text baseline

One BGE-M3 dense vector per page over the corpus `markdown` column, a plain HNSW index in
pgvector, cosine similarity. Deliberately the simple system: it exists to be a fair comparison
point for step 3, not to be good.

| | |
|---|---|
| embedding | 5,244 pages in 78 s (67 pages/s), fp16 on an RTX 3090, batch 16 |
| truncation | 0 pages (max page is 2,646 tokens, limit 4,096) |
| index | HNSW m=16, ef_construction=64, built in 0.9 s · 71 MB total (41.5 MB index) |
| search, top-10 | p50 **0.79 ms**, p95 1.09 ms — HNSW index scan |
| search, top-100 | p50 16.1 ms — sequential scan (see below) |
| query embedding | 1.6 ms/query |
| ANN recall@10 vs exact | 0.97 at ef_search=100 |

### Per-slice results

| slice | n | NDCG@10 | recall@10 | mean gold pages |
|---|---|---|---|---|
| all | 283 | 0.390 | 0.444 | 5.7 |
| human-written | 177 | 0.464 | 0.517 | 5.1 |
| synthetic | 106 | 0.268 | 0.322 | 6.7 |
| visual_only (gold is entirely table/diagram) | 23 | 0.572 | 0.696 | 1.4 |
| any visual gold | 126 | 0.358 | 0.356 | 8.0 |
| text-only gold | 157 | 0.417 | 0.515 | 3.9 |
| multi-document | 23 | 0.119 | 0.087 | 12.4 |

The `visual_only` slice scoring *higher* is not evidence that OCR handles tables well — those
queries average 1.4 gold pages while the text-only slice averages 3.9, and NDCG is easier to
satisfy when there is one right answer than when there are twelve. **Slice-to-slice comparison
within one retriever is confounded by gold-page count.** The comparison that is valid is text vs
visual *on the same slice*, which is what every table below does.

The multi-document slice (NDCG 0.119, recall@10 0.087) is the honest weak spot: single-vector
retrieval of one page at a time has no mechanism for "one page from each of two manuals".

### The ANN result worth knowing

At the metric cutoff (k=10) Postgres uses the HNSW index and answers in 0.79 ms. At depth 100
the planner **drops the index and sequentially scans** all 5,244 rows — on a corpus this small
an exact scan is cheaper than a wide-beam graph traversal, and the two paths return the same
thing. So the ANN machinery is not what makes this fast *here*; it is in place because Part 2
and the two-stage visual path in step 3 need it to hold up at a scale where it does matter.
Reporting the 16 ms depth-100 number as "ANN latency" would have been wrong.

The scorer is checked against `pytrec_eval` on every run and the script aborts if the two
disagree by more than 1e-3 — a metric bug and a retrieval result look identical otherwise.

## Step 3 — visual retrieval, and the shortlist that nearly sank it

ColQwen2 embeds each page as **756 vectors** (one per image patch), not one: 5,244 pages become
3.9M vectors and 1 GB on disk. A single ANN index over those returns *patches*, not pages, so
retrieval is two-stage — a compact page representation to build a shortlist, then exact MaxSim
late interaction over the shortlist only.

**The obvious stage-1 representation is a trap.** Mean-pooling each page into one vector is what
most write-ups do, and it retrieves only 53% of the gold pages at N=100 — dragging the final
score to 0.425, *below* the 0.390 text baseline's neighbourhood and erasing the entire result.
It isn't the ANN's fault: computing the same pooled ranking *exactly*, with no index, scores
identically. Averaging 756 patch vectors is simply lossy — a page holding a pin table and a
wiring diagram averages into a direction that matches neither.

Clustering each page's patches into **16 centroids** and running one indexed top-50 per query
token, unioned by page (the ColBERT/PLAID shape), fixes it:

| stage 1 | index | shortlist recall@100 | NDCG@10 |
|---|---|---|---|
| mean-pooled, 1 vector/page | 7.6 MB | 0.533 | 0.425 |
| 16 centroids/page, per-token ANN | 118.6 MB | **0.669** | **0.500** |
| exhaustive MaxSim (ceiling) | 1.01 GB in VRAM | 1.000 | 0.519 |

96.4% of the achievable quality, from an index 8.6× smaller than the multi-vector set it stands
in for (83,904 rows against 3.9M patch vectors). Both variants are built and scored on every
run, so the design choice is defended by numbers in `reports/visual_retrieval.json` rather than
asserted.

### Cost

| | |
|---|---|
| page embedding | 5,244 pages in 19.6 min (4.5 pages/s), bf16 on an RTX 3090, batch 8 |
| storage | 1,015 MB multi-vector (194 KB/page) vs 21 MB for the text baseline — **48×** |
| query encode | 10.6 ms |
| stage 1 (31 tokens × indexed top-50, one round trip) | p50 23.6 ms |
| stage 2 (MaxSim rerank of 100 pages, GPU) | p50 4.0 ms |
| end-to-end | ~38 ms |

### The honest note about brute force

Exhaustive MaxSim over all 5,244 pages takes **4.5 ms** on the GPU — faster *and* better than
the 28 ms two-stage path, because the entire 1 GB multi-vector corpus fits in VRAM. At this
corpus size the two-stage design is not a speed optimisation and pretending otherwise would be
dishonest. It is what keeps the design viable when the corpus stops fitting in memory, and it
costs 3.6% of the ceiling to get there. That trade is the point of the exercise; Part 2's corpus
is where it starts paying rent.

## Where the delta lives

Visual beats text on every slice, but the size of the win depends almost entirely on **how the
question was written** — and that is the most useful thing this half of the project found.

| slice | n | text | visual | delta | mean gold pages |
|---|---|---|---|---|---|
| human wrote it **looking at a page image** | 107 | 0.558 | **0.752** | **+0.194** | 3.7 |
| human wrote it from a **document summary** | 70 | 0.320 | 0.423 | +0.103 | 7.3 |
| generated from a **document summary** | 106 | 0.268 | 0.298 | +0.030 | 6.7 |

All 106 synthetic queries were generated from summaries; the human set is 107 image-sourced and
70 summary-sourced. Holding provenance fixed (the two summary rows) shows most of the gap is
about *what the question points at*, not who wrote it: a question written from a whole-document
summary asks about a theme spread over many pages, and no page-level retriever — visual or text
— can point at one page for it.

The same effect by question type:

| query type | n | text | visual | delta | mean gold pages |
|---|---|---|---|---|---|
| extractive | 125 | 0.470 | **0.619** | +0.149 | 4.2 |
| boolean | 44 | 0.472 | **0.621** | +0.148 | 5.1 |
| enumerative | 55 | 0.329 | 0.445 | +0.116 | 7.5 |
| multi-hop | 28 | 0.387 | 0.466 | +0.079 | 7.6 |
| numerical | 29 | 0.556 | **0.628** | +0.072 | 3.0 |
| open-ended | 67 | 0.215 | 0.243 | +0.028 | 8.7 |

Visual retrieval earns its keep exactly where retrieval is a well-posed page-level task — a fact
that lives *somewhere specific*. It converges with text on diffuse, open-ended questions. That is
a direct instruction for Part 2's question set: **prefer specific, page-localised questions**,
which is what errata entries and Stack Exchange questions naturally are.

These are point estimates on small slices. [Step 4](#step-4--calibration-checkpoint) puts
intervals on them, and two of these gaps turn out not to be conclusive — the summary-generated
row among them.

### Where neither retriever works

| slice | n | text | visual |
|---|---|---|---|
| gold is entirely table/diagram | 23 | 0.572 | **0.793** |
| any visual gold | 126 | 0.358 | **0.449** |
| text-only gold | 157 | 0.417 | **0.542** |
| multi-document | 23 | 0.119 | **0.160** |

Multi-document queries stay bad for both: retrieving pages independently has no mechanism for
"one page from each of two manuals", and that is a limitation of the architecture, not a tuning
problem.

## Step 4 — calibration checkpoint

The gate for the retrieval half: are these numbers *plausible* against what ViDoRe V3 publishes
for **this corpus**, and does the text-vs-visual delta survive a significance test? Not "am I
SOTA" — the benchmark is here to catch bugs.

### The comparison target was wrong in the plan, and it matters

The plan doc anchors on "best models ≈65% NDCG@10 on English". That is the **average across all
ten ViDoRe V3 datasets**. Industrial is the hardest of the ten and scores far below it — the
launch blogpost calls it the lowest-scoring public set. Judged against 0.65 a correct pipeline
looks broken; judged against the industrial column it is fine:

| model | industrial NDCG@10 | |
|---|---|---|
| nemo-colembed-3b | 0.570 | best at benchmark launch ([blogpost](https://huggingface.co/blog/QuentinJG/introducing-vidore-v3)) |
| nemotron-colembed-vl-8b-v2 | 0.560 | leaderboard #1 overall — 0.634 across all 10 datasets ([paper](https://arxiv.org/html/2602.03992v2)) |
| tomoro-colqwen3-embed-8b | 0.544 | |
| nemotron-colembed-vl-4b-v2 | 0.539 | |
| **mine — colqwen2-v1.0 (2B, 2024), exhaustive** | **0.519** | not on the V3 leaderboard, so no like-for-like figure |
| **mine — colqwen2-v1.0, two-stage (served)** | **0.500** | |
| mine — BGE-M3 over OCR text | 0.390 | no published OCR baseline exists for this subset |

Scored the way the leaderboard scores it: all 283 English queries, human-written and synthetic
together, graded NDCG@10. A 2B retriever from 2024 landing 2–5 points under a field of 3B–8B
models from 2026 is exactly the "plausible, not SOTA" the checkpoint asks for — and my
confidence interval overlaps the bottom of that band.

### With intervals, because 283 queries is not many

| system | NDCG@10 | 95% CI |
|---|---|---|
| text | 0.390 | [0.350, 0.432] |
| visual, two-stage | 0.500 | [0.457, 0.545] |
| visual, exhaustive | 0.519 | [0.476, 0.563] |

| paired comparison | Δ | 95% CI | p |
|---|---|---|---|
| visual − text | **+0.110** | [+0.074, +0.147] | 0.0001 |
| exhaustive − two-stage | +0.019 | [+0.008, +0.030] | 0.0005 |

Paired bootstrap over queries: both retrievers answer the same 283 questions, and query-to-query
variance dwarfs the gap between systems, so pairing is what makes the comparison readable. The
shortlist's 0.019 cost is small but *real* — the interval excludes zero — which is the honest
version of "97% of the ceiling".

### Which slices actually support a claim

| slice | n | text | visual | Δ | 95% CI | conclusive? |
|---|---|---|---|---|---|---|
| all | 283 | 0.390 | 0.500 | +0.110 | [+0.074, +0.147] | yes |
| human-written | 177 | 0.464 | 0.622 | +0.158 | [+0.108, +0.209] | yes |
| gold entirely table/diagram | 23 | 0.572 | 0.793 | +0.221 | [+0.078, +0.371] | yes |
| text-only gold | 157 | 0.417 | 0.542 | +0.125 | [+0.070, +0.182] | yes |
| any visual gold | 126 | 0.358 | 0.449 | +0.091 | [+0.049, +0.136] | yes |
| synthetic (`sdg`) | 106 | 0.268 | 0.298 | +0.030 | [−0.019, +0.079] | **no** |
| multi-document | 23 | 0.119 | 0.160 | +0.042 | [−0.014, +0.105] | **no** |

Two slices do **not** support a claim: on summary-generated queries and on multi-document
queries the visual advantage is indistinguishable from zero at this sample size. I would have
reported both as real effects on point estimates alone.

### Verdict: PASS

- visual beats text, interval excludes zero (Δ +0.110, p=0.0001)
- visual sits below the published industrial frontier but within reach (0.519 vs 0.539–0.570)
- the text baseline is a real baseline, not a broken one (0.390)
- the two-stage shortlist keeps 96.4% of its own ceiling

Retrieval is closed. No ColQwen2 tuning, no smarter reranker, no leaderboard chasing —
`reports/calibration.json` has the full record. Next is serving: Qwen2.5-VL on vLLM.

## Step 5 — generation on a self-hosted, quantized VLM

`Qwen2.5-VL-7B-Instruct-AWQ` (int4) served by vLLM v0.28 in its own container, answering from
the **page images** the retriever ranked. No OCR text reaches the generator, and every claim has
to carry a `[Page N]` citation so answers can be checked against the evidence instead of trusted.

The 3090 is Ampere (sm_86), which has no FP8 — so int4 AWQ is the quantisation that fits, not a
preference. Weights load in 6.7 GB; the server holds 14.3 GB at `gpu-memory-utilization 0.55`,
leaving room for the retriever on the same card.

### Grounding — 40 queries, top-3 pages each

| | |
|---|---|
| a gold page was actually among the 3 shown | 62% |
| answers carrying a citation | 83% |
| cited pages that are gold | 60% |
| answers citing a gold page | 53% |
| refused (`NOT_IN_PAGES`) | 4 / 40 |
| **refused when no gold page was shown** | **13%** |
| refused despite a gold page being shown | 8% |

The last two rows are the interesting ones. When retrieval hands the model three wrong pages, it
writes a confident answer anyway **87% of the time** — fluent, specific, sourced from whatever
was in front of it. That is the failure this architecture is supposed to prevent and doesn't yet:
citation makes the failure *auditable*, not impossible. Part 2's refusal path (refuse below a
retrieval-confidence threshold) is aimed exactly here, and now it has a baseline to beat.

### Latency, concurrency 1

| stage | p50 |
|---|---|
| query encode (ColQwen2, batch of 1) | 53 ms |
| stage 1 — pgvector, 31 tokens × top-50 | 46 ms |
| stage 2 — MaxSim rerank of 100 pages | 8 ms |
| generation — 3 page images, ~50 output tokens | 2,009 ms |
| **end-to-end** | **~2.1 s** |

Generation dominates by 20×. Output throughput is 24-32 tok/s at concurrency 1; step 7 measures
it under real load.

### Three things that had to be measured, not assumed

**Pages are 3.3–4.1 MP, which Qwen2.5-VL turns into ~5,400 tokens each** — three of them will not
fit an 8k context. Rather than guess a downscale, I measured accuracy against resolution on a
dense 13-row stock-number table:

| pixel cap | image size | prompt tokens | exact stock numbers recovered |
|---|---|---|---|
| native | 1800×2300 | 5,408 | 9/10 |
| 2.0 MP | 1251×1598 | 2,725 | 10/10 |
| **1.2 MP** | **969×1238** | **1,700** | **10/10** |
| 0.4 MP | 559×714 | 680 | 10/10 |

More pixels was not more accuracy — native actually dropped one number. The client caps at
1.2 MP, cutting prompt cost 3× for free.

**The retriever and the generator do fit on one 24 GB card**: 19.6 GB with ColQwen2 and vLLM both
resident, ~5 GB spare. That only works because vLLM is capped at 0.55; its default would take
~90% of the card and leave the retriever nothing.

**A memory-mapped 1 GB vector store is a cold-start trap.** The first measured run showed stage-2
rerank at 435 ms p50; steady state is 6 ms. Nothing was wrong with the GPU — the pages were being
faulted in from disk. The retriever now warms the store at startup (73 ms) and reports the
distinction, because a server that skips this publishes its own warm-up as its latency.

### One caching caveat for step 7

An early live run reported 535 ms generation p50 and 128 tok/s. That was vLLM's multimodal prefix
cache hitting at 56% on images it had just seen. Re-run against unseen queries, the same code
gives 2,009 ms and 24.5 tok/s. Step 7's load test has to control for this or it will publish a
number that only holds for repeated questions.

## Step 6 — serving on k3s with real GPU scheduling

Both halves run as Kubernetes workloads: pgvector as a StatefulSet with a volume claim, and the
quantized VLM as a Deployment requesting `nvidia.com/gpu: 1`. Manifests are kustomize base +
overlays, and the same workload definition was deployed and verified on **two different
clusters** — k3s (the target) and minikube — which is what turned up most of the findings below.

```
k8s/base/               namespace, pgvector StatefulSet + Services, vLLM Deployment + Services
k8s/device-plugin/      NVIDIA device plugin DaemonSet + time-slicing config
k8s/overlays/k3s/       RuntimeClass nvidia, local-path storage, host HF cache
k8s/overlays/minikube/  node-default runtime, standard storage, /hf-cache mount
```

### Verified on k3s, not just applied

`make k8s-verify OVERLAY=k3s` checks the things that are actually easy to get wrong
(`reports/k8s.json`):

| check | result |
|---|---|
| node advertises `nvidia.com/gpu` | 4 allocatable from 1 physical card (time-slicing on) |
| RuntimeClass `nvidia` | present — k3s detects the NVIDIA runtime at install |
| vLLM pod holds a GPU allocation | `nvidia.com/gpu: 1`, **0 restarts** |
| image pull into containerd | 8.6 GB compressed, 3m51s; pod ready 340 s including pull |
| model server answers through the NodePort Service | 1,602 ms multimodal request |
| retrieval against the in-cluster pgvector | NDCG@10 **0.498** (0.500 in Compose — ANN variance) |
| full RAG through the cluster, 40 queries | 2,449 ms p50 · 53% of answers cite a gold page |

The retrieval index was rebuilt inside the cluster and reproduces the calibrated score, so this
is the system step 4 blessed, not a demo that merely boots.

### What actually differed between k3s and minikube

Worth knowing, because "it works on my cluster" is where portability claims go to die:

| | k3s | minikube (docker driver) |
|---|---|---|
| GPU reaches the container via | `RuntimeClass: nvidia` (auto-created) | node's default runtime |
| device plugin | applied from this repo, time-slicing from the start | `nvidia-device-plugin` addon, patched for time-slicing |
| storage class | `local-path` | `standard` |
| NodePort reachable at | node IP / localhost | the node container's IP |
| model weights | host HF cache via hostPath | host cache bind-mounted into the node VM |
| image store | containerd, 8.6 GB compressed | docker, 19.8 GB |

Only the overlay changed; the workload definitions did not.

### Three failures worth more than the YAML

**Kubernetes crash-looped vLLM by injecting its own config.** On minikube the pod died at engine
init, twice, with no useful error. The cause: Kubernetes writes an env var per Service into every
pod, the Service here is named `vllm`, so the container received
`VLLM_PORT=tcp://10.111.112.198:8000` — and vLLM reads `VLLM_PORT` as its own integer setting.
Confirmed by reading the pod's environment, not by guessing. The fix is one line,
`enableServiceLinks: false`. k3s would have hit this identically — it is core Kubernetes
behaviour, not a minikube quirk — and because the fix was already in the manifest, the k3s
deployment came up first try with 0 restarts. Any app whose config prefix matches a Service name
has this bug waiting.

**GPUs are indivisible to the scheduler.** Scaling to two replicas left the second pod Pending:

```
0/1 nodes are available: 1 Insufficient nvidia.com/gpu.
```

Not a memory problem — the device plugin hands out whole cards, so a one-GPU node runs exactly
one GPU pod no matter how little VRAM each needs. Time-slicing (`replicas: 4` in the plugin
config) made the node advertise 4 logical GPUs, and a second GPU pod then scheduled and saw the
3090. The caveat belongs with the fix: time-slicing shares *scheduling*, not memory — the pods
interleave on the same SMs and the same 24 GB, and nothing stops one OOMing the other. Real
isolation needs MIG, which consumer Ampere does not support. That is why vLLM is *also* capped
at `gpu-memory-utilization 0.55`.

**Start order matters on a single card.** On minikube a pod restart happened while an indexing
job had ColQwen2 resident: vLLM profiles free VRAM at startup, and with ~6 GB already taken it
could not satisfy its 0.55 target and the engine died. Running the same indexing job *after* the
k3s pod was ready caused no restart — the generator has to claim its memory first, and then the
two coexist at 19.6 GB of 24 GB.

Smaller things, recorded because they cost time: k3s's kubeconfig is root-only
(`/etc/rancher/k3s/k3s.yaml`, mode 600), NodePorts are iptables rules rather than listening
sockets so `ss` shows nothing and a not-yet-Ready pod gives "connection refused", minikube on
WSL2 ignores `--memory`/`--cpus`, and the model weights are bind-mounted from the host HF cache
rather than re-downloaded — the manifest's "model repository" volume is the one line a
multi-node cluster would repoint at a PVC or object store.

## Step 7 — the serving numbers

Load test against the k3s deployment, 32 requests per level, **a distinct question and distinct
page images per request** (prefix-cache hit rate stayed at 3.7-5.7%, which is how you can tell
the control worked — an early careless run hit 56% and reported 5x the real throughput), fixed
128-token outputs so tokens/second is comparable across levels.

| concurrency | p50 | p95 | p99 | TTFT p50 | req/s | out tok/s | GPU % | power |
|---|---|---|---|---|---|---|---|---|
| 1 | 2,909 ms | 3,024 ms | 3,042 ms | 1,866 ms | 0.35 | 45 | 97% | 274 W |
| 4 | 8,466 ms | 8,899 ms | 11,877 ms | 4,396 ms | **0.48** | 61 | 100% | 276 W |
| 16 | 32,915 ms | 53,938 ms | 61,907 ms | 6,318 ms | **0.48** | 61 | 100% | 276 W |

**It saturates at concurrency 4.** Throughput is identical at 4 and 16 (0.48 req/s, 61 tok/s)
while p50 latency grows 4x and p95 to 54 seconds — past saturation, extra concurrency buys
nothing but queue time. The GPU is already at 97% with a *single* request in flight, because
each one carries ~5,100 prompt tokens of page imagery: this workload is prefill-bound, not
decode-bound, which is why batching helps so little (0.35 → 0.48 req/s, +37%) compared to a
text-only server. The usable operating point is **concurrency 4**; 16 is where you would page
someone.

### Cost per 1,000 queries

| | per 1k queries | vs self-hosted |
|---|---|---|
| electricity only (hardware owned) | **$0.04** | — |
| rented GPU equivalent ($1.00/hr) | **$0.58** | — |
| Claude Haiku 4.5 (same tokens) | $5.39 | **9.3x** more |
| Claude Sonnet 5 (same tokens) | $10.78 | 18.6x more |

At the saturated operating point each 1,000 queries costs 2,101 GPU-seconds — 35 GPU-minutes.
The workload is input-heavy (≈5,100 prompt tokens against 128 output), so hosted cost is
dominated by image tokens, which is exactly where a self-hosted small VLM wins.

**What these numbers do not say.** The hosted price buys zero ops, elastic capacity and a much
stronger model; this comparison prices *tokens*, not capability, and the two models are not
equivalent. The $0.04 electricity figure ignores the card's capital cost, and the $0.58 rental
figure assumes you keep the GPU busy — at 10% utilisation it is ~$5.80/1k and the arbitrage
disappears. Token counts are vLLM's (Qwen2.5-VL's image encoder, ~1,700 tokens per 1.2 MP page);
Anthropic's documented estimate for the same page is width×height/750 ≈ 1,600, within ~6%, so
the hosted figures are estimates but not loose ones.

### Where the HPA signal comes from

vLLM exposes `vllm:num_requests_waiting` and `vllm:request_queue_time_seconds`. Those — not CPU
utilisation — are the autoscaling signal for this workload: at concurrency 16 the GPU sits at
100% and CPU tells you nothing, while queue depth is what actually tracks user-visible latency.

## Development

```bash
make lint    # ruff check + format check
make test    # pytest (unit tests + invariants on the built eval set)
```
