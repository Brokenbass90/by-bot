#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dynamic universe scanner (Bybit linear USDT):
- filters by 24h turnover
- filters by listing age (min days)
- filters by ATR% on 1h candles
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Dict, List, Tuple

import requests

from backtest.bybit_data import DEFAULT_BYBIT_BASE, fetch_klines_public
from indicators import atr_pct_from_ohlc


def _now_ms() -> int:
    return int(time.time() * 1000)


def _get_tickers(base: str) -> List[dict]:
    url = f"{base.rstrip('/')}/v5/market/tickers"
    params = {"category": "linear"}
    js = requests.get(url, params=params, timeout=20).json()
    if js.get("retCode") != 0:
        raise RuntimeError(f"Bybit tickers error {js.get('retCode')}: {js.get('retMsg')}")
    return ((js.get("result") or {}).get("list") or [])


def _get_instruments_info(base: str) -> Dict[str, dict]:
    url = f"{base.rstrip('/')}/v5/market/instruments-info"
    params = {"category": "linear"}
    out: Dict[str, dict] = {}
    cursor = None
    while True:
        if cursor:
            params["cursor"] = cursor
        js = requests.get(url, params=params, timeout=20).json()
        if js.get("retCode") != 0:
            raise RuntimeError(f"Bybit instruments error {js.get('retCode')}: {js.get('retMsg')}")
        lst = ((js.get("result") or {}).get("list") or [])
        for it in lst:
            sym = str(it.get("symbol") or "").upper()
            if sym:
                out[sym] = it
        cursor = (js.get("result") or {}).get("nextPageCursor")
        if not cursor:
            break
    return out


def _atr_pct_1h(symbol: str, *, base: str, lookback_days: int, polite_sleep_sec: float) -> float:
    end_ms = _now_ms()
    start_ms = end_ms - int(lookback_days) * 86400 * 1000
    kl = fetch_klines_public(
        symbol,
        interval="60",
        start_ms=start_ms,
        end_ms=end_ms,
        base=base,
        cache=True,
        polite_sleep_sec=polite_sleep_sec,
    )
    if len(kl) < 20:
        return 0.0
    h = [float(k.h) for k in kl]
    l = [float(k.l) for k in kl]
    c = [float(k.c) for k in kl]
    return float(atr_pct_from_ohlc(h, l, c, period=14, fallback=0.0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min_turnover", type=float, default=25_000_000.0, help="24h turnover filter (USD).")
    ap.add_argument("--min_atr_pct", type=float, default=0.35, help="Min ATR%% on 1h candles.")
    ap.add_argument("--min_listing_days", type=int, default=7, help="Exclude symbols younger than this.")
    ap.add_argument("--lookback_days", type=int, default=14, help="ATR lookback days.")
    ap.add_argument("--top_n", type=int, default=60, help="Max output symbols.")
    ap.add_argument("--bybit_base", default=DEFAULT_BYBIT_BASE)
    ap.add_argument("--polite_sleep_sec", type=float, default=float(os.getenv("BYBIT_DATA_POLITE_SLEEP_SEC", "0.8")))
    ap.add_argument("--out", default="", help="Optional output file for comma-separated symbols.")
    args = ap.parse_args()

    base = args.bybit_base
    instruments = _get_instruments_info(base)
    tickers = _get_tickers(base)

    now_ms = _now_ms()
    min_age_ms = int(args.min_listing_days) * 86400 * 1000

    rows: List[Tuple[float, float, float, str]] = []
    for it in tickers:
        sym = str(it.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            continue
        try:
            turn = float(it.get("turnover24h") or 0.0)
        except Exception:
            turn = 0.0
        if turn < float(args.min_turnover):
            continue

        info = instruments.get(sym, {})
        launch_ms = None
        try:
            launch_ms = int(info.get("launchTime") or 0)
        except Exception:
            launch_ms = 0
        if launch_ms and (now_ms - launch_ms) < min_age_ms:
            continue

        atr_pct = _atr_pct_1h(sym, base=base, lookback_days=args.lookback_days, polite_sleep_sec=args.polite_sleep_sec)
        if atr_pct < float(args.min_atr_pct):
            continue

        rows.append((turn, atr_pct, launch_ms or 0.0, sym))

    rows.sort(reverse=True)  # turnover desc
    selected = rows[: max(1, int(args.top_n))]

    symbols = [sym for _, _, _, sym in selected]
    print("Selected symbols:", ",".join(symbols))
    for turn, atr_pct, launch_ms, sym in selected:
        age_days = (now_ms - launch_ms) / 86400000.0 if launch_ms else -1
        print(f"{sym}\tturnover24h={turn:,.0f}\tATR%={atr_pct:.3f}\tage_days={age_days:.1f}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(",".join(symbols))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
