"""The analysis, on small synthetic data with a known answer."""

import json

import numpy as np
import pandas as pd
import pytest

from pipeline import analysis, stats
from pipeline.runner import results_file


def make_rows(project, shortlist_prob, sessions=("day1", "day2"), samples=2, models=None, likelihood_gap=20.0,
              seed=0):
    """Fake successful rows, one CV per call. The higher-class CV (x) of each arm is
    shortlisted with probability shortlist_prob[arm], the other with 0.5, and x's
    0-100 likelihood sits likelihood_gap points higher on average."""
    rng = np.random.default_rng(seed)
    rows = []
    for model in models or [m.id for m in project.models]:
        for cv in range(1, 4):
            for arm, (x, y) in project.arms.items():
                for variant in (x, y):
                    is_x = variant == x
                    for session in sessions:
                        for sample in range(1, samples + 1):
                            p = shortlist_prob[arm] if is_x else 0.5
                            likelihood = rng.normal(55 + (likelihood_gap if is_x else 0), 8)
                            # In the explicit arm the x reasons also mention the monitoring block.
                            reason = ("Strong school and university background" + ("; the monitoring answers were disregarded"
                                      if arm == "explicit" else "")) if is_x else "Solid overall"
                            rows.append({
                                "ok": True, "dry_run": False, "session": session, "model": model,
                                "cv_id": f"cv0{cv}", "arm": arm, "variant": variant,
                                "stimulus_id": f"cv0{cv}_{arm}_{variant}", "sample": sample, "prompt_hash": "abc",
                                "n_fillers": 9, "target_position": 10,
                                "shortlist": bool(rng.random() < p),
                                # x ranks a place or two better than y, on average
                                "rank_in_round": int(rng.integers(2, 5) if is_x else rng.integers(3, 7)),
                                "likelihood": int(np.clip(round(likelihood), 0, 100)),
                                # "experience" is a keyword, so the y reason avoids every keyword on purpose
                                "reason": reason,
                            })
    return rows


def write_rows(project, rows, dry_run=False):
    path = results_file(project.output_dir(dry_run))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def test_prepare_marks_the_higher_class_variant(project):
    rows = make_rows(project, {"implicit": 1.0, "explicit": 1.0, "demographic": 1.0}, samples=1)
    df = analysis.prepare(project, rows, dry_run=False)
    assert df["is_x"].mean() == 0.5  # both variants equally often
    assert ((df["variant"] == df["x_variant"]) == (df["is_x"] == 1)).all()
    assert (df.loc[df["is_x"] == 1, "shortlist"] == 1).all()
    assert df.loc[df["is_x"] == 1, "likelihood"].mean() > df.loc[df["is_x"] == 0, "likelihood"].mean()
    assert (df["pair_id"] == df["cv_id"] + "_" + df["arm"]).all()
    assert (df["rank_score"] == 11 - df["rank_in_round"]).all()
    assert df.loc[(df["arm"] == "explicit") & (df["is_x"] == 1), "mentions_monitoring"].eq(1).all()
    assert df.loc[(df["arm"] != "explicit") | (df["is_x"] == 0), "mentions_monitoring"].eq(0).all()


def test_effects_by_cv_are_the_variant_differences(project):
    rows = make_rows(project, {"implicit": 1.0, "explicit": 0.5, "demographic": 0.5}, samples=4, seed=1)
    df = analysis.prepare(project, rows, dry_run=False)
    effects = analysis.effects_by_cv(df)
    assert len(effects) == 2 * 3 * 3  # models x arms x base CVs
    imp = effects[effects["arm"] == "implicit"]
    assert (imp["shortlist_rate_x"] == 1.0).all()
    assert (imp["n_calls_x"] == 8).all() and (imp["n_calls_y"] == 8).all()  # 2 sessions x 4 samples
    assert np.allclose(imp["shortlist_effect"], imp["shortlist_rate_x"] - imp["shortlist_rate_y"])
    assert (effects["likelihood_effect"] > 0).all()
    assert (effects["rank_effect"] > 0).mean() > 0.8  # x ranks better in nearly every base


def test_h1_finds_a_real_class_effect_and_not_a_null_one(project):
    rows = make_rows(project, {"implicit": 0.95, "explicit": 0.5, "demographic": 0.5}, samples=10, seed=2)
    df = analysis.prepare(project, rows, dry_run=False)
    h1 = analysis.h1_table(df, analysis.effects_by_cv(df))
    imp = h1[h1["arm"] == "implicit"]
    assert (imp["n_cvs"] == 3).all() and (imp["n_calls"] == 120).all()
    assert (imp["shortlist_effect"] > 0.3).all() and (imp["shortlist_ci_low"] > 0).all()
    assert (imp["shortlist_t_p"] < 0.05).all()
    assert (imp["pooled_odds_ratio"] > 1).all() and (imp["pooled_or_ci_low"] > 1).all()
    null = h1[h1["arm"] == "explicit"]
    assert ((null["shortlist_ci_low"] < 0) & (null["shortlist_ci_high"] > 0)).all()
    # The likelihood gap is built into every arm, so every arm shows it.
    assert (h1["likelihood_effect"] > 10).all() and (h1["likelihood_ci_low"] > 0).all()
    assert (h1["pooled_likelihood_diff"] > 10).all()
    # The sign test counts base CVs: with 0.95 vs 0.5 every implicit base favours x.
    assert (imp["shortlist_cvs_favouring_x"] == 3).all() and (imp["shortlist_cvs_favouring_y"] == 0).all()
    assert (imp["shortlist_sign_p"] == 0.25).all()  # 3 of 3, two-sided exact binomial
    assert (h1["rank_effect"] > 0).all()
    assert ((h1["deterministic_share"] >= 0) & (h1["deterministic_share"] <= 1)).all()


def test_a_deterministic_model_gets_the_sign_test_as_its_record(project):
    """Every sample of a CV the same decision: share of yes is 0 or 1 per CV."""
    rows = make_rows(project, {"implicit": 1.0, "explicit": 1.0, "demographic": 1.0}, samples=5, seed=7)
    for r in rows:          # y never shortlisted, x always: a deterministic model with a full effect
        r["shortlist"] = r["variant"] == project.arms[r["arm"]][0]
    df = analysis.prepare(project, rows, dry_run=False)
    h1 = analysis.h1_table(df, analysis.effects_by_cv(df))
    assert (h1["deterministic_share"] == 1.0).all()
    assert (h1["shortlist_effect"] == 1.0).all() and h1["shortlist_ci_low"].isna().all()  # no variance across CVs
    assert (h1["shortlist_cvs_favouring_x"] == 3).all() and (h1["shortlist_sign_p"] == 0.25).all()


def test_monitoring_table_counts_only_the_explicit_arm(project):
    rows = make_rows(project, {"implicit": 0.5, "explicit": 0.5, "demographic": 0.5}, samples=4, seed=8)
    df = analysis.prepare(project, rows, dry_run=False)
    mon = analysis.monitoring_table(project, df)
    assert len(mon) == 2 and (mon["mentions_x_pct"] == 100.0).all() and (mon["mentions_y_pct"] == 0.0).all()
    assert (mon["cvs_more_for_x"] == 3).all() and (mon["cv_level_mean_diff"] == 1.0).all()
    assert (mon["n_calls_x"] == 24).all()  # 3 CVs x 2 sessions x 4 samples


def test_sign_test_helper():
    s = stats.sign_test([1, 1, 1, 0, -1, np.nan])
    assert (s["n"], s["pos"], s["neg"], s["ties"]) == (5, 3, 1, 1)
    assert abs(s["p"] - 0.625) < 1e-9  # 3 of 4 non-ties, two-sided
    assert np.isnan(stats.sign_test([0, 0])["p"]) and stats.sign_test([])["n"] == 0


def test_h2_sees_a_smaller_explicit_effect(project):
    rows = make_rows(project, {"implicit": 0.95, "explicit": 0.55, "demographic": 0.5}, samples=10, seed=3)
    df = analysis.prepare(project, rows, dry_run=False)
    h2 = analysis.h2_table(project, df, analysis.effects_by_cv(df))
    assert (h2["cv_level_mean_diff_implicit_minus_explicit"] > 0.2).all()
    assert (h2["implicit_shortlist_effect"] > h2["explicit_shortlist_effect"]).all()
    assert (h2["interaction_odds_ratio"] < 1).all()
    assert (h2["n_cvs_paired"] == 3).all()


def test_consistency_sessions_and_likelihood_tables(project):
    rows = make_rows(project, {"implicit": 1.0, "explicit": 0.5, "demographic": 1.0}, samples=3, seed=4)
    df = analysis.prepare(project, rows, dry_run=False)
    cons = analysis.consistency_table(df)
    x_implicit = cons[(cons["arm"] == "implicit") & (cons["is_x"] == 1)]
    assert (x_implicit["agreement_with_majority"] == 1.0).all() and (x_implicit["shortlist_rate"] == 1.0).all()
    assert (cons["n_calls"] == 6).all()  # 2 sessions x 3 samples
    assert len(cons) == 2 * 18  # models x CVs
    sess = analysis.sessions_table(df)
    assert set(sess["session_1"]) == {"day1"} and set(sess["session_2"]) == {"day2"}
    assert (sess["mean_abs_change_per_cv"] >= 0).all()
    assert analysis.sessions_table(df[df["session"] == "day1"]).empty
    like = analysis.likelihood_table(df)
    assert len(like) == 2 * 3 * 2  # models x arms x variants
    x = like[like["variant"] == "x (higher-class)"].set_index(["model", "arm"])["mean"]
    y = like[like["variant"] == "y"].set_index(["model", "arm"])["mean"]
    assert (x > y + 10).all()


def test_reasons_table(project):
    rows = make_rows(project, {"implicit": 0.5, "explicit": 0.5, "demographic": 0.5}, samples=2, seed=5)
    df = analysis.prepare(project, rows, dry_run=False)
    reas = analysis.reasons_table(project, df)
    any_rows = reas[reas["keyword"] == "(any keyword)"]
    assert (any_rows["x_pct"] == 100.0).all() and (any_rows["y_pct"] == 0.0).all()
    school = reas[reas["keyword"] == "school*"]
    assert (school["x_mentions"] == school["n_reasons_x"]).all()


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
    assert stats.clustered_difference([2, 2, 2, 2], [0, 1, 0, 1], ["a", "b", "c", "d"])["note"] == "no variation"
    assert stats.clustered_difference([1, 2, 3, 4], [1, 1, 1, 1], ["a", "b", "c", "d"])["note"]
    # Within-cluster differences of 10, 12, 8 and 12: the slope is their mean and the
    # interval has to contain it (identical differences would collapse it to a point).
    d = stats.clustered_difference([10, 20, 11, 23, 9, 17, 12, 24], [0, 1, 0, 1, 0, 1, 0, 1],
                                   ["a", "a", "b", "b", "c", "c", "d", "d"])
    assert abs(d["diff"] - 10.5) < 1e-9 and d["low"] < 10.5 < d["high"] and d["p"] < 0.05
    assert np.isnan(stats.cv_level([0.5, 0.5])["t_p"]) and np.isnan(stats.cv_level([0.5, 0.5])["wilcoxon_p"])


def test_analyze_writes_every_output(project, capsys):
    write_rows(project, make_rows(project, {"implicit": 0.8, "explicit": 0.6, "demographic": 0.5}, samples=3, seed=6)
               + [{"ok": False, "dry_run": False, "session": "day1", "model": "m", "cv_id": "cv01", "arm": "implicit",
                   "variant": "high", "stimulus_id": "cv01_implicit_high", "sample": 9, "n_fillers": 9,
                   "target_position": 10, "error": "boom", "error_type": "x"}])
    summary = analysis.analyze(project, dry_run=False)
    assert len(summary) == 6  # 2 models x 3 arms
    out_dir = project.output_dir(False)
    for name in ["summary.csv", "all_calls_flat.csv", "effects_by_cv.csv", "h1_class_effect.csv",
                 "h2_explicit_vs_implicit.csv", "consistency.csv", "sessions.csv", "likelihood.csv", "reasons.csv",
                 "monitoring.csv", "report.md", "figures/effects.png", "figures/likelihoods.png"]:
        assert (out_dir / name).exists(), name
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    for heading in ("## H1", "## H2", "## Consistency", "## How the likelihoods are spread",
                    "## Explicit arm: does the reason refer to the monitoring block?", "## Caveats"):
        assert heading in report, heading
    assert "Position bias" not in report
    assert "1 failed calls excluded" in capsys.readouterr().out
    h1 = pd.read_csv(out_dir / "h1_class_effect.csv")
    assert list(h1.columns[:4]) == ["model", "arm", "n_calls", "n_cvs"]


def test_analyze_ignores_dry_run_rows_in_the_real_file_and_reports_empty_data(project, capsys):
    rows = make_rows(project, {"implicit": 0.5, "explicit": 0.5, "demographic": 0.5}, samples=1)
    for r in rows:
        r["dry_run"] = True
    write_rows(project, rows)
    assert analysis.analyze(project, dry_run=False) is None
    assert "No usable rows" in capsys.readouterr().out
