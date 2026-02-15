#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build JSON symbol filters for live bot.

Profiles are defined in a JSON file with a base profile and optional per-strategy profiles.
The output JSON is compatible with SYMBOL_FILTERS_PATH and supports per-strategy allow/deny.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f) or {}


def _save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True)


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


def _select_symbols(
    tickers: List[dict],
    instruments: Dict[str, dict],
    *,
    min_turnover: float,
    min_atr_pct: float,
    min_listing_days: int,
    lookback_days: int,
    top_n: int,
    base: str,
    polite_sleep_sec: float,
    restrict_to: set[str] | None = None,
) -> List[str]:
    now_ms = _now_ms()
    min_age_ms = int(min_listing_days) * 86400 * 1000

    rows: List[Tuple[float, float, float, str]] = []
    for it in tickers:
        sym = str(it.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            continue
        if restrict_to and sym not in restrict_to:
            continue
        try:
            turn = float(it.get("turnover24h") or 0.0)
        except Exception:
            turn = 0.0
        if turn < float(min_turnover):
            continue

        info = instruments.get(sym, {})
        try:
            launch_ms = int(info.get("launchTime") or 0)
        except Exception:
            launch_ms = 0
        if launch_ms and (now_ms - launch_ms) < min_age_ms:
            continue

        atr_pct = _atr_pct_1h(sym, base=base, lookback_days=lookback_days, polite_sleep_sec=polite_sleep_sec)
        if atr_pct < float(min_atr_pct):
            continue

        rows.append((turn, atr_pct, launch_ms or 0.0, sym))

    rows.sort(reverse=True)
    selected = rows[: max(1, int(top_n))]
    return [sym for _, _, _, sym in selected]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True, help="Path to profiles JSON.")
    ap.add_argument("--out", required=True, help="Output JSON file (SYMBOL_FILTERS_PATH).")
    ap.add_argument("--bybit_base", default=DEFAULT_BYBIT_BASE)
    ap.add_argument("--polite_sleep_sec", type=float, default=float(os.getenv("BYBIT_DATA_POLITE_SLEEP_SEC", "0.8")))
    ap.add_argument("--tickers_json", default="", help="Optional: load /v5/market/tickers response from file.")
    ap.add_argument("--instruments_json", default="", help="Optional: load /v5/market/instruments-info response from file.")
    ap.add_argument("--dump_json_dir", default="", help="Optional: save raw JSON responses to this dir.")
    args = ap.parse_args()

    with open(args.profiles, "r", encoding="utf-8") as f:
        profiles = json.load(f) or {}

    base_cfg = profiles.get("base") or {}
    strat_cfg = profiles.get("per_strategy") or {}

    base = args.bybit_base
    if args.instruments_json:
        js = _load_json(args.instruments_json)
        instruments = {}
        lst = ((js.get("result") or {}).get("list") or [])
        for it in lst:
            sym = str(it.get("symbol") or "").upper()
            if sym:
                instruments[sym] = it
    else:
        js = None
        instruments = _get_instruments_info(base)
        if args.dump_json_dir:
            _save_json(os.path.join(args.dump_json_dir, "instruments.json"), {"result": {"list": list(instruments.values())}})

    if args.tickers_json:
        js = _load_json(args.tickers_json)
        tickers = ((js.get("result") or {}).get("list") or [])
    else:
        tickers = _get_tickers(base)
        if args.dump_json_dir:
            _save_json(os.path.join(args.dump_json_dir, "tickers.json"), {"result": {"list": tickers}})

    base_allow = _select_symbols(
        tickers,
        instruments,
        min_turnover=float(base_cfg.get("min_turnover", 25_000_000)),
        min_atr_pct=float(base_cfg.get("min_atr_pct", 0.35)),
        min_listing_days=int(base_cfg.get("min_listing_days", 7)),
        lookback_days=int(base_cfg.get("lookback_days", 14)),
        top_n=int(base_cfg.get("top_n", 60)),
        base=base,
        polite_sleep_sec=float(args.polite_sleep_sec),
        restrict_to=None,
    )

    per_out: dict[str, dict] = {}
    base_set = set(base_allow)
    for name, cfg in strat_cfg.items():
        allow = _select_symbols(
            tickers,
            instruments,
            min_turnover=float(cfg.get("min_turnover", base_cfg.get("min_turnover", 25_000_000))),
            min_atr_pct=float(cfg.get("min_atr_pct", base_cfg.get("min_atr_pct", 0.35))),
            min_listing_days=int(cfg.get("min_listing_days", base_cfg.get("min_listing_days", 7))),
            lookback_days=int(cfg.get("lookback_days", base_cfg.get("lookback_days", 14))),
            top_n=int(cfg.get("top_n", base_cfg.get("top_n", 60))),
            base=base,
            polite_sleep_sec=float(args.polite_sleep_sec),
            restrict_to=base_set,
        )
        per_out[str(name).lower()] = {"allowlist": allow, "denylist": []}

    out = {
        "allowlist": base_allow,
        "denylist": profiles.get("denylist", []),
        "per_strategy": per_out,
        "meta": {
            "generated_at": int(time.time()),
            "base": base,
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=True)

    print(f"Saved filters to {args.out} (base_allow={len(base_allow)})")
    for k, v in per_out.items():
        print(f"  {k}: allow={len(v.get('allowlist') or [])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
