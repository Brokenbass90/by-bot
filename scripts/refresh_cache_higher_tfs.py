#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.bybit_data import fetch_klines_public  # noqa: E402


CORE_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "SUIUSDT",
    "ATOMUSDT",
    "XRPUSDT",
    "BNBUSDT",
)

DEFAULT_INTERVALS = ("15", "60", "240", "1440")


def _parse_csv(raw: str, default: Iterable[str]) -> list[str]:
    values = [item.strip().upper() for item in str(raw or "").replace(";", ",").split(",") if item.strip()]
    return values or list(default)


def _parse_end(raw: str) -> int:
    if not raw:
        return int(time.time())
    dt = datetime.strptime(raw.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _k_ts_ms(kline) -> int:
    for attr in ("ts", "start_ms", "startTime", "start_time"):
        value = getattr(kline, attr, None)
        if value is not None:
            return int(value)
    raise AttributeError("Kline has no timestamp attribute")


def _cache_path(cache_dir: Path, symbol: str, interval: str, start_ms: int, end_ms: int) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{symbol}_{interval}_{start_ms}_{end_ms}.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh .cache/klines for higher timeframes used by strategy research.")
    ap.add_argument("--symbols", default=",".join(CORE_SYMBOLS))
    ap.add_argument("--intervals", "--tfs", dest="intervals", default=",".join(DEFAULT_INTERVALS))
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--end", default="", help="YYYY-MM-DD UTC. Defaults to now.")
    ap.add_argument("--cache", default=".cache/klines")
    ap.add_argument("--bybit-base", default=os.getenv("BYBIT_BASE", "https://api.bybit.com"))
    ap.add_argument("--polite-sleep-sec", type=float, default=float(os.getenv("BYBIT_DATA_POLITE_SLEEP_SEC", "0.35") or 0.35))
    ap.add_argument("--force", action="store_true", help="Refresh even when the exact cache file exists.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    symbols = _parse_csv(args.symbols, CORE_SYMBOLS)
    intervals = [item.strip() for item in str(args.intervals or "").replace(";", ",").split(",") if item.strip()]
    if not intervals:
        intervals = list(DEFAULT_INTERVALS)

    end_ts = _parse_end(args.end)
    start_ts = end_ts - int(args.days) * 86400
    start_ms = start_ts * 1000
    end_ms = end_ts * 1000
    cache_dir = Path(args.cache)

    ok = 0
    skipped = 0
    empty = 0
    failed = 0
    total = len(symbols) * len(intervals)

    if not args.quiet:
        start_s = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        end_s = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        print(f"Refresh higher-TF klines: {len(symbols)} symbols x {len(intervals)} intervals")
        print(f"Window: {start_s}..{end_s} UTC ({args.days}d)")
        print(f"Cache: {cache_dir}")

    for interval in intervals:
        for idx, symbol in enumerate(symbols, start=1):
            path = _cache_path(cache_dir, symbol, interval, start_ms, end_ms)
            label = f"[{interval} {idx}/{len(symbols)}]"
            if path.exists() and path.stat().st_size > 50 and not args.force:
                skipped += 1
                if not args.quiet:
                    print(f"{label} {symbol}: cached")
                continue
            try:
                klines = fetch_klines_public(
                    symbol,
                    interval=str(interval),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    base=args.bybit_base,
                    cache=True,
                    polite_sleep_sec=float(args.polite_sleep_sec),
                )
                rows = [[_k_ts_ms(k), k.o, k.h, k.l, k.c, k.v] for k in klines]
                path.write_text(json.dumps(rows), encoding="utf-8")
                if rows:
                    ok += 1
                    if not args.quiet:
                        print(f"{label} {symbol}: saved {len(rows)} bars -> {path.name}")
                else:
                    empty += 1
                    print(f"{label} {symbol}: empty")
            except Exception as exc:
                failed += 1
                print(f"{label} {symbol}: FAILED {exc}")
                time.sleep(3.0)

    print(f"Done. total={total} ok={ok} skipped={skipped} empty={empty} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
