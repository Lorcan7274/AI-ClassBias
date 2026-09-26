"""Human survey comparison:  python -m pipeline analyze-survey --csv FILE [--dry-run]

Reads the survey export (one row per participant and pair; the columns are listed
below and in the README), reports how often people picked the higher-class CV, the
manipulation check, and a side-by-side comparison with the models on the same pairs.
Outputs go to results/survey/ (or results/dry_run/survey/ with --dry-run):
survey_summary.csv, survey_by_pair.csv, survey_manipulation_check.csv,
figures/survey_vs_models.png and survey_report.md.

Expected columns (extra columns are ignored):
  participant_id   who answered (any text or number)
  pair_id          the pair shown, e.g. cv01_implicit (must match the CV file names)
  first_variant    the variant shown as Candidate 1: high or low
  chosen_position  which candidate the participant preferred: 1 or 2
  guess_job_1, guess_job_2        guessed parental job of candidate 1 / 2:
                                  professional, manual or unsure
  guess_school_1, guess_school_2  guessed school type of candidate 1 / 2:
                                  private, state or unsure
  rating_1, rating_2 (optional)   rating out of 10 for candidate 1 / 2
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import stats
from pipeline.analysis import ARM_COLOURS, GRID, INK, INK_SOFT, SURFACE, load_rows, prepare, short_model
from pipeline.runner import results_file
from pipeline.tables import fmt, md_table, pct

REQUIRED_COLUMNS = ["participant_id", "pair_id", "first_variant", "chosen_position",
                    "guess_job_1", "guess_job_2", "guess_school_1", "guess_school_2"]
JOB_VALUES = {"professional", "manual", "unsure"}
SCHOOL_VALUES = {"private", "state", "unsure"}
# The guess that matches the marker each variant carries.
INTENDED_JOB = {"high": "professional", "low": "manual"}
INTENDED_SCHOOL = {"high": "private", "low": "state"}


class SurveyError(Exception):
    """The survey CSV is missing something or holds a value that can't be used."""


def load_survey(path, arms) -> pd.DataFrame:
    """Read and check the survey CSV. Returns one row per participant and pair with
    the derived columns chosen_variant, other_variant and picked_high."""
    path = Path(path)
    if not path.exists():
        raise SurveyError(f"survey file not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SurveyError(f"the survey CSV is missing the column(s): {', '.join(missing)}. "
                          f"Expected: {', '.join(REQUIRED_COLUMNS)} (see the README)")
    if df.empty:
        raise SurveyError("the survey CSV has no rows")
    for c in df.columns:
        df[c] = df[c].str.strip()
    df["arm"] = df["pair_id"].str.rsplit("_", n=1).str[-1]
    bad_arm = df[~df["arm"].isin(list(arms))]
    if not bad_arm.empty:
        raise SurveyError(f"pair_id must end in an arm name ({', '.join(arms)}): "
                          f"row {bad_arm.index[0] + 2} has '{bad_arm.iloc[0]['pair_id']}'")
    df["variants"] = df["arm"].map(lambda a: arms[a])
    for i, row in df.iterrows():
        x, y = row["variants"]
        line = i + 2  # CSV line number, counting the header
        if row["first_variant"] not in (x, y):
            raise SurveyError(f"line {line}: first_variant must be {x} or {y} for {row['pair_id']}, "
                              f"not '{row['first_variant']}'")
        if row["chosen_position"] not in ("1", "2"):
            raise SurveyError(f"line {line}: chosen_position must be 1 or 2, not '{row['chosen_position']}'")
        for c in ("guess_job_1", "guess_job_2"):
            if row[c].lower() not in JOB_VALUES:
                raise SurveyError(f"line {line}: {c} must be professional, manual or unsure, not '{row[c]}'")
        for c in ("guess_school_1", "guess_school_2"):
            if row[c].lower() not in SCHOOL_VALUES:
                raise SurveyError(f"line {line}: {c} must be private, state or unsure, not '{row[c]}'")
    df["second_variant"] = [y if f == x else x for f, (x, y) in zip(df["first_variant"], df["variants"])]
    df["chosen_variant"] = np.where(df["chosen_position"] == "1", df["first_variant"], df["second_variant"])
    # "high" = the first variant of the arm (the higher-class CV), as in the model analysis.
    df["picked_high"] = (df["chosen_variant"] == df["variants"].str[0]).astype(int)
    df["cv_id"] = df["pair_id"].str.rsplit("_", n=1).str[0]
    for c in ("rating_1", "rating_2"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.drop(columns=["variants"])


def manipulation_check(df, arms) -> pd.DataFrame:
    """Did people read the markers as intended? For each variant shown, the share of
    guesses in each category, and the share of decided (not "unsure") guesses that
    point in the intended direction, with a CI clustered by participant."""
    shown = []
    for _, row in df.iterrows():
        x = arms[row["arm"]][0]
        for pos, variant in ((1, row["first_variant"]), (2, row["second_variant"])):
            label = "high" if variant == x else "low"
            shown.append({"participant_id": row["participant_id"], "variant": label,
                          "guess_job": row[f"guess_job_{pos}"].lower(),
                          "guess_school": row[f"guess_school_{pos}"].lower()})
    shown = pd.DataFrame(shown)
    out = []
    for variant, g in shown.groupby("variant", sort=True):
        for kind, column, intended, values in (("parental job", "guess_job", INTENDED_JOB[variant], ["professional", "manual", "unsure"]),
                                               ("school type", "guess_school", INTENDED_SCHOOL[variant], ["private", "state", "unsure"])):
            decided = g[g[column] != "unsure"]
            right = (decided[column] == intended).astype(int)
            ci = stats.clustered_rate(right, decided["participant_id"]) if len(decided) else None
            row = {"variant_shown": variant, "guess": kind, "n_shown": len(g), "intended_answer": intended}
            for v in values:
                row[f"pct_{v}"] = 100 * (g[column] == v).mean()
            row.update({"n_decided": len(decided),
                        "pct_intended_of_decided": 100 * ci["rate"] if ci else np.nan,
                        "ci_low": 100 * ci["low"] if ci else np.nan, "ci_high": 100 * ci["high"] if ci else np.nan,
                        "p_vs_50": ci["p"] if ci else np.nan})
            out.append(row)
    return pd.DataFrame(out)


def compare_with_models(df, model_df) -> pd.DataFrame:
    """Per pair: the human pick-high rate next to each model's pick rate on the same pair."""
    by_pair = df.groupby("pair_id").agg(n_humans=("picked_high", "size"),
                                        human_pick_high_rate=("picked_high", "mean")).reset_index()
    if model_df is not None and not model_df.empty:
        model_rates = (model_df[model_df["pair_id"].isin(by_pair["pair_id"])]
                       .groupby(["pair_id", "model"])["picked_x"].mean().unstack("model"))
        model_rates.columns = [f"model_{short_model(m)}" for m in model_rates.columns]
        by_pair = by_pair.merge(model_rates, left_on="pair_id", right_index=True, how="left")
    return by_pair


def correlations(by_pair) -> pd.DataFrame:
    """Spearman correlation across pairs between the human rate and each model's rate."""
    out = []
    for column in [c for c in by_pair.columns if c.startswith("model_")]:
        both = by_pair[["human_pick_high_rate", column]].dropna()
        if len(both) >= 3 and both[column].nunique() > 1 and both["human_pick_high_rate"].nunique() > 1:
            from scipy.stats import spearmanr
            r = spearmanr(both["human_pick_high_rate"], both[column])
            out.append({"model": column[len("model_"):], "n_pairs": len(both),
                        "spearman_r": float(r.statistic), "p": float(r.pvalue),
                        "model_mean_pick_high_rate": both[column].mean()})
        else:
            out.append({"model": column[len("model_"):], "n_pairs": len(both), "spearman_r": np.nan, "p": np.nan,
                        "model_mean_pick_high_rate": both[column].mean() if len(both) else np.nan})
    return pd.DataFrame(out)


def plot_comparison(by_pair, path):
    """Dot plot per pair: human pick-high rate (filled) and each model's rate (hollow)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    model_cols = [c for c in by_pair.columns if c.startswith("model_")]
    fig, ax = plt.subplots(figsize=(max(6, 0.6 * len(by_pair) + 2), 4))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_title("Share picking the higher-class CV, per pair: humans vs models", color=INK, fontsize=10, loc="left")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.axhline(50, color=INK_SOFT, linewidth=1)
    xs = np.arange(len(by_pair))
    for i, col in enumerate(model_cols[:5]):
        colour = ARM_COLOURS[(i + 1) % len(ARM_COLOURS)]
        ax.plot(xs, 100 * by_pair[col], "o", markerfacecolor=SURFACE, markeredgecolor=colour, markersize=6,
                label=col[len("model_"):])
    ax.plot(xs, 100 * by_pair["human_pick_high_rate"], "o", color=INK, markersize=7, label="humans")
    ax.set_xticks(xs)
    ax.set_xticklabels(by_pair["pair_id"], rotation=45, ha="right", fontsize=7)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% picking the higher-class CV", color=INK_SOFT, fontsize=8)
    ax.tick_params(colors=INK_SOFT, labelsize=8)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def analyze_survey(cfg, csv_path, dry_run=False):
    """Run the survey analysis and save the tables, figure and report. Returns the summary table."""
    df = load_survey(csv_path, cfg.arms)
    results_dir = cfg.output_dir(dry_run)
    out_dir = results_dir / "survey"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(exist_ok=True)

    overall = stats.clustered_rate(df["picked_high"], df["participant_id"])
    per_cv = stats.cv_level(df.groupby("cv_id")["picked_high"].mean().values, 0.5)
    summary = pd.DataFrame([{
        "n_answers": len(df), "n_participants": df["participant_id"].nunique(), "n_pairs": df["pair_id"].nunique(),
        "human_pick_high_rate": overall["rate"], "ci_low": overall["low"], "ci_high": overall["high"],
        "p_vs_50": overall["p"], "cv_level_mean": per_cv["mean"], "cv_level_ci_low": per_cv["low"],
        "cv_level_ci_high": per_cv["high"], "cv_level_t_p": per_cv["t_p"], "cv_level_wilcoxon_p": per_cv["wilcoxon_p"],
        "pct_picked_candidate_1": 100 * (df["chosen_position"] == "1").mean(),
    }])
    check = manipulation_check(df, cfg.arms)

    model_path = results_file(results_dir)
    model_df = prepare(cfg, load_rows(model_path), dry_run) if model_path.exists() else None
    by_pair = compare_with_models(df, model_df)
    corr = correlations(by_pair)

    summary.to_csv(out_dir / "survey_summary.csv", index=False)
    check.to_csv(out_dir / "survey_manipulation_check.csv", index=False)
    by_pair.to_csv(out_dir / "survey_by_pair.csv", index=False)
    plot_comparison(by_pair, out_dir / "figures" / "survey_vs_models.png")

    s = summary.iloc[0]
    lines = [f"# Human survey results{' (compared with DRY-RUN model data)' if dry_run else ''}", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from `{csv_path}`.", "",
             "## Human pick rate", "",
             f"{int(s['n_participants'])} participants answered {int(s['n_answers'])} pair questions on "
             f"{int(s['n_pairs'])} pairs. They picked the higher-class CV in {pct(s['human_pick_high_rate'])} of "
             f"answers (95% CI {pct(s['ci_low'])} to {pct(s['ci_high'])}, clustered by participant; "
             f"p = {fmt(s['p_vs_50'])} against 50%). Per base CV: mean {pct(s['cv_level_mean'])} "
             f"(t-test p = {fmt(s['cv_level_t_p'])}, Wilcoxon p = {fmt(s['cv_level_wilcoxon_p'])}). "
             f"They picked Candidate 1 in {fmt(s['pct_picked_candidate_1'], 1)}% of answers.", "",
             "## Manipulation check", "",
             "For each CV shown, what participants guessed about the candidate's parental job and school. "
             "`pct_intended_of_decided` is the share of non-\"unsure\" guesses that match the marker the "
             "variant carries (professional and private for the higher-class CV, manual and state for the "
             "other), with a 95% CI clustered by participant.", "",
             md_table(check, 1), "",
             "## Humans and models on the same pairs", ""]
    if model_df is None or model_df.empty:
        lines += ["No model results were found to compare with.", ""]
    else:
        lines += ["Share picking the higher-class CV per pair. Model columns use all the models' calls on that "
                  "pair (both orders, all sessions).", "", md_table(by_pair, 2), "",
                  "Spearman rank correlation across pairs between the human rate and each model's rate:", "",
                  md_table(corr, 3), "", "![humans vs models](figures/survey_vs_models.png)", ""]
    lines += ["## Caveats", "",
              "- Participants were told the study is about gender, so their guesses about class are not "
              "primed; but a pair each person saw only once gives a noisy per-pair rate.",
              "- The comparison is descriptive: humans and models saw the same CV pairs but different "
              "instructions and numbers of trials.", ""]
    report = out_dir / "survey_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    pd.set_option("display.width", 200)
    print(summary.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nManipulation check:\n")
    print(check.to_string(index=False, float_format=lambda v: f"{v:.1f}"))
    print(f"\nSaved {out_dir / 'survey_summary.csv'}, {out_dir / 'survey_by_pair.csv'} and {report}")
    return summary


def write_sample_survey(path, arms, n_participants=24, pairs_per_participant=6, n_cvs=15, seed=7) -> Path:
    """A fake survey export for testing, in the expected format. Humans in it favour
    the higher-class CV a little and read the markers correctly most of the time."""
    rng = np.random.default_rng(seed)
    x, y = arms["implicit"]
    rows = []
    for p in range(1, n_participants + 1):
        for cv in rng.choice(np.arange(1, n_cvs + 1), size=pairs_per_participant, replace=False):
            first = x if rng.random() < 0.5 else y
            second = y if first == x else x
            picked = x if rng.random() < 0.58 else y
            def guess(variant, right, wrong):
                r = rng.random()
                return right if r < 0.62 else (wrong if r < 0.85 else "unsure")
            row = {"participant_id": f"P{p:03d}", "pair_id": f"cv{cv:02d}_implicit", "first_variant": first,
                   "chosen_position": 1 if picked == first else 2}
            for pos, variant in ((1, first), (2, second)):
                job = guess(variant, "professional", "manual") if variant == x else guess(variant, "manual", "professional")
                school = guess(variant, "private", "state") if variant == x else guess(variant, "state", "private")
                row[f"guess_job_{pos}"] = job
                row[f"guess_school_{pos}"] = school
                row[f"rating_{pos}"] = int(np.clip(rng.normal(6.5 if variant == x else 6.0, 1.5), 1, 10))
            rows.append(row)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path
