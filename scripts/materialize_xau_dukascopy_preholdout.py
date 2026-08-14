#!/usr/bin/env python3
"""Resumable public Dukascopy XAUUSD M5 backfill before the sealed holdout."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fetch_forex_dukascopy import _build_rows_for_pair, _write_rows


DEFAULT_OUT = ROOT / "research_lab/data/xauusd_m5_preholdout_20210101_20250930"
SEALED_START = dt.datetime(2025, 10, 1, tzinfo=dt.UTC)
MIN_FREE_BYTES = 20 * 1024**3


def _parse_day(value: str) -> dt.datetime:
    parsed = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.UTC)
    return parsed


def month_windows(start: dt.datetime, end: dt.datetime):
    cursor = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cursor < end:
        if cursor.month == 12:
            nxt = cursor.replace(year=cursor.year + 1, month=1)
        else:
            nxt = cursor.replace(month=cursor.month + 1)
        left, right = max(start, cursor), min(end, nxt)
        if left < right:
            yield left, right
        cursor = nxt


def day_windows(start: dt.datetime, end: dt.datetime):
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor < end:
        nxt = cursor + dt.timedelta(days=1)
        left, right = max(start, cursor), min(end, nxt)
        if left < right:
            yield left, right
        cursor = nxt


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _load_status(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chunk_bounds(path: Path) -> tuple[int, int, int]:
    count = 0
    first = 0
    last = 0
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ts = int(row["ts"])
            first = first or ts
            last = ts
            count += 1
    return first, last, count


def _valid_chunk(path: Path, left: dt.datetime, right: dt.datetime) -> bool:
    if not path.is_file() or path.stat().st_size <= 32:
        return False
    try:
        first, last, count = _chunk_bounds(path)
    except (OSError, ValueError, KeyError):
        return False
    return count > 0 and first >= int(left.timestamp()) and last < int(right.timestamp())


def _merge(chunks: list[Path], output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    rows = 0
    first_ts = 0
    last_ts = 0
    seen_ts = 0
    with temp.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(["ts", "o", "h", "l", "c", "v"])
        for chunk in chunks:
            with chunk.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
                    ts = int(row["ts"])
                    if ts <= seen_ts:
                        if ts == seen_ts:
                            continue
                        raise RuntimeError(f"out-of-order chunk row: {chunk} ts={ts}")
                    seen_ts = ts
                    first_ts = first_ts or ts
                    last_ts = ts
                    writer.writerow([row[name] for name in ("ts", "o", "h", "l", "c", "v")])
                    rows += 1
    os.replace(temp, output)
    return {
        "rows": rows,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "bytes": output.stat().st_size,
        "sha256": _sha256(output),
    }


def materialize(args: argparse.Namespace) -> int:
    start = _parse_day(args.from_utc)
    end = _parse_day(args.to_utc)
    if end > SEALED_START:
        raise ValueError(f"end {end.isoformat()} crosses sealed holdout start {SEALED_START.isoformat()}")
    if start >= end:
        raise ValueError("from-utc must be earlier than to-utc")
    out = Path(args.out_dir).resolve()
    chunks_dir = out / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    status_path = out / "status.json"
    windows = list(day_windows(start, end))
    known_days = {left.strftime("%Y-%m-%d") for left, _right in windows}
    previous = _load_status(status_path)
    completed: list[str] = []
    empty_market_days: list[str] = sorted({
        str(value) for value in previous.get("empty_market_days", [])
        if str(value) in known_days
    })
    quarantined_days: list[dict] = [
        value for value in previous.get("quarantined_days", [])
        if isinstance(value, dict) and str(value.get("day") or "") in known_days
    ]
    for index, (left, right) in enumerate(windows, start=1):
        free = shutil.disk_usage(out).free
        if free < int(args.min_free_gb * 1024**3):
            _atomic_json(status_path, {
                "state": "storage_guard",
                "free_bytes": free,
                "min_free_bytes": int(args.min_free_gb * 1024**3),
                "completed": completed,
                "empty_market_days": empty_market_days,
                "quarantined_days": quarantined_days,
                "sealed_holdout_rows_decoded": 0,
            })
            return 3
        name = left.strftime("%Y-%m-%d")
        chunk = chunks_dir / f"XAUUSD_M5_{name}.csv"
        if _valid_chunk(chunk, left, right):
            completed.append(name)
            continue
        if left.weekday() >= 5:
            if name not in empty_market_days:
                empty_market_days.append(name)
                empty_market_days.sort()
            _atomic_json(status_path, {
                "state": "collecting_with_quarantine" if quarantined_days else "collecting",
                "progress": f"{index}/{len(windows)}",
                "last_day": name,
                "completed": completed,
                "empty_market_days": empty_market_days,
                "quarantined_days": quarantined_days,
                "authority": "research_only_public_data_no_orders",
                "sealed_holdout_rows_decoded": 0,
            })
            continue
        if name in empty_market_days:
            continue
        previous_quarantine = next((item for item in quarantined_days if item.get("day") == name), None)
        if previous_quarantine and not bool(getattr(args, "retry_quarantined", False)):
            continue
        if previous_quarantine:
            quarantined_days.remove(previous_quarantine)
        _atomic_json(status_path, {
            "state": "collecting",
            "progress": f"{index - 1}/{len(windows)}",
            "current_day": name,
            "completed": completed,
            "empty_market_days": empty_market_days,
            "quarantined_days": quarantined_days,
            "authority": "research_only_public_data_no_orders",
            "sealed_holdout_rows_decoded": 0,
        })
        last_error = ""
        last_stats: dict = {}
        for attempt in range(1, max(1, args.window_attempts) + 1):
            rows, stats, last_error = _build_rows_for_pair(
                pair="XAUUSD",
                start_utc=left,
                end_utc=right,
                timeout_sec=args.timeout_sec,
                sleep_sec=args.sleep_sec,
                retries=args.hour_retries,
                max_hours=0,
            )
            last_stats = dict(stats)
            if rows and stats["hours_fail"] == 0:
                _write_rows(chunk, rows)
                completed.append(name)
                break
            if not rows and stats["hours_fail"] == 0:
                empty_market_days.append(name)
                break
            if attempt < args.window_attempts:
                time.sleep(args.retry_delay_sec)
        else:
            quarantined_days.append({
                "day": name,
                "left_utc": left.isoformat(),
                "right_utc_exclusive": right.isoformat(),
                "last_error": last_error,
                "stats": last_stats,
            })
            _atomic_json(status_path, {
                "state": "collecting_with_quarantine",
                "day": name,
                "last_error": last_error,
                "completed": completed,
                "empty_market_days": empty_market_days,
                "quarantined_days": quarantined_days,
                "sealed_holdout_rows_decoded": 0,
            })
            if len(quarantined_days) > args.max_quarantined_days:
                _atomic_json(status_path, {
                    "state": "quarantine_guard",
                    "completed": completed,
                    "empty_market_days": empty_market_days,
                    "quarantined_days": quarantined_days,
                    "max_quarantined_days": args.max_quarantined_days,
                    "promotion_eligible": False,
                    "sealed_holdout_rows_decoded": 0,
                })
                return 2
        _atomic_json(status_path, {
            "state": "collecting_with_quarantine" if quarantined_days else "collecting",
            "progress": f"{index}/{len(windows)}",
            "completed": completed,
            "empty_market_days": empty_market_days,
            "quarantined_days": quarantined_days,
            "last_day": name,
            "authority": "research_only_public_data_no_orders",
            "sealed_holdout_rows_decoded": 0,
        })

    chunk_paths = [
        chunks_dir / f"XAUUSD_M5_{left.strftime('%Y-%m-%d')}.csv"
        for left, right in windows
        if _valid_chunk(chunks_dir / f"XAUUSD_M5_{left.strftime('%Y-%m-%d')}.csv", left, right)
    ]
    if not chunk_paths:
        _atomic_json(status_path, {
            "state": "no_data",
            "completed": completed,
            "empty_market_days": empty_market_days,
            "quarantined_days": quarantined_days,
            "promotion_eligible": False,
            "sealed_holdout_rows_decoded": 0,
        })
        return 2
    receipt = _merge(chunk_paths, out / "XAUUSD_M5.csv")
    _atomic_json(status_path, {
        "state": "complete_with_quarantine" if quarantined_days else "complete",
        "authority": "research_only_public_data_no_orders",
        "private_api_calls": False,
        "orders_or_risk_mutation": False,
        "start_utc": start.isoformat(),
        "end_utc_exclusive": end.isoformat(),
        "days": len(windows),
        "completed": completed,
        "empty_market_days": empty_market_days,
        "quarantined_days": quarantined_days,
        "promotion_eligible": not quarantined_days,
        "output": receipt,
        "sealed_holdout_rows_decoded": 0,
    })
    return 4 if quarantined_days else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-utc", default="2021-01-01")
    parser.add_argument("--to-utc", default="2025-10-01")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--sleep-sec", type=float, default=0.01)
    parser.add_argument("--timeout-sec", type=float, default=15.0)
    parser.add_argument("--hour-retries", type=int, default=2)
    parser.add_argument(
        "--window-attempts",
        "--month-attempts",
        dest="window_attempts",
        type=int,
        default=4,
        help="Attempts per atomic day (the legacy --month-attempts spelling is retained).",
    )
    parser.add_argument("--max-quarantined-days", type=int, default=31)
    parser.add_argument(
        "--retry-quarantined",
        action="store_true",
        help="Explicitly retry days already quarantined by an earlier resumable run.",
    )
    parser.add_argument("--retry-delay-sec", type=float, default=30.0)
    parser.add_argument("--min-free-gb", type=float, default=20.0)
    args = parser.parse_args()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / "backfill.flock").open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"XAUUSD backfill already running: {out}")
            return 0
        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.write(f"{os.getpid()}\n")
        lock_handle.flush()
        return materialize(args)


if __name__ == "__main__":
    raise SystemExit(main())
