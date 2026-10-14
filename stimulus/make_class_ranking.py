"""Generate class_ranking.csv from markers.csv.

    python make_class_ranking.py              # write class_ranking.csv
    python make_class_ranking.py --check      # fail if the committed file is stale

One row per distinct marker value, so the class level assigned to every
descriptor in the stimulus set -- and the reason for it -- can be read off a
single sheet:

    marker_type, value, class_level, nssec_class, justification

`class_level` is read from the version the value appears in: v1 is the
higher-class variant, v2 the lower-class one, and v3 to v6 carry the neutral
values the class arms are stripped down to. `nssec_class` is filled in for
parent_job rows only.

The justifications live in the dicts below rather than in a hand-written CSV,
so the reasoning is reviewable in the same place as the coding. School rows take
theirs from schools_verification.csv, so each one cites the establishment type
the DfE register records and the school's URN rather than an assertion.

Scope: the six marker types the brief defines. The monitoring form's own answers
(school_type, free_school_meals) are the explicit arm's instrument rather than
descriptors in this taxonomy -- their class level is carried by parent_job -- and
email and phone are derived from the name or constant, so none of them appear here.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MARKER_TYPES = ["school", "first_name", "surname", "interests", "award", "parent_job"]

# v1 is the higher-class variant of a pair, v2 the lower; v3-v6 hold neutral values.
# parent_job is the exception: it only exists on v3/v4, where v3 is the high answer.
LEVEL_BY_VERSION = {"v1": "high", "v2": "low", "v3": "neutral",
                    "v4": "neutral", "v5": "neutral", "v6": "neutral"}
PARENT_JOB_LEVEL = {"v3": "high", "v4": "low"}

# ---------------------------------------------------------------- parent_job

# The brief drew the high answers from NS-SEC analytic class 1 and the low ones
# from classes 6 and 7. Each low job is classified on its own: "semi-routine"
# (class 6) and "routine" (class 7) are different classes, so flattening them all
# to 7 would misstate the design.
NSSEC = {
    # class 1 -- higher managerial, administrative and professional
    "Solicitor": (1, "NS-SEC 1, higher professional occupation"),
    "General practitioner (GP)": (1, "NS-SEC 1, higher professional occupation"),
    "Chartered accountant": (1, "NS-SEC 1, higher professional occupation"),
    "Architect": (1, "NS-SEC 1, higher professional occupation"),
    "Dentist": (1, "NS-SEC 1, higher professional occupation"),
    "Consultant surgeon": (1, "NS-SEC 1, higher professional occupation"),
    "Actuary": (1, "NS-SEC 1, higher professional occupation"),
    "University lecturer": (1, "NS-SEC 1, higher education teaching professional"),
    "Secondary school head teacher": (1, "NS-SEC 1, higher managerial occupation in education"),
    # class 6 -- semi-routine
    "Care assistant (care home)": (6, "NS-SEC 6, semi-routine personal service occupation"),
    "Supermarket cashier": (6, "NS-SEC 6, semi-routine sales occupation"),
    "Security guard": (6, "NS-SEC 6, semi-routine service occupation"),
    "Kitchen assistant": (6, "NS-SEC 6, semi-routine service occupation"),
    "Catering assistant": (6, "NS-SEC 6, semi-routine service occupation"),
    # class 7 -- routine
    "Warehouse operative": (7, "NS-SEC 7, routine operative occupation"),
    "Packer": (7, "NS-SEC 7, routine operative occupation"),
    "Labourer": (7, "NS-SEC 7, routine manual occupation"),
    "Cleaner": (7, "NS-SEC 7, routine manual occupation"),
    "Hospital porter": (7, "NS-SEC 7, routine service occupation"),
    "Bus driver": (7, "NS-SEC 7, routine transport operative"),
    "Delivery driver": (7, "NS-SEC 7, routine transport operative"),
}

# -------------------------------------------------------------------- awards

AWARDS = {
    # Status awards held through the school, carrying no attainment claim.
    "Head of House": "school office, awarded through the institution rather than on attainment",
    "Senior Prefect": "school office, awarded through the institution rather than on attainment",
    "School Scholar (academic scholarship)":
        "merit scholarship at a fee-paying school, signals selective private entry",
    "Sixth Form Academic Scholarship":
        "merit scholarship at a fee-paying school, signals selective private entry",
    # Retained to document the exclusion rule, not used by any base: a subject-specific
    # prize claims a competence beyond the identical qualifications. See REVIEW.md.
    "School Prize for Mathematics":
        "EXCLUDED: subject-specific prize, claims a competence beyond the identical "
        "qualifications",
    # Need-based or widening-participation awards, which mark low family income.
    "16 to 19 Bursary Fund recipient":
        "need-based state bursary, eligibility requires low household income",
    "Sixth-form bursary award": "need-based award, eligibility requires low household income",
    "Sutton Trust UK Summer School participant":
        "widening-participation programme, selects on low-SES background",
    "Realising Opportunities participant":
        "widening-participation programme, selects on low-SES background",
    "Social Mobility Foundation Aspiring Professionals Programme":
        "widening-participation programme, selects on low-SES background",
}
NEUTRAL_AWARD = "university-level academic award, carries no school or income signal"

# ----------------------------------------------------------------- interests

# Activities whose cost, facilities or club structure make them class-coded.
INTEREST_CODES = {
    "high": {
        "rowing": "rowing, requires club or school boathouse",
        "sailing": "sailing, high equipment and club cost",
        "skiing": "skiing, depends on paid foreign travel",
        "lacrosse": "lacrosse, rarely offered outside independent schools",
        "fencing": "fencing, rarely offered outside independent schools",
        "riding": "riding, high cost of access to horses",
        "eventing": "eventing, high cost of access to horses",
        "polo": "polo, high cost of access to horses",
        "choral singing": "choral singing, usually through a school or cathedral choir",
        "chamber orchestra": "orchestral playing, presupposes sustained paid tuition",
        "grade 8": "graded music to Grade 8, presupposes years of paid tuition",
        "grade 7": "graded music to Grade 7, presupposes years of paid tuition",
        "hockey": "hockey, club and pitch access skewed to independent schools",
        "tennis": "tennis, club membership cost",
        "debating": "competitive debating, organised mainly through selective schools",
    },
    "low": {
        "five-a-side football": "five-a-side football, low-cost mass-participation sport",
        "football": "football, low-cost mass-participation sport",
        "going to the match": "watching football live, a mass-participation leisure marker",
        "boxing": "boxing, typically through a community or council gym",
        "darts": "darts, pub and club leisure marker",
        "fishing": "fishing, low-cost outdoor leisure",
        "bmx": "BMX, low-cost and self-organised",
        "gaming": "gaming, home-based and low-cost",
        "guitar (self-taught)": "self-taught instrument, explicitly no paid tuition",
        "snooker": "snooker, club and pub leisure marker",
    },
}
NEUTRAL_INTEREST = ("low-cost, widely available activities chosen to carry "
                    "no class signal either way")

# --------------------------------------------------------------------- names

# The least externally grounded of the markers: these are chosen for their
# class connotation in British usage, not validated against a name-SES dataset.
# That limitation is stated in the justification rather than hidden behind it.
NAME_REASONS = {
    ("first_name", "high"): "given name chosen for upper-middle-class connotation in "
                            "British usage; not validated against a name-SES dataset",
    ("first_name", "low"): "given name chosen for working-class connotation in "
                           "British usage; not validated against a name-SES dataset",
    ("first_name", "neutral"): "given name used in the neutral and demographic arms, "
                               "chosen to carry no class signal",
    ("surname", "high"): "surname chosen for upper-middle-class connotation in "
                         "British usage; not validated against a name-SES dataset",
    ("surname", "low"): "very common British surname, coded low by its absence of elite "
                        "connotation; not validated against a name-SES dataset",
    ("surname", "neutral"): "surname used in the neutral and demographic arms, "
                            "chosen to carry no class signal",
}
DOUBLE_BARRELLED = ("double-barrelled surname, a conventional marker of inherited "
                    "status in British usage; not validated against a name-SES dataset")

NEUTRAL_SCHOOL_VALUE = "(not named)"


def school_justifications():
    """School reasons taken from the DfE register, via schools_verification.csv."""
    path = ROOT / "schools_verification.csv"
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            full = row["school"]
            if row["town"]:
                full = f"{full}, {row['town']}, {row['county']}"
            else:
                full = f"{full}, {row['county']}"
            if row["variant"] == "high":
                reason = (f"fee-paying independent school "
                          f"(GIAS: {row['establishment_type']}, URN {row['urn']})")
            else:
                reason = (f"non-selective state school "
                          f"(GIAS: {row['establishment_type']}, URN {row['urn']}; "
                          f"{row['local_authority']} runs selection: {row['la_selective']})")
            out[full] = reason
    return out


def interest_reason(value, level):
    """Compose a reason from the class-coded activities actually present."""
    if level == "neutral":
        return NEUTRAL_INTEREST
    low = value.lower()
    hits = [reason for token, reason in INTEREST_CODES[level].items() if token in low]
    if not hits:
        return (f"{level}-class coded activity set; no individually coded activity "
                "matched, review this row")
    return "; ".join(hits[:2])


def rows_from_markers(markers):
    """One record per (marker_type, value), with its level and justification."""
    schools = school_justifications()
    seen, out = {}, []

    def add(marker_type, value, level, justification, nssec=""):
        if not value:
            return
        key = (marker_type, value)
        if key in seen:
            if seen[key] != level:
                raise SystemExit(f"{marker_type} {value!r} appears as both "
                                 f"{seen[key]} and {level}")
            return
        seen[key] = level
        out.append({"marker_type": marker_type, "value": value, "class_level": level,
                    "nssec_class": nssec, "justification": justification})

    for marker in markers:
        level = LEVEL_BY_VERSION[marker["version"]]

        first, *rest = marker["name"].split()
        surname = " ".join(rest)
        add("first_name", first, level, NAME_REASONS[("first_name", level)])
        add("surname", surname, level,
            DOUBLE_BARRELLED if ("-" in surname and level == "high")
            else NAME_REASONS[("surname", level)])

        school = marker["school"]
        if school == NEUTRAL_SCHOOL_VALUE:
            add("school", school, "neutral",
                "school deliberately not named, so the CV carries no school signal")
        else:
            add("school", school, level,
                schools.get(school, "school not found in schools_verification.csv, "
                                    "re-run verify_schools.py"))

        award = marker["award"]
        add("award", award, level,
            NEUTRAL_AWARD if level == "neutral"
            else AWARDS.get(award, "award not classified, add it to AWARDS"))

        add("interests", marker["interests"], level,
            interest_reason(marker["interests"], level))

        job = marker["parent_job"]
        if job:
            job_level = PARENT_JOB_LEVEL[marker["version"]]
            nssec, reason = NSSEC.get(job, ("", "job not classified, add it to NSSEC"))
            add("parent_job", job, job_level, reason, str(nssec))

    order = {name: i for i, name in enumerate(MARKER_TYPES)}
    level_order = {"high": 0, "low": 1, "neutral": 2}
    out.sort(key=lambda r: (order[r["marker_type"]],
                            level_order[r["class_level"]], r["value"]))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "class_ranking.csv"))
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the file on disk is not what this would write")
    args = parser.parse_args()

    with (ROOT / "markers.csv").open(encoding="utf-8-sig", newline="") as fh:
        markers = list(csv.DictReader(fh))
    records = rows_from_markers(markers)

    import io
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["marker_type", "value", "class_level",
                                                "nssec_class", "justification"],
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    text = buffer.getvalue()

    out_path = Path(args.out)
    if args.check:
        current = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        if current != text:
            print(f"{out_path.name} is out of date; run make_class_ranking.py",
                  file=sys.stderr)
            raise SystemExit(1)
        print(f"{out_path.name} is up to date ({len(records)} rows)")
        return

    out_path.write_text(text, encoding="utf-8")
    counts = {}
    for record in records:
        counts[record["marker_type"]] = counts.get(record["marker_type"], 0) + 1
    detail = ", ".join(f"{counts[m]} {m}" for m in MARKER_TYPES if m in counts)
    print(f"Wrote {out_path.name}: {len(records)} rows ({detail})")

    unclassified = [r for r in records if "add it to" in r["justification"]
                    or "review this row" in r["justification"]
                    or "re-run" in r["justification"]]
    if unclassified:
        print(f"\n{len(unclassified)} row(s) need attention:", file=sys.stderr)
        for record in unclassified:
            print(f"  {record['marker_type']}: {record['value']!r}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
