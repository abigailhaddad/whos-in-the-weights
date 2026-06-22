"""
Step 12 — Where do the models AGREE, and when are you "in all of them"?

For each person we look across the 13 models at: the mean, the spread (SD), the weakest
model's score (the floor), and whether *every* model clears a bar. Then we ask what level of
fame / writing / name-uniqueness gets you into all of them.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm

DATA = Path(__file__).resolve().parent.parent / "data"


def main():
    long = pd.read_csv(DATA / "dataset_long.csv")
    people = pd.read_csv(DATA / "dataset_people.csv")
    cov = pd.read_csv(DATA / "covariates.csv")
    grid = long[long["fame_tier"].isin(["high", "low"])]
    wide = grid.pivot_table("confidence", "name", "model")

    per = pd.DataFrame({
        "mean": wide.mean(1), "sd": wide.std(1), "floor": wide.min(1),
        "n_pos": (wide > 0).sum(1), "n_mod": (wide >= 50).sum(1),
    })
    per["all_pos"] = per["n_pos"] == wide.shape[1]
    per["all_mod"] = per["n_mod"] == wide.shape[1]
    per = per.join(people.set_index("name")[["fame_tier", "pageviews_monthly_avg", "n_referents"]])
    per = per.join(cov.set_index("name")[["article_bytes"]])
    per["log_pv"] = np.log10(per["pageviews_monthly_avg"])
    per["log_bytes"] = np.log10(per["article_bytes"])

    print("=" * 64)
    print("DO MODELS AGREE? (spread across the 13 models, by recognition level)")
    per["band"] = pd.cut(per["mean"], [0, 20, 40, 60, 80, 100],
                         labels=["0–20", "20–40", "40–60", "60–80", "80–100"])
    print(per.groupby("band", observed=True).agg(
        people=("sd", "size"), avg_spread_SD=("sd", "mean")).round(1).to_string())
    print("  -> agreement is highest at the extremes, lowest in the middle (the 'maybe' zone)")

    print("\n" + "=" * 64)
    print("ARE YOU IN ALL OF THEM?")
    print(f"  every model gives you ANY recognition (>0):   {per['all_pos'].mean():.0%} of people")
    print(f"  every model gives you a MODERATE score (>=50): {per['all_mod'].mean():.0%} of people")
    print("\n  by fame tier:")
    print(per.groupby("fame_tier").agg(all_pos=("all_pos", "mean"),
          all_mod=("all_mod", "mean")).round(2).to_string())

    print("\n  the 'floor' model (lowest score) is almost always the smallest:")
    floor_model = grid.loc[grid.groupby("name")["confidence"].idxmin()]["model"].value_counts()
    for m, c in floor_model.head(3).items():
        print(f"    {m.replace(' Instruct',''):28} is the weakest link for {c} people")

    print("\n" + "=" * 64)
    print("WHAT GETS YOU INTO ALL OF THEM (logistic, standardized predictors)")
    d = per.dropna(subset=["log_pv", "log_bytes", "n_referents"]).copy()
    for c in ["log_pv", "log_bytes", "n_referents"]:
        d["z_" + c] = (d[c] - d[c].mean()) / d[c].std()
    X = sm.add_constant(d[["z_log_pv", "z_log_bytes", "z_n_referents"]])
    for target in ["all_pos", "all_mod"]:
        try:
            m = sm.Logit(d[target].astype(int), X).fit(disp=0)
            print(f"\n  P({target}):")
            for k in ["z_log_pv", "z_log_bytes", "z_n_referents"]:
                print(f"    {k:14} coef {m.params[k]:+.2f}  p={m.pvalues[k]:.1e}")
        except Exception as e:
            print(f"  ({target}: {e})")

    # threshold: median pageviews / article length among those in-all vs not
    print("\n  who clears 'every model >=50' looks like:")
    g = per.groupby("all_mod").agg(pageviews=("pageviews_monthly_avg", "median"),
        article_bytes=("article_bytes", "median"), namesakes=("n_referents", "median")).round(0)
    print(g.to_string())


if __name__ == "__main__":
    main()
