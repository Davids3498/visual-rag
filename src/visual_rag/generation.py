"""Client for the self-hosted VLM: answers grounded in retrieved page *images*.

The generator never sees OCR text. It sees the same page images the visual retriever ranked,
and it is asked to cite the pages it used — so an answer can be checked against the evidence
rather than taken on faith. That is the whole point of building it this way.

The server is vLLM's OpenAI-compatible endpoint (see docker-compose.yml, `serving` profile).
"""

from __future__ import annotations

import base64
import io
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

DEFAULT_BASE_URL = os.environ.get("VRAG_VLLM_URL", "http://localhost:8000/v1")
DEFAULT_MODEL = "qwen2.5-vl-7b-awq"

SYSTEM_PROMPT = (
    "You answer questions about pages from technical manuals. You are given page images, each "
    "labelled 'Page N'. Answer only from what is visible in those pages — tables, diagrams and "
    "text all count as visible.\n"
    "Rules:\n"
    "1. Cite every claim inline as [Page N], using the labels given.\n"
    "2. If the pages do not contain the answer, reply exactly: NOT_IN_PAGES\n"
    "3. Be specific: quote the exact values, part numbers and units shown, not paraphrases.\n"
    "4. Keep the answer under 120 words."
)

CITATION = re.compile(r"\[?[Pp]age\s+(\d+)\]?")


@dataclass
class VLMConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    max_tokens: int = 400
    temperature: float = 0.0  # deterministic: this is an evaluation, not a demo
    timeout: float = 180.0
    max_pages: int = 3
    jpeg_quality: int = 85
    # Corpus pages are 3.3-4.1 MP, which Qwen2.5-VL turns into ~4-5k visual tokens each —
    # three of them would not fit an 8k context. Measured on a dense 13-row stock-number
    # table, capping at 1.2 MP recovered 10/10 exact part numbers against 9/10 at native
    # resolution, for a third of the prompt tokens. More pixels is not more accuracy here.
    max_pixels: int = 1_200_000


@dataclass
class Answer:
    text: str
    cited_pages: list[int]  # corpus_ids, resolved from the [Page N] labels
    shown_pages: list[int]
    refused: bool
    latency_ms: float
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def uncited(self) -> bool:
        return not self.refused and not self.cited_pages


def downscale(image, max_pixels: int):
    """Shrink to a pixel budget, preserving aspect ratio. Never upscales."""
    pixels = image.width * image.height
    if not max_pixels or pixels <= max_pixels:
        return image
    scale = (max_pixels / pixels) ** 0.5
    return image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))


def encode_image(image, quality: int = 85, max_pixels: int = 0) -> str:
    """PIL image -> data URL, downscaled to the token budget. JPEG keeps the payload small."""
    buffer = io.BytesIO()
    downscale(image, max_pixels).convert("RGB").save(buffer, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def build_messages(question: str, pages: list[dict], cfg: VLMConfig) -> list[dict]:
    """One user turn: each page labelled and shown, then the question."""
    content: list[dict] = []
    for position, page in enumerate(pages[: cfg.max_pages], start=1):
        content.append(
            {
                "type": "text",
                "text": f"Page {position} (document {page['doc_id']}, page {page['page_number']}):",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": encode_image(page["image"], cfg.jpeg_quality, cfg.max_pixels)},
            }
        )
    content.append({"type": "text", "text": f"Question: {question}"})
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def parse_citations(text: str, pages: list[dict], cfg: VLMConfig) -> list[int]:
    """Resolve '[Page 2]' back to the corpus_id that was shown in slot 2."""
    shown = [page["corpus_id"] for page in pages[: cfg.max_pages]]
    cited = []
    for match in CITATION.finditer(text):
        index = int(match.group(1)) - 1
        if 0 <= index < len(shown) and shown[index] not in cited:
            cited.append(shown[index])
    return cited


def health(cfg: VLMConfig) -> bool:
    try:
        response = requests.get(cfg.base_url.replace("/v1", "/health"), timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def answer(question: str, pages: list[dict], cfg: VLMConfig | None = None) -> Answer:
    """Ask the served model, with the retrieved pages as the only evidence."""
    cfg = cfg or VLMConfig()
    payload = {
        "model": cfg.model,
        "messages": build_messages(question, pages, cfg),
        "max_tokens": cfg.max_tokens,
        "temperature": cfg.temperature,
    }
    started = time.perf_counter()
    response = requests.post(f"{cfg.base_url}/chat/completions", json=payload, timeout=cfg.timeout)
    response.raise_for_status()
    body = response.json()
    latency_ms = (time.perf_counter() - started) * 1000

    text = body["choices"][0]["message"]["content"].strip()
    refused = "NOT_IN_PAGES" in text
    return Answer(
        text=text,
        cited_pages=parse_citations(text, pages, cfg),
        shown_pages=[page["corpus_id"] for page in pages[: cfg.max_pages]],
        refused=refused,
        latency_ms=latency_ms,
        usage=body.get("usage", {}),
    )
