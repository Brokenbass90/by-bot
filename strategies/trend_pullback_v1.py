"""Trend pullback — TPB1 (Opus 2026-06-08).

Fits TREND regimes (complements range_mean_reversion for chop): buy a pullback to
the fast EMA inside an established uptrend (mirror for downtrend). OHLCV only,
ATR-based stop, R-multiple target. Regime-gated to trend. Candidate for backtest
via lab + robustness before live. signal() -> dict mapping to TradeSignal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence


@dataclass
class TPBConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_long_max: float = 70.0
    rsi_short_min: float = 30.0
    pullback_atr: float = 0.6     # entry when price within this many ATR of fast EMA
    atr_period: int = 14
    sl_atr_mult: float = 1.5
    tp_rr: float = 2.0
    min_trend_slope_pct: float = 0.05  # fast EMA must slope at least this %/bar


def _ema(xs: Sequence[float], n: int) -> float:
    if len(xs) < n:
        return float("nan")
    k = 2.0 / (n + 1)
    e = sum(xs[:n]) / n
    for x in xs[n:]:
        e = x * k + e * (1 - k)
    return e


def _rsi(c: Sequence[float], p: int) -> float:
    if len(c) < p + 1:
        return float("nan")
    g = l = 0.0
    for i in range(-p, 0):
        ch = c[i] - c[i - 1]
        g += max(0.0, ch); l += max(0.0, -ch)
    if l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + (g / p) / (l / p))


def _atr(h, lo, c, p) -> float:
    n = len(c)
    if n < p + 1:
        return float("nan")
    trs = [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(n - p, n)]
    return sum(trs) / len(trs)


class TrendPullbackV1:
    NAME = "trend_pullback_v1"

    def __init__(self, cfg: Optional[TPBConfig] = None):
        self.cfg = cfg or TPBConfig()
        self.last_reason = ""

    def signal(self, highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> Optional[Dict]:
        c = self.cfg
        need = max(c.ema_slow, c.rsi_period, c.atr_period) + 3
        if len(closes) < need:
            self.last_reason = "history_short"; return None
        ef = _ema(closes, c.ema_fast)
        es = _ema(closes, c.ema_slow)
        ef_prev = _ema(closes[:-1], c.ema_fast)
        rsi = _rsi(closes, c.rsi_period)
        atr = _atr(highs, lows, closes, c.atr_period)
        if not all(math.isfinite(x) for x in (ef, es, ef_prev, rsi, atr)) or atr <= 0:
            self.last_reason = "nan"; return None
        price = closes[-1]
        slope_pct = (ef - ef_prev) / price * 100.0 if price else 0.0
        near_ema = abs(price - ef) <= c.pullback_atr * atr
        if not near_ema:
            self.last_reason = "not_at_pullback"; return None
        # uptrend pullback long
        if ef > es and slope_pct >= c.min_trend_slope_pct and rsi <= c.rsi_long_max:
            sl = price - c.sl_atr_mult * atr
            tp = price + c.tp_rr * (price - sl)
            self.last_reason = f"long_pullback_slope{slope_pct:.2f}"
            return {"side": "long", "entry": price, "sl": sl, "tp": tp, "rr": c.tp_rr, "reason": self.last_reason}
        # downtrend pullback short
        if ef < es and slope_pct <= -c.min_trend_slope_pct and rsi >= c.rsi_short_min:
            sl = price + c.sl_atr_mult * atr
            tp = price - c.tp_rr * (sl - price)
            self.last_reason = f"short_pullback_slope{slope_pct:.2f}"
            return {"side": "short", "entry": price, "sl": sl, "tp": tp, "rr": c.tp_rr, "reason": self.last_reason}
        self.last_reason = "no_setup"
        return None
