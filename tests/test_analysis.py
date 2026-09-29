"""Analysis helpers on the real 2026-09-29 data. With one real day, movers must refuse."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from thaliflation.analysis import daily_calendar, top_movers
from thaliflation.config import load_baskets, load_commodity_map
from thaliflation.coverage import load_doca_prices
from thaliflation.engine import compute_costs, compute_index
from thaliflation.ingest.doca_home import DocaPriceRow, store_rows


def _prices(rows: list[DocaPriceRow], tmp_path: Path) -> pd.DataFrame:
    store_rows(rows, root=tmp_path)
    return load_doca_prices(root=tmp_path)


def test_movers_refuse_with_a_single_real_day(
    doca_rows: list[DocaPriceRow], tmp_path: Path
) -> None:
    movers, reason = top_movers(_prices(doca_rows, tmp_path))
    assert movers.empty and reason is not None and "have 1" in reason


def test_calendar_marks_days_without_snapshot_and_breaks_segments(
    doca_rows: list[DocaPriceRow], tmp_path: Path
) -> None:
    costs, _ = compute_costs(_prices(doca_rows, tmp_path), load_baskets(), load_commodity_map())
    idx = compute_index(costs, date(2026, 9, 29), 100)
    veg = idx[idx["thali"] == "veg_thali"]
    cal = daily_calendar(veg, as_of=date(2026, 10, 1))
    assert list(cal["as_on_date"]) == [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]
    assert list(cal["status"]) == ["OK", "NO SNAPSHOT", "NO SNAPSHOT"]
    assert cal["index"].iloc[0] == 100 and cal["index"].iloc[1:].isna().all()  # not filled
    assert cal["segment"].iloc[0] != cal["segment"].iloc[2]
