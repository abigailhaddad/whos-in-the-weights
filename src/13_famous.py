"""
Step 13 — A 'famous' anchor tier: household names, to extend the fame gradient to the top
so the predictive story spans obscure -> well-known -> famous (not two clumps).
Hand-picked, 3 per category, unique-ish names. Writes names_famous.json.
"""
import json, re, time, unicodedata
from pathlib import Path
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"
WDQS = "https://query.wikidata.org/sparql"

FAMOUS = {
    "politician": ["Barack Obama", "Angela Merkel", "Hillary Clinton"],
    "athlete":    ["Lionel Messi", "Serena Williams", "Usain Bolt"],
    "scientist":  ["Stephen Hawking", "Jane Goodall", "Neil deGrasse Tyson"],
    "musician":   ["Beyoncé", "Taylor Swift", "Paul McCartney"],
    "actor":      ["Meryl Streep", "Tom Hanks", "Denzel Washington"],
    "novelist":   ["Stephen King", "Margaret Atwood", "J. K. Rowling"],
    "journalist": ["Anderson Cooper", "Christiane Amanpour", "Bob Woodward"],
}


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def run_sparql(query):
    r = requests.get(WDQS, params={"query": query, "format": "json"},
                     headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}, timeout=120)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def pageviews(title):
    import datetime as dt
    end = dt.date.today().replace(day=1); start = (end - dt.timedelta(days=365)).replace(day=1)
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
           f"all-access/all-agents/{requests.utils.quote(title.replace(' ', '_'), safe='')}/monthly/"
           f"{start.strftime('%Y%m01')}/{end.strftime('%Y%m01')}")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    items = r.json().get("items", []) if r.status_code == 200 else []
    return round(sum(it["views"] for it in items) / len(items)) if items else None


def main():
    names = [(n, c) for c, lst in FAMOUS.items() for n in lst]
    vals = " ".join('"%s"@en' % n.replace('"', '\\"') for n, _ in names)
    rows = run_sparql(f"""
      SELECT ?name ?person ?sl ?article WHERE {{
        VALUES ?name {{ {vals} }}
        ?person rdfs:label ?name ; wdt:P31 wd:Q5 ; wikibase:sitelinks ?sl .
        ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
      }}""")
    best = {}
    for b in rows:                      # pick the most-linked human per name (the famous one)
        nm = b["name"]["value"]; sl = int(b["sl"]["value"])
        if nm not in best or sl > best[nm][0]:
            best[nm] = (sl, b["person"]["value"].rsplit("/", 1)[-1],
                        requests.utils.unquote(b["article"]["value"].rsplit("/", 1)[-1]))

    out = []
    for nm, cat in names:
        if nm not in best:
            print(f"  ! no Wikidata match for {nm}"); continue
        sl, qid, title = best[nm]
        pv = pageviews(title); time.sleep(0.05)
        out.append({"name": nm, "wikipedia_title": title, "wikidata_id": qid,
                    "sitelinks": sl, "pageviews_monthly_avg": pv, "category": cat,
                    "fame_tier": "famous", "fame_label": "Household name",
                    "slug": slugify(nm), "occupations": []})
        print(f"  {cat:11} {nm:22} {pv:>8} views/mo")
    (DATA / "names_famous.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {len(out)} -> names_famous.json")


if __name__ == "__main__":
    main()
