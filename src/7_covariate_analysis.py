"""
Step 7 — What actually predicts a person's score?

Merges data/covariates.csv with each person's mean score (across the 13 models) and asks:
  * Does "how much is written about them" (Wikipedia article length) predict score —
    more than how often they're looked up (pageviews)?
  * Is there an era effect (historical vs recent people)?
  * A gender gap at matched fame?
  * Do novelists (and others) on Project Gutenberg — i.e. with public-domain, scraped text —
    score higher?

Charts -> charts/ ; findings printed.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; CH = ROOT / "charts"
INK, ACCENT = "#1b2a4a", "#c65b3c"
mpl.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 140,
                     "axes.titlesize": 13, "axes.titleweight": "bold"})


def corr(a, b):
    m = a.notna() & b.notna()
    return np.corrcoef(a[m], b[m])[0, 1] if m.sum() > 2 else float("nan")


def load():
    long = pd.read_csv(DATA / "dataset_long.csv")
    people = pd.read_csv(DATA / "dataset_people.csv")
    cov = pd.read_csv(DATA / "covariates.csv")
    score = long.groupby("name")["confidence"].mean().rename("score")
    df = people.merge(score, on="name").merge(
        cov.drop(columns=["category"]), on="name", how="left")
    df["log_pv"] = np.log10(df["pageviews_monthly_avg"])
    df["log_bytes"] = np.log10(df["article_bytes"])
    return df, long


def chart_predictors(df):
    """score vs article length and vs pageviews, well-known tier."""
    hi = df[df["fame_tier"] == "high"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for ax, (xcol, lab) in zip(axes, [("log_bytes", "Wikipedia article length (bytes, log)"),
                                       ("log_pv", "Wikipedia pageviews / month (log)")]):
        ax.scatter(hi[xcol], hi["score"], s=26, color=INK, alpha=.55)
        m = hi[xcol].notna() & hi["score"].notna()
        if m.sum() > 2:
            b, a = np.polyfit(hi[xcol][m], hi["score"][m], 1)
            xs = np.linspace(hi[xcol][m].min(), hi[xcol][m].max(), 50)
            ax.plot(xs, a + b * xs, color=ACCENT, lw=2)
            ax.set_title(f"r = {corr(hi[xcol], hi['score']):+.2f}")
        ax.set_xlabel(lab); ax.set_ylabel("mean score"); ax.set_ylim(0, 100)
    fig.suptitle("What predicts a well-known person's score?", fontweight="bold")
    fig.tight_layout()
    fig.savefig(CH / "predictors.png", bbox_inches="tight"); plt.close(fig)


def chart_era(df):
    sub = df[df["death_year"].notna() | df["birth_year"].notna()].copy()
    sub["era"] = sub["death_year"].fillna(sub["birth_year"] + 60)
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.scatter(sub["era"], sub["score"], s=26, color=INK, alpha=.5)
    m = sub["era"].notna() & sub["score"].notna()
    b, a = np.polyfit(sub["era"][m], sub["score"][m], 1)
    xs = np.linspace(sub["era"][m].min(), sub["era"][m].max(), 50)
    ax.plot(xs, a + b * xs, color=ACCENT, lw=2)
    ax.set_title(f"Era vs score   (r = {corr(sub['era'], sub['score']):+.2f})")
    ax.set_xlabel("year (death, or birth + 60)"); ax.set_ylabel("mean score"); ax.set_ylim(0, 100)
    fig.tight_layout(); fig.savefig(CH / "era.png", bbox_inches="tight"); plt.close(fig)
    return sub


def chart_gutenberg(df):
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    groups = [("All people", df), ("Novelists only", df[df["category"] == "novelist"])]
    labels, on_vals, off_vals, on_n, off_n = [], [], [], [], []
    for name, g in groups:
        labels.append(name)
        on_vals.append(g[g["on_gutenberg"]]["score"].mean())
        off_vals.append(g[~g["on_gutenberg"]]["score"].mean())
        on_n.append(int(g["on_gutenberg"].sum())); off_n.append(int((~g["on_gutenberg"]).sum()))
    x = range(len(labels)); bw = 0.36
    ax.bar([i - bw/2 for i in x], on_vals, bw, color=INK, label="On Project Gutenberg")
    ax.bar([i + bw/2 for i in x], off_vals, bw, color="#b9b3a4", label="Not on Gutenberg")
    for i, (v, n) in enumerate(zip(on_vals, on_n)): ax.text(i - bw/2, v + 1.5, f"{v:.0f}\nn={n}", ha="center", fontsize=8.5)
    for i, (v, n) in enumerate(zip(off_vals, off_n)): ax.text(i + bw/2, v + 1.5, f"{v:.0f}\nn={n}", ha="center", fontsize=8.5)
    ax.set_xticks(list(x), labels); ax.set_ylim(0, 100); ax.set_ylabel("mean score")
    ax.legend(frameon=False, fontsize=9)
    ax.set_title("Public-domain text (on Gutenberg) → better known?")
    fig.tight_layout(); fig.savefig(CH / "gutenberg.png", bbox_inches="tight"); plt.close(fig)


def main():
    df, long = load()
    print("=" * 60)
    print(f"{len(df)} people with covariates  ({df['on_gutenberg'].sum()} on Gutenberg, "
          f"{df['gender'].notna().sum()} with gender, {df['death_year'].notna().sum()} deceased)")

    hi = df[df["fame_tier"] == "high"]
    print("\nPREDICTORS OF SCORE (well-known tier):")
    print(f"   article length (log bytes)   r = {corr(hi['log_bytes'], hi['score']):+.2f}")
    print(f"   pageviews (log)              r = {corr(hi['log_pv'], hi['score']):+.2f}")
    print(f"   era (death/birth year)       r = {corr(df['death_year'].fillna(df['birth_year']+60), df['score']):+.2f}")

    print("\nGENDER (mean score):")
    for g, v in df.groupby("gender")["score"].agg(["mean", "size"]).round(1).iterrows():
        print(f"   {str(g):20} {v['mean']:5.1f}  (n={int(v['size'])})")

    print("\nPROJECT GUTENBERG (public-domain text):")
    for label, g in [("all", df), ("novelists", df[df.category == 'novelist'])]:
        on = g[g["on_gutenberg"]]["score"].mean(); off = g[~g["on_gutenberg"]]["score"].mean()
        print(f"   {label:10} on={on:5.1f} (n={g['on_gutenberg'].sum()})  "
              f"off={off:5.1f} (n={(~g['on_gutenberg']).sum()})")

    chart_predictors(df); chart_era(df); chart_gutenberg(df)
    print("\ncharts -> charts/predictors.png, era.png, gutenberg.png")


if __name__ == "__main__":
    main()
