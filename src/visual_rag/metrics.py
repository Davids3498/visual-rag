"""Retrieval metrics.

Relevance here is graded (2 = the page fully answers, 1 = partial) and a query has several
relevant pages, so NDCG@10 is the headline number and plain recall is only context.

Two implementations are kept deliberately: a readable one here, and `pytrec_eval` (the
trec_eval C code the ViDoRe leaderboard scores with). `tests/test_metrics.py` asserts they
agree on the real run — a metric bug would otherwise look exactly like a retrieval result.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

# query_id -> {corpus_id: score}. Run scores are similarities; gold scores are grades.
Run = Mapping[int, Mapping[int, float]]
Gold = Mapping[int, Mapping[int, int]]

# trec_eval's ndcg_cut uses linear gains (gain = relevance grade), not 2^rel - 1. Everything
# below defaults to that so the numbers are comparable with the published leaderboard.
DEFAULT_GAIN = "linear"


def _gain(relevance: float, kind: str) -> float:
    if kind == "linear":
        return float(relevance)
    if kind == "exponential":
        return float(2**relevance - 1)
    raise ValueError(f"unknown gain {kind!r}")


def rank(scores: Mapping[int, float]) -> list[int]:
    """Documents best-first. Ties break on doc id so a run is reproducible."""
    return [doc for doc, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def dcg(gains: Iterable[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(
    ranked: Sequence[int], gold: Mapping[int, int], k: int, gain: str = DEFAULT_GAIN
) -> float:
    if not gold:
        return 0.0
    actual = dcg(_gain(gold.get(doc, 0), gain) for doc in ranked[:k])
    ideal = dcg(_gain(rel, gain) for rel in sorted(gold.values(), reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def recall_at_k(ranked: Sequence[int], gold: Mapping[int, int], k: int) -> float:
    if not gold:
        return 0.0
    return len(set(ranked[:k]) & set(gold)) / len(gold)


def precision_at_k(ranked: Sequence[int], gold: Mapping[int, int], k: int) -> float:
    if k == 0:
        return 0.0
    return len(set(ranked[:k]) & set(gold)) / k


def success_at_k(ranked: Sequence[int], gold: Mapping[int, int], k: int) -> float:
    """1.0 if any relevant page made the top k — 'did the user get something useful at all'."""
    return float(bool(set(ranked[:k]) & set(gold)))


def mrr_at_k(ranked: Sequence[int], gold: Mapping[int, int], k: int) -> float:
    for i, doc in enumerate(ranked[:k]):
        if doc in gold:
            return 1.0 / (i + 1)
    return 0.0


def average_precision(
    ranked: Sequence[int], gold: Mapping[int, int], k: int | None = None
) -> float:
    """MAP's per-query term, on binarised relevance (trec_eval's `map`)."""
    if not gold:
        return 0.0
    hits = 0
    total = 0.0
    for i, doc in enumerate(ranked if k is None else ranked[:k]):
        if doc in gold:
            hits += 1
            total += hits / (i + 1)
    return total / len(gold)


def per_query_ndcg(run: Run, gold: Gold, k: int, gain: str = DEFAULT_GAIN) -> dict[int, float]:
    """Per-query NDCG@k — needed for subset breakdowns and for paired comparisons."""
    return {qid: ndcg_at_k(rank(run.get(qid, {})), gold.get(qid, {}), k, gain) for qid in gold}


def evaluate(
    run: Run, gold: Gold, ks: Sequence[int] = (1, 5, 10), gain: str = DEFAULT_GAIN
) -> dict[str, float]:
    """Macro-averaged metrics over every query in `gold` (a missing query scores 0, not skipped)."""
    ranked = {qid: rank(run.get(qid, {})) for qid in gold}
    n = len(gold) or 1
    out: dict[str, float] = {}
    for k in ks:
        out[f"ndcg@{k}"] = sum(ndcg_at_k(ranked[q], gold[q], k, gain) for q in gold) / n
        out[f"recall@{k}"] = sum(recall_at_k(ranked[q], gold[q], k) for q in gold) / n
        out[f"precision@{k}"] = sum(precision_at_k(ranked[q], gold[q], k) for q in gold) / n
        out[f"success@{k}"] = sum(success_at_k(ranked[q], gold[q], k) for q in gold) / n
    out[f"mrr@{max(ks)}"] = sum(mrr_at_k(ranked[q], gold[q], max(ks)) for q in gold) / n
    out["map"] = sum(average_precision(ranked[q], gold[q]) for q in gold) / n
    return {name: round(value, 4) for name, value in out.items()}


def evaluate_pytrec(run: Run, gold: Gold, ks: Sequence[int] = (1, 5, 10)) -> dict[str, float]:
    """The same numbers via trec_eval itself. Raises ImportError if pytrec_eval is absent."""
    import pytrec_eval

    qrel = {str(q): {str(d): int(r) for d, r in rels.items()} for q, rels in gold.items()}
    trec_run = {str(q): {str(d): float(s) for d, s in run.get(q, {}).items()} for q in gold}
    measures = {f"ndcg_cut.{k}" for k in ks} | {f"recall.{k}" for k in ks} | {"map"}
    results = pytrec_eval.RelevanceEvaluator(qrel, measures).evaluate(trec_run)
    n = len(qrel) or 1
    names = sorted({m for per_query in results.values() for m in per_query})
    return {
        name: round(sum(per_query.get(name, 0.0) for per_query in results.values()) / n, 4)
        for name in names
    }


def subset(gold: Gold, query_ids: Iterable[int]) -> Gold:
    keep = set(query_ids)
    return {qid: rels for qid, rels in gold.items() if qid in keep}
