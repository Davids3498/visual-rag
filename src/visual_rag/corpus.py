"""The Part 2 corpus definition: a manifest of vendor PDFs, not the PDFs themselves.

Retrieval numbers reproduce only if the corpus reproduces. The bytes here are neither ours
nor redistributable, so what is version-controlled is a *manifest* — URL, content hash,
revision, which pages are in scope, licence status — and `scripts/09_fetch_corpus.py`
rebuilds `data/mcu/pdfs/` from it.

Two invariants earn their keep:

* every document carries a sha256 recorded at collect time and re-verified on every fetch.
  Vendors supersede documents in place (STM32 datasheets change revision at the same URL),
  which would silently move the ground under the eval set. A mismatch fails the run instead.
* every vendor has an explicit licence entry. Adding a vendor forces a decision about
  redistribution rather than leaving it implicit.

Page selection is part of the manifest because the retrieval unit is the page: a 1,741-page
reference manual is mostly running prose, where the visual-vs-text delta is near zero, so
only the chapters the errata actually reference are ingested. Whole datasheets and errata,
sliced manuals.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import requests

from . import config

SCHEMA_VERSION = 1

DOC_TYPES = ("datasheet", "errata", "reference_manual")

# How a document is acquired. "manual" exists because some vendors' edges refuse scripted
# clients outright (st.com's Akamai front end black-holes both HTTP/2 and HTTP/1.1 requests
# from this machine, with or without full browser headers). Rather than escalate into
# fingerprint impersonation, those documents are downloaded once in a browser and dropped
# into the PDF directory by hand; the manifest still pins their hash, so the corpus is just
# as reproducible — only the acquisition step is manual.
FETCH_MODES = ("http", "manual")

# Some vendor CDNs (st.com among them) answer a bare client library with 403. A browser UA
# gets the same public file the browser would; the rate limit below is what makes it polite.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class Download:
    """What a successful fetch learned about the bytes."""

    sha256: str
    bytes: int
    resolved_url: str  # after redirects — vendors move files between hosts (and encode the
    # document revision in the final path), so this is worth recording


# --- page selection ----------------------------------------------------------------------


@dataclass(frozen=True)
class PageSpec:
    """Which pages of a PDF belong to the corpus.

    Ranges are 1-based and inclusive, and index *physical* PDF pages — not the numbers
    printed in the footer, which are offset by the cover pages and restart in appendices.
    Resolve ranges in a viewer that shows physical position, not by the printed folio.

    `mode="slice"` with no ranges is legal and means "not chosen yet": the errata has to be
    read before you know which reference-manual chapters to keep, so the manifest can name a
    document before it can name its pages. Ingestion refuses such a document; fetching does
    not, because the bytes are needed in order to choose.
    """

    mode: Literal["whole", "slice"] = "whole"
    ranges: tuple[tuple[int, int], ...] = ()
    why: str = ""

    @property
    def pending(self) -> bool:
        return self.mode == "slice" and not self.ranges

    def page_numbers(self, total_pages: int) -> list[int]:
        """The selected page numbers, 1-based, sorted and de-duplicated."""
        if self.pending:
            raise ValueError("slice ranges have not been chosen yet")
        if self.mode == "whole":
            return list(range(1, total_pages + 1))
        pages: set[int] = set()
        for start, end in self.ranges:
            pages.update(range(start, end + 1))
        return sorted(p for p in pages if 1 <= p <= total_pages)

    def page_count(self, total_pages: int) -> int | None:
        """Selected page count, or None while the ranges are still undecided."""
        return None if self.pending else len(self.page_numbers(total_pages))

    def problems(self, total_pages: int | None = None) -> list[str]:
        """Structural complaints about the ranges. Empty list == usable."""
        out: list[str] = []
        if self.mode not in ("whole", "slice"):
            out.append(f"unknown page mode {self.mode!r}")
        if self.mode == "whole" and self.ranges:
            out.append("mode 'whole' must not carry ranges")
        seen: list[tuple[int, int]] = []
        for start, end in self.ranges:
            if start < 1:
                out.append(f"range {start}-{end} starts below page 1")
            if end < start:
                out.append(f"range {start}-{end} ends before it starts")
            if total_pages is not None and end > total_pages:
                out.append(f"range {start}-{end} runs past the document's {total_pages} pages")
            # Overlaps de-duplicate harmlessly, but they are almost always a transcription
            # slip in a hand-written range list, so say so.
            for prev in seen:
                if start <= prev[1] and prev[0] <= end:
                    out.append(f"range {start}-{end} overlaps {prev[0]}-{prev[1]}")
            seen.append((start, end))
        return out

    def to_json_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "ranges": [list(r) for r in self.ranges], "why": self.why}

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> PageSpec:
        ranges = tuple((int(r[0]), int(r[1])) for r in raw.get("ranges", ()))
        return cls(mode=raw.get("mode", "whole"), ranges=ranges, why=raw.get("why", ""))


# --- documents and licences --------------------------------------------------------------


@dataclass(frozen=True)
class License:
    """The vendor's terms, as they bear on this project. Not legal advice, a decision record."""

    terms: str
    redistribute: bool  # may the PDF itself be re-hosted? assume no unless a licence says yes
    url: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {"terms": self.terms, "redistribute": self.redistribute, "url": self.url}

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> License:
        return cls(
            terms=raw["terms"], redistribute=bool(raw["redistribute"]), url=raw.get("url", "")
        )


@dataclass(frozen=True)
class Document:
    """One vendor PDF, pinned.

    The fields below the `pages` spec are *recorded*, not authored: `--record` fills them in
    from the first successful download and every later fetch checks against them.
    """

    doc_id: str
    vendor: str
    family: str
    doc_type: str
    title: str
    url: str
    identity_hint: str = ""  # must appear in the document's first pages — see identity_ok()
    fetch_mode: str = "http"
    pages: PageSpec = field(default_factory=PageSpec)
    expected_pages: int | None = None  # rough, from the vendor's page; a first-fetch sanity net
    revision: str | None = None
    notes: str = ""
    sha256: str | None = None
    bytes: int | None = None
    page_count: int | None = None
    retrieved_at: str | None = None
    resolved_url: str | None = None

    @property
    def filename(self) -> str:
        return f"{self.doc_id}.pdf"

    @property
    def pinned(self) -> bool:
        return self.sha256 is not None

    def path(self, out_dir: Path) -> Path:
        return out_dir / self.filename

    def selected_pages(self) -> int | None:
        """Pages this document contributes to the corpus, if that is known yet."""
        if self.page_count is None:
            return None
        return self.pages.page_count(self.page_count)

    def problems(self) -> list[str]:
        out: list[str] = []
        if not self.doc_id or any(c in self.doc_id for c in "/\\ "):
            out.append(f"{self.doc_id!r}: doc_id must be a path-safe token")
        if self.doc_type not in DOC_TYPES:
            out.append(f"{self.doc_id}: doc_type {self.doc_type!r} not in {DOC_TYPES}")
        if not self.url.startswith("https://"):
            out.append(f"{self.doc_id}: url must be https")
        if self.fetch_mode not in FETCH_MODES:
            out.append(f"{self.doc_id}: fetch_mode {self.fetch_mode!r} not in {FETCH_MODES}")
        out += [f"{self.doc_id}: {p}" for p in self.pages.problems(self.page_count)]
        if (self.sha256 is None) != (self.bytes is None):
            out.append(f"{self.doc_id}: sha256 and bytes must be recorded together")
        if self.sha256 is not None and len(self.sha256) != 64:
            out.append(f"{self.doc_id}: sha256 is not a 64-char hex digest")
        return out

    def to_json_dict(self) -> dict[str, Any]:
        # Fixed key order: the manifest is hand-edited and diffed, so a --record run must not
        # reshuffle the file.
        return {
            "doc_id": self.doc_id,
            "vendor": self.vendor,
            "family": self.family,
            "doc_type": self.doc_type,
            "title": self.title,
            "identity_hint": self.identity_hint,
            "url": self.url,
            "fetch_mode": self.fetch_mode,
            "pages": self.pages.to_json_dict(),
            "expected_pages": self.expected_pages,
            "revision": self.revision,
            "notes": self.notes,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "page_count": self.page_count,
            "retrieved_at": self.retrieved_at,
            "resolved_url": self.resolved_url,
        }

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> Document:
        return cls(
            doc_id=raw["doc_id"],
            vendor=raw["vendor"],
            family=raw["family"],
            doc_type=raw["doc_type"],
            title=raw.get("title", ""),
            identity_hint=raw.get("identity_hint", ""),
            url=raw["url"],
            fetch_mode=raw.get("fetch_mode", "http"),
            pages=PageSpec.from_json_dict(raw.get("pages", {})),
            expected_pages=raw.get("expected_pages"),
            revision=raw.get("revision"),
            notes=raw.get("notes", ""),
            sha256=raw.get("sha256"),
            bytes=raw.get("bytes"),
            page_count=raw.get("page_count"),
            retrieved_at=raw.get("retrieved_at"),
            resolved_url=raw.get("resolved_url"),
        )


@dataclass(frozen=True)
class FetchPolicy:
    """How to talk to vendor servers: identify as a browser, wait between requests, retry."""

    user_agent: str = DEFAULT_USER_AGENT
    accept: str = "application/pdf,*/*;q=0.8"
    min_delay_s: float = 1.0
    max_delay_s: float = 2.0
    timeout_s: float = 60.0
    retries: int = 3

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "user_agent": self.user_agent,
            "accept": self.accept,
            "min_delay_s": self.min_delay_s,
            "max_delay_s": self.max_delay_s,
            "timeout_s": self.timeout_s,
            "retries": self.retries,
        }

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> FetchPolicy:
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})


@dataclass
class Manifest:
    corpus_id: str
    description: str
    licenses: dict[str, License]
    documents: list[Document]
    fetch: FetchPolicy = field(default_factory=FetchPolicy)
    schema_version: int = SCHEMA_VERSION

    def by_id(self, doc_id: str) -> Document:
        for doc in self.documents:
            if doc.doc_id == doc_id:
                return doc
        raise KeyError(doc_id)

    def select(
        self,
        doc_ids: list[str] | None = None,
        vendors: list[str] | None = None,
        doc_types: list[str] | None = None,
    ) -> list[Document]:
        docs = self.documents
        if doc_ids:
            docs = [d for d in docs if d.doc_id in set(doc_ids)]
        if vendors:
            docs = [d for d in docs if d.vendor in set(vendors)]
        if doc_types:
            docs = [d for d in docs if d.doc_type in set(doc_types)]
        return list(docs)

    def replace_document(self, doc: Document) -> None:
        for i, existing in enumerate(self.documents):
            if existing.doc_id == doc.doc_id:
                self.documents[i] = doc
                return
        raise KeyError(doc.doc_id)

    def problems(self) -> list[str]:
        """Everything structurally wrong with the manifest. Empty list == valid."""
        out: list[str] = []
        if self.schema_version != SCHEMA_VERSION:
            out.append(f"schema_version {self.schema_version} != {SCHEMA_VERSION}")
        seen: set[str] = set()
        for doc in self.documents:
            if doc.doc_id in seen:
                out.append(f"duplicate doc_id {doc.doc_id}")
            seen.add(doc.doc_id)
            if doc.vendor not in self.licenses:
                out.append(f"{doc.doc_id}: vendor {doc.vendor!r} has no licence entry")
            out += doc.problems()
        urls: dict[str, str] = {}
        for doc in self.documents:
            if doc.url in urls:
                out.append(f"{doc.doc_id} and {urls[doc.url]} point at the same URL")
            urls[doc.url] = doc.doc_id
        return out

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "corpus_id": self.corpus_id,
            "description": self.description,
            "fetch": self.fetch.to_json_dict(),
            "licenses": {k: v.to_json_dict() for k, v in self.licenses.items()},
            "documents": [d.to_json_dict() for d in self.documents],
        }

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> Manifest:
        return cls(
            corpus_id=raw["corpus_id"],
            description=raw.get("description", ""),
            licenses={k: License.from_json_dict(v) for k, v in raw.get("licenses", {}).items()},
            documents=[Document.from_json_dict(d) for d in raw["documents"]],
            fetch=FetchPolicy.from_json_dict(raw.get("fetch", {})),
            schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
        )


def load_manifest(path: Path = config.MCU_MANIFEST) -> Manifest:
    return Manifest.from_json_dict(json.loads(path.read_text()))


def save_manifest(manifest: Manifest, path: Path = config.MCU_MANIFEST) -> Path:
    """Write the manifest atomically, so an interrupted --record cannot truncate the pins."""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest.to_json_dict(), indent=2) + "\n")
    os.replace(tmp, path)
    return path


# --- hashing and page counts -------------------------------------------------------------


def sha256_file(path: Path, chunk_bytes: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def first_pages_text(path: Path, pages: int = 3) -> str:
    """Text of the document's opening pages, for the identity check below."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return " ".join(
        reader.pages[i].extract_text() or "" for i in range(min(pages, len(reader.pages)))
    )


def identity_ok(text: str, hint: str) -> bool:
    """Does `hint` appear in `text`, ignoring whitespace and case?

    Whitespace is stripped on both sides because PDF text extraction breaks words on kerning
    ("T echnical Reference Manual") and glues them across line ends ("SoC ErrataVersion 3.0"),
    which would defeat a literal substring match.
    """
    squash = re.compile(r"\s+")
    return squash.sub("", hint).lower() in squash.sub("", text).lower()


def pdf_page_count(path: Path) -> int:
    """Physical page count. Imported lazily so the manifest is usable without pypdf."""
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)


# --- fetching ----------------------------------------------------------------------------

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class NotAPdfError(RuntimeError):
    """The server answered 200 with something that is not a PDF (a consent or error page)."""


class Fetcher:
    """A rate-limited PDF downloader. One instance per run so the delay spans all documents."""

    def __init__(self, policy: FetchPolicy | None = None) -> None:
        self.policy = policy or FetchPolicy()
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": self.policy.user_agent, "Accept": self.policy.accept}
        )
        self._last_request: float | None = None
        self.requests_made = 0

    def _wait_turn(self) -> None:
        if self._last_request is None:
            return
        target = random.uniform(self.policy.min_delay_s, self.policy.max_delay_s)
        elapsed = time.monotonic() - self._last_request
        if elapsed < target:
            time.sleep(target - elapsed)

    def download(self, url: str, dest: Path) -> Download:
        """Stream `url` to `dest`, returning what the bytes turned out to be. Raises on give-up.

        Bytes land in a `.part` file and are hashed on the way through, so `dest` never
        exists in a half-written state and the file is never read twice.
        """
        last_error: Exception | None = None
        for attempt in range(self.policy.retries + 1):
            self._wait_turn()
            try:
                return self._download_once(url, dest)
            except NotAPdfError as exc:
                # A vendor gate or error page answered 200. Retrying returns the same page.
                raise RuntimeError(f"{url}: {exc}") from exc
            except requests.HTTPError as exc:
                last_error = exc
                if attempt == self.policy.retries or not getattr(exc, "retryable", False):
                    break
                self._backoff(attempt, getattr(exc, "retry_after", None))
            except requests.RequestException as exc:
                # Connection reset, read timeout, DNS: transient by nature, so always retry.
                last_error = exc
                if attempt == self.policy.retries:
                    break
                self._backoff(attempt, None)
        raise RuntimeError(
            f"giving up on {url} after {self.policy.retries + 1} tries: {last_error}"
        )

    def _backoff(self, attempt: int, retry_after: float | None) -> None:
        """Exponential backoff, but honour Retry-After when the server sent one."""
        time.sleep(min(retry_after or self.policy.min_delay_s * (2**attempt), 30.0))

    def _download_once(self, url: str, dest: Path) -> Download:
        self.requests_made += 1
        self._last_request = time.monotonic()
        with self.session.get(url, timeout=self.policy.timeout_s, stream=True) as response:
            if response.status_code in RETRY_STATUS:
                exc = requests.HTTPError(f"HTTP {response.status_code} for {url}")
                exc.retryable = True  # type: ignore[attr-defined]
                header = response.headers.get("Retry-After", "")
                exc.retry_after = float(header) if header.isdigit() else None  # type: ignore[attr-defined]
                raise exc
            response.raise_for_status()

            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_suffix(".part")
            digest = hashlib.sha256()
            size = 0
            first = True
            with part.open("wb") as fh:
                for block in response.iter_content(chunk_size=1 << 20):
                    if not block:
                        continue
                    if first:
                        first = False
                        # A 200 that is really a consent/interstitial page is the failure mode
                        # here, not a 404. Check the bytes, not the content type.
                        if not block.startswith(PDF_MAGIC):
                            part.unlink(missing_ok=True)
                            ctype = response.headers.get("Content-Type", "?")
                            raise NotAPdfError(
                                f"{url} returned {ctype} without a %PDF- header "
                                "(consent page or vendor gate?)"
                            )
                    digest.update(block)
                    size += len(block)
                    fh.write(block)
            os.replace(part, dest)
            self._last_request = time.monotonic()
            return Download(digest.hexdigest(), size, response.url)


# --- syncing one document ----------------------------------------------------------------

# Terminal statuses. Anything in FAILURE_STATUSES makes the run exit non-zero.
FAILURE_STATUSES = frozenset(
    {"hash-mismatch", "unpinned", "missing", "manual-missing", "identity-mismatch", "error"}
)


@dataclass
class SyncResult:
    doc_id: str
    status: str
    path: Path | None = None
    sha256: str | None = None
    bytes: int | None = None
    page_count: int | None = None
    selected_pages: int | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status not in FAILURE_STATUSES

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "status": self.status,
            "path": str(self.path) if self.path else None,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "page_count": self.page_count,
            "selected_pages": self.selected_pages,
            "message": self.message,
        }


def superseded_path(dest: Path, digest: str) -> Path:
    """Where a download that does not match the pin is parked for inspection."""
    return dest.with_name(f"{dest.stem}.superseded-{digest[:12]}.pdf")


def sync_document(
    doc: Document,
    out_dir: Path,
    fetcher: Fetcher | None = None,
    *,
    record: bool = False,
    force: bool = False,
    verify_only: bool = False,
    try_manual: bool = False,
) -> tuple[SyncResult, Document]:
    """Bring one document into `out_dir` and check it against its pin.

    Returns the outcome and the document as it should now appear in the manifest (unchanged
    unless `record` filled in a pin). Statuses:

      cached          local bytes match the recorded hash — nothing done
      downloaded      fetched, and the hash matches the pin
      recorded        fetched or found locally, and the hash was written into the manifest
      hash-mismatch   the vendor's bytes differ from the pin: the corpus has moved (fails)
      unpinned        bytes present but no recorded hash, and --record was not passed (fails)
      missing         not local and --verify-only forbade the network (fails)
      manual-missing  vendor refuses scripted clients: download it in a browser (fails)
      identity-mismatch  the bytes are a PDF, but not the document this entry names (fails)
      error           the download itself failed (fails)
    """
    dest = doc.path(out_dir)
    updated = doc
    resolved = doc.resolved_url

    if dest.exists():
        digest = sha256_file(dest)
        size = dest.stat().st_size
        if doc.sha256 is not None and digest != doc.sha256 and not force:
            return (
                SyncResult(
                    doc.doc_id,
                    "hash-mismatch",
                    path=dest,
                    sha256=digest,
                    bytes=size,
                    message=(
                        f"local file hashes {digest[:12]} but the manifest pins "
                        f"{doc.sha256[:12]}; delete it to re-fetch, or re-pin deliberately "
                        "with --record --force"
                    ),
                ),
                doc,
            )
        status = "cached" if doc.sha256 is not None else "unpinned"
        if doc.sha256 is None or force:
            if record:
                status = "recorded"
            elif doc.sha256 is None:
                return (
                    SyncResult(
                        doc.doc_id,
                        "unpinned",
                        path=dest,
                        sha256=digest,
                        bytes=size,
                        message="present but not pinned; re-run with --record to pin this hash",
                    ),
                    doc,
                )
    elif verify_only:
        return (
            SyncResult(doc.doc_id, "missing", message="not downloaded (--verify-only)"),
            doc,
        )
    elif doc.fetch_mode == "manual" and not try_manual:
        return (
            SyncResult(
                doc.doc_id,
                "manual-missing",
                message=f"download {doc.url} in a browser and save it as {dest}",
            ),
            doc,
        )
    else:
        fetcher = fetcher or Fetcher()
        try:
            download = fetcher.download(doc.url, dest)
        except Exception as exc:  # network, HTTP, or a non-PDF response
            return SyncResult(doc.doc_id, "error", message=str(exc)), doc
        digest, size = download.sha256, download.bytes
        resolved = download.resolved_url

        if doc.sha256 is not None and digest != doc.sha256 and not force:
            parked = superseded_path(dest, digest)
            os.replace(dest, parked)
            return (
                SyncResult(
                    doc.doc_id,
                    "hash-mismatch",
                    path=parked,
                    sha256=digest,
                    bytes=size,
                    message=(
                        f"vendor now serves {digest[:12]}, manifest pins {doc.sha256[:12]} — "
                        f"the document was superseded at the same URL. Parked at {parked.name}; "
                        "diff the revisions, then re-pin with --record --force and re-index"
                    ),
                ),
                doc,
            )
        if doc.sha256 is None and not record:
            return (
                SyncResult(
                    doc.doc_id,
                    "unpinned",
                    path=dest,
                    sha256=digest,
                    bytes=size,
                    message="downloaded but not pinned; re-run with --record to pin this hash",
                ),
                doc,
            )
        status = "recorded" if (record and (doc.sha256 is None or force)) else "downloaded"

    pages = pdf_page_count(dest)

    # Identity is checked when a pin is *created*, because that is the only moment the hash
    # cannot catch a wrong file: afterwards every run compares against the pin. It matters
    # most for hand-placed downloads, where saving the right PDF under the wrong name is a
    # one-keystroke mistake that would otherwise be pinned as truth.
    identity_note = ""
    if status == "recorded" and doc.identity_hint:
        text = first_pages_text(dest)
        if not text.strip():
            identity_note = f"no extractable text — could not confirm this is {doc.identity_hint}"
        elif not identity_ok(text, doc.identity_hint):
            return (
                SyncResult(
                    doc.doc_id,
                    "identity-mismatch",
                    path=dest,
                    sha256=digest,
                    bytes=size,
                    page_count=pages,
                    message=(
                        f"{dest.name} is a valid PDF but its first pages never say "
                        f"{doc.identity_hint!r} — this is not the document the manifest names. "
                        "Not pinned; check what you downloaded"
                    ),
                ),
                doc,
            )

    if status == "recorded":
        updated = replace(
            doc,
            sha256=digest,
            bytes=size,
            page_count=pages,
            retrieved_at=datetime.now(UTC).isoformat(timespec="seconds"),
            resolved_url=resolved if resolved and resolved != doc.url else None,
        )

    result = SyncResult(
        doc.doc_id,
        status,
        path=dest,
        sha256=digest,
        bytes=size,
        page_count=pages,
        selected_pages=updated.pages.page_count(pages),
    )

    # Warnings, not failures: they mean "look at this", not "the corpus is wrong".
    warnings: list[str] = []
    if doc.page_count is not None and doc.page_count != pages:
        warnings.append(f"page count changed {doc.page_count} -> {pages}")
    if doc.expected_pages and abs(pages - doc.expected_pages) > max(5, doc.expected_pages * 0.1):
        warnings.append(f"{pages} pages, expected roughly {doc.expected_pages}")
    if identity_note:
        warnings.append(identity_note)
    if updated.pages.pending:
        warnings.append("slice ranges not chosen yet — read the errata, then fill them in")
    warnings += updated.pages.problems(pages)
    result.message = "; ".join(warnings)
    return result, updated


def manual_downloads(
    results: list[SyncResult], manifest: Manifest, out_dir: Path
) -> list[tuple[str, Path]]:
    """(url, destination) for every document the operator has to fetch in a browser."""
    return [
        (manifest.by_id(r.doc_id).url, manifest.by_id(r.doc_id).path(out_dir))
        for r in results
        if r.status == "manual-missing"
    ]


def page_budget(results: list[SyncResult], manifest: Manifest) -> dict[str, Any]:
    """Roll the per-document page counts up into the number that governs Part 2's scope.

    Pages, not documents, drive index size, embedding time and retrieval difficulty, so this
    is the figure to compare against the 1,500-2,500 page target.
    """
    by_id = {d.doc_id: d for d in manifest.documents}
    totals: dict[str, Any] = {
        "documents": len(results),
        "physical_pages": 0,
        "selected_pages": 0,
        "pending_documents": [],
        "bytes": 0,
        "by_doc_type": {},
        "by_vendor": {},
    }
    for res in results:
        doc = by_id.get(res.doc_id)
        if doc is None or res.page_count is None:
            continue
        totals["physical_pages"] += res.page_count
        totals["bytes"] += res.bytes or 0
        if res.selected_pages is None:
            totals["pending_documents"].append(res.doc_id)
            continue
        totals["selected_pages"] += res.selected_pages
        for key, bucket in (("by_doc_type", doc.doc_type), ("by_vendor", doc.vendor)):
            totals[key][bucket] = totals[key].get(bucket, 0) + res.selected_pages
    return totals
