"""Build the JSON payload the dashboard frontend renders. Every number comes from the committed
outputs of the pipeline (data/processed/). Nothing is filled, rounded away or made up.
Missing values become null and are drawn as gaps.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from thaliflation.analysis import daily_calendar, top_movers
from thaliflation.coverage import load_doca_prices
from thaliflation.settings import PROCESSED_DIR

REPO_URL = "https://github.com/shreyasinha1502/thali-flation-index"
SOURCE_URL = "https://fcainfoweb.nic.in/"

# Presentation labels only (the data keeps the exact DoCA strings in `source_commodity`).
LABELS: dict[str, tuple[str, str]] = {
    "rice": ("Rice", "🍚"),
    "atta": ("Atta · 2 rotis", "🌾"),
    "tur_dal": ("Tur dal", "🥣"),
    "potato": ("Aloo", "🥔"),
    "onion": ("Onion", "🧅"),
    "tomato": ("Tomato", "🍅"),
    "cooking_oil": ("Mustard oil", "🌼"),
    "salt": ("Salt", "🧂"),
    "sugar": ("Sugar", "🍬"),
    "milk": ("Milk / curd", "🥛"),
}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _csv(root: Path, rel: str) -> pd.DataFrame:
    p = root / rel
    return pd.read_csv(p) if p.is_file() else pd.DataFrame()


def build_payload(as_of: date, root: Path = PROCESSED_DIR) -> dict[str, Any]:
    idx = _csv(root, "index/thali_index.csv")
    comps = _csv(root, "index/components.csv")
    prices = load_doca_prices(root)
    out: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "repo_url": REPO_URL,
        "source_url": SOURCE_URL,
        "ready": not idx.empty,
    }
    if idx.empty:
        return out

    idx["as_on_date"] = pd.to_datetime(idx["as_on_date"]).dt.date
    veg = idx[(idx["thali"] == "veg_thali") & (idx["geo"] == "All India")].sort_values("as_on_date")
    ok = veg[veg["status"] == "OK"]
    base = veg["base_date"].dropna()
    cal = daily_calendar(veg, as_of=max(as_of, veg["as_on_date"].max()))
    out["base_date"] = str(base.iloc[0]) if not base.empty else None
    out["series"] = [
        {
            "date": r.as_on_date.isoformat(),
            "index": _num(r.index),
            "cost": _num(r.cost),
            "status": r.status,
        }
        for r in cal.itertuples()
    ]
    out["history"] = {
        "ok_days": len(ok),
        "calendar_days": len(cal),
        "first_date": cal["as_on_date"].min().isoformat(),
    }

    latest = prev = None
    if not ok.empty:
        last = ok.iloc[-1]
        latest = {
            "date": last["as_on_date"].isoformat(),
            "cost": _num(last["cost"]),
            "index": _num(last["index"]),
        }
        if len(ok) > 1:
            p = ok.iloc[-2]
            prev = {
                "date": p["as_on_date"].isoformat(),
                "cost": _num(p["cost"]),
                "index": _num(p["index"]),
            }
    out["latest"], out["previous"] = latest, prev

    items: list[dict[str, Any]] = []
    if latest and not comps.empty:
        comps["as_on_date"] = pd.to_datetime(comps["as_on_date"]).dt.date
        day = comps[
            (comps["thali"] == "veg_thali") & (comps["as_on_date"].astype(str) == latest["date"])
        ]
        total = float(day["cost"].sum())
        for r in day.sort_values("cost", ascending=False).itertuples():
            label, emoji = LABELS.get(r.ingredient, (r.ingredient, "•"))
            items.append(
                {
                    "ingredient": r.ingredient,
                    "label": label,
                    "emoji": emoji,
                    "qty": _num(r.qty),
                    "unit": r.unit,
                    "source_commodity": r.source_commodity,
                    "price": _num(r.price),
                    "source_unit": r.source_unit,
                    "cost": _num(r.cost),
                    "share": _num(r.cost) / total if total else None,
                    "raw_sha256": r.raw_sha256,
                    "raw_path": r.raw_path,
                }
            )
    out["items"] = items

    nonveg = idx[idx["thali"] == "nonveg_thali"].sort_values("as_on_date")
    out["nonveg"] = (
        None
        if nonveg.empty
        else {
            "status": nonveg.iloc[-1]["status"],
            "reason": str(nonveg.iloc[-1]["excluded_reason"] or nonveg.iloc[-1]["missing_items"]),
        }
    )

    movers, why = top_movers(prices) if not prices.empty else (pd.DataFrame(), "No prices yet.")
    out["movers"] = {
        "reason": why,
        "rows": [
            {
                "commodity": r.commodity,
                "from": _num(r.price_from),
                "to": _num(r.price_to),
                "pct": _num(r.pct_change),
                "date_from": str(r.date_from),
                "date_to": str(r.date_to),
                "days_between": int(r.days_between),
            }
            for r in movers.itertuples()
        ],
    }

    # Coverage grid: basket ingredients x calendar days (retail DoCA series).
    days = [r["date"] for r in out["series"]]
    grid = []
    if not prices.empty:
        retail = prices[prices["price_type"] == "retail"]
        have = {
            (c, d.isoformat())
            for c, d in zip(retail["commodity"], retail["as_on_date"], strict=True)
        }
        for it in items or []:
            grid.append(
                {
                    "label": it["label"],
                    "emoji": it["emoji"],
                    "cells": [(it["source_commodity"], d) in have for d in days],
                }
            )
    out["coverage"] = {"days": days, "rows": grid}

    dq = _csv(root, "index/dq_panel.csv")
    out["geos_without_source"] = (
        []
        if dq.empty
        else [{"geo": r.geo, "note": r.dropped} for r in dq[dq["n_dates"] == 0].itertuples()]
    )

    if not prices.empty:
        lastfetch = prices.sort_values("fetched_at").iloc[-1]
        out["provenance"] = {
            "fetched_at": str(lastfetch["fetched_at"]),
            "raw_sha256": lastfetch["raw_sha256"],
            "n_prices": int((prices["as_on_date"] == prices["as_on_date"].max()).sum()),
        }
    return out
