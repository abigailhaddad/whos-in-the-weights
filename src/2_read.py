"""
Step 2 — Read whatever intheweights.com already has cached, across all sampled tiers.

GET /api/result/<slug> is open (no bot-check). For each person in every data/names_<tier>.json
we read the cached result; hits are saved to data/raw/<slug>.json (cached per person, so this
never re-fetches generation). Misses go to data/uncached.json for the browser step (step 3).

Run again after generation to pick up the newly-cached names.
"""
import json, time, glob
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"; RAW.mkdir(parents=True, exist_ok=True)
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"


def read(slug):
    try:
        r = requests.get(f"https://intheweights.com/api/result/{slug}",
                         headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
        if r.status_code == 200 and '"referents"' in r.text:
            return r.json()
    except Exception:
        pass
    return None


def load_people():
    people = []
    for f in sorted(glob.glob(str(DATA / "names_*.json"))):
        people.extend(json.loads(Path(f).read_text()))
    return people


def main():
    people = load_people()
    cached, uncached = [], []
    for i, rec in enumerate(people, 1):
        data = read(rec["slug"])
        if data:
            data["_meta"] = rec
            (RAW / f"{rec['slug']}.json").write_text(json.dumps(data, ensure_ascii=False))
            cached.append(rec); tag = "cached"
        else:
            uncached.append(rec); tag = "MISS"
        print(f"  [{i:>3}/{len(people)}] {tag:6} {rec['fame_tier']:5} {rec['category']:11} {rec['name']}")
        time.sleep(0.08)

    (DATA / "uncached.json").write_text(json.dumps(uncached, indent=2, ensure_ascii=False))
    print(f"\ncached {len(cached)}/{len(people)}  |  {len(uncached)} need generation")
    from collections import Counter
    tot = Counter((r["fame_tier"], r["category"]) for r in people)
    hit = Counter((r["fame_tier"], r["category"]) for r in cached)
    for k in sorted(tot):
        print(f"   {k[0]:5} {k[1]:11} {hit[k]:>2}/{tot[k]:>2} cached")


if __name__ == "__main__":
    main()
