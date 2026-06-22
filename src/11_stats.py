"""
Step 11 — The statistics behind the story.

Answers two questions:
  A. How well do our fame/coverage measures predict whether a person is "in the weights"?
     (regression R^2 + standardized coefficients; ANOVA for the category & ambiguity claims)
  B. How different are the 13 models from each other?
     (per-model means, pairwise agreement, variance between models vs between people)
"""
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
from scipy import stats

DATA = Path(__file__).resolve().parent.parent / "data"


def load():
    long = pd.read_csv(DATA / "dataset_long.csv")
    people = pd.read_csv(DATA / "dataset_people.csv")
    cov = pd.read_csv(DATA / "covariates.csv")
    score = long.groupby("name")["confidence"].mean().rename("score")
    df = people.merge(score, on="name").merge(cov.drop(columns=["category"]), on="name", how="left")
    df = df[df["fame_tier"].isin(["high", "low"])].copy()
    df["log_pv"] = np.log10(df["pageviews_monthly_avg"])
    df["log_bytes"] = np.log10(df["article_bytes"])
    df["namesakes"] = df["n_referents"]
    return long, df


def z(s):
    return (s - s.mean()) / s.std()


def predict_recognition(df):
    print("=" * 66)
    print("A. WHAT PREDICTS BEING IN THE WEIGHTS?  (n = %d)" % len(df))
    d = df.dropna(subset=["score", "log_pv", "log_bytes", "namesakes"]).copy()
    for c in ["log_pv", "log_bytes", "namesakes"]:
        d["z_" + c] = z(d[c])
    # single-predictor R^2
    print("\n  single predictor   |  r      R^2")
    for c, lab in [("z_log_pv", "Wikipedia pageviews"), ("z_log_bytes", "article length"),
                   ("z_namesakes", "name ambiguity (namesakes)")]:
        r = np.corrcoef(d[c], d["score"])[0, 1]
        print(f"  {lab:30} {r:+.2f}   {r**2:.2f}")
    # combined standardized model
    m = smf.ols("score ~ z_log_pv + z_log_bytes + z_namesakes", data=d).fit()
    print(f"\n  combined model R^2 = {m.rsquared:.2f}  (adj {m.rsquared_adj:.2f})")
    print("  standardized betas (points of score per 1 SD):")
    for name in ["z_log_pv", "z_log_bytes", "z_namesakes"]:
        print(f"    {name:14} {m.params[name]:+6.1f}   p = {m.pvalues[name]:.1e}")


def anova_story(long, df):
    print("\n" + "=" * 66)
    print("B. DOES CATEGORY MATTER — AND IS IT REALLY NAME AMBIGUITY?")
    hi = df[df["fame_tier"] == "high"].dropna(subset=["score", "namesakes"]).copy()

    f, p = stats.f_oneway(*[g["score"].values for _, g in hi.groupby("category")])
    print(f"\n  1) category only (all well-known names): F = {f:.2f}, p = {p:.1e}  -> categories differ")

    m1 = smf.ols("score ~ C(category)", data=hi).fit()
    m2 = smf.ols("score ~ C(category) + namesakes", data=hi).fit()
    print(f"  2) R^2 category only          = {m1.rsquared:.2f}")
    print(f"     R^2 category + namesakes   = {m2.rsquared:.2f}  (namesakes p = {m2.pvalues['namesakes']:.1e})")
    a2 = sm.stats.anova_lm(m2, typ=2)
    print(f"     partial F for category, controlling namesakes: "
          f"F = {a2.loc['C(category)','F']:.2f}, p = {a2.loc['C(category)','PR(>F)']:.2f}")

    unq = hi[hi["namesakes"] == 1]
    fu, pu = stats.f_oneway(*[g["score"].values for _, g in unq.groupby("category") if len(g) > 1])
    print(f"  3) category among UNAMBIGUOUS names only (n = {len(unq)}): "
          f"F = {fu:.2f}, p = {pu:.2f}  -> gap {'vanishes' if pu>0.05 else 'remains'}")

    fa, pa = stats.f_oneway(*[g["namesakes"].values for _, g in hi.groupby("category")])
    print(f"  4) do categories differ in namesakes? F = {fa:.2f}, p = {pa:.1e}  "
          f"(athletes have commoner names)")


def model_differences(long):
    print("\n" + "=" * 66)
    print("C. HOW DIFFERENT ARE THE MODELS?")
    grid = long[long["fame_tier"].isin(["high", "low"])]
    mm = grid.groupby("model")["confidence"].mean().sort_values(ascending=False)
    print(f"\n  per-model mean score: {mm.max():.0f} ({mm.idxmax()}) "
          f"down to {mm.min():.0f} ({mm.idxmin()}) — a {mm.max()-mm.min():.0f}-point range")

    wide = grid.pivot_table("confidence", "name", "model")
    # variance decomposition: between-people vs between-models
    gm = grid["confidence"].mean()
    ss_total = ((grid["confidence"] - gm) ** 2).sum()
    ss_person = grid.groupby("name")["confidence"].apply(lambda s: len(s)*(s.mean()-gm)**2).sum()
    ss_model = grid.groupby("model")["confidence"].apply(lambda s: len(s)*(s.mean()-gm)**2).sum()
    print(f"  variance explained by WHO the person is: {ss_person/ss_total:.0%}")
    print(f"  variance explained by WHICH model:       {ss_model/ss_total:.0%}")

    corr = wide.corr()
    iu = np.triu_indices_from(corr, k=1)
    print(f"  average pairwise model agreement (correlation across people): r = {corr.values[iu].mean():.2f}")
    # most and least similar model pairs
    pairs = [(corr.index[i], corr.columns[j], corr.values[i, j]) for i, j in zip(*iu)]
    pairs.sort(key=lambda t: t[2])
    short = lambda s: s.replace(" Instruct", "").replace("Meta ", "")
    print(f"  most similar:  {short(pairs[-1][0])} ~ {short(pairs[-1][1])} (r={pairs[-1][2]:.2f})")
    print(f"  least similar: {short(pairs[0][0])} ~ {short(pairs[0][1])} (r={pairs[0][2]:.2f})")


def main():
    long, df = load()
    predict_recognition(df)
    anova_story(long, df)
    model_differences(long)


if __name__ == "__main__":
    main()
