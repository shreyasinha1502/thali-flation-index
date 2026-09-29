# Thali-flation Index

A hyperlocal, high-frequency **"cost of a thali"** index for India, computed only from real
government ingredient prices. It can be compared against official CPI, which is aggregate and
published about 1.5 months late, to test whether it leads food inflation.

```
thali_cost(city, date) = Σ qty_i × unit_price_i(city, date)      # MISSING if any ingredient is missing
index(city, date)      = thali_cost(city, date) / thali_cost(city, base_date) × 100
```

## Non-negotiable: no synthetic data

- No price, date, city or record is ever fabricated, mocked, randomised, interpolated or
  forward-filled. Not in code, not in tests.
- If a source is down or a value is absent, the pipeline logs it, skips it and records the gap
  in a coverage report. Missing stays missing.
- Every stored row carries provenance: source name, endpoint, fetch timestamp and a pointer to
  the raw response. The raw response is cached to disk before any transformation.
- Tests run against real responses captured from the live sources.
- `tests/test_guardrails.py` fails the build if random generators, faker, interpolation or
  forward/back-fill appear anywhere in `src/`, `tests/`, `scripts/` or `app/`.
  `config/index.yaml: allow_synthetic` must stay `false`.

## Data sources

| # | Source | Kind | Status (last checked) |
|---|--------|------|------------------------|
| 1 | data.gov.in Mandi API `9ef84268-d588-465a-a308-a864a43d0070` | wholesale, daily snapshot | Gateway **live** (2026-09-28). Blocked on key. No data pulled yet: the public sample key only returns 429/403/504, so a personal `DATA_GOV_API_KEY` is needed. The gateway tarpits the `python-requests` UA (see docs/decisions.md D7). |
| 2 | DoCA Price Monitoring Division (fcainfoweb.nic.in) | retail, 38 commodities, ~550 centres | **Ingesting daily** (public homepage: All-India averages, one date per day). Centre-wise reports are CAPTCHA-gated and not automated. |
| 3 | data.gov.in per-commodity daily/weekly retail price CSVs | retail history backfill | Verified: history **ends in 2015**; downloads are CAPTCHA-gated, API needs `DATA_GOV_API_KEY`. |

The **historical ingredient index** is the main deliverable. A **prospective menu-price layer**
(M6) only grows through daily snapshots from its start date and is never backfilled.

## Setup

```bash
py -3.12 -m venv .venv            # any Python >= 3.11
.venv/Scripts/python -m pip install -r requirements-dev.txt -e .
cp .env.example .env              # then set DATA_GOV_API_KEY
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
```

(On Linux/macOS use `.venv/bin/python`.)

## Layout

```
config/            baskets.yaml, commodity_map.yaml, index.yaml  (domain assumptions, not data)
data/raw/          cached raw responses, byte-for-byte (gitignored)
data/processed/    normalised, provenance-stamped tables (committed)
docs/decisions.md  non-obvious decisions and why
src/thaliflation/  package: settings, logging, ingestion, index engine
tests/             guardrails + tests on real captured fixtures
```

## Milestones

- [x] **M0** Scaffold, pinned deps, JSON logging with secret redaction, guardrail tests
- [~] **M1** Ingestion
  - [x] Transport: retry/backoff, byte-exact raw cache, failure records, key redaction
  - [x] Source #2: DoCA homepage daily snapshot (`scripts/snapshot_doca.py`), first real day 2026-09-29
  - [ ] Source #1: mandi API schema + one-day pull, **blocked on `DATA_GOV_API_KEY`**
- [x] **M2** Coverage report (`data/processed/reports/coverage.md`); source #3 backfill blocked on key
- [x] **M3** Typed configs, commodity strings matched to the live page, conversion tests on real rows
- [x] **M4** Missing-aware index engine + data-quality panel (veg thali All India = ₹22.30 = 100 on 2026-09-29)
- [ ] **M5** Analysis: movers are implemented; volatility, anomalies and CPI lead/lag need weeks of real history (and a CPI source, pending approval)
- [x] **M6** Streamlit dashboard with an always-visible coverage/gaps panel. Menu-price layer: **no source chosen yet**
- [~] **M7** Daily GitHub Actions workflow + Streamlit Cloud config written; needs the repo pushed and the app connected (steps below)

See `docs/sources.md` for what each source really provides, and `docs/decisions.md` for why.

## Daily pipeline

```bash
python scripts/snapshot_doca.py   # fetch + cache raw + parse + store (only if values changed)
python scripts/build_index.py     # coverage report + thali index + components + DQ panel
streamlit run app/streamlit_app.py
```

## Deployment (M7)

**Persistence.** Streamlit Community Cloud's filesystem is ephemeral. Real data therefore
lives in git. The scheduled workflow `.github/workflows/daily-snapshot.yml` runs at 13:30 UTC
(19:00 IST). It snapshots DoCA, rebuilds the index and coverage report, and commits
`data/processed/` plus the gzip'd raw HTML in `data/raw/doca_home/` (about 20 KB a day),
so every stored price keeps a verifiable raw file. The dashboard reads only those committed
files, and Streamlit Cloud redeploys on each push. If the repo gets heavy, move raw and
processed files to an object store (S3, R2 or GCS) or a hosted DB (e.g. MotherDuck or
Postgres) and have the app read from there. That hasn't been done yet.

1. **GitHub.** Create an empty repo, then:
   ```bash
   git remote add origin https://github.com/<you>/thali-flation-index.git
   git push -u origin main
   ```
2. **Actions.** Under Settings → Actions → General → Workflow permissions, choose **Read and
   write**. Then open Actions → daily-snapshot → **Run workflow** once to confirm it's green.
3. **Secrets.** When you have a data.gov.in key, add it under Settings → Secrets and
   variables → Actions → `DATA_GOV_API_KEY`. The key is never committed; `.env` is gitignored.
4. **Streamlit.** Go to [share.streamlit.io](https://share.streamlit.io) → Create app → pick
   the repo, branch `main`, main file `app/streamlit_app.py`. Under Advanced settings, set
   Python to 3.12. The app needs no secrets. If later features need the key, add
   `DATA_GOV_API_KEY = "..."` under the app's Settings → Secrets.

**Known risk:** `fcainfoweb.nic.in` may refuse non-Indian IPs, and GitHub's runners are in the
US or EU. A refusal turns the run red and records the attempt in the raw cache and coverage
report. It is never replaced with anything. If that happens, run `snapshot_doca.py` from an
Indian machine or a self-hosted runner.
