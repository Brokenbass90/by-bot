from __future__ import annotations

"""
Bollinger Band Mean Reversion V1
=================================
Designed for SIDEWAYS / RANGING markets — the complement to LOB which needs a trend.

Logic:
  1. Detect RANGE regime: ATR(14) is LOW relative to its own 50-bar average
     (flat market = ATR below its moving average)
  2. Bollinger Bands(20, 2σ) — mark the expected range
  3. Long entry: price touches lower band AND RSI(14) < 40 (oversold) AND
     next bar closes ABOVE lower band (reversal confirmation)
  4. Short entry: mirror
  5. TP = midline (SMA20) — only target the mean, not the other band
  6. SL = 1.5× ATR beyond the touched band

Why this beats "trade breakout in range":
  - Takes profit at the mean (realistic) not the other extreme
  - Regime filter prevents trading this when trend is running
  - Waits for reversal bar to confirm (avoids catching a falling knife)

Best for: EURUSD, GBPUSD, USDJPY during flat months (Aug–Sep 2025 type)
"""

from dataclasses import dataclass
from typing import List, Optional
from math import sqrt

from forex.indicators import atr, rsi
from forex.types import Candle, Signal


def _bollinger(closes: List[float], period: int = 20, std_mult: float = 2.0):
    """Returns (mid, upper, lower) for the last bar."""
    if len(closes) < period:
        return float("nan"), float("nan"), float("nan")
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((v - mid) ** 2 for v in window) / period
    std = sqrt(max(0.0, variance))
    return mid, mid + std_mult * std, mid - std_mult * std


@dataclass
class Config:
    # Bollinger params
    bb_period: int = 20
    bb_std: float = 2.0
    # RSI gate
    rsi_period: int = 14
    rsi_long_max: float = 42.0    # oversold threshold for longs
    rsi_short_min: float = 58.0   # overbought threshold for shorts
    # Range regime filter: ATR must be below its own N-bar average × multiplier
    # (detects flat market)
    atr_regime_bars: int = 50     # compare current ATR to 50-bar average
    atr_regime_mult: float = 0.85 # trade only when ATR < 85% of its average
    # SL placement
    sl_atr_mult: float = 1.5
    # TP = midline always (mean reversion target)
    # Minimum band width (avoids entering when bands are too tight)
    min_band_width_pips: float = 8.0
    pip_size: float = 0.0001
    # Session filter
    session_start_utc: int = 7
    session_end_utc: int = 20
    # Cooldown
    cooldown_bars: int = 36   # 3H cooldown


class BBMeanReversionV1:
    """Bollinger Band mean-reversion for ranging markets."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown: int = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        return self.cfg.session_start_utc <= h < self.cfg.session_end_utc

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        need = self.cfg.bb_period + self.cfg.atr_regime_bars + 20
        if i < need:
            return None

        c = candles[i]
        if not self._in_session(c.ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # ── Slice windows ──────────────────────────────────────────
        window = candles[i - need: i + 1]
        closes = [x.c for x in window]
        highs  = [x.h for x in window]
        lows   = [x.l for x in window]

        # ── Current ATR ────────────────────────────────────────────
        a_cur = atr(highs[-30:], lows[-30:], closes[-30:], 14)
        if not (a_cur == a_cur and a_cur > 0):
            return None

        # ── ATR regime: is market flat? ────────────────────────────
        # Compute average ATR over last atr_regime_bars bars
        atr_vals = []
        step = max(1, self.cfg.atr_regime_bars // 10)
        for k in range(-self.cfg.atr_regime_bars, 0, step):
            win_h = highs[k - 15: k + 1] if len(highs) > abs(k) + 15 else highs[:k+1]
            win_l = lows[k - 15: k + 1] if len(lows) > abs(k) + 15 else lows[:k+1]
            win_c = closes[k - 15: k + 1] if len(closes) > abs(k) + 15 else closes[:k+1]
            a = atr(win_h, win_l, win_c, 14)
            if a == a and a > 0:
                atr_vals.append(a)
        if not atr_vals:
            return None
        atr_avg = sum(atr_vals) / len(atr_vals)

        # Regime check: only trade if ATR is suppressed (below average)
        if a_cur > atr_avg * self.cfg.atr_regime_mult:
            return None   # trending — skip, let LOB handle it

        # ── Bollinger Bands ────────────────────────────────────────
        mid, upper, lower = _bollinger(closes, self.cfg.bb_period, self.cfg.bb_std)
        if not all(v == v for v in [mid, upper, lower]):
            return None

        ps = self.cfg.pip_size
        band_width_pips = (upper - lower) / max(ps, 1e-12)
        if band_width_pips < self.cfg.min_band_width_pips:
            return None   # bands too tight, no meaningful range

        # ── RSI ────────────────────────────────────────────────────
        r = rsi(closes[-30:], self.cfg.rsi_period)
        if not (r == r):
            return None

        close = c.c
        prev  = candles[i - 1]

        # ── Long: price touched lower band, RSI oversold, bar closed above band ──
        if (prev.l <= lower and       # previous bar touched lower band
                close > lower and     # current close is back above lower band
                r <= self.cfg.rsi_long_max):
            sl  = lower - self.cfg.sl_atr_mult * a_cur
            tp  = mid   # target = midline
            risk = close - sl
            if risk > 0 and (tp - close) > 0:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="long", entry=close, sl=sl, tp=tp,
                              reason="bb_rev_long")

        # ── Short: price touched upper band, RSI overbought, bar closed below ──
        if (prev.h >= upper and
                close < upper and
                r >= self.cfg.rsi_short_min):
            sl  = upper + self.cfg.sl_atr_mult * a_cur
            tp  = mid
            risk = sl - close
            if risk > 0 and (close - tp) > 0:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="short", entry=close, sl=sl, tp=tp,
                              reason="bb_rev_short")

        return None
