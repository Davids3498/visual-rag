"""Unit tests for page selection and rendering, plus invariants on the built page table."""

from __future__ import annotations

from pathlib import Path

import pytest

from visual_rag import corpus, ingest


def make_doc(**kwargs):
    base = dict(
        doc_id="st_x_datasheet",
        vendor="st",
        family="x",
        doc_type="datasheet",
        title="t",
        url="https://example.com/x.pdf",
        sha256="a" * 64,
        bytes=10,
        page_count=8,
    )
    base.update(kwargs)
    return corpus.Document(**base)


def make_manifest(documents):
    return corpus.Manifest(
        corpus_id="test",
        description="",
        licenses={"st": corpus.License("terms", False)},
        documents=documents,
    )


# --- which pages ---------------------------------------------------------------------------


def test_ordinals_follow_sorted_doc_ids_not_file_order():
    manifest = make_manifest([make_doc(doc_id="zulu"), make_doc(doc_id="alpha")])
    assert ingest.doc_ordinals(manifest) == {"alpha": 1, "zulu": 2}


def test_a_whole_document_contributes_every_page():
    refs = ingest.page_refs(make_doc(page_count=3), ordinal=2)
    assert [r.page_number for r in refs] == [1, 2, 3]
    assert [r.page_id for r in refs] == [20001, 20002, 20003]


def test_a_slice_contributes_only_its_ranges():
    doc = make_doc(page_count=100, pages=corpus.PageSpec("slice", ((5, 7), (20, 21))))
    assert [r.page_number for r in ingest.page_refs(doc, 1)] == [5, 6, 7, 20, 21]


def test_page_ids_are_unique_across_the_whole_corpus():
    manifest = make_manifest(
        [make_doc(doc_id="a", page_count=50), make_doc(doc_id="b", page_count=50)]
    )
    ids = [r.page_id for r in ingest.plan_pages(manifest)]
    assert len(ids) == len(set(ids)) == 100


def test_an_unpinned_document_cannot_be_rendered():
    with pytest.raises(ValueError, match="not pinned"):
        ingest.page_refs(make_doc(sha256=None, bytes=None, page_count=None), 1)


def test_a_document_whose_ranges_are_undecided_cannot_be_rendered():
    doc = make_doc(pages=corpus.PageSpec("slice"))
    with pytest.raises(ValueError, match="no slice ranges"):
        ingest.page_refs(doc, 1)


def test_every_page_carries_the_revision_it_came_from():
    refs = ingest.page_refs(make_doc(sha256="b" * 64), 1)
    assert {r.doc_sha256 for r in refs} == {"b" * 64}


# --- rendering -----------------------------------------------------------------------------


def test_render_scale_hits_the_pixel_target():
    scale = ingest.render_scale(595, 842, 1_200_000)  # A4 in points
    assert round(595 * scale * 842 * scale) == pytest.approx(1_200_000, rel=0.01)


def test_render_scale_refuses_to_explode_a_tiny_page():
    assert ingest.render_scale(10, 10, 1_200_000) == 4.0


def test_image_paths_group_by_document_and_sort_by_page():
    ref = ingest.page_refs(make_doc(page_count=12), 1)[11]
    assert ingest.image_path(Path("/pages"), ref) == Path("/pages/st_x_datasheet/p0012.png")


# --- the page table ------------------------------------------------------------------------


def rendered(page_id, doc_id="d", sha="a" * 64, path="/x.png"):
    return ingest.RenderedPage(
        page_id=page_id,
        doc_id=doc_id,
        vendor="st",
        family="f",
        doc_type="datasheet",
        page_number=page_id % 10_000,
        doc_sha256=sha,
        path=path,
        width=1000,
        height=1200,
        bytes=500,
        rendered=True,
    )


def test_the_table_is_sorted_by_page_id():
    table = ingest.page_table([rendered(20002), rendered(10001)])
    assert list(table["page_id"]) == [10001, 20002]


def test_duplicate_page_ids_are_reported():
    table = ingest.page_table([rendered(1), rendered(1)])
    manifest = make_manifest([make_doc(doc_id="d")])
    assert any("duplicate page_id" in p for p in ingest.table_problems(table, manifest))


def test_pages_rendered_from_a_superseded_revision_are_reported(tmp_path):
    image = tmp_path / "x.png"
    image.write_bytes(b"")
    table = ingest.page_table([rendered(1, sha="b" * 64, path=str(image))])
    manifest = make_manifest([make_doc(doc_id="d", sha256="a" * 64)])
    problems = ingest.table_problems(table, manifest)
    assert any("different revision" in p for p in problems)


def test_a_missing_image_file_is_reported():
    table = ingest.page_table([rendered(1, path="/definitely/not/here.png")])
    manifest = make_manifest([make_doc(doc_id="d")])
    assert any("gone from disk" in p for p in ingest.table_problems(table, manifest))


def test_summarise_counts_by_type_and_vendor():
    summary = ingest.summarise(ingest.page_table([rendered(1), rendered(2)]))
    assert summary["pages"] == 2
    assert summary["by_doc_type"] == {"datasheet": 2}
    assert summary["megapixels_mean"] == 1.2


# --- invariants on the corpus `make pages` builds (skipped until it has been run) -----------


@pytest.fixture(scope="module")
def built():
    try:
        return ingest.load_page_table()
    except FileNotFoundError:
        pytest.skip("page table not built yet — run `make pages`")


@pytest.fixture(scope="module")
def mcu():
    return corpus.load_manifest()


def test_the_built_table_holds_up(built, mcu):
    assert ingest.table_problems(built, mcu) == []


def test_every_selected_page_was_rendered(built, mcu):
    assert len(built) == len(ingest.plan_pages(mcu))


def test_no_page_outside_its_document_slice_slipped_in(built, mcu):
    for doc in mcu.documents:
        selected = set(doc.pages.page_numbers(doc.page_count))
        got = set(built[built["doc_id"] == doc.doc_id]["page_number"])
        assert got == selected, doc.doc_id


def test_images_are_near_the_measured_resolution_ceiling(built):
    megapixels = built["width"] * built["height"] / 1e6
    assert megapixels.between(1.0, 1.4).all()
