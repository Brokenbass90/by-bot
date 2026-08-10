#!/usr/bin/env python3
"""Check cached market-data coverage before bounded research runs.

This is intentionally independent from a specific strategy. Long runners should
fail fast here instead of spending hours before a missing/partial cache slice
turns into a misleading strategy result.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


ROOT = Path(__file__).resolve().parents[1]


def _parse_end(raw: str) -> int:
    dt = datetime.strptime(raw.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _csv_values(raw: str) -> List[str]:
    return [x.strip().upper() for x in str(raw or "").split(",") if x.strip()]


def _norm_ts_ms(raw: object) -> int:
    try:
        val = int(float(raw))
    except Exception:
        return 0
    if val <= 0:
        return 0
    return val * 1000 if val < 10_000_000_000 else val


def _json_row_ts_ms(row: object) -> int:
    if isinstance(row, dict):
        return _norm_ts_ms(row.get("ts") or row.get("timestamp") or row.get("startTime"))
    if isinstance(row, (list, tuple)) and row:
        return _norm_ts_ms(row[0])
    return 0


def _crypto_ts(cache_dir: Path, symbol: str, interval_min: int) -> List[int]:
    interval = "1" if int(interval_min) == 1 else "5"
    stamps: set[int] = set()
    for path in cache_dir.glob(f"{symbol}_{interval}_*.json"):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            ts = _json_row_ts_ms(row)
            if ts > 0:
                stamps.add(ts)
    return sorted(stamps)


def _forex_ts(cache_dir: Path, symbol: str) -> List[int]:
    path = cache_dir / f"{symbol}_M5.csv"
    if not path.exists():
        return []
    stamps: set[int] = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = _norm_ts_ms(row.get("ts"))
            if ts > 0:
                stamps.add(ts)
    return sorted(stamps)


def _max_gap_bars(stamps: List[int], interval_ms: int) -> int:
    if len(stamps) < 2:
        return 0
    max_gap_ms = max(max(0, cur - prev - interval_ms) for prev, cur in zip(stamps, stamps[1:]))
    return int(math.ceil(max_gap_ms / interval_ms)) if max_gap_ms else 0


def _filter_window(stamps: Iterable[int], start_ms: int, end_ms: int) -> List[int]:
    return [ts for ts in stamps if start_ms <= ts < end_ms]


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight cached data coverage.")
    ap.add_argument("--asset-class", choices=("crypto", "forex"), required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--days", type=int, required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--interval-min", type=int, default=5)
    ap.add_argument("--min-coverage", type=float, default=0.95)
    ap.add_argument("--max-gap-bars", type=int, default=1000000)
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if any symbol fails.")
    ap.add_argument("--out", default="", help="Optional CSV output path.")
    args = ap.parse_args()

    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    symbols = _csv_values(args.symbols)
    end_ts = _parse_end(args.end)
    start_ts = end_ts - int(args.days) * 86400
    start_ms = start_ts * 1000
    end_ms = end_ts * 1000
    interval_ms = int(args.interval_min) * 60_000
    expected = max(1, (end_ms - start_ms) // interval_ms)

    rows = []
    for symbol in symbols:
        if args.asset_class == "crypto":
            all_ts = _crypto_ts(cache_dir, symbol, int(args.interval_min))
        else:
            all_ts = _forex_ts(cache_dir, symbol)
        win_ts = _filter_window(all_ts, start_ms, end_ms)
        coverage = len(win_ts) / expected
        max_gap = _max_gap_bars(win_ts, interval_ms)
        passed = coverage >= float(args.min_coverage) and max_gap <= int(args.max_gap_bars)
        rows.append(
            {
                "symbol": symbol,
                "passed": passed,
                "coverage": round(coverage, 6),
                "rows": len(win_ts),
                "expected_rows": expected,
                "max_gap_bars": max_gap,
                "first_ts": win_ts[0] if win_ts else "",
                "last_ts": win_ts[-1] if win_ts else "",
            }
        )

    fields = ["symbol", "passed", "coverage", "rows", "expected_rows", "max_gap_bars", "first_ts", "last_ts"]
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    print("symbol,passed,coverage,rows,expected_rows,max_gap_bars")
    for row in rows:
        print(
            f"{row['symbol']},{int(bool(row['passed']))},{row['coverage']},"
            f"{row['rows']},{row['expected_rows']},{row['max_gap_bars']}"
        )

    failed = [r for r in rows if not r["passed"]]
    if failed:
        print("failed_symbols=" + ",".join(str(r["symbol"]) for r in failed), file=sys.stderr)
        return 2 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
