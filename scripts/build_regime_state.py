#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_regime_state.py — Live Regime Orchestrator (V1)

Classifies the current market regime and writes:
  1. runtime/regime/orchestrator_state.json  — full machine-readable state
  2. configs/regime_orchestrator_latest.env  — env overlay for live bot

Regimes (4):
  bull_trend   BTC 4H EMA21 > EMA55, close > EMA55, ER > threshold
  bull_chop    BTC above EMA55 but low ER (choppy)
  bear_chop    BTC 4H EMA21 < EMA55 but low ER (drift/chop)
  bear_trend   BTC 4H EMA21 < EMA55, close < EMA55, ER > threshold

Hysteresis (anti-flicker):
  A new regime is only applied after min_regime_hold_cycles consecutive
  re-computations agree (default 3). Prevents thrashing at regime boundaries.

Sleeve decision table:
  bull_trend  → breakout ON,  breakdown OFF, fade OFF, swing ON,  risk 1.00
  bull_chop   → breakout RED, breakdown OFF, fade ON,  swing RED, risk 0.85
  bear_chop   → breakout OFF, breakdown RED, fade ON,  swing ON,  risk 0.70
  bear_trend  → breakout OFF, breakdown ON,  fade ON,  swing OFF, risk 0.50

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
  ORCH_ER_TREND_THRESH     ER threshold for "trending" (default 0.35)
  ORCH_BARS                4H bars to fetch (default 120 = ~20 days)
"""

from __future__ import annotations

import argparse
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
STATE_VERSION = "1"

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
ER_TREND_THRESH  = float(os.getenv("ORCH_ER_TREND_THRESH", "0.35"))
FETCH_BARS       = int(os.getenv("ORCH_BARS", "120"))
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
    er    = _efficiency_ratio(closes, 20)

    bull_ema  = ema21 > ema55
    above_55  = close > ema55
    trending  = er >= ER_TREND_THRESH

    if bull_ema and above_55 and trending:
        regime = REGIME_BULL_TREND
    elif bull_ema or above_55:
        regime = REGIME_BULL_CHOP
    elif trending:           # bearish + trending
        regime = REGIME_BEAR_TREND
    else:                    # bearish + choppy
        regime = REGIME_BEAR_CHOP

    indicators = {
        "ema21": round(ema21, 6),
        "ema55": round(ema55, 6),
        "close": round(close, 6),
        "atr":   round(atr, 6) if atr == atr else 0.0,
        "er":    round(er, 4),
        "bull_ema": int(bull_ema),
        "above_55": int(above_55),
        "trending": int(trending),
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
        "sleeves": {"momentum": "active", "mean_reversion": "off", "swing": "active"},
        "overrides": {
            "ENABLE_BREAKOUT_TRADING":   "1",
            "BREAKOUT_ALLOW_LONGS":      "1",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_BREAKDOWN_TRADING":  "0",
            "ENABLE_FLAT_TRADING":       "0",
            "ENABLE_MIDTERM_TRADING":    "1",
            "ORCH_REGIME":               REGIME_BULL_TREND,
        },
        "notes": ["BTC 4H EMA21 > EMA55", "price above EMA55", "ER trending — momentum mode active"],
    },
    REGIME_BULL_CHOP: {
        "risk_level": 2,
        "global_risk_mult": 0.85,
        "btc_bias": "neutral",
        "sleeves": {"momentum": "reduced", "mean_reversion": "active", "swing": "reduced"},
        "overrides": {
            "ENABLE_BREAKOUT_TRADING":   "1",
            "BREAKOUT_ALLOW_LONGS":      "1",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_BREAKDOWN_TRADING":  "0",
            "ENABLE_FLAT_TRADING":       "1",
            "ENABLE_MIDTERM_TRADING":    "1",
            "ORCH_REGIME":               REGIME_BULL_CHOP,
        },
        "notes": ["BTC still above EMA55 but ER low", "choppy — reduce momentum, activate fade"],
    },
    REGIME_BEAR_CHOP: {
        "risk_level": 3,
        "global_risk_mult": 0.70,
        "btc_bias": "short",
        "sleeves": {"momentum": "off", "mean_reversion": "active", "swing": "active"},
        "overrides": {
            "ENABLE_BREAKOUT_TRADING":   "0",
            "BREAKOUT_ALLOW_LONGS":      "0",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_BREAKDOWN_TRADING":  "1",
            "ENABLE_FLAT_TRADING":       "1",
            "ENABLE_MIDTERM_TRADING":    "1",
            "ORCH_REGIME":               REGIME_BEAR_CHOP,
        },
        "notes": ["BTC 4H EMA21 < EMA55", "low ER — choppy bear", "longs off, breakdown reduced, fade on"],
    },
    REGIME_BEAR_TREND: {
        "risk_level": 4,
        "global_risk_mult": 0.50,
        "btc_bias": "short",
        "sleeves": {"momentum": "off", "mean_reversion": "active", "swing": "off"},
        "overrides": {
            "ENABLE_BREAKOUT_TRADING":   "0",
            "BREAKOUT_ALLOW_LONGS":      "0",
            "BREAKOUT_ALLOW_SHORTS":     "0",
            "ENABLE_BREAKDOWN_TRADING":  "1",
            "ENABLE_FLAT_TRADING":       "1",
            "ENABLE_MIDTERM_TRADING":    "0",
            "ORCH_REGIME":               REGIME_BEAR_TREND,
        },
        "notes": ["BTC 4H EMA21 < EMA55", "price below EMA55", "strong bear — breakdown + fade only"],
    },
}

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
    log.info(f"=== Regime cycle start: {ts_utc} ===")

    # 1. Fetch BTC 4H data
    candles = _fetch_4h("BTCUSDT", FETCH_BARS)
    if len(candles) < 60:
        log.error(f"Insufficient BTC 4H data ({len(candles)} bars). Skipping cycle.")
        return {}

    # 2. Classify raw regime
    raw_regime, indicators = _classify_regime(candles)
    log.info(f"Raw regime: {raw_regime} | EMA21={indicators.get('ema21')} EMA55={indicators.get('ema55')} ER={indicators.get('er')}")

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
    decision = _REGIME_DECISIONS[new_regime]
    overrides = decision["overrides"].copy()
    overrides["ORCH_CONFIDENCE"] = str(round(indicators.get("er", 0.5), 3))
    overrides["ORCH_RAW_REGIME"] = raw_regime
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
        "sleeves":         decision["sleeves"],
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
            f"Sleeves: {sleeve_summary}\n"
            f"EMA21={indicators.get('ema21')} EMA55={indicators.get('ema55')} ER={indicators.get('er')}"
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
