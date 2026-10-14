"""Analysis:  python -m pipeline analyze [--dry-run]

One row per call, one CV per call. For every base CV the two variants of an arm are
compared on two measures, each averaged over that CV's samples and sessions:

  shortlist rate    the share of calls that said yes
  mean likelihood   the mean 0-100 likelihood of shortlisting

The class effect for a base CV is the higher-class variant minus the other on each
measure. The 15 base CVs are the units: the headline estimate is the mean effect
across them with a t-interval and a Wilcoxon test, and a regression on all the calls
with standard errors clustered by base CV is the cross-check. Everything is saved
next to the results file (results/, or results/dry_run/ for a dry run):

  summary.csv              shortlist rates and mean likelihoods per model x arm
  all_calls_flat.csv       every successful call with the derived columns
  effects_by_cv.csv        both effects for every model x arm x base CV
  h1_class_effect.csv      mean effect across base CVs, with CIs and tests
  h2_explicit_vs_implicit.csv
  consistency.csv          agreement across the samples of each CV
  sessions.csv             the effect in each session and the change between them
  likelihood.csv           how the 0-100 likelihoods are spread
  reasons.csv              keyword mentions in the one-sentence reasons
  figures/*.png
  report.md

How the tests deal with repeated calls: see pipeline/stats.py.
"""

from __future__ import annotations

import json
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import stats
from pipeline.runner import results_file
from pipeline.tables import fmt, md_table, pct

# Colours for the arms, in the order they appear in config.yaml. These three are the
# first three slots of a palette checked for colour-blind safety (see the dataviz
# notes in the README); every mark also carries a text label.
ARM_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, INK_SOFT, GRID, SURFACE = "#0b0b0b", "#52514e", "#dddcd7", "#fcfcfb"


# ----------------------------- loading -----------------------------

def load_rows(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def prepare(cfg, rows, dry_run) -> pd.DataFrame | None:
    """Successful rows as a table with the derived columns the analysis needs."""
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    df = df[df["ok"]].copy()
    if not dry_run:
        # The real results file should never hold dry-run rows, but never count them as data.
        df = df[~df["dry_run"]]
    df = df[df["arm"].isin(list(cfg.arms))]
    if df.empty:
        return None
    df = df.copy()
    df["x_variant"] = df["arm"].map(lambda a: cfg.arms[a][0])
    # is_x = 1 for the first variant of the arm (for the class arms, the higher-class CV).
    df["is_x"] = (df["variant"] == df["x_variant"]).astype(int)
    df["pair_id"] = df["cv_id"].astype(str) + "_" + df["arm"].astype(str)
    df["shortlist"] = df["shortlist"].astype(int)
    df["likelihood"] = df["likelihood"].astype(float)
    return df


# ----------------------------- the tables -----------------------------

def effects_by_cv(df) -> pd.DataFrame:
    """Per model x arm x base CV: each variant's shortlist rate and mean likelihood
    over all its samples and sessions, and the higher-class variant minus the other.
    These per-CV effects are what the headline tests are run on."""
    g = (df.groupby(["model", "arm", "cv_id", "is_x"])
           .agg(n=("shortlist", "size"), shortlist_rate=("shortlist", "mean"),
                mean_likelihood=("likelihood", "mean")).reset_index())
    wide = g.pivot(index=["model", "arm", "cv_id"], columns="is_x",
                   values=["n", "shortlist_rate", "mean_likelihood"])
    out = pd.DataFrame(index=wide.index)
    for measure, name in (("n", "n_calls"), ("shortlist_rate", "shortlist_rate"),
                          ("mean_likelihood", "mean_likelihood")):
        absent = pd.Series(np.nan, index=wide.index)
        out[f"{name}_x"] = wide[measure][1] if 1 in wide[measure] else absent
        out[f"{name}_y"] = wide[measure][0] if 0 in wide[measure] else absent
    out = out.reset_index()
    out["shortlist_effect"] = out["shortlist_rate_x"] - out["shortlist_rate_y"]
    out["likelihood_effect"] = out["mean_likelihood_x"] - out["mean_likelihood_y"]
    return out


def descriptive_table(df) -> pd.DataFrame:
    """Plain averages per model x arm, over all calls, before any clustering."""
    out = []
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        x, y = g[g["is_x"] == 1], g[g["is_x"] == 0]
        out.append({
            "model": model, "arm": arm, "n_calls": len(g),
            "shortlist_rate_x": x["shortlist"].mean(), "shortlist_rate_y": y["shortlist"].mean(),
            "shortlist_diff": x["shortlist"].mean() - y["shortlist"].mean(),
            "mean_likelihood_x": x["likelihood"].mean(), "mean_likelihood_y": y["likelihood"].mean(),
            "likelihood_diff": x["likelihood"].mean() - y["likelihood"].mean(),
        })
    return pd.DataFrame(out)


def h1_table(df, effects) -> pd.DataFrame:
    """H1: is the higher-class CV (x) shortlisted more than the other?

    Main estimate, per model x arm: the mean of the per-CV effects across base CVs,
    with a t-interval and a Wilcoxon signed-rank test against 0 (each base CV counts
    once). Cross-check on all the calls: a logistic regression shortlist ~ is_x and a
    linear regression likelihood ~ is_x, both with standard errors clustered by base CV.
    """
    out = []
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        e = effects[(effects["model"] == model) & (effects["arm"] == arm)]
        e = e.dropna(subset=["shortlist_effect", "likelihood_effect"])
        shortlist = stats.cv_level(e["shortlist_effect"].values, 0.0)
        likelihood = stats.cv_level(e["likelihood_effect"].values, 0.0)
        pooled_odds = stats.clustered_odds_ratio(g["shortlist"], g["is_x"], g["cv_id"])
        pooled_diff = stats.clustered_difference(g["likelihood"], g["is_x"], g["cv_id"])
        out.append({
            "model": model, "arm": arm, "n_calls": len(g), "n_cvs": shortlist["n_cvs"],
            "shortlist_effect": shortlist["mean"], "shortlist_ci_low": shortlist["low"],
            "shortlist_ci_high": shortlist["high"], "shortlist_t_p": shortlist["t_p"],
            "shortlist_wilcoxon_p": shortlist["wilcoxon_p"],
            "likelihood_effect": likelihood["mean"], "likelihood_ci_low": likelihood["low"],
            "likelihood_ci_high": likelihood["high"], "likelihood_t_p": likelihood["t_p"],
            "likelihood_wilcoxon_p": likelihood["wilcoxon_p"],
            "pooled_odds_ratio": pooled_odds["odds_ratio"], "pooled_or_ci_low": pooled_odds["low"],
            "pooled_or_ci_high": pooled_odds["high"], "pooled_or_p": pooled_odds["p"],
            "pooled_likelihood_diff": pooled_diff["diff"], "pooled_likelihood_ci_low": pooled_diff["low"],
            "pooled_likelihood_ci_high": pooled_diff["high"], "pooled_likelihood_p": pooled_diff["p"],
            "note": "; ".join(n for n in (pooled_odds["note"], pooled_diff["note"]) if n),
        })
    return pd.DataFrame(out)


def h2_table(cfg, df, effects) -> pd.DataFrame:
    """H2: is the class effect smaller when class is stated explicitly?

    Per model: for each base CV, its implicit-arm effect minus its explicit-arm
    effect, then a paired t-test and a Wilcoxon test across the CVs (on both
    measures). Cross-check: a logistic regression on the two class arms together,
    shortlist ~ is_x + explicit + is_x:explicit, clustered by base CV; the odds ratio
    for the interaction is below 1 when the explicit arm's effect is the smaller.
    """
    out = []
    for model, g in df.groupby("model", sort=True):
        e = effects[effects["model"] == model]
        imp = e[e["arm"] == cfg.implicit_arm].set_index("cv_id")
        exp = e[e["arm"] == cfg.explicit_arm].set_index("cv_id")
        both = imp.join(exp, lsuffix="_imp", rsuffix="_exp", how="inner")
        d_short = stats.cv_level((both["shortlist_effect_imp"] - both["shortlist_effect_exp"]).dropna().values, 0.0)
        d_like = stats.cv_level((both["likelihood_effect_imp"] - both["likelihood_effect_exp"]).dropna().values, 0.0)

        gg = g[g["arm"].isin([cfg.implicit_arm, cfg.explicit_arm])]
        explicit = (gg["arm"] == cfg.explicit_arm).astype(int)
        interaction = stats.clustered_odds_ratio(gg["shortlist"], gg["is_x"] * explicit, gg["cv_id"],
                                                 extra=[gg["is_x"], explicit])
        out.append({
            "model": model,
            "implicit_shortlist_effect": imp["shortlist_effect"].mean() if len(imp) else np.nan,
            "explicit_shortlist_effect": exp["shortlist_effect"].mean() if len(exp) else np.nan,
            "cv_level_mean_diff_implicit_minus_explicit": d_short["mean"],
            "cv_level_ci_low": d_short["low"], "cv_level_ci_high": d_short["high"],
            "cv_level_t_p": d_short["t_p"], "cv_level_wilcoxon_p": d_short["wilcoxon_p"],
            "implicit_likelihood_effect": imp["likelihood_effect"].mean() if len(imp) else np.nan,
            "explicit_likelihood_effect": exp["likelihood_effect"].mean() if len(exp) else np.nan,
            "likelihood_cv_level_mean_diff": d_like["mean"], "likelihood_cv_level_ci_low": d_like["low"],
            "likelihood_cv_level_ci_high": d_like["high"], "likelihood_cv_level_t_p": d_like["t_p"],
            "likelihood_cv_level_wilcoxon_p": d_like["wilcoxon_p"],
            "interaction_odds_ratio": interaction["odds_ratio"], "interaction_ci_low": interaction["low"],
            "interaction_ci_high": interaction["high"], "interaction_p": interaction["p"],
            "n_cvs_paired": d_short["n_cvs"], "note": interaction["note"],
        })
    return pd.DataFrame(out)


def consistency_table(df) -> pd.DataFrame:
    """Consistency: for each model x CV, how often its samples agreed with the CV's
    majority answer (1.0 = every sample said the same, 0.5 = a coin flip), and how
    spread its likelihoods were."""
    out = []
    for (model, arm, stimulus_id), g in df.groupby(["model", "arm", "stimulus_id"], sort=True):
        rate = g["shortlist"].mean()
        out.append({
            "model": model, "arm": arm, "stimulus_id": stimulus_id,
            "cv_id": g["cv_id"].iloc[0], "variant": g["variant"].iloc[0], "is_x": int(g["is_x"].iloc[0]),
            "n_calls": len(g), "shortlist_rate": rate, "agreement_with_majority": max(rate, 1 - rate),
            "mean_likelihood": g["likelihood"].mean(),
            "likelihood_sd": g["likelihood"].std(ddof=0) if len(g) > 1 else np.nan,
        })
    return pd.DataFrame(out)


def sessions_table(df) -> pd.DataFrame:
    """Session 1 vs session 2: the shortlist effect in each, the mean absolute change
    in each base CV's effect between them, and the odds ratio for the effect being
    different in the later session (the is_x:later interaction, clustered by base CV)."""
    sessions = sorted(df["session"].unique())
    out = []
    if len(sessions) < 2:
        return pd.DataFrame(out)
    s1, s2 = sessions[:2]
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        g = g[g["session"].isin([s1, s2])]
        rates = g.groupby(["session", "cv_id", "is_x"])["shortlist"].mean().unstack("is_x")
        effect = (rates.get(1) - rates.get(0)).unstack("session") if (1 in rates and 0 in rates) else pd.DataFrame()
        e1 = effect[s1].mean() if s1 in effect else np.nan
        e2 = effect[s2].mean() if s2 in effect else np.nan
        gap = (effect[s1] - effect[s2]).abs().mean() if (s1 in effect and s2 in effect) else np.nan
        later = (g["session"] == s2).astype(int)
        interaction = stats.clustered_odds_ratio(g["shortlist"], g["is_x"] * later, g["cv_id"],
                                                 extra=[g["is_x"], later])
        out.append({
            "model": model, "arm": arm, "session_1": s1, "session_2": s2,
            "shortlist_effect_session_1": e1, "shortlist_effect_session_2": e2,
            "mean_abs_change_per_cv": gap,
            "interaction_odds_ratio": interaction["odds_ratio"], "ci_low": interaction["low"],
            "ci_high": interaction["high"], "p": interaction["p"], "note": interaction["note"],
        })
    return pd.DataFrame(out)


def likelihood_table(df) -> pd.DataFrame:
    """How the 0-100 likelihoods are spread, per model x arm x variant. A model that
    answers 70 to everything shows up here as a sd near 0."""
    out = []
    for (model, arm, is_x), g in df.groupby(["model", "arm", "is_x"], sort=True):
        q = g["likelihood"].quantile([0.1, 0.5, 0.9])
        out.append({
            "model": model, "arm": arm, "variant": "x (higher-class)" if is_x else "y",
            "n_calls": len(g), "mean": g["likelihood"].mean(), "sd": g["likelihood"].std(ddof=0),
            "min": g["likelihood"].min(), "p10": q[0.1], "median": q[0.5], "p90": q[0.9],
            "max": g["likelihood"].max(), "n_distinct_values": g["likelihood"].nunique(),
            "shortlist_rate": g["shortlist"].mean(),
        })
    return pd.DataFrame(out)


def keyword_pattern(keyword) -> re.Pattern:
    """A whole-word pattern for one keyword; a trailing * also matches longer words."""
    if keyword.endswith("*"):
        return re.compile(r"\b" + re.escape(keyword[:-1]) + r"\w*", re.IGNORECASE)
    return re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)


def reasons_table(cfg, df) -> pd.DataFrame:
    """How often the one-sentence reasons mention class-related words (the list is
    analysis.reason_keywords in config.yaml), for the higher-class (x) CVs and the
    other (y) CVs separately. The "(any keyword)" rows count reasons with at least one hit."""
    patterns = {k: keyword_pattern(k) for k in cfg.reason_keywords}
    out = []
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        x_reasons = g.loc[g["is_x"] == 1, "reason"].fillna("").astype(str)
        y_reasons = g.loc[g["is_x"] == 0, "reason"].fillna("").astype(str)
        any_x = np.zeros(len(x_reasons), dtype=bool)
        any_y = np.zeros(len(y_reasons), dtype=bool)
        rows = []
        for keyword, pattern in patterns.items():
            hits_x = x_reasons.map(lambda t: bool(pattern.search(t))).values
            hits_y = y_reasons.map(lambda t: bool(pattern.search(t))).values
            any_x |= hits_x
            any_y |= hits_y
            rows.append({"model": model, "arm": arm, "keyword": keyword,
                         "n_reasons_x": len(x_reasons), "n_reasons_y": len(y_reasons),
                         "x_mentions": int(hits_x.sum()), "x_pct": 100 * hits_x.mean() if len(hits_x) else np.nan,
                         "y_mentions": int(hits_y.sum()), "y_pct": 100 * hits_y.mean() if len(hits_y) else np.nan})
        out.append({"model": model, "arm": arm, "keyword": "(any keyword)",
                    "n_reasons_x": len(x_reasons), "n_reasons_y": len(y_reasons),
                    "x_mentions": int(any_x.sum()), "x_pct": 100 * any_x.mean() if len(any_x) else np.nan,
                    "y_mentions": int(any_y.sum()), "y_pct": 100 * any_y.mean() if len(any_y) else np.nan})
        out += rows
    return pd.DataFrame(out)


# ----------------------------- figures -----------------------------

def _style(ax, title):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SOFT, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def short_model(model_id) -> str:
    """The model slug without its author prefix, cut to fit a panel title."""
    name = model_id.split("/")[-1]
    return name if len(name) <= 26 else name[:24] + "…"


def panel_title(model_id) -> str:
    """A model name wrapped on to two lines if it is long, for narrow panels."""
    return textwrap.fill(short_model(model_id), 16, break_long_words=True)


def plot_effects(cfg, h1, path):
    """One panel per model: the shortlist effect per arm (higher-class minus other, in
    percentage points) with its t-interval across base CVs, and a line at 0."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = sorted(h1["model"].unique())
    arms = list(cfg.arms)
    fig, axes = plt.subplots(1, len(models), figsize=(3.2 * len(models) + 1, 3.8), sharey=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax, model in zip(axes[0], models):
        _style(ax, panel_title(model))
        ax.axhline(0, color=INK_SOFT, linewidth=1)
        for i, arm in enumerate(arms):
            row = h1[(h1["model"] == model) & (h1["arm"] == arm)]
            if row.empty:
                continue
            r = row.iloc[0]
            effect, low, high = (100 * r["shortlist_effect"], 100 * r["shortlist_ci_low"],
                                 100 * r["shortlist_ci_high"])
            colour = ARM_COLOURS[i % len(ARM_COLOURS)]
            if not np.isnan(low):
                ax.plot([i, i], [low, high], color=colour, linewidth=2, solid_capstyle="round")
            ax.plot(i, effect, "o", color=colour, markersize=8)
            ax.annotate(f"{effect:+.0f}", (i, effect), xytext=(8, 0), textcoords="offset points",
                        fontsize=8, color=INK, va="center")
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels(arms, rotation=0)
        ax.set_xlim(-0.6, len(arms) - 0.4)
    axes[0][0].set_ylabel("shortlist rate, higher-class CV minus other\n(percentage points; 95% t-interval across base CVs)",
                          color=INK_SOFT, fontsize=8)
    axes[0][0].set_ylim(-100, 100)
    fig.suptitle("H1: class effect on the shortlist rate, per model and arm", color=INK, fontsize=11,
                 x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_likelihoods(cfg, df, path):
    """Rows = models, columns = arms: how the 0-100 likelihoods are spread for the
    higher-class CVs (filled) and the other CVs (outline)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = sorted(df["model"].unique())
    arms = list(cfg.arms)
    fig, axes = plt.subplots(len(models), len(arms), figsize=(3 * len(arms) + 1, 2.2 * len(models) + 1),
                             sharex=True, sharey="row", squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    bins = np.arange(0, 101, 10)
    for r, model in enumerate(models):
        for c, arm in enumerate(arms):
            ax = axes[r][c]
            g = df[(df["model"] == model) & (df["arm"] == arm)]
            colour = ARM_COLOURS[c % len(ARM_COLOURS)]
            _style(ax, arm if r == 0 else "")
            x, y = g.loc[g["is_x"] == 1, "likelihood"], g.loc[g["is_x"] == 0, "likelihood"]
            ax.hist(x, bins=bins, color=colour, alpha=0.75, label="higher-class")
            ax.hist(y, bins=bins, histtype="step", color=INK, linewidth=1.2, label="other")
            if len(x) and len(y):
                ax.annotate(f"means {x.mean():.0f} vs {y.mean():.0f}", (0.02, 0.9), xycoords="axes fraction",
                            fontsize=8, color=INK)
            if r == len(models) - 1:
                ax.set_xlabel("likelihood of shortlisting (0-100)", color=INK_SOFT, fontsize=8)
            if c == 0:
                ax.set_ylabel(f"{short_model(model)}\ncalls", color=INK, fontsize=8)
    axes[0][0].legend(fontsize=7, frameon=False, loc="upper right")
    fig.suptitle("Likelihoods: higher-class CV (filled) vs the other (outline); rows = models, columns = arms",
                 color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


# ----------------------------- the report -----------------------------

def significance(p) -> str:
    if p is None or np.isnan(p):
        return "no test possible"
    return "significant at 5%" if p < 0.05 else "not significant at 5%"


def write_report(cfg, df, tables, out_dir, n_failed, dry_run) -> Path:
    """results/report.md: every table in plain English, with the figures linked."""
    h1, h2, cons, sess, like, reas = (tables[k] for k in ("h1", "h2", "consistency", "sessions", "likelihood", "reasons"))
    models = sorted(df["model"].unique())
    sessions = sorted(df["session"].unique())
    lines = [f"# CV class-bias study: results{' (DRY RUN, fake answers)' if dry_run else ''}", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from `{results_file(out_dir)}`.", "",
             "## Data", "",
             f"- {len(df)} successful calls ({n_failed} failed calls excluded), "
             f"{df['stimulus_id'].nunique()} CVs from {df['cv_id'].nunique()} base CVs, "
             f"{len(models)} models, sessions: {', '.join(sessions)}.",
             "- Each call shows the model one CV; the model says whether it would shortlist the applicant "
             "and gives a 0-100 likelihood. Each CV is sampled several times per session.",
             "- Arms and their variants: " + "; ".join(f"{a} = {x} vs {y}" for a, (x, y) in cfg.arms.items())
             + ". In the tables, x is the first variant of each arm (for the class arms, the higher-class CV).",
             f"- Prompt hashes in the data: {', '.join(sorted(df['prompt_hash'].astype(str).str[:12].unique()))}.",
             "", "How the tests deal with repeated calls: the calls on one base CV share its wording and are "
             "not independent, so the headline estimates use one number per base CV (its effect), and the "
             "cross-checks are regressions on all calls with standard errors clustered by base CV.", ""]

    lines += ["## Summary", "",
              "Plain averages over all calls. `shortlist_diff` is the shortlist rate of the higher-class CV "
              "minus the other; `likelihood_diff` the same for the mean 0-100 likelihood.", "",
              md_table(tables["summary"], 3), ""]

    lines += ["## H1: is the higher-class CV shortlisted more than the other?", "",
              "`shortlist_effect` is the mean, across base CVs, of (higher-class CV's shortlist rate minus "
              "the other's), with a 95% t-interval and a Wilcoxon test against 0; `likelihood_effect` the "
              "same on the 0-100 scale. H1 is supported for a model and arm when the whole interval lies "
              "above 0. The pooled columns are the clustered-regression cross-checks.", ""]
    show = h1[["model", "arm", "n_calls", "n_cvs", "shortlist_effect", "shortlist_ci_low", "shortlist_ci_high",
               "shortlist_t_p", "shortlist_wilcoxon_p", "likelihood_effect", "likelihood_ci_low",
               "likelihood_ci_high", "likelihood_t_p", "pooled_odds_ratio", "pooled_or_p"]].copy()
    lines += [md_table(show, 3), ""]
    for _, r in h1.iterrows():
        verdict = ("above 0" if r["shortlist_ci_low"] > 0 else "below 0" if r["shortlist_ci_high"] < 0
                   else "includes 0") if not np.isnan(r["shortlist_ci_low"]) else "no interval"
        lines.append(f"- {r['model']}, {r['arm']}: shortlist effect {pct(r['shortlist_effect'])} "
                     f"(95% CI {pct(r['shortlist_ci_low'])} to {pct(r['shortlist_ci_high'])}, {verdict}; "
                     f"t-test {significance(r['shortlist_t_p'])}, Wilcoxon p = {fmt(r['shortlist_wilcoxon_p'])}). "
                     f"Likelihood effect {fmt(r['likelihood_effect'], 1)} points "
                     f"(95% CI {fmt(r['likelihood_ci_low'], 1)} to {fmt(r['likelihood_ci_high'], 1)}). "
                     f"Pooled odds ratio {fmt(r['pooled_odds_ratio'])}, p = {fmt(r['pooled_or_p'])}."
                     + (f" Note: {r['note']}." if r["note"] else ""))
    lines += ["", "![class effects](figures/effects.png)", ""]

    lines += [f"## H2: is the effect smaller when class is stated explicitly ({cfg.explicit_arm} vs "
              f"{cfg.implicit_arm})?", "",
              "For each base CV, its implicit-arm effect minus its explicit-arm effect; the mean across "
              "CVs with a paired t-test and a Wilcoxon test. Above 0 means the explicit arm's effect is "
              "the smaller. `interaction_odds_ratio` is the clustered-regression cross-check (below 1 "
              "means the same thing).", "",
              md_table(h2[["model", "implicit_shortlist_effect", "explicit_shortlist_effect",
                           "cv_level_mean_diff_implicit_minus_explicit", "cv_level_ci_low", "cv_level_ci_high",
                           "cv_level_t_p", "cv_level_wilcoxon_p", "implicit_likelihood_effect",
                           "explicit_likelihood_effect", "likelihood_cv_level_mean_diff", "likelihood_cv_level_t_p",
                           "interaction_odds_ratio", "interaction_p", "n_cvs_paired"]], 3), ""]
    for _, r in h2.iterrows():
        lines.append(f"- {r['model']}: implicit effect {pct(r['implicit_shortlist_effect'])} vs explicit "
                     f"{pct(r['explicit_shortlist_effect'])}; CV-level difference "
                     f"{pct(r['cv_level_mean_diff_implicit_minus_explicit'])} (paired t-test "
                     f"p = {fmt(r['cv_level_t_p'])}, Wilcoxon p = {fmt(r['cv_level_wilcoxon_p'])}). "
                     f"Interaction odds ratio {fmt(r['interaction_odds_ratio'])} "
                     f"(95% CI {fmt(r['interaction_ci_low'])} to {fmt(r['interaction_ci_high'])}), "
                     f"{significance(r['interaction_p'])}.")
    lines += [""]

    lines += ["## Consistency across the samples of each CV", "",
              "`agreement_with_majority` is the share of a CV's samples that gave its most common answer "
              "(1 = always the same, 0.5 = a coin flip); `likelihood_sd` is the spread of its likelihoods. "
              "A model whose samples never disagree gives no information about its shortlist probability "
              "beyond yes or no.", ""]
    cons_summary = cons.groupby(["model", "arm"], sort=True).agg(
        n_cvs=("stimulus_id", "nunique"), mean_agreement=("agreement_with_majority", "mean"),
        cvs_fully_consistent=("agreement_with_majority", lambda s: int((s >= 0.999).sum())),
        mean_likelihood_sd=("likelihood_sd", "mean")).reset_index()
    lines += [md_table(cons_summary, 3), "", "The full per-CV table is in `consistency.csv`.", ""]

    lines += ["## Session 1 vs session 2", ""]
    if sess.empty:
        lines += ["Only one session so far, so there is nothing to compare yet.", ""]
    else:
        lines += ["The shortlist effect in each session, the mean absolute change in each base CV's effect "
                  "between them, and the odds ratio for the effect differing in the later session "
                  "(clustered by base CV).", "", md_table(sess, 3), ""]

    lines += ["## How the likelihoods are spread", "",
              "If every CV gets a likelihood near the same value, the 0-100 scale is not discriminating "
              "and only the yes/no decision carries information.", "",
              md_table(like, 1), "", "![likelihoods](figures/likelihoods.png)", ""]

    lines += ["## What the reasons mention", "",
              "Share of one-sentence reasons mentioning each keyword (analysis.reason_keywords in "
              "config.yaml), for the higher-class CVs (x) and the other CVs (y).", "",
              md_table(reas[reas["keyword"] == "(any keyword)"][["model", "arm", "n_reasons_x", "x_pct",
                                                                 "n_reasons_y", "y_pct"]], 1),
              "", "Per keyword (only keywords mentioned at least once):", "",
              md_table(reas[(reas["keyword"] != "(any keyword)") & ((reas["x_mentions"] + reas["y_mentions"]) > 0)]
                       [["model", "arm", "keyword", "x_mentions", "x_pct", "y_mentions", "y_pct"]], 1), ""]

    lines += ["## Caveats", "",
              "- Calls on the same base CV are not independent; the headline estimates use one effect per "
              "base CV, but with 15 base CVs the intervals are wide and a single unusual CV can move a result.",
              "- Twelve model-by-arm comparisons are tested; expect about one false positive at the 5% "
              "level by chance alone.",
              "- The models may have changed between sessions (see `served_model` and `provider` in the "
              "results), and the answers depend on the exact prompt (`prompt_hash`).",
              "- Models that were not sent a temperature (see `temperature` in the rows) sampled at their "
              "own default; check the consistency table before reading their shortlist rates as probabilities.",
              "- A dry run uses random answers, so its numbers mean nothing." if dry_run else
              "- The 0-100 likelihoods are numbers the models chose freely; treat them as ordinal.",
              ""]
    path = Path(out_dir) / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ----------------------------- entry point -----------------------------

def analyze(cfg, dry_run=False):
    """Run every analysis, save the tables, figures and report, and print the main tables.
    Returns the descriptive summary table, or None if there is nothing to analyse."""
    out_dir = cfg.output_dir(dry_run)
    path = results_file(out_dir)
    if not path.exists():
        print(f"No results yet: {path} does not exist.")
        return None
    rows = load_rows(path)
    n_failed = sum(1 for r in rows if not r.get("ok"))
    if n_failed:
        print(f"{n_failed} failed calls excluded (see the 'error' column in {path.name})\n")
    df = prepare(cfg, rows, dry_run)
    if df is None:
        print("No usable rows.")
        return None

    effects = effects_by_cv(df)
    tables = {
        "summary": descriptive_table(df),
        "effects": effects,
        "h1": h1_table(df, effects),
        "h2": h2_table(cfg, df, effects),
        "consistency": consistency_table(df),
        "sessions": sessions_table(df),
        "likelihood": likelihood_table(df),
        "reasons": reasons_table(cfg, df),
    }
    files = {"summary": "summary.csv", "effects": "effects_by_cv.csv", "h1": "h1_class_effect.csv",
             "h2": "h2_explicit_vs_implicit.csv", "consistency": "consistency.csv", "sessions": "sessions.csv",
             "likelihood": "likelihood.csv", "reasons": "reasons.csv"}
    for key, name in files.items():
        tables[key].to_csv(out_dir / name, index=False)
    df.to_csv(out_dir / "all_calls_flat.csv", index=False)

    figures = out_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    plot_effects(cfg, tables["h1"], figures / "effects.png")
    plot_likelihoods(cfg, df, figures / "likelihoods.png")
    report = write_report(cfg, df, tables, out_dir, n_failed, dry_run)

    pd.set_option("display.width", 200)
    print("x = first variant listed for the arm in config.yaml (for the class arms, the higher-class CV)\n")
    print(tables["summary"].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nH1: shortlist effect (x minus y) with a 95% t-interval across base CVs\n")
    print(tables["h1"][["model", "arm", "n_calls", "n_cvs", "shortlist_effect", "shortlist_ci_low",
                        "shortlist_ci_high", "shortlist_t_p", "likelihood_effect"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nH2: implicit effect minus explicit effect, per base CV (above 0 = smaller effect when class is stated)\n")
    print(tables["h2"][["model", "implicit_shortlist_effect", "explicit_shortlist_effect",
                        "cv_level_mean_diff_implicit_minus_explicit", "cv_level_ci_low", "cv_level_ci_high",
                        "cv_level_t_p"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    per_cv = effects.pivot_table(index=["model", "arm"], columns="cv_id", values="shortlist_effect").round(2)
    print("\nShortlist effect (x minus y), per base CV:\n")
    print(per_cv.to_string())
    print(f"\nSaved tables to {out_dir}, figures to {figures}, and the report to {report}")
    return tables["summary"]
