"""
Step 5 — Prepare data + a shareable hero image for the static front end.

Emits:
  web/data.json     aggregates the story page renders from
  web/og-image.png  1200x630 social-share card
"""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEB = ROOT / "web"; WEB.mkdir(exist_ok=True)

CAT_ORDER = ["politician", "actor", "musician", "athlete", "scientist", "journalist", "novelist"]
SIZE_ORDER = ["small", "mid", "large", "frontier"]
INK = "#1b2a4a"
ACCENT = "#c65b3c"
PAPER = "#faf7f2"


def build_json():
    long = pd.read_csv(DATA / "dataset_long.csv")
    people = pd.read_csv(DATA / "dataset_people.csv")
    # headline visuals use the well-known tier; the dot plot ships every person tagged
    # unambiguous (name maps to one person) so the site can toggle all-vs-unambiguous live.
    hi = long[long["fame_tier"] == "high"]
    hi_people = people[people["fame_tier"] == "high"]
    unambig = set(hi_people[hi_people["n_referents"] == 1]["name"])

    cat_mean = (hi.groupby("category")["confidence"].mean()
                .sort_values(ascending=False))
    categories = list(cat_mean.index)

    model_mean = hi.groupby("model")["confidence"].mean().sort_values(ascending=False)
    models = list(model_mean.index)
    model_meta = (hi.groupby("model")["param_class"].first())

    hm = hi.groupby(["category", "model"])["confidence"].mean().unstack()
    hm = hm.loc[categories, models]

    size = hi.groupby(["category", "param_class"])["confidence"].mean().unstack()
    size = size.loc[categories, [s for s in SIZE_ORDER if s in size.columns]]

    # a few example people per category (closest to that category's mean)
    pmean = hi.groupby("name")["confidence"].mean()
    ppivot = hi.pivot_table("confidence", "name", "model")   # per-person per-model scores
    hi_people = hi_people.assign(mean_conf=hi_people["name"].map(pmean))
    examples = {}
    for c in categories:
        sub = hi_people[hi_people["category"] == c].copy()
        lo = sub.nsmallest(1, "mean_conf").iloc[0]
        top = sub.nlargest(1, "mean_conf").iloc[0]
        examples[c] = {
            "best_known": {"name": top["name"], "conf": round(top["mean_conf"])},
            "least_known": {"name": lo["name"], "conf": round(lo["mean_conf"])},
        }

    # an illustrative single lookup: a well-known person where models disagree a bit,
    # so the per-model bars actually vary (shows what one query returns).
    hi_long = long[long["fame_tier"] == "high"]
    stdev = hi_long.groupby("name")["confidence"].std()
    mean_by = hi_long.groupby("name")["confidence"].mean()
    pool = [n for n in stdev.index if 45 <= mean_by[n] <= 80]
    ex_name = max(pool, key=lambda n: stdev[n]) if pool else mean_by.idxmax()
    ex_rows = hi_long[hi_long["name"] == ex_name].set_index("model")
    ex_person = hi_people[hi_people["name"] == ex_name].iloc[0]
    top_percent = None
    if pd.notna(ex_person.get("weight_rank")) and pd.notna(ex_person.get("weight_total")):
        top_percent = max(1, round(ex_person["weight_rank"] / ex_person["weight_total"] * 100))
    example = {
        "name": ex_name,
        "category": ex_person["category"],
        "descriptor": (ex_person.get("matched_descriptor") if pd.notna(ex_person.get("matched_descriptor")) else ""),
        "top_percent": top_percent,   # the site's "Top X%" (from its global weight rank)
        "bars": [{"model": m, "score": int(ex_rows.loc[m, "confidence"])} for m in models],
    }

    # name-ambiguity finding (well-known tier, so fame is held constant):
    # how many people share the searched name vs the score.
    allscore = long.groupby("name")["confidence"].mean()
    grid = people[people["fame_tier"] == "high"].copy()
    grid["score"] = grid["name"].map(allscore)
    bins = [(1, 1, "Just them"), (2, 3, "2–3 people"), (4, 99, "4+ people")]
    ambiguity = {
        "r": round(float(np.corrcoef(grid["n_referents"], grid["score"])[0, 1]), 2),
        "bins": [{"label": lab,
                  "mean": round(float(grid[(grid.n_referents >= lo) & (grid.n_referents <= hi)]["score"].mean())),
                  "n": int(((grid.n_referents >= lo) & (grid.n_referents <= hi)).sum())}
                 for lo, hi, lab in bins],
    }

    fame = None
    if long["fame_tier"].nunique() > 1:
        fg = long.groupby(["category", "fame_tier"])["confidence"].mean().unstack()
        tiers = [t for t in ["high", "low"] if t in fg.columns]
        fg = fg.loc[categories, tiers]
        pv = people.groupby("fame_tier")["pageviews_monthly_avg"].median().round().astype(int)
        fame = {
            "tiers": tiers,
            "tier_pageviews": {t: int(pv[t]) for t in tiers},
            "categories": categories,
            "values": {t: [round(float(fg.loc[c, t])) for c in categories] for t in tiers},
        }

    # ---- Act 1: what predicts being in the weights? (representative fame range only;
    #      the name/PD sub-experiments are sampled for special properties, so excluded here) ----
    cov = pd.read_csv(DATA / "covariates.csv")
    repres = people[people["fame_tier"].isin(["famous", "high", "low"])]
    allp = repres.merge(allscore.rename("score"), on="name").merge(
        cov[["name", "article_bytes"]], on="name", how="left")
    allp = allp.dropna(subset=["score", "pageviews_monthly_avg", "article_bytes", "n_referents"]).copy()
    allp["log_pv"] = np.log10(allp["pageviews_monthly_avg"])
    allp["log_bytes"] = np.log10(allp["article_bytes"])

    # Two INDEPENDENT predictors only. (A name-ambiguity variable was dropped: intheweights
    # derives it from the models' own answers, so it leaks the outcome — and we sampled unique
    # names, so the real name-commonness has no variance to test.)
    def zc(s): return (s - s.mean()) / s.std()
    Z = np.column_stack([zc(allp["log_bytes"]), zc(allp["log_pv"])])
    y = allp["score"].values
    Xc = np.column_stack([np.ones(len(y)), Z])
    beta = np.linalg.lstsq(Xc, y, rcond=None)[0]
    r2 = 1 - ((y - Xc @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    predictors = {
        "r2": round(float(r2), 2),
        "rows": [
            {"key": "written about them (Wikipedia)", "r": round(float(np.corrcoef(allp["log_bytes"], y)[0, 1]), 2),
             "beta": round(float(beta[1]), 1)},
            {"key": "how often looked up", "r": round(float(np.corrcoef(allp["log_pv"], y)[0, 1]), 2),
             "beta": round(float(beta[2]), 1)},
        ],
    }
    gradient = [{"name": row["name"], "pv": int(row["pageviews_monthly_avg"]),
                 "score": round(float(row["score"]))} for _, row in allp.iterrows()]

    # ---- does occupation matter? mean recognition per occupation (same people as the scatter) ----
    occ = allp.groupby("category")["score"].agg(["mean", "count"]).sort_values("mean", ascending=False)
    occupations = [{"category": c, "mean": round(float(r["mean"])), "n": int(r["count"])}
                   for c, r in occ.iterrows()]

    # ---- leakage-free name test: unique vs genuinely-shared names, matched on fame ----
    name_experiment = None
    tiers_here = set(people["fame_tier"])
    if {"deuuniq", "deushared"} <= tiers_here:
        ne = people[people["fame_tier"].isin(["deuuniq", "deushared"])].merge(
            allscore.rename("score"), on="name").merge(cov[["name", "article_bytes"]], on="name", how="left")
        ne["shared"] = (ne["fame_tier"] == "deushared").astype(int)
        ne["log_pv"] = np.log10(ne["pageviews_monthly_avg"])
        ne["log_bytes"] = np.log10(ne["article_bytes"])
        u = ne[ne.shared == 0]["score"]; s = ne[ne.shared == 1]["score"]
        # difference adjusted for fame + article length (regression coef on `shared`)
        d = ne.dropna(subset=["score", "log_pv", "log_bytes"])
        X = np.column_stack([np.ones(len(d)), d["log_pv"], d["log_bytes"], d["shared"]])
        b = np.linalg.lstsq(X, d["score"].values, rcond=None)[0]
        se = math.sqrt(u.var() / len(u) + s.var() / len(s))
        t = (s.mean() - u.mean()) / se if se else 0
        diff = round(float(s.mean() - u.mean()))
        adj = round(float(b[3]))
        name_experiment = {
            "unique": {"mean": round(float(u.mean())), "n": int(len(u))},
            "shared": {"mean": round(float(s.mean())), "n": int(len(s)), "threshold": 4},
            "diff": diff, "adjusted_diff": adj, "t": round(float(t), 1),
            "caption": (f"{len(u)} unique-name vs {len(s)} shared-name German footballers, "
                        f"matched so the two groups are equally famous. The shared group (exact "
                        f"name shared with 4+ other notable people) scored {abs(diff)} points "
                        f"{'lower' if diff < 0 else 'higher'} — still {abs(adj)} points "
                        f"{'lower' if adj < 0 else 'higher'} even after accounting for how much "
                        f"Wikipedia writes about each person. Same country, same sport, similar "
                        f"fame — only the name differs."),
        }

    # ---- Act 2: how different are the models? (the informative middle: well-known + obscure) ----
    gridl = long[long["fame_tier"].isin(["high", "low"])]
    wide = gridl.pivot_table("confidence", "name", "model")
    mlin = gridl.groupby("model")["confidence"].mean().sort_values(ascending=False)
    pc = gridl.groupby("model")["param_class"].first()
    model_lineup = [{"label": m, "mean": round(float(mlin[m])), "param_class": pc[m]} for m in mlin.index]

    # ---- do the models agree on WHO is in the weights? rank correlation between models, over
    #      people — scale-free, so it ignores each model's overall generosity (the lineup above) ----
    corr = wide.corr(method="spearman")
    mods = list(wide.columns)
    agree_models = sorted(
        [{"label": m, "rho": round(float(np.mean([corr.loc[m, o] for o in mods if o != m])), 2),
          "param_class": pc[m]} for m in mods],
        key=lambda r: -r["rho"])
    pairs = [(a, b, float(corr.loc[a, b])) for i, a in enumerate(mods) for b in mods[i + 1:]]
    lo_pair = min(pairs, key=lambda x: x[2]); hi_pair = max(pairs, key=lambda x: x[2])
    model_agreement = {
        "mean": round(float(np.mean([p[2] for p in pairs])), 2),
        "models": agree_models,
        "least": {"a": lo_pair[0], "b": lo_pair[1], "rho": round(lo_pair[2], 2)},
        "most": {"a": hi_pair[0], "b": hi_pair[1], "rho": round(hi_pair[2], 2)},
    }

    per_sd = wide.std(1); per_mean = wide.mean(1)
    a_bands = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]
    agreement = [{"band": f"{lo}–{hi}",
                  "sd": round(float(per_sd[(per_mean > lo) & (per_mean <= hi)].mean()), 0),
                  "n": int(((per_mean > lo) & (per_mean <= hi)).sum())} for lo, hi in a_bands]
    n_models = wide.shape[1]
    all_pos = (wide > 0).sum(1) == n_models
    in_all = {
        "pct": round(float(all_pos.mean()) * 100),
        "n_models": int(n_models),
        "range_hi": {"label": mlin.index[0], "mean": round(float(mlin.iloc[0]))},
        "range_lo": {"label": mlin.index[-1], "mean": round(float(mlin.iloc[-1]))},
        "var_person": round(float(((gridl.groupby("name")["confidence"].transform("mean") - gridl["confidence"].mean()) ** 2).sum() / ((gridl["confidence"] - gridl["confidence"].mean()) ** 2).sum()) * 100),
        "var_model": round(float(((gridl.groupby("model")["confidence"].transform("mean") - gridl["confidence"].mean()) ** 2).sum() / ((gridl["confidence"] - gridl["confidence"].mean()) ** 2).sum()) * 100),
    }

    # per-model metadata for the hover tooltips (maker, size class, knowledge cutoff)
    makers = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google", "x-ai": "xAI",
              "meta-llama": "Meta", "deepseek": "DeepSeek", "moonshotai": "Moonshot AI",
              "z-ai": "Z.ai", "mistralai": "Mistral AI", "qwen": "Alibaba (Qwen)"}
    models_meta = {}
    for _, r in long.drop_duplicates("model")[["model", "model_id", "param_class", "knowledge_cutoff"]].iterrows():
        cut = str(r["knowledge_cutoff"])
        models_meta[r["model"]] = {
            "param_class": r["param_class"],
            "cutoff": (None if cut in ("unknown", "nan", "") else cut),
            "maker": makers.get(str(r["model_id"]).split("/")[0], str(r["model_id"]).split("/")[0]),
        }

    out = {
        "meta": {"n_people": int(len(people)), "n_models": int(long["model"].nunique()),
                 "n_scatter": int(len(allp))},
        "example": example,
        "gradient": gradient,
        "occupations": occupations,
        "model_lineup": model_lineup,
        "model_agreement": model_agreement,
        "models": models_meta,
        "name_experiment": name_experiment,
    }
    (WEB / "data.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("wrote web/data.json")
    return out


def build_og(d):
    mpl.rcParams.update({"font.family": "DejaVu Sans"})
    ml = d["model_lineup"]                       # share card = the models-disagree finding
    labels = [m["label"].replace(" Instruct", "").replace("Meta Llama", "Llama")
              .replace("Google ", "").replace("xAI ", "").replace("Z.ai ", "")
              .replace(" Flash Lite", " Lite").replace(" Small", "") for m in ml][::-1]
    vals = [m["mean"] for m in ml][::-1]
    colors = [INK for _ in ml]

    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([0.40, 0.08, 0.56, 0.72]); ax.set_facecolor(PAPER)
    ax.barh(range(len(vals)), vals, color=colors, height=0.74)
    for i, (lab, v) in enumerate(zip(labels, vals)):
        ax.text(-2, i, lab, va="center", ha="right", color="#333", fontsize=10.5)
        ax.text(v + 1.5, i, f"{v:.0f}", va="center", ha="left", color="#333", fontsize=10.5, fontweight="bold")
    ax.set_xlim(0, 100); ax.set_ylim(-0.6, len(vals) - 0.4); ax.axis("off")

    fig.text(0.05, 0.90, "Who's in the weights?", fontsize=33, fontweight="bold", color=INK)
    fig.text(0.05, 0.62, "Ask 13 models\nwho a person is —\nsome know far\nmore than others.",
             fontsize=20, fontweight="bold", color=ACCENT, linespacing=1.25)
    fig.text(0.05, 0.30, "One knows almost\neveryone; another\nalmost no one.",
             fontsize=14, color="#444", linespacing=1.4)
    fig.text(0.05, 0.05, "avg recognition score, 0–100  ·  via intheweights.com",
             fontsize=11, color="#888")
    fig.savefig(WEB / "og-image.png", facecolor=PAPER)
    plt.close(fig)
    print("wrote web/og-image.png")


if __name__ == "__main__":
    build_og(build_json())
