"""Slide figures for the class-bias study:  python slides/make_figures.py

Writes slides/slide_main_findings.png (each model's class effect with 95% CIs) and
slides/slide_claude_monitoring.png (how often each model says it ignored the
equal-opportunities box), both 16:9, from the result tables in results/.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "slides"
MODELS = [("anthropic/claude-opus-5.5", "Claude"), ("openai/gpt-6.1-sol-pro", "GPT"),
          ("google/gemini-4-argon", "Gemini"), ("meta-llama/llama-4-maverick", "Llama"),
          ("all models", "All four models")]

SURFACE, INK, INK2, MUTED, GRID, ZERO = "#ffffff", "#1d1d1b", "#52514e", "#8a8984", "#ebeae6", "#8a8984"
BLUE, ORANGE, VIOLET, AQUA = "#2a78d6", "#eb6834", "#6250d6", "#1baf7a"

plt.rcParams.update({"font.family": "Inter", "font.size": 15, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK, "axes.edgecolor": GRID,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})


def header(fig, title):
    fig.text(0.045, 0.915, title, fontsize=34, fontweight="bold", family="Inter Display", va="baseline")


def legend_row(fig, y, items, ncol=None):
    handles = [Line2D([], [], marker="o", ls="", ms=12, mfc=c, mec=SURFACE, mew=2, label=t) for c, t in items]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.038, y), ncol=ncol or len(items), frameon=False,
               fontsize=16, handletextpad=0.3, columnspacing=2.2)


def main_findings():
    data = pd.read_csv(ROOT / "results" / "h1_class_effect.csv").set_index(["model", "arm"])
    fig = plt.figure(figsize=(16, 9), dpi=200)
    header(fig, "No AI model favoured the higher-class CV")
    legend_row(fig, 0.875, [(BLUE, "Class hinted"), (ORANGE, "Class stated")])
    panels = [("shortlist", 100, "Shortlisted (percentage points)", 17, [-15, -10, -5, 0, 5, 10, 15]),
              ("likelihood", 1, "Likelihood score (0–100)", 7, [-6, -4, -2, 0, 2, 4, 6])]
    axes = fig.subplots(1, 2, gridspec_kw={"left": 0.16, "right": 0.97, "top": 0.71, "bottom": 0.09, "wspace": 0.12})
    rows = {name: i for i, (_, name) in enumerate(MODELS)}
    for ax, (measure, scale, title, lim, ticks) in zip(axes, panels):
        ax.set_title(title, loc="left", fontsize=18, fontweight="semibold", color=INK, pad=42)
        tr = blended_transform_factory(ax.transData, ax.transAxes)
        ax.text(-lim * 0.03, 1.02, "← favours lower-class", transform=tr, ha="right", va="bottom",
                fontsize=14, color=MUTED)
        ax.text(lim * 0.03, 1.02, "favours higher-class →", transform=tr, ha="left", va="bottom",
                fontsize=14, color=MUTED)
        for arm, color, off in (("implicit", BLUE, -0.16), ("explicit", ORANGE, 0.16)):
            for model, name in MODELS:
                r = data.loc[(model, arm)]
                y = rows[name] + off
                est = r[f"{measure}_effect"] * scale
                lo, hi = r[f"{measure}_ci_low"] * scale, r[f"{measure}_ci_high"] * scale
                ax.plot([lo, hi], [y, y], color=color, lw=2.4, solid_capstyle="round", zorder=2)
                ax.plot(est, y, "o", ms=12, mfc=color, mec=SURFACE, mew=2, zorder=3)
                if model == "all models":
                    ax.annotate(f"{est:+.1f}".replace("-", "−"), (hi, y), xytext=(8, 0),
                                textcoords="offset points", va="center", fontsize=14, color=INK2)
        ax.axvline(0, color=ZERO, lw=1.3, zorder=1)
        ax.axhline(3.5, color=GRID, lw=1.2, zorder=0)
        ax.set_xlim(-lim, lim)
        ax.set_xticks(ticks, [f"{t:+d}".replace("-", "−") if t else "0" for t in ticks])
        ax.set_ylim(len(MODELS) - 0.45, -0.55)
        ax.grid(axis="x", color=GRID, lw=0.9, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(axis="both", length=0, labelsize=15)
    axes[0].set_yticks(range(len(MODELS)), [name for _, name in MODELS], fontsize=17)
    axes[0].get_yticklabels()[-1].set_fontweight("bold")
    axes[1].set_yticks(range(len(MODELS)), [])
    fig.savefig(OUT / "slide_main_findings.png", facecolor=SURFACE)
    plt.close(fig)


def rounded_bar(ax, x, w, h, color, radius_px=7):
    if h <= 0:
        return
    to_px = ax.transData.transform
    (x0, y0), (x1, y1) = to_px((0, 0)), to_px((1, 1))
    px_x, px_y = x1 - x0, y1 - y0
    r = radius_px / px_x
    ax.add_patch(FancyBboxPatch((x, 0), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                mutation_aspect=px_x / px_y, fc=color, ec="none", zorder=2))
    ax.add_patch(Rectangle((x, 0), w, min(h, radius_px / px_y), fc=color, ec="none", zorder=2))


def claude_monitoring():
    data = pd.read_csv(ROOT / "results" / "monitoring.csv").set_index("model")
    fig = plt.figure(figsize=(16, 9), dpi=200)
    header(fig, "Claude says it ignored class mostly for the privileged candidate")
    legend_row(fig, 0.875, [(VIOLET, "Higher-class"), (AQUA, "Lower-class")])
    ax = fig.add_axes([0.07, 0.1, 0.9, 0.66])
    names = MODELS[:4]
    ax.set_xlim(-0.6, len(names) - 0.4)
    ax.set_ylim(0, 60)
    w, gap = 0.3, 0.012
    for i, (model, name) in enumerate(names):
        r = data.loc[model]
        for val, color, x in ((r["mentions_x_pct"], VIOLET, i - w - gap / 2), (r["mentions_y_pct"], AQUA, i + gap / 2)):
            rounded_bar(ax, x, w, val, color)
            if val > 0:
                ax.text(x + w / 2, val + 1.2, f"{val:.0f}%", ha="center", va="bottom", fontsize=20,
                        fontweight="semibold", color=INK)
        if r["mentions_x_pct"] == 0 and r["mentions_y_pct"] == 0:
            ax.text(i, 1.2, "0%", ha="center", va="bottom", fontsize=20, fontweight="semibold", color=INK)
    ax.set_xticks(range(len(names)), [n for _, n in names], fontsize=19)
    ax.set_yticks([0, 20, 40, 60], ["0%", "20%", "40%", "60%"])
    ax.grid(axis="y", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="both", length=0, labelsize=16)
    ax.tick_params(axis="x", pad=12)
    fig.savefig(OUT / "slide_claude_monitoring.png", facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main_findings()
    claude_monitoring()
    print("\n".join(str(p) for p in sorted(OUT.glob("slide_*.png"))))
