"""The analysis, on small synthetic data with a known answer."""

import json

import numpy as np
import pandas as pd
import pytest

from pipeline import analysis, stats
from pipeline.runner import results_file


def make_rows(project, pick_high_prob, sessions=("day1", "day2"), reps=2, models=None, position_pull=0.0, seed=0):
    """Fake successful rows: the higher-class CV (x) is picked with probability
    pick_high_prob[arm], plus an optional pull towards Candidate 1."""
    rng = np.random.default_rng(seed)
    rows = []
    for model in models or [m.id for m in project.models]:
        for cv in range(1, 4):
            for arm, (x, y) in project.arms.items():
                for session in sessions:
                    for order in ("xy", "yx"):
                        for rep in range(1, reps + 1):
                            first, second = (x, y) if order == "xy" else (y, x)
                            p = pick_high_prob[arm] + (position_pull if first == x else -position_pull)
                            picked = x if rng.random() < p else y
                            x_rating = rng.integers(6, 10)
                            y_rating = rng.integers(3, 6)  # always below x_rating
                            rows.append({
                                "ok": True, "dry_run": False, "session": session, "model": model, "pair_id": f"cv0{cv}_{arm}",
                                "cv_id": f"cv0{cv}", "arm": arm, "order": order, "rep": rep, "pos1_variant": first,
                                "pos2_variant": second, "prompt_hash": "abc", "preferred_position": 1 if picked == first else 2,
                                "preferred_variant": picked,
                                "pos1_rating": int(x_rating if first == x else y_rating),
                                "pos2_rating": int(x_rating if second == x else y_rating),
                                "pos1_shortlist": True if first == x else bool(rng.random() < 0.5),
                                "pos2_shortlist": True if second == x else bool(rng.random() < 0.5),
                                # "experience" is a keyword, so the y reason avoids every keyword on purpose
                                "pos1_reason": "Strong school and university background" if first == x else "Solid overall",
                                "pos2_reason": "Strong school and university background" if second == x else "Solid overall",
                            })
    return rows


def write_rows(project, rows, dry_run=False):
    path = results_file(project.output_dir(dry_run))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def test_prepare_maps_positions_back_to_variants(project):
    rows = make_rows(project, {"implicit": 1.0, "explicit": 1.0, "demographic": 1.0}, reps=1)
    df = analysis.prepare(project, rows, dry_run=False)
    assert (df["picked_x"] == 1).all()
    assert (df["x_rating"] >= 6).all() and (df["y_rating"] <= 5).all()
    assert (df["rating_diff"] > 0).all()
    assert df["x_first"].mean() == 0.5  # both orders equally often
    assert ((df["picked_first"] == 1) == (df["x_first"] == 1)).all()
    assert (df["x_reason"] == "Strong school and university background").all()


def test_h1_finds_a_real_class_effect_and_not_a_null_one(project):
    rows = make_rows(project, {"implicit": 0.95, "explicit": 0.5, "demographic": 0.5}, reps=5, seed=1)
    df = analysis.prepare(project, rows, dry_run=False)
    h1 = analysis.h1_table(df)
    imp = h1[h1["arm"] == "implicit"]
    assert (imp["ci_low"] > 0.5).all() and (imp["p_vs_50"] < 0.05).all()
    assert (imp["n_cvs"] == 3).all() and (imp["n_calls"] == 60).all()
    null = h1[h1["arm"] == "explicit"]
    assert ((null["ci_low"] < 0.5) & (null["ci_high"] > 0.5)).all()
    # The clustered interval is never narrower than a naive one would suggest is impossible.
    assert (imp["ci_high"] <= 1).all() and (imp["ci_low"] >= 0).all()


def test_h2_odds_ratio_is_below_one_when_the_explicit_effect_is_smaller(project):
    rows = make_rows(project, {"implicit": 0.9, "explicit": 0.55, "demographic": 0.5}, reps=5, seed=2)
    h2 = analysis.h2_table(project, analysis.prepare(project, rows, dry_run=False))
    assert (h2["odds_ratio_explicit_vs_implicit"] < 1).all()
    assert (h2["ci_high"] < 1).all() and (h2["p"] < 0.05).all()
    assert (h2["cv_level_mean_diff_implicit_minus_explicit"] > 0).all()
    assert (h2["n_cvs_paired"] == 3).all()


def test_position_bias_is_detected_and_the_class_effect_survives_adjustment(project):
    rows = make_rows(project, {"implicit": 0.7, "explicit": 0.7, "demographic": 0.7}, reps=8, position_pull=0.25, seed=3)
    pos = analysis.position_table(analysis.prepare(project, rows, dry_run=False))
    overall = pos[pos["arm"] == "(all arms)"]
    assert (overall["pick_position1_rate"] > 0.6).all()
    by_arm = pos[pos["arm"] != "(all arms)"]
    assert (by_arm["pick_x_when_first"] > by_arm["pick_x_when_second"]).all()
    assert (by_arm["position_odds_ratio"] > 1).all()
    assert (by_arm["adjusted_pick_x_rate"] > 0.55).all()


def test_consistency_and_sessions_tables(project):
    rows = make_rows(project, {"implicit": 1.0, "explicit": 0.5, "demographic": 1.0}, reps=3, seed=4)
    df = analysis.prepare(project, rows, dry_run=False)
    cons = analysis.consistency_table(df)
    assert (cons.loc[cons["arm"] == "implicit", "agreement_with_majority"] == 1.0).all()
    assert (cons.loc[cons["arm"] == "implicit", "order_gap"] == 0.0).all()
    assert (cons["n_calls"] == 12).all()  # 2 sessions x 2 orders x 3 reps
    sess = analysis.sessions_table(df)
    assert set(sess["session_1"]) == {"day1"} and set(sess["session_2"]) == {"day2"}
    assert (sess.loc[sess["arm"] == "implicit", "mean_abs_change_per_pair"] == 0.0).all()
    assert analysis.sessions_table(df[df["session"] == "day1"]).empty


def test_ratings_and_reasons_tables(project):
    rows = make_rows(project, {"implicit": 0.5, "explicit": 0.5, "demographic": 0.5}, reps=2, seed=5)
    df = analysis.prepare(project, rows, dry_run=False)
    rat = analysis.ratings_table(df)
    assert (rat["mean_rating_diff"] > 0).all() and (rat["rating_ci_low"] > 0).all()
    assert (rat["shortlist_x_rate"] == 1.0).all()
    reas = analysis.reasons_table(project, df)
    any_rows = reas[reas["keyword"] == "(any keyword)"]
    assert (any_rows["x_pct"] == 100.0).all() and (any_rows["y_pct"] == 0.0).all()
    school = reas[reas["keyword"] == "school*"]
    assert (school["x_mentions"] == school["n_reasons"]).all()


def test_keyword_patterns_match_whole_words_and_wildcards():
    assert analysis.keyword_pattern("school*").search("Good schooling") is not None
    assert analysis.keyword_pattern("school").search("Good schooling") is None
    assert analysis.keyword_pattern("a-level*").search("Strong A-Levels") is not None
    assert analysis.keyword_pattern("free school meals").search("had free school meals") is not None


def test_stats_helpers_handle_degenerate_data():
    assert stats.clustered_rate([], [])["n"] == 0
    r = stats.clustered_rate([1, 1, 1], ["a", "b", "c"])
    assert r["rate"] == 1.0 and np.isnan(r["low"]) and r["note"]
    assert stats.clustered_odds_ratio([1, 0, 1, 0], [1, 1, 1, 1], ["a", "b", "c", "d"])["note"]
    assert stats.clustered_mean([2, 2, 2], ["a", "b", "c"])["note"] == "no variation"
    assert np.isnan(stats.cv_level([0.5, 0.5])["t_p"]) and np.isnan(stats.cv_level([0.5, 0.5])["wilcoxon_p"])


def test_analyze_writes_every_output(project, capsys):
    write_rows(project, make_rows(project, {"implicit": 0.8, "explicit": 0.6, "demographic": 0.5}, reps=3, seed=6)
               + [{"ok": False, "dry_run": False, "session": "day1", "model": "m", "pair_id": "cv01_implicit",
                   "cv_id": "cv01", "arm": "implicit", "order": "xy", "rep": 9, "error": "boom", "error_type": "x"}])
    summary = analysis.analyze(project, dry_run=False)
    assert len(summary) == 6  # 2 models x 3 arms
    out_dir = project.output_dir(False)
    for name in ["summary.csv", "all_calls_flat.csv", "h1_class_effect.csv", "h2_explicit_vs_implicit.csv",
                 "position_bias.csv", "consistency.csv", "sessions.csv", "ratings_shortlist.csv", "reasons.csv",
                 "report.md", "figures/pick_rates.png", "figures/rating_differences.png", "figures/position_bias.png"]:
        assert (out_dir / name).exists(), name
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "## H1" in report and "## H2" in report and "## Position bias" in report and "## Caveats" in report
    assert "1 failed calls excluded" in capsys.readouterr().out
    h1 = pd.read_csv(out_dir / "h1_class_effect.csv")
    assert list(h1.columns[:4]) == ["model", "arm", "n_calls", "n_cvs"]


def test_analyze_ignores_dry_run_rows_in_the_real_file_and_reports_empty_data(project, capsys):
    rows = make_rows(project, {"implicit": 0.5, "explicit": 0.5, "demographic": 0.5}, reps=1)
    for r in rows:
        r["dry_run"] = True
    write_rows(project, rows)
    assert analysis.analyze(project, dry_run=False) is None
    assert "No usable rows" in capsys.readouterr().out
