"""Build the six CV versions of every base CV from two spreadsheets.

    python render.py                 # writes out/ and ../cvs/, then runs the diff check
    python render.py --no-pipeline   # writes out/ only
    python render.py --help

Inputs (in this folder):
  base_cvs.csv      one row per base CV: everything that stays the same across versions
  markers.csv       one row per base CV: the values swapped in (schools, names, interests,
                    awards, parents' jobs)
  cv_template.txt   the Jinja2 layout of a CV
  form_template.txt the Jinja2 layout of the separate equal-opportunities monitoring form

Outputs:
  out/<base_id>_v1.txt .. _v6.txt   the six CV versions (see VERSIONS below)
  out/<base_id>_v3_form.txt, _v4_form.txt   the monitoring form for the explicit arm (parent's
                    occupation, school type and free-school-meal eligibility)
  out/manifest.csv                  what each file contains
  out/canva_bulk.csv                one row per version, one column per Canva text box
  ../cvs/<base_id>_<arm>_<variant>.txt   the same CVs named the way the scoring
                    pipeline (python -m pipeline) expects; for the explicit arm the form
                    is appended to the CV as an "Equal Opportunities Monitoring" section

The script ends with a diff check: every pair of versions must differ only in the
lines it is meant to differ in. The last line printed is "Diff check: OK" or a list
of problems (exit code 1).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
PIPELINE_CV_DIR = HERE.parent / "cvs"   # where python -m pipeline reads CVs from

# Ofcom reserves 07700 900000-900999 for drama and fiction, so this number can never
# reach a real person. It is the same in every version, so it carries no signal.
PHONE = "07700 900412"
EMAIL_DOMAIN = "gmail.com"              # first.surname@gmail.com, as a real applicant would have

# The answer options of the Social Mobility Commission's recommended school-type
# question (gov.uk, "Simplifying how employers measure socio-economic background",
# 2021), as used on the explicit-arm monitoring form.
SCHOOL_TYPE = {
    "high": "Independent or fee-paying school",
    "low": "State-run or state-funded school – non-selective",
}
# Free school meals (the SMC's third recommended question): eligibility is the low-class answer.
FSM = {"high": "No", "low": "Yes"}

# What each version is made of. `arm`/`variant` are the names the scoring pipeline
# uses (config.yaml: arms). A column name means "take this column of markers.csv";
# None for `school` means the school is not named; `form` is the class level of the
# monitoring form, or None for no form.
VERSIONS = {
    "v1": dict(arm="implicit", variant="high", name="name_high", school="school_high",
               interests="interests_high", award="award_high", form=None),
    "v2": dict(arm="implicit", variant="low", name="name_low", school="school_low",
               interests="interests_low", award="award_low", form=None),
    "v3": dict(arm="explicit", variant="high", name="name_neutral", school=None,
               interests="interests_neutral", award="award_neutral", form="high"),
    "v4": dict(arm="explicit", variant="low", name="name_neutral", school=None,
               interests="interests_neutral", award="award_neutral", form="low"),
    "v5": dict(arm="demographic", variant="a", name="name_bench_a", school=None,
               interests="interests_neutral", award="award_neutral", form=None),
    "v6": dict(arm="demographic", variant="b", name="name_bench_b", school=None,
               interests="interests_neutral", award="award_neutral", form=None),
}

BASE_COLUMNS = ["base_id", "profile", "university", "degree", "degree_class", "uni_years", "modules",
                "school_years", "alevels", "gcses", "job1_title", "job1_org", "job1_dates", "job1_bullets",
                "job2_title", "job2_org", "job2_dates", "job2_bullets", "skills"]
MARKER_COLUMNS = ["base_id", "school_high", "school_low", "name_high", "name_low", "name_neutral",
                  "name_bench_a", "name_bench_b", "interests_high", "interests_low", "interests_neutral",
                  "award_high", "award_low", "award_neutral", "parent_job_high", "parent_job_low"]

# Which template fields each pair of versions is allowed to differ in. "contact" is the
# e-mail line, which follows the name. Everything else must be identical.
ALLOWED_DIFFERENCES = {
    ("v1", "v2"): {"name", "contact", "school", "award", "interests"},
    ("v3", "v4"): set(),                 # byte-identical CVs; only the forms differ
    ("v5", "v6"): {"name", "contact"},
    ("v3", "v5"): {"name", "contact"},   # the neutral CV and the benchmark CV share everything else
}
FORM_ALLOWED_DIFFERENCES = {"parent_job", "school_type", "fsm"}

# Columns written to canva_bulk.csv, in order. Each is one text box in the Canva design.
CANVA_COLUMNS = ["Name", "Contact", "Profile", "University", "Modules", "School", "A-levels", "GCSEs",
                 "Job1 heading", "Job1 bullets", "Job2 heading", "Job2 bullets", "Skills", "Award",
                 "Interests", "Monitoring"]


class SheetError(Exception):
    """A problem in base_cvs.csv or markers.csv that stops the build."""


# ----------------------------- reading the sheets -----------------------------

def read_sheet(path, columns) -> dict[str, dict]:
    """Rows of a CSV keyed by base_id. Checks the header and that nothing is blank."""
    if not path.exists():
        raise SheetError(f"{path.name} not found")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in columns if c not in header]
        extra = [c for c in header if c not in columns]
        if missing or extra:
            raise SheetError(f"{path.name}: wrong columns. Missing: {missing or 'none'}. Unexpected: {extra or 'none'}. "
                             f"Expected exactly: {', '.join(columns)}")
        rows = {}
        for n, row in enumerate(reader, 2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}
            if not any(row.values()):
                continue   # a blank line
            base_id = row.get("base_id", "")
            if not re.fullmatch(r"B\d{2}", base_id):
                raise SheetError(f"{path.name} line {n}: base_id must look like B01, not {base_id!r}")
            if base_id in rows:
                raise SheetError(f"{path.name}: base_id {base_id} appears twice")
            blank = [c for c in columns if not row[c]]
            if blank:
                raise SheetError(f"{path.name} {base_id}: empty cell(s) in {', '.join(blank)}")
            rows[base_id] = row
    if not rows:
        raise SheetError(f"{path.name} has no rows")
    return rows


def load_sheets(folder):
    bases = read_sheet(folder / "base_cvs.csv", BASE_COLUMNS)
    markers = read_sheet(folder / "markers.csv", MARKER_COLUMNS)
    if set(bases) != set(markers):
        only_b = sorted(set(bases) - set(markers))
        only_m = sorted(set(markers) - set(bases))
        raise SheetError("base_cvs.csv and markers.csv must hold the same base_ids. "
                         f"Only in base_cvs: {only_b or 'none'}; only in markers: {only_m or 'none'}")
    return bases, markers


# ----------------------------- rendering -----------------------------

def email_for(name) -> str:
    """first.last@example.com, keeping hyphens in double-barrelled surnames."""
    parts = re.sub(r"[^a-z\- ]", "", name.lower()).split()
    return ".".join(parts) + "@" + EMAIL_DOMAIN


def split_bullets(text) -> list[str]:
    return [b.strip() for b in text.split("|") if b.strip()]


def fields_for(base, marker, spec) -> dict:
    """Every value the CV template needs for one version of one base CV."""
    name = marker[spec["name"]]
    return {
        **{k: v for k, v in base.items() if k != "base_id"},
        "job1_bullets": split_bullets(base["job1_bullets"]),
        "job2_bullets": split_bullets(base["job2_bullets"]),
        "name": name,
        "email": email_for(name),
        "contact": None,  # the contact line is derived from name; listed so the diff check can tag it
        "phone": PHONE,
        "school": marker[spec["school"]] if spec["school"] else "",
        "interests": marker[spec["interests"]],
        "award": marker[spec["award"]],
    }


def form_fields_for(marker, spec, name) -> dict | None:
    if spec["form"] is None:
        return None
    level = spec["form"]
    return {"name": name, "parent_job": marker[f"parent_job_{level}"], "school_type": SCHOOL_TYPE[level],
            "fsm": FSM[level]}


def make_env(folder):
    env = Environment(loader=FileSystemLoader(str(folder)), undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
                      autoescape=False)
    return env


def render_cv(env, fields) -> str:
    text = env.get_template("cv_template.txt").render(**fields)
    return text.rstrip("\n") + "\n"


def render_form(env, fields) -> str:
    text = env.get_template("form_template.txt").render(**fields)
    return text.rstrip("\n") + "\n"


# ----------------------------- the diff check -----------------------------

def tag_lines(env, template_name, fields, taggable) -> list[set]:
    """Which taggable fields appear on each line of the rendered template.

    The template is rendered once more with each taggable field replaced by a unique
    token, so a line that holds, say, the school can be recognised whatever its text.
    The line count is the same as in the real rendering because every taggable field
    is a single line of text.
    """
    tokens = {f: f"\x00{f.upper()}\x00" for f in taggable}
    probe = dict(fields)
    for f in taggable:
        if f == "contact":
            probe["email"] = tokens[f]
        else:
            probe[f] = tokens[f]
    text = env.get_template(template_name).render(**probe).rstrip("\n") + "\n"
    tags = []
    for line in text.splitlines():
        tags.append({f for f, tok in tokens.items() if tok in line})
    return tags


def compare(label, text_a, text_b, tags, allowed) -> list[str]:
    """Problems with one pair of texts: lines that differ outside `allowed`, lines that
    should differ but don't, or a different number of lines."""
    a, b = text_a.splitlines(), text_b.splitlines()
    problems = []
    if len(a) != len(b):
        return [f"{label}: different number of lines ({len(a)} vs {len(b)})"]
    differing_fields = set()
    for i, (la, lb) in enumerate(zip(a, b), 1):
        if la == lb:
            continue
        fields = tags[i - 1]
        if not fields or not fields <= allowed:
            problems.append(f"{label}: line {i} differs but may not: {la!r} vs {lb!r}")
        differing_fields |= fields
    # Every allowed field must actually differ; otherwise the marker is missing.
    for f in sorted(allowed - differing_fields):
        problems.append(f"{label}: the {f} line is the same in both versions, so that marker is missing")
    return problems


def diff_check(env, rendered) -> list[str]:
    """Check every base CV's versions against ALLOWED_DIFFERENCES. Returns problems."""
    cv_taggable = ["name", "contact", "school", "award", "interests"]
    form_taggable = ["name", "parent_job", "school_type", "fsm"]
    problems = []
    for base_id, versions in rendered.items():
        for (va, vb), allowed in ALLOWED_DIFFERENCES.items():
            tags = tag_lines(env, "cv_template.txt", versions[va]["fields"], cv_taggable)
            problems += compare(f"{base_id} {va}/{vb}", versions[va]["cv"], versions[vb]["cv"], tags, allowed)
        tags = tag_lines(env, "form_template.txt", versions["v3"]["form_fields"], form_taggable)
        problems += compare(f"{base_id} v3_form/v4_form", versions["v3"]["form"], versions["v4"]["form"],
                            tags, FORM_ALLOWED_DIFFERENCES)
        for v, data in versions.items():
            for text_name, text in (("cv", data["cv"]), ("form", data["form"])):
                if text and ("[" in text or "]" in text):
                    problems.append(f"{base_id} {v} {text_name}: contains a square bracket, "
                                    "which probably means a [placeholder] was left in a sheet")
    return problems


def length_report(rendered) -> list[str]:
    """How much the two CVs of each implicit pair differ in length, in percent."""
    lines = []
    for base_id, versions in rendered.items():
        a, b = len(versions["v1"]["cv"]), len(versions["v2"]["cv"])
        pct = 100 * abs(a - b) / max(a, b)
        flag = "   <-- more than 3%: consider shortening the longer marker text" if pct > 3 else ""
        lines.append(f"  {base_id} v1/v2: {a} vs {b} characters ({pct:.1f}%){flag}")
    return lines


# ----------------------------- outputs -----------------------------

def canva_row(base_id, version, fields, form_text) -> dict:
    school = f"{fields['school']}, {fields['school_years']}" if fields["school"] \
        else f"Secondary school, {fields['school_years']}"
    return {
        "base_id": base_id, "version": version,
        "Name": fields["name"],
        "Contact": f"{fields['email']} | {fields['phone']}",
        "Profile": fields["profile"],
        "University": f"{fields['university']}, {fields['uni_years']}\n{fields['degree']}, {fields['degree_class']}",
        "Modules": f"Modules: {fields['modules']}",
        "School": school,
        "A-levels": f"A-levels: {fields['alevels']}",
        "GCSEs": f"GCSEs: {fields['gcses']}",
        "Job1 heading": f"{fields['job1_title']}, {fields['job1_org']} ({fields['job1_dates']})",
        "Job1 bullets": "\n".join("- " + b for b in fields["job1_bullets"]),
        "Job2 heading": f"{fields['job2_title']}, {fields['job2_org']} ({fields['job2_dates']})",
        "Job2 bullets": "\n".join("- " + b for b in fields["job2_bullets"]),
        "Skills": fields["skills"],
        "Award": f"Awards: {fields['award']}",
        "Interests": fields["interests"],
        "Monitoring": form_text.strip() if form_text else "",
    }


def write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def build(folder, out_dir, pipeline_dir=None, quiet=False):
    bases, markers = load_sheets(folder)
    env = make_env(folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    if pipeline_dir is not None:
        pipeline_dir.mkdir(parents=True, exist_ok=True)

    rendered = {}   # base_id -> version -> {"fields", "cv", "form_fields", "form", ...}
    manifest, canva = [], []
    for base_id in sorted(bases):
        base, marker = bases[base_id], markers[base_id]
        rendered[base_id] = {}
        for version, spec in VERSIONS.items():
            fields = fields_for(base, marker, spec)
            cv_text = render_cv(env, fields)
            form_fields = form_fields_for(marker, spec, fields["name"])
            form_text = render_form(env, form_fields) if form_fields else ""

            cv_file = out_dir / f"{base_id}_{version}.txt"
            cv_file.write_text(cv_text, encoding="utf-8")
            form_file = None
            if form_text:
                form_file = out_dir / f"{base_id}_{version}_form.txt"
                form_file.write_text(form_text, encoding="utf-8")
            pipeline_file = None
            if pipeline_dir is not None:
                pipeline_file = pipeline_dir / f"{base_id}_{spec['arm']}_{spec['variant']}.txt"
                # The scoring pipeline takes one text per candidate, so the form is sent
                # after the CV as its own section (config.yaml allows the explicit arm to
                # differ only there).
                pipeline_file.write_text(cv_text + ("\n" + form_text if form_text else ""), encoding="utf-8")

            rendered[base_id][version] = {"fields": fields, "cv": cv_text, "form_fields": form_fields, "form": form_text}
            manifest.append({
                "base_id": base_id, "version": version, "arm": spec["arm"], "variant": spec["variant"],
                "cv_file": cv_file.name, "form_file": form_file.name if form_file else "",
                "pipeline_file": pipeline_file.name if pipeline_file else "",
                "name": fields["name"], "email": fields["email"], "school": fields["school"] or "(not named)",
                "award": fields["award"], "interests": fields["interests"],
                "parent_job": form_fields["parent_job"] if form_fields else "",
                "school_type": form_fields["school_type"] if form_fields else "",
                "free_school_meals": form_fields["fsm"] if form_fields else "",
            })
            canva.append(canva_row(base_id, version, fields, form_text))

    manifest_columns = ["base_id", "version", "arm", "variant", "cv_file", "form_file", "pipeline_file", "name",
                        "email", "school", "award", "interests", "parent_job", "school_type", "free_school_meals"]
    write_csv(out_dir / "manifest.csv", manifest, manifest_columns)
    write_csv(out_dir / "canva_bulk.csv", canva, ["base_id", "version"] + CANVA_COLUMNS)

    n_cv = len(bases) * len(VERSIONS)
    n_form = len(bases) * sum(1 for s in VERSIONS.values() if s["form"])
    if not quiet:
        print(f"{len(bases)} base CVs -> {n_cv} CV files and {n_form} form files in {out_dir}/, "
              f"plus manifest.csv and canva_bulk.csv")
        if pipeline_dir is not None:
            print(f"{n_cv} pipeline-format files in {pipeline_dir}/")
        print("Length of v1 vs v2:")
        print("\n".join(length_report(rendered)))
    problems = diff_check(env, rendered)
    if not quiet:
        if problems:
            print("Diff check: PROBLEMS")
            print("\n".join("  " + p for p in problems))
        else:
            print("Diff check: OK")
    return rendered, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render the six CV versions of every base CV.")
    parser.add_argument("--out", default=str(HERE / "out"), help="output folder (default: out/)")
    parser.add_argument("--pipeline-dir", default=str(PIPELINE_CV_DIR),
                        help="also write the CVs in the scoring pipeline's naming (default: ../cvs/)")
    parser.add_argument("--no-pipeline", action="store_true", help="don't write the pipeline-format copies")
    args = parser.parse_args(argv)
    try:
        _, problems = build(HERE, Path(args.out), None if args.no_pipeline else Path(args.pipeline_dir))
    except SheetError as e:
        sys.exit(f"Problem in the sheets: {e}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
