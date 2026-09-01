"""Load ViDoRe V3 industrial and build the evaluation slice.

The retrieval steps that follow (text baseline, ColQwen2) both consume exactly what
`build_eval_set()` writes, so the two retrievers are always scored on identical ground.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from datasets import Dataset, load_dataset

from . import config

# --- raw subsets -------------------------------------------------------------------------


def load_subset(name: str, split: str = config.SPLIT) -> Dataset:
    """Load one HF config of the benchmark (downloads to the HF cache on first call)."""
    if name not in config.SUBSETS:
        raise ValueError(f"unknown subset {name!r}, expected one of {config.SUBSETS}")
    return load_dataset(config.DATASET_ID, name, split=split)


def load_frame(name: str, split: str = config.SPLIT) -> pd.DataFrame:
    """Load a subset as a DataFrame, without decoding page images.

    The corpus carries 2 GB of PNGs; dropping the column keeps every metadata operation
    (joins, stats, the eval set) cheap. Use `load_corpus_images()` when pixels are needed.
    """
    ds = load_subset(name, split=split)
    if "image" in ds.column_names:
        ds = ds.remove_columns("image")
    return ds.to_pandas()


def load_corpus_images(split: str = config.SPLIT) -> tuple[Dataset, dict[int, int]]:
    """Return the corpus with images plus a `corpus_id -> row index` map.

    `corpus_id` is not guaranteed to equal the row position, so never index by id directly.
    """
    ds = load_subset("corpus", split=split)
    ids = ds.remove_columns([c for c in ds.column_names if c != "corpus_id"])["corpus_id"]
    return ds, {int(cid): i for i, cid in enumerate(ids)}


def row_counts(split: str = config.SPLIT) -> dict[str, int]:
    return {name: load_subset(name, split=split).num_rows for name in config.SUBSETS}


def check_row_counts(counts: dict[str, int]) -> list[str]:
    """Compare observed row counts against the dataset card. Empty list == match."""
    return [
        f"{name}: expected {expected}, got {counts.get(name)}"
        for name, expected in config.EXPECTED_ROWS.items()
        if counts.get(name) != expected
    ]


# --- eval slice --------------------------------------------------------------------------


@dataclass
class EvalSet:
    """The strict English/human slice, joined and validated."""

    queries: pd.DataFrame  # one row per eval query
    qrels: pd.DataFrame  # one row per (query, relevant page), graded
    corpus: pd.DataFrame  # page metadata for the whole corpus (no images)
    documents: pd.DataFrame
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def query_ids(self) -> list[int]:
        return self.queries["query_id"].tolist()

    def gold(self) -> dict[int, dict[int, int]]:
        """`{query_id: {corpus_id: graded_score}}` — the form the NDCG scorer wants."""
        out: dict[int, dict[int, int]] = {qid: {} for qid in self.query_ids}
        for qid, cid, score in self.qrels[["query_id", "corpus_id", "score"]].itertuples(
            index=False, name=None
        ):
            out[int(qid)][int(cid)] = int(score)
        return out


def build_eval_set(
    language: str = config.EVAL_LANGUAGE,
    generator: str = config.EVAL_QUERY_GENERATOR,
    min_score: int = config.MIN_RELEVANT_SCORE,
) -> EvalSet:
    """Filter queries to language+generator, join to qrels and corpus, and validate the join.

    `generator="any"` keeps the synthetic queries too (283 English instead of 177); the default
    is the strict human-written slice, which is what the calibration in step 4 is scored on.
    """
    queries = load_frame("queries")
    qrels = load_frame("qrels")
    corpus = load_frame("corpus")
    documents = load_frame("documents_metadata")

    mask = queries["language"] == language
    if generator != "any":
        mask &= queries["query_generator"] == generator
    eval_queries = queries[mask].copy()
    eval_queries = eval_queries.sort_values("query_id").reset_index(drop=True)

    qids = set(eval_queries["query_id"])
    eval_qrels = qrels[qrels["query_id"].isin(qids)].copy()

    # Judged-but-not-relevant rows are real annotations; they are not positives.
    graded = eval_qrels[eval_qrels["score"] >= min_score].copy()
    graded = graded.sort_values(["query_id", "score"], ascending=[True, False]).reset_index(
        drop=True
    )

    # --- join validation: fail loudly rather than score a silently broken eval set
    corpus_ids = set(corpus["corpus_id"])
    orphan_pages = sorted(set(graded["corpus_id"]) - corpus_ids)
    unjudged = sorted(qids - set(graded["query_id"]))
    if orphan_pages:
        raise ValueError(f"{len(orphan_pages)} qrel pages missing from corpus: {orphan_pages[:5]}")
    if unjudged:
        raise ValueError(f"{len(unjudged)} eval queries have no relevant page: {unjudged[:5]}")

    # Drop the answer-bearing pages onto their source document, so a query can be reported as
    # single- or multi-document (multi-doc is where a bare model reliably fails).
    page_to_doc = corpus.set_index("corpus_id")["doc_id"]
    graded["doc_id"] = graded["corpus_id"].map(page_to_doc)
    graded["page_number_in_doc"] = graded["corpus_id"].map(
        corpus.set_index("corpus_id")["page_number_in_doc"]
    )

    # A gold span is "visual" when the annotator tagged it as anything other than running text
    # (Table / Infographic / Image). Step 4 reports the text-vs-visual delta on the subset where
    # *every* gold span is visual — that is where OCR is expected to break.
    graded["gold_is_visual"] = graded["content_type"].apply(lambda t: bool(set(t) - {"Text"}))

    per_query = graded.groupby("query_id")
    eval_queries["n_relevant"] = eval_queries["query_id"].map(per_query.size()).astype(int)
    eval_queries["n_docs"] = eval_queries["query_id"].map(per_query["doc_id"].nunique()).astype(int)
    eval_queries["max_score"] = eval_queries["query_id"].map(per_query["score"].max()).astype(int)
    eval_queries["n_visual_gold"] = (
        eval_queries["query_id"].map(per_query["gold_is_visual"].sum()).astype(int)
    )
    eval_queries["visual_only"] = (
        eval_queries["query_id"].map(per_query["gold_is_visual"].all()).astype(bool)
    )

    stats = _eval_stats(queries, qrels, corpus, documents, eval_queries, eval_qrels, graded)
    return EvalSet(
        queries=eval_queries, qrels=graded, corpus=corpus, documents=documents, stats=stats
    )


def _explode_counts(series: pd.Series) -> dict[str, int]:
    """Value counts for a column of lists (`content_type`, `query_types`, ...)."""
    exploded = series.explode().dropna()
    return {str(k): int(v) for k, v in exploded.value_counts().items()}


def _visual_dependency(
    corpus: pd.DataFrame, graded: pd.DataFrame, eval_queries: pd.DataFrame
) -> dict[str, Any]:
    """How much of the gold evidence the text baseline structurally cannot see.

    If a gold page carried no OCR at all the comparison would be rigged in the visual
    retriever's favour, so this is checked and reported rather than assumed.
    """
    md_len = corpus.set_index("corpus_id")["markdown"].fillna("").str.len()
    gold_md_len = graded["corpus_id"].map(md_len)
    return {
        "gold_pages_with_empty_markdown": int((gold_md_len == 0).sum()),
        "gold_pages_with_markdown_under_200_chars": int((gold_md_len < 200).sum()),
        "gold_spans_visual": int(graded["gold_is_visual"].sum()),
        "gold_spans_total": int(len(graded)),
        "queries_with_any_visual_gold": int((eval_queries["n_visual_gold"] > 0).sum()),
        "queries_visual_only": int(eval_queries["visual_only"].sum()),
    }


def _eval_stats(
    queries: pd.DataFrame,
    qrels: pd.DataFrame,
    corpus: pd.DataFrame,
    documents: pd.DataFrame,
    eval_queries: pd.DataFrame,
    eval_qrels_all: pd.DataFrame,
    graded: pd.DataFrame,
) -> dict[str, Any]:
    md_len = corpus["markdown"].fillna("").str.len()
    return {
        "raw": {
            "corpus_pages": int(len(corpus)),
            "documents": int(documents["doc_id"].nunique()),
            "queries": int(len(queries)),
            "qrels": int(len(qrels)),
            "languages": {str(k): int(v) for k, v in queries["language"].value_counts().items()},
            "query_generators": {
                str(k): int(v) for k, v in queries["query_generator"].value_counts().items()
            },
            "qrel_score_distribution": {
                str(k): int(v) for k, v in qrels["score"].value_counts().sort_index().items()
            },
        },
        "eval": {
            "queries": int(len(eval_queries)),
            "judgements_all": int(len(eval_qrels_all)),
            "judgements_relevant": int(len(graded)),
            "score_distribution": {
                str(k): int(v) for k, v in graded["score"].value_counts().sort_index().items()
            },
            "relevant_pages_per_query": {
                "mean": round(float(eval_queries["n_relevant"].mean()), 2),
                "median": float(eval_queries["n_relevant"].median()),
                "min": int(eval_queries["n_relevant"].min()),
                "max": int(eval_queries["n_relevant"].max()),
            },
            "docs_per_query": {
                "mean": round(float(eval_queries["n_docs"].mean()), 2),
                "multi_doc_queries": int((eval_queries["n_docs"] > 1).sum()),
            },
            "queries_with_full_answer_page": int((eval_queries["max_score"] >= 2).sum()),
            "gold_content_types": _explode_counts(graded["content_type"]),
            "query_types": _explode_counts(eval_queries["query_types"]),
            "query_formats": {
                str(k): int(v) for k, v in eval_queries["query_format"].value_counts().items()
            },
            "gold_pages_unique": int(graded["corpus_id"].nunique()),
            "gold_docs_unique": int(graded["doc_id"].nunique()),
        },
        "visual_dependency": _visual_dependency(corpus, graded, eval_queries),
        "text_baseline_inputs": {
            "pages_with_empty_markdown": int((md_len == 0).sum()),
            "markdown_chars": {
                "mean": round(float(md_len.mean()), 1),
                "median": float(md_len.median()),
                "p95": float(md_len.quantile(0.95)),
                "max": int(md_len.max()),
            },
        },
    }


# --- persistence -------------------------------------------------------------------------

_FILES = {
    "queries": "eval_queries.parquet",
    "qrels": "eval_qrels.parquet",
    "corpus": "corpus_meta.parquet",
    "documents": "documents_metadata.parquet",
}


def save_eval_set(eval_set: EvalSet) -> dict[str, str]:
    config.ensure_dirs()
    written = {}
    for attr, filename in _FILES.items():
        path = config.EVAL_DIR / filename
        getattr(eval_set, attr).to_parquet(path, index=False)
        written[attr] = str(path)
    return written


def load_eval_set() -> EvalSet:
    """Read back what `save_eval_set` wrote (no HF download, no image decode)."""
    frames = {}
    for attr, filename in _FILES.items():
        path = config.EVAL_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"{path} missing — run `make data` first")
        frames[attr] = pd.read_parquet(path)
    return EvalSet(**frames)
