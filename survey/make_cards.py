"""Printable cards for the human check:  python survey/make_cards.py

One implicit-arm CV per A4 page, set like a real CV, with only a card number in the
corner. survey/cards/cards.pdf is what you print; survey/cards/card_key.csv says
which CV each card is (keep it off the table). Cards are numbered in a shuffled
order with a fixed seed, so neighbouring numbers are not the two versions of one base.
"""

from __future__ import annotations

import csv
import random
import re
import sys
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent
CV_DIR = ROOT.parent / "cvs"
OUT = ROOT / "cards"
ARM = "implicit"
SEED = 20261020
INK, SOFT, RULE = "#111111", "#555555", "#999999"

# Each card is set at the largest type size at which it still fills one page and no
# more, so a short CV gets bigger type than a long one. Bold is for the name, the
# section headings and the entry titles only; everything else is plain.
SCALES = [round(2.2 - 0.025 * i, 3) for i in range(49)]  # 2.2 down to 1.0
MARGINS = dict(leftMargin=13 * mm, rightMargin=13 * mm, topMargin=13 * mm, bottomMargin=11 * mm)


def styles(scale: float, gap: float = 0.0) -> dict:
    """Type at this scale; `gap` is extra space above each section heading and
    entry title, used to spread a card over the whole page once its size is set."""
    body = 11 * scale
    return {
        "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=18 * scale, leading=22 * scale,
                               textColor=INK, spaceAfter=2 * scale),
        "contact": ParagraphStyle("contact", fontName="Helvetica", fontSize=10 * scale, leading=13 * scale,
                                  textColor=SOFT, spaceAfter=3 * scale + gap),
        "heading": ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=12 * scale, leading=15 * scale,
                                  textColor=INK, spaceBefore=9 * scale + gap, spaceAfter=1.5 * scale),
        "entry": ParagraphStyle("entry", fontName="Helvetica-Bold", fontSize=body, leading=1.22 * body,
                                textColor=INK, spaceBefore=4 * scale + gap / 2),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=body, leading=1.22 * body, textColor=INK,
                               alignment=TA_LEFT),
    }


def used_height(story, width) -> float:
    """The height the card's paragraphs take at this width, spacing included."""
    total = 0.0
    for i, f in enumerate(story):
        _, h = f.wrap(width, 10000)
        total += h + f.getSpaceAfter() + (f.getSpaceBefore() if i else 0)
    return total


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_cvs() -> list[tuple[str, str, str, str]]:
    """(stimulus_id, cv_id, variant, text) for every CV of the arm, in file order."""
    out = []
    for path in sorted(CV_DIR.glob(f"*_{ARM}_*.txt")):
        cv_id, _, variant = path.stem.split("_")
        out.append((path.stem, cv_id, variant, path.read_text(encoding="utf-8")))
    if not out:
        sys.exit(f"no {ARM}-arm CVs in {CV_DIR}: run stimulus/install_to_pipeline.py first")
    return out


def section_headings(cvs) -> set[str]:
    """Lines that stand alone as a section heading in most CVs (no digits, short)."""
    counts: dict[str, int] = {}
    for *_, text in cvs:
        for line in {ln.strip() for ln in text.splitlines()}:
            if line and len(line) <= 30 and not re.search(r"\d|:|,|\(", line):
                counts[line] = counts.get(line, 0) + 1
    return {line for line, n in counts.items() if n >= len(cvs) // 2}


def flow(text: str, headings: set[str], st: dict) -> list:
    """The CV as paragraphs: name, contact line, then sections. Within a section the
    text is split into blocks at blank lines; a block of more than one line is an
    entry (a degree, a job) whose first line is set bold, and lines starting with
    "- " are bullets. A one-line block (the profile, skills, interests) is plain."""
    lines = text.splitlines()
    bullet = ParagraphStyle("bullet", parent=st["body"], leftIndent=14 * st["body"].fontSize / 11, bulletIndent=0)
    scale = st["body"].fontSize / 11
    story = [Paragraph(esc(lines[0].strip()), st["name"]), Paragraph(esc(lines[1].strip()), st["contact"]),
             HRFlowable(width="100%", thickness=1, color=INK, spaceBefore=0, spaceAfter=2 * scale)]
    blocks: list[list[str]] = [[]]
    for raw in lines[2:]:
        line = raw.strip()
        if not line:
            if blocks[-1]:
                blocks.append([])
            continue
        if line in headings:
            if blocks[-1]:
                blocks.append([])
            blocks[-1].append(line)
            blocks.append([])
            continue
        blocks[-1].append(line)
    for block in blocks:
        if not block:
            continue
        if len(block) == 1 and block[0] in headings:
            story.append(Paragraph(esc(block[0]), st["heading"]))
            story.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=0, spaceAfter=3 * scale))
            continue
        for i, line in enumerate(block):
            if line.startswith("- "):
                story.append(Paragraph(esc(line[2:]), bullet, bulletText="\u2022"))
            elif i == 0 and len(block) > 1:
                story.append(Paragraph(esc(line), st["entry"]))
            else:
                story.append(Paragraph(esc(line), st["body"]))
    return story


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cvs = load_cvs()
    headings = section_headings(cvs)
    order = list(range(len(cvs)))
    random.Random(SEED).shuffle(order)
    cards = [(n + 1, cvs[i]) for n, i in enumerate(order)]

    pdf_path = OUT / "cards.pdf"
    margins = MARGINS
    # The frame inside the margins has 6pt of padding on each side.
    frame_w = A4[0] - margins["leftMargin"] - margins["rightMargin"] - 12
    frame_h = A4[1] - margins["topMargin"] - margins["bottomMargin"] - 12

    def pages(text, scale, gap=0.0) -> int:
        """How many pages the card takes, from a throwaway build: the real layout."""
        import io
        d = SimpleDocTemplate(io.BytesIO(), pagesize=A4, **margins)
        d.build(flow(text, headings, styles(scale, gap)))
        return d.page

    chosen = []
    for n, (sid, cv_id, variant, text) in cards:
        # The largest type size that fits one page, by the height estimate, confirmed
        # by a real build; then the largest spacing that still builds as one page.
        scale = next((sc for sc in SCALES
                      if used_height(flow(text, headings, styles(sc)), frame_w) <= frame_h and pages(text, sc) == 1),
                     None)
        if scale is None:
            sys.exit(f"card {n:02d} ({sid}) does not fit one page even at the smallest size")
        lo, hi = 0.0, 8.0
        while pages(text, scale, hi) == 1 and hi < 400:
            lo, hi = hi, hi * 2
        for _ in range(10):
            mid = (lo + hi) / 2
            if pages(text, scale, mid) == 1:
                lo = mid
            else:
                hi = mid
        chosen.append((scale, lo))

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, title="CV cards", author="", **margins)
    story = []
    labels = {}

    def corner(canvas, doc_):
        n = labels[doc_.page]
        canvas.saveState()
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(RULE)
        canvas.drawRightString(A4[0] - 13 * mm, A4[1] - 8 * mm, f"Card {n:02d}")
        canvas.restoreState()

    from reportlab.platypus import PageBreak
    for page, ((n, (sid, cv_id, variant, text)), (scale, gap)) in enumerate(zip(cards, chosen), 1):
        labels[page] = n
        story += flow(text, headings, styles(scale, gap))
        if page < len(cards):
            story.append(PageBreak())
    doc.build(story, onFirstPage=corner, onLaterPages=corner)
    if doc.page != len(cards):
        sys.exit(f"{doc.page} pages for {len(cards)} cards: a card spilled on to a second page")
    print("type scale and gap per card:", ", ".join(f"{n:02d}:{sc:g}/{g:.0f}" for (n, _), (sc, g) in zip(cards, chosen)))

    with open(OUT / "card_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["card", "stimulus_id", "cv_id", "arm", "variant", "name"])
        for n, (sid, cv_id, variant, text) in cards:
            w.writerow([f"{n:02d}", sid, cv_id, ARM, variant, text.splitlines()[0].strip()])
    print(f"{len(cards)} cards -> {pdf_path}; key -> {OUT / 'card_key.csv'}; headings: {sorted(headings)}")


if __name__ == "__main__":
    main()
