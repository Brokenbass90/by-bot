"""
Bollinger Band Mean Reversion V2+ (V2 Plus)
============================================
Extends V2 with a **touch-quality filter** on the band-touch candle.

Why V2 still has losing months
-------------------------------
V2 checks: prev.l <= lower AND close > lower AND RSI <= 32
The prev bar just needs its LOW at the band — its CLOSE could be anywhere.
This means V2 sometimes enters when the band-touch bar was a full bearish
candle that closed at the band (i.e. NOT a rejection — a continuation).

V2+ adds three checks on the touch bar (prev candle):
  1. WICK REJECTION — the bar must have a meaningful lower wick
     (min_wick_frac × bar_range below the body)
  2. CLOSE POSITION — prev bar's close must be in the upper portion
     of its range (close_vs_range >= 0.35 = close not stuck at the low)
  3. CURRENT RECLAIM — current close must be at least reclaim_atr × ATR
     above the lower band (not just barely above it)

These three filters together catch the "real bounce" vs "candle closing at
band before continuing down".

Expected vs V2:
  - Trade count: -20 to -30% (stricter filter)
  - Win rate:    +5 to +10 percentage points
  - Losing months: fewer — mostly months where there are 0 signals anyway

Universalisation notes
----------------------
All thresholds are ATR-normalised → same parameters work on:
  EURUSD M5, USDJPY M5, BTCUSDT M5, ETHUSDT M5, AAPL H1, etc.
Only `pip_size` and `min_band_width_pips` need asset-specific values.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import List, Optional

from forex.indicators import atr, rsi
from forex.touch_quality import touch_quality
from forex.types import Candle, Signal


def _bollinger(closes: List[float], period: int = 20, std_mult: float = 2.0):
    if len(closes) < period:
        return float("nan"), float("nan"), float("nan")
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((v - mid) ** 2 for v in window) / period
    std = sqrt(max(0.0, variance))
    return mid, mid + std_mult * std, mid - std_mult * std


@dataclass
class Config:
    # ── Bollinger ──────────────────────────────────────────────────
    bb_period: int = 20
    bb_std: float = 2.0

    # ── RSI gate (strict — same as V2) ────────────────────────────
    rsi_period: int = 14
    rsi_long_max: float = 32.0
    rsi_short_min: float = 68.0

    # ── ATR regime filter (same as V2) ────────────────────────────
    atr_regime_bars: int = 50
    atr_regime_mult: float = 0.90

    # ── SL / RR (same as V2) ──────────────────────────────────────
    sl_atr_mult: float = 1.2
    rr_min: float = 1.2
    min_band_width_pips: float = 20.0
    pip_size: float = 0.0001
    max_atr_pips: float = 25.0

    # ── Session ───────────────────────────────────────────────────
    session_start_utc: int = 7
    session_end_utc: int = 20

    # ── Cooldown ──────────────────────────────────────────────────
    cooldown_bars: int = 24

    # ── V2+ Touch Quality additions ───────────────────────────────
    # TQ score of the band-touch bar must exceed this threshold
    # 0.0 = off (same as V2), 0.35 = moderate, 0.50 = strict
    min_touch_quality: float = 0.0   # off by default — wick filter removed (hurts more than helps)

    # Lower wick must be at least this fraction of bar range
    min_wick_frac: float = 0.0        # off by default

    # Prev bar close position check
    min_close_vs_range: float = 0.0   # off by default

    # Current bar reclaim above band
    reclaim_atr: float = 0.0          # off by default

    # ── V2+ Macro drift filter (KEY improvement) ──────────────────
    # Blocks entries when price is in a slow directional drift
    # even if ATR is low (trending slowly = still a trend)
    #
    # Method: compare SMA(drift_sma_bars) now vs drift_lookback bars ago.
    # If it moved more than drift_max_pct of current price → skip.
    # Calibrated: 0.5% over 100 bars on EURUSD M5 = 50 pips in 8 hours
    drift_sma_bars: int = 100          # length of SMA for drift detection
    drift_lookback: int = 80           # compare now vs N bars ago
    drift_max_pct: float = 0.55        # max allowed SMA drift in %
                                       # 0.55% on EUR = ~55 pips over 80×5m ≈ 6.7h


class BBMeanReversionV2P:
    """BB mean-reversion V2 with touch-quality filter."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown: int = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        return self.cfg.session_start_utc <= h < self.cfg.session_end_utc

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        need = max(
            self.cfg.bb_period + self.cfg.atr_regime_bars + 20,
            self.cfg.drift_sma_bars + self.cfg.drift_lookback,
        )
        if i < need:
            return None

        c = candles[i]
        if not self._in_session(c.ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        window = candles[i - need: i + 1]
        closes = [x.c for x in window]
        highs  = [x.h for x in window]
        lows   = [x.l for x in window]

        # ── ATR ────────────────────────────────────────────────────
        a_cur = atr(highs[-30:], lows[-30:], closes[-30:], 14)
        if not (a_cur == a_cur and a_cur > 0):
            return None

        ps = self.cfg.pip_size
        if a_cur / max(ps, 1e-12) > self.cfg.max_atr_pips:
            return None

        # ── ATR regime ─────────────────────────────────────────────
        atr_vals = []
        step = max(1, self.cfg.atr_regime_bars // 10)
        for k in range(-self.cfg.atr_regime_bars, 0, step):
            wh = highs[k - 15: k + 1] if len(highs) > abs(k) + 15 else highs[:k+1]
            wl = lows[k - 15: k + 1]  if len(lows)  > abs(k) + 15 else lows[:k+1]
            wc = closes[k - 15: k + 1] if len(closes) > abs(k) + 15 else closes[:k+1]
            a = atr(wh, wl, wc, 14)
            if a == a and a > 0:
                atr_vals.append(a)
        if not atr_vals:
            return None
        atr_avg = sum(atr_vals) / len(atr_vals)
        if a_cur > atr_avg * self.cfg.atr_regime_mult:
            return None

        # ── Macro drift filter (V2+ key improvement) ────────────────
        # Catches slow directional moves that ATR regime misses:
        # price drifts quietly for hours → ATR stays "low" → regime passes
        # → but every BB touch just keeps going, not reverting.
        # Fix: if SMA(drift_sma_bars) moved more than drift_max_pct% over
        # the last drift_lookback bars, we are in a slow trend → skip.
        if self.cfg.drift_max_pct > 0:
            need_drift = self.cfg.drift_sma_bars + self.cfg.drift_lookback
            if len(closes) >= need_drift:
                sma_now  = sum(closes[-self.cfg.drift_sma_bars:]) / self.cfg.drift_sma_bars
                sma_then = sum(
                    closes[-self.cfg.drift_sma_bars - self.cfg.drift_lookback:
                           -self.cfg.drift_lookback]
                ) / self.cfg.drift_sma_bars
                drift_pct = abs(sma_now - sma_then) / max(sma_then, 1e-9) * 100.0
                if drift_pct > self.cfg.drift_max_pct:
                    return None  # slow trend detected — skip mean reversion

        # ── Bollinger Bands ─────────────────────────────────────────
        mid, upper, lower = _bollinger(closes, self.cfg.bb_period, self.cfg.bb_std)
        if not all(v == v for v in [mid, upper, lower]):
            return None
        if (upper - lower) / max(ps, 1e-12) < self.cfg.min_band_width_pips:
            return None

        # ── RSI ─────────────────────────────────────────────────────
        r = rsi(closes[-30:], self.cfg.rsi_period)
        if not (r == r):
            return None

        close = c.c
        prev  = candles[i - 1]
        bar_range = prev.h - prev.l

        # ────────────────────────────────────────────────────────────
        # LONG: prev bar touched lower band + current reclaims
        # ────────────────────────────────────────────────────────────
        if (prev.l <= lower and
                close > lower and
                r <= self.cfg.rsi_long_max):

            # ── V2+ Check A: lower wick on touch bar ────────────────
            lower_wick = min(prev.o, prev.c) - prev.l
            wick_frac  = lower_wick / max(bar_range, 1e-9)
            if wick_frac < self.cfg.min_wick_frac:
                return None   # no rejection wick — continuation candle

            # ── V2+ Check B: prev close not stuck at the bottom ──────
            close_vs_range = (prev.c - prev.l) / max(bar_range, 1e-9)
            if close_vs_range < self.cfg.min_close_vs_range:
                return None   # prev close in bottom 30% = bearish continuation

            # ── V2+ Check C: current bar genuinely reclaimed band ────
            if (close - lower) < self.cfg.reclaim_atr * a_cur:
                return None   # barely above band — weak reclaim

            # ── V2+ Check D: TQ score on touch bar ──────────────────
            if self.cfg.min_touch_quality > 0:
                tq = touch_quality(
                    prev.o, prev.h, prev.l, prev.c,
                    line_price=lower,
                    atr=a_cur,
                    is_support=True,
                )
                if tq < self.cfg.min_touch_quality:
                    return None

            sl     = lower - self.cfg.sl_atr_mult * a_cur
            tp     = mid
            risk   = close - sl
            reward = tp - close
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="long", entry=close, sl=sl, tp=tp,
                              reason="bb2p_rev_long")

        # ────────────────────────────────────────────────────────────
        # SHORT: prev bar touched upper band + current reclaims
        # ────────────────────────────────────────────────────────────
        if (prev.h >= upper and
                close < upper and
                r >= self.cfg.rsi_short_min):

            # ── V2+ Check A: upper wick on touch bar ─────────────────
            upper_wick = prev.h - max(prev.o, prev.c)
            wick_frac  = upper_wick / max(bar_range, 1e-9)
            if wick_frac < self.cfg.min_wick_frac:
                return None

            # ── V2+ Check B: prev close not stuck at the top ──────────
            close_vs_range = (prev.h - prev.c) / max(bar_range, 1e-9)
            if close_vs_range < self.cfg.min_close_vs_range:
                return None

            # ── V2+ Check C: current bar genuinely reclaimed ──────────
            if (upper - close) < self.cfg.reclaim_atr * a_cur:
                return None

            # ── V2+ Check D: TQ score ─────────────────────────────────
            if self.cfg.min_touch_quality > 0:
                tq = touch_quality(
                    prev.o, prev.h, prev.l, prev.c,
                    line_price=upper,
                    atr=a_cur,
                    is_support=False,
                )
                if tq < self.cfg.min_touch_quality:
                    return None

            sl     = upper + self.cfg.sl_atr_mult * a_cur
            tp     = mid
            risk   = sl - close
            reward = close - tp
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="short", entry=close, sl=sl, tp=tp,
                              reason="bb2p_rev_short")

        return None
