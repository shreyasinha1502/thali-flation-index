"""Config validation + unit-conversion maths on REAL DoCA rows (2026-09-29 fixture).

Every expected rupee value is qty x published price x unit factor, worked out by hand from
the prices DoCA published that day. The published prices are asserted first, so a changed
fixture can't slip through.
"""

from __future__ import annotations

import pytest

from thaliflation.config import (
    BasketItem,
    CommodityMapping,
    ConfigError,
    IndexConfig,
    ingredient_cost,
    load_baskets,
    load_commodity_map,
    load_index_config,
    validate,
)
from thaliflation.ingest.doca_home import DocaPriceRow

BASKETS = load_baskets()
CMAP = load_commodity_map()


def _retail(rows: list[DocaPriceRow], commodity: str) -> float:
    return next(r.price for r in rows if r.price_type == "retail" and r.commodity == commodity)


def test_configs_load_and_cross_validate() -> None:
    assert set(BASKETS) == {"veg_thali", "nonveg_thali"}
    assert len(BASKETS["veg_thali"]) == 10 and len(BASKETS["nonveg_thali"]) == 8
    validate(BASKETS, CMAP)
    assert load_index_config().allow_synthetic is False


def test_every_mapped_commodity_string_exists_in_the_live_source(
    doca_rows: list[DocaPriceRow],
) -> None:
    published = {r.commodity for r in doca_rows if r.price_type == "retail"}
    for ingredient, m in CMAP.items():
        assert m.source_commodity in published, f"{ingredient}: {m.source_commodity!r} not on page"


# (ingredient, published ₹ price on 2026-09-29, expected ₹ for the veg-thali quantity)
VEG_EXPECTED = [
    ("rice", 46.64, 80 * 46.64 / 1000),  # 3.7312
    ("atta", 37.65, 60 * 37.65 / 1000),  # 2.259
    ("tur_dal", 125.95, 30 * 125.95 / 1000),  # 3.7785
    ("potato", 22.60, 100 * 22.60 / 1000),  # 2.26
    ("onion", 53.97, 40 * 53.97 / 1000),  # 2.1588
    ("tomato", 40.11, 40 * 40.11 / 1000),  # 1.6044
    ("cooking_oil", 203.14, 15 * 203.14 / 1000),  # 3.0471
    ("salt", 22.48, 5 * 22.48 / 1000),  # 0.1124
    ("sugar", 56.07, 5 * 56.07 / 1000),  # 0.28035
    ("milk", 61.31, 50 * 61.31 / 1000),  # 3.0655 (ml at ₹/litre)
]


@pytest.mark.parametrize(("ingredient", "published", "expected"), VEG_EXPECTED)
def test_veg_ingredient_cost_on_real_prices(
    doca_rows: list[DocaPriceRow], ingredient: str, published: float, expected: float
) -> None:
    m = CMAP[ingredient]
    price = _retail(doca_rows, m.source_commodity)
    assert price == published
    item = next(i for i in BASKETS["veg_thali"] if i.ingredient == ingredient)
    assert ingredient_cost(item, m, price) == pytest.approx(expected, rel=1e-12)


def test_veg_thali_total_on_2026_09_29(doca_rows: list[DocaPriceRow]) -> None:
    total = sum(
        ingredient_cost(
            i, CMAP[i.ingredient], _retail(doca_rows, CMAP[i.ingredient].source_commodity)
        )
        for i in BASKETS["veg_thali"]
    )
    assert total == pytest.approx(22.29725, abs=1e-9)


def test_exact_factor_is_used_not_the_rounded_config_value() -> None:
    egg = CMAP["egg"]
    assert egg.price_factor == 0.08333 and egg.exact_factor == pytest.approx(1 / 12)


def test_price_factor_that_contradicts_unit_is_rejected() -> None:
    with pytest.raises(ValueError, match="disagrees"):
        CommodityMapping(
            source_commodity="Rice",
            source_unit="per_kg",
            price_factor=0.01,
            source_status="CONFIRMED",
            preferred_source="DoCA_retail",
        )


def test_incompatible_recipe_and_source_units_are_rejected() -> None:
    grams = BasketItem(ingredient="milk", qty=50, unit="g", weight=1.0)
    with pytest.raises(ConfigError, match="incompatible"):
        ingredient_cost(grams, CMAP["milk"], 61.31)


def test_allow_synthetic_true_is_rejected() -> None:
    with pytest.raises(ValueError):
        IndexConfig(
            base_date=None, base_value=100, cities=[], missing_policy="drop", allow_synthetic=True
        )  # type: ignore[arg-type]
