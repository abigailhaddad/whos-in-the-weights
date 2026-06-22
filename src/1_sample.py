"""
Step 1 — Sample roughly fame-matched people from Wikidata, by occupation, per fame tier.

Everything configurable lives in config.yaml: the groups (occupations) and the fame rules
(sitelink + pageview bands per tier). The pipeline is INCREMENTAL — a tier that already has
data/names_<tier>.json is left untouched, so adding a tier/category and re-running only
generates the new sample. Delete a tier's names file to deliberately re-sample it.

Per tier we:
  * pull humans with the occupation + an English article, in the tier's sitelink band,
  * fetch 12-month Wikipedia pageviews ("how often people look them up"),
  * keep people whose pageviews fall in the tier's band, preferring unique names,
  * pick the N per category closest to the band centre (fame matched within the tier).

Output: data/names_<tier>.json (list of person records, each tagged with fame_tier).

Usage:  python src/1_sample.py [tier ...]   (default: every tier in config.yaml)
"""
import json, re, sys, time, random, unicodedata, datetime as dt, math
from pathlib import Path
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())

UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
WDQS = "https://query.wikidata.org/sparql"
PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
             "en.wikipedia/all-access/all-agents/{title}/monthly/{start}/{end}")

random.seed(CONFIG["seed"])


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def run_sparql(query, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(WDQS, params={"query": query, "format": "json"},
                             headers={"User-Agent": UA,
                                      "Accept": "application/sparql-results+json"}, timeout=120)
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"SPARQL failed: {last}")


def sparql_candidates(qid, sitelink_band):
    lo, hi = sitelink_band
    query = f"""
    SELECT ?person ?personLabel ?sitelinks ?article WHERE {{
      ?person wdt:P31 wd:Q5 ; wdt:P106 wd:{qid} ; wikibase:sitelinks ?sitelinks .
      FILTER(?sitelinks >= {lo} && ?sitelinks <= {hi})
      ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 800
    """
    out = []
    for b in run_sparql(query):
        label = b["personLabel"]["value"]
        if re.fullmatch(r"Q\d+", label):
            continue
        if len(label.split()) < 2 or re.search(r"\d", label):   # drop mononyms / odd labels
            continue
        out.append({
            "name": label,
            "wikipedia_title": requests.utils.unquote(b["article"]["value"].rsplit("/", 1)[-1]),
            "wikidata_id": b["person"]["value"].rsplit("/", 1)[-1],
            "sitelinks": int(b["sitelinks"]["value"]),
        })
    return out


def name_collision_counts(names):
    counts = {}
    uniq = sorted(set(names))
    for i in range(0, len(uniq), 120):
        chunk = uniq[i:i + 120]
        values = " ".join('"%s"@en' % n.replace("\\", "\\\\").replace('"', '\\"') for n in chunk)
        query = f"""
        SELECT ?name (COUNT(DISTINCT ?p) AS ?c) WHERE {{
          VALUES ?name {{ {values} }}
          ?p wdt:P31 wd:Q5 ; rdfs:label ?name .
        }} GROUP BY ?name
        """
        try:
            for b in run_sparql(query):
                counts[b["name"]["value"]] = int(b["c"]["value"])
        except Exception as e:
            print(f"   (collision query chunk failed: {e})")
    return counts


def fetch_occupations(qids):
    if not qids:
        return {}
    values = " ".join(f"wd:{q}" for q in qids)
    query = f"""
    SELECT ?person (GROUP_CONCAT(DISTINCT ?occLabel; separator="|") AS ?occs) WHERE {{
      VALUES ?person {{ {values} }}
      ?person wdt:P106 ?occ . ?occ rdfs:label ?occLabel . FILTER(LANG(?occLabel)="en")
    }} GROUP BY ?person
    """
    return {b["person"]["value"].rsplit("/", 1)[-1]: sorted(set(b["occs"]["value"].split("|")) - {""})
            for b in run_sparql(query)}


def pageviews_year(title):
    end = dt.date.today().replace(day=1)
    start = (end - dt.timedelta(days=365)).replace(day=1)
    url = PAGEVIEWS.format(title=requests.utils.quote(title.replace(" ", "_"), safe=""),
                           start=start.strftime("%Y%m01"), end=end.strftime("%Y%m01"))
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200:
            return None, None
        items = r.json().get("items", [])
        if not items:
            return None, None
        total = sum(it["views"] for it in items)
        return total, round(total / len(items))
    except Exception:
        return None, None


def already_taken_ids():
    """Wikidata ids already chosen in any existing tier (so tiers don't overlap)."""
    taken = set()
    for f in DATA.glob("names_*.json"):
        for r in json.loads(f.read_text()):
            taken.add(r["wikidata_id"])
    return taken


def sample_tier(tier, spec, categories, existing):
    """Sample only `categories` for this tier; append to `existing` and write the file."""
    sit = spec["sitelink_band"]
    pv_lo, pv_hi = spec["pageviews_band"]
    center = math.sqrt(pv_lo * pv_hi)           # geometric centre of the fame band
    per_cat = CONFIG["sampling"]["per_category"]
    pool = CONFIG["sampling"]["pool_per_category"]
    prefer_unique = CONFIG["sampling"]["prefer_unique_names"]
    taken = already_taken_ids()

    print(f"\n=== tier '{tier}' ({spec['label']}): sitelinks {sit}, "
          f"pageviews {pv_lo}-{pv_hi}/mo · sampling {categories} ===")
    chosen, seen = [], set()
    for cat in categories:
        qid = CONFIG["categories"][cat]
        print(f"[{cat}] querying Wikidata ...", flush=True)
        cands = [c for c in sparql_candidates(qid, sit) if c["wikidata_id"] not in taken]
        random.shuffle(cands)
        cands = cands[:pool]
        print(f"  {len(cands)} candidates; fetching pageviews ...", flush=True)
        for c in cands:
            c["pageviews_year"], c["pageviews_monthly_avg"] = pageviews_year(c["wikipedia_title"])
            time.sleep(0.05)
        cands = [c for c in cands if c["pageviews_monthly_avg"]
                 and pv_lo <= c["pageviews_monthly_avg"] <= pv_hi]
        if prefer_unique and cands:
            coll = name_collision_counts([c["name"] for c in cands])
            for c in cands:
                c["name_collisions"] = coll.get(c["name"], 1)
        cands.sort(key=lambda x: (x.get("name_collisions", 1) > 1,
                                  abs(x["pageviews_monthly_avg"] - center)))
        picked = []
        for c in cands:
            if c["wikidata_id"] in seen:
                continue
            c.update(category=cat, fame_tier=tier, fame_label=spec["label"],
                     slug=slugify(c["name"]))
            picked.append(c); seen.add(c["wikidata_id"])
            if len(picked) >= per_cat:
                break
        chosen.extend(picked)
        if len(picked) < per_cat:
            print(f"  ! only {len(picked)}/{per_cat} for {cat} in band", flush=True)
        else:
            print(f"  {cat:11} picked {len(picked)}", flush=True)

    if chosen:
        print("fetching occupation lists ...", flush=True)
        occ = fetch_occupations([c["wikidata_id"] for c in chosen])
        for c in chosen:
            c["occupations"] = occ.get(c["wikidata_id"], [])

    out = DATA / f"names_{tier}.json"
    out.write_text(json.dumps(existing + chosen, indent=2, ensure_ascii=False))
    print(f"+{len(chosen)} people ({len(existing) + len(chosen)} total) -> {out.name}")


def main():
    requested = sys.argv[1:] or list(CONFIG["fame_tiers"].keys())
    for tier in requested:
        if tier not in CONFIG["fame_tiers"]:
            print(f"(unknown tier '{tier}', skipping)"); continue
        path = DATA / f"names_{tier}.json"
        existing = json.loads(path.read_text()) if path.exists() else []
        have = {r["category"] for r in existing}
        missing = [c for c in CONFIG["categories"] if c not in have]
        if not missing:
            print(f"tier '{tier}': all categories present — skipping.")
            continue
        sample_tier(tier, CONFIG["fame_tiers"][tier], missing, existing)


if __name__ == "__main__":
    main()
