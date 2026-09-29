"""Thali-flation Index dashboard. Reads only committed files under data/processed/.

    streamlit run app/streamlit_app.py

A custom frontend (app/frontend/*) is mounted with st.components.v2. It renders only the JSON
payload built from real pipeline outputs. Gaps are drawn as gaps, and the native tables below
give a screen-reader / download-friendly view of the same data.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thaliflation.dashboard_data import build_payload  # noqa: E402

FRONTEND = Path(__file__).parent / "frontend"
PROCESSED = ROOT / "data" / "processed"
IST = timezone(timedelta(hours=5, minutes=30))

st.set_page_config(
    page_title="Thali-flation Index",
    page_icon="🍛",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.html(FRONTEND / "page.css")  # page chrome + fonts (style-only -> no layout space)

dashboard = st.components.v2.component(
    "thaliflation_dashboard",
    html="",
    css=(FRONTEND / "dashboard.css").read_text(encoding="utf-8"),
    js=(FRONTEND / "dashboard.js").read_text(encoding="utf-8"),
)


@st.cache_data(ttl=900)
def payload(as_of_iso: str) -> dict:
    return build_payload(datetime.fromisoformat(as_of_iso).date(), PROCESSED)


today_ist = datetime.now(UTC).astimezone(IST).date()
# ?thali=nonveg (or veg) preselects a thali, so links can be shared.
initial = {"veg": "veg_thali", "nonveg": "nonveg_thali"}.get(
    str(st.query_params.get("thali", "veg")).lower(), "veg_thali"
)
dashboard(data={**payload(today_ist.isoformat()), "initial": initial}, key="dash")

with st.expander("📋 Data tables (same data as above, for screen readers and download)"):
    for title, rel in [
        ("Thali cost & index", "index/thali_index.csv"),
        ("Ingredient components (with provenance)", "index/components.csv"),
        ("Data-quality panel", "index/dq_panel.csv"),
        ("Series coverage", "reports/coverage_series.csv"),
    ]:
        p = PROCESSED / rel
        if p.is_file():
            st.markdown(f"**{title}** · `data/processed/{rel}`")
            st.dataframe(pd.read_csv(p), hide_index=True, width="stretch")
