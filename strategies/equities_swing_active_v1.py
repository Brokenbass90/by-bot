"""PDT-safe active swing selector for a small Alpaca account (Opus 2026-06-08).

Problem: a US equities account under $25k is capped at 3 day-trades / 5 days
(PDT rule). So "more active intraday" is regulatorily blocked at $500-1000.

Smart workaround: trade ACTIVE SWING instead of intraday — hold 2-10 days,
rotate a wider universe more often than the monthly sleeve, and never round-trip
the same name same-day. That is "more active" without tripping PDT.

Selection = blend of:
  - momentum (20d + 60d return, trend must be up: price > SMA50)
  - a pullback bonus (buy strength on a dip, not after it is overbought)
Pure stdlib, unit-tested offline. Wiring into the Alpaca bridge + real backtest
(walk-forward via backtest/robustness.py) is Codex's step before live.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class SwingConfig:
    mom_fast: int = 20
    mom_slow: int = 60
    sma_trend: int = 50
    rsi_period: int = 14
    rsi_max: float = 78.0        # skip already-overbought (chasing tops)
    rsi_pullback_lo: float = 40.0  # sweet spot: pullback within uptrend
    rsi_pullback_hi: float = 60.0
    top_n: int = 5
    max_positions: int = 4       # sized for $500-1000 (a few names, not 1)
    min_hold_days: int = 2       # PDT-safe: never same-day round trip
    w_mom: float = 0.6
    w_pullback: float = 0.4


def _sma(xs: Sequence[float], n: int) -> float:
    if len(xs) < n or n <= 0:
        return float("nan")
    return sum(xs[-n:]) / n


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _ret(closes: Sequence[float], n: int) -> float:
    if len(closes) <= n or closes[-n - 1] <= 0:
        return float("nan")
    return closes[-1] / closes[-n - 1] - 1.0


def score_symbol(closes: Sequence[float], cfg: Optional[SwingConfig] = None) -> Dict[str, float]:
    cfg = cfg or SwingConfig()
    need = max(cfg.mom_slow, cfg.sma_trend, cfg.rsi_period) + 2
    if len(closes) < need:
        return {"eligible": False, "reason": "history_short", "score": 0.0}
    price = closes[-1]
    sma = _sma(closes, cfg.sma_trend)
    rsi = _rsi(closes, cfg.rsi_period)
    mom_f = _ret(closes, cfg.mom_fast)
    mom_s = _ret(closes, cfg.mom_slow)
    if not all(math.isfinite(x) for x in (sma, rsi, mom_f, mom_s)):
        return {"eligible": False, "reason": "nan", "score": 0.0}
    trend_ok = price > sma
    if not trend_ok:
        return {"eligible": False, "reason": "below_sma", "score": 0.0, "rsi": rsi}
    if rsi >= cfg.rsi_max:
        return {"eligible": False, "reason": "overbought", "score": 0.0, "rsi": rsi}
    momentum = 0.5 * mom_f + 0.5 * mom_s          # blended momentum
    # pullback bonus: peaks when RSI sits in the [lo,hi] band (dip within uptrend)
    mid = (cfg.rsi_pullback_lo + cfg.rsi_pullback_hi) / 2.0
    half = max(1e-9, (cfg.rsi_pullback_hi - cfg.rsi_pullback_lo) / 2.0)
    pullback = max(0.0, 1.0 - abs(rsi - mid) / half)
    score = cfg.w_mom * momentum + cfg.w_pullback * (pullback * 0.05)  # scale pullback to return-units
    return {
        "eligible": True, "reason": "ok", "score": round(score, 6),
        "momentum": round(momentum, 6), "pullback": round(pullback, 4),
        "rsi": round(rsi, 2), "trend_ok": True,
    }


def select(
    universe_closes: Dict[str, Sequence[float]],
    cfg: Optional[SwingConfig] = None,
) -> List[Tuple[str, Dict[str, float]]]:
    """Return ranked [(symbol, score_dict)] of eligible names, best first, top_n."""
    cfg = cfg or SwingConfig()
    scored = []
    for sym, closes in universe_closes.items():
        s = score_symbol(closes, cfg)
        if s.get("eligible"):
            scored.append((sym, s))
    scored.sort(key=lambda kv: kv[1]["score"], reverse=True)
    return scored[: cfg.top_n]


def is_day_trade_safe(entry_ts: int, now_ts: int, min_hold_days: int = 2) -> bool:
    """True if closing now would NOT be a same-day round trip (PDT-safe)."""
    return (now_ts - entry_ts) >= min_hold_days * 86400
