"""Range mean-reversion (Bollinger band fade) — RMR1 (Opus 2026-06-08).

Fits CHOP / range regimes (like today's bear_chop): fade Bollinger-band extremes
back to the mean. OHLCV only. Proper ATR-based stop (NOT a tight 0.3% — that bug is
why we exist). Regime-gated: only trades when the market is ranging, not trending.

Candidate for backtest via backtest/lab + robustness (walk-forward + fee_sensitivity)
before any live wiring. signal() returns a dict mapping cleanly to TradeSignal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


@dataclass
class RMRConfig:
    bb_period: int = 20
    bb_k: float = 2.0
    rsi_period: int = 14
    rsi_os: float = 30.0
    rsi_ob: float = 70.0
    atr_period: int = 14
    sl_atr_mult: float = 1.2          # stop beyond the band, in ATRs
    tp_to_mean_frac: float = 1.0      # target = SMA (mean reversion)
    max_trend_slope_pct: float = 0.10  # reject if SMA slope steeper than this %/bar (=trend)
    min_rr: float = 1.0


def _sma(xs: Sequence[float], n: int) -> float:
    return sum(xs[-n:]) / n if len(xs) >= n else float("nan")


def _std(xs: Sequence[float], n: int) -> float:
    if len(xs) < n:
        return float("nan")
    m = _sma(xs, n)
    return math.sqrt(sum((x - m) ** 2 for x in xs[-n:]) / n)


def _rsi(c: Sequence[float], p: int) -> float:
    if len(c) < p + 1:
        return float("nan")
    g = l = 0.0
    for i in range(-p, 0):
        ch = c[i] - c[i - 1]
        g += max(0.0, ch); l += max(0.0, -ch)
    if l == 0:
        return 100.0
    rs = (g / p) / (l / p)
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(highs, lows, closes, p) -> float:
    n = len(closes)
    if n < p + 1:
        return float("nan")
    trs = []
    for i in range(n - p, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs) / len(trs)


class RangeMeanReversionV1:
    NAME = "range_mean_reversion_v1"

    def __init__(self, cfg: Optional[RMRConfig] = None):
        self.cfg = cfg or RMRConfig()
        self.last_reason = ""

    def signal(self, highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> Optional[Dict]:
        c = self.cfg
        need = max(c.bb_period, c.rsi_period, c.atr_period) + 2
        if len(closes) < need:
            self.last_reason = "history_short"; return None
        sma = _sma(closes, c.bb_period)
        sd = _std(closes, c.bb_period)
        rsi = _rsi(closes, c.rsi_period)
        atr = _atr(highs, lows, closes, c.atr_period)
        if not all(math.isfinite(x) for x in (sma, sd, rsi, atr)) or sd <= 0 or atr <= 0:
            self.last_reason = "nan"; return None
        upper = sma + c.bb_k * sd
        lower = sma - c.bb_k * sd
        price = closes[-1]
        # regime gate: SMA slope must be flat-ish (range, not trend)
        prev_sma = _sma(closes[:-1], c.bb_period)
        slope_pct = abs(sma - prev_sma) / price * 100.0 if price else 99.0
        if slope_pct > c.max_trend_slope_pct:
            self.last_reason = f"trending_{slope_pct:.3f}"; return None
        if price <= lower and rsi <= c.rsi_os:
            sl = price - c.sl_atr_mult * atr
            tp = sma  # revert to mean
            rr = (tp - price) / (price - sl) if price > sl else 0.0
            if rr < c.min_rr:
                self.last_reason = f"rr_low_{rr:.2f}"; return None
            self.last_reason = f"long_band_fade_rsi{rsi:.0f}"
            return {"side": "long", "entry": price, "sl": sl, "tp": tp, "rr": round(rr, 2), "reason": self.last_reason}
        if price >= upper and rsi >= c.rsi_ob:
            sl = price + c.sl_atr_mult * atr
            tp = sma
            rr = (price - tp) / (sl - price) if sl > price else 0.0
            if rr < c.min_rr:
                self.last_reason = f"rr_low_{rr:.2f}"; return None
            self.last_reason = f"short_band_fade_rsi{rsi:.0f}"
            return {"side": "short", "entry": price, "sl": sl, "tp": tp, "rr": round(rr, 2), "reason": self.last_reason}
        self.last_reason = "no_setup"
        return None
