"""Analysis helpers (M5 subset needed by the dashboard). Honest about thin history.

- top_movers: % change per commodity between the two latest *available* snapshot dates.
  It reports the real gap in days between them, so a 3-day gap is never presented as a
  1-day move. With fewer than 2 dates it returns an empty frame plus a reason.
- daily_calendar: one row per calendar day from the series start to `as_of`. Days without a
  computable index keep NaN and get a `segment` id, so charts break the line at gaps
  instead of drawing across them.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

MOVER_COLS = [
    "commodity",
    "commodity_group",
    "date_from",
    "date_to",
    "days_between",
    "price_from",
    "price_to",
    "pct_change",
]


def top_movers(
    prices: pd.DataFrame, *, price_type: str = "retail", n: int | None = 10
) -> tuple[pd.DataFrame, str | None]:
    p = prices[prices["price_type"] == price_type]
    dates = sorted(set(p["as_on_date"]))
    if len(dates) < 2:
        return (
            pd.DataFrame(columns=MOVER_COLS),
            f"Needs at least 2 snapshot dates; have {len(dates)}. "
            "History grows by one real day per published DoCA update.",
        )
    d0, d1 = dates[-2], dates[-1]
    a = p[p["as_on_date"] == d0][["commodity", "commodity_group", "price"]]
    b = p[p["as_on_date"] == d1][["commodity", "price"]]
    m = a.merge(b, on="commodity", suffixes=("_from", "_to"))  # inner: both days published
    m["date_from"], m["date_to"] = d0, d1
    m["days_between"] = (d1 - d0).days
    m["pct_change"] = (m["price_to"] / m["price_from"] - 1) * 100
    m = m.reindex(m["pct_change"].abs().sort_values(ascending=False).index)
    return (m[MOVER_COLS].head(n) if n else m[MOVER_COLS]).reset_index(drop=True), None


def daily_calendar(index_rows: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """index_rows: one (geo, thali) slice of thali_index.csv. Returns a full daily calendar."""
    if index_rows.empty:
        return pd.DataFrame(columns=["as_on_date", "index", "cost", "status", "segment"])
    r = index_rows.copy()
    r["as_on_date"] = pd.to_datetime(r["as_on_date"]).dt.date
    start = min(r["as_on_date"])
    cal = pd.DataFrame({"as_on_date": pd.date_range(start, max(as_of, start), freq="D").date})
    out = cal.merge(r[["as_on_date", "index", "cost", "status"]], on="as_on_date", how="left")
    out["status"] = out["status"].fillna("NO SNAPSHOT")
    has = out["index"].notna()
    out["segment"] = (~has).cumsum()  # a new segment starts after every gap day
    return out
