"""Paths and dataset constants.

Everything that a later build step might want to point somewhere else (a different corpus in
Part 2, a different eval filter) is named here rather than inlined in scripts.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("VRAG_DATA_DIR", PROJECT_ROOT / "data"))
EVAL_DIR = DATA_DIR / "eval"
REPORTS_DIR = Path(os.environ.get("VRAG_REPORTS_DIR", PROJECT_ROOT / "reports"))
SANITY_DIR = REPORTS_DIR / "sanity"

# --- ViDoRe V3 industrial ----------------------------------------------------------------
DATASET_ID = "vidore/vidore_v3_industrial"
SPLIT = "test"
SUBSETS = ("corpus", "queries", "qrels", "documents_metadata")

# Row counts from the dataset card. `01_load_inspect.py` asserts against these: if HF ships a
# new revision the run fails loudly instead of silently scoring a different benchmark.
EXPECTED_ROWS = {
    "corpus": 5244,
    "queries": 1698,
    "qrels": 9684,
    "documents_metadata": 27,
}

# The eval slice: all 283 English queries. The other ~1.4k rows are translations of these same
# 283 into five languages, so this is the full English benchmark, not a sample of it.
EVAL_LANGUAGE = "english"
EVAL_QUERY_GENERATOR = "any"
# 177 of the 283 were written by a human annotator and 106 were generated ("sdg"). Both are
# kept and reported as separate slices rather than filtered out up front: the human subset is
# the stricter set, the full 283 is what the benchmark actually publishes.

# Graded relevance: 2 = page fully answers the query, 1 = partial. 0 (if present) = judged
# non-relevant, which is a real annotation but not a positive.
MIN_RELEVANT_SCORE = 1

# Retrieval metric cutoff. NDCG (not plain recall) because relevance is graded and multi-page.
NDCG_K = 10


# --- Part 2: the MCU-datasheet corpus ----------------------------------------------------
# The corpus *definition* is version-controlled (CORPUS_DIR); the PDFs are not. Vendor terms
# grant no redistribution right, so the manifest points at each vendor's own copy and the
# fetch script rebuilds data/mcu/pdfs/ locally.
CORPUS_DIR = PROJECT_ROOT / "corpus"
MCU_MANIFEST = CORPUS_DIR / "mcu_manifest.json"
MCU_DIR = DATA_DIR / "mcu"
MCU_PDF_DIR = MCU_DIR / "pdfs"

# Target page budget, from the Part 1 finding that the *page* is the retrieval unit: pages
# drive index size, embed time (~4.5 pages/s) and retrieval difficulty, not document count.
# Advisory only — the 24 GB card fits far more; below this the corpus is thin, above it every
# reindex costs iteration speed and the prose-heavy reference manuals start to dominate.
MCU_PAGE_TARGET = (1500, 2500)


def ensure_dirs() -> None:
    for d in (DATA_DIR, EVAL_DIR, REPORTS_DIR, SANITY_DIR, MCU_DIR, MCU_PDF_DIR):
        d.mkdir(parents=True, exist_ok=True)
