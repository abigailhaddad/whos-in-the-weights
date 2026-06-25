"""
Step 16 — Name experiment across fame tiers.

Same design as step 15 (German footballers, unique vs shared full name, matched on pageviews),
but run at two additional pageview bands:
  - hi_fame:  5,000–200,000 monthly views  (established / well-known players)
  - lo_fame:    50–600 monthly views        (very obscure but Wikipedia-notable)

Writes:
  data/names_deuuniq_hi.json  / data/names_deushared_hi.json
  data/names_deuuniq_lo.json  / data/names_deushared_lo.json

Run this to get candidate lists, then drive intheweights.com (see generate_notes.md)
to score them and save slugs to data/slugmap_tiers.json.
"""
import json, re, time, math, unicodedata, statistics as st
from pathlib import Path
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
WDQS = "https://query.wikidata.org/sparql"
PV_URL = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
           "all-access/all-agents/{t}/monthly/{a}/{b}")

GERMANY = ["Q183", "Q16957", "Q41304", "Q7318", "Q43287"]
FOOTBALLER = "Q937857"

BANDS = {
    "mid":  (5_000,  50_000),   # established players — Uwe Seeler / Beckenbauer tier
    "top":  (50_000, 300_000),  # household names — Neuer / Klopp tier
}
N_PER = 20


def run_sparql(q, tries=4):
    for i in range(tries):
        try:
            r = requests.get(WDQS, params={"query": q, "format": "json"},
                             headers={"User-Agent": UA,
                                      "Accept": "application/sparql-results+json"}, timeout=120)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
        except Exception:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError("SPARQL failed")


def candidates():
    vals = " ".join(f"wd:{q}" for q in GERMANY)
    rows = run_sparql(f"""
      SELECT DISTINCT ?person ?personLabel ?article WHERE {{
        ?person wdt:P31 wd:Q5 ; wdt:P106 wd:{FOOTBALLER} ; wikibase:sitelinks ?sl .
        ?person wdt:P27 ?c . VALUES ?c {{ {vals} }}
        FILTER(?sl >= 3 && ?sl <= 200)
        ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }} LIMIT 2000""")
    out = []
    for b in rows:
        lab = b["personLabel"]["value"]
        if re.fullmatch(r"Q\d+", lab) or len(lab.split()) < 2 or re.search(r"\d", lab):
            continue
        out.append({
            "name": lab,
            "category": "athlete",
            "wikipedia_title": requests.utils.unquote(b["article"]["value"].rsplit("/", 1)[-1]),
            "wikidata_id": b["person"]["value"].rsplit("/", 1)[-1],
        })
    return out


def collisions(names):
    counts = {}
    uniq = sorted(set(names))
    for i in range(0, len(uniq), 120):
        chunk = uniq[i:i + 120]
        vals = " ".join('"%s"@en' % n.replace("\\", "\\\\").replace('"', '\\"') for n in chunk)
        rows = run_sparql(
            f'SELECT ?name (COUNT(DISTINCT ?p) AS ?c) WHERE '
            f'{{ VALUES ?name {{ {vals} }} ?p wdt:P31 wd:Q5; rdfs:label ?name. }} GROUP BY ?name'
        )
        for b in rows:
            counts[b["name"]["value"]] = int(b["c"]["value"])
    return counts


def pageviews(title):
    import datetime as dt
    end = dt.date.today().replace(day=1)
    start = (end.replace(day=1) - dt.timedelta(days=365)).replace(day=1)
    url = PV_URL.format(
        t=requests.utils.quote(title.replace(" ", "_"), safe=""),
        a=start.strftime("%Y%m01"),
        b=end.strftime("%Y%m01"),
    )
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        items = r.json().get("items", []) if r.status_code == 200 else []
        return round(sum(it["views"] for it in items) / len(items)) if items else None
    except Exception:
        return None


def slugify(n):
    s = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    import random; random.seed(16)

    print("Querying Wikidata for German footballers ...", flush=True)
    pool = candidates()
    print(f"  {len(pool)} candidates; computing name collisions ...", flush=True)

    coll = collisions([c["name"] for c in pool])
    for c in pool:
        c["name_collisions"] = coll.get(c["name"], 1)

    uniq_pool   = [c for c in pool if c["name_collisions"] == 1]
    shared_pool = [c for c in pool if c["name_collisions"] >= 4]
    print(f"  {len(uniq_pool)} unique-name, {len(shared_pool)} shared-name candidates")
    print("  Fetching pageviews (slow) ...", flush=True)

    def enrich(lst, cap=300):
        out = []
        for c in lst[:cap]:
            c["pageviews_monthly_avg"] = pageviews(c["wikipedia_title"])
            time.sleep(0.05)
            if c["pageviews_monthly_avg"]:
                out.append(c)
        return out

    random.shuffle(uniq_pool); random.shuffle(shared_pool)
    uniq_all   = enrich(uniq_pool)
    shared_all = enrich(shared_pool)

    for band_name, (lo, hi) in BANDS.items():
        print(f"\n=== Band: {band_name} ({lo:,}–{hi:,} pv/mo) ===")
        u = [c for c in uniq_all   if lo <= c["pageviews_monthly_avg"] <= hi]
        s = [c for c in shared_all if lo <= c["pageviews_monthly_avg"] <= hi]
        print(f"  Available: unique={len(u)}, shared={len(s)}")

        if len(u) < 5 or len(s) < 5:
            print("  Too few — skipping this band.")
            continue

        center = math.sqrt(
            st.median([c["pageviews_monthly_avg"] for c in u]) *
            st.median([c["pageviews_monthly_avg"] for c in s])
        )
        print(f"  Fame center: ~{int(center):,} pv/mo")

        def pick(lst, tier, label):
            lst = sorted(lst, key=lambda x: abs(x["pageviews_monthly_avg"] - center))
            chosen = lst[:N_PER]
            for c in chosen:
                c.update(fame_tier=tier, fame_label=label,
                         slug=slugify(c["name"]),
                         occupations=["association football player"])
            path = DATA / f"names_{tier}.json"
            path.write_text(json.dumps(chosen, indent=2, ensure_ascii=False))
            pvs = [c["pageviews_monthly_avg"] for c in chosen]
            colls = sorted(c["name_collisions"] for c in chosen)
            print(f"  {tier}: n={len(chosen)}, pv median={int(st.median(pvs)):,} "
                  f"(range {min(pvs):,}–{max(pvs):,}), collisions={colls}")
            return chosen

        pick(u, f"deuuniq_{band_name}",   f"Unique-name German footballer ({band_name} fame)")
        pick(s, f"deushared_{band_name}", f"Shared-name German footballer ({band_name} fame)")

    print("\nDone. Now run intheweights.com generation (see generate_notes.md) for the new names.")


if __name__ == "__main__":
    main()
