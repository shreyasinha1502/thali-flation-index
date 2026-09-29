# Decisions log

Non-obvious choices, newest last. Each entry records what was decided, why, and what evidence
it rests on.

## M0 — 2026-09-28

**D1. `config/baskets.yaml` syntax repaired, values unchanged.**
The supplied file had several `key: value` pairs on one line (`- ingredient: rice   qty: 80 ...`).
PyYAML rejects this (`ScannerError: mapping values are not allowed here`). Each item is now a
flow mapping `{ ingredient: rice, qty: 80, unit: g, weight: 1.0 }`. Every quantity, unit, weight
and comment is the same as supplied. `commodity_map.yaml` and `index.yaml` parsed as supplied and
are copied verbatim.

**D2. No python-dotenv.** It isn't on the approved dependency list, and parsing `KEY=VALUE`
lines takes about 15 lines of stdlib (`settings.load_env_file`). Real environment variables
override `.env`, so GitHub Actions and Streamlit secrets win in CI and deployment.

**D3. Python 3.12 venv.** The spec requires 3.11+. 3.14 is also installed, but 3.12 has the
widest wheel support for the later statsmodels, prophet and streamlit stack, and both GitHub
Actions and Streamlit Community Cloud offer it.

**D4. JSON-lines logging with secret redaction.** The data.gov.in key goes in the query string
(`api-key=`), so any logged URL would leak it. Every secret read through `require_secret()` is
registered and scrubbed from all rendered log lines. `urllib3` is pinned to WARNING because its
DEBUG output prints full request URLs.

**D5. Guardrail test for the no-synthetic rule.** `tests/test_guardrails.py` scans all code for
random generators, faker, `.interpolate(`, `ffill/bfill` and `fillna(method=)`. The rule is
enforced by CI, not only by convention.

**D6. Observed live behaviour of source #1 (2026-09-28 ~06:10 UTC).**
- The endpoint is served through a Tyk gateway (`X-Generator: tyk.io`).
- With no key it returns `400 {"error": "Authorization field missing"}`.
- With the public sample key it returned `429 {"error": "Rate limit exceeded"}` on every
  attempt (backoff 0/5/15/30/60 s). There was no `Retry-After` header, so the client must use
  its own exponential backoff.
- One attempt failed at TCP connect after 21 s, so retries must also cover connection errors,
  not only HTTP status codes.
- Conclusion: the shared sample key can't be relied on, even for a probe. The pipeline requires
  `DATA_GOV_API_KEY` and fails loudly without it.

## M1 (part 1: transport + raw cache) — 2026-09-28

**D7. The gateway tarpits the `python-requests` User-Agent.** Measured the same minute:
- curl, default UA, no key → `400` in 1.05 s
- curl with `-A python-requests/2.34.2` → 0 bytes after 60 s
- requests with its default UA → `ReadTimeout` after 61 s, and empty-body `502`s from a proxy
  (`Server: Caddy`)
- requests with a non-default UA → `400` in about 9 s

Every early "outage" seen from Python was this block. The transport now sends an honest
`thaliflation/<version> (food-price research)` UA. It doesn't impersonate curl or a browser.
A contact URL can be added once the public repo exists (M7).

**D8. The API key can only be sent as the `api-key` query parameter.** The gateway ignores it as
the `api-key`, `Authorization` or `X-API-KEY` header (all return 400
`Authorization field missing`). Keys in URLs leak easily. A first live run crashed on a
LogRecord name clash, and the default traceback printed the full URL including the (public
sample) key. Mitigations:
1. Every `requests` exception becomes a `FetchError` with a redacted message, raised with
   `from None`.
2. `setup_logging` installs a redacting `sys.excepthook`.
3. Cache metadata and logs store only `api-key=***`.

Tests check that the key never appears in errors, logs or cached files.

**D9. The public sample key is unusable.** Over about 30 minutes it returned 429
`Rate limit exceeded`, 403 `Key not authorised` and 504 (nginx upstream timeout, HTML body), but
never a 200. A personal `DATA_GOV_API_KEY` is required. No fallback exists.

**D10. M1 is split at the point where real data is required.** The spec says to confirm the
endpoint and show a real raw sample before writing ingestion. Only the schema-independent parts
are built: retry/backoff, byte-exact raw cache and failure records, all tested against real
captured gateway responses. The record schema (pydantic), normalizer, pagination-by-`total` and
the one-day end-to-end pull wait for a real 200 page. They will be written against its actual
field names, types, date format and price units, with no assumed schema.

**D11. Deterministic backoff, no jitter.** Jitter needs a random source, and the guardrail bans
`random` outright to keep the no-synthetic rule simple to enforce. With one client and one
daily run, a thundering herd isn't a concern. Backoff is 2, 4, 8, … s, capped at 120 s, and
`Retry-After` is honoured if the server ever sends it.

**D12. A fetch with no response still leaves a record.** When every attempt fails at the
connection level, `write_failure()` writes a meta-only record (`status: null`, attempt history)
so the gap stays visible in the raw audit trail and later coverage reports.

## Source #2 ingestion (DoCA homepage) — 2026-09-29

**D13. Priority changed: user asked for everything to be done without waiting on them.** The
`DATA_GOV_API_KEY` blocker remains. Creating the account and key is a human step (account
creation and credentials can't be automated here). Source #2 is the spec's preferred source
(`preferred_source: DoCA_retail` for every ingredient), so it was taken up next. Full inventory
is in docs/sources.md.

**D14. The DoCA report generator is CAPTCHA-gated and is not automated.** No CAPTCHA
solving, and no hunting for an undocumented mobile-app backend to get around it. The public
homepage, which needs no CAPTCHA, is ingested instead. It publishes one "As on" date of
All-India averages, so it is snapshotted daily and history accumulates going forward. Nothing
is backfilled.

**D15. Strict HTML parsing with stdlib `html.parser`.** This avoids adding bs4 or lxml, which
aren't on the approved list. The parser expects the observed structure:
- an `<h2>` holding "All India Average (Retail|Wholesale) Price(<unit>) As on DD/MM/YYYY"
- `<caption>` elements holding "… Price - <group>"
- a header row of exactly `Commodity | Prices`

Any deviation raises `DocaParseError`, the run fails and nothing is written. A non-numeric
price cell is logged and skipped, never set to zero.

**D16. Storage is one CSV per as-on date, written only when the published values change.**
The raw HTML differs on every fetch (CAPTCHA text, viewstate), so change detection hashes the
published values (as_on, price_type, commodity, price), not the bytes. A revised page for an
already-stored date is written as a new file, and readers take the latest fetch. CSVs are small
(64 rows) and diff cleanly in git, which suits the M7 commit-back workflow.

**D17. `unit_stated` is stored verbatim; units are trusted only via config.** The page's
"₹/Kg" retail header is demonstrably wrong for several "Additional Commodities" (see
docs/sources.md). The stored rows keep what the page says. Which unit a price is in, for index
maths, is asserted per ingredient in `config/commodity_map.yaml`.
