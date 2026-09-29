"""Coverage maths on the real 2026-09-29 DoCA rows. Gaps must be counted, not filled."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from thaliflation.coverage import load_doca_prices, series_coverage, write_coverage_report
from thaliflation.ingest.doca_home import DocaPriceRow, store_rows


def _frame(rows: list[DocaPriceRow], tmp_path: Path) -> pd.DataFrame:
    store_rows(rows, root=tmp_path)
    return load_doca_prices(root=tmp_path)


def test_single_real_day_has_no_gaps(doca_rows: list[DocaPriceRow], tmp_path: Path) -> None:
    cov = series_coverage(_frame(doca_rows, tmp_path), as_of=date(2026, 9, 29))
    assert len(cov) == 64
    assert (cov["observed_days"] == 1).all() and (cov["missing_days"] == 0).all()


def test_days_without_a_snapshot_are_reported_as_missing(
    doca_rows: list[DocaPriceRow], tmp_path: Path
) -> None:
    # Report three days later with no new snapshot: each series must show 3 missing days.
    cov = series_coverage(_frame(doca_rows, tmp_path), as_of=date(2026, 10, 2))
    assert (cov["expected_days"] == 4).all()
    assert (cov["missing_days"] == 3).all()
    assert (cov["pct_missing"] == 75.0).all()
    assert set(cov["missing_dates"]) == {"2026-09-30;2026-10-01;2026-10-02"}


def test_report_lists_blocked_sources(doca_rows: list[DocaPriceRow], tmp_path: Path) -> None:
    path = write_coverage_report(
        _frame(doca_rows, tmp_path), date(2026, 9, 29), out_dir=tmp_path / "reports"
    )
    text = path.read_text(encoding="utf-8")
    assert "datagov_mandi" in text and "blocked" in text
    assert "| retail | Rice | 2026-09-29 | 2026-09-29 | 1 | 1 | 0 | 0.0 |" in text
