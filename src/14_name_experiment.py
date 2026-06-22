"""
SUPERSEDED by src/15_name_experiment_v2.py. This v1 compared unique- vs shared-name people of
mixed nationalities, which introduced a nationality confound; v2 re-runs the test within German
footballers only. Kept for the record.

Step 14 — Does a genuinely shared name lower recognition? (leakage-free test)

The earlier "name ambiguity" finding used intheweights' own referent count, which is derived
from the models' answers — circular. Here we use an INDEPENDENT predictor: how many notable
humans share the person's exact name, counted on Wikidata before any model is queried.

Sample two cohorts, matched on fame (pageviews):
  * unique:  exactly 1 human on Wikidata has that name
  * shared:  >= 4 humans share the name
Same occupations (footballer / actor / politician), so referent-matching keywords still work.
Writes names_nameunique.json / names_nameshared.json for the existing pipeline.
"""
import json, re, time, math, unicodedata, statistics as st
from pathlib import Path
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
WDQS = "https://query.wikidata.org/sparql"
PV = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
      "all-access/all-agents/{t}/monthly/{a}/{b}")
DOMAINS = {"athlete": "Q937857", "actor": "Q33999", "politician": "Q82955"}  # footballer/actor/politician
PV_BAND = (400, 25000)
N_PER = 18


def slugify(n):
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def run_sparql(q, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(WDQS, params={"query": q, "format": "json"},
                             headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}, timeout=120)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            last = r.status_code
        except Exception as e:
            last = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"sparql {last}")


def candidates(qid, cat):
    rows = run_sparql(f"""
      SELECT ?person ?personLabel ?article WHERE {{
        ?person wdt:P31 wd:Q5 ; wdt:P106 wd:{qid} ; wikibase:sitelinks ?sl .
        FILTER(?sl >= 6 && ?sl <= 45)
        ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }} LIMIT 500""")
    out = []
    for b in rows:
        lab = b["personLabel"]["value"]
        if re.fullmatch(r"Q\d+", lab) or len(lab.split()) < 2 or re.search(r"\d", lab):
            continue
        out.append({"name": lab, "category": cat,
                    "wikipedia_title": requests.utils.unquote(b["article"]["value"].rsplit("/", 1)[-1]),
                    "wikidata_id": b["person"]["value"].rsplit("/", 1)[-1]})
    return out


def collisions(names):
    counts = {}
    uniq = sorted(set(names))
    for i in range(0, len(uniq), 120):
        vals = " ".join('"%s"@en' % n.replace("\\", "\\\\").replace('"', '\\"') for n in uniq[i:i + 120])
        for b in run_sparql(f'SELECT ?name (COUNT(DISTINCT ?p) AS ?c) WHERE {{ VALUES ?name {{ {vals} }} ?p wdt:P31 wd:Q5; rdfs:label ?name. }} GROUP BY ?name'):
            counts[b["name"]["value"]] = int(b["c"]["value"])
    return counts


def pageviews(title):
    import datetime as dt
    end = dt.date.today().replace(day=1); start = (end - dt.timedelta(days=365)).replace(day=1)
    url = PV.format(t=requests.utils.quote(title.replace(" ", "_"), safe=""),
                    a=start.strftime("%Y%m01"), b=end.strftime("%Y%m01"))
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        items = r.json().get("items", []) if r.status_code == 200 else []
        return round(sum(it["views"] for it in items) / len(items)) if items else None
    except Exception:
        return None


def occupations(qids):
    if not qids:
        return {}
    vals = " ".join(f"wd:{q}" for q in qids)
    res = {}
    for b in run_sparql(f'SELECT ?person (GROUP_CONCAT(DISTINCT ?o; separator="|") AS ?occ) WHERE {{ VALUES ?person {{ {vals} }} ?person wdt:P106 ?oc. ?oc rdfs:label ?o. FILTER(LANG(?o)="en") }} GROUP BY ?person'):
        res[b["person"]["value"].rsplit("/", 1)[-1]] = sorted(set(b["occ"]["value"].split("|")) - {""})
    return res


def main():
    import random; random.seed(11)
    pool = []
    for cat, qid in DOMAINS.items():
        print(f"[{cat}] querying ...", flush=True)
        pool += candidates(qid, cat)
    # dedupe by qid
    seen = {};
    for c in pool: seen[c["wikidata_id"]] = c
    pool = list(seen.values())
    print(f"{len(pool)} candidates; computing name collisions ...", flush=True)
    coll = collisions([c["name"] for c in pool])
    for c in pool:
        c["name_collisions"] = coll.get(c["name"], 1)
    uniq = [c for c in pool if c["name_collisions"] == 1]
    shared = [c for c in pool if c["name_collisions"] >= 4]
    random.shuffle(uniq); random.shuffle(shared)
    print(f"unique pool {len(uniq)}, shared pool {len(shared)}; fetching pageviews ...", flush=True)

    def enrich(lst, cap=140):
        out = []
        for c in lst[:cap]:
            c["pageviews_monthly_avg"] = pageviews(c["wikipedia_title"]); time.sleep(0.04)
            if c["pageviews_monthly_avg"] and PV_BAND[0] <= c["pageviews_monthly_avg"] <= PV_BAND[1]:
                out.append(c)
        return out
    uniq, shared = enrich(uniq), enrich(shared)
    center = math.sqrt(st.median([c["pageviews_monthly_avg"] for c in uniq]) *
                       st.median([c["pageviews_monthly_avg"] for c in shared]))
    print(f"matched-fame center ~{int(center)} views/mo  (unique band {len(uniq)}, shared {len(shared)})")

    def pick(lst, tier, label):
        lst.sort(key=lambda x: abs(x["pageviews_monthly_avg"] - center))
        chosen = lst[:N_PER]
        occ = occupations([c["wikidata_id"] for c in chosen])
        for c in chosen:
            c.update(fame_tier=tier, fame_label=label, slug=slugify(c["name"]),
                     occupations=occ.get(c["wikidata_id"], []))
        (DATA / f"names_{tier}.json").write_text(json.dumps(chosen, indent=2, ensure_ascii=False))
        print(f"{tier}: {len(chosen)} picked, median {int(st.median([c['pageviews_monthly_avg'] for c in chosen]))} views")
        return chosen

    pick(uniq, "nameuniq", "Unique name")
    pick(shared, "nameshared", "Shared name (4+ namesakes)")


if __name__ == "__main__":
    main()
