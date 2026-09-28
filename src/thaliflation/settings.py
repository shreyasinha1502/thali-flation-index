"""Repository paths, environment loading and secret access.

`.env` is parsed with a tiny stdlib loader instead of python-dotenv to keep dependencies lean.
Real environment variables always win over `.env` values (so CI secrets override local files).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_DIR = REPO_ROOT / "logs"
ENV_FILE = REPO_ROOT / ".env"


class MissingSecretError(RuntimeError):
    """Raised when a required secret is absent. Never fall back to a guessed value."""


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Load KEY=VALUE lines from `path` into os.environ without overriding existing vars.

    Returns the pairs that were read from the file (for diagnostics; values are not logged).
    """
    if not path.is_file():
        return {}
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        parsed[key] = value
        os.environ.setdefault(key, value)
    return parsed


def require_secret(name: str) -> str:
    """Return a non-empty secret from the environment (after loading .env) or fail loudly."""
    load_env_file()
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingSecretError(
            f"{name} is not set. Put it in {ENV_FILE.name} (see .env.example) or export it. "
            "Refusing to continue without it."
        )
    from thaliflation.logging_setup import register_secret

    register_secret(value)
    return value
