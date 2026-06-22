"""
Step 4 — Analysis + simple/beautiful charts.

Headline question: which *categories* of people are best known across models, holding
fame (Wikipedia pageviews) roughly constant — and how does that vary by model?

Produces:
  charts/heatmap_category_model.png   recognition rate, category x model
  charts/category_recognition.png     categories ranked, with per-model spread
  charts/model_recognition.png        models ranked by overall recognition
  data/summary_category_model.csv
Prints a short findings digest.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CH = ROOT / "charts"; CH.mkdir(exist_ok=True)

# ---- styling: clean, restrained ----
mpl.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#666", "axes.labelcolor": "#222", "text.color": "#222",
    "xtick.color": "#444", "ytick.color": "#444", "figure.dpi": 140,
    "axes.titlesize": 13, "axes.titleweight": "bold",
})
INK = "#1b2a4a"
ACCENT = "#c65b3c"

# model display order (frontier -> small) for readability
MODEL_ORDER = ["GPT-5.5", "Claude Opus 4.8", "xAI Grok 4.20", "Google Gemini 3.1 Flash Lite",
               "Claude Haiku 4.5", "GPT-5.4 Mini", "Kimi K2 0905", "DeepSeek V4 Flash",
               "Llama 3.3 70B Instruct", "GLM 4.7 Flash", "Mistral Small 3.2 24B Instruct",
               "Qwen3 8B", "Meta Llama 3.2 1B Instruct"]
CAT_ORDER = ["politician", "actor", "musician", "athlete", "scientist", "journalist", "novelist"]


def load():
    long = pd.read_csv(DATA / "dataset_long.csv")
    people = pd.read_csv(DATA / "dataset_people.csv")
    return long, people


def order(values, pref):
    seen = [v for v in pref if v in set(values)]
    rest = sorted(set(values) - set(seen))
    return seen + rest


def heatmap(long):
    pivot = (long.groupby(["category", "model"])["confidence"].mean().unstack())
    cats = order(pivot.index, CAT_ORDER)
    # order columns by overall model strength (descending) for a clean gradient
    mods = list(long.groupby("model")["confidence"].mean().sort_values(ascending=False).index)
    pivot = pivot.loc[cats, mods]

    fig, ax = plt.subplots(figsize=(11, 4.6))
    im = ax.imshow(pivot.values, cmap="YlGnBu", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(mods)), [m.replace(" Instruct", "") for m in mods],
                  rotation=40, ha="right", fontsize=9)
    ax.set_yticks(range(len(cats)), [c.capitalize() for c in cats])
    for i in range(len(cats)):
        for j in range(len(mods)):
            v = pivot.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                    color="white" if v > 55 else "#333")
    ax.set_title("Who's in the weights?  Mean confidence by category × model")
    fig.text(0.5, 0.005, "Mean model confidence (0–100) that the person exists / is known. "
             "Fame held ~constant (Wikipedia pageviews matched). Models ordered strongest→weakest.",
             ha="center", fontsize=8.5, color="#666")
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("mean confidence", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(CH / "heatmap_category_model.png", bbox_inches="tight")
    plt.close(fig)
    return pivot


def category_chart(long):
    g = long.groupby(["category", "model"])["confidence"].mean()
    cat_mean = g.groupby("category").mean().sort_values(ascending=True)
    cats = list(cat_mean.index)

    fig, ax = plt.subplots(figsize=(9, 4.4))
    y = range(len(cats))
    ax.barh(y, cat_mean.values, color=INK, height=0.55, zorder=2)
    for i, c in enumerate(cats):
        vals = g.loc[c].values
        ax.scatter(vals, [i] * len(vals), color=ACCENT, alpha=0.55, s=22, zorder=3)
    ax.set_yticks(list(y), [c.capitalize() for c in cats])
    ax.set_xlabel("mean confidence (0–100)")
    ax.set_xlim(0, 100)
    ax.set_title("Which kinds of people do models know best?")
    fig.text(0.5, 0.005, "Bar = average across 13 models.  Dots = individual models "
             "(spread shows model disagreement).", ha="center", fontsize=8.5, color="#666")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(CH / "category_recognition.png", bbox_inches="tight")
    plt.close(fig)
    return cat_mean


def size_interaction_chart(long):
    """The headline: where does category knowledge drop off as models shrink?"""
    size_order = ["frontier", "large", "mid", "small"]   # bigger left, smaller right
    g = long.groupby(["category", "param_class"])["confidence"].mean().unstack()
    g = g[[c for c in size_order if c in g.columns]]
    cats = order(g.index, CAT_ORDER)

    # emphasise athletes; mute the rest into a band
    colors = {"athlete": "#c65b3c", "scientist": "#1b2a4a", "politician": "#1b2a4a",
              "actor": "#9aa6bf", "musician": "#9aa6bf", "journalist": "#9aa6bf"}
    lw = {"athlete": 3.0, "scientist": 2.4, "politician": 2.4}
    fig, ax = plt.subplots(figsize=(8.2, 5))
    x = range(len(g.columns))
    for c in cats:
        ax.plot(x, g.loc[c].values, marker="o", lw=lw.get(c, 1.8),
                color=colors.get(c, "#9aa6bf"),
                alpha=1.0 if c in ("athlete", "scientist", "politician") else 0.7,
                label=c.capitalize(), zorder=3 if c == "athlete" else 2)
    ax.set_xticks(list(x), [s.capitalize() for s in g.columns])
    ax.set_xlabel("model class  (small → frontier)")
    ax.set_ylabel("mean confidence (0–100)")
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right", frameon=False, fontsize=9, ncol=2)
    ax.set_title("Smaller models forget athletes first")
    fig.text(0.5, 0.005, "At matched fame, every category is well known by frontier models — but as "
             "models shrink, athletes drop off far faster than scientists or politicians.",
             ha="center", fontsize=8.5, color="#666")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(CH / "size_interaction.png", bbox_inches="tight")
    plt.close(fig)
    return g


def fame_chart(long):
    """High vs low fame, per category — only if more than one tier is present."""
    if long["fame_tier"].nunique() < 2:
        return None
    g = long.groupby(["category", "fame_tier"])["confidence"].mean().unstack()
    tiers = [t for t in ["high", "low"] if t in g.columns]
    g = g[tiers]
    cats = order(g.index, CAT_ORDER)
    g = g.loc[cats]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    n = len(cats); x = range(n); bw = 0.38
    tone = {"high": INK, "low": ACCENT}
    pretty = {"high": "Well-known", "low": "Obscure"}
    for k, t in enumerate(tiers):
        offs = [i + (k - (len(tiers) - 1) / 2) * bw for i in x]
        ax.bar(offs, g[t].values, width=bw, color=tone.get(t, "#888"), label=pretty.get(t, t))
        for xo, v in zip(offs, g[t].values):
            ax.text(xo, v + 1.5, f"{v:.0f}", ha="center", fontsize=8, color="#444")
    ax.set_xticks(list(x), [c.capitalize() for c in cats])
    ax.set_ylim(0, 100)
    ax.set_ylabel("mean confidence (0–100)")
    ax.legend(frameon=False, fontsize=10)
    ax.set_title("Make people obscure, and the gaps widen")
    fig.text(0.5, 0.005, "Every group, two fame levels (people matched on Wikipedia pageviews "
             "within each level).", ha="center", fontsize=8.5, color="#666")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(CH / "fame_comparison.png", bbox_inches="tight")
    plt.close(fig)
    return g


def model_chart(long):
    m = long.groupby("model")["confidence"].mean().sort_values()
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.barh(range(len(m)), m.values, color=INK, height=0.6)
    ax.set_yticks(range(len(m)), [x.replace(" Instruct", "") for x in m.index], fontsize=9)
    ax.set_xlabel("mean confidence (0–100)")
    ax.set_xlim(0, 100)
    ax.set_title("Which models know the most people?")
    fig.tight_layout()
    fig.savefig(CH / "model_recognition.png", bbox_inches="tight")
    plt.close(fig)
    return m


def main():
    long, people = load()
    # headline visuals use the well-known tier (clean matched-fame story);
    # the fame chart compares well-known vs obscure.
    high = long[long["fame_tier"] == "high"] if "fame_tier" in long else long
    pivot = heatmap(high)
    cat_mean = category_chart(high)
    size_g = size_interaction_chart(high)
    fame_g = fame_chart(long)
    model_mean = model_chart(high)
    pivot.to_csv(DATA / "summary_category_model.csv")

    print("=" * 64)
    print(f"{len(people)} people · {long['model'].nunique()} models · "
          f"matched on Wikipedia pageviews (median ~2.5k monthly views)")
    print(f"people matched to the right person: {people['matched'].sum()}/{len(people)}")
    print("\nMEAN CONFIDENCE BY CATEGORY (avg across models):")
    for c, v in cat_mean.sort_values(ascending=False).items():
        print(f"   {c.capitalize():12} {v:5.1f}")
    print("\nCATEGORY × MODEL SIZE (mean confidence):")
    print(size_g.round(0).to_string())
    if fame_g is not None:
        print("\nCATEGORY × FAME TIER (mean confidence):")
        print(fame_g.round(0).to_string())
    print("\nMODELS, most -> least confident overall:")
    for c, v in model_mean.sort_values(ascending=False).items():
        print(f"   {c.replace(' Instruct',''):32} {v:5.1f}")

    spread = (long.groupby(["category", "model"])["confidence"].mean()) \
        .groupby("category").std().sort_values(ascending=False)
    print("\nCATEGORIES WHERE MODELS DISAGREE MOST (std across models):")
    for c, v in spread.items():
        print(f"   {c.capitalize():12} ±{v:4.1f}")
    print("\ncharts -> charts/*.png")


if __name__ == "__main__":
    main()
