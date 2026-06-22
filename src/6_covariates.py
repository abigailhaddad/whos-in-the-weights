"""
Step 6 — Fetch per-person covariates to probe *why* some groups score higher.

Hypotheses to test:
  * "Lots of writing about them"  -> Wikipedia article length (bytes of wikitext).
  * "Their writing was scraped"   -> presence in Project Gutenberg (public-domain texts),
                                      and a rough public-domain flag from death year.
  * era / recency                 -> birth & death year.
  * gender                        -> Wikidata P21.

Reads every data/names_<tier>.json; writes data/covariates.csv (one row per person).
Incremental: rows already in covariates.csv (by wikidata_id) are kept and not refetched.
"""
import json, time, glob, datetime as dt
from pathlib import Path
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
THIS_YEAR = 2026


def load_people():
    people = []
    for f in sorted(glob.glob(str(DATA / "names_*.json"))):
        people.extend(json.loads(Path(f).read_text()))
    return people


def wiki_article_lengths(titles):
    """bytes of wikitext per title, batched 50 at a time."""
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        r = requests.get("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "info", "titles": "|".join(chunk),
            "format": "json", "redirects": 1}, headers={"User-Agent": UA}, timeout=30)
        data = r.json().get("query", {})
        norm = {n["from"]: n["to"] for n in data.get("normalized", [])}
        red = {n["from"]: n["to"] for n in data.get("redirects", [])}
        pages = {p.get("title"): p.get("length") for p in data.get("pages", {}).values()}

        def resolve(t):
            t = norm.get(t, t); t = red.get(t, t); return pages.get(t)
        for t in chunk:
            out[t] = resolve(t)
        time.sleep(0.1)
    return out


def wikidata_bio(qids):
    """birth year, death year, gender per Wikidata id (batched)."""
    out = {}
    for i in range(0, len(qids), 150):
        chunk = qids[i:i + 150]
        values = " ".join(f"wd:{q}" for q in chunk)
        query = f"""
        SELECT ?p ?birth ?death ?genderLabel WHERE {{
          VALUES ?p {{ {values} }}
          OPTIONAL {{ ?p wdt:P569 ?birth. }}
          OPTIONAL {{ ?p wdt:P570 ?death. }}
          OPTIONAL {{ ?p wdt:P21 ?gender. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        """
        r = requests.get("https://query.wikidata.org/sparql",
                         params={"query": query, "format": "json"},
                         headers={"User-Agent": UA}, timeout=120)
        for b in r.json()["results"]["bindings"]:
            qid = b["p"]["value"].rsplit("/", 1)[-1]
            yr = lambda k: int(b[k]["value"][:4].lstrip("-") or 0) * (-1 if b[k]["value"].startswith("-") else 1) if k in b else None
            out[qid] = {
                "birth_year": yr("birth"), "death_year": yr("death"),
                "gender": b.get("genderLabel", {}).get("value"),
            }
        time.sleep(0.3)
    return out


def gutenberg_count(name):
    """# of Project Gutenberg works matching this person (public-domain texts online)."""
    try:
        r = requests.get("https://gutendex.com/books", params={"search": name},
                         headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        # count only where the person appears as an author (not just mentioned)
        n = 0
        nl = name.lower()
        for bk in results:
            for a in bk.get("authors", []):
                an = a.get("name", "").lower()         # "Surname, Given"
                parts = [p.strip() for p in an.replace(",", " ").split()]
                if all(tok in parts for tok in nl.split() if len(tok) > 2):
                    n += 1; break
        return n
    except Exception:
        return None


def main():
    people = load_people()
    existing = {}
    cov_path = DATA / "covariates.csv"
    if cov_path.exists():
        existing = {r["wikidata_id"]: r for _, r in pd.read_csv(cov_path).iterrows()}

    todo = [p for p in people if p["wikidata_id"] not in existing]
    print(f"{len(people)} people, {len(todo)} to fetch ({len(existing)} cached)")

    if todo:
        lengths = wiki_article_lengths([p["wikipedia_title"] for p in todo])
        bios = wikidata_bio([p["wikidata_id"] for p in todo])
        rows = []
        for i, p in enumerate(todo, 1):
            g = gutenberg_count(p["name"])
            bio = bios.get(p["wikidata_id"], {})
            death = bio.get("death_year")
            rows.append({
                "wikidata_id": p["wikidata_id"], "name": p["name"],
                "category": p["category"], "fame_tier": p["fame_tier"],
                "wiki_bytes": lengths.get(p["wikipedia_title"]),
                "birth_year": bio.get("birth_year"), "death_year": death,
                "gender": bio.get("gender"),
                "gutenberg_works": g,
                "has_gutenberg": (g or 0) > 0,
                # rough public-domain proxy: died long enough ago (US life+70 / ~95yr rule)
                "public_domain": bool(death and death <= THIS_YEAR - 95),
            })
            if i % 20 == 0:
                print(f"  gutenberg {i}/{len(todo)}", flush=True)
            time.sleep(0.1)
        new = pd.DataFrame(rows)
        combined = pd.concat([pd.DataFrame(existing.values()), new], ignore_index=True) \
            if existing else new
        combined.to_csv(cov_path, index=False)
        print(f"wrote {len(combined)} rows -> data/covariates.csv")
    else:
        print("nothing to fetch.")


if __name__ == "__main__":
    main()
