"""Thali-flation Index dashboard. Reads only committed files under data/processed/.

    streamlit run app/streamlit_app.py

Real data only. Gaps are drawn as gaps and listed in the always-visible coverage panel.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thaliflation.analysis import daily_calendar, top_movers  # noqa: E402
from thaliflation.coverage import load_doca_prices  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
IST = timezone(timedelta(hours=5, minutes=30))
BLUE, RED, GRAY = "#2a78d6", "#e34948", "#8a8984"  # reference palette: series-1, red, muted
CRITICAL = "#d03b3b"  # status: critical (always shipped with a text label)

st.set_page_config(page_title="Thali-flation Index", page_icon="🍛", layout="wide")


@st.cache_data(ttl=900)
def load() -> dict[str, pd.DataFrame]:
    def csv(rel: str) -> pd.DataFrame:
        p = PROCESSED / rel
        return pd.read_csv(p) if p.is_file() else pd.DataFrame()

    return {
        "index": csv("index/thali_index.csv"),
        "components": csv("index/components.csv"),
        "dq": csv("index/dq_panel.csv"),
        "coverage": csv("reports/coverage_series.csv"),
        "prices": load_doca_prices(PROCESSED),
    }


d = load()
idx, comps, prices = d["index"], d["components"], d["prices"]
today_ist = datetime.now(UTC).astimezone(IST).date()

st.title("🍛 Thali-flation Index")
st.caption(
    "Cost of one home-cooked veg thali, priced from the Department of Consumer Affairs' "
    "published **All-India average retail prices**. Real data only: missing days stay "
    "missing and are listed below."
)

if idx.empty:
    st.error(
        "No index has been built yet. Run `scripts/snapshot_doca.py` then `scripts/build_index.py`."
    )
    st.stop()

idx["as_on_date"] = pd.to_datetime(idx["as_on_date"]).dt.date
veg = idx[(idx["thali"] == "veg_thali") & (idx["geo"] == "All India")].sort_values("as_on_date")
ok = veg[veg["status"] == "OK"]
base_date = str(veg["base_date"].dropna().iloc[0]) if veg["base_date"].notna().any() else "not set"

# ---- headline tiles ---------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
if ok.empty:
    c1.metric("Veg thali cost", "—")
    c2.metric("Index", "—")
else:
    last = ok.iloc[-1]
    prev = ok.iloc[-2] if len(ok) > 1 else None
    c1.metric(
        f"Veg thali cost · {last['as_on_date']:%d %b %Y}",
        f"₹{last['cost']:.2f}",
        delta=None
        if prev is None
        else f"₹{last['cost'] - prev['cost']:+.2f} vs {prev['as_on_date']:%d %b}",
        delta_color="inverse",
    )
    c2.metric(f"Index (base {base_date} = 100)", f"{last['index']:.1f}")
first = veg["as_on_date"].min()
cal_days = (max(today_ist, veg["as_on_date"].max()) - first).days + 1
c3.metric(
    "Days with a real index",
    f"{len(ok)} of {cal_days}",
    help="Calendar days since the first snapshot. Days without a snapshot are gaps.",
)
nonveg = idx[idx["thali"] == "nonveg_thali"]
c4.metric(
    "Non-veg thali",
    "Excluded" if (nonveg["status"] == "EXCLUDED").all() else "Computed",
    help="Egg is published by DoCA, but its unit (dozen or kg) isn't stated anywhere "
    "verifiable, so the non-veg thali isn't computed.",
)

# ---- trend ------------------------------------------------------------------------------
st.subheader("Veg thali index over time")
cal = daily_calendar(veg, as_of=max(today_ist, veg["as_on_date"].max()))
cal["as_on_date"] = pd.to_datetime(cal["as_on_date"])
line_data = cal[cal["index"].notna()]
gaps = cal[cal["index"].isna()]
base = alt.Chart(line_data).encode(
    x=alt.X("as_on_date:T", title=None, axis=alt.Axis(format="%d %b", grid=False)),
    y=alt.Y("index:Q", title="Index", scale=alt.Scale(zero=False), axis=alt.Axis(format=".1f")),
    tooltip=[
        alt.Tooltip("as_on_date:T", title="Date", format="%d %b %Y"),
        alt.Tooltip("index:Q", title="Index", format=".2f"),
        alt.Tooltip("cost:Q", title="Cost (₹)", format=".2f"),
    ],
)
chart = base.mark_line(color=BLUE, strokeWidth=2).encode(detail="segment:N") + base.mark_point(
    color=BLUE, filled=True, size=80
)
if not gaps.empty:
    chart += (
        alt.Chart(gaps)
        .mark_rule(color=CRITICAL, strokeDash=[3, 3], opacity=0.6)
        .encode(
            x="as_on_date:T",
            tooltip=[
                alt.Tooltip("as_on_date:T", title="No index on", format="%d %b %Y"),
                alt.Tooltip("status:N", title="Why"),
            ],
        )
    )
st.altair_chart(chart.properties(height=280), width="stretch")
st.caption(
    f"History starts on the first snapshot ({first:%d %b %Y}); nothing before that is backfilled. "
    f"Dashed red lines = days with no index ({len(gaps)} so far)."
)

# ---- composition + movers ---------------------------------------------------------------
left, right = st.columns(2)
with left:
    st.subheader("What the thali costs, item by item")
    if comps.empty or ok.empty:
        st.info("No complete basket yet.")
    else:
        comps["as_on_date"] = pd.to_datetime(comps["as_on_date"]).dt.date
        latest = comps[
            (comps["thali"] == "veg_thali") & (comps["as_on_date"] == ok.iloc[-1]["as_on_date"])
        ].copy()
        latest["label"] = (
            latest["ingredient"] + " · " + latest["qty"].map("{:g}".format) + latest["unit"]
        )
        bars = (
            alt.Chart(latest)
            .mark_bar(color=BLUE, cornerRadiusEnd=4)
            .encode(
                x=alt.X("cost:Q", title="₹ in one thali"),
                y=alt.Y("label:N", sort="-x", title=None),
                tooltip=[
                    alt.Tooltip("source_commodity:N", title="DoCA commodity"),
                    alt.Tooltip("price:Q", title="Published price (₹)", format=".2f"),
                    alt.Tooltip("source_unit:N", title="Price unit"),
                    alt.Tooltip("cost:Q", title="₹ in thali", format=".3f"),
                ],
            )
        )
        st.altair_chart(bars.properties(height=320), width="stretch")

with right:
    st.subheader("Top movers (retail, all commodities)")
    movers, why = top_movers(prices) if not prices.empty else (pd.DataFrame(), "No prices yet.")
    if why:
        st.info(why)
    else:
        movers["direction"] = movers["pct_change"].map(lambda v: "▲ up" if v > 0 else "▼ down")
        mv = (
            alt.Chart(movers)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("pct_change:Q", title="% change"),
                y=alt.Y(
                    "commodity:N",
                    sort=alt.EncodingSortField("pct_change", op="max", order="descending"),
                    title=None,
                ),
                color=alt.Color(
                    "direction:N",
                    scale=alt.Scale(domain=["▲ up", "▼ down"], range=[RED, BLUE]),
                    title=None,
                ),
                tooltip=[
                    "commodity",
                    "price_from",
                    "price_to",
                    alt.Tooltip("pct_change:Q", format="+.2f"),
                    "days_between",
                ],
            )
        )
        st.altair_chart(mv.properties(height=320), width="stretch")
        r = movers.iloc[0]
        st.caption(
            f"Compares {r['date_from']} with {r['date_to']} "
            f"({r['days_between']} day(s) apart: the two latest published dates)."
        )

# ---- coverage & gaps (always visible) ---------------------------------------------------
st.divider()
st.subheader("⚠️ Coverage & gaps — nothing here is hidden")
st.markdown(
    "- **Veg thali, All India:** priced from DoCA's published All-India average (not a city).\n"
    "- **Non-veg thali: EXCLUDED.** Egg's unit is unverified, and a guessed unit would be "
    "invented data.\n"
    "- **Delhi (configured city): no live source yet.** DoCA's centre-wise reports are behind "
    "a CAPTCHA, and the data.gov.in mandi API needs an API key that hasn't been set up yet.\n"
    "- **No history before the first snapshot.** The data.gov.in retail CSVs end in 2015 and "
    "also need the key."
)
st.markdown("**Data-quality panel** (dropped or excluded days and why)")
st.dataframe(d["dq"], hide_index=True, width="stretch")
cov = d["coverage"]
if not cov.empty:
    basket = set(comps["source_commodity"]) if not comps.empty else set()
    show_all = st.toggle("Show all 64 published series (default: thali ingredients only)")
    view = cov if show_all else cov[(cov["price_type"] == "retail") & cov["commodity"].isin(basket)]
    st.markdown("**Series coverage** (calendar days since first observation; gaps counted)")
    st.dataframe(view, hide_index=True, width="stretch")

with st.expander("Method & sources"):
    st.markdown(
        "`cost = Σ qty × published price × unit factor` (g↔kg, ml↔litre), per "
        "`config/baskets.yaml` and `config/commodity_map.yaml`. "
        f"`index = cost / cost(base {base_date}) × 100`. If any ingredient is missing, "
        "that day's thali is MISSING. There's no partial sum or substitute.\n\n"
        "Source: Department of Consumer Affairs, Price Monitoring Division, "
        "[fcainfoweb.nic.in](https://fcainfoweb.nic.in/), captured daily. Every stored price "
        "carries its fetch time and the sha256 of the raw HTML it came from."
    )
    if not prices.empty:
        st.caption(f"Latest fetch: {prices['fetched_at'].max():%Y-%m-%d %H:%M} UTC")
