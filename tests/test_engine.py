"""Index engine on the real 2026-09-29 DoCA rows.

The MISSING case is simulated by *removing* a real row (a gap), never by adding one.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from thaliflation.config import load_baskets, load_commodity_map
from thaliflation.coverage import load_doca_prices
from thaliflation.engine import EXCLUDED, MISSING, OK, compute_costs, compute_index, dq_panel
from thaliflation.ingest.doca_home import DocaPriceRow, store_rows

BASE = date(2026, 9, 29)


@pytest.fixture
def prices(doca_rows: list[DocaPriceRow], tmp_path: Path) -> pd.DataFrame:
    store_rows(doca_rows, root=tmp_path)
    return load_doca_prices(root=tmp_path)


def _run(prices: pd.DataFrame) -> pd.DataFrame:
    costs, _ = compute_costs(prices, load_baskets(), load_commodity_map())
    return compute_index(costs, BASE, 100).set_index("thali")


def test_veg_thali_cost_and_base_index(prices: pd.DataFrame) -> None:
    out = _run(prices)
    veg = out.loc["veg_thali"]
    assert veg["status"] == OK and veg["geo"] == "All India"
    assert veg["cost"] == pytest.approx(22.29725, abs=1e-9)
    assert veg["index"] == pytest.approx(100.0)


def test_nonveg_is_excluded_because_egg_is_unverified(prices: pd.DataFrame) -> None:
    nonveg = _run(prices).loc["nonveg_thali"]
    assert nonveg["status"] == EXCLUDED and pd.isna(nonveg["cost"]) and pd.isna(nonveg["index"])
    assert "egg" in nonveg["excluded_reason"]


def test_one_missing_ingredient_makes_the_whole_thali_missing(prices: pd.DataFrame) -> None:
    gap = prices[~((prices["price_type"] == "retail") & (prices["commodity"] == "Tomato"))]
    veg = _run(gap).loc["veg_thali"]
    assert veg["status"] == MISSING and veg["missing_items"] == "tomato"
    assert pd.isna(veg["cost"]) and pd.isna(veg["index"])  # no substitution, no partial sum


def test_components_carry_provenance(prices: pd.DataFrame) -> None:
    _, comps = compute_costs(prices, load_baskets(), load_commodity_map())
    assert len(comps) == 10 and comps["cost"].sum() == pytest.approx(22.29725, abs=1e-9)
    assert comps["raw_path"].str.endswith("home_2026-09-29.html").all()
    assert comps["raw_sha256"].nunique() == 1


def test_no_base_date_or_base_without_data_gives_no_index(prices: pd.DataFrame) -> None:
    costs, _ = compute_costs(prices, load_baskets(), load_commodity_map())
    assert compute_index(costs, None, 100)["index"].isna().all()
    later = compute_index(costs, date(2026, 10, 1), 100)  # a date with no snapshot
    assert later["index"].isna().all()
    assert later["index_note"].str.contains("no complete basket").all()


def test_dq_panel_reports_configured_city_without_source(prices: pd.DataFrame) -> None:
    costs, _ = compute_costs(prices, load_baskets(), load_commodity_map())
    dq = dq_panel(costs, ["Delhi"]).set_index(["geo", "thali"])
    assert dq.loc[("All India", "veg_thali"), "n_ok"] == 1
    assert dq.loc[("All India", "nonveg_thali"), "n_excluded"] == 1
    assert dq.loc[("Delhi", "*"), "n_dates"] == 0
