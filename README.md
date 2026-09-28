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
| 1 | data.gov.in Mandi API `9ef84268-d588-465a-a308-a864a43d0070` | wholesale, daily snapshot | Gateway **live** (2026-09-28). No data pulled yet: the public sample key only returns 429/403/504, so a personal `DATA_GOV_API_KEY` is needed. The gateway tarpits the `python-requests` UA (see docs/decisions.md D7). |
| 2 | DoCA Price Monitoring Division (fcainfoweb.nic.in) | retail, 38 commodities, ~550 centres | Not yet investigated (planned for M2) |
| 3 | data.gov.in per-commodity daily/weekly retail price CSVs | retail history backfill | Not yet investigated (M2) |

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

- [x] **M0** Scaffold: venv, pinned requirements, `.env.example`, JSON logging with secret
  redaction, configs, guardrail tests
- [~] **M1** Mandi API ingestion
  - [x] part 1: retry/backoff transport, byte-exact raw cache, failure records, key redaction,
    liveness probe (`scripts/probe_mandi.py`), tests on real captured gateway responses
  - [ ] part 2 (**blocked on `DATA_GOV_API_KEY`**): schema from a real 200 page, pagination,
    provenance-stamped normalized table, one real day end-to-end
- [ ] **M2** Historical CSV backfill + coverage report
- [ ] **M3** Basket / mapping configs + unit-conversion tests on real rows
- [ ] **M4** Missing-aware index engine + data-quality panel
- [ ] **M5** Movers, veg vs non-veg divergence, volatility, anomalies, CPI lead/lag
- [ ] **M6** Streamlit dashboard with coverage panel + daily menu snapshot script
- [ ] **M7** Deployment: Streamlit Community Cloud + GitHub Actions daily commit of real data
