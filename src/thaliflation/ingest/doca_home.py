"""Source #2 (public part): DoCA Price Monitoring homepage, https://fcainfoweb.nic.in/

What it is (verified live 2026-09-29, see docs/sources.md):
- The homepage publishes "All India Average Retail Price(₹/Kg) As on DD/MM/YYYY" for 41
  commodities (22 core + additional) and "All India Average Wholesale Price(₹/Qtl.)" for 23.
- It shows ONE as-on date only. History exists only if we snapshot it daily.
- It is the All-India average published by DoCA, not a city series.
- DoCA's date-wise *reports* sit behind a CAPTCHA, so they are not automated here.

Parsing is strict. If the page layout changes (missing headers, unexpected columns), it raises
DocaParseError instead of guessing. A blank or non-numeric price is logged and skipped (it
stays missing), never replaced with zero.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from thaliflation.ingest.raw_cache import RawArtifact
from thaliflation.logging_setup import get_logger
from thaliflation.settings import PROCESSED_DIR, REPO_ROOT

log = get_logger(__name__)

DOCA_HOME_URL = "https://fcainfoweb.nic.in/"
DOCA_HOME_SOURCE = "doca_home"
PROCESSED_SUBDIR = "doca_all_india"

_HEADER_RE = re.compile(
    r"All India Average (Retail|Wholesale) Price\s*\(([^)]*)\)\s*As on\s*(\d{2}/\d{2}/\d{4})"
)
_GROUP_RE = re.compile(r"All India Average (Retail|Wholesale) Price - (.+)$")
_PRICE_RE = re.compile(r"^\d+(?:\.\d+)?$")


class DocaParseError(ValueError):
    """The page no longer has the structure this parser was built against."""


class DocaPriceRow(BaseModel):
    """One published All-India average price, with provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_on_date: date
    geo: Literal["All India"] = "All India"
    statistic: Literal["average"] = "average"
    price_type: Literal["retail", "wholesale"]
    commodity_group: str = Field(min_length=1)
    commodity: str = Field(min_length=1)  # exact string as published
    price: float = Field(gt=0)
    unit_stated: str = Field(min_length=1)  # unit text from the section header, verbatim
    source: str
    source_url: str
    fetched_at: datetime
    raw_path: str  # repo-relative path of the cached raw HTML
    raw_sha256: str


FIELDS = list(DocaPriceRow.model_fields)


@dataclass
class _Table:
    table_id: str
    caption: str
    rows: list[list[str]]


class _Flattener(HTMLParser):
    """Flatten HTML into an ordered list of ('text', str) and ('table', _Table) items.

    On the live page each price table carries its section name in <caption>
    ("All India Average Retail Price - Grains & Pulses") and an id like GridViewRetailGroupA.
    The unit and as-on date sit in an <h2> outside the tables.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, object]] = []
        self._table_depth = 0
        self._table: _Table | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._caption: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table = _Table(dict(attrs).get("id") or "", "", [])
        elif self._table_depth == 1 and tag == "caption":
            self._caption = []
        elif self._table_depth and tag == "tr":
            self._row = []
        elif self._table_depth and tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "caption" and self._caption is not None and self._table is not None:
            self._table.caption = " ".join("".join(self._caption).split())
            self._caption = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._table is not None:
                self.items.append(("table", self._table))
                self._table = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._caption is not None:
            self._caption.append(data)
        elif not self._table_depth:
            text = " ".join(data.split())
            if text:
                self.items.append(("text", text))


@dataclass(frozen=True)
class SkippedValue:
    price_type: str
    commodity: str
    raw_value: str


def parse_home(
    html: str, *, artifact: RawArtifact, source_url: str = DOCA_HOME_URL
) -> tuple[list[DocaPriceRow], list[SkippedValue]]:
    """Parse the homepage price tables. Returns (validated rows, skipped non-numeric values)."""
    flat = _Flattener()
    flat.feed(html)
    flat.close()

    raw_rel = artifact.body_path.resolve().relative_to(REPO_ROOT).as_posix()
    headers: dict[str, tuple[str, date]] = {}  # price_type -> (unit_stated, as_on_date)
    text_since_table: list[str] = []
    rows: list[DocaPriceRow] = []
    skipped: list[SkippedValue] = []

    for kind, payload in flat.items:
        if kind == "text":
            text_since_table.append(payload)  # type: ignore[arg-type]
            joined = " ".join(text_since_table)
            for m in _HEADER_RE.finditer(joined):
                ptype = m.group(1).lower()
                headers[ptype] = (
                    m.group(2).strip(),
                    datetime.strptime(m.group(3), "%d/%m/%Y").date(),
                )
            continue

        table: _Table = payload  # type: ignore[assignment]
        text_since_table = []
        group_match = _GROUP_RE.search(table.caption)
        if group_match is None:
            if "GridView" in table.table_id:
                raise DocaParseError(
                    f"price table {table.table_id} has no recognisable caption: {table.caption!r}"
                )
            continue  # a layout table, not a price table
        ptype, group = group_match.group(1).lower(), group_match.group(2).strip()
        if ptype not in headers:
            raise DocaParseError(f"{ptype} section '{group}' found before its unit/as-on header")
        if not table.rows or table.rows[0] != ["Commodity", "Prices"]:
            raise DocaParseError(f"unexpected header row in {ptype}/{group}: {table.rows[:1]}")
        unit, as_on = headers[ptype]
        for cells in table.rows[1:]:
            if len(cells) != 2:
                raise DocaParseError(f"expected 2 cells in {ptype}/{group}, got {cells}")
            commodity, value = cells
            if not _PRICE_RE.match(value):
                skipped.append(SkippedValue(ptype, commodity, value))
                log.warning(
                    "doca_value_skipped",
                    extra={"price_type": ptype, "commodity": commodity, "raw_value": value},
                )
                continue
            rows.append(
                DocaPriceRow(
                    as_on_date=as_on,
                    price_type=ptype,
                    commodity_group=group,  # type: ignore[arg-type]
                    commodity=commodity,
                    price=float(value),
                    unit_stated=unit,
                    source=DOCA_HOME_SOURCE,
                    source_url=source_url,
                    fetched_at=artifact.fetched_at,
                    raw_path=raw_rel,
                    raw_sha256=artifact.sha256,
                )
            )

    for ptype in ("retail", "wholesale"):
        if ptype not in headers:
            raise DocaParseError(f"no '{ptype}' header (unit + as-on date) found on the page")
    if not any(r.price_type == "retail" for r in rows):
        raise DocaParseError("no retail price rows parsed")
    dupes = {(r.price_type, r.commodity) for r in rows}
    if len(dupes) != len(rows):
        raise DocaParseError("duplicate (price_type, commodity) rows on one page")
    return rows, skipped


def _content_key(rows: list[dict[str, str]] | list[DocaPriceRow]) -> str:
    """Hash of the published values only (ignores fetch metadata), to detect unchanged pages."""
    items = sorted(
        (
            str(r["as_on_date"] if isinstance(r, dict) else r.as_on_date),
            r["price_type"] if isinstance(r, dict) else r.price_type,
            r["commodity"] if isinstance(r, dict) else r.commodity,
            f"{float(r['price'] if isinstance(r, dict) else r.price):.4f}",
        )
        for r in rows
    )
    return hashlib.sha256(repr(items).encode()).hexdigest()


def store_rows(rows: list[DocaPriceRow], *, root: Path = PROCESSED_DIR) -> list[Path]:
    """Write one CSV per (as_on_date) snapshot. Skip it if an identical one already exists.

    Filenames: <root>/doca_all_india/as_on=<date>__fetched=<UTC ts>.csv. A changed page for an
    as-on date that's already stored (a DoCA revision) is kept as a new file. Readers take the
    latest fetch.
    """
    out_dir = root / PROCESSED_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for as_on in sorted({r.as_on_date for r in rows}):
        batch = [r for r in rows if r.as_on_date == as_on]
        key = _content_key(batch)
        existing = sorted(out_dir.glob(f"as_on={as_on.isoformat()}__fetched=*.csv"))
        if existing:
            with existing[-1].open(encoding="utf-8", newline="") as fh:
                if _content_key(list(csv.DictReader(fh))) == key:
                    log.info(
                        "doca_snapshot_unchanged",
                        extra={"as_on_date": as_on.isoformat(), "existing": existing[-1].name},
                    )
                    continue
        stamp = batch[0].fetched_at.strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"as_on={as_on.isoformat()}__fetched={stamp}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            for r in batch:
                writer.writerow(r.model_dump(mode="json"))
        log.info(
            "doca_snapshot_written",
            extra={"as_on_date": as_on.isoformat(), "rows": len(batch), "path": str(path)},
        )
        written.append(path)
    return written
