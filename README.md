# Watchlist Monitor — Sanctions Surveillance Web App

A self-contained web app that pulls official sanctions/watchlist feeds,
normalizes them to one schema, stores versioned snapshots, computes a daily
diff (added / removed / modified), and screens names against the current set.

## What's included

```
sanctions-app/
├── backend/
│   ├── sources.py     # feed definitions (which sources, URLs, enabled flags)
│   ├── parsers.py     # XML -> common normalized record
│   ├── storage.py     # SQLite snapshots + history + diff engine
│   ├── ingest.py      # fetch/parse/store runner + name screening
│   ├── scheduler.py   # optional daily loop
│   └── app.py         # Flask server + JSON API
├── frontend/
│   └── index.html     # dashboard (change feed, source status, screening)
├── data/              # sqlite db is created here
└── requirements.txt
```

## Sources — honest status

| Source    | Auto-feed? | Notes |
|-----------|------------|-------|
| OFAC      | Yes        | Official consolidated XML. |
| UN        | Yes        | Official canonical XML. |
| EU        | Token req. | Needs a free EU FSF login token. Set the URL in `sources.py` and flip `enabled` to True. |
| INTERPOL  | No         | No official feed; scraping violates their ToS. Add entries manually or via a licensed provider. |

Consider **OpenSanctions** (opensanctions.org) if you'd rather consume one
pre-consolidated, normalized daily dataset instead of maintaining parsers.

## Setup

```bash
cd sanctions-app
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python backend/app.py
```

Open http://127.0.0.1:5000 and click **Run ingest now** (requires internet
access to the official feeds). For automation, run `python backend/scheduler.py`
or point cron at `POST /api/ingest`.

## API

- `POST /api/ingest` — fetch + diff all enabled sources
- `GET  /api/stats` — per-source last-updated + counts
- `GET  /api/changes?limit=400` — recent change feed
- `GET  /api/screen?q=NAME&threshold=0.5` — screen a name

## Feed validation (catches format drift)

Before any fetched feed is trusted and stored, it passes through
`validation.py`, which guards against the most common real-world failures:

- **Not XML / HTML error page** (login, redirect, maintenance, 5xx) → `fail`
- **Malformed or truncated XML** → `fail`
- **Expected record element missing** (source renamed its structure) → `fail`
- **Name/id fields renamed** (parses but records come out blank) → `warn`
- **Suspicious count collapse** (e.g. list drops 40%+ vs last snapshot) → `warn`

On **fail**, the snapshot is *not stored* — this prevents a broken fetch from
overwriting good data or producing a false "everything was removed" diff. On
**warn**, the snapshot is stored but flagged for review. All statuses surface
on the dashboard as a banner and in the `POST /api/ingest` JSON response.

Tune the thresholds (`min_records`, swing ratio) per source in
`validation.py` → `CONTRACTS`.

## Production hardening checklist

- Replace token-overlap matching with rapidfuzz + phonetic/transliteration handling.
- Move from SQLite to Postgres for concurrency and retention.
- Add authentication and an immutable audit log of every screen and ingest.
- Add alerting (email/Slack) on diffs; validate each feed's schema before trusting it.
- Respect every source's terms of service; this tool is a starting point, not legal/compliance advice.
```
