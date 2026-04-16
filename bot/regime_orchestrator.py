"""
Regime Orchestrator v1 — portfolio-level market phase controller.

Reads 4h BTCUSDT OHLCV, computes market regime, writes runtime/regime.json.
The live bot reads that file and adjusts ALLOW_LONGS/ALLOW_SHORTS per strategy.

Design principles:
  - Rule-based, deterministic, no external API calls
  - Idempotent: safe to run every 5-15 minutes
  - Fail-safe: if data unavailable, writes NEUTRAL (no disables)
  - Decoupled: bot reads the file; orchestrator never touches bot directly

Regime states:
  BEAR_TREND   — 4h MACD hist < 0 for 3+ bars AND EMA20 < EMA50
                 → enable shorts (Elder, ASB1, HZBO1), disable IVB1 longs
  BULL_TREND   — 4h MACD hist > 0 for 3+ bars AND EMA20 > EMA50
                 → enable IVB1/Bounce longs, disable Elder/ASB1/HZBO1 shorts
  NEUTRAL/CHOP — mixed signals
                 → keep all enabled, reduce risk multiplier

Output (runtime/regime.json):
  {
    "regime": "BEAR_TREND",
    "ts_utc": "2026-04-16T10:00:00Z",
    "confidence": 0.82,
    "allow_shorts": true,
    "allow_longs": false,
    "global_risk_mult": 1.0,
    "reason": "4h MACD hist < 0 for 4 bars, EMA20 < EMA50",
    "strategy_overrides": {
      "elder_triple_screen_v2": {"allow_shorts": true, "allow_longs": false},
      "alt_slope_break_v1":     {"allow_shorts": true},
      "alt_horizontal_break_v1":{"allow_shorts": true},
      "impulse_volume_breakout_v1": {"allow_longs": false},
      "alt_support_bounce_v1":  {"allow_longs": false}
    }
  }

Usage:
  python3 bot/regime_orchestrator.py --symbol BTCUSDT --tf 240 --out runtime/regime.json
  # Or import and call compute_regime() from within the bot
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─── Indicator helpers ────────────────────────────────────────────────────────

def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _ema_series(values: List[float], period: int) -> List[float]:
    if not values or period <= 0:
        return [float("nan")] * len(values)
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def _macd_hist_series(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> List[float]:
    """Return full MACD histogram series (same length as closes)."""
    if len(closes) < slow + signal:
        return [float("nan")] * len(closes)
    fast_ema = _ema_series(closes, fast)
    slow_ema = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    # align: macd_line valid from index (slow-1), signal from (slow+signal-2)
    signal_line = _ema_series(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return hist


def _atr(rows: List[list], period: int = 14) -> float:
    if len(rows) < period + 1:
        return float("nan")
    trs = []
    for i in range(-period, 0):
        h = float(rows[i][2])
        l = float(rows[i][3])
        pc = float(rows[i - 1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)


# ─── Regime computation ───────────────────────────────────────────────────────

REGIME_BEAR = "BEAR_TREND"
REGIME_BULL = "BULL_TREND"
REGIME_NEUTRAL = "NEUTRAL"


def compute_regime(
    rows_4h: List[list],
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    ema_fast_period: int = 20,
    ema_slow_period: int = 50,
    bear_consec: int = 3,   # bars MACD hist must be negative for BEAR
    bull_consec: int = 3,   # bars MACD hist must be positive for BULL
    atr_chop_pct: float = 0.02,  # ATR/price < this → chop (no trend)
) -> Dict:
    """
    Compute market regime from 4h bars.

    Returns a dict with: regime, confidence, allow_shorts, allow_longs,
    global_risk_mult, reason, strategy_overrides.
    """
    # Default: NEUTRAL fail-safe
    result = {
        "regime": REGIME_NEUTRAL,
        "confidence": 0.0,
        "allow_shorts": True,
        "allow_longs": True,
        "global_risk_mult": 1.0,
        "reason": "insufficient data",
        "strategy_overrides": {},
    }

    needed = macd_slow + macd_signal + max(bear_consec, bull_consec) + 5
    if len(rows_4h) < needed:
        result["reason"] = f"only {len(rows_4h)} bars, need {needed}"
        return result

    closes = [float(r[4]) for r in rows_4h]
    highs  = [float(r[2]) for r in rows_4h]
    lows   = [float(r[3]) for r in rows_4h]

    # ── MACD histogram ────────────────────────────────────────────────────────
    hist_series = _macd_hist_series(closes, macd_fast, macd_slow, macd_signal)
    recent_hists = [h for h in hist_series[-(max(bear_consec, bull_consec) + 2):] if math.isfinite(h)]
    if not recent_hists:
        result["reason"] = "MACD histogram NaN"
        return result

    last_hist = recent_hists[-1]
    # Check consecutive bars
    bear_bars = sum(1 for h in recent_hists[-bear_consec:] if h < 0)
    bull_bars = sum(1 for h in recent_hists[-bull_consec:] if h > 0)
    is_bear_macd = bear_bars >= bear_consec
    is_bull_macd = bull_bars >= bull_consec

    # ── EMA trend ─────────────────────────────────────────────────────────────
    ema_fast_val = _ema(closes, ema_fast_period)
    ema_slow_val = _ema(closes, ema_slow_period)
    ema_bear = ema_fast_val < ema_slow_val
    ema_bull = ema_fast_val > ema_slow_val

    # ── ATR / chop check ─────────────────────────────────────────────────────
    atr_val = _atr(rows_4h[-50:], 14)
    price = closes[-1]
    atr_pct = atr_val / max(1e-12, price)
    is_choppy = atr_pct < atr_chop_pct and not (is_bear_macd or is_bull_macd)

    # ── Rolling returns ───────────────────────────────────────────────────────
    ret_1d  = (closes[-1] / max(1e-12, closes[-6])  - 1.0) if len(closes) >= 6  else 0.0
    ret_3d  = (closes[-1] / max(1e-12, closes[-18]) - 1.0) if len(closes) >= 18 else 0.0
    ret_7d  = (closes[-1] / max(1e-12, closes[-42]) - 1.0) if len(closes) >= 42 else 0.0

    # ── Regime decision ───────────────────────────────────────────────────────
    reasons = []
    confidence = 0.0

    if is_bear_macd and ema_bear:
        regime = REGIME_BEAR
        reasons.append(f"4h MACD hist < 0 for {bear_bars}/{bear_consec} bars")
        reasons.append(f"EMA{ema_fast_period} < EMA{ema_slow_period}")
        confidence = 0.85
        if ret_7d < -0.05:
            reasons.append(f"7d return={ret_7d*100:.1f}% (bearish)")
            confidence = 0.95
        # In strong bear: reduce short risk slightly to avoid pile-on
        global_risk = 1.0 if confidence >= 0.90 else 0.85
        result.update({
            "regime": REGIME_BEAR,
            "confidence": confidence,
            "allow_shorts": True,
            "allow_longs": False,
            "global_risk_mult": global_risk,
            "reason": " | ".join(reasons),
            "strategy_overrides": {
                "elder_triple_screen_v2":      {"ETS2_ALLOW_SHORTS": "1", "ETS2_ALLOW_LONGS": "0"},
                "alt_slope_break_v1":          {"ASB1_ALLOW_SHORTS": "1", "ASB1_ALLOW_LONGS": "0"},
                "alt_horizontal_break_v1":     {"HZBO1_ALLOW_SHORTS": "1", "HZBO1_ALLOW_LONGS": "0"},
                "impulse_volume_breakout_v1":  {"IVB1_ALLOW_LONGS": "0"},
                "alt_support_bounce_v1":       {"ASB1_ALLOW_LONGS": "0"},
            },
        })
        return result

    if is_bull_macd and ema_bull:
        regime = REGIME_BULL
        reasons.append(f"4h MACD hist > 0 for {bull_bars}/{bull_consec} bars")
        reasons.append(f"EMA{ema_fast_period} > EMA{ema_slow_period}")
        confidence = 0.80
        if ret_7d > 0.05:
            reasons.append(f"7d return={ret_7d*100:.1f}% (bullish)")
            confidence = 0.92
        global_risk = 1.0 if confidence >= 0.90 else 0.80
        result.update({
            "regime": REGIME_BULL,
            "confidence": confidence,
            "allow_shorts": False,
            "allow_longs": True,
            "global_risk_mult": global_risk,
            "reason": " | ".join(reasons),
            "strategy_overrides": {
                "elder_triple_screen_v2":      {"ETS2_ALLOW_SHORTS": "0", "ETS2_ALLOW_LONGS": "1"},
                "alt_slope_break_v1":          {"ASB1_ALLOW_SHORTS": "0", "ASB1_ALLOW_LONGS": "1"},
                "alt_horizontal_break_v1":     {"HZBO1_ALLOW_SHORTS": "0", "HZBO1_ALLOW_LONGS": "1"},
                "impulse_volume_breakout_v1":  {"IVB1_ALLOW_LONGS": "1"},
                "alt_support_bounce_v1":       {"ASB1_ALLOW_LONGS": "1"},
            },
        })
        return result

    # ── NEUTRAL / CHOP ────────────────────────────────────────────────────────
    reasons.append(f"mixed signals: bear_macd={is_bear_macd} bull_macd={is_bull_macd} ema_bear={ema_bear} ema_bull={ema_bull}")
    reasons.append(f"last hist={last_hist:.5f}")
    # In chop: keep all enabled but reduce global risk
    result.update({
        "regime": REGIME_NEUTRAL,
        "confidence": 0.4,
        "allow_shorts": True,
        "allow_longs": True,
        "global_risk_mult": 0.75,   # reduce risk in chop/neutral markets
        "reason": " | ".join(reasons),
        "strategy_overrides": {},
    })
    return result


# ─── File I/O ─────────────────────────────────────────────────────────────────

def write_regime(regime_dict: Dict, out_path: str, env_out_path: Optional[str] = None) -> None:
    """Write regime dict to JSON file (atomic via temp file).

    Optionally also writes an env overlay file at env_out_path that the live bot
    can hot-reload via apply_regime_overlay_if_updated().  The env file contains
    flat key=value pairs derived from strategy_overrides + ORCH_* globals.
    """
    regime_dict["ts_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    regime_dict["ts_epoch"] = int(time.time())
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(regime_dict, indent=2))
    tmp.replace(out)

    if env_out_path:
        _write_env_overlay(regime_dict, env_out_path)


def _write_env_overlay(regime_dict: Dict, env_path: str) -> None:
    """Write flat key=value env overlay from a regime dict.

    The bot's apply_regime_overlay_if_updated() reads this file and sets
    os.environ for all keys, which strategies then pick up on their next
    _load_runtime_config() call.

    Keys written:
      ORCH_REGIME          — regime name (BEAR_TREND / BULL_TREND / NEUTRAL)
      ORCH_GLOBAL_RISK_MULT — global risk multiplier
      All keys from strategy_overrides (flat merged)
    """
    lines = [
        "# Auto-generated by bot/regime_orchestrator.py — DO NOT EDIT BY HAND",
        f"# Updated: {regime_dict.get('ts_utc', '')}",
        f"# Regime: {regime_dict.get('regime', 'NEUTRAL')} "
        f"(confidence={regime_dict.get('confidence', 0.0):.2f})",
        f"# Reason: {regime_dict.get('reason', '')}",
        "",
        f"ORCH_REGIME={regime_dict.get('regime', 'NEUTRAL')}",
        f"ORCH_GLOBAL_RISK_MULT={regime_dict.get('global_risk_mult', 1.0):.4f}",
        "",
        "# Strategy-level allow_longs / allow_shorts overrides",
    ]
    overrides = regime_dict.get("strategy_overrides", {})
    for _strat, kv in overrides.items():
        for key, val in kv.items():
            lines.append(f"{key}={val}")

    env_out = Path(env_path)
    env_out.parent.mkdir(parents=True, exist_ok=True)
    tmp = env_out.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(env_out)


def read_regime(path: str = "runtime/regime.json", max_age_sec: int = 1800) -> Optional[Dict]:
    """Read regime from JSON file. Returns None if missing or stale."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        ts = int(data.get("ts_epoch", 0))
        if time.time() - ts > max_age_sec:
            return None   # stale — treat as unknown
        return data
    except Exception:
        return None


# ─── Fetch helper (uses same fetch_klines interface as the bot) ───────────────

def fetch_4h_rows(symbol: str, limit: int = 200, fetch_fn=None) -> List[list]:
    """Fetch 4h klines. Uses fetch_fn if provided (live bot integration).
    Falls back to reading local backtest cache for standalone use."""
    if fetch_fn is not None:
        return fetch_fn(symbol, "240", limit) or []

    # Standalone: try to read from backtest cache
    import glob, json as j
    pattern = f"backtest/cache/{symbol}_240_*.json"
    files = sorted(glob.glob(pattern))
    if not files:
        return []
    try:
        data = j.loads(Path(files[-1]).read_text())
        rows = data.get("rows", data) if isinstance(data, dict) else data
        return [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows[-limit:]]
    except Exception:
        return []


# ─── Standalone CLI ───────────────────────────────────────────────────────────

def _run_once(args) -> None:
    rows = fetch_4h_rows(args.symbol, limit=200)
    if not rows:
        print(f"[ORCH] ERROR: no 4h data for {args.symbol}")
        regime = {
            "regime": REGIME_NEUTRAL,
            "confidence": 0.0,
            "allow_shorts": True,
            "allow_longs": True,
            "global_risk_mult": 1.0,
            "reason": "no data — fail-safe neutral",
            "strategy_overrides": {},
        }
    else:
        regime = compute_regime(
            rows,
            bear_consec=args.bear_consec,
            bull_consec=args.bull_consec,
        )

    env_out = getattr(args, "env_out", None)
    write_regime(regime, args.out, env_out_path=env_out)
    print(f"[ORCH] {regime['regime']} (confidence={regime['confidence']:.2f})")
    print(f"[ORCH] reason: {regime['reason']}")
    print(f"[ORCH] allow_shorts={regime['allow_shorts']} allow_longs={regime['allow_longs']}")
    print(f"[ORCH] global_risk_mult={regime['global_risk_mult']}")
    print(f"[ORCH] wrote JSON → {args.out}")
    if env_out:
        print(f"[ORCH] wrote env  → {env_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regime Orchestrator v1")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--tf", default="240", help="Timeframe for MACD (default: 240=4h)")
    parser.add_argument("--out", default="runtime/regime.json",
                        help="Output JSON path (default: runtime/regime.json)")
    parser.add_argument("--env-out", default=None, dest="env_out",
                        help="Also write bot-readable env overlay to this path "
                             "(e.g. configs/regime_orchestrator_latest.env). "
                             "The live bot hot-reloads this file every REGIME_OVERLAY_RELOAD_SEC seconds.")
    parser.add_argument("--bear-consec", type=int, default=3, dest="bear_consec",
                        help="Consecutive 4h bars MACD hist < 0 for BEAR_TREND")
    parser.add_argument("--bull-consec", type=int, default=3, dest="bull_consec",
                        help="Consecutive 4h bars MACD hist > 0 for BULL_TREND")
    parser.add_argument("--loop", action="store_true",
                        help="Run in a loop every --interval seconds")
    parser.add_argument("--interval", type=int, default=900,
                        help="Seconds between updates in loop mode (default: 900=15min)")
    args = parser.parse_args()

    if args.loop:
        print(f"[ORCH] Starting loop mode (interval={args.interval}s)")
        while True:
            try:
                _run_once(args)
            except Exception as e:
                print(f"[ORCH] ERROR: {e}")
            time.sleep(args.interval)
    else:
        _run_once(args)
