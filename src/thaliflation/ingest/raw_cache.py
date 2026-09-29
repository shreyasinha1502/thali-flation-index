"""Append-only, byte-exact cache of raw source responses.

Layout:  data/raw/<source>/<YYYY-MM-DD>/<run_id>/<name>.<ext>  +  <name>.meta.json

The body is written exactly as received, before any parsing. The sidecar meta records the
redacted request URL, status, response headers, fetch timestamp, retry history and sha256.
Existing files are never overwritten.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from thaliflation.settings import RAW_DIR

_EXT_BY_CONTENT_TYPE = {"application/json": "json", "text/csv": "csv", "text/html": "html"}


@dataclass(frozen=True)
class RawArtifact:
    body_path: Path
    meta_path: Path
    sha256: str
    n_bytes: int
    fetched_at: datetime
    public_url: str
    status: int


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_run_dir(source: str, *, root: Path = RAW_DIR, now: datetime | None = None) -> Path:
    """Create a fresh directory for one ingestion run. Fails if it already exists."""
    now = now or utc_now()
    run_dir = root / source / now.strftime("%Y-%m-%d") / now.strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def ext_for(content_type: str | None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    return _EXT_BY_CONTENT_TYPE.get(base, "bin")


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"raw cache is append-only; refusing to overwrite {path}")
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def write_raw(
    run_dir: Path,
    name: str,
    body: bytes,
    *,
    content_type: str | None,
    fetched_at: datetime,
    public_url: str,
    status: int,
    meta: dict[str, Any],
    compress: bool = False,
) -> RawArtifact:
    """Cache `body` exactly. With compress=True it is stored gzip'd (lossless; sha256 and
    n_bytes always describe the *uncompressed* bytes as received). Used for sources whose raw
    responses are committed to git (M7) so provenance survives ephemeral CI filesystems."""
    suffix = ".gz" if compress else ""
    body_path = run_dir / f"{name}.{ext_for(content_type)}{suffix}"
    meta_path = run_dir / f"{name}.meta.json"
    sha256 = hashlib.sha256(body).hexdigest()
    _write_new(body_path, gzip.compress(body, mtime=0) if compress else body)
    full_meta = {
        "body_file": body_path.name,
        "stored_encoding": "gzip" if compress else "identity",
        "sha256": sha256,
        "n_bytes": len(body),
        "fetched_at": fetched_at.isoformat(),
        "url": public_url,
        "status": status,
        "content_type": content_type,
        **meta,
    }
    _write_new(meta_path, json.dumps(full_meta, indent=2, ensure_ascii=False).encode("utf-8"))
    return RawArtifact(body_path, meta_path, sha256, len(body), fetched_at, public_url, status)


def read_raw(body_path: Path) -> bytes:
    """Return the original bytes of a cached body and verify them against its meta sha256."""
    data = body_path.read_bytes()
    if body_path.suffix == ".gz":
        data = gzip.decompress(data)
    stem = body_path.name.split(".")[0]
    meta = json.loads((body_path.parent / f"{stem}.meta.json").read_text(encoding="utf-8"))
    if hashlib.sha256(data).hexdigest() != meta["sha256"]:
        raise ValueError(f"raw body {body_path} does not match its recorded sha256")
    return data


def write_failure(run_dir: Path, name: str, *, public_url: str, meta: dict[str, Any]) -> Path:
    """Record a fetch that produced no response at all (connection errors on every attempt).

    No body exists, so none is written. The meta file keeps the attempt in the audit trail
    and lets it be counted in coverage/gap reports.
    """
    meta_path = run_dir / f"{name}.meta.json"
    doc = {
        "body_file": None,
        "status": None,
        "url": public_url,
        "recorded_at": utc_now().isoformat(),
        **meta,
    }
    _write_new(meta_path, json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8"))
    return meta_path
