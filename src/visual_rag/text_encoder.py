"""Text encoder for the baseline retriever (BAAI/bge-m3 dense vectors).

The input is the corpus `markdown` column — someone else's OCR — so the text-vs-visual
comparison isn't confounded by my own PDF parsing.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

DEFAULT_MODEL = "BAAI/bge-m3"


@dataclass
class EncoderConfig:
    model_name: str = DEFAULT_MODEL
    device: str = "cuda"
    dtype: str = "float16"
    # Longest page in this corpus tokenises to 2,646 tokens, so 4096 truncates nothing while
    # keeping activations far below what BGE-M3's 8192 ceiling would cost.
    max_seq_length: int = 4096
    batch_size: int = 16
    # BGE-M3 needs no instruction prefix on either side; keeping the hooks explicit so a
    # model that does need one (e5, gte) can be swapped in without editing call sites.
    query_prefix: str = ""
    passage_prefix: str = ""


def load_encoder(cfg: EncoderConfig):
    import torch
    from sentence_transformers import SentenceTransformer

    dtype = getattr(torch, cfg.dtype)
    try:
        # transformers >= 5 renamed the argument; keep both paths so the pin can move.
        model = SentenceTransformer(
            cfg.model_name, device=cfg.device, model_kwargs={"dtype": dtype}
        )
    except (TypeError, ValueError):
        model = SentenceTransformer(
            cfg.model_name, device=cfg.device, model_kwargs={"torch_dtype": dtype}
        )
    model.max_seq_length = cfg.max_seq_length
    model.eval()
    return model


def encode(
    model,
    texts: Sequence[str],
    cfg: EncoderConfig,
    prefix: str = "",
    show_progress: bool = True,
) -> tuple[np.ndarray, float]:
    """Encode to L2-normalised float32 vectors. Returns (embeddings, seconds)."""
    payload = [prefix + (t or "") for t in texts] if prefix else [t or "" for t in texts]
    started = time.perf_counter()
    vectors = model.encode(
        payload,
        batch_size=cfg.batch_size,
        normalize_embeddings=True,  # cosine == dot product downstream
        convert_to_numpy=True,
        show_progress_bar=show_progress,
    )
    elapsed = time.perf_counter() - started
    return np.ascontiguousarray(vectors, dtype=np.float32), elapsed


def token_stats(model, texts: Sequence[str], max_seq_length: int) -> dict:
    """How much of each page actually fits — a silently truncated page is a silent recall bug."""
    tokenizer = model.tokenizer
    lengths = np.array(
        [len(ids) for ids in tokenizer([t or "" for t in texts], truncation=False)["input_ids"]]
    )
    return {
        "max_seq_length": max_seq_length,
        "tokens_mean": round(float(lengths.mean()), 1),
        "tokens_p95": int(np.percentile(lengths, 95)),
        "tokens_max": int(lengths.max()),
        "pages_truncated": int((lengths > max_seq_length).sum()),
        "pages_empty": int((lengths <= 2).sum()),  # CLS + SEP only
    }
