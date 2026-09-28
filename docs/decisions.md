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
