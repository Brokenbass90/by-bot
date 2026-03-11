from __future__ import annotations

"""
Bollinger Band Mean Reversion V2
=================================
Fixes V1's core flaw: TP=midline with tight bands creates 0.5:1 RR.

Key improvements over V1:
  1. Minimum RR gate: only enter if (TP - entry) >= rr_min × (entry - SL)
     → enforces at least 1.2:1 reward/risk on every trade
  2. Stricter RSI gate: < 30 long / > 70 short (not 40/60)
     → only enter at genuine extremes, not mild dips
  3. Wider minimum band: 20 pips (was 8)
     → ensures TP (midline) is a realistic distance away
  4. Same regime filter: ATR below 50-bar avg × mult
     → don't trade during trending conditions
  5. Optional: partial TP at midline, extend to other band (not used by default)

Expected outcome:
  - Fewer trades (stricter entry)
  - Higher WR (catching extremes only)
  - Positive EV because (TP - entry) >= 1.2 × risk

Best for: EURUSD sideways months (Apr–Jul 2025 pattern)
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
    # RSI gate — stricter than V1
    rsi_period: int = 14
    rsi_long_max: float = 32.0    # only buy genuine oversold (was 42)
    rsi_short_min: float = 68.0   # only sell genuine overbought (was 58)
    # Range regime filter
    atr_regime_bars: int = 50
    atr_regime_mult: float = 0.90  # slightly looser to catch more months
    # SL placement
    sl_atr_mult: float = 1.2       # tighter SL (was 1.5)
    # Minimum RR enforcement: only enter if reward >= rr_min × risk
    rr_min: float = 1.2
    # Minimum band width in pips (wider than V1's 8)
    min_band_width_pips: float = 20.0
    pip_size: float = 0.0001
    # Session filter
    session_start_utc: int = 7
    session_end_utc: int = 20
    # Cooldown
    cooldown_bars: int = 24   # 2H cooldown (was 3H)
    # Max ATR pips absolute (avoid entering extreme volatility)
    max_atr_pips: float = 25.0


class BBMeanReversionV2:
    """Bollinger Band mean-reversion for ranging markets — RR-enforced version."""

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

        # ── Absolute ATR cap (too volatile = skip) ─────────────────
        ps = self.cfg.pip_size
        atr_pips = a_cur / max(ps, 1e-12)
        if atr_pips > self.cfg.max_atr_pips:
            return None

        # ── ATR regime: is market flat? ─────────────────────────────
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

        if a_cur > atr_avg * self.cfg.atr_regime_mult:
            return None   # trending — skip

        # ── Bollinger Bands ─────────────────────────────────────────
        mid, upper, lower = _bollinger(closes, self.cfg.bb_period, self.cfg.bb_std)
        if not all(v == v for v in [mid, upper, lower]):
            return None

        band_width_pips = (upper - lower) / max(ps, 1e-12)
        if band_width_pips < self.cfg.min_band_width_pips:
            return None   # bands too tight

        # ── RSI ─────────────────────────────────────────────────────
        r = rsi(closes[-30:], self.cfg.rsi_period)
        if not (r == r):
            return None

        close = c.c
        prev  = candles[i - 1]

        # ── Long: prev bar touched lower band, RSI deeply oversold,
        #          current close back above lower band ──────────────
        if (prev.l <= lower and
                close > lower and
                r <= self.cfg.rsi_long_max):
            sl   = lower - self.cfg.sl_atr_mult * a_cur
            tp   = mid   # target = midline
            risk = close - sl
            reward = tp - close
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="long", entry=close, sl=sl, tp=tp,
                              reason="bb2_rev_long")

        # ── Short: prev bar touched upper band, RSI deeply overbought,
        #           current close back below upper band ───────────────
        if (prev.h >= upper and
                close < upper and
                r >= self.cfg.rsi_short_min):
            sl     = upper + self.cfg.sl_atr_mult * a_cur
            tp     = mid
            risk   = sl - close
            reward = close - tp
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="short", entry=close, sl=sl, tp=tp,
                              reason="bb2_rev_short")

        return None
