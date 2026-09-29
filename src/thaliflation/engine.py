"""Thali cost + index engine. Missing-aware; no substitution, no gap filling.

    cost(geo, date, thali) = Σ qty_i * price_i(geo, date) * unit_factor_i * weight_i
    index(geo, date, thali) = cost / cost(geo, base_date) * base_value

Status per (geo, date, thali):
    OK        every ingredient has a real published price that day
    MISSING   at least one ingredient price absent -> cost and index are NaN (missing_policy: drop)
    EXCLUDED  the basket uses a mapping that is not CONFIRMED (e.g. egg: VERIFY) -> never computed

Geography: the only live series today is DoCA's *published* All-India average (geo "All India").
It's DoCA's own average across its centres, not a mean computed here over cities. Configured
cities with no source are reported in the data-quality panel as having no data.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from thaliflation.config import BasketItem, CommodityMapping, ingredient_cost

OK, MISSING, EXCLUDED = "OK", "MISSING", "EXCLUDED"

COST_COLS = [
    "as_on_date",
    "geo",
    "thali",
    "status",
    "cost",
    "n_items",
    "n_priced",
    "missing_items",
    "excluded_reason",
]
COMPONENT_COLS = [
    "as_on_date",
    "geo",
    "thali",
    "ingredient",
    "source_commodity",
    "qty",
    "unit",
    "price",
    "source_unit",
    "cost",
    "source",
    "raw_path",
    "raw_sha256",
]


def compute_costs(
    prices: pd.DataFrame,
    baskets: dict[str, list[BasketItem]],
    cmap: dict[str, CommodityMapping],
    *,
    price_type: str = "retail",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (costs, components). `prices` = rows as stored by an ingester (latest fetch)."""
    p = prices[prices["price_type"] == price_type]
    lookup = {(r.geo, r.as_on_date, r.commodity): r for r in p.itertuples(index=False)}
    cost_rows, comp_rows = [], []
    for geo, day in sorted({(r.geo, r.as_on_date) for r in p.itertuples(index=False)}):
        for thali, items in baskets.items():
            unverified = [
                i.ingredient for i in items if cmap[i.ingredient].source_status != "CONFIRMED"
            ]
            base = {"as_on_date": day, "geo": geo, "thali": thali, "n_items": len(items)}
            if unverified:
                cost_rows.append(
                    {
                        **base,
                        "status": EXCLUDED,
                        "cost": float("nan"),
                        "n_priced": 0,
                        "missing_items": "",
                        "excluded_reason": "unverified mapping: " + ",".join(unverified),
                    }
                )
                continue
            missing, parts = [], []
            for item in items:
                m = cmap[item.ingredient]
                row = lookup.get((geo, day, m.source_commodity))
                if row is None:
                    missing.append(item.ingredient)
                    continue
                c = ingredient_cost(item, m, float(row.price))
                parts.append(c)
                comp_rows.append(
                    {
                        "as_on_date": day,
                        "geo": geo,
                        "thali": thali,
                        "ingredient": item.ingredient,
                        "source_commodity": m.source_commodity,
                        "qty": item.qty,
                        "unit": item.unit,
                        "price": float(row.price),
                        "source_unit": m.source_unit,
                        "cost": c,
                        "source": row.source,
                        "raw_path": row.raw_path,
                        "raw_sha256": row.raw_sha256,
                    }
                )
            cost_rows.append(
                {
                    **base,
                    "status": MISSING if missing else OK,
                    "cost": float("nan") if missing else sum(parts),
                    "n_priced": len(parts),
                    "missing_items": ",".join(missing),
                    "excluded_reason": "",
                }
            )
    return (
        pd.DataFrame(cost_rows, columns=COST_COLS),
        pd.DataFrame(comp_rows, columns=COMPONENT_COLS),
    )


def compute_index(costs: pd.DataFrame, base_date: date | None, base_value: float) -> pd.DataFrame:
    """Add base_date, base_cost, index, index_note. Index only where status is OK."""
    out = costs.copy()
    out["base_date"] = base_date
    out["base_cost"] = float("nan")
    out["index"] = float("nan")
    out["index_note"] = ""
    if base_date is None:
        out["index_note"] = "base_date not set"
        return out
    for (_geo, _thali), g in out.groupby(["geo", "thali"]):
        base = g[(g["as_on_date"] == base_date) & (g["status"] == OK)]
        if base.empty:
            out.loc[g.index, "index_note"] = f"no complete basket on base date {base_date}"
            continue
        base_cost = float(base["cost"].iloc[0])
        ok = g.index[g["status"] == OK]
        out.loc[g.index, "base_cost"] = base_cost
        out.loc[ok, "index"] = out.loc[ok, "cost"] / base_cost * base_value
    return out


def dq_panel(costs: pd.DataFrame, configured_geos: list[str]) -> pd.DataFrame:
    """Per (geo, thali): how many days were computable, and which were dropped and why."""
    rows = []
    for (geo, thali), g in costs.groupby(["geo", "thali"]):
        dropped = g[g["status"] != OK]
        rows.append(
            {
                "geo": geo,
                "thali": thali,
                "n_dates": len(g),
                "n_ok": int((g["status"] == OK).sum()),
                "n_missing": int((g["status"] == MISSING).sum()),
                "n_excluded": int((g["status"] == EXCLUDED).sum()),
                "first_date": min(g["as_on_date"]),
                "last_date": max(g["as_on_date"]),
                "dropped": "; ".join(
                    f"{r.as_on_date}:{r.status}({r.missing_items or r.excluded_reason})"
                    for r in dropped.itertuples()
                ),
            }
        )
    have = set(costs["geo"]) if not costs.empty else set()
    for geo in configured_geos:
        if geo not in have:
            rows.append(
                {
                    "geo": geo,
                    "thali": "*",
                    "n_dates": 0,
                    "n_ok": 0,
                    "n_missing": 0,
                    "n_excluded": 0,
                    "first_date": None,
                    "last_date": None,
                    "dropped": "no live source for this geography yet",
                }
            )
    return pd.DataFrame(rows)
