"""Rebuild every derived output from the stored real snapshots (idempotent, cron-ready).

    python scripts/build_index.py

Writes:
    data/processed/reports/coverage.md, coverage_series.csv   (M2 gaps report)
    data/processed/index/thali_index.csv                      (cost + index per geo/date/thali)
    data/processed/index/components.csv                       (per-ingredient cost + provenance)
    data/processed/index/dq_panel.csv                         (dropped/excluded days and why)
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta, timezone

from thaliflation.config import load_baskets, load_commodity_map, load_index_config, validate
from thaliflation.coverage import fetch_log, load_doca_prices, write_coverage_report
from thaliflation.engine import compute_costs, compute_index, dq_panel
from thaliflation.logging_setup import get_logger, setup_logging
from thaliflation.settings import LOG_DIR, PROCESSED_DIR

IST = timezone(timedelta(hours=5, minutes=30))  # fixed offset; no tzdata dependency on Windows
INDEX_DIR = PROCESSED_DIR / "index"
log = get_logger("build_index")


def main() -> int:
    setup_logging(log_file=LOG_DIR / "build_index.jsonl")
    baskets, cmap, icfg = load_baskets(), load_commodity_map(), load_index_config()
    validate(baskets, cmap)

    prices = load_doca_prices()
    as_of = datetime.now(UTC).astimezone(IST).date()
    report = write_coverage_report(prices, as_of, log=fetch_log())
    if prices.empty:
        log.error("no_prices_stored")
        return 1

    costs, components = compute_costs(prices, baskets, cmap)
    indexed = compute_index(costs, icfg.base_date, icfg.base_value)
    dq = dq_panel(indexed, icfg.cities)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    # LF on every OS, so local (Windows) and CI (Linux) rebuilds produce identical files.
    indexed.to_csv(INDEX_DIR / "thali_index.csv", index=False, lineterminator="\n")
    components.to_csv(INDEX_DIR / "components.csv", index=False, lineterminator="\n")
    dq.to_csv(INDEX_DIR / "dq_panel.csv", index=False, lineterminator="\n")

    print(f"coverage report: {report}")
    cols = [
        "as_on_date",
        "geo",
        "thali",
        "status",
        "cost",
        "index",
        "missing_items",
        "excluded_reason",
        "index_note",
    ]
    print(indexed[cols].to_string(index=False))
    print("\ndata-quality panel:")
    print(dq.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
