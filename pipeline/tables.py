"""Formatting helpers for the reports: markdown tables and tidy numbers."""

from __future__ import annotations

import math

import pandas as pd


def fmt(value, digits=3):
    """A number as short text; blanks for missing values."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != 0 and abs(value) < 0.001:
            return f"{value:.1e}"
        return f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return str(value)


def pct(value, digits=1):
    """A share (0 to 1) as a percentage, e.g. 0.5467 -> '54.7%'."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{100 * value:.{digits}f}%"


def md_table(df: pd.DataFrame, digits=3) -> str:
    """A pandas table as a markdown table (written here to avoid another dependency)."""
    if df is None or len(df) == 0:
        return "_(no data)_"
    columns = [str(c) for c in df.columns]
    rows = [[fmt(v, digits) for v in row] for row in df.itertuples(index=False)]
    widths = [max(len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(columns)]
    line = lambda cells: "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |"
    return "\n".join([line(columns), "| " + " | ".join("-" * w for w in widths) + " |"] + [line(r) for r in rows])
