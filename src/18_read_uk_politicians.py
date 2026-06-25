"""
Step 18 — Read UK politician scores from intheweights.com and save to data files.

Reads the API for all people in the names_gbpol_*.json files,
saves full model-by-model scores, updates slugmap.json, and appends to
dataset_long.csv and dataset_people.csv.
"""
import json, csv, requests, time, re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "weights-research/0.1 (+https://github.com/abigailhaddad/whos-in-the-weights) educational"

SLUGMAP = {
    'Bernard Henry Bourdillon': 'bernard-henry-bourdillon',
    'Thomas Flamank': 'thomas-flamank', 'Percy Sykes': 'percy-sykes',
    'Alf Morris': 'alf-morris', 'McKeeva Bush': 'mckeeva-bush',
    'Denis Pritt': 'denis-pritt', 'Charles Hendry': 'charles-hendry',
    'Richard Gavin Reid': 'richard-gavin-reid', 'Ann Winterton': 'ann-winterton',
    'Claus Moser, Baron Moser': 'claus-moser~2c~-baron-moser',
    'Harry Hylton-Foster': 'harry-hylton~2d~foster',
    'Elizabeth Symons, Baroness Symons of Vernham Dean': 'elizabeth-symons~2c~-baroness-symons-of-vernham-dean',
    'Colin Burgon': 'colin-burgon', 'Simon Mackay, Baron Tanlaw': 'simon-mackay~2c~-baron-tanlaw',
    'Anne Begg': 'anne-begg', 'Angus Maude': 'angus-maude',
    'Richard Marsh, Baron Marsh': 'richard-marsh~2c~-baron-marsh', 'David Nuttall': 'david-nuttall',
    'Ian Lang, Baron Lang of Monkton': 'ian-lang~2c~-baron-lang-of-monkton',
    'Cyril Garbett': 'cyril-garbett', 'Jonathan Edwards': 'jonathan-edwards',
    'George Adam': 'george-adam', 'Liz Smith': 'liz-smith', 'Thomas Ley': 'thomas-ley',
    'Kevin Stewart': 'kevin-stewart', 'Thomas Woodcock': 'thomas-woodcock',
    'Jessica Lee': 'jessica-lee', 'Tim Stevens': 'tim-stevens',
    'Bob Russell': 'bob-russell', 'Henry Bellingham': 'henry-bellingham',
    'John Holmes': 'john-holmes', 'Michael Ball': 'michael-ball',
    'John Oliver': 'john-oliver', 'Stephen Williams': 'stephen-williams',
    'Anne McGuire': 'anne-mcguire', 'Terry Davis': 'terry-davis',
    'Leslie Wilson': 'leslie-wilson', 'David Drew': 'david-drew',
    'Ian Davidson': 'ian-davidson', 'Richard Taylor': 'richard-taylor',
    'Willie Whitelaw': 'willie-whitelaw', 'Stafford Cripps': 'stafford-cripps',
    'Leo Amery': 'leo-amery', 'Duncan Sandys': 'duncan-sandys',
    'Nicholas Stern, Baron Stern of Brentford': 'nicholas-stern~2c~-baron-stern-of-brentford',
    'Halford Mackinder': 'halford-mackinder', 'Bernard Miles': 'bernard-miles',
    'Tim Farron': 'tim-farron', 'Gusty Spence': 'gusty-spence',
    'Anna Soubry': 'anna-soubry', 'Alf Dubs, Baron Dubs': 'alf-dubs~2c~-baron-dubs',
    'Tristram Hunt': 'tristram-hunt', 'Duff Cooper': 'duff-cooper',
    'Geoff Hoon': 'geoff-hoon',
    'Edward Carson, Baron Carson': 'edward-carson~2c~-baron-carson',
    'Helena Kennedy, Baroness Kennedy of The Shaws': 'helena-kennedy~2c~-baroness-kennedy-of-the-shaws',
    'Archibald Maule Ramsay': 'archibald-maule-ramsay', 'Caroline Nokes': 'caroline-nokes',
    'Kate Hoey': 'kate-hoey', 'Harold Nicolson': 'harold-nicolson',
    'Nick Brown': 'nick-brown', 'Keith Joseph': 'keith-joseph',
    'Steve Baker': 'steve-baker', 'John Woodcock': 'john-woodcock',
    'Mervyn King': 'mervyn-king', 'Martin Bell': 'martin-bell',
    'Kurt Hahn': 'kurt-hahn', 'Tom Watson': 'tom-watson',
    'Michael Martin': 'michael-martin', 'David Trimble': 'david-trimble',
    'Norman Lamont': 'norman-lamont', 'Philip Hammond': 'philip-hammond',
    "Jim O'Neill": 'jim-o~27~neill', 'Ian Murray': 'ian-murray',
    'William Temple': 'william-temple', 'Geoffrey Cox': 'geoffrey-cox',
    'Greg Clark': 'greg-clark', 'Alok Sharma': 'alok-sharma',
    'Arthur Henderson': 'arthur-henderson', 'Robert Stephenson': 'robert-stephenson',
    'Nawaz Sharif': 'nawaz-sharif', 'Anthony Eden': 'anthony-eden',
    'Jerry Springer': 'jerry-springer', 'Bernard Montgomery': 'bernard-montgomery',
    'Harold Macmillan': 'harold-macmillan', 'Ed Miliband': 'ed-miliband',
    'Laurence Fox': 'laurence-fox', 'Glenda Jackson': 'glenda-jackson',
    'Alan Sugar': 'alan-sugar', 'Nicola Sturgeon': 'nicola-sturgeon',
    'Liz Kendall': 'liz-kendall', 'Boris Johnson': 'boris-johnson',
    'John Major': 'john-major', 'Gordon Brown': 'gordon-brown',
    'Harold Wilson': 'harold-wilson', 'David Cameron': 'david-cameron',
    'Alastair Campbell': 'alastair-campbell', 'Altaf Hussain': 'altaf-hussain',
    'Robert Maxwell': 'robert-maxwell',
}

GROUP_FILES = [
    'names_gbpol_uniq_lo.json', 'names_gbpol_shared_lo.json',
    'names_gbpol_uniq_mid.json', 'names_gbpol_shared_mid.json',
    'names_gbpol_uniq_hi.json', 'names_gbpol_shared_hi.json',
]


def norm(s):
    import unicodedata
    return unicodedata.normalize('NFKD', s or '').lower().strip()


def fetch_result(slug):
    url = f'https://intheweights.com/api/result/{slug}'
    for attempt in range(3):
        try:
            r = requests.get(url, headers={'User-Agent': UA}, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(2)
    return None


def main():
    # Load all people from group files
    all_people = {}
    for fname in GROUP_FILES:
        p = DATA / fname
        if not p.exists():
            print(f"Missing: {fname}")
            continue
        for person in json.loads(p.read_text()):
            all_people[person['name']] = person

    print(f"Total people to read: {len(all_people)}")

    # Fetch all results
    api_results = {}
    for name, person in all_people.items():
        slug = SLUGMAP.get(name)
        if not slug:
            print(f"  No slug for {name}")
            continue
        data = fetch_result(slug)
        if not data:
            print(f"  Failed to fetch {name}")
            continue
        referents = data.get('referents', [])
        matched = next((r for r in referents if norm(r.get('name', '')) == norm(name)), None)
        if not matched and referents:
            matched = referents[0]
        if matched:
            api_results[name] = {'data': data, 'matched': matched, 'slug': slug}
        time.sleep(0.08)

    print(f"Got API results for {len(api_results)} people")

    # Update slugmap.json
    slugmap_path = DATA / 'slugmap.json'
    slugmap = json.loads(slugmap_path.read_text()) if slugmap_path.exists() else {}
    for name, slug in SLUGMAP.items():
        if name in api_results:
            slugmap[name] = slug
    slugmap_path.write_text(json.dumps(slugmap, indent=2, ensure_ascii=False))
    print(f"slugmap.json updated ({len(slugmap)} entries)")

    # Build new rows for dataset_long.csv
    existing_long = list(csv.DictReader((DATA / 'dataset_long.csv').open()))
    existing_names = {r['name'] for r in existing_long}
    fieldnames = list(existing_long[0].keys())

    new_long_rows = []
    new_people_rows = []

    for name, res in api_results.items():
        if name in existing_names:
            continue
        person = all_people[name]
        matched = res['matched']
        cells = matched.get('cells', {})

        # dataset_long rows (one per model)
        for model_id, cell in cells.items():
            conf = cell.get('confidence', 0)
            rec = cell.get('recognitionScore', conf)
            row = {
                'name': name,
                'category': person['category'],
                'fame_tier': person['fame_tier'],
                'pageviews_monthly_avg': person['pageviews_monthly_avg'],
                'model': model_id,
                'model_id': model_id,
                'param_class': '',
                'knowledge_cutoff': '',
                'confidence': conf,
                'recognition_score': rec,
                'result_count': cell.get('resultCount', ''),
                'recognized': str(conf > 0),
                'matched_person': 'True',
            }
            new_long_rows.append(row)

        # dataset_people row
        confs = [cell.get('confidence', 0) for cell in cells.values()]
        new_people_rows.append({
            'name': name,
            'slug': res['slug'],
            'category': person['category'],
            'fame_tier': person['fame_tier'],
            'fame_label': person.get('fame_label', ''),
            'pageviews_monthly_avg': person['pageviews_monthly_avg'],
            'sitelinks': '',
            'occupations': '; '.join(person.get('occupations', [])),
            'matched': 'True',
            'matched_referent': matched.get('name', ''),
            'matched_descriptor': matched.get('descriptor', ''),
            'matched_id': res['slug'],
            'site_category': '',
            'existence_confidence': matched.get('existenceConfidence', ''),
            'weight_rank': matched.get('weightRank', {}).get('rank', ''),
            'weight_total': matched.get('weightRank', {}).get('total', ''),
            'n_referents': len(res['data'].get('referents', [])),
            'n_models_recognize': sum(1 for c in confs if c > 0),
            'n_models': len(confs),
        })

    # Append to dataset_long.csv
    if new_long_rows:
        with open(DATA / 'dataset_long.csv', 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            for row in new_long_rows:
                w.writerow({k: row.get(k, '') for k in fieldnames})
        print(f"Appended {len(new_long_rows)} rows to dataset_long.csv")

    # Append to dataset_people.csv
    if new_people_rows:
        existing_ppl = list(csv.DictReader((DATA / 'dataset_people.csv').open()))
        ppl_fields = list(existing_ppl[0].keys())
        with open(DATA / 'dataset_people.csv', 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=ppl_fields)
            for row in new_people_rows:
                w.writerow({k: row.get(k, '') for k in ppl_fields})
        print(f"Appended {len(new_people_rows)} rows to dataset_people.csv")

    print("\nFinal results by band:")
    import statistics as st
    for band in ['lo', 'mid', 'hi']:
        uf = DATA / f'names_gbpol_uniq_{band}.json'
        sf = DATA / f'names_gbpol_shared_{band}.json'
        if not uf.exists() or not sf.exists():
            continue
        u = [p['name'] for p in json.loads(uf.read_text())]
        s = [p['name'] for p in json.loads(sf.read_text())]
        def avg_score(names):
            scores = []
            for n in names:
                if n in api_results:
                    cells = api_results[n]['matched'].get('cells', {})
                    confs = [c.get('confidence', 0) for c in cells.values()]
                    if confs: scores.append(sum(confs)/len(confs))
            return scores
        us = avg_score(u); ss = avg_score(s)
        if us and ss:
            print(f"  {band}: unique={st.mean(us):.1f} (n={len(us)}), shared={st.mean(ss):.1f} (n={len(ss)}), gap={st.mean(us)-st.mean(ss):+.1f}")


if __name__ == '__main__':
    main()
