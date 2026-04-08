#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.chart_geometry import analyze_geometry  # noqa: E402


DATA_CACHE_DIR = ROOT / "data_cache"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _load_cache_rows(symbol: str, interval: str) -> List[List[float]]:
    paths = sorted(DATA_CACHE_DIR.glob(f"{symbol}_{interval}_*.json"), reverse=True)
    merged: List[List[float]] = []
    seen_ts: set[int] = set()
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in reversed(raw):
            try:
                ts = int(item["ts"])
                if ts in seen_ts:
                    continue
                seen_ts.add(ts)
                merged.append(
                    [
                        ts,
                        _safe_float(item["o"]),
                        _safe_float(item["h"]),
                        _safe_float(item["l"]),
                        _safe_float(item["c"]),
                        _safe_float(item["v"]),
                    ]
                )
            except Exception:
                continue
    merged.sort(key=lambda row: row[0])
    return merged


def _aggregate_rows(rows: List[List[float]], target_min: int) -> List[List[float]]:
    if not rows:
        return []
    bucket_ms = int(target_min) * 60 * 1000
    buckets: Dict[int, List[float]] = {}
    order: List[int] = []
    for row in rows:
        bucket_ts = int(row[0] // bucket_ms) * bucket_ms
        slot = buckets.get(bucket_ts)
        if slot is None:
            slot = [bucket_ts, row[1], row[2], row[3], row[4], row[5]]
            buckets[bucket_ts] = slot
            order.append(bucket_ts)
        else:
            slot[2] = max(slot[2], row[2])
            slot[3] = min(slot[3], row[3])
            slot[4] = row[4]
            slot[5] += row[5]
    return [buckets[ts] for ts in sorted(order)]


def _load_rows(symbol: str, interval: str) -> List[List[float]]:
    direct = _load_cache_rows(symbol, interval)
    if direct:
        return direct
    if interval == "60":
        rows_5 = _load_cache_rows(symbol, "5")
        if rows_5:
            return _aggregate_rows(rows_5, 60)
    if interval == "240":
        rows_60 = _load_cache_rows(symbol, "60")
        if rows_60:
            return _aggregate_rows(rows_60, 240)
        rows_5 = _load_cache_rows(symbol, "5")
        if rows_5:
            return _aggregate_rows(rows_5, 240)
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Build deterministic geometry snapshot from cached OHLCV.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--interval", default="60", help="Cache interval: 5, 60, 240.")
    ap.add_argument("--bars", type=int, default=240)
    ap.add_argument("--json", action="store_true", help="Print JSON only.")
    args = ap.parse_args()

    symbol = str(args.symbol).strip().upper()
    interval = str(args.interval).strip()
    rows = _load_rows(symbol, interval)
    if not rows:
        raise SystemExit(f"No cached rows for {symbol} interval={interval}")
    rows = rows[-max(20, int(args.bars)) :]
    snapshot = analyze_geometry(rows)
    if args.json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=True))
        return 0

    print(f"symbol={symbol}")
    print(f"interval={interval}")
    print(f"rows={snapshot.get('rows')}")
    print(f"current_price={snapshot.get('current_price'):.6f}")
    print(f"atr={snapshot.get('atr'):.6f}")
    channel = dict(snapshot.get("channel") or {})
    compression = dict(snapshot.get("compression") or {})
    if channel:
        print(
            "channel="
            f"r2={channel.get('r2', 0.0):.3f} "
            f"width_pct={channel.get('width_pct', 0.0):.2f} "
            f"pos={channel.get('position', 0.0):.2f} "
            f"slope_pct_per_bar={channel.get('slope_pct_per_bar', 0.0):+.4f}"
        )
    if compression:
        print(
            "compression="
            f"ratio={compression.get('compression_ratio', 0.0):.3f} "
            f"is_compressed={int(bool(compression.get('is_compressed')))}"
        )
    nearest = dict(snapshot.get("nearest_levels") or {})
    print("nearest_below=" + json.dumps(nearest.get("below", []), ensure_ascii=True))
    print("nearest_above=" + json.dumps(nearest.get("above", []), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
