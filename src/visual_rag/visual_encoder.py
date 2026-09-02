"""ColQwen2 page-image and query encoder.

No OCR, no chunking: the retrieval unit is the whole page, embedded as pixels. This is the
half of the comparison that is supposed to survive tables and diagrams.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np

DEFAULT_MODEL = "vidore/colqwen2-v1.0"


@dataclass
class VisualEncoderConfig:
    model_name: str = DEFAULT_MODEL
    device: str = "cuda:0"
    dtype: str = "bfloat16"
    # 8 measured fastest on a 24 GB 3090 (5.4 pages/s, 7.8 GB); 16 is slower and 11 GB.
    batch_size: int = 8
    query_batch_size: int = 16


def load_encoder(cfg: VisualEncoderConfig):
    import torch
    from colpali_engine.models import ColQwen2, ColQwen2Processor

    model = ColQwen2.from_pretrained(
        cfg.model_name, torch_dtype=getattr(torch, cfg.dtype), device_map=cfg.device
    ).eval()
    processor = ColQwen2Processor.from_pretrained(cfg.model_name)
    return model, processor


def _batched(items: Sequence, size: int) -> Iterator[Sequence]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def embed_images(model, processor, images, cfg: VisualEncoderConfig) -> list[np.ndarray]:
    """Embed one batch of PIL images into a list of [n_patches, dim] float16 arrays."""
    import torch

    batch = processor.process_images(list(images)).to(cfg.device)
    with torch.no_grad():
        embeddings = model(**batch)
    mask = batch["attention_mask"].bool()
    # Trim padding per image: batches are ragged and the pad vectors are not real patches.
    return [embeddings[i][mask[i]].to(torch.float16).cpu().numpy() for i in range(len(embeddings))]


def embed_queries(
    model, processor, queries: Sequence[str], cfg: VisualEncoderConfig
) -> tuple[list[np.ndarray], float]:
    """Embed queries into per-token vectors. Returns (embeddings, seconds)."""
    import torch

    started = time.perf_counter()
    out: list[np.ndarray] = []
    for chunk in _batched(list(queries), cfg.query_batch_size):
        batch = processor.process_queries(list(chunk)).to(cfg.device)
        with torch.no_grad():
            embeddings = model(**batch)
        mask = batch["attention_mask"].bool()
        out.extend(
            embeddings[i][mask[i]].to(torch.float16).cpu().numpy() for i in range(len(embeddings))
        )
    return out, time.perf_counter() - started
