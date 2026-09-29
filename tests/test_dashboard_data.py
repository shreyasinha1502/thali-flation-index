"""Dashboard payload built from real pipeline outputs (2026-09-29 DoCA snapshot)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from thaliflation.config import load_baskets, load_commodity_map, load_index_config
from thaliflation.coverage import load_doca_prices, write_coverage_report
from thaliflation.dashboard_data import build_payload
from thaliflation.engine import compute_costs, compute_index, dq_panel
from thaliflation.ingest.doca_home import DocaPriceRow, store_rows


@pytest.fixture
def processed(doca_rows: list[DocaPriceRow], tmp_path: Path) -> Path:
    """Run the real pipeline steps on the real fixture into a temp processed/ dir."""
    store_rows(doca_rows, root=tmp_path)
    prices = load_doca_prices(tmp_path)
    costs, comps = compute_costs(prices, load_baskets(), load_commodity_map())
    icfg = load_index_config()
    idx = compute_index(costs, icfg.base_date, icfg.base_value)
    (tmp_path / "index").mkdir()
    idx.to_csv(tmp_path / "index" / "thali_index.csv", index=False)
    comps.to_csv(tmp_path / "index" / "components.csv", index=False)
    dq_panel(idx, icfg.cities).to_csv(tmp_path / "index" / "dq_panel.csv", index=False)
    write_coverage_report(prices, date(2026, 9, 29), out_dir=tmp_path / "reports")
    return tmp_path


def test_payload_carries_exact_real_values(processed: Path) -> None:
    p = build_payload(date(2026, 9, 29), processed)
    json.dumps(p, allow_nan=False)  # no NaN/inf can reach the frontend
    assert p["order"] == ["veg_thali", "nonveg_thali"]
    veg, nonveg = p["thalis"]["veg_thali"], p["thalis"]["nonveg_thali"]
    assert veg["latest"] == {"date": "2026-09-29", "cost": pytest.approx(22.29725), "index": 100.0}
    assert veg["previous"] is None
    assert [i["ingredient"] for i in veg["items"]][:2] == ["tur_dal", "rice"]
    assert sum(i["share"] for i in veg["items"]) == pytest.approx(1.0)
    # non-veg: egg per dozen (DoCA's own stated unit) -> 2 eggs = 2 * 83.81 / 12
    assert nonveg["status"] == "OK" and nonveg["latest"]["cost"] == pytest.approx(
        32.297533, abs=1e-6
    )
    egg = nonveg["items"][0]
    assert egg["ingredient"] == "egg" and egg["cost"] == pytest.approx(2 * 83.81 / 12)
    assert egg["source_unit"] == "per_dozen" and egg["share"] == pytest.approx(
        13.968333 / 32.297533
    )
    assert [r["label"] for r in p["coverage"]["rows"]][-1] == "Eggs"  # union of both baskets
    assert len(p["coverage"]["rows"]) == 11
    assert p["geos_without_source"][0]["geo"] == "Delhi"
    assert p["movers"]["rows"] == [] and "have 1" in p["movers"]["reason"]


def test_days_without_snapshot_reach_the_frontend_as_gaps(processed: Path) -> None:
    p = build_payload(date(2026, 10, 1), processed)
    for t in p["thalis"].values():
        assert [s["index"] for s in t["series"]] == [100.0, None, None]
        assert [s["status"] for s in t["series"]][1:] == ["NO SNAPSHOT", "NO SNAPSHOT"]
        assert t["history"] == {"ok_days": 1, "calendar_days": 3, "first_date": "2026-09-29"}
    assert all(row["cells"] == [True, False, False] for row in p["coverage"]["rows"])


def test_empty_processed_dir_gives_not_ready(tmp_path: Path) -> None:
    assert build_payload(date(2026, 9, 29), tmp_path)["ready"] is False
