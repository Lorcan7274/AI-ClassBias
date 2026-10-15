"""The CV check's export-to-CSV step, on a fake responses export with thirty blocks."""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "survey"))

import form_responses as form  # noqa: E402

QUESTIONS = ["Would you invite this person to interview?", "How likely is it that this person gets an interview?",
             "What kind of school do you think they went to?",
             "What do you think their parents do for a living?"]


def fake_export(path, per_card=2):
    header = ["Timestamp", "What day of the month were you born on?"] + QUESTIONS * 30
    key = form.load_key()
    rows = []
    for card, info in sorted(key.items()):
        k = int(card) - 1
        for rep in range(per_card):
            high = info["variant"] == "high"
            row = ["15/10/2026 12:00:00", str(k + 1 + 30 * (rep % 1))] + [""] * (4 * 30)
            row[2 + 4 * k:6 + 4 * k] = ["Yes" if high else "No", "8" if high else "3",
                                        "Private (fee-paying)" if high else "State", "doctor" if high else ""]
            rows.append(row)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_tidy_finds_the_answered_block_and_summarises(tmp_path):
    rows = form.tidy(fake_export(tmp_path / "export.csv"))
    assert len(rows) == 60 and {r["variant"] for r in rows} == {"high", "low"}
    assert all(r["interview"] == (1 if r["variant"] == "high" else 0) for r in rows)
    assert all(r["likelihood"] == (8 if r["variant"] == "high" else 3) for r in rows)
    assert all(r["guess_private"] == (1 if r["variant"] == "high" else 0) for r in rows)
    assert all(r["card_matches_day"] == 1 for r in rows)
    text = form.summary(rows)
    assert "60 responses; 30 of 30 cards seen; 60 of 60 cards match" in text
    assert "interviewed more on 15, less on 0" in text
    assert "private-school guesses 100% for the higher-class version vs 0%" in text


def test_a_row_with_no_block_answered_is_skipped(tmp_path, capsys):
    path = fake_export(tmp_path / "export.csv", per_card=1)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    lines.append("15/10/2026 12:00:00,7" + "," * 120)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = form.tidy(path)
    assert len(rows) == 30
    assert "0 blocks answered, skipped" in capsys.readouterr().out
