"""The CV check's answers:  python survey/form_responses.py <export.csv>

Reads the responses sheet exported as CSV (File > Download > CSV in Google
Sheets). The form has one block of four questions per card, so the sheet has
thirty blocks of identical headers in card order and each response fills one of
them. This joins each response to its card and CV (survey/cards/card_key.csv),
writes survey/form_responses.csv with one row per response, and prints the
summary: interview rate, mean likelihood and private-school guesses for each
version, the manipulation check, and a sign test across bases.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEY = ROOT / "cards" / "card_key.csv"
OUT = ROOT / "form_responses.csv"

# A column is matched by the start of its header, so rewording a question is fine
# as long as it starts the same way.
BLOCK = {"interview": "Would you invite", "likelihood": "How likely", "school": "What kind of school",
         "parents": "What do you think their parents"}
DAY = "What day of the month"


def load_key() -> dict[str, dict]:
    with open(KEY, encoding="utf-8") as f:
        return {row["card"]: row for row in csv.DictReader(f)}


def columns(header: list[str]) -> tuple[int, dict[str, list[int]]]:
    """The day column, and for each question the indexes of its thirty columns in order."""
    day = [i for i, h in enumerate(header) if h.strip().lower().startswith(DAY.lower())]
    if not day:
        sys.exit(f"no column starting with {DAY!r} in the export; columns are {header}")
    blocks = {}
    for key, start in BLOCK.items():
        blocks[key] = [i for i, h in enumerate(header) if h.strip().lower().startswith(start.lower())]
        if not blocks[key]:
            sys.exit(f"no column starting with {start!r} in the export")
    n = len(blocks["interview"])
    if any(len(v) != n for v in blocks.values()):
        sys.exit(f"the question blocks are uneven: {{k: len(v) for k, v in blocks.items()}}")
    return day[0], blocks


def tidy(export: Path) -> list[dict]:
    key = load_key()
    with open(export, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        day_col, blocks = columns(header)
        n_blocks = len(blocks["interview"])
        rows = []
        for i, raw in enumerate(reader, 1):
            raw = raw + [""] * (len(header) - len(raw))
            filled = [k for k in range(n_blocks) if raw[blocks["interview"][k]].strip()]
            if len(filled) != 1:
                print(f"row {i}: {len(filled)} blocks answered, skipped")
                continue
            k = filled[0]
            card = f"{k + 1:02d}"
            if card not in key:
                sys.exit(f"row {i}: block {k + 1} has no card in {KEY}")
            day = raw[day_col].strip()
            expected = f"{(int(day) - 1) % n_blocks + 1:02d}" if day.isdigit() else ""
            answer = raw[blocks["interview"][k]].strip().lower()
            school = raw[blocks["school"][k]].strip().lower()
            likelihood = raw[blocks["likelihood"][k]].strip()
            rows.append({
                "participant_id": f"F{i:03d}", "timestamp": raw[0], "day_of_month": day,
                "card": card, "card_matches_day": int(card == expected) if expected else "",
                "stimulus_id": key[card]["stimulus_id"], "cv_id": key[card]["cv_id"],
                "arm": key[card]["arm"], "variant": key[card]["variant"],
                "interview": 1 if answer.startswith("y") else 0,
                "likelihood": int(float(likelihood)) if likelihood else "",
                "guess_private": 1 if school.startswith("private") else (0 if school.startswith("state") else ""),
                "parents_guess": raw[blocks["parents"][k]].strip(),
            })
    return rows


def summary(rows: list[dict]) -> str:
    sys.path.insert(0, str(ROOT.parent))
    from pipeline.stats import sign_test  # the same exact test the model analysis uses

    def rate(items, field):
        vals = [r[field] for r in items if r[field] != ""]
        return (sum(vals) / len(vals), len(vals)) if vals else (float("nan"), 0)

    lines = [f"{len(rows)} responses; {len({r['card'] for r in rows})} of 30 cards seen; "
             f"{sum(1 for r in rows if r['card_matches_day'] == 1)} of {sum(1 for r in rows if r['card_matches_day'] != '')} "
             "cards match the day given"]
    by_variant = defaultdict(list)
    for r in rows:
        by_variant[r["variant"]].append(r)
    for variant in ("high", "low"):
        g = by_variant.get(variant, [])
        inter, _ = rate(g, "interview")
        like, _ = rate(g, "likelihood")
        priv, n_priv = rate(g, "guess_private")
        lines.append(f"  {variant:>4}-class version: {len(g)} responses; interview {inter:.0%}; "
                     f"mean likelihood {like:.1f}/10; guessed private {priv:.0%} of the {n_priv} who guessed")
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
    rows = tidy(Path(argv[1]))
    if not rows:
        sys.exit("no usable responses")
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT}\n" + summary(rows))


if __name__ == "__main__":
    main(sys.argv)
