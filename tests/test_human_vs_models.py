"""People against the models: the per-CV join, the weighting and the class effect, on fake data."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "survey"))

import human_vs_models as hvm  # noqa: E402


def fake(tmp_path):
    people = [  # B01 seen in both versions, B02 only in its higher-class one
        ("F001", "01", "B01", "high", 1, 8, 1, "doctor"),
        ("F002", "02", "B01", "high", 0, 4, 1, "lawyer"),
        ("F003", "03", "B01", "low", 1, 6, 0, "builder"),
        ("F004", "04", "B02", "high", 1, 9, 1, "doctor"),
        ("F005", "04", "B02", "high", 1, 9, 1, "doctor"),
    ]
    humans = pd.DataFrame(people, columns=["participant_id", "card", "cv_id", "variant", "interview",
                                           "likelihood", "guess_private", "parents_guess"])
    humans["stimulus_id"] = humans["cv_id"] + "_implicit_" + humans["variant"]
    humans["card_matches_day"] = 1
    humans["timestamp"] = "15/10/2026 12:00:00"
    calls = []
    for model, high_rate, low_rate in [("anthropic/claude-opus-5.5", 0.2, 0.6), ("openai/gpt-6.1-sol-pro", 1.0, 1.0)]:
        for cv in ("B01", "B02"):
            for variant, rate in (("high", high_rate), ("low", low_rate)):
                for i in range(10):
                    calls.append({"model": model, "arm": "implicit", "ok": True, "cv_id": cv, "variant": variant,
                                  "stimulus_id": f"{cv}_implicit_{variant}", "shortlist": int(i < 10 * rate),
                                  "likelihood": 100 * rate})
    calls.append({"model": "openai/gpt-6.1-sol-pro", "arm": "explicit", "ok": True, "cv_id": "B01",
                  "variant": "high", "stimulus_id": "B01_explicit_high", "shortlist": 0, "likelihood": 0})
    humans.to_csv(tmp_path / "responses.csv", index=False)
    pd.DataFrame(calls).to_csv(tmp_path / "calls.csv", index=False)
    return hvm.load(tmp_path / "responses.csv", tmp_path / "calls.csv")


def test_per_cv_joins_each_seen_cv_to_its_implicit_calls(tmp_path):
    humans, models = fake(tmp_path)
    assert set(models["arm"]) == {"implicit"}
    table = per = hvm.per_cv(humans, models).set_index("stimulus_id")
    assert list(per.index) == ["B01_implicit_high", "B01_implicit_low", "B02_implicit_high"]
    assert table.loc["B01_implicit_high", "n_people"] == 2
    assert table.loc["B01_implicit_high", "people_interview"] == 0.5
    assert table.loc["B01_implicit_high", "people_likelihood"] == 60
    assert table.loc["B01_implicit_low", "Claude_shortlist"] == 0.6
    assert table.loc["B02_implicit_high", "GPT_likelihood"] == 100


def test_report_weights_by_people_and_holds_the_base_fixed(tmp_path):
    humans, models = fake(tmp_path)
    text = hvm.report(humans, models, hvm.per_cv(humans, models))
    # People: 4 of 5 interviewed; Claude on the same five views is 0.2 x 4 + 0.6 x 1 over 5
    assert "| People | 80% | 75% | 100% | 72.0 | 75.0 | 60.0 |" in text
    assert "| Claude | 28% | 20% | 60% |" in text
    # Only B01 has both versions: people 50% - 100%, Claude 20% - 60%; Claude over both bases is the same
    assert "| People | -50.0 | -50.0 |  |" in text
    assert "| Claude | -40.0 | -40.0 | -40.0 |" in text
    assert "1 for the lower-class one" in text
    assert "| higher-class version | 4 | 4 | 0 | 0 | 100% |" in text
    assert "possibly one person submitting twice: F004, F005" in text
