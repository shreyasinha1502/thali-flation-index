"""DoCA homepage parser + store, tested on the page captured live on 2026-09-29.

Expected values below were read off that real page. The negative tests delete structural
markup from the real page to simulate a layout change. No value is invented.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from conftest import DOCA_HTML, doca_artifact
from thaliflation.ingest.doca_home import DocaParseError, DocaPriceRow, parse_home, store_rows


def _price(rows: list[DocaPriceRow], ptype: str, commodity: str) -> float:
    return next(r.price for r in rows if r.price_type == ptype and r.commodity == commodity)


def test_parses_every_published_price(doca_rows: list[DocaPriceRow]) -> None:
    retail = [r for r in doca_rows if r.price_type == "retail"]
    wholesale = [r for r in doca_rows if r.price_type == "wholesale"]
    assert (len(retail), len(wholesale)) == (41, 23)
    assert {r.as_on_date for r in doca_rows} == {date(2026, 9, 29)}
    assert {r.unit_stated for r in retail} == {"₹/Kg"}
    assert {r.unit_stated for r in wholesale} == {"₹/Qtl."}
    assert {r.commodity_group for r in retail} == {
        "Grains & Pulses",
        "Oils",
        "Vegetables",
        "Others",
        "Additional Commodities",
    }


def test_exact_values_and_commodity_strings(doca_rows: list[DocaPriceRow]) -> None:
    assert _price(doca_rows, "retail", "Rice") == 46.64
    assert _price(doca_rows, "retail", "Tur/Arhar Dal") == 125.95
    assert _price(doca_rows, "retail", "Mustard Oil (Packed)") == 203.14
    assert _price(doca_rows, "retail", "Milk @") == 61.31
    assert _price(doca_rows, "retail", "Eggs") == 83.81
    assert _price(doca_rows, "wholesale", "Tur/Arhar Dal") == 11653.55


def test_provenance_points_at_the_cached_raw(doca_rows: list[DocaPriceRow]) -> None:
    art = doca_artifact()
    for r in doca_rows:
        assert r.source == "doca_home" and r.source_url == "https://fcainfoweb.nic.in/"
        assert r.raw_sha256 == art.sha256 and r.fetched_at == art.fetched_at
        assert r.raw_path == "tests/fixtures/doca_home/home_2026-09-29.html"


@pytest.mark.parametrize(
    ("pattern", "why"),
    [
        (r"All India Average Retail Price\(&#8377/Kg\) As on", "retail header removed"),
        (
            r"<caption>\s*All India Average Retail Price - Grains & Pulses\s*</caption>",
            "no caption",
        ),
        (r"<b>Commodity</b>", "column header changed"),
    ],
)
def test_layout_change_fails_loudly(pattern: str, why: str) -> None:
    html = DOCA_HTML.read_text(encoding="utf-8")
    assert re.search(pattern, html), f"precondition: real page matches {pattern!r}"
    with pytest.raises(DocaParseError):
        parse_home(re.sub(pattern, "", html, count=1), artifact=doca_artifact())


def test_store_writes_once_then_skips_unchanged(
    doca_rows: list[DocaPriceRow], tmp_path: Path
) -> None:
    first = store_rows(doca_rows, root=tmp_path)
    assert [p.name for p in first] == ["as_on=2026-09-29__fetched=20260929T160118Z.csv"]
    assert store_rows(doca_rows, root=tmp_path) == []  # same published values -> no new file
    lines = first[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 + 64
