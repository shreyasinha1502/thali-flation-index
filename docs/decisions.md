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

## M3: configs + unit conversion — 2026-09-29

**D18. The commodity strings in `commodity_map.yaml` now match the live page exactly.** The
config said to match the real response, not the guesses. Changed: `Mustard Oil` →
`Mustard Oil (Packed)`, `Salt` → `Salt Pack (Iodised)`, `Milk` → `Milk @`, `Egg` → `Eggs`.
A test asserts every mapped string appears in the real 2026-09-29 page.

**D19. The exact unit factor is used, and the declared factor is only cross-checked.**
`price_factor` must agree with `source_unit` within 0.1 % or loading fails, which catches
typos such as 0.01 for per_kg. The maths then uses the exact value, e.g. 1/12 for
per_dozen, not the config's rounded 0.08333. Recipe and source units must be compatible
(g ↔ kg/quintal, ml ↔ litre, piece ↔ dozen/piece), otherwise `ConfigError` is raised.

**D20. Egg stays VERIFY, so the non-veg thali is excluded.** "Eggs" is published (₹83.81 on
2026-09-29), but its unit isn't stated verifiably, and the page's "₹/Kg" header is provably
wrong for other additional commodities. Assuming "per dozen" would be inventing a unit. The
non-veg thali will be computed once a source confirms the unit.

**D21. Milk uses `per_litre`, the config's assumption, with a caveat.** The page marks milk
with "@", and the footnote isn't on the page. `per_litre` is what the config asserts and
fits an exception marker on a "₹/Kg" table. Impact if wrong: 50 ml at ₹61.31/L is ₹3.07,
versus ₹3.16 treating it as ₹/kg at about 1.03 g/ml, about 0.4 % of the veg thali.

## M4: index engine — 2026-09-29

**D22. `base_date` is 2026-09-29.** It's the first (and only) real date with a complete veg
basket in the M2 coverage report: DoCA's All-India average, 10/10 ingredients published. On
that date the veg thali costs ₹22.29725 and indexes to 100.

**D23. "All India" is DoCA's published average, not our mean over cities.** The spec's
all-India figure is a mean over cities with complete baskets. No city-level series exists yet:
DoCA centre reports are behind a CAPTCHA and the mandi API needs the key. The engine
therefore uses DoCA's own All-India average as the geo "All India" and labels it that way. The
city aggregator will be written once a real city series exists to test it against. Configured
cities without a source (Delhi) show up in the data-quality panel as "no live source".

**D24. Status semantics.**
- OK: every ingredient is priced that day.
- MISSING: any ingredient is absent. Cost and index are NaN, with no partial sum and no
  substitution.
- EXCLUDED: the basket uses a non-CONFIRMED mapping.

The index is computed only for OK rows, against the base-date cost of the same geo and thali.
If that base cost doesn't exist, every index for the series is NaN, with a note saying why.

## M5–M7 — 2026-09-29

**D25. M5 is deliberately thin.** There is one real day of history. Top movers is
implemented; it compares the two latest published dates and reports the real gap between
them, and it refuses to run with fewer than two dates. Volatility, anomaly flags, the veg vs
non-veg divergence and a CPI lead/lag test all need weeks of real data, and CPI also needs a
data source (such as MoSPI) that isn't on the approved list yet. Writing them now would mean
code that can't be checked against real data.

**D26. The prospective menu-price layer isn't built.** The spec names no menu source.
Scraping delivery apps raises terms-of-service problems and would be a new data source, so it
needs the user's choice and approval first.

**D27. Raw HTML for DoCA is committed, gzip'd.** Stored rows point at their raw file through
`raw_path`. On an ephemeral CI filesystem that pointer would dangle unless the raw file is
committed. gzip is lossless: sha256 and n_bytes describe the uncompressed body, and
`read_raw()` verifies them. The size is about 20 KB a day. The first five captures, from
before compression existed, stay uncompressed, since the raw cache is append-only.

**D28. Session cookies are never stored.** DoCA's responses set `ASP.NET_SessionId` and
`BNI_persistence` cookies, which are anonymous session tokens. The transport now redacts
`Set-Cookie`, `Cookie` and `Authorization` header values in cache metadata. The six
already-written meta files were redacted in place, with a note added to each; the response
bodies are untouched. Commit b706812 (local only, never pushed) still contains one expired
anonymous DoCA session id. History wasn't rewritten for that, because the token carries no
login, expires within minutes and belongs to a public page.

**D29. The daily workflow commits even when the snapshot fails.** The raw failure record and
the refreshed coverage report are evidence of the gap. The run is then marked red, so a gap is
recorded and visible, never silent. The GitHub runners may be outside India; see the README's
known-risk note.
