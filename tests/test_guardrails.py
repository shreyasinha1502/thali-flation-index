"""Guardrails for the project's non-negotiable: no synthetic data, no leaked secrets.

These are static checks over the repository, so they run without network or data.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from thaliflation.logging_setup import JsonFormatter, redact, register_secret
from thaliflation.settings import CONFIG_DIR, REPO_ROOT

CODE_DIRS = ["src", "tests", "scripts", "app"]

# Patterns that generate or invent values. Gap-filling (interpolate / ffill / bfill) counts:
# a missing price must stay missing.
FORBIDDEN = {
    "random module": re.compile(r"^\s*(import random\b|from random import)", re.M),
    "numpy random": re.compile(r"\bnp\.random\b|\bnumpy\.random\b"),
    "faker": re.compile(r"\bfaker\b", re.I),
    "interpolate": re.compile(r"\.interpolate\("),
    "forward/back fill": re.compile(r"\.(ffill|bfill|pad|backfill)\(|fillna\([^)]*method="),
}


def _code_files() -> list[Path]:
    files: list[Path] = []
    for d in CODE_DIRS:
        root = REPO_ROOT / d
        if root.is_dir():
            files.extend(p for p in root.rglob("*.py") if p.resolve() != Path(__file__).resolve())
    return files


def test_no_synthetic_data_generators_in_code() -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {label}"
        for path in _code_files()
        for label, pattern in FORBIDDEN.items()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "Synthetic-data / gap-filling patterns found:\n" + "\n".join(offenders)


def test_no_random_values_in_frontend_js() -> None:
    offenders = [
        str(f.relative_to(REPO_ROOT))
        for f in (REPO_ROOT / "app").rglob("*.js")
        if re.search(r"Math\.random|crypto\.getRandomValues|faker", f.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"random value generation in frontend code: {offenders}"


def test_allow_synthetic_hard_gate_is_false() -> None:
    cfg = yaml.safe_load((CONFIG_DIR / "index.yaml").read_text(encoding="utf-8"))
    assert cfg["allow_synthetic"] is False


def test_all_configs_are_valid_yaml() -> None:
    for name in ("baskets.yaml", "commodity_map.yaml", "index.yaml"):
        assert yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) is not None


def test_env_file_is_gitignored() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored


def test_registered_secrets_are_redacted_from_logs() -> None:
    import logging

    secret = "unit-test-secret-value-0000"  # a placeholder credential, not a data value
    register_secret(secret)
    record = logging.makeLogRecord(
        {"msg": f"GET https://host/x?api-key={secret}", "url": f"https://h?k={secret}"}
    )
    line = JsonFormatter().format(record)
    assert secret not in line
    assert redact(f"k={secret}") == "k=***REDACTED***"
