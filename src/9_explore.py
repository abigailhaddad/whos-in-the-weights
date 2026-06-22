"""
Step 9 — Quick exploration of extra angles, all from data already collected.
Prints findings; no charts, no new queries.
"""
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def corr(a, b):
    m = a.notna() & b.notna()
    return np.corrcoef(a[m], b[m])[0, 1] if m.sum() > 2 else float("nan")


def main():
    long = pd.read_csv(DATA / "dataset_long.csv")
    people = pd.read_csv(DATA / "dataset_people.csv")
    cov = pd.read_csv(DATA / "covariates.csv")
    score = long.groupby("name")["confidence"].mean().rename("score")
    df = people.merge(score, on="name").merge(cov.drop(columns=["category"]), on="name", how="left")
    df = df[df["fame_tier"].isin(["high", "low"])]          # the matched-fame grid only
    hi = df[df["fame_tier"] == "high"]

    print("=" * 60)
    print("1) COVERAGE BREADTH (how many language Wikipedias)")
    print(f"   sitelinks vs score (well-known): r = {corr(hi['sitelinks'], hi['score']):+.2f}")
    print(f"   article length vs score:         r = {corr(np.log10(hi['article_bytes']), hi['score']):+.2f}")
    print(f"   pageviews vs score:              r = {corr(np.log10(hi['pageviews_monthly_avg']), hi['score']):+.2f}")

    print("\n2) NAMESAKES (how many people share the searched name → site referents)")
    print(f"   n_referents vs score: r = {corr(hi['n_referents'], hi['score']):+.2f}")
    print(df.groupby(pd.cut(df["n_referents"], [0, 1, 3, 6, 50]))["score"].agg(["mean", "size"]).round(1).to_string())

    print("\n3) GENDER GAP, overall and within category (well-known)")
    print(hi.groupby("gender")["score"].agg(["mean", "size"]).round(1).to_string())
    g = hi.pivot_table("score", "category", "gender", aggfunc="mean").round(0)
    print(g.to_string())

    print("\n4) PRODUCERS vs SUBJECTS (do people who *write* beat people written *about*?)")
    producers = ["novelist", "journalist"]
    df["maker"] = np.where(df["category"].isin(producers), "writes text", "written about")
    print(df[df.fame_tier == "high"].groupby("maker")["score"].agg(["mean", "size"]).round(1).to_string())

    print("\n5) SITE'S OWN existence-confidence vs our mean model score (sanity)")
    print(f"   r = {corr(hi['existence_confidence'], hi['score']):+.2f}")


if __name__ == "__main__":
    main()
