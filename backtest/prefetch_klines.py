#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Prefetch (download + cache) Bybit public klines for backtests.

This script is intentionally boring: it just fills the JSON cache files that
`run_portfolio.py` and other backtests can reuse, so you don't hit Bybit rate
limits mid-run.

Example:
  python3 backtest/prefetch_klines.py \
    --auto_symbols --top_n 25 --min_volume_usd 20000000 \
    --days 180 --end 2026-02-01 \
    --cache .cache/klines

If you get rate-limited, rerun — completed cache files are skipped.
"""

from __future__ import annotations

import os, sys
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests

from backtest.bybit_data import fetch_klines_public
from backtest.engine import Candle


def _parse_end(s: Optional[str]) -> int:
    if not s:
        return int(time.time())
    dt = datetime.strptime(s.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _select_auto_symbols(*, base: str, min_volume_usd: float, top_n: int, exclude: List[str]) -> List[str]:
    url = f"{base.rstrip('/')}/v5/market/tickers"
    params = {"category": "linear"}
    js = requests.get(url, params=params, timeout=20).json()
    if js.get("retCode") != 0:
        raise RuntimeError(f"Bybit tickers error {js.get('retCode')}: {js.get('retMsg')}")
    lst = (((js.get("result") or {}).get("list")) or [])

    ex = set(x.strip().upper() for x in exclude if x.strip())
    rows = []
    for it in lst:
        sym = str(it.get("symbol") or "").upper()
        if not sym or not sym.endswith("USDT"):
            continue
        if sym in ex:
            continue
        try:
            turn = float(it.get("turnover24h") or 0.0)
        except Exception:
            turn = 0.0
        if turn < float(min_volume_usd):
            continue
        rows.append((turn, sym))

    rows.sort(reverse=True)
    return [sym for _, sym in rows[: max(1, int(top_n))]]


def _k_ts_ms(k) -> int:
    for attr in ("ts", "start_ms", "startTime", "start_time"):
        v = getattr(k, attr, None)
        if v is not None:
            return int(v)
    raise AttributeError("Kline has no timestamp attribute (ts/start_ms/startTime/start_time)")


def _cache_path(cache_dir: Path, symbol: str, start_ms: int, end_ms: int) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{symbol}_5_{start_ms}_{end_ms}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="Comma-separated symbols")
    ap.add_argument("--auto_symbols", action="store_true", help="Auto-select from Bybit 24h tickers")
    ap.add_argument("--min_volume_usd", type=float, default=20_000_000.0)
    ap.add_argument("--top_n", type=int, default=15)
    ap.add_argument("--exclude_symbols", type=str, default="")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--end", default="", help="YYYY-MM-DD (UTC)")
    ap.add_argument("--bybit_base", default=os.getenv("BYBIT_BASE", "https://api.bybit.com"))
    ap.add_argument("--cache", default=".cache/klines")
    ap.add_argument("--polite_sleep_sec", type=float, default=float(os.getenv("BYBIT_DATA_POLITE_SLEEP_SEC", "0.6")))
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    exclude = [s.strip() for s in (args.exclude_symbols or "").split(",") if s.strip()]
    if args.auto_symbols or not symbols:
        symbols = _select_auto_symbols(base=args.bybit_base, min_volume_usd=args.min_volume_usd, top_n=args.top_n, exclude=exclude)
    if not symbols:
        raise SystemExit("No symbols selected. Provide --symbols or relax --min_volume_usd/--top_n.")

    end_ts = _parse_end(args.end)
    start_ts = end_ts - int(args.days) * 86400
    start_ms = int(start_ts) * 1000
    end_ms = int(end_ts) * 1000

    cache_dir = Path(args.cache)

    print(f"Prefetch 5m klines: {len(symbols)} symbols, {args.days}d, {datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime('%Y-%m-%d')}..{datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime('%Y-%m-%d')} UTC")
    print(f"Cache dir: {cache_dir}")

    ok = 0
    skipped = 0
    failed = 0

    for idx, sym in enumerate(symbols, 1):
        fname = _cache_path(cache_dir, sym, start_ms, end_ms)
        if fname.exists() and fname.stat().st_size > 50:
            skipped += 1
            print(f"[{idx}/{len(symbols)}] {sym}: cached (skip)")
            continue

        print(f"[{idx}/{len(symbols)}] {sym}: downloading...")
        try:
            kl = fetch_klines_public(sym, interval="5", start_ms=start_ms, end_ms=end_ms, base=args.bybit_base, cache=True, polite_sleep_sec=args.polite_sleep_sec)
            rows = [[_k_ts_ms(k), k.o, k.h, k.l, k.c, k.v] for k in kl]
            fname.write_text(json.dumps(rows), encoding="utf-8")
            ok += 1
            print(f"  saved {len(rows)} bars -> {fname.name}")
        except Exception as e:
            failed += 1
            print(f"  FAILED: {e}")
            # small cool-down (rate limit etc.) and continue; rerun later to resume
            time.sleep(5.0)

    print(f"Done. ok={ok} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
