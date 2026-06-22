"""
Step 8 — Public-domain vs in-copyright novelists, matched on current fame.

Tests the scraping hypothesis properly: are authors whose novels are public-domain (and thus
freely scraped into training corpora) better known than in-copyright authors of the same
current popularity?

  * public cohort:   novelists who died before 1930 (works long in the public domain)
  * copyright cohort: novelists born after 1930 and living / died after 1995

Both are drawn from a shared Wikipedia-pageview band so the contrast is copyright status,
not current fame. Written as two extra "tiers" (names_pdpublic.json / names_pdcopyright.json)
so the existing read/parse pipeline picks them up; they're excluded from the main category charts.
"""
import json, re, time, math, unicodedata
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
WDQS = "https://query.wikidata.org/sparql"
PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
             "en.wikipedia/all-access/all-agents/{title}/monthly/{start}/{end}")
NOVELIST = "Q6625963"
N_PER = 16
PV_BAND = (300, 25000)         # broad; cohorts then matched to a shared center


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def run_sparql(query, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(WDQS, params={"query": query, "format": "json"},
                             headers={"User-Agent": UA, "Accept": "application/sparql-results+json"},
                             timeout=120)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"SPARQL failed: {last}")


def candidates(cohort):
    if cohort == "public":
        clause = "?person wdt:P570 ?death. FILTER(YEAR(?death) < 1930)"
    else:
        clause = ("?person wdt:P569 ?birth. FILTER(YEAR(?birth) > 1930) "
                  "OPTIONAL { ?person wdt:P570 ?death. } FILTER(!BOUND(?death) || YEAR(?death) > 1995)")
    query = f"""
    SELECT DISTINCT ?person ?personLabel ?article WHERE {{
      ?person wdt:P31 wd:Q5 ; wdt:P106 wd:{NOVELIST} ; wikibase:sitelinks ?sl .
      FILTER(?sl >= 8)
      {clause}
      ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 700
    """
    out = []
    for b in run_sparql(query):
        label = b["personLabel"]["value"]
        if re.fullmatch(r"Q\d+", label) or len(label.split()) < 2 or re.search(r"\d", label):
            continue
        out.append({"name": label,
                    "wikipedia_title": requests.utils.unquote(b["article"]["value"].rsplit("/", 1)[-1]),
                    "wikidata_id": b["person"]["value"].rsplit("/", 1)[-1]})
    return out


def pageviews_year(title):
    import datetime as dt
    end = dt.date.today().replace(day=1); start = (end - dt.timedelta(days=365)).replace(day=1)
    url = PAGEVIEWS.format(title=requests.utils.quote(title.replace(" ", "_"), safe=""),
                           start=start.strftime("%Y%m01"), end=end.strftime("%Y%m01"))
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200: return None
        items = r.json().get("items", [])
        return round(sum(it["views"] for it in items) / len(items)) if items else None
    except Exception:
        return None


def collisions(names):
    counts = {}
    uniq = sorted(set(names))
    for i in range(0, len(uniq), 120):
        vals = " ".join('"%s"@en' % n.replace("\\", "\\\\").replace('"', '\\"') for n in uniq[i:i+120])
        q = f'SELECT ?name (COUNT(DISTINCT ?p) AS ?c) WHERE {{ VALUES ?name {{ {vals} }} ?p wdt:P31 wd:Q5; rdfs:label ?name. }} GROUP BY ?name'
        try:
            for b in run_sparql(q): counts[b["name"]["value"]] = int(b["c"]["value"])
        except Exception: pass
    return counts


def enrich(cands):
    import random; random.seed(7)
    random.shuffle(cands); cands = cands[:120]
    for c in cands:
        c["pageviews_monthly_avg"] = pageviews_year(c["wikipedia_title"]); time.sleep(0.05)
    cands = [c for c in cands if c["pageviews_monthly_avg"] and PV_BAND[0] <= c["pageviews_monthly_avg"] <= PV_BAND[1]]
    coll = collisions([c["name"] for c in cands])
    for c in cands: c["name_collisions"] = coll.get(c["name"], 1)
    return cands


def main():
    pub = enrich(candidates("public"))
    cop = enrich(candidates("copyright"))
    print(f"public band-candidates: {len(pub)} | copyright: {len(cop)}")
    import statistics as st
    center = math.sqrt(st.median([c["pageviews_monthly_avg"] for c in pub]) *
                       st.median([c["pageviews_monthly_avg"] for c in cop]))
    print(f"matched-fame center ~{int(center)} views/mo")

    def pick(cands, cohort, tier):
        cands.sort(key=lambda x: (x["name_collisions"] > 1, abs(x["pageviews_monthly_avg"] - center)))
        chosen = []
        for c in cands[:N_PER]:
            c.update(category="novelist", fame_tier=tier, fame_label=f"Novelist ({cohort})",
                     cohort=cohort, slug=slugify(c["name"]), occupations=["novelist"])
            chosen.append(c)
        (DATA / f"names_{tier}.json").write_text(json.dumps(chosen, indent=2, ensure_ascii=False))
        mv = [c["pageviews_monthly_avg"] for c in chosen]
        print(f"{tier}: {len(chosen)} picked, median {int(st.median(mv))} views -> names_{tier}.json")
        return chosen

    pick(pub, "public-domain", "pdpublic")
    pick(cop, "in-copyright", "pdcopyright")


if __name__ == "__main__":
    main()
