"""Render the manifest's selected pages into the images the retriever actually sees.

This is where the corpus stops being ten PDFs and becomes a list of pages, because the page
is ColQwen2's retrieval unit: one page, one row in the index, one score at ranking time.

Three things are decided here and recorded rather than left implicit:

* which pages. Whole documents for the datasheets and errata, and only the chosen ranges for
  the reference manuals, so 4,813 physical pages become the ~1,200 that serve the thesis.
* at what resolution. 1.2 MP, the figure step 5 measured: on a dense stock-number table it
  recovered 10/10 values where the native 3.3-4.1 MP page recovered 9/10 at three times the
  tokens. More pixels was worse, not better.
* which revision. Every row carries the source document's sha256, so a page image can always
  be traced to the exact PDF it came from — and a re-pinned document is visibly stale here.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from . import config
from .corpus import Document, Manifest

# --- which pages ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageRef:
    """One page of one document, before it has been rendered."""

    page_id: int
    doc_id: str
    vendor: str
    family: str
    doc_type: str
    page_number: int  # physical, 1-based — the same convention as the manifest's ranges
    doc_sha256: str


def doc_ordinals(manifest: Manifest) -> dict[str, int]:
    """`doc_id -> ordinal`, assigned by sorted doc_id so page ids do not depend on file order.

    Adding a document later can shift the ordinals of the ones after it, which changes their
    page ids. That is acceptable because changing the corpus means re-embedding it anyway —
    but it is the reason the page table is written out rather than recomputed on the fly.
    """
    return {doc_id: i + 1 for i, doc_id in enumerate(sorted(d.doc_id for d in manifest.documents))}


def page_refs(doc: Document, ordinal: int) -> list[PageRef]:
    """Expand one document's page selection into concrete page references."""
    if doc.page_count is None or doc.sha256 is None:
        raise ValueError(f"{doc.doc_id} is not pinned yet — run the fetch script first")
    if doc.pages.pending:
        raise ValueError(f"{doc.doc_id} has no slice ranges yet — read its errata and choose")
    return [
        PageRef(
            page_id=ordinal * config.PAGE_ID_STRIDE + number,
            doc_id=doc.doc_id,
            vendor=doc.vendor,
            family=doc.family,
            doc_type=doc.doc_type,
            page_number=number,
            doc_sha256=doc.sha256,
        )
        for number in doc.pages.page_numbers(doc.page_count)
    ]


def plan_pages(manifest: Manifest, documents: list[Document] | None = None) -> list[PageRef]:
    """Every page the corpus contains, in document order."""
    ordinals = doc_ordinals(manifest)
    refs: list[PageRef] = []
    for doc in documents if documents is not None else manifest.documents:
        refs.extend(page_refs(doc, ordinals[doc.doc_id]))
    return refs


# --- rendering -----------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderedPage:
    page_id: int
    doc_id: str
    vendor: str
    family: str
    doc_type: str
    page_number: int
    doc_sha256: str
    path: str
    width: int
    height: int
    bytes: int
    rendered: bool  # False when a matching image was already on disk


def render_scale(width_pt: float, height_pt: float, target_pixels: int) -> float:
    """Points-to-pixels factor that lands the page on `target_pixels`, never upscaling past 4x.

    PDF pages are vector, so this is a real choice rather than a resize: rendering at a higher
    scale genuinely produces sharper glyphs. The cap only guards against a pathologically small
    page box turning into an enormous bitmap.
    """
    area = max(width_pt * height_pt, 1.0)
    return min((target_pixels / area) ** 0.5, 4.0)


def image_path(pages_dir: Path, ref: PageRef) -> Path:
    return pages_dir / ref.doc_id / f"p{ref.page_number:04d}.png"


def render_document(
    pdf_path: Path,
    refs: list[PageRef],
    pages_dir: Path,
    target_pixels: int = config.MCU_TARGET_PIXELS,
    overwrite: bool = False,
) -> list[RenderedPage]:
    """Render one document's selected pages to PNG, skipping images already on disk."""
    import pypdfium2 as pdfium
    from PIL import Image

    out: list[RenderedPage] = []
    pdf = None
    try:
        for ref in refs:
            dest = image_path(pages_dir, ref)
            if dest.exists() and not overwrite:
                with Image.open(dest) as img:  # header only, no decode
                    width, height = img.size
                out.append(_row(ref, dest, width, height, dest.stat().st_size, rendered=False))
                continue

            if pdf is None:
                pdf = pdfium.PdfDocument(str(pdf_path))
            page = pdf[ref.page_number - 1]
            width_pt, height_pt = page.get_size()
            bitmap = page.render(scale=render_scale(width_pt, height_pt, target_pixels))
            image = bitmap.to_pil().convert("RGB")
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Written via a temporary name so an interrupted run cannot leave a truncated PNG
            # that the skip-if-exists branch would then trust.
            tmp = dest.with_suffix(".png.part")
            image.save(tmp, format="PNG", optimize=True)
            tmp.replace(dest)
            out.append(
                _row(ref, dest, image.width, image.height, dest.stat().st_size, rendered=True)
            )
    finally:
        if pdf is not None:
            pdf.close()
    return out


def _row(ref: PageRef, path: Path, width: int, height: int, size: int, rendered: bool):
    return RenderedPage(
        **asdict(ref), path=str(path), width=width, height=height, bytes=size, rendered=rendered
    )


def render_corpus(
    manifest: Manifest,
    pdf_dir: Path = config.MCU_PDF_DIR,
    pages_dir: Path = config.MCU_PAGES_DIR,
    documents: list[Document] | None = None,
    target_pixels: int = config.MCU_TARGET_PIXELS,
    overwrite: bool = False,
    progress=None,
) -> tuple[list[RenderedPage], float]:
    """Render every selected page of every (selected) document. Returns (rows, seconds)."""
    ordinals = doc_ordinals(manifest)
    started = time.perf_counter()
    rows: list[RenderedPage] = []
    for doc in documents if documents is not None else manifest.documents:
        refs = page_refs(doc, ordinals[doc.doc_id])
        rows.extend(
            render_document(doc.path(pdf_dir), refs, pages_dir, target_pixels, overwrite=overwrite)
        )
        if progress is not None:
            progress(doc, refs)
    return rows, time.perf_counter() - started


# --- the page table ------------------------------------------------------------------------


def page_table(rows: list[RenderedPage]) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in rows]).sort_values("page_id").reset_index(drop=True)


def save_page_table(table: pd.DataFrame, path: Path = config.MCU_PAGE_TABLE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path, index=False)
    return path


def load_page_table(path: Path = config.MCU_PAGE_TABLE) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} — run `make pages` first")
    return pd.read_parquet(path)


def table_problems(table: pd.DataFrame, manifest: Manifest) -> list[str]:
    """Invariants the rest of the pipeline relies on. Empty list == usable."""
    out: list[str] = []
    if table["page_id"].duplicated().any():
        out.append("duplicate page_id — the ids are supposed to be unique across the corpus")
    pinned = {d.doc_id: d.sha256 for d in manifest.documents}
    for doc_id, sha in table.groupby("doc_id")["doc_sha256"].first().items():
        if pinned.get(doc_id) != sha:
            out.append(f"{doc_id}: pages were rendered from a different revision than is pinned")
    missing = [p for p in table["path"] if not Path(p).exists()]
    if missing:
        out.append(f"{len(missing)} page image(s) named in the table are gone from disk")
    return out


def summarise(table: pd.DataFrame) -> dict:
    """The numbers worth reporting: page counts and megapixels by document and by type."""
    megapixels = (table["width"] * table["height"]) / 1e6
    return {
        "pages": int(len(table)),
        "documents": int(table["doc_id"].nunique()),
        "bytes": int(table["bytes"].sum()),
        "megapixels_mean": round(float(megapixels.mean()), 2),
        "megapixels_min": round(float(megapixels.min()), 2),
        "megapixels_max": round(float(megapixels.max()), 2),
        "by_doc_type": table.groupby("doc_type").size().to_dict(),
        "by_vendor": table.groupby("vendor").size().to_dict(),
        "by_doc": table.groupby("doc_id").size().to_dict(),
    }
