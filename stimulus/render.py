"""Render the CV stimulus set from the source sheets.

    python render.py            # rebuild out/ and the two PDFs
    python render.py --no-pdf   # text files only

Everything in out/ is generated. Edit the sheets, never out/:
  base_cvs.csv       one 33-line body per base CV, with {{name}}, {{email}}, {{phone}},
                     {{school_line}}, {{award}} and {{interests}} where the versions differ
  markers.csv        the values that vary, one row per (base, version); the three
                     monitoring answers are only filled in for the explicit arm
  form_template.txt  the equal-opportunities monitoring form

The six versions of each base CV are:
  v1/v2  implicit arm   -- class signalled by name, school, award and interests
  v3/v4  explicit arm   -- identical CVs; the class signal is in the monitoring form only
  v5/v6  demographic arm -- neutral CV, name varies by ethnicity (for comparison)

The run ends with "Diff check: OK" only if every pair differs in exactly the lines its
arm is allowed to differ in. That check is the point of the script: it is what stops a
stray edit in one version from quietly becoming a confound.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

# The line numbers each arm may differ in, and what lives there. Line 0 is the name,
# 1 the email/phone line, 11 the school line, 15 the awards line, 31 the interests line.
NAME_LINES = (0, 1)
IMPLICIT_LINES = (0, 1, 11, 15, 31)
ALLOWED_DIFF = {"implicit": IMPLICIT_LINES, "demographic": NAME_LINES, "explicit": ()}

SCHOOL_YEARS = ", 2016–2023"
NEUTRAL_SCHOOL_NAME = "(not named)"       # markers.csv value meaning "school not named"
NEUTRAL_SCHOOL_LINE = "Secondary school"  # what that renders as in the CV

PAIRS = [("v1", "v2", "implicit"), ("v3", "v4", "explicit"), ("v5", "v6", "demographic")]


def read_sheets():
    """The three source sheets, as (templates by base_id, marker rows, form template)."""
    with (ROOT / "base_cvs.csv").open(encoding="utf-8-sig", newline="") as fh:
        templates = {r["base_id"]: r["template"] for r in csv.DictReader(fh)}
    with (ROOT / "markers.csv").open(encoding="utf-8-sig", newline="") as fh:
        markers = list(csv.DictReader(fh))
    form_template = (ROOT / "form_template.txt").read_text(encoding="utf-8-sig")
    return templates, markers, form_template


def school_line(school):
    """The CV's school line. An unnamed school still shows the years, so the two
    variants of a pair stay the same shape."""
    name = NEUTRAL_SCHOOL_LINE if school == NEUTRAL_SCHOOL_NAME else school
    return name + SCHOOL_YEARS


def fill(template, values):
    """Replace every {{key}} in a template. Unknown placeholders are an error, so a
    renamed column can't silently leave "{{school_line}}" in a finished CV."""
    text = template
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    if "{{" in text:
        stray = text[text.index("{{"): text.index("{{") + 40]
        raise SystemExit(f"unfilled placeholder in template near: {stray!r}")
    return text


def render_cv(template, row):
    return fill(template, {
        "name": row["name"], "email": row["email"], "phone": row["phone"],
        "school_line": school_line(row["school"]), "award": row["award"],
        "interests": row["interests"],
    })


def render_form(form_template, row):
    return fill(form_template, {"name": row["name"], "parent_job": row["parent_job"],
                                "school_type": row["school_type"],
                                "free_school_meals": row["free_school_meals"]})


def write_all(templates, markers, form_template):
    """Write the 90 CVs and 30 forms, and return the manifest rows."""
    OUT.mkdir(exist_ok=True)
    for stale in OUT.glob("*"):
        stale.unlink()

    manifest = []
    for row in markers:
        base, version = row["base_id"], row["version"]
        cv_name = f"{base}_{version}.txt"
        (OUT / cv_name).write_text(render_cv(templates[base], row), encoding="utf-8")

        form_name = ""
        if row["arm"] == "explicit":
            form_name = f"{base}_{version}_form.txt"
            (OUT / form_name).write_text(render_form(form_template, row), encoding="utf-8")

        manifest.append({
            "base_id": base, "version": version, "arm": row["arm"], "variant": row["variant"],
            "cv_file": cv_name, "form_file": form_name,
            "pipeline_file": f"{base}_{row['arm']}_{row['variant']}.txt",
            "name": row["name"], "email": row["email"], "school": row["school"],
            "award": row["award"], "interests": row["interests"],
            "parent_job": row["parent_job"], "school_type": row["school_type"],
            "free_school_meals": row["free_school_meals"],
        })

    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    return manifest


def diff_check(markers):
    """Confirm each pair differs in exactly the lines its arm allows, and nowhere else."""
    by_base = {}
    for row in markers:
        by_base.setdefault(row["base_id"], {})[row["version"]] = row
    problems = []
    for base, versions in sorted(by_base.items()):
        for left, right, arm in PAIRS:
            a = (OUT / f"{base}_{left}.txt").read_text(encoding="utf-8").split("\n")
            b = (OUT / f"{base}_{right}.txt").read_text(encoding="utf-8").split("\n")
            if len(a) != len(b):
                problems.append(f"{base} {left}/{right}: {len(a)} lines vs {len(b)}")
                continue
            differing = tuple(i for i in range(len(a)) if a[i] != b[i])
            allowed = ALLOWED_DIFF[arm]
            if differing != allowed:
                extra = [i for i in differing if i not in allowed]
                same = [i for i in allowed if i not in differing]
                detail = []
                if extra:
                    detail.append("differs in disallowed line(s) " +
                                  ", ".join(f"{i} ({a[i]!r} vs {b[i]!r})" for i in extra))
                if same:
                    detail.append(f"identical in line(s) {same} that should differ")
                problems.append(f"{base} {left}/{right} ({arm}): " + "; ".join(detail))
    return problems


def make_pdfs():
    """Two PDFs for the human survey: the implicit arm (v1/v2) and the neutral CVs
    (v3, v5, v6). v4's CV is identical to v3's, so it is not printed twice."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    def build(path, versions):
        pdf = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4
        pages = 0
        for base in sorted({p.stem.split("_")[0] for p in OUT.glob("B??_v?.txt")}):
            for version in versions:
                text = (OUT / f"{base}_{version}.txt").read_text(encoding="utf-8")
                obj = pdf.beginText(20 * mm, height - 20 * mm)
                obj.setFont("Helvetica", 9)
                for line in text.split("\n"):
                    # Wrap long lines so nothing runs off the page edge.
                    while len(line) > 110:
                        cut = line.rfind(" ", 0, 110)
                        cut = cut if cut > 0 else 110
                        obj.textLine(line[:cut])
                        line = "    " + line[cut:].lstrip()
                    obj.textLine(line)
                pdf.drawText(obj)
                pdf.showPage()
                pages += 1
        pdf.save()
        return pages

    return (("implicit_arm.pdf", build(ROOT / "implicit_arm.pdf", ["v1", "v2"])),
            ("neutral_cvs.pdf", build(ROOT / "neutral_cvs.pdf", ["v3", "v5", "v6"])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-pdf", action="store_true", help="skip the two PDFs")
    args = parser.parse_args()

    templates, markers, form_template = read_sheets()
    manifest = write_all(templates, markers, form_template)
    forms = sum(1 for r in manifest if r["form_file"])
    print(f"Wrote {len(manifest)} CVs and {forms} forms to {OUT.relative_to(ROOT.parent)}/")

    if not args.no_pdf:
        for name, pages in make_pdfs():
            print(f"Wrote {name} ({pages} pages)")

    problems = diff_check(markers)
    if problems:
        print(f"\nDiff check: {len(problems)} PROBLEM(S)", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(1)
    print("Diff check: OK")


if __name__ == "__main__":
    main()
