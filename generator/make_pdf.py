"""Turn rendered CV text files into one A4 PDF, one page per CV.

    python make_pdf.py out/*v1*.txt out/*v2*.txt -o implicit_arm.pdf
    python make_pdf.py out/*v3*.txt out/*v5*.txt out/*v6*.txt -o neutral_cvs.pdf

For CV files only: the _form.txt files are not CVs and are skipped with a warning.
Layout: name in bold at the top, section headings in bold, bullets indented, long
lines wrapped. Every CV must fit on one page; the script says so if one doesn't.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

HEADINGS = {"personal profile", "education", "work experience", "skills", "interests",
            "equal opportunities monitoring"}

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=13, alignment=TA_LEFT)
NAME = ParagraphStyle("name", parent=BODY, fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=1)
CONTACT = ParagraphStyle("contact", parent=BODY, textColor="#333333")
HEADING = ParagraphStyle("heading", parent=BODY, fontName="Helvetica-Bold", fontSize=11, leading=14,
                         spaceBefore=7, spaceAfter=2)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=12, firstLineIndent=-8)


def cv_flowables(text):
    """The reportlab flowables for one CV's text."""
    lines = text.rstrip("\n").splitlines()
    flow = []
    for i, line in enumerate(lines):
        if i == 0:
            flow.append(Paragraph(escape(line), NAME))
        elif i == 1:
            flow.append(Paragraph(escape(line), CONTACT))
        elif not line.strip():
            flow.append(Spacer(1, 5))
        elif line.strip().casefold() in HEADINGS:
            flow.append(Paragraph(escape(line.strip()), HEADING))
        elif line.startswith("- "):
            flow.append(Paragraph("• " + escape(line[2:]), BULLET))
        else:
            flow.append(Paragraph(escape(line), BODY))
    return flow


class PageCounter:
    """Counts the pages each CV takes, so a CV that spills onto a second page is reported."""

    def __init__(self):
        self.pages = 0

    def __call__(self, canvas, doc):
        self.pages += 1


def make_pdf(paths, output):
    story = []
    kept = []
    for path in paths:
        path = Path(path)
        if path.name.endswith("_form.txt"):
            print(f"skipped {path.name}: monitoring forms are not CVs", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8-sig")
        if kept:
            story.append(PageBreak())
        story += cv_flowables(text)
        kept.append(path)
    if not kept:
        sys.exit("no CV files to put in the PDF")
    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=Path(output).stem,
                            author="")
    counter = PageCounter()
    doc.build(story, onFirstPage=counter, onLaterPages=counter)
    print(f"{output}: {len(kept)} CVs on {counter.pages} pages")
    if counter.pages != len(kept):
        print(f"WARNING: {counter.pages - len(kept)} CV(s) ran over one page; shorten them or the layout",
              file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Turn rendered CV text files into an A4 PDF, one page each.")
    parser.add_argument("files", nargs="+", help="CV text files, in the order they should appear")
    parser.add_argument("-o", "--output", required=True, help="the PDF to write")
    args = parser.parse_args(argv)
    sys.exit(make_pdf(args.files, args.output))


if __name__ == "__main__":
    main()
