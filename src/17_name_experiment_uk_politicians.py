"""
Step 17 — Name experiment: UK politicians across three fame bands.

Same design as step 15 (controlled: same nationality + occupation, matched on pageviews,
unique-name vs shared-name), but using UK politicians instead of German footballers.
Politicians naturally span a far wider fame range than the original footballer sample,
letting us test whether the name penalty holds at low, mid, and high fame levels.

Fame bands (monthly Wikipedia pageviews):
  lo:   200 –  2,000   (backbenchers, very obscure MPs)
  mid: 2,000 – 30,000  (known ministers, recognisable politicians)
  hi: 30,000 – 500,000 (household names — PM / major party leader tier)

Writes:
  data/names_gbpol_{tier}_{band}.json   (e.g. names_gbpol_uniq_mid.json)

After running, generate scores via intheweights.com (see generate_notes.md).
"""
import json, re, time, math, unicodedata, statistics as st, random
from pathlib import Path
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
WDQS = "https://query.wikidata.org/sparql"
PV_URL = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
          "all-access/all-agents/{t}/monthly/{a}/{b}")

UK = "Q145"
POLITICIAN = "Q82955"

BANDS = {
    "lo":  (200,    2_000),
    "mid": (2_000,  30_000),
    "hi":  (30_000, 500_000),
}
N_PER = 20
random.seed(17)


def run_sparql(q, tries=4):
    for i in range(tries):
        try:
            r = requests.get(WDQS, params={"query": q, "format": "json"},
                             headers={"User-Agent": UA,
                                      "Accept": "application/sparql-results+json"}, timeout=120)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
        except Exception as e:
            print(f"  SPARQL attempt {i+1} failed: {e}")
        time.sleep(3 * (i + 1))
    raise RuntimeError("SPARQL failed after retries")


def candidates():
    rows = run_sparql(f"""
      SELECT DISTINCT ?person ?personLabel ?article WHERE {{
        ?person wdt:P31 wd:Q5 ; wdt:P106 wd:{POLITICIAN} ; wikibase:sitelinks ?sl .
        ?person wdt:P27 wd:{UK} .
        FILTER(?sl >= 3 && ?sl <= 400)
        ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
      }} LIMIT 3000""")
    out = []
    for b in rows:
        lab = b["personLabel"]["value"]
        if re.fullmatch(r"Q\d+", lab) or len(lab.split()) < 2 or re.search(r"\d", lab):
            continue
        out.append({
            "name": lab,
            "category": "politician",
            "wikipedia_title": requests.utils.unquote(b["article"]["value"].rsplit("/", 1)[-1]),
            "wikidata_id": b["person"]["value"].rsplit("/", 1)[-1],
        })
    return out


def collisions(names):
    counts = {}
    uniq = sorted(set(names))
    for i in range(0, len(uniq), 100):
        chunk = uniq[i:i + 100]
        vals = " ".join('"%s"@en' % n.replace("\\", "\\\\").replace('"', '\\"') for n in chunk)
        rows = run_sparql(
            f'SELECT ?name (COUNT(DISTINCT ?p) AS ?c) WHERE '
            f'{{ VALUES ?name {{ {vals} }} ?p wdt:P31 wd:Q5; rdfs:label ?name. }} GROUP BY ?name'
        )
        for b in rows:
            counts[b["name"]["value"]] = int(b["c"]["value"])
        time.sleep(0.5)
    return counts


def pageviews(title):
    import datetime as dt
    end = dt.date.today().replace(day=1)
    start = (end - dt.timedelta(days=365)).replace(day=1)
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
    print("Querying Wikidata for UK politicians ...", flush=True)
    pool = candidates()
    print(f"  {len(pool)} candidates found", flush=True)

    print("  Computing name collisions ...", flush=True)
    coll = collisions([c["name"] for c in pool])
    for c in pool:
        c["name_collisions"] = coll.get(c["name"], 1)

    uniq_pool   = [c for c in pool if c["name_collisions"] == 1]
    shared_pool = [c for c in pool if c["name_collisions"] >= 4]
    print(f"  {len(uniq_pool)} unique-name, {len(shared_pool)} shared-name candidates")

    print("  Fetching pageviews (this takes a while) ...", flush=True)
    random.shuffle(uniq_pool)
    random.shuffle(shared_pool)

    def enrich(lst, cap=600):
        out = []
        for i, c in enumerate(lst[:cap]):
            c["pageviews_monthly_avg"] = pageviews(c["wikipedia_title"])
            time.sleep(0.05)
            if c["pageviews_monthly_avg"]:
                out.append(c)
            if (i + 1) % 50 == 0:
                print(f"    {i+1}/{min(cap, len(lst))} fetched, {len(out)} with data", flush=True)
        return out

    uniq_all   = enrich(uniq_pool)
    shared_all = enrich(shared_pool)
    print(f"  Pageviews done: {len(uniq_all)} unique, {len(shared_all)} shared with data")

    for band_name, (lo, hi) in BANDS.items():
        print(f"\n=== Band: {band_name} ({lo:,}–{hi:,} pv/mo) ===")
        u = [c for c in uniq_all   if lo <= c["pageviews_monthly_avg"] <= hi]
        s = [c for c in shared_all if lo <= c["pageviews_monthly_avg"] <= hi]
        print(f"  Available: unique={len(u)}, shared={len(s)}")

        if len(u) < 5 or len(s) < 5:
            print("  Too few for a balanced experiment — skipping.")
            continue

        center = math.sqrt(
            st.median([c["pageviews_monthly_avg"] for c in u]) *
            st.median([c["pageviews_monthly_avg"] for c in s])
        )
        print(f"  Fame centre: ~{int(center):,} pv/mo")

        def pick(lst, tier, label):
            lst = sorted(lst, key=lambda x: abs(x["pageviews_monthly_avg"] - center))
            chosen = lst[:N_PER]
            for c in chosen:
                c.update(fame_tier=tier, fame_label=label,
                         slug=slugify(c["name"]),
                         occupations=["politician"])
            path = DATA / f"names_{tier}.json"
            path.write_text(json.dumps(chosen, indent=2, ensure_ascii=False))
            pvs = [c["pageviews_monthly_avg"] for c in chosen]
            colls = sorted(c["name_collisions"] for c in chosen)
            print(f"  {tier}: n={len(chosen)}, pv median={int(st.median(pvs)):,} "
                  f"(range {min(pvs):,}–{max(pvs):,})")
            print(f"    collisions: {colls}")
            print(f"    names: {[c['name'] for c in chosen[:5]]} ...")
            return chosen

        pick(u, f"gbpol_uniq_{band_name}", f"Unique-name UK politician ({band_name} fame)")
        pick(s, f"gbpol_shared_{band_name}", f"Shared-name UK politician ({band_name} fame)")

    print("\nDone. Now score the new names via intheweights.com (see generate_notes.md).")


if __name__ == "__main__":
    main()
