# Source inventory (verified live)

What each spec-listed source actually delivers, checked against the live endpoints.
Nothing here is assumed; each line says what was observed and when.

## #1 data.gov.in Mandi API: resource `9ef84268-d588-465a-a308-a864a43d0070`
*Checked 2026-09-28.*
- **Kind:** wholesale mandi prices, per market.
- **History:** none. It is a rolling current-day snapshot, so history only exists if we
  snapshot it every day.
- **Access:** needs a personal `DATA_GOV_API_KEY`, passed only as the `api-key` query
  parameter. The public sample key returns 429/403/504 and never a 200 (D9).
- **Gateway quirk:** it tarpits the `python-requests` User-Agent (D7).
- **Status:** transport and probe built. Schema and one-day pull are **blocked on the key**.

## #2 DoCA Price Monitoring Division: fcainfoweb.nic.in
*Checked 2026-09-29.*

**Report generator `Reports/Report_Menu_Web.aspx`.** Offers retail and wholesale price
reports, average/month-end reports and variation reports over a selected time span, with
centre-level history. The form requires a **CAPTCHA** (`ctl00$MainContent$Captcha`).
Automating CAPTCHA-gated reports, or hunting for an undocumented app backend to get round
them, is off-limits for this project, so these reports are **not automated**. A human could
download them by hand, and an importer for such exports could be added.

**Homepage `https://fcainfoweb.nic.in/`.** Public, no CAPTCHA.
- Shows **All India Average Retail Price (₹/Kg)** for 41 commodities and **All India
  Average Wholesale Price (₹/Qtl.)** for 23, "As on" a single date.
- Only one day is shown and there is no history, so it must be snapshotted daily
  (`scripts/snapshot_doca.py`).
- It is the All-India average only, with no city breakdown.
- The retail section header says "₹/Kg" for every row. That cannot hold for the
  "Additional Commodities" group: Black Pepper ₹88.65, Turmeric powder ₹16.74 and Butter
  ₹60.58 on 2026-09-29 are only plausible per 100 g. So `unit_stated` is stored verbatim,
  and units are trusted only where `config/commodity_map.yaml` asserts them.
- `Milk @` carries an "@" marker whose footnote is not on the page. DoCA's Price Monitoring
  Division page on consumeraffairs.gov.in lists the 38 commodities but gives no units.
- `Eggs` is published (₹83.81 on 2026-09-29) with **no verifiable unit** (dozen? kg?).

This source is ingested now.

## #3 data.gov.in per-commodity "Daily/weekly Retail prices" catalogs
*Checked 2026-09-29.*
- **What it is:** a Department of Consumer Affairs catalog per commodity, e.g.
  "Daily/weekly Retail prices of Milk" (catalog node 326781, last updated 21/09/2015).
- **Resources:**
  - "Daily retail price of Milk upto April - 2015" (resource `e5e37e68-faed-46bd-b6c2-001cbc633e29`,
    CSV of 3.1 MB, `is_api_available=1`)
  - "Weekly retail price of Milk upto 2012"
- **History ends in 2015.** These give real centre-level history, but it stops about 11 years
  before today.
- **Access:** the website's file download goes through a "download purpose" form with a
  CAPTCHA, so it is not automated. The sanctioned programmatic path is the API
  (`api.data.gov.in/resource/<uuid>`), which needs `DATA_GOV_API_KEY`.
- The data.gov.in frontend bundle embeds the portal's own API key. It was not issued to this
  project and is **never used**.
- **Status:** blocked on the key. Once available, the backfill can pull the pre-2015 series
  per commodity via the API.

## Consequence for the index

With only key-free, CAPTCHA-free access, the one real current series is the DoCA All-India
average (source #2 homepage). The historical ingredient index therefore **starts on the first
snapshot date (2026-09-29)** and grows by one real point per published day. There is no real
2015–2026 series to backfill from the listed sources without a human in the loop.
