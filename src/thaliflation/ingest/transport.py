"""Source-agnostic HTTP GET with retry/backoff and raw caching.

Designed against observed data.gov.in gateway behaviour (docs/decisions.md D6):
429 with a JSON body and *no* Retry-After header, and intermittent TCP connect timeouts.

- Retries: HTTP 429/500/502/503/504 and connection/timeout errors, with deterministic
  exponential backoff (Retry-After honoured if the server ever sends it).
- The final response, success or failure, is cached byte-exact before anything parses it.
- Secret query params (e.g. `api-key`) are redacted from URLs, logs and cache metadata.
  The gateway rejects the key as a header (tested: `api-key`, `Authorization`, `X-API-KEY`
  all return 400), so it must travel in the query string. That's why no `requests` exception
  may escape unredacted: its message embeds the full URL.
- A non-200 final response raises FetchError. It is never converted into empty data.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from thaliflation import __version__
from thaliflation.ingest.raw_cache import RawArtifact, utc_now, write_failure, write_raw
from thaliflation.logging_setup import get_logger, redact, register_secret

log = get_logger(__name__)

# The data.gov.in gateway tarpits the default `python-requests/x.y` User-Agent (60 s read
# timeouts / empty 502s, reproduced with curl -A too), so identify ourselves honestly.
USER_AGENT = f"thaliflation/{__version__} (food-price research)"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
RETRYABLE_EXC = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
)
DEFAULT_SECRET_PARAMS = frozenset({"api-key"})
_SNIPPET = 200


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 6
    base_delay_s: float = 2.0
    max_delay_s: float = 120.0
    connect_timeout_s: float = 20.0
    read_timeout_s: float = 90.0

    def delay(self, attempt: int, retry_after_s: float | None = None) -> float:
        backoff = min(self.max_delay_s, self.base_delay_s * 2 ** (attempt - 1))
        return backoff if retry_after_s is None else max(backoff, retry_after_s)


@dataclass(frozen=True)
class FetchResult:
    status: int
    body: bytes
    artifact: RawArtifact


class FetchError(RuntimeError):
    def __init__(self, message: str, *, artifact: RawArtifact | None = None):
        super().__init__(message)
        self.artifact = artifact


def public_url(url: str, params: Mapping[str, Any], secret_params: frozenset[str]) -> str:
    shown = {k: ("***" if k in secret_params else v) for k, v in params.items()}
    return f"{url}?{urlencode(shown, safe='*')}" if shown else url


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


def fetch(
    url: str,
    params: Mapping[str, Any],
    *,
    source: str,
    run_dir: Path,
    name: str,
    secret_params: frozenset[str] = DEFAULT_SECRET_PARAMS,
    policy: RetryPolicy = RetryPolicy(),  # noqa: B008 - frozen, immutable default
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """GET `url` with retries; cache the final response under `run_dir/name.*`."""
    for key in secret_params & params.keys():
        register_secret(str(params[key]))
    shown_url = public_url(url, params, secret_params)
    session = session or requests.Session()
    history: list[dict[str, Any]] = []
    # NB: `extra` keys must not collide with LogRecord attributes (e.g. "name").
    ctx = {"source": source, "url": shown_url, "artifact": name}

    for attempt in range(1, policy.max_attempts + 1):
        last = attempt == policy.max_attempts
        try:
            resp = session.get(
                url,
                params=dict(params),
                headers={"User-Agent": USER_AGENT},
                timeout=(policy.connect_timeout_s, policy.read_timeout_s),
            )
        except requests.RequestException as exc:
            # str(exc) embeds the full URL incl. the api-key -> redact, and never chain it.
            if not isinstance(exc, RETRYABLE_EXC):
                raise FetchError(
                    f"{source}: {type(exc).__name__} for {shown_url}: {redact(str(exc))[:_SNIPPET]}"
                ) from None
            history.append({"attempt": attempt, "error": type(exc).__name__})
            wait = 0.0 if last else policy.delay(attempt)
            log.warning(
                "fetch_connection_error",
                extra={
                    **ctx,
                    "attempt": attempt,
                    "error": redact(str(exc))[:_SNIPPET],
                    "wait_s": wait,
                },
            )
            if last:
                failure = write_failure(
                    run_dir,
                    name,
                    public_url=shown_url,
                    meta={"source": source, "attempts": history},
                )
                raise FetchError(
                    f"{source}: {type(exc).__name__} on all {attempt} attempts for {shown_url} "
                    f"(failure recorded at {failure})"
                ) from None
            sleep(wait)
            continue

        fetched_at = utc_now()
        snippet = redact(resp.content[:_SNIPPET].decode("utf-8", "replace"))
        history.append(
            {"attempt": attempt, "status": resp.status_code, "at": fetched_at.isoformat()}
        )
        if resp.status_code in RETRYABLE_STATUS and not last:
            wait = policy.delay(attempt, parse_retry_after(resp.headers.get("Retry-After")))
            history[-1]["wait_s"] = wait
            log.warning(
                "fetch_retryable_status",
                extra={
                    **ctx,
                    "attempt": attempt,
                    "status": resp.status_code,
                    "body_snippet": snippet,
                    "wait_s": wait,
                },
            )
            sleep(wait)
            continue

        artifact = write_raw(
            run_dir,
            name,
            resp.content,
            content_type=resp.headers.get("Content-Type"),
            fetched_at=fetched_at,
            public_url=shown_url,
            status=resp.status_code,
            meta={
                "source": source,
                "user_agent": USER_AGENT,
                "attempts": history,
                "response_headers": dict(resp.headers),
            },
        )
        if resp.status_code != 200:
            log.error(
                "fetch_failed",
                extra={
                    **ctx,
                    "status": resp.status_code,
                    "attempts": attempt,
                    "body_snippet": snippet,
                    "raw": str(artifact.body_path),
                },
            )
            raise FetchError(
                f"{source}: HTTP {resp.status_code} after {attempt} attempt(s) for {shown_url}: "
                f"{snippet}",
                artifact=artifact,
            )
        log.info(
            "fetch_ok",
            extra={
                **ctx,
                "attempts": attempt,
                "n_bytes": artifact.n_bytes,
                "sha256": artifact.sha256,
                "raw": str(artifact.body_path),
            },
        )
        return FetchResult(resp.status_code, resp.content, artifact)

    raise AssertionError("unreachable")  # loop always returns or raises
