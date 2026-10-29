"""Verify every school in the stimulus set against the official DfE register.

    python verify_schools.py                 # download today's register, write the CSV
    python verify_schools.py --gias FILE     # use a register already downloaded

Writes schools_verification.csv: one row per school, carrying its URN, the name
and establishment type GIAS records, whether it is open, single-sex status, its
local authority, and how selective that authority is.

The source is Get Information about Schools, the DfE's statutory register:
https://get-information-schools.service.gov.uk
Every row's source_url points at that school's GIAS page, so each claim here can
be checked against the register rather than taken on trust.

Two things this settles that a web search does not:

1. "Is the school the type the CV implies?" -- GIAS states the establishment
   type, so an independent school playing a state role (or the reverse) is
   caught, as is a school that has closed.

2. "Does the pair sit in a selective area?" -- a non-selective state school in a
   county that runs the 11-plus is a secondary modern in practice, which is a
   stronger class signal than a comprehensive elsewhere. Rather than rely on a
   remembered list of grammar-school counties, the selective share is counted
   from the register: how many of an authority's open state-funded secondaries
   GIAS records as Selective. Grammar schools in the same *town* as the pair's
   state school are reported separately, since those are the ones that actually
   cream off its intake.

Candidate gender is inferred from the first name and used only to check the
single-sex schools. It is reported in its own column so the inference stays
visible rather than buried in a pass/fail.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(10 ** 7)

ROOT = Path(__file__).resolve().parent
GIAS_PAGE = "https://get-information-schools.service.gov.uk/Establishments/Establishment/Details/"
GIAS_DOWNLOAD = ("https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/"
                 "edubasealldata{date}.csv")

STATE_TYPES = {"Community school", "Foundation school", "Voluntary aided school",
               "Voluntary controlled school", "Academy converter", "Academy sponsor led",
               "Free schools", "Studio schools", "University technical college",
               "City technology college"}
INDEPENDENT_TYPES = {"Other independent school", "Other independent special school",
                     "Independent school", "Non-maintained special school"}
SECONDARY_PHASES = {"Secondary", "Middle deemed secondary", "All-through"}

# Where the name a candidate would write on a CV is not one open GIAS establishment.
PINNED_URNS = {
    ("B09", "high"): "105271",  # "Bolton School" is registered as two single-sex divisions
    ("B14", "low"): "141269",   # the pre-academy City of Norwich School record is Closed
}

# Only used to check the single-sex schools; see the module docstring.
MALE_NAMES = {"Hugo", "Connor", "Rupert", "Kieran", "Henry", "Callum", "Felix", "Jayden",
              "Oliver", "Jordan", "Arthur", "Liam", "Benedict", "Kyle"}
FEMALE_NAMES = {"Imogen", "Kayleigh", "Arabella", "Chelsea", "Clementine", "Jade",
                "Georgina", "Shannon", "Rosalind", "Courtney", "Harriet", "Jodie",
                "Octavia", "Chantelle", "Cressida", "Kelsey"}


def download_register(path: Path) -> Path:
    """Fetch the register, trying the last few days -- it is republished daily."""
    for back in range(0, 5):
        day = dt.date.today() - dt.timedelta(days=back)
        url = GIAS_DOWNLOAD.format(date=day.strftime("%Y%m%d"))
        try:
            with urllib.request.urlopen(url, timeout=180) as response:
                data = response.read()
        except Exception:
            continue
        if len(data) > 1_000_000:
            path.write_bytes(data)
            print(f"Downloaded the register for {day} ({len(data) // 1_000_000} MB)")
            return path
    raise SystemExit("could not download the GIAS register; pass --gias with a local copy")


def normalise(name: str) -> str:
    """A school name reduced to its distinctive words, for matching."""
    name = name.lower().replace("&", "and")
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\b(the|school|college|academy|an|a)\b", " ", name)
    return " ".join(name.split())


def selectivity_by_authority(register):
    """Per authority: how many open state-funded secondaries GIAS calls Selective.
    Also returns, per town, the selective schools in it."""
    authorities = defaultdict(lambda: {"selective": 0, "total": 0})
    by_town = defaultdict(list)
    for row in register:
        if row["EstablishmentStatus (name)"] != "Open":
            continue
        if row["TypeOfEstablishment (name)"] not in STATE_TYPES:
            continue
        if row["PhaseOfEducation (name)"] not in SECONDARY_PHASES:
            continue
        stats = authorities[row["LA (name)"]]
        stats["total"] += 1
        if row["AdmissionsPolicy (name)"] == "Selective":
            stats["selective"] += 1
            by_town[row["Town"].strip().lower()].append(row["EstablishmentName"])
    return authorities, by_town


def best_match(register, school, town, county):
    """The GIAS row most likely to be this school, preferring the same town and open status."""
    key = normalise(school)
    tokens = set(key.split())
    best, best_score = None, 0
    for row in register:
        candidate = normalise(row["EstablishmentName"])
        if not candidate:
            continue
        if candidate == key:
            score = 100
        elif key and (key in candidate or candidate in key):
            score = 80
        else:
            other = set(candidate.split())
            overlap = len(tokens & other) / max(len(tokens), len(other)) if tokens and other else 0
            score = int(60 * overlap) if overlap >= 0.6 else 0
        if not score:
            continue
        if row["Town"].strip().lower() == town.lower():
            score += 12
        if row["County (name)"].strip().lower() == county.lower():
            score += 6
        if row["EstablishmentStatus (name)"] == "Open":
            score += 8
        if score > best_score:
            best, best_score = row, score
    return best


def check(entry, gias, authorities, selective_towns, gender):
    """Everything that would make this row wrong. Empty list means it checks out."""
    problems = []
    etype = gias["TypeOfEstablishment (name)"]
    wants_independent = entry["variant"] == "high"
    is_independent = etype in INDEPENDENT_TYPES

    if gias["EstablishmentStatus (name)"] != "Open":
        problems.append(f"GIAS status is {gias['EstablishmentStatus (name)']}, not Open")
    if wants_independent and not is_independent:
        problems.append(f"plays the independent role but GIAS type is '{etype}'")
    if not wants_independent and is_independent:
        problems.append(f"plays the state role but GIAS type is '{etype}'")
    if not wants_independent and etype in STATE_TYPES \
            and gias["AdmissionsPolicy (name)"] == "Selective":
        problems.append("GIAS records this state school as Selective, so it is not non-selective")

    sex = gias["Gender (name)"]
    if sex in ("Boys", "Girls"):
        wanted = "male" if sex == "Boys" else "female"
        if gender != wanted:
            problems.append(f"single-sex ({sex}) but the pair's candidate reads {gender}")

    if normalise(gias["EstablishmentName"]) != normalise(entry["school"]):
        problems.append(f"CV writes '{entry['school']}'; "
                        f"GIAS name is '{gias['EstablishmentName']}'")

    if not wants_independent:
        local = selective_towns.get(entry["town"].lower(), [])
        if local:
            problems.append(f"{len(local)} selective school(s) in {entry['town']}: "
                            + "; ".join(local[:3]))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gias", help="a register CSV already downloaded")
    parser.add_argument("--out", default=str(ROOT / "schools_verification.csv"))
    args = parser.parse_args()

    gias_path = Path(args.gias) if args.gias else download_register(
        ROOT / "_gias_register.csv")
    with gias_path.open(encoding="latin-1", newline="") as fh:
        register = list(csv.DictReader(fh))
    by_urn = {row["URN"]: row for row in register}
    authorities, selective_towns = selectivity_by_authority(register)
    print(f"Register: {len(register)} establishments; "
          f"{sum(1 for a in authorities.values() if a['selective'])} authorities run selection")

    with (ROOT / "markers.csv").open(encoding="utf-8-sig", newline="") as fh:
        markers = list(csv.DictReader(fh))

    results = []
    for index in range(1, 16):
        base = f"B{index:02d}"
        high = next(m for m in markers if m["base_id"] == base and m["version"] == "v1")
        first = high["name"].split()[0]
        gender = "male" if first in MALE_NAMES else (
            "female" if first in FEMALE_NAMES else "UNKNOWN")

        for version, variant in [("v1", "high"), ("v2", "low")]:
            marker = next(m for m in markers
                          if m["base_id"] == base and m["version"] == version)
            parts = [p.strip() for p in marker["school"].split(",")]
            entry = {"base_id": base, "variant": variant, "school": parts[0],
                     "town": parts[1] if len(parts) > 2 else "", "county": parts[-1]}

            pin = PINNED_URNS.get((base, variant))
            gias = by_urn[pin] if pin else best_match(
                register, entry["school"], entry["town"], entry["county"])
            if gias is None:
                raise SystemExit(f"no GIAS match for {entry['school']} ({base} {variant})")

            authority = gias["LA (name)"]
            stats = authorities.get(authority, {"selective": 0, "total": 0})
            share = (stats["selective"] / stats["total"] * 100) if stats["total"] else 0.0
            problems = check(entry, gias, authorities, selective_towns, gender)

            results.append({
                **entry,
                "candidate_name": marker["name"],
                "candidate_gender_inferred": gender,
                "expected_role": "Independent" if variant == "high"
                                 else "State-funded, non-selective",
                "urn": gias["URN"],
                "gias_name": gias["EstablishmentName"],
                "establishment_type": gias["TypeOfEstablishment (name)"],
                "gias_status": gias["EstablishmentStatus (name)"],
                "phase": gias["PhaseOfEducation (name)"],
                "admissions_policy": gias["AdmissionsPolicy (name)"],
                "single_sex": gias["Gender (name)"],
                "local_authority": authority,
                "la_selective": "yes" if stats["selective"] else "no",
                "la_selective_schools": stats["selective"],
                "la_state_secondaries": stats["total"],
                "la_selective_share_pct": f"{share:.1f}",
                "verified": "GIAS" if not problems else "GIAS-FLAGGED",
                "source_url": GIAS_PAGE + gias["URN"],
                "notes": " | ".join(problems),
            })

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    flagged = [r for r in results if r["verified"] == "GIAS-FLAGGED"]
    print(f"Wrote {out_path.name}: {len(results)} schools, "
          f"{len(results) - len(flagged)} clean, {len(flagged)} flagged")
    for row in flagged:
        print(f"  {row['base_id']} {row['variant']}: {row['notes']}")


if __name__ == "__main__":
    main()
