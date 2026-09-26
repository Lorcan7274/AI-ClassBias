"""Analysis:  python -m pipeline analyze [--dry-run]

Keeps the descriptive tables of the first version and adds the tests of the two
hypotheses, position bias, consistency, ratings and shortlisting, the reason
keywords, three figures and a plain-English report. Everything is saved next to
the results file (results/, or results/dry_run/ for a dry run):

  summary.csv           descriptive table per model x arm (as before)
  all_calls_flat.csv    every successful call with the derived columns
  h1_class_effect.csv   pick rate of the higher-class CV with clustered 95% CIs
  h2_explicit_vs_implicit.csv
  position_bias.csv
  consistency.csv       agreement across the repeated calls of each pair
  sessions.csv          session 1 vs session 2
  ratings_shortlist.csv
  reasons.csv           keyword mentions in the one-sentence reasons
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
    df["picked_x"] = (df["preferred_variant"] == df["x_variant"]).astype(int)
    x_first = df["pos1_variant"] == df["x_variant"]
    df["x_first"] = x_first.astype(int)
    df["x_rating"] = np.where(x_first, df["pos1_rating"], df["pos2_rating"]).astype(float)
    df["y_rating"] = np.where(x_first, df["pos2_rating"], df["pos1_rating"]).astype(float)
    df["rating_diff"] = df["x_rating"] - df["y_rating"]
    df["x_shortlist"] = np.where(x_first, df["pos1_shortlist"], df["pos2_shortlist"]).astype(int)
    df["y_shortlist"] = np.where(x_first, df["pos2_shortlist"], df["pos1_shortlist"]).astype(int)
    df["x_reason"] = np.where(x_first, df["pos1_reason"], df["pos2_reason"])
    df["y_reason"] = np.where(x_first, df["pos2_reason"], df["pos1_reason"])
    df["picked_first"] = (df["preferred_position"] == 1).astype(int)
    return df


# ----------------------------- the tables -----------------------------

def descriptive_table(df) -> pd.DataFrame:
    """The table from the first version of the pipeline: naive percentages and a
    binomial test that treats every call as independent."""
    out = []
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        k, n = int(g["picked_x"].sum()), len(g)
        out.append({
            "model": model, "arm": arm, "n": n,
            "pct_pick_x": round(100 * k / n, 1),
            "p_vs_50": round(stats.binomial_p(k, n), 4),
            "mean_rating_diff_x_minus_y": round(g["rating_diff"].mean(), 2),
            "shortlist_x_pct": round(100 * g["x_shortlist"].mean(), 1),
            "shortlist_y_pct": round(100 * g["y_shortlist"].mean(), 1),
            "pct_pick_first_position": round(100 * g["picked_first"].mean(), 1),
        })
    return pd.DataFrame(out)


def h1_table(df) -> pd.DataFrame:
    """H1: does each model pick the higher-class CV (x) more than 50% of the time?

    Main estimate: pick rate with a 95% CI from a logistic regression with standard
    errors clustered by base CV. Cross-check: one pick rate per base CV, then a
    t-interval and a Wilcoxon test across the CVs. The naive Wilson interval that
    treats all calls as independent is shown last, for comparison only.
    """
    out = []
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        main = stats.clustered_rate(g["picked_x"], g["cv_id"])
        per_cv = g.groupby("cv_id")["picked_x"].mean()
        cv = stats.cv_level(per_cv.values, 0.5)
        naive = stats.wilson(main["k"], main["n"])
        out.append({
            "model": model, "arm": arm, "n_calls": main["n"], "n_cvs": main["n_clusters"],
            "pick_x_rate": main["rate"], "ci_low": main["low"], "ci_high": main["high"], "p_vs_50": main["p"],
            "cv_level_mean": cv["mean"], "cv_level_ci_low": cv["low"], "cv_level_ci_high": cv["high"],
            "cv_level_t_p": cv["t_p"], "cv_level_wilcoxon_p": cv["wilcoxon_p"],
            "naive_ci_low": naive[0], "naive_ci_high": naive[1], "note": main["note"],
        })
    return pd.DataFrame(out)


def h2_table(cfg, df) -> pd.DataFrame:
    """H2: is the class effect smaller when class is stated explicitly?

    Logistic regression on the two class arms together: picked_x ~ explicit, clustered
    by base CV. The odds ratio for `explicit` is the explicit-arm odds of picking the
    higher-class CV divided by the implicit-arm odds; below 1 means a smaller effect
    in the explicit arm (when the implicit rate is above 50%). Cross-check: for each
    base CV, its implicit pick rate minus its explicit pick rate, then a paired
    t-test and a Wilcoxon test across the CVs.
    """
    out = []
    for model, g in df.groupby("model", sort=True):
        imp = g[g["arm"] == cfg.implicit_arm]
        exp = g[g["arm"] == cfg.explicit_arm]
        both = pd.concat([imp, exp])
        effect = stats.clustered_odds_ratio(both["picked_x"], (both["arm"] == cfg.explicit_arm).astype(int),
                                            both["cv_id"])
        per_cv = pd.concat([imp.groupby("cv_id")["picked_x"].mean().rename("implicit"),
                            exp.groupby("cv_id")["picked_x"].mean().rename("explicit")], axis=1).dropna()
        paired = stats.cv_level((per_cv["implicit"] - per_cv["explicit"]).values, 0.0)
        out.append({
            "model": model,
            "implicit_pick_x_rate": imp["picked_x"].mean() if len(imp) else np.nan,
            "explicit_pick_x_rate": exp["picked_x"].mean() if len(exp) else np.nan,
            "odds_ratio_explicit_vs_implicit": effect["odds_ratio"], "ci_low": effect["low"],
            "ci_high": effect["high"], "p": effect["p"],
            "cv_level_mean_diff_implicit_minus_explicit": paired["mean"], "cv_level_ci_low": paired["low"],
            "cv_level_ci_high": paired["high"], "cv_level_t_p": paired["t_p"],
            "cv_level_wilcoxon_p": paired["wilcoxon_p"], "n_cvs_paired": paired["n_cvs"], "note": effect["note"],
        })
    return pd.DataFrame(out)


def position_table(df) -> pd.DataFrame:
    """Position bias: how often each model picks whoever is listed first, and whether
    the class effect survives controlling for position.

    Per model: the position-1 pick rate with a clustered CI. Per model x arm: a
    logistic regression picked_x ~ (x_first - 0.5), clustered by base CV. Centring
    x_first makes the intercept the class effect averaged over both positions
    ("adjusted pick rate"), and the odds ratio for x_first is the position effect.
    """
    out = []
    for model, g in df.groupby("model", sort=True):
        first = stats.clustered_rate(g["picked_first"], g["cv_id"])
        out.append({"model": model, "arm": "(all arms)", "n_calls": first["n"],
                    "pick_position1_rate": first["rate"], "position1_ci_low": first["low"],
                    "position1_ci_high": first["high"], "position1_p_vs_50": first["p"]})
        for arm, ga in g.groupby("arm", sort=True):
            adj = stats.clustered_odds_ratio(ga["picked_x"], ga["x_first"] - 0.5, ga["cv_id"])
            pos1 = stats.clustered_rate(ga["picked_first"], ga["cv_id"])
            out.append({
                "model": model, "arm": arm, "n_calls": len(ga),
                "pick_position1_rate": pos1["rate"], "position1_ci_low": pos1["low"],
                "position1_ci_high": pos1["high"], "position1_p_vs_50": pos1["p"],
                "pick_x_when_first": ga.loc[ga["x_first"] == 1, "picked_x"].mean(),
                "pick_x_when_second": ga.loc[ga["x_first"] == 0, "picked_x"].mean(),
                "adjusted_pick_x_rate": adj["base_rate"],
                "position_odds_ratio": adj["odds_ratio"], "position_ci_low": adj["low"],
                "position_ci_high": adj["high"], "position_p": adj["p"], "note": adj["note"],
            })
    return pd.DataFrame(out)


def consistency_table(df) -> pd.DataFrame:
    """Consistency: for each model x pair, how often the calls agreed with the pair's
    majority answer (1.0 = all 20 calls gave the same answer, 0.5 = a coin flip)."""
    out = []
    for (model, arm, pair_id), g in df.groupby(["model", "arm", "pair_id"], sort=True):
        rate = g["picked_x"].mean()
        by_order = g.groupby("order")["picked_x"].mean()
        out.append({
            "model": model, "arm": arm, "pair_id": pair_id, "n_calls": len(g),
            "pick_x_rate": rate, "agreement_with_majority": max(rate, 1 - rate),
            "pick_x_rate_when_x_first": by_order.get("xy", np.nan),
            "pick_x_rate_when_x_second": by_order.get("yx", np.nan),
            # Did the answer flip with the order? 0 = same rate in both orders.
            "order_gap": abs(by_order.get("xy", np.nan) - by_order.get("yx", np.nan)),
        })
    return pd.DataFrame(out)


def sessions_table(df) -> pd.DataFrame:
    """Session 1 vs session 2: pick rates per session, the odds ratio for being in
    the later session (clustered by base CV), and the mean absolute change in each
    pair's pick rate between the sessions."""
    sessions = sorted(df["session"].unique())
    out = []
    if len(sessions) < 2:
        return pd.DataFrame(out)
    s1, s2 = sessions[:2]
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        g = g[g["session"].isin([s1, s2])]
        effect = stats.clustered_odds_ratio(g["picked_x"], (g["session"] == s2).astype(int), g["cv_id"])
        per_pair = g.groupby(["pair_id", "session"])["picked_x"].mean().unstack("session")
        gap = (per_pair[s1] - per_pair[s2]).abs().mean() if s1 in per_pair and s2 in per_pair else np.nan
        out.append({
            "model": model, "arm": arm, "session_1": s1, "session_2": s2,
            "pick_x_rate_session_1": g.loc[g["session"] == s1, "picked_x"].mean(),
            "pick_x_rate_session_2": g.loc[g["session"] == s2, "picked_x"].mean(),
            "odds_ratio_session_2_vs_1": effect["odds_ratio"], "ci_low": effect["low"], "ci_high": effect["high"],
            "p": effect["p"], "mean_abs_change_per_pair": gap, "note": effect["note"],
        })
    return pd.DataFrame(out)


def ratings_table(df) -> pd.DataFrame:
    """Ratings and shortlisting: each call rates both CVs, so the difference (x minus
    y) is a paired comparison within the call. Its mean gets a CI clustered by base
    CV; the same for the shortlist difference (x shortlisted minus y shortlisted)."""
    out = []
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        rating = stats.clustered_mean(g["rating_diff"], g["cv_id"])
        shortlist = stats.clustered_mean(g["x_shortlist"] - g["y_shortlist"], g["cv_id"])
        out.append({
            "model": model, "arm": arm, "n_calls": len(g),
            "mean_rating_x": g["x_rating"].mean(), "mean_rating_y": g["y_rating"].mean(),
            "mean_rating_diff": rating["mean"], "rating_ci_low": rating["low"], "rating_ci_high": rating["high"],
            "rating_p": rating["p"],
            "shortlist_x_rate": g["x_shortlist"].mean(), "shortlist_y_rate": g["y_shortlist"].mean(),
            "shortlist_diff": shortlist["mean"], "shortlist_ci_low": shortlist["low"],
            "shortlist_ci_high": shortlist["high"], "shortlist_p": shortlist["p"],
        })
    return pd.DataFrame(out)


def keyword_pattern(keyword) -> re.Pattern:
    """A whole-word pattern for one keyword; a trailing * also matches longer words."""
    if keyword.endswith("*"):
        return re.compile(r"\b" + re.escape(keyword[:-1]) + r"\w*", re.IGNORECASE)
    return re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)


def reasons_table(cfg, df) -> pd.DataFrame:
    """How often the one-sentence reasons mention class-related words (the list is
    analysis.reason_keywords in config.yaml), for the higher-class (x) and the other
    (y) CV separately. The "(any keyword)" rows count reasons with at least one hit."""
    patterns = {k: keyword_pattern(k) for k in cfg.reason_keywords}
    out = []
    for (model, arm), g in df.groupby(["model", "arm"], sort=True):
        x_reasons, y_reasons = g["x_reason"].fillna("").astype(str), g["y_reason"].fillna("").astype(str)
        n = len(g)
        any_x = np.zeros(n, dtype=bool)
        any_y = np.zeros(n, dtype=bool)
        rows = []
        for keyword, pattern in patterns.items():
            hits_x = x_reasons.map(lambda t: bool(pattern.search(t))).values
            hits_y = y_reasons.map(lambda t: bool(pattern.search(t))).values
            any_x |= hits_x
            any_y |= hits_y
            rows.append({"model": model, "arm": arm, "keyword": keyword, "n_reasons": n,
                         "x_mentions": int(hits_x.sum()), "x_pct": 100 * hits_x.mean(),
                         "y_mentions": int(hits_y.sum()), "y_pct": 100 * hits_y.mean()})
        out.append({"model": model, "arm": arm, "keyword": "(any keyword)", "n_reasons": n,
                    "x_mentions": int(any_x.sum()), "x_pct": 100 * any_x.mean(),
                    "y_mentions": int(any_y.sum()), "y_pct": 100 * any_y.mean()})
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


def plot_pick_rates(cfg, h1, path):
    """One panel per model: pick rate of the higher-class (x) CV per arm, with the
    clustered 95% CI, and a line at 50%."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = sorted(h1["model"].unique())
    arms = list(cfg.arms)
    fig, axes = plt.subplots(1, len(models), figsize=(3.2 * len(models) + 1, 3.8), sharey=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax, model in zip(axes[0], models):
        _style(ax, panel_title(model))
        ax.axhline(50, color=INK_SOFT, linewidth=1, linestyle="-")
        for i, arm in enumerate(arms):
            row = h1[(h1["model"] == model) & (h1["arm"] == arm)]
            if row.empty:
                continue
            r = row.iloc[0]
            rate, low, high = 100 * r["pick_x_rate"], 100 * r["ci_low"], 100 * r["ci_high"]
            colour = ARM_COLOURS[i % len(ARM_COLOURS)]
            if not np.isnan(low):
                ax.plot([i, i], [low, high], color=colour, linewidth=2, solid_capstyle="round")
            ax.plot(i, rate, "o", color=colour, markersize=8)
            ax.annotate(f"{rate:.0f}%", (i, rate), xytext=(8, 0), textcoords="offset points",
                        fontsize=8, color=INK, va="center")
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels(arms, rotation=0)
        ax.set_xlim(-0.6, len(arms) - 0.4)
    axes[0][0].set_ylabel("% of calls picking the higher-class CV\n(x variant; 95% CI clustered by base CV)",
                          color=INK_SOFT, fontsize=8)
    axes[0][0].set_ylim(0, 100)
    fig.suptitle("H1: pick rate of the higher-class CV, per model and arm", color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_rating_differences(cfg, df, path):
    """Rows = models, columns = arms: how the rating difference (x minus y) is spread."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = sorted(df["model"].unique())
    arms = list(cfg.arms)
    fig, axes = plt.subplots(len(models), len(arms), figsize=(3 * len(arms) + 1, 2.2 * len(models) + 1),
                             sharex=True, sharey="row", squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    values = np.arange(-9, 10)
    for r, model in enumerate(models):
        for c, arm in enumerate(arms):
            ax = axes[r][c]
            g = df[(df["model"] == model) & (df["arm"] == arm)]
            counts = g["rating_diff"].value_counts().reindex(values, fill_value=0)
            _style(ax, arm if r == 0 else "")
            ax.bar(values, counts.values, width=0.8, color=ARM_COLOURS[c % len(ARM_COLOURS)])
            ax.axvline(0, color=INK_SOFT, linewidth=1)
            mean = g["rating_diff"].mean() if len(g) else np.nan
            if not np.isnan(mean):
                ax.annotate(f"mean {mean:+.2f}", (0.98, 0.9), xycoords="axes fraction", ha="right",
                            fontsize=8, color=INK)
            if r == len(models) - 1:
                ax.set_xlabel("rating of x minus rating of y", color=INK_SOFT, fontsize=8)
            if c == 0:
                ax.set_ylabel(f"{short_model(model)}\ncalls", color=INK, fontsize=8)
    fig.suptitle("Rating differences (higher-class CV minus the other): rows = models, columns = arms",
                 color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_position_bias(cfg, position, path):
    """Left: how often each model picks Candidate 1, with CI. Right, one panel per
    model: pick rate of the higher-class CV when it is shown first vs second, per arm."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    overall = position[position["arm"] == "(all arms)"].reset_index(drop=True)
    by_arm = position[position["arm"] != "(all arms)"]
    models = list(overall["model"])
    arms = list(cfg.arms)
    fig = plt.figure(figsize=(3.6 + 2.9 * len(models), 4.4))
    fig.patch.set_facecolor(SURFACE)
    grid = fig.add_gridspec(1, 1 + len(models), width_ratios=[1.6] + [1] * len(models), wspace=0.35)

    ax1 = fig.add_subplot(grid[0, 0])
    _style(ax1, "Share of calls picking Candidate 1")
    ax1.axhline(50, color=INK_SOFT, linewidth=1)
    for i, r in overall.iterrows():
        rate, low, high = 100 * r["pick_position1_rate"], 100 * r["position1_ci_low"], 100 * r["position1_ci_high"]
        if not np.isnan(low):
            ax1.plot([i, i], [low, high], color=INK_SOFT, linewidth=2, solid_capstyle="round")
        ax1.plot(i, rate, "o", color=INK, markersize=7)
        ax1.annotate(f"{rate:.0f}%", (i, rate), xytext=(7, 0), textcoords="offset points", fontsize=8,
                     color=INK, va="center")
    ax1.set_xticks(range(len(models)))
    ax1.set_xticklabels([panel_title(m) for m in models], rotation=30, ha="right", fontsize=7)
    ax1.set_xlim(-0.6, len(models) - 0.4)
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("% picking Candidate 1, all arms\n(95% CI clustered by base CV)", color=INK_SOFT, fontsize=8)

    first_axis = None
    for j, model in enumerate(models):
        ax = fig.add_subplot(grid[0, 1 + j], sharey=first_axis)
        first_axis = first_axis or ax
        _style(ax, panel_title(model))
        ax.axhline(50, color=INK_SOFT, linewidth=1)
        for i, arm in enumerate(arms):
            row = by_arm[(by_arm["model"] == model) & (by_arm["arm"] == arm)]
            if row.empty:
                continue
            r = row.iloc[0]
            colour = ARM_COLOURS[i % len(ARM_COLOURS)]
            first, second = 100 * r["pick_x_when_first"], 100 * r["pick_x_when_second"]
            ax.plot([i, i], [first, second], color=colour, linewidth=1)
            ax.plot(i, first, "o", color=colour, markersize=7)
            ax.plot(i, second, "o", markerfacecolor=SURFACE, markeredgecolor=colour, markersize=7)
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels(arms, fontsize=7, rotation=20, ha="right")
        ax.set_xlim(-0.6, len(arms) - 0.4)
        ax.set_ylim(0, 100)
        if j > 0:
            ax.tick_params(labelleft=False)
    if first_axis is not None:
        first_axis.set_ylabel("% picking the higher-class CV\nwhen shown first (filled) vs second (hollow)",
                              color=INK_SOFT, fontsize=8)
    fig.suptitle("Position bias", color=INK, fontsize=11, x=0.01, ha="left")
    fig.savefig(path, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


# ----------------------------- the report -----------------------------

def significance(p) -> str:
    if p is None or np.isnan(p):
        return "no test possible"
    return "significant at 5%" if p < 0.05 else "not significant at 5%"


def write_report(cfg, df, tables, out_dir, n_failed, dry_run) -> Path:
    """results/report.md: every table in plain English, with the figures linked."""
    h1, h2, pos, cons, sess, rat, reas = (tables[k] for k in
                                          ("h1", "h2", "position", "consistency", "sessions", "ratings", "reasons"))
    models = sorted(df["model"].unique())
    sessions = sorted(df["session"].unique())
    lines = [f"# CV class-bias study: results{' (DRY RUN, fake answers)' if dry_run else ''}", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from `{results_file(out_dir)}`.", "",
             "## Data", "",
             f"- {len(df)} successful calls ({n_failed} failed calls excluded), "
             f"{df['pair_id'].nunique()} pairs from {df['cv_id'].nunique()} base CVs, "
             f"{len(models)} models, sessions: {', '.join(sessions)}.",
             f"- Arms and their variants: " + "; ".join(f"{a} = {x} vs {y}" for a, (x, y) in cfg.arms.items())
             + ". In the tables, x is the first variant of each arm (for the class arms, the higher-class CV).",
             f"- Prompt hashes in the data: {', '.join(sorted(df['prompt_hash'].astype(str).str[:12].unique()))}.",
             "", "How the tests deal with repeated calls: the calls on one base CV share its wording and are "
             "not independent, so every confidence interval below comes from a regression with standard "
             "errors clustered by base CV, or from one number per base CV. The naive intervals that treat "
             "every call as independent are shown only for comparison.", ""]

    lines += ["## Descriptive table (as in the first version of the pipeline)", "",
              "Percentages of all calls; `p_vs_50` is a plain binomial test that ignores clustering.", "",
              md_table(tables["summary"], 4), ""]

    lines += ["## H1: do the models pick the higher-class CV more than 50% of the time?", "",
              "`pick_x_rate` is the share of calls picking the higher-class CV (for the demographic arm, "
              "variant a), with a 95% CI clustered by base CV. H1 is supported for a model and arm when the "
              "whole interval lies above 50%.", ""]
    show = h1[["model", "arm", "n_calls", "pick_x_rate", "ci_low", "ci_high", "p_vs_50",
               "cv_level_mean", "cv_level_ci_low", "cv_level_ci_high", "cv_level_t_p", "cv_level_wilcoxon_p"]].copy()
    lines += [md_table(show, 3), ""]
    for _, r in h1.iterrows():
        verdict = ("above 50%" if r["ci_low"] > 0.5 else "below 50%" if r["ci_high"] < 0.5 else "includes 50%") \
            if not np.isnan(r["ci_low"]) else "no interval"
        lines.append(f"- {r['model']}, {r['arm']}: picks x in {pct(r['pick_x_rate'])} of calls "
                     f"(95% CI {pct(r['ci_low'])} to {pct(r['ci_high'])}, {verdict}; {significance(r['p_vs_50'])}). "
                     f"CV-level cross-check: mean {pct(r['cv_level_mean'])}, t-test p = {fmt(r['cv_level_t_p'])}, "
                     f"Wilcoxon p = {fmt(r['cv_level_wilcoxon_p'])}."
                     + (f" Note: {r['note']}." if r["note"] else ""))
    lines += ["", "![pick rates](figures/pick_rates.png)", ""]

    lines += [f"## H2: is the effect smaller when class is stated explicitly ({cfg.explicit_arm} vs "
              f"{cfg.implicit_arm})?", "",
              "Odds ratio for the explicit arm from a logistic regression on both class arms, clustered by "
              "base CV. Below 1 means the explicit arm picks the higher-class CV less often than the implicit "
              "arm. The CV-level row is the mean of (implicit rate minus explicit rate) across base CVs.", "",
              md_table(h2, 3), ""]
    for _, r in h2.iterrows():
        lines.append(f"- {r['model']}: implicit {pct(r['implicit_pick_x_rate'])} vs explicit "
                     f"{pct(r['explicit_pick_x_rate'])}; odds ratio {fmt(r['odds_ratio_explicit_vs_implicit'])} "
                     f"(95% CI {fmt(r['ci_low'])} to {fmt(r['ci_high'])}), {significance(r['p'])}. "
                     f"CV-level mean difference {fmt(r['cv_level_mean_diff_implicit_minus_explicit'])} "
                     f"(paired t-test p = {fmt(r['cv_level_t_p'])}, Wilcoxon p = {fmt(r['cv_level_wilcoxon_p'])}).")
    lines += [""]

    lines += ["## Position bias", "",
              "`pick_position1_rate` is how often the model preferred whichever CV was listed first. "
              "`adjusted_pick_x_rate` is the class effect after controlling for position (the pick rate of "
              "the higher-class CV averaged over both positions); `position_odds_ratio` is the odds of picking "
              "the higher-class CV when it is shown first relative to second.", "",
              md_table(pos[["model", "arm", "n_calls", "pick_position1_rate", "position1_ci_low", "position1_ci_high",
                            "pick_x_when_first", "pick_x_when_second", "adjusted_pick_x_rate",
                            "position_odds_ratio", "position_ci_low", "position_ci_high", "position_p"]], 3), "",
              "![position bias](figures/position_bias.png)", ""]

    lines += ["## Consistency across the repeated calls of each pair", "",
              "`agreement_with_majority` is the share of a pair's calls that gave the pair's most common "
              "answer (1 = always the same answer, 0.5 = a coin flip). `order_gap` is how much the pick "
              "rate changed when the two CVs swapped places.", ""]
    cons_summary = cons.groupby(["model", "arm"], sort=True).agg(
        n_pairs=("pair_id", "nunique"), mean_agreement=("agreement_with_majority", "mean"),
        pairs_fully_consistent=("agreement_with_majority", lambda s: int((s >= 0.999).sum())),
        mean_order_gap=("order_gap", "mean")).reset_index()
    lines += [md_table(cons_summary, 3), "", "The full per-pair table is in `consistency.csv`.", ""]

    lines += ["## Session 1 vs session 2", ""]
    if sess.empty:
        lines += ["Only one session so far, so there is nothing to compare yet.", ""]
    else:
        lines += ["Pick rates in each session and the odds ratio for the later session (clustered by base CV). "
                  "`mean_abs_change_per_pair` is the average absolute change in a pair's pick rate between "
                  "the sessions.", "", md_table(sess, 3), ""]

    lines += ["## Ratings and shortlisting", "",
              "Each call rates both CVs, so the rating difference (higher-class CV minus the other) is a "
              "paired comparison within the call; its mean has a 95% CI clustered by base CV. The "
              "shortlist difference is the share of calls shortlisting x minus the share shortlisting y.", "",
              md_table(rat, 3), "", "![rating differences](figures/rating_differences.png)", ""]

    lines += ["## What the reasons mention", "",
              "Share of one-sentence reasons mentioning each keyword (analysis.reason_keywords in "
              "config.yaml), for the higher-class CV (x) and the other CV (y).", "",
              md_table(reas[reas["keyword"] == "(any keyword)"][["model", "arm", "n_reasons", "x_pct", "y_pct"]], 1),
              "", "Per keyword (only keywords mentioned at least once):", "",
              md_table(reas[(reas["keyword"] != "(any keyword)") & ((reas["x_mentions"] + reas["y_mentions"]) > 0)]
                       [["model", "arm", "keyword", "x_mentions", "x_pct", "y_mentions", "y_pct"]], 1), ""]

    lines += ["## Caveats", "",
              "- Position bias can be large; the design sends every pair in both orders so it cancels in "
              "the pick rates, but check the position table before trusting a small class effect.",
              "- Calls on the same base CV are not independent; the clustered intervals handle this, "
              "but with 15 base CVs the intervals are wide and a single unusual CV can move a result.",
              "- Twelve model-by-arm comparisons are tested; expect about one false positive at the 5% "
              "level by chance alone.",
              "- The models may have changed between sessions (see `served_model` and `provider` in the "
              "results), and the answers depend on the exact prompt (`prompt_hash`).",
              "- A dry run uses random answers, so its numbers mean nothing." if dry_run else
              "- Rating differences are on a 1 to 10 scale the models chose freely; treat them as ordinal.",
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

    tables = {
        "summary": descriptive_table(df),
        "h1": h1_table(df),
        "h2": h2_table(cfg, df),
        "position": position_table(df),
        "consistency": consistency_table(df),
        "sessions": sessions_table(df),
        "ratings": ratings_table(df),
        "reasons": reasons_table(cfg, df),
    }
    files = {"summary": "summary.csv", "h1": "h1_class_effect.csv", "h2": "h2_explicit_vs_implicit.csv",
             "position": "position_bias.csv", "consistency": "consistency.csv", "sessions": "sessions.csv",
             "ratings": "ratings_shortlist.csv", "reasons": "reasons.csv"}
    for key, name in files.items():
        tables[key].to_csv(out_dir / name, index=False)
    df.to_csv(out_dir / "all_calls_flat.csv", index=False)

    figures = out_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    plot_pick_rates(cfg, tables["h1"], figures / "pick_rates.png")
    plot_rating_differences(cfg, df, figures / "rating_differences.png")
    plot_position_bias(cfg, tables["position"], figures / "position_bias.png")
    report = write_report(cfg, df, tables, out_dir, n_failed, dry_run)

    pd.set_option("display.width", 200)
    print("x = first variant listed for the arm in config.yaml (for the class arms, the higher-class CV)\n")
    print(tables["summary"].to_string(index=False))
    print("\nH1: pick rate of x with 95% CI clustered by base CV\n")
    print(tables["h1"][["model", "arm", "n_calls", "pick_x_rate", "ci_low", "ci_high", "p_vs_50"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nH2: odds ratio for the explicit arm (below 1 = smaller effect when class is stated)\n")
    print(tables["h2"][["model", "implicit_pick_x_rate", "explicit_pick_x_rate", "odds_ratio_explicit_vs_implicit",
                        "ci_low", "ci_high", "p"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    per_cv = df.groupby(["model", "arm", "cv_id"])["picked_x"].mean().unstack("cv_id").round(2)
    print("\nShare picking x, per base CV:\n")
    print(per_cv.to_string())
    print(f"\nSaved tables to {out_dir}, figures to {figures}, and the report to {report}")
    return tables["summary"]
