"""Unit tests for the Part 2 corpus manifest, plus invariants on the committed manifest itself."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from visual_rag import corpus

# --- page selection -----------------------------------------------------------------------


def test_whole_selects_every_physical_page():
    assert corpus.PageSpec(mode="whole").page_numbers(4) == [1, 2, 3, 4]


def test_slice_expands_inclusive_one_based_ranges():
    spec = corpus.PageSpec(mode="slice", ranges=((1, 2), (10, 12)))
    assert spec.page_numbers(640) == [1, 2, 10, 11, 12]
    assert spec.page_count(640) == 5


def test_slice_clips_to_the_document_and_dedupes_overlaps():
    spec = corpus.PageSpec(mode="slice", ranges=((1, 3), (2, 4)))
    assert spec.page_numbers(3) == [1, 2, 3]


def test_pending_slice_refuses_to_expand_rather_than_ingesting_everything():
    spec = corpus.PageSpec(mode="slice")
    assert spec.pending
    assert spec.page_count(1741) is None
    with pytest.raises(ValueError):
        spec.page_numbers(1741)


def test_whole_is_never_pending():
    assert not corpus.PageSpec(mode="whole").pending


@pytest.mark.parametrize(
    "spec,total,needle",
    [
        (corpus.PageSpec("slice", ((0, 5),)), 100, "below page 1"),
        (corpus.PageSpec("slice", ((9, 4),)), 100, "ends before it starts"),
        (corpus.PageSpec("slice", ((90, 120),)), 100, "past the document"),
        (corpus.PageSpec("slice", ((1, 10), (5, 20))), 100, "overlaps"),
        (corpus.PageSpec("whole", ((1, 10),)), 100, "must not carry ranges"),
    ],
)
def test_problems_catches_bad_ranges(spec, total, needle):
    assert any(needle in p for p in spec.problems(total))


def test_good_ranges_have_no_problems():
    assert corpus.PageSpec("slice", ((1, 40), (150, 220))).problems(640) == []


# --- manifest validation ------------------------------------------------------------------


def make_doc(**kwargs):
    base = dict(
        doc_id="st_x_datasheet",
        vendor="st",
        family="x",
        doc_type="datasheet",
        title="t",
        url="https://example.com/x.pdf",
    )
    base.update(kwargs)
    return corpus.Document(**base)


def make_manifest(documents, licenses=None):
    return corpus.Manifest(
        corpus_id="test",
        description="",
        licenses=licenses if licenses is not None else {"st": corpus.License("terms", False)},
        documents=documents,
    )


def test_valid_manifest_has_no_problems():
    assert make_manifest([make_doc()]).problems() == []


def test_duplicate_doc_ids_are_rejected():
    problems = make_manifest([make_doc(), make_doc(url="https://example.com/y.pdf")]).problems()
    assert any("duplicate doc_id" in p for p in problems)


def test_two_documents_may_not_share_a_url():
    docs = [make_doc(), make_doc(doc_id="other")]
    assert any("same URL" in p for p in make_manifest(docs).problems())


def test_a_vendor_without_a_licence_entry_is_a_problem():
    problems = make_manifest([make_doc(vendor="nordic")]).problems()
    assert any("no licence entry" in p for p in problems)


@pytest.mark.parametrize(
    "kwargs,needle",
    [
        ({"url": "http://example.com/x.pdf"}, "must be https"),
        ({"doc_type": "app_note"}, "doc_type"),
        ({"doc_id": "has space"}, "path-safe"),
        ({"sha256": "a" * 64}, "recorded together"),
        ({"sha256": "abc", "bytes": 10}, "64-char hex"),
        ({"fetch_mode": "playwright"}, "fetch_mode"),
    ],
)
def test_document_problems(kwargs, needle):
    assert any(needle in p for p in make_doc(**kwargs).problems())


def test_json_round_trip_preserves_ranges_and_pins():
    doc = make_doc(
        pages=corpus.PageSpec("slice", ((1, 10), (100, 120)), why="because"),
        sha256="f" * 64,
        bytes=123,
        page_count=640,
        expected_pages=640,
        revision="Rev 5",
    )
    manifest = make_manifest([doc])
    reloaded = corpus.Manifest.from_json_dict(json.loads(json.dumps(manifest.to_json_dict())))
    assert reloaded.to_json_dict() == manifest.to_json_dict()
    assert reloaded.by_id(doc.doc_id).pages.ranges == ((1, 10), (100, 120))
    assert reloaded.licenses["st"].redistribute is False


def test_select_filters_are_conjunctive():
    docs = [
        make_doc(doc_id="a", vendor="st", doc_type="datasheet", url="https://e.com/a.pdf"),
        make_doc(doc_id="b", vendor="st", doc_type="errata", url="https://e.com/b.pdf"),
        make_doc(doc_id="c", vendor="espressif", doc_type="errata", url="https://e.com/c.pdf"),
    ]
    manifest = make_manifest(
        docs, {"st": corpus.License("t", False), "espressif": corpus.License("t", False)}
    )
    assert [d.doc_id for d in manifest.select(vendors=["st"])] == ["a", "b"]
    assert [d.doc_id for d in manifest.select(vendors=["st"], doc_types=["errata"])] == ["b"]
    assert [d.doc_id for d in manifest.select(doc_ids=["c"])] == ["c"]


# --- hashing and sync ---------------------------------------------------------------------


def test_sha256_file_matches_hashlib(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"pin me")
    assert corpus.sha256_file(path) == hashlib.sha256(b"pin me").hexdigest()


@pytest.fixture
def fake_pages(monkeypatch):
    monkeypatch.setattr(corpus, "pdf_page_count", lambda path: 24)


def write_pdf(path, body=b"body"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(corpus.PDF_MAGIC + b"1.7\n" + body)
    return corpus.sha256_file(path)


def test_matching_local_file_is_cached_and_the_manifest_is_untouched(tmp_path, fake_pages):
    doc = make_doc()
    digest = write_pdf(doc.path(tmp_path))
    doc = replace(doc, sha256=digest, bytes=doc.path(tmp_path).stat().st_size)
    result, updated = corpus.sync_document(doc, tmp_path)
    assert result.status == "cached"
    assert result.ok
    assert updated is doc
    assert result.selected_pages == 24


def test_a_changed_local_file_fails_instead_of_scoring_on_new_ground(tmp_path, fake_pages):
    doc = make_doc(sha256="a" * 64, bytes=5)
    write_pdf(doc.path(tmp_path))
    result, _ = corpus.sync_document(doc, tmp_path)
    assert result.status == "hash-mismatch"
    assert not result.ok


def test_present_but_unpinned_fails_until_record_pins_it(tmp_path, fake_pages):
    doc = make_doc()
    digest = write_pdf(doc.path(tmp_path))

    result, updated = corpus.sync_document(doc, tmp_path)
    assert result.status == "unpinned"
    assert not result.ok
    assert updated.sha256 is None

    result, updated = corpus.sync_document(doc, tmp_path, record=True)
    assert result.status == "recorded"
    assert updated.sha256 == digest
    assert updated.page_count == 24
    assert updated.bytes == doc.path(tmp_path).stat().st_size
    assert updated.retrieved_at


def test_verify_only_reports_missing_without_touching_the_network(tmp_path):
    result, _ = corpus.sync_document(make_doc(), tmp_path, verify_only=True)
    assert result.status == "missing"
    assert not result.ok


class StubFetcher:
    """Stands in for `Fetcher`: writes fixed bytes instead of making a request."""

    def __init__(self, body):
        self.body = body
        self.requests_made = 0

    def download(self, url, dest):
        self.requests_made += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.body)
        return corpus.Download(hashlib.sha256(self.body).hexdigest(), len(self.body), url)


def test_a_superseded_document_is_parked_not_installed(tmp_path, fake_pages):
    doc = make_doc(sha256="b" * 64, bytes=4)
    body = corpus.PDF_MAGIC + b"revision 5"
    result, updated = corpus.sync_document(doc, tmp_path, StubFetcher(body))
    assert result.status == "hash-mismatch"
    assert not doc.path(tmp_path).exists()  # the corpus dir never holds unverified bytes
    assert corpus.superseded_path(doc.path(tmp_path), result.sha256).exists()
    assert updated is doc  # the pin is not quietly moved


def test_force_record_repins_a_superseded_document(tmp_path, fake_pages):
    doc = make_doc(sha256="b" * 64, bytes=4)
    body = corpus.PDF_MAGIC + b"revision 5"
    result, updated = corpus.sync_document(
        doc, tmp_path, StubFetcher(body), record=True, force=True
    )
    assert result.status == "recorded"
    assert updated.sha256 == hashlib.sha256(body).hexdigest()
    assert doc.path(tmp_path).exists()


def test_download_of_a_pinned_document_is_a_plain_success(tmp_path, fake_pages):
    body = corpus.PDF_MAGIC + b"pinned"
    doc = make_doc(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    result, updated = corpus.sync_document(doc, tmp_path, StubFetcher(body))
    assert result.status == "downloaded"
    assert updated is doc


def test_pending_slices_warn_but_do_not_fail_the_fetch(tmp_path, fake_pages):
    doc = make_doc(pages=corpus.PageSpec("slice"))
    digest = write_pdf(doc.path(tmp_path))
    doc = replace(doc, sha256=digest, bytes=doc.path(tmp_path).stat().st_size)
    result, _ = corpus.sync_document(doc, tmp_path)
    assert result.ok
    assert result.selected_pages is None
    assert "slice ranges not chosen" in result.message


def test_expected_pages_mismatch_warns(tmp_path, fake_pages):
    doc = make_doc(expected_pages=640)
    digest = write_pdf(doc.path(tmp_path))
    doc = replace(doc, sha256=digest, bytes=doc.path(tmp_path).stat().st_size)
    result, _ = corpus.sync_document(doc, tmp_path)
    assert "expected roughly 640" in result.message


def test_a_manual_document_is_never_fetched_over_http(tmp_path, fake_pages):
    doc = make_doc(fetch_mode="manual")
    fetcher = StubFetcher(corpus.PDF_MAGIC + b"never asked for")
    result, _ = corpus.sync_document(doc, tmp_path, fetcher, record=True)
    assert result.status == "manual-missing"
    assert not result.ok
    assert fetcher.requests_made == 0
    assert str(doc.path(tmp_path)) in result.message  # tells the operator where to put it


def test_try_manual_overrides_the_block(tmp_path, fake_pages):
    doc = make_doc(fetch_mode="manual")
    body = corpus.PDF_MAGIC + b"worked from another network"
    result, updated = corpus.sync_document(
        doc, tmp_path, StubFetcher(body), record=True, try_manual=True
    )
    assert result.status == "recorded"
    assert updated.sha256 == hashlib.sha256(body).hexdigest()


def test_a_hand_placed_manual_file_pins_like_any_other(tmp_path, fake_pages):
    doc = make_doc(fetch_mode="manual")
    digest = write_pdf(doc.path(tmp_path))
    result, updated = corpus.sync_document(doc, tmp_path, record=True)
    assert result.status == "recorded"
    assert updated.sha256 == digest


def test_manual_downloads_lists_url_and_destination():
    doc = make_doc(fetch_mode="manual")
    manifest = make_manifest([doc])
    results = [corpus.SyncResult(doc.doc_id, "manual-missing")]
    assert corpus.manual_downloads(results, manifest, Path("/pdfs")) == [
        (doc.url, Path("/pdfs") / doc.filename)
    ]


def test_a_redirect_is_recorded_as_provenance(tmp_path, fake_pages):
    doc = make_doc()
    body = corpus.PDF_MAGIC + b"moved host"

    class Redirecting(StubFetcher):
        def download(self, url, dest):
            super().download(url, dest)
            return corpus.Download(
                hashlib.sha256(self.body).hexdigest(),
                len(self.body),
                "https://cdn.example.com/final.pdf",
            )

    _, updated = corpus.sync_document(doc, tmp_path, Redirecting(body), record=True)
    assert updated.resolved_url == "https://cdn.example.com/final.pdf"


def test_no_redirect_leaves_resolved_url_empty(tmp_path, fake_pages):
    doc = make_doc()
    body = corpus.PDF_MAGIC + b"same host"
    _, updated = corpus.sync_document(doc, tmp_path, StubFetcher(body), record=True)
    assert updated.resolved_url is None


# --- the identity guard ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text,hint,expected",
    [
        ("DS5319 Rev 20 STM32F103x8", "DS5319", True),
        ("ESP32 T echnical Reference ManualVersion 5.8", "Technical Reference Manual", True),
        ("ESP32 Series SoC ErrataVersion v3.0", "SoC Errata", True),
        ("rm0008 reference manual", "RM0008", True),
        ("DS5319 Rev 20 medium-density performance line", "ES096", False),
    ],
)
def test_identity_ignores_the_whitespace_pdf_extraction_invents(text, hint, expected):
    assert corpus.identity_ok(text, hint) is expected


def test_the_right_pdf_under_the_wrong_name_cannot_be_pinned(tmp_path, fake_pages, monkeypatch):
    monkeypatch.setattr(corpus, "first_pages_text", lambda path, pages=3: "DS5319 Rev 20")
    doc = make_doc(doc_id="st_errata", identity_hint="ES096", fetch_mode="manual")
    write_pdf(doc.path(tmp_path))
    result, updated = corpus.sync_document(doc, tmp_path, record=True)
    assert result.status == "identity-mismatch"
    assert not result.ok
    assert updated.sha256 is None  # nothing written into the manifest


def test_the_named_document_pins_normally(tmp_path, fake_pages, monkeypatch):
    monkeypatch.setattr(corpus, "first_pages_text", lambda path, pages=3: "ES096 Rev 7")
    doc = make_doc(identity_hint="ES096", fetch_mode="manual")
    write_pdf(doc.path(tmp_path))
    result, updated = corpus.sync_document(doc, tmp_path, record=True)
    assert result.status == "recorded"
    assert updated.sha256


def test_an_unextractable_pdf_warns_rather_than_blocking(tmp_path, fake_pages, monkeypatch):
    monkeypatch.setattr(corpus, "first_pages_text", lambda path, pages=3: "   ")
    doc = make_doc(identity_hint="ES096")
    write_pdf(doc.path(tmp_path))
    result, updated = corpus.sync_document(doc, tmp_path, record=True)
    assert result.status == "recorded"
    assert "could not confirm" in result.message


def test_identity_is_only_checked_when_a_pin_is_created(tmp_path, fake_pages, monkeypatch):
    # once pinned, the hash is the guard; re-reading text on every run would be wasted work
    calls = []
    monkeypatch.setattr(corpus, "first_pages_text", lambda path, pages=3: calls.append(path) or "x")
    doc = make_doc(identity_hint="ES096")
    digest = write_pdf(doc.path(tmp_path))
    doc = replace(doc, sha256=digest, bytes=doc.path(tmp_path).stat().st_size)
    result, _ = corpus.sync_document(doc, tmp_path)
    assert result.status == "cached"
    assert calls == []


# --- the consent-page guard ---------------------------------------------------------------


class FakeResponse:
    def __init__(
        self,
        body,
        status_code=200,
        content_type="application/pdf",
        url="https://cdn.example.com/x.pdf",
    ):
        self.body = body
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=1):
        yield self.body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}

    def get(self, url, timeout=None, stream=None):
        return self.response


def test_a_200_that_is_not_a_pdf_fails_loudly(tmp_path):
    fetcher = corpus.Fetcher(corpus.FetchPolicy(min_delay_s=0, max_delay_s=0, retries=0))
    fetcher.session = FakeSession(
        FakeResponse(b"<html>accept our terms</html>", content_type="text/html")
    )
    with pytest.raises(RuntimeError, match="%PDF-"):
        fetcher.download("https://example.com/x.pdf", tmp_path / "x.pdf")
    assert not (tmp_path / "x.pdf").exists()
    assert not (tmp_path / "x.part").exists()


def test_a_real_pdf_body_is_hashed_on_the_way_through(tmp_path):
    body = corpus.PDF_MAGIC + b"1.7 real content"
    fetcher = corpus.Fetcher(corpus.FetchPolicy(min_delay_s=0, max_delay_s=0))
    fetcher.session = FakeSession(FakeResponse(body))
    result = fetcher.download("https://example.com/x.pdf", tmp_path / "x.pdf")
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.bytes == len(body)
    assert result.resolved_url == "https://cdn.example.com/x.pdf"
    assert (tmp_path / "x.pdf").read_bytes() == body


# --- page budget --------------------------------------------------------------------------


def test_page_budget_rolls_up_by_type_and_vendor_and_flags_pending():
    docs = [
        make_doc(doc_id="ds", vendor="st", doc_type="datasheet", url="https://e.com/1.pdf"),
        make_doc(doc_id="rm", vendor="st", doc_type="reference_manual", url="https://e.com/2.pdf"),
        make_doc(doc_id="er", vendor="espressif", doc_type="errata", url="https://e.com/3.pdf"),
    ]
    manifest = make_manifest(
        docs, {"st": corpus.License("t", False), "espressif": corpus.License("t", False)}
    )
    results = [
        corpus.SyncResult("ds", "cached", page_count=130, selected_pages=130, bytes=1000),
        corpus.SyncResult("rm", "cached", page_count=1136, selected_pages=None, bytes=2000),
        corpus.SyncResult("er", "cached", page_count=24, selected_pages=24, bytes=500),
    ]
    budget = corpus.page_budget(results, manifest)
    assert budget["physical_pages"] == 1290
    assert budget["selected_pages"] == 154
    assert budget["pending_documents"] == ["rm"]
    assert budget["by_vendor"] == {"st": 130, "espressif": 24}
    assert budget["by_doc_type"] == {"datasheet": 130, "errata": 24}


# --- invariants on the committed manifest -------------------------------------------------


@pytest.fixture(scope="module")
def mcu():
    return corpus.load_manifest()


def test_the_committed_manifest_is_valid(mcu):
    assert mcu.problems() == []


def test_every_vendor_has_an_explicit_licence_decision(mcu):
    for doc in mcu.documents:
        licence = mcu.licenses[doc.vendor]
        assert licence.terms.strip()
        assert isinstance(licence.redistribute, bool)


def test_datasheets_and_errata_are_taken_whole_unless_the_reason_is_written_down(mcu):
    for doc in mcu.documents:
        if doc.doc_type in ("datasheet", "errata") and doc.pages.mode == "slice":
            assert doc.pages.why, f"{doc.doc_id} is sliced without saying why"


def test_every_reference_manual_is_sliced(mcu):
    manuals = [d for d in mcu.documents if d.doc_type == "reference_manual"]
    assert manuals
    for doc in manuals:
        assert doc.pages.mode == "slice", f"{doc.doc_id} would add ~{doc.expected_pages} pages"


def test_every_page_spec_explains_itself(mcu):
    for doc in mcu.documents:
        assert doc.pages.why.strip(), f"{doc.doc_id}: no rationale for its page selection"


def test_every_hand_placed_document_can_be_identity_checked(mcu):
    for doc in mcu.documents:
        assert doc.identity_hint, f"{doc.doc_id}: no identity_hint to catch a misnamed file"


def test_manual_acquisition_is_always_justified_in_the_notes(mcu):
    for doc in mcu.documents:
        if doc.fetch_mode == "manual":
            assert "ACQUISITION" in doc.notes, f"{doc.doc_id}: manual mode with no reason given"


def test_the_corpus_spans_several_vendors_and_families(mcu):
    assert len({d.vendor for d in mcu.documents}) >= 3
    assert len({d.family for d in mcu.documents}) >= 4


def test_at_least_three_families_can_ask_cross_document_questions(mcu):
    by_family = {}
    for doc in mcu.documents:
        by_family.setdefault(doc.family, set()).add(doc.doc_type)
    pairs = [f for f, types in by_family.items() if {"errata", "reference_manual"} <= types]
    assert len(pairs) >= 3
