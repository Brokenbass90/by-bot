from __future__ import annotations

"""
Bollinger Band Mean Reversion V3
==================================
Incremental upgrade over V2. Uses the new `forex.regime` indicators.

V2 regime filter: ATR < ATR_50bar_avg × 0.90  (single filter)
V3 regime filter: BOTH must pass:
  A) ATR < ATR_50bar_avg × atr_regime_mult  (same as V2)
  B) ADX proxy < adx_max                   (NEW: block directional momentum)

Why adding ADX catches V2's losses:
  V2 can enter in a "quiet" market that is still TRENDING slowly (e.g.,
  EURUSD drifting down from Jan-Feb 2025). ATR is low → V2 enters long.
  But ADX > 28 → trend is present → V3 skips it.

Additional improvement: body_ratio_min
  Require the reversal bar's body >= 30% of its range.
  Filters dojis and spinning tops where reversal direction is unclear.

Result target: better Sharpe, same or higher pip count vs V2.
"""

from dataclasses import dataclass
from math import sqrt
from typing import List, Optional

from forex.indicators import atr, rsi
from forex.regime import adx_proxy
from forex.types import Candle, Signal


def _bollinger(closes: List[float], period: int, std_mult: float):
    if len(closes) < period:
        return float("nan"), float("nan"), float("nan")
    w = closes[-period:]
    mid = sum(w) / period
    var = sum((v - mid) ** 2 for v in w) / period
    std = sqrt(max(0.0, var))
    return mid, mid + std_mult * std, mid - std_mult * std


@dataclass
class Config:
    # Bollinger
    bb_period: int = 20
    bb_std: float = 2.0
    # RSI
    rsi_period: int = 14
    rsi_long_max: float = 40.0   # relaxed vs V2's 32 — ADX+ATR regime does the heavy lifting
    rsi_short_min: float = 60.0  # relaxed vs V2's 68
    # Regime A: ATR ratio (same as V2)
    atr_regime_bars: int = 50
    atr_regime_mult: float = 0.90
    # Regime B: ADX proxy (NEW) — skip if directional momentum detected
    adx_period: int = 14
    adx_max: float = 40.0
    # Reversal bar body (NEW) — body must be >= this fraction of bar range
    body_ratio_min: float = 0.30
    # SL / RR
    sl_atr_mult: float = 1.2
    rr_min: float = 1.2
    # Band width in pips (same scaling as V2)
    min_band_width_pips: float = 20.0
    pip_size: float = 0.0001
    max_atr_pips: float = 25.0
    # Session
    session_start_utc: int = 7
    session_end_utc: int = 20
    cooldown_bars: int = 24


class BBMeanReversionV3:
    """BB mean-reversion with ATR regime + ADX filter + body confirmation."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown: int = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        s, e = self.cfg.session_start_utc, self.cfg.session_end_utc
        return s <= h < e

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        need = max(self.cfg.bb_period, self.cfg.atr_regime_bars,
                   self.cfg.rsi_period, self.cfg.adx_period) + 30
        if i < need:
            return None

        c = candles[i]
        if not self._in_session(c.ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ps = self.cfg.pip_size
        window = candles[max(0, i - self.cfg.atr_regime_bars - 30): i + 1]
        closes = [x.c for x in window]
        highs  = [x.h for x in window]
        lows   = [x.l for x in window]

        # ── Current ATR ─────────────────────────────────────────────
        a_cur = atr(highs[-30:], lows[-30:], closes[-30:], 14)
        if not (a_cur == a_cur and a_cur > 0):
            return None

        atr_pips = a_cur / max(ps, 1e-12)
        if atr_pips > self.cfg.max_atr_pips:
            return None

        # ── Regime A: ATR ratio (identical to V2) ───────────────────
        atr_vals = []
        step = max(1, self.cfg.atr_regime_bars // 10)
        for k in range(-self.cfg.atr_regime_bars, 0, step):
            wh = highs[k - 15: k + 1] if len(highs) > abs(k) + 15 else highs[:k+1]
            wl = lows[k - 15: k + 1]  if len(lows)  > abs(k) + 15 else lows[:k+1]
            wc = closes[k - 15: k + 1] if len(closes) > abs(k) + 15 else closes[:k+1]
            a  = atr(wh, wl, wc, 14)
            if a == a and a > 0:
                atr_vals.append(a)
        if not atr_vals:
            return None
        atr_avg = sum(atr_vals) / len(atr_vals)
        if a_cur > atr_avg * self.cfg.atr_regime_mult:
            return None  # trending by ATR

        # ── Regime B: ADX proxy (NEW in V3) ─────────────────────────
        adx = adx_proxy(candles, i, self.cfg.adx_period)
        if adx == adx and adx > self.cfg.adx_max:
            return None  # directional momentum → skip

        # ── Bollinger Bands ──────────────────────────────────────────
        bb_closes = [x.c for x in candles[max(0, i - self.cfg.bb_period - 5): i + 1]]
        mid, upper, lower = _bollinger(bb_closes, self.cfg.bb_period, self.cfg.bb_std)
        if not all(v == v for v in [mid, upper, lower]):
            return None

        band_width_pips = (upper - lower) / max(ps, 1e-12)
        if band_width_pips < self.cfg.min_band_width_pips:
            return None

        # ── RSI ─────────────────────────────────────────────────────
        r = rsi(closes[-30:], self.cfg.rsi_period)
        if not (r == r):
            return None

        close = c.c
        prev  = candles[i - 1]

        # ── Long signal ─────────────────────────────────────────────
        if (prev.l <= lower and close > lower and r <= self.cfg.rsi_long_max):
            # Body confirmation (NEW in V3)
            bar_range = c.h - c.l
            if bar_range > 0:
                bar_body = abs(c.c - c.o)
                if (bar_body / bar_range) < self.cfg.body_ratio_min:
                    return None  # doji — no clear reversal

            sl = lower - self.cfg.sl_atr_mult * a_cur
            tp = mid
            risk   = close - sl
            reward = tp - close
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="long", entry=close, sl=sl, tp=tp,
                              reason="bb3_long")

        # ── Short signal ─────────────────────────────────────────────
        if (prev.h >= upper and close < upper and r >= self.cfg.rsi_short_min):
            bar_range = c.h - c.l
            if bar_range > 0:
                bar_body = abs(c.c - c.o)
                if (bar_body / bar_range) < self.cfg.body_ratio_min:
                    return None

            sl = upper + self.cfg.sl_atr_mult * a_cur
            tp = mid
            risk   = sl - close
            reward = close - tp
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="short", entry=close, sl=sl, tp=tp,
                              reason="bb3_short")

        return None
