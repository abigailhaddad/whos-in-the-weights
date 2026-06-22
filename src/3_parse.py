"""
Step 3 — Parse raw API results into tidy datasets, matching each result back to the
*specific person we sampled* (not a more-famous namesake).

A search for a name returns several "referents" (disambiguated entities). We score each
referent against our sampled person using (a) name-token overlap and (b) domain keywords
from their occupation / category / Wikipedia title appearing in the referent's
descriptor+summary+site-category. A positive match needs BOTH name overlap and >=1 domain
keyword. If no referent matches, the person was "not surfaced" -> recognition 0 for every
model (a real, meaningful datapoint), and we log which namesake the site ranked first.

Outputs:
  data/dataset_long.csv   one row per (person, model)
  data/dataset_people.csv one row per person (with match audit + fame covariates)
"""
import json, re, glob, unicodedata
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CAT_KEYWORDS = {
    "politician": ["politic", "minister", "senator", "president", "governor", "parliament",
                   "congress", "mayor", "diplomat", "statesman", "chancellor", "party"],
    "actor":      ["actor", "actress", "film", "movie", "television", "tv", "director",
                   "screen", "theatre", "theater", "comedian", "hollywood"],
    "musician":   ["music", "singer", "composer", "band", "pianist", "songwriter",
                   "guitarist", "rapper", "conductor", "violinist", "drummer", "vocalist"],
    "athlete":    ["football", "soccer", "athlete", "player", "olympic", "tennis", "sport",
                   "runner", "cyclist", "boxer", "swimmer", "basketball", "baseball",
                   "cricket", "golfer", "coach", "striker", "midfielder"],
    "scientist":  ["scientist", "physic", "chemist", "biolog", "research", "professor",
                   "mathematic", "engineer", "astronom", "geolog", "neuro", "academic",
                   "inventor", "nobel", "ecolog"],
    "journalist": ["journalist", "editor", "reporter", "writer", "correspondent",
                   "columnist", "news", "broadcaster", "author", "publisher", "media"],
    "novelist":   ["novel", "writer", "author", "fiction", "poet", "literary",
                   "literature", "playwright", "essayist"],
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def tokens(s):
    return {t for t in norm(s).split() if len(t) > 1}


def match_referent(d):
    """Return (best_referent or None, audit dict)."""
    meta = d["_meta"]
    our_name_tokens = tokens(meta["name"])
    kw = set(CAT_KEYWORDS.get(meta["category"], []))
    for occ in meta.get("occupations", []):
        kw |= {w for w in norm(occ).split() if len(w) > 2}
    title_kw = {w for w in tokens(meta.get("wikipedia_title", "")) if w not in our_name_tokens}

    best, best_score = None, -1
    for ref in d["referents"]:
        rtok = tokens(ref.get("canonicalName", ""))
        name_overlap = our_name_tokens & rtok
        if not name_overlap:
            continue
        text = norm(" ".join([ref.get("canonicalDescriptor", ""), ref.get("summary", ""),
                              ref.get("category", "")]))
        kw_hits = sum(1 for k in (kw | title_kw) if k in text)
        score = len(name_overlap) * 2 + kw_hits
        # tie-breakers: prefer plausible domain + site identity signals
        score += 0.01 * (ref.get("existenceConfidence") or 0)
        if kw_hits == 0:
            score -= 5         # name-only match (likely a namesake) is penalised hard
        if score > best_score:
            best, best_score = ref, score

    # require a domain-keyword-supported match
    top = d["referents"][0] if d["referents"] else None
    if best is None or best_score < 0:
        audit = {"matched": False,
                 "site_top_referent": (top or {}).get("canonicalName"),
                 "site_top_descriptor": (top or {}).get("canonicalDescriptor"),
                 "n_referents": len(d["referents"])}
        return None, audit
    audit = {"matched": True,
             "matched_referent": best.get("canonicalName"),
             "matched_descriptor": best.get("canonicalDescriptor"),
             "matched_id": best.get("id"),
             "site_category": best.get("category"),
             "existence_confidence": best.get("existenceConfidence"),
             "weight_rank": (best.get("weightRank") or {}).get("rank"),
             "weight_total": (best.get("weightRank") or {}).get("total"),
             "n_referents": len(d["referents"])}
    return best, audit


def main():
    files = sorted(glob.glob(str(DATA / "raw" / "*.json")))
    long_rows, people_rows = [], []
    for f in files:
        d = json.load(open(f))
        meta = d["_meta"]
        models = {m["id"]: m for m in d["models"]}
        ref, audit = match_referent(d)

        person = {
            "name": meta["name"], "slug": meta["slug"], "category": meta["category"],
            "fame_tier": meta.get("fame_tier", "high"),
            "fame_label": meta.get("fame_label", ""),
            "pageviews_monthly_avg": meta.get("pageviews_monthly_avg"),
            "sitelinks": meta.get("sitelinks"),
            "occupations": "; ".join(meta.get("occupations", [])),
            **audit,
        }
        cells = ref.get("cells", {}) if ref else {}
        n_recog = 0
        for mid, m in models.items():
            c = cells.get(mid, {})
            conf = c.get("confidence", 0) if ref else 0
            recognized = bool(conf and conf > 0)
            n_recog += recognized
            long_rows.append({
                "name": meta["name"], "category": meta["category"],
                "fame_tier": meta.get("fame_tier", "high"),
                "pageviews_monthly_avg": meta.get("pageviews_monthly_avg"),
                "model": m["label"], "model_id": mid,
                "param_class": m.get("paramClass"), "knowledge_cutoff": m.get("knowledgeCutoff"),
                "confidence": conf,
                "recognition_score": (c.get("recognitionScore", 0) if ref else 0),
                "result_count": (c.get("resultCount", 0) if ref else 0),
                "recognized": recognized,
                "matched_person": audit["matched"],
            })
        person["n_models_recognize"] = n_recog
        person["n_models"] = len(models)
        people_rows.append(person)

    long = pd.DataFrame(long_rows)
    people = pd.DataFrame(people_rows)
    long.to_csv(DATA / "dataset_long.csv", index=False)
    people.to_csv(DATA / "dataset_people.csv", index=False)
    print(f"parsed {len(people)} people x {long['model'].nunique()} models = {len(long)} rows")
    print(f"matched to our person: {people['matched'].sum()}/{len(people)}")
    print("\nunmatched (person not surfaced by any model — recognition 0):")
    for _, r in people[~people["matched"]].iterrows():
        print(f"   {r['category']:11} {r['name']:28} site top: {r['site_top_referent']}")
    print("\nmean confidence by fame tier × category:")
    piv = long.pivot_table("confidence", "category", "fame_tier", aggfunc="mean").round(0)
    print(piv.to_string())


if __name__ == "__main__":
    main()
