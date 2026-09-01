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

# The clean, strict eval slice: English questions actually written by a human annotator.
EVAL_LANGUAGE = "english"
EVAL_QUERY_GENERATOR = "human"
# The other ~1.4k queries are machine-generated ("sdg") or translations of the English set.

# Graded relevance: 2 = page fully answers the query, 1 = partial. 0 (if present) = judged
# non-relevant, which is a real annotation but not a positive.
MIN_RELEVANT_SCORE = 1

# Retrieval metric cutoff. NDCG (not plain recall) because relevance is graded and multi-page.
NDCG_K = 10


def ensure_dirs() -> None:
    for d in (DATA_DIR, EVAL_DIR, REPORTS_DIR, SANITY_DIR):
        d.mkdir(parents=True, exist_ok=True)
