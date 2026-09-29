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
EVIDENCE_URL = f"{REPO_URL}/blob/main/docs/evidence/README.md"

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
    "egg": ("Eggs", "🥚"),
}
THALIS: dict[str, dict[str, str]] = {
    "veg_thali": {
        "label": "Veg thali",
        "emoji": "🥗",
        "blurb": "rice, 2 rotis, dal, aloo sabzi, tadka, a little milk",
    },
    "nonveg_thali": {
        "label": "Non-veg thali",
        "emoji": "🥚",
        "blurb": "rice, 2 rotis, a smaller dal, 2-egg curry, tadka",
    },
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


def _point(row: pd.Series) -> dict[str, Any]:
    return {
        "date": row["as_on_date"].isoformat(),
        "cost": _num(row["cost"]),
        "index": _num(row["index"]),
    }


def _thali_block(key: str, rows: pd.DataFrame, comps: pd.DataFrame, as_of: date) -> dict[str, Any]:
    rows = rows.sort_values("as_on_date")
    ok = rows[rows["status"] == "OK"]
    cal = daily_calendar(rows, as_of=max(as_of, rows["as_on_date"].max()))
    last = rows.iloc[-1]
    block: dict[str, Any] = {
        "key": key,
        **THALIS.get(key, {"label": key, "emoji": "🍽️", "blurb": ""}),
        "status": last["status"],
        "reason": str(last["excluded_reason"] or last["missing_items"] or ""),
        "n_items": int(last["n_items"]),
        "latest": _point(ok.iloc[-1]) if not ok.empty else None,
        "previous": _point(ok.iloc[-2]) if len(ok) > 1 else None,
        "series": [
            {
                "date": r.as_on_date.isoformat(),
                "index": _num(r.index),
                "cost": _num(r.cost),
                "status": r.status,
            }
            for r in cal.itertuples()
        ],
        "history": {
            "ok_days": len(ok),
            "calendar_days": len(cal),
            "first_date": cal["as_on_date"].min().isoformat(),
        },
        "items": [],
    }
    if block["latest"] and not comps.empty:
        day = comps[
            (comps["thali"] == key) & (comps["as_on_date"].astype(str) == block["latest"]["date"])
        ]
        total = float(day["cost"].sum())
        for r in day.sort_values("cost", ascending=False).itertuples():
            label, emoji = LABELS.get(r.ingredient, (r.ingredient, "•"))
            block["items"].append(
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
                }
            )
    return block


def build_payload(as_of: date, root: Path = PROCESSED_DIR) -> dict[str, Any]:
    idx = _csv(root, "index/thali_index.csv")
    comps = _csv(root, "index/components.csv")
    prices = load_doca_prices(root)
    out: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "repo_url": REPO_URL,
        "source_url": SOURCE_URL,
        "evidence_url": EVIDENCE_URL,
        "ready": not idx.empty,
    }
    if idx.empty:
        return out

    idx["as_on_date"] = pd.to_datetime(idx["as_on_date"]).dt.date
    if not comps.empty:
        comps["as_on_date"] = pd.to_datetime(comps["as_on_date"]).dt.date
    all_india = idx[idx["geo"] == "All India"]
    base = all_india["base_date"].dropna()
    out["base_date"] = str(base.iloc[0]) if not base.empty else None
    order = [k for k in THALIS if k in set(all_india["thali"])]
    order += sorted(set(all_india["thali"]) - set(order))
    out["order"] = order
    out["thalis"] = {
        k: _thali_block(k, all_india[all_india["thali"] == k], comps, as_of) for k in order
    }

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

    # Coverage grid: every basket ingredient (union over thalis) x calendar days.
    days = [s["date"] for s in out["thalis"][order[0]]["series"]] if order else []
    grid: list[dict[str, Any]] = []
    if not prices.empty:
        retail = prices[prices["price_type"] == "retail"]
        have = {
            (c, d.isoformat())
            for c, d in zip(retail["commodity"], retail["as_on_date"], strict=True)
        }
        seen: set[str] = set()
        for k in order:
            for it in out["thalis"][k]["items"]:
                if it["ingredient"] in seen:
                    continue
                seen.add(it["ingredient"])
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
        }
    return out
