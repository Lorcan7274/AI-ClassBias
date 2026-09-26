"""Small statistics helpers used by the analysis.

Why clustering: the 20 calls on one pair (and the 60 on one base CV) are not
independent. They share the CV's wording, so a quirk of one CV moves all of them
together. Treating them as independent would make confidence intervals too narrow
and p-values too small. Every interval below therefore comes from a regression
with standard errors clustered by base CV (cv_id), or from aggregating to one
number per base CV first. statsmodels' cov_type="cluster" does the clustering.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from scipy.special import expit


def _codes(groups):
    return pd.factorize(pd.Series(groups).astype(str))[0]


def _fit(model, groups):
    with warnings.catch_warnings():  # perfect separation etc. is reported through the "note" instead
        warnings.simplefilter("ignore")
        return model.fit(disp=0, maxiter=200, cov_type="cluster", cov_kwds={"groups": _codes(groups)})


def clustered_rate(y, groups) -> dict:
    """Share of 1s in y, with a 95% CI and a p-value against 50%, from an
    intercept-only logistic regression with standard errors clustered by `groups`."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    k = int(y.sum())
    out = {"n": n, "k": k, "rate": k / n if n else math.nan, "low": math.nan, "high": math.nan,
           "p": math.nan, "n_clusters": int(pd.Series(groups).nunique()) if n else 0, "note": ""}
    if n < 2 or k in (0, n):
        out["note"] = "every answer was the same, so no interval can be estimated"
        return out
    try:
        res = _fit(sm.Logit(y, np.ones((n, 1))), groups)
        low, high = res.conf_int()[0]
        out.update({"rate": float(expit(res.params[0])), "low": float(expit(low)), "high": float(expit(high)),
                    "p": float(res.pvalues[0])})
    except Exception as e:  # singular matrix, non-convergence, ...
        out["note"] = f"model did not fit ({type(e).__name__})"
    return out


def clustered_odds_ratio(y, x, groups, extra=None) -> dict:
    """Logistic regression y ~ 1 + x (+ extra columns), clustered by `groups`.
    Returns the odds ratio for x with its 95% CI and p-value, plus the intercept's
    rate (the rate when x = 0, or at the average when x is centred)."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    cols = [np.ones(len(y)), x] + ([np.asarray(e, dtype=float) for e in extra] if extra else [])
    X = np.column_stack(cols)
    out = {"n": len(y), "odds_ratio": math.nan, "low": math.nan, "high": math.nan, "p": math.nan,
           "base_rate": math.nan, "note": ""}
    if len(y) < 4 or y.sum() in (0, len(y)) or len(set(x)) < 2:
        out["note"] = "not enough variation to estimate the effect"
        return out
    try:
        res = _fit(sm.Logit(y, X), groups)
        low, high = res.conf_int()[1]
        out.update({"odds_ratio": float(np.exp(res.params[1])), "low": float(np.exp(low)),
                    "high": float(np.exp(high)), "p": float(res.pvalues[1]),
                    "base_rate": float(expit(res.params[0]))})
    except Exception as e:
        out["note"] = f"model did not fit ({type(e).__name__})"
    return out


def clustered_mean(values, groups) -> dict:
    """Mean of `values` with a 95% CI and a p-value against 0, from an intercept-only
    linear regression with standard errors clustered by `groups`."""
    v = np.asarray(values, dtype=float)
    out = {"n": len(v), "mean": float(v.mean()) if len(v) else math.nan, "low": math.nan, "high": math.nan,
           "p": math.nan, "note": ""}
    if len(v) < 2 or np.allclose(v, v[0]):
        out["note"] = "no variation"
        return out
    try:
        res = sm.OLS(v, np.ones((len(v), 1))).fit(cov_type="cluster", cov_kwds={"groups": _codes(groups)})
        low, high = res.conf_int()[0]
        out.update({"low": float(low), "high": float(high), "p": float(res.pvalues[0])})
    except Exception as e:
        out["note"] = f"model did not fit ({type(e).__name__})"
    return out


def cv_level(per_cv_values, null_value=0.5) -> dict:
    """One value per base CV (e.g. its pick rate): the mean with a t-based 95% CI,
    a one-sample t-test and a Wilcoxon signed-rank test against `null_value`.
    This is the simplest way to respect that calls on one CV are not independent:
    each CV counts once."""
    v = np.asarray(per_cv_values, dtype=float)
    out = {"n_cvs": len(v), "mean": float(v.mean()) if len(v) else math.nan, "low": math.nan, "high": math.nan,
           "t_p": math.nan, "wilcoxon_p": math.nan}
    if len(v) < 2:
        return out
    if not np.allclose(v, v[0]):
        t = stats.ttest_1samp(v, null_value)
        ci = t.confidence_interval()
        out.update({"low": float(ci.low), "high": float(ci.high), "t_p": float(t.pvalue)})
    diffs = v - null_value
    if np.any(diffs != 0):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out["wilcoxon_p"] = float(stats.wilcoxon(diffs).pvalue)
    return out


def wilson(k, n) -> tuple:
    """Naive 95% CI for a share, ignoring clustering. Shown only for comparison."""
    if n == 0:
        return (math.nan, math.nan)
    ci = stats.binomtest(int(k), int(n), 0.5).proportion_ci(confidence_level=0.95, method="wilson")
    return (float(ci.low), float(ci.high))


def binomial_p(k, n) -> float:
    return float(stats.binomtest(int(k), int(n), 0.5).pvalue) if n else math.nan
