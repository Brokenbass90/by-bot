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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.bybit_data import DEFAULT_BYBIT_BASE, fetch_klines_public


def _now_ms() -> int:
    return int(time.time() * 1000)


def _get_tickers(base: str) -> List[dict]:
    import requests
    url = f"{base.rstrip('/')}/v5/market/tickers"
    params = {"category": "linear"}
    js = requests.get(url, params=params, timeout=20).json()
    if js.get("retCode") != 0:
        raise RuntimeError(f"Bybit tickers error {js.get('retCode')}: {js.get('retMsg')}")
    return ((js.get("result") or {}).get("list") or [])


def _get_instruments_info(base: str) -> Dict[str, dict]:
    import requests
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


def _atr_pct_from_ohlc(h: list[float], l: list[float], c: list[float], period: int = 14, fallback: float = 0.0) -> float:
    if len(c) < period + 1 or len(h) < period or len(l) < period:
        return float(fallback)
    trs: list[float] = []
    for i in range(1, period + 1):
        pc = c[-i - 1]
        tr = max(h[-i] - l[-i], abs(h[-i] - pc), abs(l[-i] - pc))
        trs.append(tr / max(1e-12, pc))
    return 100.0 * sum(trs) / float(period)


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
    return float(_atr_pct_from_ohlc(h, l, c, period=14, fallback=0.0))


def _resample_1h_from_5m(bars: list[dict]) -> list[dict]:
    if not bars:
        return []
    # assume bars sorted by ts asc
    out = []
    bucket = None
    cur = None
    for b in bars:
        ts = int(b.get("ts") or 0)
        if ts <= 0:
            continue
        hour = ts // 3_600_000
        if bucket is None or hour != bucket:
            if cur:
                out.append(cur)
            bucket = hour
            cur = {"ts": ts, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b.get("v", 0.0)}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
            cur["v"] = float(cur.get("v", 0.0)) + float(b.get("v", 0.0))
    if cur:
        out.append(cur)
    return out


def _atr_pct_1h_from_cache(bars_5m: list[dict], lookback_days: int) -> float:
    if not bars_5m:
        return 0.0
    bars_5m = sorted(bars_5m, key=lambda x: x.get("ts", 0))
    bars_1h = _resample_1h_from_5m(bars_5m)
    if len(bars_1h) < 20:
        return 0.0
    # take last lookback_days
    if lookback_days and lookback_days > 0:
        cutoff = bars_1h[-1]["ts"] - lookback_days * 24 * 3_600_000
        bars_1h = [b for b in bars_1h if b["ts"] >= cutoff]
    h = [float(b["h"]) for b in bars_1h]
    l = [float(b["l"]) for b in bars_1h]
    c = [float(b["c"]) for b in bars_1h]
    return float(_atr_pct_from_ohlc(h, l, c, period=14, fallback=0.0))


def _turnover_24h_from_cache(bars_5m: list[dict]) -> float:
    if not bars_5m:
        return 0.0
    bars_5m = sorted(bars_5m, key=lambda x: x.get("ts", 0))
    last_ts = bars_5m[-1]["ts"]
    cutoff = last_ts - 24 * 3_600_000
    turn = 0.0
    for b in bars_5m:
        if b["ts"] >= cutoff:
            turn += float(b.get("v", 0.0)) * float(b.get("c", 0.0))
    return turn


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
    ap.add_argument("--cache_dir", default="", help="Offline mode: use cached 5m klines from data_cache.")
    args = ap.parse_args()

    with open(args.profiles, "r", encoding="utf-8") as f:
        profiles = json.load(f) or {}

    base_cfg = profiles.get("base") or {}
    strat_cfg = profiles.get("per_strategy") or {}

    base = args.bybit_base
    if args.cache_dir:
        # Offline mode: build pseudo tickers/instruments from cached 5m data
        cache = Path(args.cache_dir)
        if not cache.exists():
            raise SystemExit(f"cache_dir not found: {args.cache_dir}")
        tickers = []
        instruments = {}
        # pick latest cache file per symbol
        latest = {}
        for p in cache.glob("*.json"):
            name = p.stem
            if "_5_" not in name:
                continue
            sym = name.split("_5_")[0].upper()
            latest.setdefault(sym, []).append(p)
        for sym, files in latest.items():
            # use lexicographically max (newest end date)
            f = sorted(files)[-1]
            try:
                bars = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not bars:
                continue
            bars = sorted(bars, key=lambda x: x.get("ts", 0))
            first_ts = int(bars[0].get("ts") or 0)
            last_ts = int(bars[-1].get("ts") or 0)
            turnover24h = _turnover_24h_from_cache(bars)
            tickers.append({"symbol": sym, "turnover24h": turnover24h})
            instruments[sym] = {"symbol": sym, "launchTime": first_ts}
        # store cache for ATR later via closure
        cache_map = {sym: sorted(files)[-1] for sym, files in latest.items()}
    elif args.instruments_json:
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

    if args.cache_dir:
        pass
    elif args.tickers_json:
        js = _load_json(args.tickers_json)
        tickers = ((js.get("result") or {}).get("list") or [])
    else:
        tickers = _get_tickers(base)
        if args.dump_json_dir:
            _save_json(os.path.join(args.dump_json_dir, "tickers.json"), {"result": {"list": tickers}})

    def _atr_for_symbol(sym: str, lookback_days: int) -> float:
        if args.cache_dir:
            p = cache_map.get(sym)
            if not p:
                return 0.0
            try:
                bars = json.loads(Path(p).read_text(encoding="utf-8"))
            except Exception:
                return 0.0
            return _atr_pct_1h_from_cache(bars, lookback_days)
        return _atr_pct_1h(sym, base=base, lookback_days=lookback_days, polite_sleep_sec=float(args.polite_sleep_sec))

    def _select_symbols_offline(
        min_turnover: float,
        min_atr_pct: float,
        min_listing_days: int,
        lookback_days: int,
        top_n: int,
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
            turn = float(it.get("turnover24h") or 0.0)
            if turn < float(min_turnover):
                continue
            info = instruments.get(sym, {})
            try:
                launch_ms = int(info.get("launchTime") or 0)
            except Exception:
                launch_ms = 0
            if launch_ms and (now_ms - launch_ms) < min_age_ms:
                continue
            atr_pct = _atr_for_symbol(sym, lookback_days)
            if atr_pct < float(min_atr_pct):
                continue
            rows.append((turn, atr_pct, launch_ms or 0.0, sym))
        rows.sort(reverse=True)
        return [sym for _, _, _, sym in rows[: max(1, int(top_n))]]

    if args.cache_dir:
        base_allow = _select_symbols_offline(
            min_turnover=float(base_cfg.get("min_turnover", 25_000_000)),
            min_atr_pct=float(base_cfg.get("min_atr_pct", 0.35)),
            min_listing_days=int(base_cfg.get("min_listing_days", 7)),
            lookback_days=int(base_cfg.get("lookback_days", 14)),
            top_n=int(base_cfg.get("top_n", 60)),
            restrict_to=None,
        )
    else:
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
        if args.cache_dir:
            allow = _select_symbols_offline(
                min_turnover=float(cfg.get("min_turnover", base_cfg.get("min_turnover", 25_000_000))),
                min_atr_pct=float(cfg.get("min_atr_pct", base_cfg.get("min_atr_pct", 0.35))),
                min_listing_days=int(cfg.get("min_listing_days", base_cfg.get("min_listing_days", 7))),
                lookback_days=int(cfg.get("lookback_days", base_cfg.get("lookback_days", 14))),
                top_n=int(cfg.get("top_n", base_cfg.get("top_n", 60))),
                restrict_to=base_set,
            )
        else:
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
