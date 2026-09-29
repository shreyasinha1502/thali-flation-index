"""Daily snapshot of DoCA's public All-India average prices (cron-ready, no API key needed).

    python scripts/snapshot_doca.py

Fetches https://fcainfoweb.nic.in/ once, caches the raw HTML, parses and validates the price
tables, and writes data/processed/doca_all_india/as_on=<date>__fetched=<ts>.csv if the page has
new values. Exit code 0 = stored or unchanged, 1 = fetch/parse failure (logged, nothing written).
"""

from __future__ import annotations

import sys

from thaliflation.ingest.doca_home import (
    DOCA_HOME_SOURCE,
    DOCA_HOME_URL,
    DocaParseError,
    parse_home,
    store_rows,
)
from thaliflation.ingest.raw_cache import new_run_dir
from thaliflation.ingest.transport import FetchError, fetch
from thaliflation.logging_setup import get_logger, setup_logging
from thaliflation.settings import LOG_DIR

log = get_logger("snapshot_doca")


def main() -> int:
    setup_logging(log_file=LOG_DIR / "snapshot_doca.jsonl")
    run_dir = new_run_dir(DOCA_HOME_SOURCE)
    try:
        result = fetch(DOCA_HOME_URL, {}, source=DOCA_HOME_SOURCE, run_dir=run_dir, name="home")
        rows, skipped = parse_home(result.body.decode("utf-8"), artifact=result.artifact)
    except (FetchError, DocaParseError) as exc:
        log.error("doca_snapshot_failed", extra={"error": str(exc)})
        return 1
    written = store_rows(rows)
    as_on = sorted({(r.price_type, r.as_on_date.isoformat()) for r in rows})
    print(f"parsed {len(rows)} prices, skipped {len(skipped)} non-numeric; as-on: {as_on}")
    print("written:", [p.name for p in written] or "nothing (unchanged since last snapshot)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
