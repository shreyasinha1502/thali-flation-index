# data.gov.in gateway fixtures (real, captured live)

Byte-for-byte copies of responses the pipeline's own `transport.fetch()` received from
`api.data.gov.in` on 2026-09-28 (see each `*.meta.json` for URL, timestamp, headers and sha256).
Nothing here was edited or hand-written.

| dir | what the live gateway returned |
|-----|--------------------------------|
| `rate_limited_429/` | public sample key → `429 {"error": "Rate limit exceeded"}` (no Retry-After) |
| `auth_missing_400/` | no key → `400 {"error": "Authorization field missing"}` |

A real `200` page fixture will be added once `DATA_GOV_API_KEY` is available (M1 part 2).
