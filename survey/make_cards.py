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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent
CV_DIR = ROOT.parent / "cvs"
OUT = ROOT / "cards"
ARM = "implicit"
SEED = 20261020
INK, SOFT, RULE = "#111111", "#555555", "#999999"

NAME = ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK, spaceAfter=1)
CONTACT = ParagraphStyle("contact", fontName="Helvetica", fontSize=10, leading=13, textColor=SOFT, spaceAfter=6)
HEADING = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=INK,
                         spaceBefore=8, spaceAfter=2)
ENTRY = ParagraphStyle("entry", fontName="Helvetica-Bold", fontSize=11, leading=14.5, textColor=INK, spaceBefore=3)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=11, leading=14.5, textColor=INK, alignment=TA_LEFT)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=10, bulletIndent=0)


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


def flow(text: str, headings: set[str]) -> list:
    """The CV as paragraphs: name, contact line, then sections. Within a section the
    text is split into blocks at blank lines; a block of more than one line is an
    entry (a degree, a job) whose first line is set bold, and lines starting with
    "- " are bullets. A one-line block (the profile, skills, interests) is plain."""
    lines = text.splitlines()
    story = [Paragraph(esc(lines[0].strip()), NAME), Paragraph(esc(lines[1].strip()), CONTACT)]
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
            story.append(Paragraph(esc(block[0]), HEADING))
            continue
        for i, line in enumerate(block):
            if line.startswith("- "):
                story.append(Paragraph(esc(line[2:]), BULLET, bulletText="\u2022"))
            elif i == 0 and len(block) > 1:
                story.append(Paragraph(esc(line), ENTRY))
            else:
                story.append(Paragraph(esc(line), BODY))
    return story


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cvs = load_cvs()
    headings = section_headings(cvs)
    order = list(range(len(cvs)))
    random.Random(SEED).shuffle(order)
    cards = [(n + 1, cvs[i]) for n, i in enumerate(order)]

    pdf_path = OUT / "cards.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title="CV cards", author="")
    story = []
    labels = {}

    def corner(canvas, doc_):
        n = labels[doc_.page]
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(RULE)
        canvas.drawRightString(A4[0] - 20 * mm, A4[1] - 12 * mm, f"Card {n:02d}")
        canvas.restoreState()

    from reportlab.platypus import PageBreak
    for page, (n, (sid, cv_id, variant, text)) in enumerate(cards, 1):
        labels[page] = n
        story += flow(text, headings)
        if page < len(cards):
            story.append(PageBreak())
    doc.build(story, onFirstPage=corner, onLaterPages=corner)

    with open(OUT / "card_key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["card", "stimulus_id", "cv_id", "arm", "variant", "name"])
        for n, (sid, cv_id, variant, text) in cards:
            w.writerow([f"{n:02d}", sid, cv_id, ARM, variant, text.splitlines()[0].strip()])
    print(f"{len(cards)} cards -> {pdf_path}; key -> {OUT / 'card_key.csv'}; headings: {sorted(headings)}")


if __name__ == "__main__":
    main()
