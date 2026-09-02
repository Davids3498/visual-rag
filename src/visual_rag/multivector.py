"""Multi-vector page storage and late-interaction (MaxSim) scoring.

ColQwen2 embeds a page as ~750 vectors, one per image patch, instead of one vector per page.
That is what makes it good at tables and diagrams — and what makes naive search impossible:
5,244 pages become ~3.9M vectors, and a single ANN index over them returns patches, not pages.

Hence the two-stage design this module supports:
  1. one cheap mean-pooled vector per page -> ordinary ANN -> a shortlist
  2. full MaxSim late interaction over only the shortlist

MaxSim score(query, page) = sum over query tokens of the best-matching patch on that page.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class MultiVectorStore:
    """Ragged multi-vector storage: one variable-length block of patch vectors per page.

    Kept ragged (concatenated + offsets) rather than padded because page patch counts vary
    with image aspect ratio, and padding 5k pages to the maximum wastes both disk and VRAM.
    """

    vectors: np.ndarray  # [total_patches, dim], float16
    offsets: np.ndarray  # [n_pages + 1], int64 — page i is vectors[offsets[i]:offsets[i+1]]
    ids: np.ndarray  # [n_pages], int64 — corpus_id per page

    def __len__(self) -> int:
        return len(self.ids)

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1])

    @property
    def lengths(self) -> np.ndarray:
        return np.diff(self.offsets)

    def get(self, index: int) -> np.ndarray:
        return self.vectors[self.offsets[index] : self.offsets[index + 1]]

    def pooled(self) -> np.ndarray:
        """Mean patch vector per page, L2-normalised — the stage-1 ANN representation.

        Mean pooling throws away exactly the locality that makes late interaction work, which
        is why stage 1 is a *shortlist* and never the final ranking. Stage-1 recall is measured
        rather than assumed.
        """
        pooled = np.zeros((len(self), self.dim), dtype=np.float32)
        for i in range(len(self)):
            pooled[i] = self.get(i).astype(np.float32).mean(axis=0)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled / np.maximum(norms, 1e-12)

    def nbytes(self) -> int:
        return int(self.vectors.nbytes + self.offsets.nbytes + self.ids.nbytes)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        np.save(directory / "offsets.npy", self.offsets)
        np.save(directory / "ids.npy", self.ids)

    @classmethod
    def load(cls, directory: Path, mmap: bool = True) -> MultiVectorStore:
        mode = "r" if mmap else None
        return cls(
            vectors=np.load(directory / "vectors.npy", mmap_mode=mode),
            offsets=np.load(directory / "offsets.npy"),
            ids=np.load(directory / "ids.npy"),
        )

    @classmethod
    def from_pages(cls, pages: list[np.ndarray], ids: np.ndarray) -> MultiVectorStore:
        lengths = np.array([len(page) for page in pages], dtype=np.int64)
        offsets = np.concatenate([[0], np.cumsum(lengths)])
        return cls(
            vectors=np.concatenate(pages).astype(np.float16),
            offsets=offsets,
            ids=np.asarray(ids, dtype=np.int64),
        )


# --- scoring ------------------------------------------------------------------------------


def _pad_pages(store: MultiVectorStore, indices, device, dtype):
    """Pad a set of pages into [n, max_patches, dim] plus a validity mask, on device."""
    import torch

    lengths = [int(store.offsets[i + 1] - store.offsets[i]) for i in indices]
    width = max(lengths)
    padded = np.zeros((len(indices), width, store.dim), dtype=np.float16)
    for row, (index, length) in enumerate(zip(indices, lengths, strict=True)):
        padded[row, :length] = store.get(index)
    mask = np.arange(width)[None, :] < np.array(lengths)[:, None]
    return (
        torch.from_numpy(padded).to(device=device, dtype=dtype),
        torch.from_numpy(mask).to(device=device),
    )


def maxsim(query, pages, mask):
    """MaxSim for one query against padded pages.

    `query` is [n_query_tokens, dim]; `pages` is [n_pages, max_patches, dim]. Padding is masked
    to -inf rather than left at zero: patch dot products can be negative, so a zero pad would
    silently win the max and inflate the score of short pages.
    """
    import torch

    similarity = torch.einsum("qd,npd->nqp", query, pages)
    similarity = similarity.masked_fill(~mask[:, None, :], float("-inf"))
    return similarity.max(dim=2).values.sum(dim=1)


def score_pages(
    store: MultiVectorStore,
    query_vectors: np.ndarray,
    indices,
    device: str = "cuda:0",
    dtype: str = "float16",
    chunk_size: int = 512,
) -> np.ndarray:
    """MaxSim between one query and `indices` pages of the store. Returns scores in that order."""
    import torch

    torch_dtype = getattr(torch, dtype)
    query = torch.from_numpy(np.asarray(query_vectors)).to(device=device, dtype=torch_dtype)
    indices = list(indices)
    scores = np.empty(len(indices), dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(indices), chunk_size):
            block = indices[start : start + chunk_size]
            pages, mask = _pad_pages(store, block, device, torch_dtype)
            scores[start : start + len(block)] = maxsim(query, pages, mask).float().cpu().numpy()
    return scores


def page_centroids(
    store: MultiVectorStore,
    k: int = 16,
    iterations: int = 10,
    device: str = "cuda:0",
    chunk_size: int = 256,
    seed: int = 0,
) -> np.ndarray:
    """Cluster each page's patch vectors into `k` L2-normalised centroids.

    This is the stage-1 representation. Mean pooling a page into one vector measurably
    destroys the shortlist (it recovers ~52% of the gold pages at N=50 on this corpus, against
    ~70% for 16 centroids), because averaging 750 patches blurs a table, a diagram and a
    paragraph into one direction that matches none of them.

    Spherical k-means (cosine, on the unit sphere) with a deterministic evenly-spaced init:
    ColQwen2's patch vectors are already unit-norm, so cosine is a dot product.
    """
    import torch

    torch.manual_seed(seed)
    lengths = store.lengths
    out = np.zeros((len(store), k, store.dim), dtype=np.float32)
    for start in range(0, len(store), chunk_size):
        block = list(range(start, min(start + chunk_size, len(store))))
        pages, mask = _pad_pages(store, block, device, torch.float32)
        n, width, dim = pages.shape
        # Seed from *valid* patches only: pages are padded at the end, so an init index past a
        # page's real length would seed a cluster with a zero vector that can never win a patch
        # and would be indexed as a dead row.
        page_lengths = mask.sum(dim=1)
        fractions = torch.linspace(0, 1, k, device=device)
        init = (fractions[None, :] * (page_lengths[:, None] - 1).clamp(min=0)).long()
        centroids = torch.gather(pages, 1, init[:, :, None].expand(-1, -1, dim)).clone()
        for _ in range(iterations):
            similarity = torch.einsum("npd,nkd->npk", pages, centroids)
            similarity = similarity.masked_fill(~mask[:, :, None], -1e4)
            assignment = similarity.argmax(dim=-1)
            onehot = torch.zeros(n, width, k, device=device)
            onehot.scatter_(2, assignment[:, :, None], 1.0)
            onehot *= mask[:, :, None].float()
            counts = onehot.sum(dim=1)
            updated = (
                torch.einsum("npk,npd->nkd", onehot, pages) / counts.clamp(min=1.0)[:, :, None]
            )
            # A cluster nobody joined keeps its previous direction instead of collapsing to
            # zero — a zero centroid is a row in the index that matches nothing.
            centroids = torch.where((counts == 0)[:, :, None], centroids, updated)
            centroids = centroids / centroids.norm(dim=-1, keepdim=True).clamp(min=1e-6)
        out[start : start + len(block)] = centroids.cpu().numpy()
    del lengths
    degenerate = int((np.linalg.norm(out, axis=2) < 0.5).sum())
    if degenerate:
        raise ValueError(f"{degenerate} centroids collapsed to (near) zero — clustering is broken")
    return out


class GpuCorpus:
    """The whole corpus padded onto the GPU once, for exhaustive MaxSim.

    At this corpus size the multi-vector set is ~1 GB, so the brute-force ceiling is affordable
    and worth having: it is the only way to know what the two-stage shortlist costs in quality.
    """

    def __init__(self, store: MultiVectorStore, device: str = "cuda:0", dtype: str = "float16"):
        import torch

        torch_dtype = getattr(torch, dtype)
        lengths = store.lengths
        width = int(lengths.max())
        padded = np.zeros((len(store), width, store.dim), dtype=np.float16)
        for i in range(len(store)):
            padded[i, : lengths[i]] = store.get(i)
        self.pages = torch.from_numpy(padded).to(device=device, dtype=torch_dtype)
        self.mask = torch.from_numpy(np.arange(width)[None, :] < lengths[:, None]).to(device=device)
        self.ids = store.ids
        self.device = device
        self.dtype = torch_dtype

    def nbytes(self) -> int:
        return self.pages.element_size() * self.pages.nelement()

    def score(self, query_vectors: np.ndarray, chunk_size: int = 1024) -> np.ndarray:
        import torch

        query = torch.from_numpy(np.asarray(query_vectors)).to(device=self.device, dtype=self.dtype)
        out = torch.empty(len(self.ids), device=self.device, dtype=torch.float32)
        with torch.no_grad():
            for start in range(0, len(self.ids), chunk_size):
                stop = start + chunk_size
                out[start:stop] = maxsim(
                    query, self.pages[start:stop], self.mask[start:stop]
                ).float()
        return out.cpu().numpy()
