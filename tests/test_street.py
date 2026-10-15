"""The street check's export-to-CSV step, on a fake responses export."""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "survey"))

import street_responses as street  # noqa: E402


def fake_export(path, n_per_card=2):
    header = ["Timestamp", "Interviewer", "Location", "Card", "Would you give this person an interview?",
              "Private school or state school?", "How likely are they to be invited, 0 to 100? (optional)"]
    key = street.load_key()
    rows = []
    for card, info in sorted(key.items()):
        for k in range(n_per_card):
            high = info["variant"] == "high"
            rows.append(["15/10/2026 12:00:00", "LP" if k else "AB", "library", card,
                         "Yes" if high else "No", "Private" if high else "State", "80" if high else ""])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_tidy_joins_cards_and_summarises(tmp_path, capsys):
    export = fake_export(tmp_path / "export.csv")
    rows = street.tidy(export)
    assert len(rows) == 60 and {r["variant"] for r in rows} == {"high", "low"}
    assert all(r["interview"] == (1 if r["variant"] == "high" else 0) for r in rows)
    assert all(r["guess_private"] == (1 if r["variant"] == "high" else 0) for r in rows)
    assert {r["likelihood"] for r in rows if r["variant"] == "high"} == {80}
    assert all(r["likelihood"] == "" for r in rows if r["variant"] == "low")
    text = street.summary(rows)
    assert "60 answers from 2 interviewer(s)" in text and "30 of 30 cards seen" in text
    assert "interviewed more on 15, less on 0" in text
    assert "private-school guesses 100% for the higher-class version vs 0%" in text


def test_a_card_outside_the_key_is_refused(tmp_path):
    export = fake_export(tmp_path / "export.csv", n_per_card=1)
    text = export.read_text(encoding="utf-8").replace(",01,", ",99,", 1)
    export.write_text(text, encoding="utf-8")
    try:
        street.tidy(export)
    except SystemExit as e:
        assert "card '99'" in str(e)
    else:
        raise AssertionError("a card outside the key should stop the run")
