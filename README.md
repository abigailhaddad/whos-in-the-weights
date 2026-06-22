# Who's in the weights?

A small experiment in **which kinds of people language models know.**

- **Live site:** https://whos-in-the-weights.vercel.app
- **Data source:** [intheweights.com](https://intheweights.com), which asks 13 models, for one
  person at a time, how confident each is that it knows who that person is (a 0–100 score per model).

We sample real people from Wikidata across **seven occupations**, hold fame roughly constant by
matching on Wikipedia pageviews, run them through intheweights.com, and look for patterns in who
the models recognize. Every number describes **our sample** — a deliberately wide spread from
household names to the genuinely obscure — not the world. They're comparisons, not rates.

## What "in the weights" means

A model's *weights* are the billions of numbers it learns in training. A person is "in the
weights" if a model can recall them on its own, without a web search — and that's rarely
all-or-nothing, so each model reports a **confidence** from 0 ("never heard of them") to 100
("sure who they are"). intheweights.com combines a person's 13 confidences into one "strength"
score; we work with the 13 underlying numbers.

## The findings (what the site shows)

The site (`web/`) is a single-scroll data story. Each section is one claim + one labelled chart:

1. **How the 13 models score one person** — one person's 13 confidences, to ground what a score
   is. For the same person, the answers can span the whole 0–100 range.
2. **More looked up → better known, but loosely** — recognition vs monthly Wikipedia pageviews
   (n = 185). It climbs — household names sit near the top — but loosely: among the rarely
   looked-up, models know some people well and draw a blank on others just as obscure.
3. **Some models are far more confident than others** — average confidence per model runs from
   ~90 (Gemini 3.1 Flash Lite) down to ~18 (Llama 3.2 1B). Which model you ask explains ~23% of
   the variation in scores; which person, ~41%.
4. **But they mostly rank people the same way** — set the levels aside and the models *order*
   people similarly: a typical pair has a Spearman rank correlation of ~0.65 (range 0.17–0.88).
   The clear outlier is the smallest model, which barely tracks the rest.
5. **Your line of work barely matters — except for athletes** — six of the seven occupations land
   within a few points of each other (~64–70); athletes are the lone exception (~56). The gap is
   *not* a fame artifact, and (see below) not a name-commonness artifact either.
6. **A shared name costs you a little** — controlled test on German footballers, unique vs shared
   *full* name, matched on fame: **−18 points (−17 adjusting for article length).** Real but modest.
7. **The short version** — recognition tracks how often the world looks someone up (loosely); a
   shared name hurts a bit; the models agree on the *ranking* of who's better-known but differ
   enormously in how confident they are overall — so whether a borderline person is "in the
   weights" depends on which model you ask.

## Two cautionary tales (being fooled by your own measurement)

The most interesting findings here are two results that **looked strong and turned out to be
artifacts** — both worth keeping as methods notes.

**1. The name effect, chased through three rounds.**
1. *Circular:* intheweights' own "referent count" (how many people it surfaced for a name)
   "predicted" the score at r ≈ −0.6 — but that count is built from the models' answers, so it
   just restates "the models were unsure." Leakage; dropped.
2. *Confounded:* an independent Wikidata namesake count showed shared-name people −27 — but the
   shared cohort was ~75% German, the unique cohort international. Nationality confound.
3. *Controlled:* re-run within German footballers only (`src/15_name_experiment_v2.py`) — same
   nationality and job, only the name differs: **−18 points, t ≈ −2.2.** The honest answer.

**2. "Athletes lag because of common names" — disproved.**
Controlling for the *circular* referent count cut the athlete gap roughly in half, which looked
like a tidy explanation. But with an **independent Wikidata namesake count** for the whole
sample, athletes do *not* have commoner names (the sample was drawn for unique names — median 1
namesake in every occupation), and controlling for it leaves the athlete gap essentially
unchanged (−13.0 → −13.2). The "half is shared names" story was the circular measure again. The
athlete gap is real and unexplained by fame, article length, or namesakes.

## What predicts the score

- **How often someone is looked up** (Wikipedia pageviews) tracks recognition — loosely.
- **How much is written about them** (Wikipedia article length) predicts recognition about as well
  as pageviews do.
- **A shared full name** costs ~18 points (controlled test above).
- **Public-domain text — tested and rejected.** A raw Project Gutenberg split looked huge
  (89 vs 61) but was a fame confound. Matching public-domain (died <1930) vs in-copyright
  novelists on *current* pageviews erases it (**72.8 vs 77.0, n.s.**). Free scrapeable text
  doesn't help once fame is held constant.
- We deliberately do **not** use intheweights' referent count as a predictor — it's derived from
  the models' own answers (see cautionary tale 1).

## Design

`data/dataset_people.csv` holds 291 real people, each an instance-of-human on Wikidata with an
English Wikipedia article (so "everyone is on Wikipedia" holds across groups). They fall into:

- **The fame spread** — *well-known* (~2.5k views/mo) and *obscure* (~170) tiers across all seven
  occupations {politician, actor, musician, athlete, scientist, journalist, novelist}, plus a small
  *famous* anchor tier (Taylor Swift, etc.). Within a tier, people are matched on monthly pageviews.
- **Targeted sub-cohorts** for specific tests: German footballers with unique vs shared full names
  (the name experiment), and public-domain vs in-copyright novelists (the Gutenberg test). An
  earlier international name cohort (`names_nameuniq` / `names_nameshared`) is **superseded** by the
  German one and kept only for the record.

**Outcome.** For each (person, model): `confidence` (0–100) and `recognitionScore` from
intheweights, plus its category guess, `existenceConfidence`, and global `weightRank`. We match
each result back to *our* sampled person (name + occupation keywords); if a person is never
surfaced, that's a real recognition-0 datapoint, not a namesake grab.

## Data source mechanics

- `GET /api/result/<slug>` returns the full result as JSON — open, no bot-check.
- Results exist only for names someone has searched. Uncached names must be **generated** via
  `POST /api/search`, gated by a Cloudflare Turnstile token minted by the page UI. We generate by
  driving the real search box in a verified browser (`src/generate_notes.md`), reading the
  canonical slug from the URL, and verifying the result's `query` matches the name.

## Configuration & incremental design

Everything tunable lives in **`config.yaml`**: the groups (Wikidata occupation QIDs) and the fame
rules (per-tier sitelink + pageview bands). The pipeline is **incremental** — adding a category or
fame tier and re-running only generates the *new* people. Sampling skips any tier already present
in `data/names_<tier>.json`, and generation is cached per person (`data/raw/<slug>.json`), so
existing work is never redone. (Delete a tier's names file to deliberately re-sample it.)

## Pipeline

```
config.yaml        groups + per-tier fame rules (edit here)
src/1_sample.py    Wikidata -> matched-fame, unique-name sample per tier -> data/names_<tier>.json
src/2_read.py      read cached results across tiers, flag uncached       -> data/raw/, data/uncached.json
(generate)         drive intheweights UI for uncached names (browser)    -> data/slugmap.json
src/2_read.py      re-run to fetch the now-cached results                -> data/raw/
src/3_parse.py     match referent to our person, build tidy data         -> data/dataset_long.csv, data/dataset_people.csv
src/4_analyze.py   summary stats + exploratory charts                    -> charts/
src/5_webdata.py   aggregates + share image for the front end           -> web/data.json, web/og-image.png
```

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python src/1_sample.py     # samples only tiers/categories not yet sampled
.venv/bin/python src/2_read.py
#   ... generate uncached names (see src/generate_notes.md) ...
.venv/bin/python src/2_read.py
.venv/bin/python src/3_parse.py
.venv/bin/python src/4_analyze.py
.venv/bin/python src/5_webdata.py
```

The name experiment and other sub-analyses have their own scripts (`src/12_agreement.py`,
`src/15_name_experiment_v2.py`, `src/7_covariate_analysis.py`, …). `src/14_name_experiment.py` is
the **superseded** (confounded) v1 of the name test.

## Front end

A static single-page data story in `web/` — HTML/CSS/vanilla JS, no build step.
`src/5_webdata.py` emits `web/data.json` and the social-share `web/og-image.png`; everything the
page shows is read from `data.json` at render time. Scatter dots and model names are hoverable
(Wikipedia previews; model maker, size, and knowledge cutoff).

```bash
.venv/bin/python src/5_webdata.py     # refresh web/data.json + og-image after any data change
cd web && python -m http.server 8731  # then open http://localhost:8731
```

Deployed to Vercel from `web/`:

```bash
vercel deploy --prod --cwd web
```

## Caveats

- **Ceiling at this fame level.** People at ~2.5k monthly views are notable enough that frontier
  models know nearly all of them; the interesting variation lives in smaller models. Lower the
  fame band in `config.yaml` to push more people to the edge of knowable.
- **Heavily international / historical sample.** The matched-fame band skews toward 20th-century
  European figures; English-language web presence may depress some scores uniformly.
- **Generation is non-deterministic** (LLM sampling) and reflects intheweights' own prompting,
  clustering, and model roster — we measure that pipeline, not the models in isolation. Each
  model's self-reported confidence is uncalibrated and can vary between runs.
- Wikidata occupations overlap; each person's full occupation list is recorded in
  `data/dataset_people.csv` for audit.
