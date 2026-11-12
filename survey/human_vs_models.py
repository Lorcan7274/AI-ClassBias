"""People against the models on the same CVs:  python survey/human_vs_models.py

Reads survey/form_responses.csv (written by form_responses.py) and the models'
implicit-arm calls in results/all_calls_flat.csv, and writes
results/human_vs_models.csv (one row per CV people saw, with each model's rates on
it) and results/human_vs_models.md (the comparison).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.stats import sign_test  # noqa: E402

RESPONSES = ROOT / "survey" / "form_responses.csv"
CALLS = ROOT / "results" / "all_calls_flat.csv"
OUT_CSV = ROOT / "results" / "human_vs_models.csv"
OUT_MD = ROOT / "results" / "human_vs_models.md"
SHORT = {"anthropic/claude-opus-5.5": "Claude", "openai/gpt-6.1-sol-pro": "GPT",
         "google/gemini-4-argon": "Gemini", "meta-llama/llama-4-maverick": "Llama"}
ANSWERS = ["interview", "likelihood", "guess_private", "parents_guess"]


def load(responses: Path = RESPONSES, calls: Path = CALLS) -> tuple[pd.DataFrame, pd.DataFrame]:
    humans = pd.read_csv(responses, dtype={"card": str})
    models = pd.read_csv(calls)
    models = models[(models["ok"].astype(str) == "True") & (models["arm"] == "implicit")].copy()
    models["name"] = models["model"].map(lambda m: SHORT.get(m, m))
    return humans, models


def model_names(models: pd.DataFrame) -> list[str]:
    present = set(models["name"])
    return [n for n in SHORT.values() if n in present] + sorted(present - set(SHORT.values()))


def per_cv(humans: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    table = (humans.groupby(["stimulus_id", "cv_id", "variant"])
             .agg(n_people=("interview", "size"), people_interview=("interview", "mean"),
                  people_likelihood=("likelihood", "mean"))
             .reset_index())
    table["people_likelihood"] *= 10  # the form's 0-10 scale onto the models' 0-100
    for name in model_names(models):
        g = models[models["name"] == name].groupby("stimulus_id")
        table[f"{name}_shortlist"] = table["stimulus_id"].map(g["shortlist"].mean())
        table[f"{name}_likelihood"] = table["stimulus_id"].map(g["likelihood"].mean())
    return table.sort_values(["cv_id", "variant"]).reset_index(drop=True)


def _pct(x) -> str:
    return "" if pd.isna(x) else f"{x:.0%}"


def _num(x, signed=False) -> str:
    return "" if pd.isna(x) else (f"{x:+.1f}" if signed else f"{x:.1f}")


def _p(p) -> str:
    return "" if pd.isna(p) else ("<0.001" if p < 0.001 else f"{p:.2f}")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(r) + " |" for r in rows])


def levels(table: pd.DataFrame, names: list[str]) -> list[str]:
    """Each source's rates on the CVs people saw, weighted by how many people saw each,
    so every row describes the same mix of CVs."""
    def weighted(col, variant=None):
        t = table if variant is None else table[table["variant"] == variant]
        return float(np.average(t[col], weights=t["n_people"])) if len(t) else np.nan

    rows = []
    for label, rate, like in [("People", "people_interview", "people_likelihood")] + \
                             [(n, f"{n}_shortlist", f"{n}_likelihood") for n in names]:
        rows.append([label] + [_pct(weighted(rate, v)) for v in (None, "high", "low")]
                    + [_num(weighted(like, v)) for v in (None, "high", "low")])
    return _table(["", "interview / shortlist", "higher-class", "lower-class",
                   "likelihood (0-100)", "higher-class", "lower-class"], rows)


def effects(table: pd.DataFrame, models: pd.DataFrame, names: list[str]) -> tuple[list[str], list[str], dict]:
    """Higher-class minus lower-class version, on the bases where people saw both."""
    both = sorted(b for b, g in table.groupby("cv_id") if set(g["variant"]) >= {"high", "low"})
    wide = table[table["cv_id"].isin(both)].set_index(["cv_id", "variant"])

    def diff(col):
        return pd.Series({b: wide.loc[(b, "high"), col] - wide.loc[(b, "low"), col] for b in both}, dtype=float)

    people = diff("people_interview")
    test = sign_test(people.values) if both else {"pos": 0, "neg": 0, "ties": 0, "p": np.nan}
    out = []
    for measure, people_col, suffix, fmt in [("interview / shortlist, percentage points", "people_interview",
                                              "shortlist", lambda x: _num(100 * x, signed=True)),
                                             ("likelihood (0-100)", "people_likelihood", "likelihood",
                                              lambda x: _num(x, signed=True))]:
        rows = []
        d = diff(people_col)
        rows.append(["People"] + [fmt(d[b]) for b in both] + [fmt(d.mean()), ""])
        for n in names:
            d = diff(f"{n}_{suffix}")
            g = models[models["name"] == n].groupby(["cv_id", "variant"])[suffix].mean().unstack()
            all15 = (g["high"] - g["low"]).mean()
            rows.append([n] + [fmt(d[b]) for b in both] + [fmt(d.mean()), fmt(all15)])
        out.append((measure, _table([""] + both + ["mean", "all 15 bases"], rows)))
    return out, both, test


def agreement(table: pd.DataFrame, names: list[str]) -> list[str]:
    def rho(a, b):
        if len(table) < 3 or table[a].nunique() < 2 or table[b].nunique() < 2:
            return np.nan, np.nan
        return stats.spearmanr(table[a], table[b])

    def signed(r):
        return "" if pd.isna(r) else f"{r:+.2f}"

    rows = []
    for n in names:
        r, p = rho("people_likelihood", f"{n}_likelihood")
        others = [rho(f"{n}_likelihood", f"{o}_likelihood")[0] for o in names if o != n]
        rows.append([n, f"{len(table)}", signed(r), _p(p), signed(np.median(others)) if others else ""])
    return _table(["model", "CVs", "Spearman rho with people's likelihood", "p",
                   "median rho with the other models"], rows)


def manipulation(humans: pd.DataFrame) -> tuple[list[str], float]:
    rows, counts = [], {}
    for v in ("high", "low"):
        g = humans[humans["variant"] == v]
        private = int((g["guess_private"] == 1).sum())
        state = int((g["guess_private"] == 0).sum())
        counts[v] = (private, state)
        rows.append([f"{v}er-class version", str(len(g)), str(private), str(state),
                     str(int(g["guess_private"].isna().sum())), _pct(private / (private + state)) if private + state else ""])
    p = stats.fisher_exact([counts["high"], counts["low"]]).pvalue if all(sum(c) for c in counts.values()) else np.nan
    return _table(["", "people", "private", "state", "no idea", "private, of those who guessed"], rows), p


def duplicates(humans: pd.DataFrame) -> list[str]:
    key = humans[["card"] + ANSWERS].fillna("").astype(str).agg("|".join, axis=1)
    return [", ".join(g["participant_id"]) for _, g in humans.groupby(key) if len(g) > 1]


def report(humans: pd.DataFrame, models: pd.DataFrame, table: pd.DataFrame) -> str:
    names = model_names(models)
    n_high = int((humans["variant"] == "high").sum())
    lines = [
        "# People and models on the same CVs", "",
        f"{len(humans)} responses to the online form, {n_high} on a higher-class and {len(humans) - n_high} on a "
        f"lower-class version, covering {len(table)} of the 30 implicit-arm CVs "
        f"({(table['variant'] == 'high').sum()} higher-class, {(table['variant'] == 'low').sum()} lower-class). "
        f"Each person saw one CV on its own; each model saw it after nine fillers, "
        f"{models.groupby(['name', 'stimulus_id']).size().median():.0f} times (both sessions pooled). "
        "Both were told only 3 in 10 applicants get an interview. People's 0-10 likelihood is shown ×10.", "",
        "## 1. How often each says yes, on the CVs people saw", "",
        "Model rates are each CV's rate weighted by the number of people who saw it, so every row covers the "
        "same mix of CVs.", "",
        *levels(table, names), "",
        "The higher-class and lower-class columns cover different bases, so a gap between them can come from "
        "which bases people happened to see rather than from class; a model showing the same gap is the sign "
        "of that. Section 2 holds the base fixed.", "",
    ]
    tables, both, test = effects(table, models, names)
    lines += ["## 2. Higher-class minus lower-class version", "",
              f"Only the {len(both)} bases on which people saw both versions. The last column is each model's "
              "effect over all fifteen bases, for scale.", ""]
    for measure, t in tables:
        lines += [f"**{measure}**", "", *t, ""]
    lines += [f"People's sign test on interview: {test['pos']} bases for the higher-class version, "
              f"{test['neg']} for the lower-class one, {test['ties']} tied, p = {_p(test['p'])}.", "",
              "## 3. Do people and models agree on which CVs are stronger?", "",
              "Across the CVs people saw, each CV's mean human likelihood against the model's. The last column "
              "is how far the models agree with one another on the same CVs, for scale.", "",
              *agreement(table, names), ""]
    t, p = manipulation(humans)
    lines += ["## 4. Manipulation check: what people guessed", "", *t, "",
              f"Fisher's exact test on private against state guesses: p = {_p(p)}.", "",
              "Parents' jobs, as written:", ""]
    for v in ("high", "low"):
        guesses = "; ".join(f"\"{s.strip()}\"" for s in humans.loc[humans["variant"] == v, "parents_guess"].dropna())
        lines.append(f"- {v}er-class version: {guesses}")
    dup = duplicates(humans)
    lines += ["", "## 5. Data notes", "",
              f"- {int((humans['card_matches_day'] == 1).sum())} of {len(humans)} responses are on the card their "
              "birth day points to."]
    if dup:
        lines.append(f"- Identical card and answers, possibly one person submitting twice: {'; '.join(dup)}. Kept.")
    return "\n".join(lines) + "\n"


def main() -> None:
    humans, models = load()
    table = per_cv(humans, models)
    table.to_csv(OUT_CSV, index=False, float_format="%.4g")
    text = report(humans, models, table)
    OUT_MD.write_text(text, encoding="utf-8")
    print(f"{OUT_CSV}\n{OUT_MD}\n\n{text}")


if __name__ == "__main__":
    main()
