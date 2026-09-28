"""Transport + raw cache tests, replaying responses captured live from api.data.gov.in.

The only things constructed here are *transport events*: the exception types requests raises
on a connect timeout, whose message format is copied from a real failure seen on 2026-09-28.
No price, date, market or record is invented anywhere.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from thaliflation.ingest.raw_cache import new_run_dir, write_raw
from thaliflation.ingest.transport import (
    USER_AGENT,
    FetchError,
    RetryPolicy,
    fetch,
    parse_retry_after,
    public_url,
)

FIXTURES = Path(__file__).parent / "fixtures" / "datagov_gateway"
URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
SECRET = "placeholder-credential-for-tests"  # not a real key, never sent anywhere
PARAMS = {"api-key": SECRET, "format": "json", "limit": 10, "offset": 0}
FAST = RetryPolicy(max_attempts=3, base_delay_s=2.0)


def recorded(case: str) -> requests.Response:
    """Rebuild a requests.Response from a live-captured body + meta, byte for byte."""
    meta_path = next((FIXTURES / case).glob("*.meta.json"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    body = (FIXTURES / case / meta["body_file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == meta["sha256"], "fixture body was modified"
    resp = requests.Response()
    resp.status_code = meta["status"]
    resp.headers = CaseInsensitiveDict(meta["response_headers"])
    resp._content = body
    resp.url = meta["url"]
    return resp


class ReplaySession:
    """Stands in for requests.Session: returns queued real responses or raises queued errors."""

    def __init__(self, *events: requests.Response | Exception):
        self.events = list(events)
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):  # type: ignore[no-untyped-def]
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return new_run_dir("test_source", root=tmp_path)


def _no_secret_anywhere(root: Path) -> None:
    for f in root.rglob("*"):
        if f.is_file():
            assert SECRET not in f.read_text(encoding="utf-8", errors="replace"), f


def test_rate_limit_is_retried_with_backoff_then_cached_and_raised(run_dir: Path) -> None:
    session = ReplaySession(*(recorded("rate_limited_429") for _ in range(3)))
    sleeps: list[float] = []

    with pytest.raises(FetchError) as err:
        fetch(
            URL,
            PARAMS,
            source="t",
            run_dir=run_dir,
            name="p0",
            policy=FAST,
            session=session,
            sleep=sleeps.append,
        )  # type: ignore[arg-type]

    assert len(session.calls) == 3
    assert sleeps == [2.0, 4.0]  # exponential; the live 429 carries no Retry-After
    art = err.value.artifact
    assert art is not None and art.status == 429
    live_body = (FIXTURES / "rate_limited_429" / "with_sample_key.json").read_bytes()
    assert art.body_path.read_bytes() == live_body  # cached byte-exact
    meta = json.loads(art.meta_path.read_text(encoding="utf-8"))
    assert [a["status"] for a in meta["attempts"]] == [429, 429, 429]
    assert "api-key=***" in meta["url"]
    assert all(c["headers"]["User-Agent"] == USER_AGENT for c in session.calls)
    assert SECRET not in str(err.value)
    _no_secret_anywhere(run_dir)


def test_auth_error_is_not_retried(run_dir: Path) -> None:
    session = ReplaySession(recorded("auth_missing_400"))
    sleeps: list[float] = []
    with pytest.raises(FetchError, match=r"(?s)HTTP 400.*Authorization field missing"):
        fetch(
            URL,
            PARAMS,
            source="t",
            run_dir=run_dir,
            name="p0",
            policy=FAST,
            session=session,
            sleep=sleeps.append,
        )  # type: ignore[arg-type]
    assert len(session.calls) == 1 and sleeps == []


def test_connection_errors_exhausted_record_failure_and_never_leak_key(run_dir: Path) -> None:
    # Message format copied from the real ConnectTimeout observed on 2026-09-28.
    msg = (
        f"HTTPSConnectionPool(host='api.data.gov.in', port=443): Max retries exceeded with "
        f"url: /resource/x?api-key={SECRET}&format=json (Caused by ConnectTimeoutError())"
    )
    session = ReplaySession(*(requests.ConnectTimeout(msg) for _ in range(3)))
    sleeps: list[float] = []

    with pytest.raises(FetchError) as err:
        fetch(
            URL,
            PARAMS,
            source="t",
            run_dir=run_dir,
            name="p0",
            policy=FAST,
            session=session,
            sleep=sleeps.append,
        )  # type: ignore[arg-type]

    assert sleeps == [2.0, 4.0]
    assert SECRET not in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__
    failure = json.loads((run_dir / "p0.meta.json").read_text(encoding="utf-8"))
    assert failure["status"] is None and failure["body_file"] is None
    assert [a["error"] for a in failure["attempts"]] == ["ConnectTimeout"] * 3
    _no_secret_anywhere(run_dir)


def test_non_retryable_request_error_is_redacted_and_not_retried(run_dir: Path) -> None:
    session = ReplaySession(requests.exceptions.InvalidURL(f"bad url ?api-key={SECRET}"))
    with pytest.raises(FetchError) as err:
        fetch(
            URL,
            PARAMS,
            source="t",
            run_dir=run_dir,
            name="p0",
            policy=FAST,
            session=session,
            sleep=lambda s: None,
        )  # type: ignore[arg-type]
    assert len(session.calls) == 1
    assert SECRET not in str(err.value) and err.value.__cause__ is None


def test_retry_after_is_honoured_when_longer_than_backoff() -> None:
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("not-a-date") is None
    assert FAST.delay(1, retry_after_s=120.0) == 120.0
    assert FAST.delay(1, retry_after_s=0.5) == 2.0
    assert RetryPolicy(base_delay_s=2, max_delay_s=10).delay(10) == 10  # capped


def test_public_url_redacts_secret_params() -> None:
    shown = public_url(URL, PARAMS, frozenset({"api-key"}))
    assert SECRET not in shown and "api-key=***" in shown


def test_raw_cache_is_append_only(run_dir: Path) -> None:
    body = (FIXTURES / "auth_missing_400" / "without_key.json").read_bytes()
    kw = dict(content_type="application/json", fetched_at=None, public_url=URL, status=400, meta={})
    from thaliflation.ingest.raw_cache import utc_now

    kw["fetched_at"] = utc_now()
    write_raw(run_dir, "same", body, **kw)  # type: ignore[arg-type]
    with pytest.raises(FileExistsError):
        write_raw(run_dir, "same", body, **kw)  # type: ignore[arg-type]
