#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_regime_state.py — Live Regime Orchestrator (V2)

Classifies the current market regime and writes:
  1. runtime/regime/orchestrator_state.json  — full machine-readable state
  2. configs/regime_orchestrator_latest.env  — env overlay for live bot

ARCHITECTURE: two-layer regime
  Layer 1 — MACRO (daily EMA50 vs EMA200):
    MACRO_BULL       daily EMA50 > EMA200 by > 5%   (structural bull, e.g. 2024)
    MACRO_WEAK_BULL  daily EMA50 > EMA200 by 1-5%
    MACRO_NEUTRAL    daily EMA50 ≈ EMA200 within ±1%
    MACRO_WEAK_BEAR  daily EMA50 < EMA200 by 1-5%
    MACRO_BEAR       daily EMA50 < EMA200 by > 5%   (structural bear, e.g. 2022)

  Layer 2 — INTERMEDIATE (4H EMA21 vs EMA55 + Efficiency Ratio):
    bull_trend   4H EMA21 > EMA55, close > EMA55, ER > threshold
    bull_chop    4H above EMA55 but low ER (choppy)
    bear_chop    4H EMA21 < EMA55 but low ER (drift/chop)
    bear_trend   4H EMA21 < EMA55, close < EMA55, ER > threshold

  Final risk mult = base_4h_mult × macro_modifier
  Example: bear_chop (0.70) × MACRO_BULL (+0.12) → 0.82 risk
  This means: in 2024 bull year, even 4H pullbacks get less risk reduction

Hysteresis (anti-flicker):
  A new regime is only applied after min_regime_hold_cycles consecutive
  re-computations agree (default 3). Prevents thrashing at regime boundaries.

Sleeve decision table (4H layer drives ON/OFF; macro layer drives risk multiplier):
  bull_trend  → breakout ON, asb1 ON, bounce ON, ivb1 ON, breakdown OFF, risk 1.00 × macro
  bull_chop   → breakout REDUCED, asb1 ON, flat ON, swing REDUCED, risk 0.85 × macro
  bear_chop   → breakdown ON, flat ON, swing ON, breakout OFF, risk 0.70 × macro
  bear_trend  → breakdown ON, flat ON, bear-swing ON, momentum OFF, risk 0.50 × macro

Usage:
  python3 scripts/build_regime_state.py            # one-shot
  python3 scripts/build_regime_state.py --dry-run  # print only, no files written
  python3 scripts/build_regime_state.py --loop 3600  # run every N seconds

Cron (every hour):
  0 * * * * cd /root/by-bot && python3 scripts/build_regime_state.py >> logs/regime_orchestrator.log 2>&1

Env vars:
  BYBIT_BASE               Bybit API base URL
  TG_TOKEN                 Telegram bot token (optional)
  TG_CHAT_ID               Telegram chat ID (optional)
  ORCH_MIN_HOLD_CYCLES     Hysteresis cycles before regime change (default 3)
  ORCH_ER_TREND_THRESH     ER threshold for "trending" (default 0.28)
  ORCH_BARS                4H bars to fetch (default 120 = ~20 days)
  ORCH_DAILY_BARS          Daily bars for macro overlay (default 220 = ~7 months)
  ORCH_MACRO_BULL_PCT      EMA50/200 gap% to call MACRO_BULL (default 5.0)
  ORCH_MACRO_BEAR_PCT      EMA50/200 gap% to call MACRO_BEAR (default -5.0)
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE_PATH = ROOT / "runtime" / "regime" / "orchestrator_state.json"
ENV_PATH   = ROOT / "configs" / "regime_orchestrator_latest.env"
LOG_PATH   = ROOT / "logs" / "regime_orchestrator.log"
CONTROL_PLANE_DIR = ROOT / "runtime" / "control_plane"
HISTORY_PATH = CONTROL_PLANE_DIR / "orchestrator_history.jsonl"
STATE_VERSION = "2"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ORCH] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
    ],
)
log = logging.getLogger("regime_orchestrator")

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------
MIN_HOLD_CYCLES  = int(os.getenv("ORCH_MIN_HOLD_CYCLES", "3"))
ER_TREND_THRESH  = float(os.getenv("ORCH_ER_TREND_THRESH", "0.28"))
ER_PERIOD        = int(os.getenv("ORCH_ER_PERIOD", "30"))
FETCH_BARS       = int(os.getenv("ORCH_BARS", "120"))
BULL_TREND_FLAT_ER_MAX = float(os.getenv("ORCH_BULL_TREND_FLAT_ER_MAX", "0.55"))
MIXED_SIGN_PRICE_WEIGHT = float(os.getenv("ORCH_MIXED_SIGN_PRICE_WEIGHT", "1.0"))
MIXED_SIGN_EMA_WEIGHT = float(os.getenv("ORCH_MIXED_SIGN_EMA_WEIGHT", "0.5"))
MIXED_SIGN_EDGE_PCT = float(os.getenv("ORCH_MIXED_SIGN_EDGE_PCT", "0.15"))
# ── Macro overlay (daily EMA50 vs EMA200) ────────────────────────────────────
DAILY_BARS       = int(os.getenv("ORCH_DAILY_BARS", "220"))   # ~7 months of daily bars
MACRO_BULL_PCT   = float(os.getenv("ORCH_MACRO_BULL_PCT", "5.0"))    # EMA gap% → MACRO_BULL
MACRO_WEAK_BULL_PCT = float(os.getenv("ORCH_MACRO_WEAK_BULL_PCT", "1.0"))
MACRO_WEAK_BEAR_PCT = float(os.getenv("ORCH_MACRO_WEAK_BEAR_PCT", "-1.0"))
MACRO_BEAR_PCT   = float(os.getenv("ORCH_MACRO_BEAR_PCT", "-5.0"))   # EMA gap% → MACRO_BEAR
TG_TOKEN         = os.getenv("TG_TOKEN", "")
TG_CHAT_ID       = os.getenv("TG_CHAT_ID", os.getenv("TG_CHAT", ""))

# ---------------------------------------------------------------------------
# Telegram helper
# ---------------------------------------------------------------------------

def _tg_send(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        return
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15):
            pass
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")

# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

def _fetch_4h(symbol: str, bars: int, *, end_ms: int | None = None, cache_only: bool = False) -> List[Dict[str, float]]:
    """Fetch last `bars` 4H klines from Bybit v5, return oldest-first list of dicts.

    Fail-safe:
      1. try fresh public data without cache
      2. if fresh fetch is rate-limited / unavailable, fall back to cached data
    """
    try:
        from backtest.bybit_data import fetch_klines_public
        end_ms = int(end_ms or int(time.time() * 1000))
        start_ms = end_ms - bars * 4 * 3600 * 1000
        common = {
            "symbol": symbol,
            "interval": "240",
            "start_ms": start_ms,
            "end_ms": end_ms,
            "polite_sleep_sec": 0.3,
            "max_retries": 3,
            "backoff_max_sec": 5.0,
        }
        if not cache_only:
            try:
                klines = fetch_klines_public(cache=False, **common)
                if klines:
                    return [{"o": k.o, "h": k.h, "l": k.l, "c": k.c, "v": k.v, "ts": k.ts} for k in klines]
            except Exception as e:
                log.warning(f"fetch_4h fresh failed for {symbol}: {e}")

        try:
            klines = fetch_klines_public(cache=True, **common)
            if klines:
                log.warning(f"fetch_4h({symbol}) used cached fallback ({len(klines)} bars)")
                return [{"o": k.o, "h": k.h, "l": k.l, "c": k.c, "v": k.v, "ts": k.ts} for k in klines]
        except Exception as e:
            log.error(f"fetch_4h cached fallback failed for {symbol}: {e}")
        cached_rows = _load_cached_lower_tf_fallback(symbol, bars, end_ms=end_ms)
        if cached_rows:
            log.warning(f"fetch_4h({symbol}) used lower-tf cache fallback ({len(cached_rows)} bars)")
            return cached_rows
    except Exception as e:
        log.error(f"fetch_4h({symbol}) failed: {e}")
        return []
    return []


def _load_cached_lower_tf_fallback(symbol: str, bars: int, *, end_ms: int | None = None) -> List[Dict[str, float]]:
    cache_dir = ROOT / "data_cache"
    if not cache_dir.exists():
        return []

    def _load_rows(path: Path) -> List[Dict[str, float]]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        out: List[Dict[str, float]] = []
        for item in raw:
            try:
                out.append(
                    {
                        "ts": int(item["ts"]),
                        "o": float(item["o"]),
                        "h": float(item["h"]),
                        "l": float(item["l"]),
                        "c": float(item["c"]),
                        "v": float(item["v"]),
                    }
                )
            except Exception:
                continue
        if end_ms is not None:
            out = [row for row in out if int(row["ts"]) < int(end_ms)]
        out.sort(key=lambda x: x["ts"])
        return out

    def _aggregate(rows: List[Dict[str, float]], target_min: int) -> List[Dict[str, float]]:
        if not rows:
            return []
        bucket_ms = target_min * 60 * 1000
        buckets: Dict[int, Dict[str, float]] = {}
        order: List[int] = []
        for row in rows:
            bucket_ts = int(row["ts"] // bucket_ms) * bucket_ms
            slot = buckets.get(bucket_ts)
            if slot is None:
                slot = {
                    "ts": bucket_ts,
                    "o": row["o"],
                    "h": row["h"],
                    "l": row["l"],
                    "c": row["c"],
                    "v": row["v"],
                }
                buckets[bucket_ts] = slot
                order.append(bucket_ts)
            else:
                slot["h"] = max(slot["h"], row["h"])
                slot["l"] = min(slot["l"], row["l"])
                slot["c"] = row["c"]
                slot["v"] += row["v"]
        return [buckets[ts] for ts in sorted(order)]

    def _merge_rows(paths: List[Path], target_bars: int, target_interval: str) -> List[Dict[str, float]]:
        merged: List[Dict[str, float]] = []
        seen_ts: set[int] = set()
        for path in sorted(paths, reverse=True):
            rows = _load_rows(path)
            if not rows:
                continue
            if target_interval != "240":
                rows = _aggregate(rows, 240)
            for row in reversed(rows):
                ts = int(row["ts"])
                if ts in seen_ts:
                    continue
                seen_ts.add(ts)
                merged.append(row)
            if len(merged) >= target_bars * 2:
                break
        merged.sort(key=lambda x: x["ts"])
        return merged[-target_bars:]

    for interval in ("240", "60", "5", "1"):
        paths = sorted(cache_dir.glob(f"{symbol}_{interval}_*.json"))
        if not paths:
            continue
        rows = _merge_rows(paths, max(60, bars), interval)
        if len(rows) >= max(60, bars):
            return rows[-bars:]
        if rows:
            return rows
    return []

def _fetch_daily(symbol: str, bars: int, *, end_ms: int | None = None) -> List[Dict[str, float]]:
    """Fetch `bars` daily (1440m) klines for macro overlay.

    Strategy:
      1. Fetch fresh 1440m klines from Bybit.
      2. On failure, aggregate from cached 4H bars (6×4H = 1 daily).
      3. On failure, return empty — macro overlay is skipped gracefully.
    """
    try:
        from backtest.bybit_data import fetch_klines_public
        end_ms = int(end_ms or int(time.time() * 1000))
        start_ms = end_ms - bars * 24 * 3600 * 1000
        try:
            klines = fetch_klines_public(
                symbol=symbol, interval="D",
                start_ms=start_ms, end_ms=end_ms,
                polite_sleep_sec=0.3, max_retries=3, backoff_max_sec=5.0,
            )
            if klines:
                return [{"o": k.o, "h": k.h, "l": k.l, "c": k.c, "v": k.v, "ts": k.ts} for k in klines]
        except Exception:
            pass
        # fallback: aggregate 4H bars into daily
        bars_4h = bars * 6 + 20  # ~6 4H bars per day + buffer
        rows_4h = _fetch_4h(symbol, bars_4h, end_ms=end_ms, cache_only=True)
        if not rows_4h:
            return []
        daily: Dict[int, Dict[str, float]] = {}
        order: List[int] = []
        day_ms = 24 * 3600 * 1000
        for r in rows_4h:
            day_ts = int(r["ts"] // day_ms) * day_ms
            slot = daily.get(day_ts)
            if slot is None:
                slot = {"ts": day_ts, "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]}
                daily[day_ts] = slot
                order.append(day_ts)
            else:
                slot["h"] = max(slot["h"], r["h"])
                slot["l"] = min(slot["l"], r["l"])
                slot["c"] = r["c"]
                slot["v"] += r["v"]
        result = [daily[ts] for ts in sorted(order)]
        return result[-bars:]
    except Exception as e:
        log.warning(f"_fetch_daily({symbol}) failed: {e}")
        return []


def _compute_macro_overlay(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """Compute weekly macro context from daily EMA50 vs EMA200.

    Returns a dict with macro_state and risk_modifier to apply on top of
    the 4H regime risk multiplier.

    Why this matters:
      - 2024: BTC daily EMA50 >> EMA200 all year → MACRO_BULL → +0.12 to risk
      - 2022: BTC daily EMA50 << EMA200 all year → MACRO_BEAR → -0.15 to risk
      - This prevents the 4H signal from being overly cautious in structural bulls
        and overly aggressive in structural bears.
    """
    candles = _fetch_daily(symbol, DAILY_BARS)
    if len(candles) < 60:
        log.warning(f"Macro overlay: only {len(candles)} daily bars — skipping (MACRO_NEUTRAL)")
        return {
            "state": "MACRO_NEUTRAL",
            "risk_modifier": 0.0,
            "ema50_daily": None,
            "ema200_daily": None,
            "gap_pct": 0.0,
            "reason": f"insufficient_data ({len(candles)} bars)",
        }

    closes = [c["c"] for c in candles]
    ema50_series  = _ema(closes, 50)
    ema200_series = _ema(closes, min(200, len(closes)))

    ema50  = ema50_series[-1]
    ema200 = ema200_series[-1]
    gap_pct = (ema50 - ema200) / max(abs(ema200), 1e-12) * 100.0

    if gap_pct >= MACRO_BULL_PCT:
        state, modifier = "MACRO_BULL", +0.12
    elif gap_pct >= MACRO_WEAK_BULL_PCT:
        state, modifier = "MACRO_WEAK_BULL", +0.06
    elif gap_pct > MACRO_WEAK_BEAR_PCT:
        state, modifier = "MACRO_NEUTRAL", 0.0
    elif gap_pct > MACRO_BEAR_PCT:
        state, modifier = "MACRO_WEAK_BEAR", -0.08
    else:
        state, modifier = "MACRO_BEAR", -0.15

    log.info(
        f"Macro overlay: {state} | daily EMA50={ema50:.1f} EMA200={ema200:.1f} "
        f"gap={gap_pct:+.2f}% → risk_modifier={modifier:+.2f}"
    )
    return {
        "state": state,
        "risk_modifier": modifier,
        "ema50_daily": round(ema50, 2),
        "ema200_daily": round(ema200, 2),
        "gap_pct": round(gap_pct, 3),
        "reason": f"daily EMA50/EMA200 gap={gap_pct:+.2f}%",
        "daily_bars_used": len(candles),
    }


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _ema(values: List[float], period: int) -> List[float]:
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1.0)
    out: List[float] = []
    e = values[0]
    out.append(e)
    for v in values[1:]:
        e = e + k * (v - e)
        out.append(e)
    return out


def _atr(candles: List[Dict], period: int) -> float:
    if len(candles) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(1, len(candles)):
        h  = candles[i]["h"]
        l  = candles[i]["l"]
        pc = candles[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    tail = trs[-period:]
    return sum(tail) / len(tail) if tail else float("nan")


def _efficiency_ratio(closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return 1.0
    start = closes[-(period + 1)]
    end   = closes[-1]
    net   = abs(end - start)
    path  = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - period, len(closes)))
    return net / path if path > 0 else 1.0


def _mixed_sign_bias(ema_gap_pct: float, close_gap_pct: float) -> Tuple[str, Dict[str, float]]:
    bull_strength = max(0.0, float(ema_gap_pct)) * MIXED_SIGN_EMA_WEIGHT + max(0.0, float(close_gap_pct)) * MIXED_SIGN_PRICE_WEIGHT
    bear_strength = max(0.0, -float(ema_gap_pct)) * MIXED_SIGN_EMA_WEIGHT + max(0.0, -float(close_gap_pct)) * MIXED_SIGN_PRICE_WEIGHT
    edge = float(bull_strength - bear_strength)
    if edge >= MIXED_SIGN_EDGE_PCT:
        bias = "bull"
    elif edge <= -MIXED_SIGN_EDGE_PCT:
        bias = "bear"
    else:
        bias = "bull" if float(close_gap_pct) >= 0.0 else "bear"
    return bias, {
        "bull_strength": round(float(bull_strength), 4),
        "bear_strength": round(float(bear_strength), 4),
        "bias_edge_pct": round(edge, 4),
    }

# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------

REGIME_BULL_TREND = "bull_trend"
REGIME_BULL_CHOP  = "bull_chop"
REGIME_BEAR_CHOP  = "bear_chop"
REGIME_BEAR_TREND = "bear_trend"

ALL_REGIMES = [REGIME_BULL_TREND, REGIME_BULL_CHOP, REGIME_BEAR_CHOP, REGIME_BEAR_TREND]


def _classify_regime(candles: List[Dict]) -> Tuple[str, Dict[str, float]]:
    """Return (regime_str, indicators_dict) from 4H BTC candles."""
    closes = [c["c"] for c in candles]

    ef_series = _ema(closes, 21)
    es_series = _ema(closes, 55)

    if not ef_series or not es_series:
        return REGIME_BEAR_CHOP, {}

    ema21 = ef_series[-1]
    ema55 = es_series[-1]
    close = closes[-1]
    atr   = _atr(candles, 14)
    er    = _efficiency_ratio(closes, ER_PERIOD)
    ema_gap_pct = ((ema21 - ema55) / ema55 * 100.0) if abs(ema55) > 1e-12 else 0.0
    close_gap_pct = ((close - ema55) / ema55 * 100.0) if abs(ema55) > 1e-12 else 0.0

    bull_ema  = ema21 > ema55
    above_55  = close > ema55
    trending  = er >= ER_TREND_THRESH
    mixed_bias = ""
    mixed_meta = {"bull_strength": 0.0, "bear_strength": 0.0, "bias_edge_pct": 0.0}

    if bull_ema and above_55:
        regime = REGIME_BULL_TREND if trending else REGIME_BULL_CHOP
    elif (not bull_ema) and (not above_55):
        regime = REGIME_BEAR_TREND if trending else REGIME_BEAR_CHOP
    else:
        mixed_bias, mixed_meta = _mixed_sign_bias(ema_gap_pct, close_gap_pct)
        if mixed_bias == "bull":
            regime = REGIME_BULL_TREND if trending and above_55 else REGIME_BULL_CHOP
        else:
            regime = REGIME_BEAR_TREND if trending and (not above_55) else REGIME_BEAR_CHOP

    indicators = {
        "ema21": round(ema21, 6),
        "ema55": round(ema55, 6),
        "close": round(close, 6),
        "atr":   round(atr, 6) if atr == atr else 0.0,
        "er":    round(er, 4),
        "ema_gap_pct": round(ema_gap_pct, 4),
        "close_vs_ema55_pct": round(close_gap_pct, 4),
        "bull_ema": int(bull_ema),
        "above_55": int(above_55),
        "trending": int(trending),
        "mixed_bias": mixed_bias,
        **mixed_meta,
    }
    return regime, indicators

# ---------------------------------------------------------------------------
# Sleeve decision table
# ---------------------------------------------------------------------------

# risk_level 1-4, global_risk_mult, sleeve states, strategy overrides
_REGIME_DECISIONS = {
    REGIME_BULL_TREND: {
        "risk_level": 1,
        "global_risk_mult": 1.00,
        "btc_bias": "long",
        "sleeves": {
            "momentum": "active", "breakout": "active", "bounce": "active",
            "mean_reversion": "off", "swing": "active", "breakdown": "off",
        },
        "overrides": {
            # Directional longs ON
            "ENABLE_BREAKOUT_TRADING":   "1",
            "BREAKOUT_ALLOW_LONGS":      "1",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_ASB1_TRADING":       "1",   # support bounce — primary bull strategy
            "ASB1_ALLOW_LONGS":          "1",
            "ASB1_ALLOW_SHORTS":         "0",
            "ENABLE_HZBO1_TRADING":      "1",   # horizontal breakout longs
            "HZBO1_ALLOW_LONGS":         "1",
            "HZBO1_ALLOW_SHORTS":        "0",
            "ENABLE_BOUNCE_TRADING":     "1",   # bounce1 — longs at support
            "ENABLE_IVB1_TRADING":       "1",   # impulse volume breakout — longs
            "ENABLE_MIDTERM_TRADING":    "1",
            "ENABLE_ATT1_TRADING":       "1",   # trendline touch longs
            # Bearish/range strategies OFF
            "ENABLE_BREAKDOWN_TRADING":  "0",
            "ENABLE_FLAT_TRADING":       "0",   # flat = range, off in trending bull
            # v7 new sleeves
            "ENABLE_BREAKDOWN2_TRADING": "0",   # SHORT breakdown — off in bull trend
            "ENABLE_SLOPE_CHOCH_TRADING":"0",   # SHORT CHOCH — off in bull trend
            "ENABLE_LC_TRADING":         "1",   # liq_cascade longs (panic dip buys)
            "LC_ALLOW_SHORTS":           "0",   # no short fades in bull trend
            "ENABLE_FR_TRADING":         "1",   # funding reversion — any regime
            "ENABLE_MSCALP_TRADING":     "1",   # micro scalper longs
            "MSCALP_ALLOW_LONGS":        "1",
            "MSCALP_ALLOW_SHORTS":       "0",
            "ORCH_REGIME":               REGIME_BULL_TREND,
        },
        "notes": [
            "BTC 4H EMA21 > EMA55, price above EMA55, ER trending",
            "Bull momentum: breakout + ASB1 + bounce + IVB1 active",
            "Bear strategies off — no shorts",
        ],
    },
    REGIME_BULL_CHOP: {
        "risk_level": 2,
        "global_risk_mult": 0.85,
        "btc_bias": "neutral",
        "sleeves": {
            "momentum": "reduced", "breakout": "reduced", "bounce": "active",
            "mean_reversion": "active", "swing": "reduced", "breakdown": "off",
        },
        "overrides": {
            # Still in bull territory but choppy — keep longs, add range strategies
            "ENABLE_BREAKOUT_TRADING":   "1",
            "BREAKOUT_ALLOW_LONGS":      "1",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_ASB1_TRADING":       "1",   # support bounce still active
            "ASB1_ALLOW_LONGS":          "1",
            "ASB1_ALLOW_SHORTS":         "0",
            "ENABLE_HZBO1_TRADING":      "1",
            "HZBO1_ALLOW_LONGS":         "1",
            "HZBO1_ALLOW_SHORTS":        "0",
            "ENABLE_BOUNCE_TRADING":     "1",
            "ENABLE_IVB1_TRADING":       "1",
            "ENABLE_MIDTERM_TRADING":    "1",
            "ENABLE_ATT1_TRADING":       "1",
            "ENABLE_FLAT_TRADING":       "1",   # flat/range strategies ON in chop
            "ENABLE_VWAP_TRADING":       "1",   # VWAP mean reversion active in chop
            # Bear strategies still off
            "ENABLE_BREAKDOWN_TRADING":  "0",
            # v7 new sleeves
            "ENABLE_BREAKDOWN2_TRADING": "0",   # SHORT — off in bull territory
            "ENABLE_SLOPE_CHOCH_TRADING":"1",   # slope CHOCH conservative — mild bear signals possible in chop
            "SRC1_ALLOW_SHORTS":         "1",
            "ENABLE_LC_TRADING":         "1",   # liq_cascade both (chop has cascade risk)
            "LC_ALLOW_SHORTS":           "1",   # allow squeeze fades in chop
            "ENABLE_FR_TRADING":         "1",   # funding reversion active
            "ENABLE_MSCALP_TRADING":     "1",   # micro scalper both sides in chop
            "MSCALP_ALLOW_LONGS":        "1",
            "MSCALP_ALLOW_SHORTS":       "1",
            "ORCH_REGIME":               REGIME_BULL_CHOP,
        },
        "notes": [
            "BTC above EMA55 but ER low — choppy bull",
            "Longs still active, range strategies added (flat, VWAP)",
            "Bear strategies off",
        ],
    },
    REGIME_BEAR_CHOP: {
        "risk_level": 3,
        "global_risk_mult": 0.70,
        "btc_bias": "short",
        "sleeves": {
            "momentum": "off", "breakout": "off", "bounce": "off",
            "mean_reversion": "active", "swing": "active", "breakdown": "reduced",
        },
        "overrides": {
            # Range + breakdown strategies; longs off (EXCEPT if MACRO_BULL overlay)
            "ENABLE_BREAKOUT_TRADING":   "0",
            "BREAKOUT_ALLOW_LONGS":      "0",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_ASB1_TRADING":       "0",   # no longs in bear chop
            "ASB1_ALLOW_LONGS":          "0",
            "ENABLE_HZBO1_TRADING":      "1",   # HZBO can do shorts
            "HZBO1_ALLOW_LONGS":         "0",
            "HZBO1_ALLOW_SHORTS":        "1",
            "ENABLE_BOUNCE_TRADING":     "0",
            "ENABLE_IVB1_TRADING":       "0",
            "ENABLE_ATT1_TRADING":       "1",   # ATT1 handles both sides
            "ENABLE_BREAKDOWN_TRADING":  "1",
            "ENABLE_FLAT_TRADING":       "1",   # flat range is best in chop
            "ENABLE_VWAP_TRADING":       "1",
            "ENABLE_MIDTERM_TRADING":    "1",
            # v7 new sleeves
            "ENABLE_BREAKDOWN2_TRADING": "1",   # improved SHORT breakdown ON in bear chop
            "ENABLE_SLOPE_CHOCH_TRADING":"1",   # CHOCH shorts active in bear chop
            "SRC1_ALLOW_SHORTS":         "1",
            "ENABLE_LC_TRADING":         "1",   # liq_cascade both sides
            "LC_ALLOW_SHORTS":           "1",
            "ENABLE_FR_TRADING":         "1",   # funding reversion active
            "ENABLE_MSCALP_TRADING":     "1",   # micro scalper both sides
            "MSCALP_ALLOW_LONGS":        "1",
            "MSCALP_ALLOW_SHORTS":       "1",
            "ORCH_REGIME":               REGIME_BEAR_CHOP,
        },
        "notes": [
            "BTC 4H below EMA55, low ER — choppy bear",
            "Range + VWAP + breakdown active; longs off",
            "Risk reduced to 0.70 base (macro modifier applied on top)",
        ],
    },
    REGIME_BEAR_TREND: {
        "risk_level": 4,
        "global_risk_mult": 0.50,
        "btc_bias": "short",
        "sleeves": {
            "momentum": "off", "breakout": "off", "bounce": "off",
            "mean_reversion": "active", "swing": "off", "breakdown": "active",
        },
        "overrides": {
            # Strong bear — only shorts and range fade strategies
            "ENABLE_BREAKOUT_TRADING":   "0",
            "BREAKOUT_ALLOW_LONGS":      "0",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_ASB1_TRADING":       "0",
            "ENABLE_HZBO1_TRADING":      "1",   # horizontal breakdown shorts
            "HZBO1_ALLOW_LONGS":         "0",
            "HZBO1_ALLOW_SHORTS":        "1",
            "ENABLE_BOUNCE_TRADING":     "0",
            "ENABLE_IVB1_TRADING":       "0",
            "ENABLE_ATT1_TRADING":       "0",   # ATT1 off in strong trend down
            "ENABLE_BREAKDOWN_TRADING":  "1",
            "ENABLE_FLAT_TRADING":       "1",   # fade bounces
            "ENABLE_VWAP_TRADING":       "1",
            "ENABLE_MIDTERM_TRADING":    "0",   # midterm longs off in bear trend
            # v7 new sleeves
            "ENABLE_BREAKDOWN2_TRADING": "1",   # improved SHORT — primary in bear trend
            "ENABLE_SLOPE_CHOCH_TRADING":"1",   # CHOCH shorts — primary in bear trend
            "SRC1_ALLOW_SHORTS":         "1",
            "ENABLE_LC_TRADING":         "1",   # liq_cascade (panic longs + squeeze shorts)
            "LC_ALLOW_SHORTS":           "1",
            "ENABLE_FR_TRADING":         "1",   # funding reversion active
            "ENABLE_MSCALP_TRADING":     "1",   # micro scalper — short-biased
            "MSCALP_ALLOW_LONGS":        "0",   # no longs in bear trend
            "MSCALP_ALLOW_SHORTS":       "1",
            "ORCH_REGIME":               REGIME_BEAR_TREND,
        },
        "notes": [
            "BTC 4H EMA21 < EMA55, price below EMA55, ER trending",
            "Strong bear: breakdown + fade only",
            "All long momentum strategies off",
        ],
    },
}


def _apply_decision_softeners(regime: str, indicators: Dict[str, Any]) -> Dict[str, Any]:
    decision = copy.deepcopy(_REGIME_DECISIONS[regime])
    softeners: List[str] = []
    er = float(indicators.get("er") or 0.0)

    # A weak bull trend can still behave like directional chop where ARF1 has edge.
    # Keep momentum active, but do not force mean-reversion fully off on borderline ER.
    if regime == REGIME_BULL_TREND and er <= BULL_TREND_FLAT_ER_MAX:
        decision["overrides"]["ENABLE_FLAT_TRADING"] = "1"
        decision["sleeves"]["mean_reversion"] = "reduced"
        decision["notes"] = list(decision.get("notes") or []) + [
            f"Weak bull trend (ER={er:.3f}) — flat re-enabled in reduced mode"
        ]
        softeners.append("weak_bull_trend_flat_on")

    decision["softeners"] = softeners
    return decision

# ---------------------------------------------------------------------------
# State persistence (for hysteresis)
# ---------------------------------------------------------------------------

def _load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Could not load prior state: {e}")
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(STATE_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, str(STATE_PATH))


def _save_env(overrides: Dict[str, str], risk_mult: float, risk_level: int) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Auto-generated by build_regime_state.py — do not edit manually",
        f"# Generated: {generated_at}",
        f"ORCH_STATE_VERSION={STATE_VERSION}",
        f"ORCH_GENERATED_AT_UTC={generated_at}",
        f"ORCH_GLOBAL_RISK_MULT={risk_mult}",
        f"ORCH_RISK_LEVEL={risk_level}",
        f"ORCH_HISTORY_PATH={HISTORY_PATH}",
    ]
    for k, v in overrides.items():
        lines.append(f"{k}={v}")
    tmp = str(ENV_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, str(ENV_PATH))


def _append_history(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")

# ---------------------------------------------------------------------------
# Main regime computation with hysteresis
# ---------------------------------------------------------------------------

def compute_and_apply(dry_run: bool = False) -> Dict[str, Any]:
    """Run one cycle. Returns the full state dict."""

    ts_utc = datetime.now(timezone.utc).isoformat()
    log.info(f"=== Regime cycle start (V2): {ts_utc} ===")

    # 1a. Fetch BTC 4H data (intermediate regime)
    candles = _fetch_4h("BTCUSDT", FETCH_BARS)
    if len(candles) < 60:
        log.error(f"Insufficient BTC 4H data ({len(candles)} bars). Skipping cycle.")
        return {}

    # 1b. Compute daily macro overlay (structural bull/bear context)
    macro = _compute_macro_overlay("BTCUSDT")
    log.info(f"Macro overlay: {macro['state']} | gap={macro.get('gap_pct',0):+.2f}% risk_mod={macro.get('risk_modifier',0):+.2f}")

    # 2. Classify raw 4H regime
    raw_regime, indicators = _classify_regime(candles)
    # Attach macro info to indicators for reporting
    indicators["macro_state"] = macro["state"]
    indicators["macro_risk_modifier"] = macro.get("risk_modifier", 0.0)
    indicators["macro_gap_pct"] = macro.get("gap_pct", 0.0)
    indicators["daily_ema50"] = macro.get("ema50_daily")
    indicators["daily_ema200"] = macro.get("ema200_daily")
    log.info(f"Raw 4H regime: {raw_regime} | EMA21={indicators.get('ema21')} EMA55={indicators.get('ema55')} ER={indicators.get('er')}")

    # 3. Load prior state for hysteresis
    prior = _load_state()
    applied_regime = prior.get("regime", raw_regime)
    pending_regime = prior.get("pending_regime", raw_regime)
    pending_count  = int(prior.get("pending_count", 0))

    # 4. Hysteresis logic
    if raw_regime == applied_regime:
        # Same as current applied — reset pending
        pending_regime = raw_regime
        pending_count  = 0
        new_regime     = applied_regime
        regime_changed = False
    elif raw_regime == pending_regime:
        # Continuing to disagree with applied — increment counter
        pending_count += 1
        log.info(f"Pending regime '{pending_regime}' — hold cycle {pending_count}/{MIN_HOLD_CYCLES}")
        if pending_count >= MIN_HOLD_CYCLES:
            new_regime     = pending_regime
            regime_changed = (new_regime != applied_regime)
            pending_count  = 0
            log.info(f"Hysteresis satisfied → applying '{new_regime}'")
        else:
            new_regime     = applied_regime   # keep current until threshold met
            regime_changed = False
    else:
        # New different pending regime — start fresh counter
        pending_regime = raw_regime
        pending_count  = 1
        new_regime     = applied_regime   # keep current
        regime_changed = False
        log.info(f"New pending regime '{pending_regime}' started (1/{MIN_HOLD_CYCLES})")

    # 5. Build decision
    decision = _apply_decision_softeners(new_regime, indicators)

    # Apply macro overlay to global risk multiplier
    # Example: bear_chop 0.70 + MACRO_BULL +0.12 = 0.82 (less cautious during structural bull year)
    # Example: bull_chop 0.85 + MACRO_BEAR -0.15 = 0.70 (more cautious during structural bear year)
    base_risk = decision["global_risk_mult"]
    macro_modifier = macro.get("risk_modifier", 0.0)
    macro_adjusted_risk = round(max(0.30, min(1.15, base_risk + macro_modifier)), 3)
    decision["global_risk_mult"] = macro_adjusted_risk
    decision["notes"] = list(decision.get("notes") or []) + [
        f"Macro overlay: {macro['state']} → risk {base_risk:.2f}{macro_modifier:+.2f} = {macro_adjusted_risk:.2f}"
    ]
    log.info(f"Risk: base={base_risk:.2f} macro_mod={macro_modifier:+.2f} → final={macro_adjusted_risk:.2f}")

    overrides = decision["overrides"].copy()
    overrides["ORCH_CONFIDENCE"] = str(round(indicators.get("er", 0.5), 3))
    overrides["ORCH_RAW_REGIME"] = raw_regime
    overrides["ORCH_MACRO_STATE"] = macro["state"]
    overrides["ORCH_MACRO_RISK_MOD"] = str(macro_modifier)
    overrides["ORCH_PENDING_REGIME"] = pending_regime
    overrides["ORCH_PENDING_COUNT"] = str(pending_count)
    overrides["ORCH_GENERATED_AT_UTC"] = ts_utc
    overrides["ORCH_STATE_VERSION"] = STATE_VERSION

    # 6. Write outputs
    state: Dict[str, Any] = {
        "version":         STATE_VERSION,
        "timestamp_utc":   ts_utc,
        "regime":          new_regime,
        "raw_regime":      raw_regime,
        "pending_regime":  pending_regime,
        "pending_count":   pending_count,
        "regime_changed":  regime_changed,
        "previous_regime": applied_regime,
        "confidence":      round(indicators.get("er", 0.5), 3),
        "btc_bias":        decision["btc_bias"],
        "risk_level":      decision["risk_level"],
        "global_risk_mult": decision["global_risk_mult"],
        "global_risk_base": base_risk,
        "macro":           macro,
        "sleeves":         decision["sleeves"],
        "softeners":       decision.get("softeners", []),
        "strategy_overrides": overrides,
        "indicators":      indicators,
        "notes":           decision["notes"],
        "state_path":      str(STATE_PATH),
        "overlay_path":    str(ENV_PATH),
        "history_path":    str(HISTORY_PATH),
    }

    if not dry_run:
        _save_state(state)
        _save_env(overrides, decision["global_risk_mult"], decision["risk_level"])
        _append_history(HISTORY_PATH, state)
        log.info(f"State written → {STATE_PATH}")
        log.info(f"Env overlay  → {ENV_PATH}")
        log.info(f"History      → {HISTORY_PATH}")
    else:
        log.info("[DRY RUN] Would write:")
        log.info(json.dumps(state, indent=2))

    # 7. Telegram alert on regime change
    if regime_changed and not dry_run:
        old = prior.get("regime", "unknown")
        sleeve_summary = " | ".join(f"{k}:{v}" for k, v in decision["sleeves"].items())
        msg = (
            f"🔄 <b>Regime changed</b>: {old} → <b>{new_regime}</b>\n"
            f"Risk: ×{decision['global_risk_mult']} (level {decision['risk_level']})\n"
            f"Macro: {macro['state']} (EMA50/200 gap={macro.get('gap_pct',0):+.1f}%)\n"
            f"Sleeves: {sleeve_summary}\n"
            f"4H: EMA21={indicators.get('ema21')} EMA55={indicators.get('ema55')} ER={indicators.get('er')}"
        )
        _tg_send(TG_TOKEN, TG_CHAT_ID, msg)
        log.info(f"REGIME CHANGE: {old} → {new_regime}")

    log.info(f"Applied regime: {new_regime} | risk×{decision['global_risk_mult']} | "
             f"sleeves: {decision['sleeves']}")
    return state


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Regime Orchestrator V1")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print state without writing files or sending Telegram")
    parser.add_argument("--loop", type=int, default=0, metavar="SECONDS",
                        help="Run continuously every N seconds (0 = one-shot)")
    args = parser.parse_args()

    if args.loop > 0:
        log.info(f"Loop mode: running every {args.loop}s")
        while True:
            try:
                compute_and_apply(dry_run=args.dry_run)
            except Exception as e:
                log.error(f"Cycle error (will retry): {e}", exc_info=True)
            time.sleep(args.loop)
    else:
        try:
            state = compute_and_apply(dry_run=args.dry_run)
            if state:
                print(json.dumps(state, indent=2))
        except Exception as e:
            log.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
