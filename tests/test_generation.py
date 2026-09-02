"""Prompt-assembly and citation-parsing tests — no server needed.

The citation parser is what turns "the model said [Page 2]" into "the model used corpus_id
4805", and every grounding number in the report is downstream of it.
"""

from __future__ import annotations

import pytest
from PIL import Image

from visual_rag import generation

CFG = generation.VLMConfig(max_pages=3)


def page(corpus_id: int, colour=(255, 255, 255)) -> dict:
    return {
        "corpus_id": corpus_id,
        "image": Image.new("RGB", (32, 48), colour),
        "doc_id": "TO_1-1-1",
        "page_number": corpus_id % 100,
    }


def test_citations_resolve_to_the_page_shown_in_that_slot():
    pages = [page(10), page(20), page(30)]
    text = "The value is 1.5 mils [Page 2] and the unit is listed on [Page 3]."
    assert generation.parse_citations(text, pages, CFG) == [20, 30]


def test_citations_out_of_range_are_ignored_not_guessed():
    pages = [page(10), page(20)]
    assert generation.parse_citations("see [Page 7]", pages, CFG) == []
    assert generation.parse_citations("see [Page 0]", pages, CFG) == []


def test_repeated_citations_are_deduplicated_in_order():
    pages = [page(10), page(20)]
    text = "[Page 2] then [Page 1] then [Page 2] again"
    assert generation.parse_citations(text, pages, CFG) == [20, 10]


def test_citation_parsing_tolerates_loose_formatting():
    pages = [page(10), page(20)]
    assert generation.parse_citations("as shown on page 2", pages, CFG) == [20]


def test_only_the_pages_actually_sent_can_be_cited():
    """max_pages truncates what is shown; a citation past it must not resolve."""
    pages = [page(10), page(20), page(30), page(40)]
    cfg = generation.VLMConfig(max_pages=2)
    assert generation.parse_citations("[Page 3]", pages, cfg) == []


def test_messages_interleave_labels_and_images_then_ask():
    messages = generation.build_messages("What is the NSN?", [page(10), page(20)], CFG)
    assert messages[0]["role"] == "system"
    content = messages[1]["content"]
    assert [part["type"] for part in content] == [
        "text",
        "image_url",
        "text",
        "image_url",
        "text",
    ]
    assert content[0]["text"].startswith("Page 1 (document TO_1-1-1")
    assert content[-1]["text"] == "Question: What is the NSN?"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_more_pages_than_the_limit_are_not_sent():
    messages = generation.build_messages("q", [page(i) for i in range(9)], CFG)
    images = [p for p in messages[1]["content"] if p["type"] == "image_url"]
    assert len(images) == 3


def test_refusal_token_is_recognised():
    assert "NOT_IN_PAGES" in generation.SYSTEM_PROMPT
    assert generation.parse_citations("NOT_IN_PAGES", [page(10)], CFG) == []


def test_health_is_false_when_nothing_is_listening():
    cfg = generation.VLMConfig(base_url="http://127.0.0.1:9/v1")
    assert generation.health(cfg) is False


@pytest.mark.parametrize("quality", [60, 85])
def test_image_encoding_round_trips_to_a_data_url(quality):
    url = generation.encode_image(Image.new("RGB", (16, 16)), quality)
    assert url.startswith("data:image/jpeg;base64,")
    assert len(url) > 60


def test_downscale_respects_the_pixel_budget_and_aspect_ratio():
    image = Image.new("RGB", (1800, 2300))  # a real page size from this corpus
    smaller = generation.downscale(image, 1_200_000)
    assert smaller.width * smaller.height <= 1_200_000
    assert abs(smaller.width / smaller.height - 1800 / 2300) < 0.01


def test_downscale_never_upscales_a_small_page():
    image = Image.new("RGB", (100, 100))
    assert generation.downscale(image, 1_200_000).size == (100, 100)
    assert generation.downscale(image, 0).size == (100, 100)
