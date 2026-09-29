"""Coverage / gap reporting. Gaps are counted and shown, never filled.

For each (source, price_type, commodity) series:
    first_date, last_date, observed_days,
    expected_days = calendar days from first_date to the report's as-of date (inclusive),
    missing_days  = expected_days - observed_days,
    pct_missing   = missing_days / expected_days.

Calendar days are the denominator on purpose: the source doesn't document which days DoCA
publishes on, so weekends and holidays show up as gaps and are not silently excused.
The fetch log lists every snapshot run from the raw cache, failures included.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from thaliflation.ingest.doca_home import DOCA_HOME_SOURCE, PROCESSED_SUBDIR
from thaliflation.settings import PROCESSED_DIR, RAW_DIR

REPORTS_DIR = PROCESSED_DIR / "reports"


def load_doca_prices(root: Path = PROCESSED_DIR) -> pd.DataFrame:
    """All stored DoCA snapshots; the latest fetch wins per (as_on_date, price_type, commodity)."""
    files = sorted((root / PROCESSED_SUBDIR).glob("as_on=*__fetched=*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f, encoding="utf-8") for f in files), ignore_index=True)
    df["as_on_date"] = pd.to_datetime(df["as_on_date"]).dt.date
    df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)
    df = df.sort_values("fetched_at")
    return df.drop_duplicates(["as_on_date", "price_type", "commodity"], keep="last").reset_index(
        drop=True
    )


def series_coverage(prices: pd.DataFrame, as_of: date) -> pd.DataFrame:
    cols = [
        "source",
        "price_type",
        "commodity",
        "first_date",
        "last_date",
        "observed_days",
        "expected_days",
        "missing_days",
        "pct_missing",
        "missing_dates",
    ]
    if prices.empty:
        return pd.DataFrame(columns=cols)
    out = []
    for (source, ptype, commodity), g in prices.groupby(["source", "price_type", "commodity"]):
        days = sorted(set(g["as_on_date"]))
        full = pd.date_range(days[0], as_of, freq="D").date
        missing = [d for d in full if d not in set(days)]
        out.append(
            {
                "source": source,
                "price_type": ptype,
                "commodity": commodity,
                "first_date": days[0],
                "last_date": days[-1],
                "observed_days": len(days),
                "expected_days": len(full),
                "missing_days": len(missing),
                "pct_missing": round(100 * len(missing) / len(full), 2),
                "missing_dates": ";".join(d.isoformat() for d in missing),
            }
        )
    return pd.DataFrame(out, columns=cols)


def fetch_log(source: str = DOCA_HOME_SOURCE, raw_root: Path = RAW_DIR) -> pd.DataFrame:
    """One row per fetch attempt recorded in the raw cache (successes and failures)."""
    rows = []
    for meta_path in sorted((raw_root / source).glob("*/*/*.meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "run": meta_path.parent.name,
                "fetched_at": meta.get("fetched_at") or meta.get("recorded_at"),
                "status": meta.get("status"),
                "attempts": len(meta.get("attempts", [])),
                "ok": meta.get("status") == 200,
                "n_bytes": meta.get("n_bytes"),
            }
        )
    return pd.DataFrame(rows, columns=["run", "fetched_at", "status", "attempts", "ok", "n_bytes"])


def write_coverage_report(
    prices: pd.DataFrame,
    as_of: date,
    *,
    out_dir: Path = REPORTS_DIR,
    log: pd.DataFrame | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    cov = series_coverage(prices, as_of)
    cov.to_csv(out_dir / "coverage_series.csv", index=False)
    lines = [
        f"# Coverage report (as of {as_of.isoformat()})",
        "",
        "Gaps are shown, never filled. Denominator = calendar days since each series' first "
        "observation.",
        "",
        "## Sources",
        "",
        "| source | status | rows | series | date range |",
        "|---|---|---|---|---|",
    ]
    if prices.empty:
        lines.append("| doca_home | no data stored | 0 | 0 | - |")
    else:
        lines.append(
            f"| doca_home (DoCA All-India average) | ingesting daily | {len(prices)} "
            f"| {len(cov)} | {min(prices['as_on_date'])} → {max(prices['as_on_date'])} |"
        )
    lines += [
        "| datagov_mandi (source #1) | **blocked**: needs `DATA_GOV_API_KEY` | 0 | 0 | - |",
        "| data.gov.in retail CSVs (source #3) | **blocked**: needs key; history ends 2015 "
        "| 0 | 0 | - |",
        "",
        "## Series coverage",
        "",
        "| price_type | commodity | first | last | observed | expected | missing | % missing |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in cov.sort_values(["price_type", "commodity"]).itertuples():
        lines.append(
            f"| {r.price_type} | {r.commodity} | {r.first_date} | {r.last_date} | "
            f"{r.observed_days} | {r.expected_days} | {r.missing_days} | "
            f"{r.pct_missing} |"
        )
    if log is not None and not log.empty:
        failed = log[~log["ok"]]
        lines += [
            "",
            "## Fetch log (raw cache)",
            "",
            f"{len(log)} fetches recorded, {len(failed)} failed.",
            "",
        ]
        if not failed.empty:
            lines += ["| run | fetched_at | status | attempts |", "|---|---|---|---|"]
            lines += [
                f"| {r.run} | {r.fetched_at} | {r.status} | {r.attempts} |"
                for r in failed.itertuples()
            ]
    path = out_dir / "coverage.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
