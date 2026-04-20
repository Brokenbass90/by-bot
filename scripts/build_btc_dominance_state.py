"""
BTC Dominance Regime Filter — build_btc_dominance_state.py
============================================================
Fetches BTC.D (Bitcoin dominance %) from Bybit using the BTC/TOTAL ratio
approximation and writes a state file used by strategies.

BTC.D logic:
  - BTC.D rising   (+0.5% over 48h) → Alt season ENDING   → reduce alt longs, allow alt shorts
  - BTC.D falling  (-0.5% over 48h) → Alt season STARTING → allow alt longs, reduce alt shorts
  - BTC.D neutral  (±0.5%)          → No alt bias change

Proxy: use BTC market cap relative to total by fetching BTCUSDT price
and estimating BTC.D using EMA of BTC price momentum vs SOL/ETH/LINK.
Actually: we approximate using BTC vs ETH ratio momentum (BTC/ETH).
If BTC/ETH rising → BTC dominance rising → alts weak.
If BTC/ETH falling → BTC dominance falling → alt season.

Output file: runtime/btc_dominance_state.json
  {
    "ts": 1234567890,
    "btc_eth_ratio": 15.3,
    "btc_eth_ratio_48h_change_pct": +0.8,
    "alt_bias": "weak",     # "strong" | "weak" | "neutral"
    "btc_dominance_trend": "rising" | "falling" | "flat",
    "recommended_alt_risk_mult": 0.5,   # 0.3-1.0 multiplier for alt positions
    "updated_at": "2026-04-19T12:00:00Z"
  }

Usage in regime overlays:
  - Source this file in build_regime_state.py
  - Apply ALT_RISK_MULT_OVERRIDE when alt_bias == "weak"

Run: python3 scripts/build_btc_dominance_state.py
Cron: every 4 hours (add to existing cron)
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "runtime" / "btc_dominance_state.json"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

BYBIT_KLINES = "https://api.bybit.com/v5/market/kline"

def _fetch_klines(symbol: str, interval: str = "240", limit: int = 30) -> list:
    url = f"{BYBIT_KLINES}?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "BybitBot/1.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            body = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[btc_dom] fetch error for {symbol}: {e}", file=sys.stderr)
        return []
    if body.get("retCode") != 0:
        return []
    return list(reversed(body.get("result", {}).get("list", [])))

def _close(row) -> float:
    try:
        return float(row[4])
    except:
        return 0.0

def compute_btc_dominance_state() -> dict:
    now = datetime.now(tz=timezone.utc)

    # Fetch 4H closes for BTC and ETH (30 bars = 5 days)
    btc_rows = _fetch_klines("BTCUSDT", "240", 30)
    eth_rows = _fetch_klines("ETHUSDT", "240", 30)

    if len(btc_rows) < 10 or len(eth_rows) < 10:
        print("[btc_dom] insufficient data, keeping existing state", file=sys.stderr)
        if OUTPUT.exists():
            return json.loads(OUTPUT.read_text())
        return {"error": "no_data", "ts": int(now.timestamp())}

    n = min(len(btc_rows), len(eth_rows))
    btc_closes = [_close(r) for r in btc_rows[-n:]]
    eth_closes = [_close(r) for r in eth_rows[-n:]]

    # BTC/ETH ratio (higher = BTC dominant, alts weak)
    ratios = [b / e if e > 0 else 0 for b, e in zip(btc_closes, eth_closes)]
    current_ratio = ratios[-1]

    # 48h change (12 × 4H bars)
    lookback_bars = min(12, len(ratios) - 1)
    old_ratio = ratios[-lookback_bars - 1]
    ratio_change_pct = ((current_ratio - old_ratio) / old_ratio * 100.0) if old_ratio > 0 else 0.0

    # BTC absolute momentum (48h price change)
    btc_now  = btc_closes[-1]
    btc_48h  = btc_closes[-min(12, len(btc_closes))]
    btc_momentum_pct = ((btc_now - btc_48h) / btc_48h * 100.0) if btc_48h > 0 else 0.0

    # Determine dominance trend
    THRESHOLD_RISING  = +0.5   # BTC/ETH ratio up 0.5% → BTC strengthening vs ETH
    THRESHOLD_FALLING = -0.5   # BTC/ETH ratio down 0.5% → alts strengthening

    if ratio_change_pct >= THRESHOLD_RISING:
        btc_dominance_trend = "rising"
        alt_bias = "weak"
        # Further reduce if ratio is rising fast
        mult = max(0.3, 1.0 - min(1.0, ratio_change_pct / 3.0))
    elif ratio_change_pct <= THRESHOLD_FALLING:
        btc_dominance_trend = "falling"
        alt_bias = "strong"
        mult = min(1.2, 1.0 + min(0.2, abs(ratio_change_pct) / 5.0))
    else:
        btc_dominance_trend = "flat"
        alt_bias = "neutral"
        mult = 1.0

    state = {
        "ts": int(now.timestamp()),
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "btc_price": round(btc_now, 2),
        "eth_price": round(eth_closes[-1], 2),
        "btc_eth_ratio": round(current_ratio, 4),
        "btc_eth_ratio_48h_change_pct": round(ratio_change_pct, 3),
        "btc_momentum_48h_pct": round(btc_momentum_pct, 2),
        "btc_dominance_trend": btc_dominance_trend,
        "alt_bias": alt_bias,
        "recommended_alt_risk_mult": round(mult, 2),
        "note": (
            "BTC/ETH ratio rising → alts weak, reduce alt long exposure"
            if alt_bias == "weak" else
            "BTC/ETH ratio falling → alt season, increase alt exposure"
            if alt_bias == "strong" else
            "BTC/ETH ratio flat → neutral alt bias"
        ),
    }
    return state


if __name__ == "__main__":
    state = compute_btc_dominance_state()
    OUTPUT.write_text(json.dumps(state, indent=2))
    bias   = state.get("alt_bias", "?")
    trend  = state.get("btc_dominance_trend", "?")
    mult   = state.get("recommended_alt_risk_mult", 1.0)
    change = state.get("btc_eth_ratio_48h_change_pct", 0)
    print(f"BTC/ETH 48h: {change:+.2f}% | dominance={trend} | alt_bias={bias} | risk_mult={mult}")
    print(f"Written → {OUTPUT}")
