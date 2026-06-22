"""
Step 10 — Public-domain vs in-copyright novelists (matched on current fame).
The controlled test of the "scraped public-domain text" hypothesis.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

DATA = Path(__file__).resolve().parent.parent / "data"
CH = Path(__file__).resolve().parent.parent / "charts"
INK, ACCENT = "#1b2a4a", "#c65b3c"
mpl.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 140,
                     "axes.titlesize": 13, "axes.titleweight": "bold"})


def main():
    long = pd.read_csv(DATA / "dataset_long.csv")
    people = pd.read_csv(DATA / "dataset_people.csv")
    score = long.groupby("name")["confidence"].mean().rename("score")
    df = people.merge(score, on="name")
    df = df[df["fame_tier"].isin(["pdpublic", "pdcopyright"])].copy()
    df["cohort"] = df["fame_tier"].map({"pdpublic": "Public domain\n(died <1930)",
                                        "pdcopyright": "In copyright\n(living / recent)"})

    summ = df.groupby("cohort")["score"].agg(["mean", "median", "std", "size"])
    print(summ.round(1).to_string())
    a = df[df.fame_tier == "pdpublic"]["score"]; b = df[df.fame_tier == "pdcopyright"]["score"]
    se = np.sqrt(a.var()/len(a) + b.var()/len(b))
    print(f"\ndiff {a.mean()-b.mean():+.1f}, approx t = {(a.mean()-b.mean())/se:.2f}  (n={len(a)} vs {len(b)})")

    order = ["Public domain\n(died <1930)", "In copyright\n(living / recent)"]
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    for i, c in enumerate(order):
        s = df[df.cohort == c]["score"]
        jit = (np.arange(len(s)) % 5 - 2) / 2 * 0.06
        ax.scatter([i + j for j in jit], s, s=40, color=INK, alpha=.5, zorder=3)
        ax.plot([i-0.22, i+0.22], [s.mean(), s.mean()], color=ACCENT, lw=3, zorder=4)
        ax.text(i, s.mean()+4, f"mean {s.mean():.0f}", ha="center", color=ACCENT, fontweight="bold")
    ax.set_xticks([0, 1], order); ax.set_ylim(0, 100); ax.set_ylabel("mean score")
    ax.set_title("Public-domain text doesn't help — once fame is matched")
    fig.text(0.5, 0.005, "Novelists matched on current Wikipedia pageviews. Difference is not "
             "significant (t ≈ −0.4).", ha="center", fontsize=8.5, color="#666")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(CH / "public_domain.png", bbox_inches="tight"); plt.close(fig)
    print("chart -> charts/public_domain.png")


if __name__ == "__main__":
    main()
