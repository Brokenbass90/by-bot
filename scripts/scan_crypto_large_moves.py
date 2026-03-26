from __future__ import annotations

import argparse
import csv
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _utc_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_csv_list(raw: str) -> list[int]:
    return [int(x.strip()) for x in str(raw).split(",") if x.strip()]


def _future_window_max(values: list[float], window: int) -> list[float | None]:
    n = len(values)
    if n <= 1 or window <= 0:
        return [None] * n
    arr = values[1:]
    out = [None] * n
    dq: deque[int] = deque()
    for idx, value in enumerate(arr):
        while dq and arr[dq[-1]] <= value:
            dq.pop()
        dq.append(idx)
        left = idx - window + 1
        while dq and dq[0] < left:
            dq.popleft()
        if idx >= window - 1:
            base_idx = idx - window + 1
            out[base_idx] = arr[dq[0]]
    return out


def _prefix_sum(values: list[float]) -> list[float]:
    out = [0.0]
    acc = 0.0
    for v in values:
        acc += v
        out.append(acc)
    return out


def _mean(prefix: list[float], start: int, end: int) -> float | None:
    if start < 0 or end <= start:
        return None
    return (prefix[end] - prefix[start]) / float(end - start)


@dataclass
class MoveEvent:
    symbol: str
    source_file: str
    horizon_bars: int
    horizon_hours: float
    start_idx: int
    start_ts_ms: int
    start_ts_utc: str
    start_close: float
    future_close: float
    future_close_return_pct: float
    future_max_high: float
    future_max_return_pct: float
    pre_ret_1h_pct: float | None
    pre_ret_4h_pct: float | None
    pre_ret_24h_pct: float | None
    ma_gap_4h_pct: float | None
    atr_like_pct_4h: float | None
    vol_ratio_4h: float | None
    compression_1h_vs_24h: float | None


def _load_rows(path: Path) -> list[list[float]]:
    with path.open() as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        return []
    if not rows:
        return []
    first = rows[0]
    if isinstance(first, list):
        return rows
    if isinstance(first, dict):
        out: list[list[float]] = []
        for row in rows:
            try:
                out.append([
                    int(row["ts"]),
                    float(row["o"]),
                    float(row["h"]),
                    float(row["l"]),
                    float(row["c"]),
                    float(row.get("v", 0.0)),
                ])
            except Exception:
                continue
        return out
    return []


def _iter_events_for_file(path: Path, horizons: list[int], min_history: int) -> Iterable[MoveEvent]:
    rows = _load_rows(path)
    if len(rows) < max(horizons) + min_history + 2:
        return

    symbol = path.name.split("_", 1)[0].upper()
    ts = [int(r[0]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    vols = [float(r[5]) for r in rows]
    ranges = [max(0.0, highs[i] - lows[i]) for i in range(len(rows))]

    range_ps = _prefix_sum(ranges)
    vol_ps = _prefix_sum(vols)
    close_ps = _prefix_sum(closes)

    for horizon in horizons:
        future_highs = _future_window_max(highs, horizon)
        for i in range(min_history, len(rows) - horizon - 1):
            future_max_high = future_highs[i]
            future_close = closes[i + horizon]
            start_close = closes[i]
            if future_max_high is None or start_close <= 0:
                continue

            mean_close_4h = _mean(close_ps, i - 48, i)
            mean_range_4h = _mean(range_ps, i - 48, i)
            mean_range_1h = _mean(range_ps, i - 12, i)
            mean_range_24h = _mean(range_ps, i - 288, i)
            mean_vol_4h = _mean(vol_ps, i - 48, i)

            pre_ret_1h = (start_close / closes[i - 12] - 1.0) * 100.0 if i >= 12 and closes[i - 12] > 0 else None
            pre_ret_4h = (start_close / closes[i - 48] - 1.0) * 100.0 if i >= 48 and closes[i - 48] > 0 else None
            pre_ret_24h = (start_close / closes[i - 288] - 1.0) * 100.0 if i >= 288 and closes[i - 288] > 0 else None
            ma_gap_4h = ((start_close - mean_close_4h) / mean_close_4h * 100.0) if mean_close_4h and mean_close_4h > 0 else None
            atr_like_4h = (mean_range_4h / start_close * 100.0) if mean_range_4h is not None and start_close > 0 else None
            vol_ratio_4h = (vols[i] / mean_vol_4h) if mean_vol_4h and mean_vol_4h > 0 else None
            compression = (mean_range_1h / mean_range_24h) if mean_range_1h is not None and mean_range_24h not in (None, 0.0) else None

            yield MoveEvent(
                symbol=symbol,
                source_file=path.name,
                horizon_bars=horizon,
                horizon_hours=horizon * 5.0 / 60.0,
                start_idx=i,
                start_ts_ms=ts[i],
                start_ts_utc=_utc_iso(ts[i]),
                start_close=start_close,
                future_close=future_close,
                future_close_return_pct=(future_close / start_close - 1.0) * 100.0,
                future_max_high=future_max_high,
                future_max_return_pct=(future_max_high / start_close - 1.0) * 100.0,
                pre_ret_1h_pct=pre_ret_1h,
                pre_ret_4h_pct=pre_ret_4h,
                pre_ret_24h_pct=pre_ret_24h,
                ma_gap_4h_pct=ma_gap_4h,
                atr_like_pct_4h=atr_like_4h,
                vol_ratio_4h=vol_ratio_4h,
                compression_1h_vs_24h=compression,
            )


def _select_non_overlapping(events: list[MoveEvent], cooldown_bars: int, top_k_per_symbol: int) -> list[MoveEvent]:
    chosen: list[MoveEvent] = []
    taken: dict[str, list[int]] = {}
    for event in sorted(events, key=lambda x: x.future_max_return_pct, reverse=True):
        starts = taken.setdefault(event.symbol, [])
        if any(abs(event.start_idx - s) < cooldown_bars for s in starts):
            continue
        starts.append(event.start_idx)
        chosen.append(event)
        if sum(1 for x in chosen if x.symbol == event.symbol and x.horizon_bars == event.horizon_bars) >= top_k_per_symbol:
            continue
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan local crypto cache for large forward moves and pre-move features.")
    parser.add_argument("--data-glob", default="data_cache/*USDT_5_*.json")
    parser.add_argument("--horizons", default="72,144,288", help="Forward horizons in 5m bars.")
    parser.add_argument("--top-k-per-horizon", type=int, default=100)
    parser.add_argument("--top-k-per-symbol", type=int, default=3)
    parser.add_argument("--min-history", type=int, default=288)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    root = Path.cwd()
    paths = sorted(root.glob(args.data_glob))
    horizons = _parse_csv_list(args.horizons)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir) if args.output_dir else root / "runtime" / "research" / f"crypto_large_moves_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_events: list[MoveEvent] = []
    for path in paths:
        all_events.extend(_iter_events_for_file(path, horizons, args.min_history))

    dedup: dict[tuple[str, int, int], MoveEvent] = {}
    for event in all_events:
        key = (event.symbol, event.horizon_bars, event.start_ts_ms)
        prev = dedup.get(key)
        if prev is None or event.future_max_return_pct > prev.future_max_return_pct:
            dedup[key] = event

    selected: list[MoveEvent] = []
    for horizon in horizons:
        horizon_events = [e for e in dedup.values() if e.horizon_bars == horizon]
        picked = _select_non_overlapping(horizon_events, cooldown_bars=horizon, top_k_per_symbol=args.top_k_per_symbol)
        picked = sorted(picked, key=lambda x: x.future_max_return_pct, reverse=True)[:args.top_k_per_horizon]
        selected.extend(picked)

    events_csv = out_dir / "top_events.csv"
    with events_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "symbol",
            "source_file",
            "horizon_bars",
            "horizon_hours",
            "start_ts_utc",
            "start_close",
            "future_close",
            "future_close_return_pct",
            "future_max_high",
            "future_max_return_pct",
            "pre_ret_1h_pct",
            "pre_ret_4h_pct",
            "pre_ret_24h_pct",
            "ma_gap_4h_pct",
            "atr_like_pct_4h",
            "vol_ratio_4h",
            "compression_1h_vs_24h",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for event in sorted(selected, key=lambda x: (x.horizon_bars, x.future_max_return_pct), reverse=True):
            row = {name: getattr(event, name) for name in fieldnames}
            writer.writerow(row)

    summary_rows = []
    for horizon in horizons:
        horizon_events = [e for e in selected if e.horizon_bars == horizon]
        by_symbol: dict[str, list[MoveEvent]] = {}
        for event in horizon_events:
            by_symbol.setdefault(event.symbol, []).append(event)
        for symbol, events in sorted(by_symbol.items()):
            summary_rows.append(
                {
                    "symbol": symbol,
                    "horizon_bars": horizon,
                    "horizon_hours": horizon * 5.0 / 60.0,
                    "events": len(events),
                    "best_return_pct": max(e.future_max_return_pct for e in events),
                    "avg_top_return_pct": sum(e.future_max_return_pct for e in events) / float(len(events)),
                    "avg_pre_ret_4h_pct": sum((e.pre_ret_4h_pct or 0.0) for e in events) / float(len(events)),
                    "avg_ma_gap_4h_pct": sum((e.ma_gap_4h_pct or 0.0) for e in events) / float(len(events)),
                    "avg_vol_ratio_4h": sum((e.vol_ratio_4h or 0.0) for e in events) / float(len(events)),
                    "avg_compression_1h_vs_24h": sum((e.compression_1h_vs_24h or 0.0) for e in events) / float(len(events)),
                }
            )

    summary_csv = out_dir / "symbol_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "horizon_bars",
                "horizon_hours",
                "events",
                "best_return_pct",
                "avg_top_return_pct",
                "avg_pre_ret_4h_pct",
                "avg_ma_gap_4h_pct",
                "avg_vol_ratio_4h",
                "avg_compression_1h_vs_24h",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"wrote {events_csv}")
    print(f"wrote {summary_csv}")
    print(f"events={len(selected)} files={len(paths)} horizons={len(horizons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
