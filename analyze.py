"""
Summarise results/results.jsonl.

For each model x arm:
  - share of calls picking variant x (for class arms: the higher-class CV)
  - binomial test vs 50%
  - mean rating difference (x minus y)
  - position bias: share picking whoever was listed first

Usage:  python analyze.py            (all sessions, dry-run rows excluded)
        python analyze.py --include-dry-run
"""

import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.stats import binomtest

from run_pipeline import ARMS, OUT_FILE


def load(include_dry):
    rows = [json.loads(l) for l in OUT_FILE.open(encoding="utf-8")]
    df = pd.DataFrame(rows)
    n_err = (~df["ok"]).sum()
    if n_err:
        print(f"{n_err} failed calls excluded (see 'error' column in results.jsonl)\n")
    df = df[df["ok"]]
    if not include_dry:
        df = df[~df["dry_run"]]
    return df.copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-dry-run", action="store_true")
    args = ap.parse_args()
    df = load(args.include_dry_run)
    if df.empty:
        print("No usable rows.")
        return

    df["x_variant"] = df["arm"].map(lambda a: ARMS[a][0])
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
            f"pct_pick_x": round(100 * k / n, 1),
            "p_vs_50": round(binomtest(k, n, 0.5).pvalue, 4),
            "mean_rating_diff_x_minus_y": round((g["x_rating"] - g["y_rating"]).mean(), 2),
            "shortlist_x_pct": round(100 * g["x_shortlist"].mean(), 1),
            "shortlist_y_pct": round(100 * g["y_shortlist"].mean(), 1),
            "pct_pick_first_position": round(100 * g["picked_first"].mean(), 1),
        })
    summary = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    print("x = first variant in ARMS (for class arms, the higher-class CV)\n")
    print(summary.to_string(index=False))

    # Per base CV: helps spot whether one CV drives the effect
    per_cv = df.groupby(["model", "arm", "cv_id"])["picked_x"].mean().unstack("cv_id").round(2)
    print("\nShare picking x, per base CV:\n")
    print(per_cv.to_string())

    Path("results").mkdir(exist_ok=True)
    summary.to_csv("results/summary.csv", index=False)
    df.to_csv("results/all_calls_flat.csv", index=False)
    print("\nSaved results/summary.csv and results/all_calls_flat.csv")


if __name__ == "__main__":
    main()
