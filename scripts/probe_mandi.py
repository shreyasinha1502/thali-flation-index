"""Liveness probe for source #1 (data.gov.in mandi API).

Fetches ONE page through the real transport, caches it byte-exact under data/raw/, and prints
the response envelope plus the first records verbatim. It does not parse or normalise records.

    python scripts/probe_mandi.py --limit 10
    python scripts/probe_mandi.py --limit 10 --filter "state.keyword=NCT of Delhi"
"""

from __future__ import annotations

import argparse
import json
import sys

from thaliflation.ingest.raw_cache import new_run_dir
from thaliflation.ingest.sources import MANDI_SOURCE, MANDI_URL
from thaliflation.ingest.transport import FetchError, RetryPolicy, fetch
from thaliflation.logging_setup import setup_logging
from thaliflation.settings import LOG_DIR, require_secret


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="adds filters[FIELD]=VALUE; repeatable",
    )
    ap.add_argument("--max-attempts", type=int, default=6)
    ap.add_argument("--show", type=int, default=3, help="records to print verbatim")
    args = ap.parse_args(argv)

    setup_logging(log_file=LOG_DIR / "probe_mandi.jsonl")
    params: dict[str, object] = {
        "api-key": require_secret("DATA_GOV_API_KEY"),
        "format": "json",
        "limit": args.limit,
        "offset": args.offset,
    }
    for f in args.filter:
        field, _, value = f.partition("=")
        params[f"filters[{field}]"] = value

    run_dir = new_run_dir(f"{MANDI_SOURCE}_probe")
    try:
        result = fetch(
            MANDI_URL,
            params,
            source=MANDI_SOURCE,
            run_dir=run_dir,
            name="page_0",
            policy=RetryPolicy(max_attempts=args.max_attempts),
        )
    except FetchError as exc:
        print(f"PROBE FAILED: {exc}", file=sys.stderr)
        if exc.artifact:
            print(f"raw response cached at {exc.artifact.body_path}", file=sys.stderr)
        return 1

    doc = json.loads(result.body)
    print(f"raw cached: {result.artifact.body_path}  sha256={result.artifact.sha256[:16]}...")
    envelope = {k: v for k, v in doc.items() if k != "records"}
    print("envelope:", json.dumps(envelope, indent=1, ensure_ascii=False))
    records = doc.get("records", [])
    print(f"records in page: {len(records)}")
    print(json.dumps(records[: args.show], indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
