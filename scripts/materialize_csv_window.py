#!/usr/bin/env python3
"""Materialize a bounded OHLCV CSV window with a write-once hash receipt."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _boundary(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize(source: Path, output: Path, receipt: Path, start_utc: str, end_utc: str) -> dict:
    start, end = _boundary(start_utc), _boundary(end_utc)
    if start >= end:
        raise ValueError("window must be nonempty")
    if output.exists() or receipt.exists():
        raise FileExistsError("output and receipt are write-once")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    source_rows_before_boundary = 0
    boundary_timestamp_rows_read = 0
    first_ts = last_ts = None
    previous_ts = None
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as target, source.open(encoding="utf-8", newline="") as raw:
        reader = csv.DictReader(raw)
        if not reader.fieldnames or "ts" not in reader.fieldnames:
            raise ValueError("source must have ts column")
        writer = csv.DictWriter(target, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in reader:
            ts = int(float(row["ts"]))
            if previous_ts is not None and ts < previous_ts:
                raise ValueError("source must be sorted by ascending ts")
            previous_ts = ts
            if ts >= end:
                boundary_timestamp_rows_read = 1
                break
            source_rows_before_boundary += 1
            if start <= ts < end:
                writer.writerow(row)
                rows += 1
                first_ts = ts if first_ts is None else first_ts
                last_ts = ts
        target.flush()
        os.fsync(target.fileno())
    if not rows:
        raise ValueError("window produced zero rows")
    payload = {
        "schema_id": "bounded_csv_materialization_v1",
        "source": str(source.resolve()),
        "source_size_bytes": source.stat().st_size,
        "source_mtime_ns": source.stat().st_mtime_ns,
        "output": str(output.resolve()),
        "output_sha256": _sha(output),
        "rows": rows,
        "window": {"start_utc": start_utc, "end_utc_exclusive": end_utc},
        "first_ts": first_ts,
        "last_ts": last_ts,
        "source_rows_before_boundary": source_rows_before_boundary,
        "boundary_timestamp_rows_read": boundary_timestamp_rows_read,
        "outcome_rows_at_or_after_end_used": 0,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--start-utc", required=True)
    parser.add_argument("--end-utc", required=True)
    args = parser.parse_args()
    print(json.dumps(materialize(args.source, args.output, args.receipt, args.start_utc, args.end_utc), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
