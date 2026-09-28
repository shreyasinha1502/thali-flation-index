"""Structured (JSON-lines) logging with secret redaction.

Usage:
    log = get_logger(__name__)
    log.info("page_fetched", extra={"offset": 0, "n_records": 10})

Every record becomes one JSON object: ts, level, logger, event + any `extra` fields.
Any value registered via `register_secret` is scrubbed from the rendered line.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_SECRETS: set[str] = set()
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
_CONFIGURED = False


def register_secret(value: str) -> None:
    """Mark a string (e.g. an API key) for redaction from all log output."""
    if value and len(value) >= 6:
        _SECRETS.add(value)


def redact(text: str) -> str:
    for secret in _SECRETS:
        text = text.replace(secret, "***REDACTED***")
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str, ensure_ascii=False))


def setup_logging(level: str | None = None, log_file: Path | None = None) -> None:
    """Configure the root logger once: JSON to stderr, and optionally to a JSONL file."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = (level or os.environ.get("THALI_LOG_LEVEL") or "INFO").upper()
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    root = logging.getLogger()
    root.setLevel(level)
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    # urllib3 debug lines would print full request URLs (including api-key query params).
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
