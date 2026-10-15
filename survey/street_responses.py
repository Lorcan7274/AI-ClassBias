"""The street check's answers:  python survey/street_responses.py <export.csv>

Reads the responses sheet exported as CSV (File > Download > CSV in Google Sheets),
joins each card to its CV through survey/cards/card_key.csv, writes
survey/street_responses.csv with one row per answer, and prints the summary:
how many answers, the interview rate and the private-school guesses for each
version, the manipulation check, and a sign test across bases.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEY = ROOT / "cards" / "card_key.csv"
OUT = ROOT / "street_responses.csv"

# Each form column is found by the start of its header, so a reworded question
# still matches as long as it starts the same way.
COLUMNS = {"timestamp": "Timestamp", "interviewer": "Interviewer", "location": "Location", "card": "Card",
           "interview": "Would you give this person an interview", "school": "Private school or state school",
           "likelihood": "How likely"}


def find_columns(header: list[str]) -> dict[str, str]:
    found = {}
    for key, start in COLUMNS.items():
        matches = [h for h in header if h.strip().lower().startswith(start.lower())]
        if not matches and key != "likelihood":
            sys.exit(f"no column starting with {start!r} in the export; columns are {header}")
        if matches:
            found[key] = matches[0]
    return found


def load_key() -> dict[str, dict]:
    with open(KEY, encoding="utf-8") as f:
        return {row["card"]: row for row in csv.DictReader(f)}


def tidy(export: Path) -> list[dict]:
    key = load_key()
    with open(export, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = find_columns(reader.fieldnames or [])
        rows = []
        for i, raw in enumerate(reader, 1):
            card = str(raw[cols["card"]]).strip().zfill(2)
            if card not in key:
                sys.exit(f"row {i}: card {card!r} is not in {KEY}")
            answer = raw[cols["interview"]].strip().lower()
            school = raw[cols["school"]].strip().lower()
            likelihood = raw.get(cols.get("likelihood", ""), "").strip() if "likelihood" in cols else ""
            rows.append({
                "participant_id": f"S{i:03d}", "timestamp": raw[cols["timestamp"]],
                "interviewer": raw[cols["interviewer"]].strip(), "location": raw[cols["location"]].strip(),
                "card": card, "stimulus_id": key[card]["stimulus_id"], "cv_id": key[card]["cv_id"],
                "arm": key[card]["arm"], "variant": key[card]["variant"],
                "interview": 1 if answer.startswith("y") else 0,
                "guess_private": 1 if school.startswith("private") else (0 if school.startswith("state") else ""),
                "likelihood": int(float(likelihood)) if likelihood else "",
            })
    return rows


def summary(rows: list[dict]) -> str:
    from pipeline.stats import sign_test  # the same exact test the model analysis uses

    def rate(items, field):
        vals = [r[field] for r in items if r[field] != ""]
        return (sum(vals) / len(vals), len(vals)) if vals else (float("nan"), 0)

    lines = [f"{len(rows)} answers from {len({r['interviewer'] for r in rows})} interviewer(s) at "
             f"{len({r['location'] for r in rows})} location(s); {len({r['card'] for r in rows})} of 30 cards seen"]
    by_variant = defaultdict(list)
    for r in rows:
        by_variant[r["variant"]].append(r)
    for variant in ("high", "low"):
        g = by_variant.get(variant, [])
        inter, n = rate(g, "interview")
        priv, n_priv = rate(g, "guess_private")
        like, n_like = rate(g, "likelihood")
        lines.append(f"  {variant:>4}-class version: {len(g)} answers; interview {inter:.0%}; "
                     f"guessed private {priv:.0%} of {n_priv} who guessed; mean likelihood "
                     f"{like:.0f} over {n_like}")
    # Per base: the higher-class version's interview rate minus the lower-class one's.
    per_base = defaultdict(dict)
    for variant, g in by_variant.items():
        by_cv = defaultdict(list)
        for r in g:
            by_cv[r["cv_id"]].append(r["interview"])
        for cv, vals in by_cv.items():
            per_base[cv][variant] = sum(vals) / len(vals)
    diffs = [d["high"] - d["low"] for d in per_base.values() if "high" in d and "low" in d]
    if diffs:
        s = sign_test(diffs)
        lines.append(f"  bases with both versions seen: {len(diffs)}; higher-class version interviewed more on "
                     f"{s['pos']}, less on {s['neg']}, tied on {s['ties']}; sign test p = {s['p']:.2f}")
    priv_high, _ = rate(by_variant.get("high", []), "guess_private")
    priv_low, _ = rate(by_variant.get("low", []), "guess_private")
    lines.append(f"  manipulation check: private-school guesses {priv_high:.0%} for the higher-class version "
                 f"vs {priv_low:.0%} for the lower-class one")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    sys.path.insert(0, str(ROOT.parent))
    rows = tidy(Path(argv[1]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT}\n" + summary(rows))


if __name__ == "__main__":
    main(sys.argv)
