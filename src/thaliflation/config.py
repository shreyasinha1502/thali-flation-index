"""Typed loaders for config/{baskets,commodity_map,index}.yaml.

The YAML files hold domain assumptions (portions, units, mappings), not data. They are
validated strictly:
- every basket ingredient must be mapped;
- the recipe unit must be compatible with the source unit (g↔kg/quintal, ml↔litre,
  piece↔dozen/piece);
- the declared price_factor must agree (within 0.1 %) with the factor implied by source_unit.
  The exact factor is then used, e.g. 1/12 for per_dozen rather than the rounded 0.08333;
- allow_synthetic must be false.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from thaliflation.settings import CONFIG_DIR

RecipeUnit = Literal["g", "ml", "piece"]
SourceUnit = Literal["per_kg", "per_quintal", "per_litre", "per_dozen", "per_piece"]

EXACT_FACTOR: dict[str, float] = {
    "per_kg": 1 / 1_000,
    "per_quintal": 1 / 100_000,
    "per_litre": 1 / 1_000,
    "per_dozen": 1 / 12,
    "per_piece": 1.0,
}
COMPATIBLE: dict[str, set[str]] = {
    "g": {"per_kg", "per_quintal"},
    "ml": {"per_litre"},
    "piece": {"per_dozen", "per_piece"},
}


class ConfigError(ValueError):
    pass


class BasketItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ingredient: str
    qty: float = Field(gt=0)
    unit: RecipeUnit
    weight: float = Field(gt=0)


class CommodityMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_commodity: str
    source_unit: SourceUnit
    price_factor: float = Field(gt=0)
    source_status: Literal["CONFIRMED", "VERIFY"]
    preferred_source: str

    @model_validator(mode="after")
    def _factor_matches_unit(self) -> CommodityMapping:
        exact = EXACT_FACTOR[self.source_unit]
        if abs(self.price_factor / exact - 1) > 1e-3:
            raise ValueError(
                f"price_factor {self.price_factor} disagrees with {self.source_unit} ({exact:.8g})"
            )
        return self

    @property
    def exact_factor(self) -> float:
        return EXACT_FACTOR[self.source_unit]


class IndexConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    base_date: date | None
    base_value: float = Field(gt=0)
    cities: list[str]
    missing_policy: Literal["drop"]
    allow_synthetic: Literal[False]

    @field_validator("allow_synthetic", mode="before")
    @classmethod
    def _hard_gate(cls, v: object) -> object:
        if v is not False:
            raise ValueError("allow_synthetic must be false (hard gate)")
        return v


def _read(name: str, config_dir: Path) -> object:
    return yaml.safe_load((config_dir / name).read_text(encoding="utf-8"))


def load_baskets(config_dir: Path = CONFIG_DIR) -> dict[str, list[BasketItem]]:
    raw = _read("baskets.yaml", config_dir)
    return {thali: [BasketItem(**item) for item in items] for thali, items in raw.items()}


def load_commodity_map(config_dir: Path = CONFIG_DIR) -> dict[str, CommodityMapping]:
    raw = _read("commodity_map.yaml", config_dir)
    return {ing: CommodityMapping(**m) for ing, m in raw.items()}


def load_index_config(config_dir: Path = CONFIG_DIR) -> IndexConfig:
    return IndexConfig(**_read("index.yaml", config_dir))


def check_unit(item: BasketItem, mapping: CommodityMapping) -> None:
    if mapping.source_unit not in COMPATIBLE[item.unit]:
        raise ConfigError(
            f"{item.ingredient}: recipe unit '{item.unit}' is incompatible with source unit "
            f"'{mapping.source_unit}'"
        )


def validate(baskets: dict[str, list[BasketItem]], cmap: dict[str, CommodityMapping]) -> None:
    for thali, items in baskets.items():
        seen: set[str] = set()
        for item in items:
            if item.ingredient in seen:
                raise ConfigError(f"{thali}: duplicate ingredient {item.ingredient}")
            seen.add(item.ingredient)
            if item.ingredient not in cmap:
                raise ConfigError(f"{thali}: ingredient '{item.ingredient}' has no mapping")
            check_unit(item, cmap[item.ingredient])


def ingredient_cost(item: BasketItem, mapping: CommodityMapping, source_price: float) -> float:
    """Rupees for `item.qty` recipe units, given a source price in `mapping.source_unit`."""
    check_unit(item, mapping)
    return item.qty * source_price * mapping.exact_factor * item.weight
