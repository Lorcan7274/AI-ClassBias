"""Summarise the results file.

For each model x arm:
  - share of calls picking variant x (for the class arms: the higher-class CV)
  - binomial test against 50%
  - mean rating difference (x minus y)
  - shortlist rates for x and y
  - position bias: share picking whoever was listed first
Plus the share picking x for each base CV, which shows whether one CV drives the effect.
"""

from __future__ import annotations

import json

import pandas as pd
from scipy.stats import binomtest

from pipeline.runner import results_file


def load_rows(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def analyze(cfg, dry_run=False):
    """Print the summary tables and save them as CSV files next to the results file.
    Returns the summary table, or None if there is nothing to analyse."""
    out_dir = cfg.output_dir(dry_run)
    path = results_file(out_dir)
    if not path.exists():
        print(f"No results yet: {path} does not exist.")
        return None
    df = pd.DataFrame(load_rows(path))
    if df.empty:
        print(f"{path} is empty.")
        return None

    n_failed = int((~df["ok"]).sum())
    if n_failed:
        print(f"{n_failed} failed calls excluded (see the 'error' column in {path.name})\n")
    df = df[df["ok"]]
    if not dry_run:
        # Safety net: the real results file should never hold dry-run rows, but if it
        # does (e.g. from the old single-file set-up), never count them as real data.
        df = df[~df["dry_run"]]
    unknown_arms = sorted(set(df["arm"]) - set(cfg.arms))
    if unknown_arms:
        print(f"WARNING: skipping rows for arms that are not in config.yaml: {unknown_arms}\n")
        df = df[df["arm"].isin(list(cfg.arms))]
    if df.empty:
        print("No usable rows.")
        return None
    df = df.copy()

    df["x_variant"] = df["arm"].map(lambda a: cfg.arms[a][0])
    df["picked_x"] = df["preferred_variant"] == df["x_variant"]
    df["x_rating"] = df.apply(lambda r: r.pos1_rating if r.pos1_variant == r.x_variant else r.pos2_rating, axis=1)
    df["y_rating"] = df.apply(lambda r: r.pos2_rating if r.pos1_variant == r.x_variant else r.pos1_rating, axis=1)
    df["x_shortlist"] = df.apply(lambda r: r.pos1_shortlist if r.pos1_variant == r.x_variant else r.pos2_shortlist, axis=1)
    df["y_shortlist"] = df.apply(lambda r: r.pos2_shortlist if r.pos1_variant == r.x_variant else r.pos1_shortlist, axis=1)
    df["picked_first"] = df["preferred_position"] == 1

    out = []
    for (model, arm), g in df.groupby(["model", "arm"]):
        k, n = int(g["picked_x"].sum()), len(g)
        out.append({
            "model": model, "arm": arm, "n": n,
            "pct_pick_x": round(100 * k / n, 1),
            "p_vs_50": round(binomtest(k, n, 0.5).pvalue, 4),
            "mean_rating_diff_x_minus_y": round((g["x_rating"] - g["y_rating"]).mean(), 2),
            "shortlist_x_pct": round(100 * g["x_shortlist"].mean(), 1),
            "shortlist_y_pct": round(100 * g["y_shortlist"].mean(), 1),
            "pct_pick_first_position": round(100 * g["picked_first"].mean(), 1),
        })
    summary = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    print("x = first variant listed for the arm in config.yaml (for the class arms, the higher-class CV)\n")
    print(summary.to_string(index=False))

    # Per base CV: helps spot whether one CV drives the effect
    per_cv = df.groupby(["model", "arm", "cv_id"])["picked_x"].mean().unstack("cv_id").round(2)
    print("\nShare picking x, per base CV:\n")
    print(per_cv.to_string())

    summary.to_csv(out_dir / "summary.csv", index=False)
    df.to_csv(out_dir / "all_calls_flat.csv", index=False)
    print(f"\nSaved {out_dir / 'summary.csv'} and {out_dir / 'all_calls_flat.csv'}")
    return summary
