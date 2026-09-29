# DoCA homepage fixture (real, captured live)

`home_2026-09-29.html` is the exact body `transport.fetch()` got from https://fcainfoweb.nic.in/
at 2026-09-29T16:01 UTC (sha256 in the meta file, verified by the tests). It is the page that
produced `data/processed/doca_all_india/as_on=2026-09-29__fetched=20260929T160118Z.csv`.
The body is unedited. It includes the page's own CAPTCHA text and ASP.NET viewstate, which
this project never uses.
