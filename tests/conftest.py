"""Shared fixtures. Everything here loads REAL captured data; nothing is generated."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from thaliflation.ingest.doca_home import DocaPriceRow, parse_home
from thaliflation.ingest.raw_cache import RawArtifact

FIXTURES = Path(__file__).parent / "fixtures"
DOCA_HTML = FIXTURES / "doca_home" / "home_2026-09-29.html"
DOCA_META = FIXTURES / "doca_home" / "home_2026-09-29.meta.json"


def doca_artifact() -> RawArtifact:
    """RawArtifact for the live-captured DoCA page, after checking it is unmodified."""
    meta = json.loads(DOCA_META.read_text(encoding="utf-8"))
    body = DOCA_HTML.read_bytes()
    assert hashlib.sha256(body).hexdigest() == meta["sha256"], "DoCA fixture was modified"
    return RawArtifact(
        body_path=DOCA_HTML,
        meta_path=DOCA_META,
        sha256=meta["sha256"],
        n_bytes=len(body),
        fetched_at=datetime.fromisoformat(meta["fetched_at"]),
        public_url=meta["url"],
        status=meta["status"],
    )


@pytest.fixture(scope="session")
def doca_rows() -> list[DocaPriceRow]:
    rows, skipped = parse_home(DOCA_HTML.read_text(encoding="utf-8"), artifact=doca_artifact())
    assert skipped == []
    return rows
