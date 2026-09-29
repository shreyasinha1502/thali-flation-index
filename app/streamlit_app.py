"""Thali-flation Index dashboard. Reads only committed files under data/processed/.

    streamlit run app/streamlit_app.py

A custom frontend (app/frontend/*) is mounted with st.components.v2. It renders only the JSON
payload built from real pipeline outputs. Gaps are drawn as gaps, and the native tables below
give a screen-reader / download-friendly view of the same data.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import thaliflation.analysis  # noqa: E402
import thaliflation.coverage  # noqa: E402
import thaliflation.dashboard_data  # noqa: E402
import thaliflation.ingest.doca_home  # noqa: E402
import thaliflation.settings  # noqa: E402

# Streamlit Cloud pulls new commits without restarting the process, and it only reloads
# modules inside app/. So hash the package source and, whenever this process hasn't yet
# loaded that exact version (including the first run after a deploy), reload the modules the
# app uses in dependency order. The hash is also part of the payload cache key, so a stale
# payload shape can never be served.
CODE_VERSION = hashlib.sha1(
    b"".join(p.read_bytes() for p in sorted((ROOT / "src" / "thaliflation").rglob("*.py")))
).hexdigest()[:12]
_RELOAD_ORDER = (
    thaliflation.settings,
    thaliflation.ingest.doca_home,
    thaliflation.analysis,
    thaliflation.coverage,
    thaliflation.dashboard_data,
)


@st.cache_resource
def _loaded() -> dict[str, str | None]:
    return {"version": None}


if _loaded()["version"] != CODE_VERSION:
    for mod in _RELOAD_ORDER:
        importlib.reload(mod)
    _loaded()["version"] = CODE_VERSION

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
def payload(as_of_iso: str, code_version: str) -> dict:
    as_of = datetime.fromisoformat(as_of_iso).date()
    return thaliflation.dashboard_data.build_payload(as_of, PROCESSED)


today_ist = datetime.now(UTC).astimezone(IST).date()
# ?thali=nonveg (or veg) preselects a thali, so links can be shared.
initial = {"veg": "veg_thali", "nonveg": "nonveg_thali"}.get(
    str(st.query_params.get("thali", "veg")).lower(), "veg_thali"
)
dashboard(data={**payload(today_ist.isoformat(), CODE_VERSION), "initial": initial}, key="dash")

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
