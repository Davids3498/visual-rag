"""Step 1 (last bullet) — look at the pages, don't just trust the ids.

For a sample of eval queries, renders the gold page image with the annotator bounding boxes
drawn on it, side by side with the query, the human reference answer, and the OCR `markdown`
for that same page — i.e. exactly what the text baseline will get to see.

The point is to confirm with my own eyes that the evidence lives in tables and diagrams, and
that the OCR column next to it is a poor substitute. Output: reports/sanity/*.png
"""

from __future__ import annotations

import argparse
import textwrap

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console

from visual_rag import config, data

console = Console()

PANEL_W = 760
MARGIN = 24
PAGE_MAX_H = 1500
BG = (255, 255, 255)
INK = (20, 20, 20)
MUTED = (110, 110, 110)
# One colour per annotator, so disagreement between annotators is visible rather than merged.
BOX_COLORS = [(214, 39, 40), (31, 119, 180), (44, 160, 44), (255, 127, 14)]

FONT_CANDIDATES = {
    "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_CANDIDATES[kind], size)
    except OSError:
        return ImageFont.load_default(size=size)


def draw_boxes(page: Image.Image, boxes: list[dict]) -> Image.Image:
    """Draw the annotator spans on a copy of the page."""
    canvas = page.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas, "RGBA")
    width = max(3, round(min(canvas.size) / 350))
    for box in boxes:
        color = BOX_COLORS[int(box["annotator"]) % len(BOX_COLORS)]
        xy = (int(box["x1"]), int(box["y1"]), int(box["x2"]), int(box["y2"]))
        draw.rectangle(xy, outline=color, width=width)
        draw.rectangle(xy, fill=(*color, 28))
    return canvas


class Panel:
    """Tiny top-down text layout helper — cheaper than pulling in a plotting library."""

    def __init__(self, draw: ImageDraw.ImageDraw, x: int, y: int, width: int):
        self.draw, self.x, self.y, self.width = draw, x, y, width

    def text(self, body: str, kind: str = "regular", size: int = 18, color=INK, wrap: int = 70):
        f = font(kind, size)
        for line in body.splitlines() or [""]:
            for chunk in textwrap.wrap(line, wrap) or [""]:
                self.draw.text((self.x, self.y), chunk, font=f, fill=color)
                self.y += size + 5
        return self

    def gap(self, px: int = 12):
        self.y += px
        return self

    def rule(self):
        self.gap(8)
        self.draw.line((self.x, self.y, self.x + self.width, self.y), fill=(220, 220, 220), width=1)
        self.gap(12)
        return self


def render(query_row, gold_row, page: Image.Image, markdown: str) -> Image.Image:
    boxed = draw_boxes(page, list(gold_row.bounding_boxes))
    scale = min(1.0, PAGE_MAX_H / boxed.height)
    if scale < 1.0:
        boxed = boxed.resize((round(boxed.width * scale), round(boxed.height * scale)))

    canvas = Image.new(
        "RGB", (boxed.width + PANEL_W + 3 * MARGIN, max(boxed.height, PAGE_MAX_H) + 2 * MARGIN), BG
    )
    canvas.paste(boxed, (MARGIN, MARGIN))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(
        (MARGIN - 1, MARGIN - 1, MARGIN + boxed.width, MARGIN + boxed.height),
        outline=(200, 200, 200),
    )

    panel = Panel(draw, boxed.width + 2 * MARGIN, MARGIN, PANEL_W)
    panel.text(f"query {query_row.query_id}", "bold", 22)
    panel.text(
        f"{', '.join(query_row.query_types)} · {query_row.query_format} · "
        f"{query_row.n_relevant} relevant page(s)",
        size=15,
        color=MUTED,
    )
    panel.gap()
    panel.text(query_row.query, size=19)
    panel.rule()

    panel.text(
        f"gold page  corpus_id={gold_row.corpus_id}  score={gold_row.score}  "
        f"{gold_row.doc_id} p{gold_row.page_number_in_doc}",
        "bold",
        16,
    )
    panel.text(
        f"annotated content: {', '.join(gold_row.content_type)}  "
        f"({len(gold_row.bounding_boxes)} box(es))",
        size=16,
        color=MUTED,
    )
    panel.rule()

    panel.text("reference answer", "bold", 16)
    panel.gap(4)
    panel.text((query_row.answer or "").strip(), size=16)
    panel.rule()

    panel.text("what the text baseline sees (OCR markdown for this page)", "bold", 16)
    panel.gap(4)
    excerpt = (markdown or "").strip()
    panel.text(
        excerpt[:1400] + ("\n[...]" if len(excerpt) > 1400 else "") or "(empty)",
        "mono",
        13,
        MUTED,
        wrap=92,
    )
    # Trim the unused canvas below whichever column ran shorter.
    return canvas.crop((0, 0, canvas.width, max(boxed.height + 2 * MARGIN, panel.y + MARGIN)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=6, help="how many queries to render")
    parser.add_argument(
        "--visual-only",
        action="store_true",
        help="only queries whose gold evidence is entirely non-text (tables/diagrams)",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    config.ensure_dirs()
    eval_set = data.load_eval_set()
    queries = eval_set.queries
    if args.visual_only:
        queries = queries[queries["visual_only"]]
    if queries.empty:
        console.print("[red]no queries match the filter[/red]")
        return 1

    # Bias the sample toward table/diagram evidence — that is the case the project is about —
    # but keep a couple of plain-text queries as the control.
    visual = queries[queries["n_visual_gold"] > 0]
    textual = queries[queries["n_visual_gold"] == 0]
    n_visual = min(len(visual), max(1, args.n - 2)) if len(textual) else min(len(visual), args.n)
    picked = visual.sample(n_visual, random_state=args.seed)
    if len(picked) < args.n and len(textual):
        n_text = min(len(textual), args.n - len(picked))
        picked = pd.concat([picked, textual.sample(n_text, random_state=args.seed)])
    picked = picked.sort_values("query_id")

    console.print("loading corpus images (first call decodes from the HF cache)…")
    corpus_ds, id_to_row = data.load_corpus_images()

    written = []
    for query_row in picked.itertuples():
        gold = eval_set.qrels[eval_set.qrels["query_id"] == query_row.query_id]
        # Highest-graded page first: score 2 means the page fully answers the query.
        gold_row = gold.sort_values("score", ascending=False).iloc[0]
        record = corpus_ds[id_to_row[int(gold_row.corpus_id)]]
        image = render(query_row, gold_row, record["image"], record["markdown"])
        out = config.SANITY_DIR / f"q{query_row.query_id:04d}_c{int(gold_row.corpus_id):05d}.png"
        image.save(out, optimize=True)
        written.append(out)
        console.print(
            f"  [green]{out.name}[/green]  {', '.join(gold_row.content_type)} · "
            f"score {gold_row.score} · {len(record['markdown'] or '')} chars of OCR"
        )

    console.print(f"\nwrote {len(written)} render(s) to {config.SANITY_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
