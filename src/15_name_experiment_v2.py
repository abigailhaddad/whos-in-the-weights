"""
Step 15 — Name experiment, confound-controlled.

v1 was confounded: the shared-name cohort was ~75% German, the unique cohort international.
Here both cohorts are the SAME nationality AND occupation — German footballers — differing only
in whether their name is shared by other notable people (independent Wikidata count). Matched on
fame (pageviews). Writes names_deuuniq.json / names_deushared.json.
"""
import json, re, time, math, unicodedata, statistics as st
from pathlib import Path
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
WDQS = "https://query.wikidata.org/sparql"
PV = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
      "all-access/all-agents/{t}/monthly/{a}/{b}")
GERMANY = ["Q183", "Q16957", "Q41304", "Q7318", "Q43287"]  # FRG, GDR, Weimar, Nazi, Empire
FOOTBALLER = "Q937857"
PV_BAND = (600, 30000)
N_PER = 20


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


def candidates():
    vals = " ".join(f"wd:{q}" for q in GERMANY)
    rows = run_sparql(f"""
      SELECT DISTINCT ?person ?personLabel ?article WHERE {{
        ?person wdt:P31 wd:Q5 ; wdt:P106 wd:{FOOTBALLER} ; wikibase:sitelinks ?sl .
        ?person wdt:P27 ?c . VALUES ?c {{ {vals} }}
        FILTER(?sl >= 5 && ?sl <= 50)
        ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }} LIMIT 900""")
    out = []
    for b in rows:
        lab = b["personLabel"]["value"]
        if re.fullmatch(r"Q\d+", lab) or len(lab.split()) < 2 or re.search(r"\d", lab):
            continue
        out.append({"name": lab, "category": "athlete",
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


def main():
    import random; random.seed(15)
    pool = candidates()
    print(f"{len(pool)} German footballers; name collisions ...", flush=True)
    coll = collisions([c["name"] for c in pool])
    for c in pool:
        c["name_collisions"] = coll.get(c["name"], 1)
    uniq = [c for c in pool if c["name_collisions"] == 1]
    shared = [c for c in pool if c["name_collisions"] >= 4]
    random.shuffle(uniq); random.shuffle(shared)
    print(f"unique {len(uniq)}, shared {len(shared)}; pageviews ...", flush=True)

    def enrich(lst, cap=160):
        out = []
        for c in lst[:cap]:
            c["pageviews_monthly_avg"] = pageviews(c["wikipedia_title"]); time.sleep(0.04)
            if c["pageviews_monthly_avg"] and PV_BAND[0] <= c["pageviews_monthly_avg"] <= PV_BAND[1]:
                out.append(c)
        return out
    uniq, shared = enrich(uniq), enrich(shared)
    center = math.sqrt(st.median([c["pageviews_monthly_avg"] for c in uniq]) *
                       st.median([c["pageviews_monthly_avg"] for c in shared]))
    print(f"center ~{int(center)} views/mo (unique band {len(uniq)}, shared {len(shared)})")

    def pick(lst, tier, label):
        lst.sort(key=lambda x: abs(x["pageviews_monthly_avg"] - center))
        chosen = lst[:N_PER]
        for c in chosen:
            c.update(fame_tier=tier, fame_label=label, slug=slugify(c["name"]),
                     occupations=["association football player"])
        (DATA / f"names_{tier}.json").write_text(json.dumps(chosen, indent=2, ensure_ascii=False))
        print(f"{tier}: {len(chosen)} picked, median {int(st.median([c['pageviews_monthly_avg'] for c in chosen]))} views, "
              f"collisions {sorted(c['name_collisions'] for c in chosen)}")
        return chosen

    pick(uniq, "deuuniq", "Unique-name German footballer")
    pick(shared, "deushared", "Shared-name German footballer")


if __name__ == "__main__":
    main()
