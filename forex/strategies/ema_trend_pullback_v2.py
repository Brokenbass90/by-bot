from __future__ import annotations

"""
EMA Trend Pullback V2
=====================
Multi-timeframe trend-following pullback using only M5 candle data.

Trend direction comes from "H1-equivalent" EMAs computed over many M5 bars:
  - EMA_FAST = EMA(240)  ≈ EMA(20) on H1 bars  (20H × 12 bars = 240 M5 bars)
  - EMA_SLOW = EMA(600)  ≈ EMA(50) on H1 bars  (50H × 12 bars = 600 M5 bars)

Long setup (all required):
  1. Trend: EMA_FAST > EMA_SLOW  (H1 uptrend)
  2. Trend slope: EMA_SLOW higher than 50 bars ago (macro direction positive)
  3. Session: 07:00–17:00 UTC (London + NY only)
  4. ATR elevated: ATR(14) ≥ min_atr_pips (active market)
  5. Pullback: low of last 3 bars touched EMA_FAST zone (± 0.4 ATR)
  6. Reversal bar: current M5 bar is bullish (close > open) AND body ≥ 30% of range
  7. RSI(14) ≤ 55 in last 2 bars (confirming we came from oversold zone)
  8. Price not extended: close ≤ EMA_FAST + 1.5 ATR (don't chase)
  SL: 1.5 ATR below the EMA_FAST
  TP: 2.5 × risk
  Cooldown: 48 bars (4H) after any trade

Short setup: mirror.

Why this beats V1:
  - EMA_SLOW(600) gives a much longer-term trend anchor than EMA(200) on M5
  - Requires actual pullback confirmation (not just "above EMA")
  - RSI gate prevents entering mid-momentum (chasing)
  - Session filter: avoids Asian flat-market noise
  - Higher RR (2.5 vs 2.2)
"""

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema, rsi
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_fast: int = 240       # M5 bars ≈ H1 EMA20
    ema_slow: int = 600       # M5 bars ≈ H1 EMA50
    slope_lookback: int = 50  # bars to measure EMA_SLOW slope
    session_start_utc: int = 7
    session_end_utc: int = 17
    atr_period: int = 14
    min_atr_pips: float = 3.0
    pullback_atr_zone: float = 0.5    # touch EMA_FAST within this many ATR
    max_extension_atr: float = 1.5    # don't enter if close > EMA_FAST + this
    min_body_ratio: float = 0.30      # reversal bar must have body ≥ 30% of range
    rsi_period: int = 14
    rsi_long_max: float = 55.0        # RSI must be ≤ 55 during pullback (longs)
    rsi_short_min: float = 45.0       # RSI must be ≥ 45 during pullback (shorts)
    sl_atr_mult: float = 1.5
    rr: float = 2.5
    cooldown_bars: int = 48
    pip_size: float = 0.0001


class EmaTrendPullbackV2:
    """H1-equivalent trend-following pullback entry at M5 resolution."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown: int = 0

    def _utc_hour(self, ts: int) -> int:
        return (ts // 3600) % 24

    def _in_session(self, ts: int) -> bool:
        h = self._utc_hour(ts)
        return self.cfg.session_start_utc <= h < self.cfg.session_end_utc

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        warmup = self.cfg.ema_slow + self.cfg.slope_lookback + 20
        if i < warmup:
            return None

        c = candles[i]
        if not self._in_session(c.ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # ── Pre-compute arrays ─────────────────────────────────────────
        closes = [x.c for x in candles[: i + 1]]
        highs  = [x.h for x in candles[: i + 1]]
        lows   = [x.l for x in candles[: i + 1]]

        # Trim to needed length for efficiency
        need = self.cfg.ema_slow + self.cfg.slope_lookback + 10
        cls = closes[-need:]
        hhs = highs[-need:]
        lls = lows[-need:]

        ef = ema(cls, self.cfg.ema_fast)
        es = ema(cls, self.cfg.ema_slow)
        # Slope: compare current EMA_SLOW vs value computed slope_lookback bars ago
        es_prev = ema(cls[: -self.cfg.slope_lookback], self.cfg.ema_slow)

        a = atr(hhs, lls, cls, self.cfg.atr_period)
        r = rsi(cls[-50:], self.cfg.rsi_period)

        # NaN / validity checks
        if not all(v == v and v > 0 for v in [ef, es, a]):
            return None

        ps = self.cfg.pip_size
        atr_pips = a / max(ps, 1e-12)
        if atr_pips < self.cfg.min_atr_pips:
            return None

        close = c.c
        body  = abs(c.c - c.o)
        rng   = c.h - c.l
        body_ratio = body / max(rng, 1e-12)

        # Check that last 3 bars had at least one low within EMA_FAST zone (long)
        # or high within EMA_FAST zone (short)
        zone = self.cfg.pullback_atr_zone * a

        # ── LONG setup ─────────────────────────────────────────────────
        if ef > es and (es_prev == es_prev and es > es_prev):
            # Trend up + EMA_SLOW rising
            # Price touched EMA_FAST zone in recent bars
            recent_lows = [candles[i - k].l for k in range(3)]
            touched_ema = any(abs(l - ef) <= zone or l < ef + zone for l in recent_lows)

            # Not over-extended above EMA_FAST
            not_extended = close <= ef + self.cfg.max_extension_atr * a

            # Reversal bar: close > open, body significant
            bull_bar = c.c > c.o and body_ratio >= self.cfg.min_body_ratio

            # RSI was in pullback territory recently
            rsi_ok = (r == r) and r <= self.cfg.rsi_long_max

            if touched_ema and not_extended and bull_bar and rsi_ok:
                sl = ef - self.cfg.sl_atr_mult * a
                risk = close - sl
                if risk > 0:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="long",
                        entry=close,
                        sl=sl,
                        tp=close + self.cfg.rr * risk,
                        reason="ema_pb_long",
                    )

        # ── SHORT setup ────────────────────────────────────────────────
        if ef < es and (es_prev == es_prev and es < es_prev):
            # Trend down + EMA_SLOW falling
            recent_highs = [candles[i - k].h for k in range(3)]
            touched_ema = any(abs(h - ef) <= zone or h > ef - zone for h in recent_highs)

            not_extended = close >= ef - self.cfg.max_extension_atr * a

            bear_bar = c.c < c.o and body_ratio >= self.cfg.min_body_ratio

            rsi_ok = (r == r) and r >= self.cfg.rsi_short_min

            if touched_ema and not_extended and bear_bar and rsi_ok:
                sl = ef + self.cfg.sl_atr_mult * a
                risk = sl - close
                if risk > 0:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="short",
                        entry=close,
                        sl=sl,
                        tp=close - self.cfg.rr * risk,
                        reason="ema_pb_short",
                    )

        return None
