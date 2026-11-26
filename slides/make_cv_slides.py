"""CV pair slides:  python slides/make_cv_slides.py  then  node slides/render.js

Writes slides/cv_pair_hinted.html (B10, class hinted by name, school, award and
interests) and slides/cv_pair_stated.html (B10, the same CV with class stated in
the equal-opportunities box), with the lines that differ highlighted.
"""

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "slides"
STIM = ROOT / "stimulus" / "out"
HEADINGS = {"Personal Profile", "Education", "Work Experience", "Skills", "Interests",
            "Equal Opportunities Monitoring"}


def read(cv, form=None):
    text = (STIM / cv).read_text(encoding="utf-8").rstrip("\n")
    if form:
        text += "\n\n" + (STIM / form).read_text(encoding="utf-8").rstrip("\n")
    return text.splitlines()


def card(lines, others, label, tag):
    out = []
    for i, line in enumerate(lines):
        changed = line != others[i]
        hl = " hl" if changed else ""
        if not line.strip():
            out.append('<div class="gap"></div>')
        elif i == 0:
            out.append(f'<div class="name{hl}">{html.escape(line)}</div>')
        elif i == 1:
            out.append(f'<div class="contact{hl}">{html.escape(line)}</div>')
        elif line in HEADINGS:
            out.append(f'<div class="h">{html.escape(line)}</div>')
        elif changed and "? " in line:
            question, answer = line.rsplit("? ", 1)
            out.append(f'<div class="ln q">{html.escape(question)}?</div><div class="hl ans">{html.escape(answer)}</div>')
        elif line.startswith("- "):
            out.append(f'<div class="li{hl}">{html.escape(line[2:])}</div>')
        else:
            out.append(f'<div class="ln{hl}">{html.escape(line)}</div>')
    return f'<section class="col"><div class="tag {tag}">{label}</div><article class="cv">{"".join(out)}</article></section>'


STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1920px; height: 1080px; }
body { background: #f4f3ef; font-family: Inter, sans-serif; color: #1d1d1b; padding: 44px 72px 0; }
.row { display: flex; gap: 48px; }
.col { flex: 1; min-width: 0; }
.tag { display: inline-flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 600; margin-bottom: 12px; }
.tag::before { content: ""; width: 13px; height: 13px; border-radius: 50%; }
.tag.hi::before { background: #6250d6; }
.tag.lo::before { background: #1baf7a; }
.cv { background: #fff; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,.06), 0 6px 24px rgba(0,0,0,.06);
      padding: 34px 40px; line-height: 1.5; height: 950px; overflow: hidden; }
.name { font-size: 1.6em; font-weight: 700; width: fit-content; }
.contact { color: #52514e; width: fit-content; margin-top: .25em; }
.h { font-weight: 700; font-size: .88em; text-transform: uppercase; letter-spacing: .05em; color: #3a3936;
     border-bottom: 1px solid #e3e1db; padding-bottom: 2px; margin-bottom: 4px; }
.gap { height: .65em; }
.li { padding-left: 1em; position: relative; }
.li::before { content: "\\2022"; position: absolute; left: .2em; color: #8a8984; }
.q { color: #52514e; }
.hl { background: #fbe7a1; border-radius: 4px; box-shadow: -6px 0 0 #fbe7a1, 6px 0 0 #fbe7a1; font-weight: 600;
      color: #1d1d1b; width: fit-content; }
.ans { margin: 1px 0 5px 6px; }
"""

FIT = """<script>
document.fonts.ready.then(() => {
  const cards = [...document.querySelectorAll('.cv')];
  let size = 20;
  const set = s => cards.forEach(c => c.style.fontSize = s + 'px');
  set(size);
  while (size > 10 && cards.some(c => c.scrollHeight > c.clientHeight)) { size -= 0.2; set(size); }
  document.body.dataset.fitted = size.toFixed(1);
});
</script>"""


def page(high, low):
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{STYLE}</style></head><body>'
            f'<div class="row">{card(high, low, "Higher-class version", "hi")}'
            f'{card(low, high, "Lower-class version", "lo")}</div>{FIT}</body></html>')


if __name__ == "__main__":
    pairs = {"cv_pair_hinted.html": (read("B10_v1.txt"), read("B10_v2.txt")),
             "cv_pair_stated.html": (read("B10_v3.txt", "B10_v3_form.txt"), read("B10_v4.txt", "B10_v4_form.txt"))}
    for name, (high, low) in pairs.items():
        assert len(high) == len(low), name
        (OUT / name).write_text(page(high, low), encoding="utf-8")
        print(OUT / name)
