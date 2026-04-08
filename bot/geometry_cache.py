from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
DATA_CACHE_DIR = ROOT / "data_cache"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def load_cache_rows(symbol: str, interval: str, *, data_cache_dir: Path | None = None) -> List[List[float]]:
    cache_dir = Path(data_cache_dir or DATA_CACHE_DIR)
    paths = sorted(cache_dir.glob(f"{symbol}_{interval}_*.json"), reverse=True)
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
                        safe_float(item["o"]),
                        safe_float(item["h"]),
                        safe_float(item["l"]),
                        safe_float(item["c"]),
                        safe_float(item["v"]),
                    ]
                )
            except Exception:
                continue
    merged.sort(key=lambda row: row[0])
    return merged


def aggregate_rows(rows: List[List[float]], target_min: int) -> List[List[float]]:
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


def load_rows(symbol: str, interval: str, *, data_cache_dir: Path | None = None) -> List[List[float]]:
    direct = load_cache_rows(symbol, interval, data_cache_dir=data_cache_dir)
    if direct:
        return direct
    if interval == "60":
        rows_5 = load_cache_rows(symbol, "5", data_cache_dir=data_cache_dir)
        if rows_5:
            return aggregate_rows(rows_5, 60)
    if interval == "240":
        rows_60 = load_cache_rows(symbol, "60", data_cache_dir=data_cache_dir)
        if rows_60:
            return aggregate_rows(rows_60, 240)
        rows_5 = load_cache_rows(symbol, "5", data_cache_dir=data_cache_dir)
        if rows_5:
            return aggregate_rows(rows_5, 240)
    return []
