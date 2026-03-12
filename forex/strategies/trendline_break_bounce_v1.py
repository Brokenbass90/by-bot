from __future__ import annotations

"""
Trendline Break & Bounce V1
============================
Programmatically draws quality trendlines from swing pivots and trades:
  A) 3rd-touch BOUNCE  — price returns to trendline for the 3rd time → reversal
  B) Confirmed BREAKOUT — price closes through trendline with momentum

Why trendlines are powerful:
  Markets follow diagonal support/resistance far more often than horizontal.
  A rising support line (higher lows) or falling resistance line (lower highs)
  represents the collective floor/ceiling of market participants.
  The 3rd touch rule: after 2 confirmed touches, the 3rd touch has ~60-70%
  probability of bouncing (more market memory = stronger reaction).

Algorithm:
  1. Swing detection: identify local highs/lows (N-bar extremes)
     A swing high = candle[i] is the highest high in candles[i-N : i+N+1]
     A swing low  = candle[i] is the lowest  low  in candles[i-N : i+N+1]

  2. Trendline construction:
     Support line:    connect the two most recent swing lows
     Resistance line: connect the two most recent swing highs
     Quality filter:  slope must be "reasonable" (not vertical, not flat)

  3. Touch counting:
     After the trendline is drawn through 2 pivots, count how many
     subsequent price bars came within `touch_pips` of the projected line
     without closing through it. Each such touch increments the touch count.

  4. Trend alignment (CRITICAL for quality):
     Use SMA(trend_sma_bars) to determine overall market direction.
     Support line bounces → ONLY trade LONG if price is above SMA
     Resistance line bounces → ONLY trade SHORT if price is below SMA
     (Breakouts: long above SMA, short below SMA — trend-aligned)

  5. Entry signals:
     BOUNCE (3rd+ touch):
       - Price approaches trendline within `touch_zone_pips`
       - RSI confirms direction (< rsi_bounce_max for long)
       - Entry: close of the touch bar
       - TP: last swing high (for long), last swing low (for short)
       - SL: other side of trendline + ATR buffer

     BREAKOUT:
       - Price closes through the trendline by at least `breakout_confirm_pips`
       - Previous bar was touching/near the trendline (no gap breakout)
       - RSI shows momentum (> 50 for bullish breakout)
       - Entry: close of the breakout bar
       - TP: range of trendline channel (measured move)
       - SL: back through the trendline

  Parameters:
    swing_window = 5       # bars each side for swing detection
    min_swing_separation = 20  # minimum bars between two line-defining pivots
    touch_zone_pips = 3.0  # within this distance = touching the line
    min_touches = 3        # minimum touches before trading bounce
    trend_sma_bars = 1440  # 5-day SMA filter
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from forex.indicators import atr, rsi
from forex.types import Candle, Signal


# ── Swing detection ─────────────────────────────────────────────────────────

def _find_swing_highs(candles: List[Candle], end: int, window: int,
                      min_count: int = 2, lookback: int = 500) -> List[int]:
    """Return indices of last `min_count` swing highs before `end`.

    Searches only the most recent `lookback` bars to keep O(lookback) per call.
    """
    start = max(window, end - lookback)
    pivots = []
    for i in range(start, end - window):
        high = candles[i].h
        if all(candles[j].h < high for j in range(i - window, i)) and \
           all(candles[j].h < high for j in range(i + 1, i + window + 1)):
            pivots.append(i)
    return pivots[-min_count:] if len(pivots) >= min_count else []


def _find_swing_lows(candles: List[Candle], end: int, window: int,
                     min_count: int = 2, lookback: int = 500) -> List[int]:
    """Return indices of last `min_count` swing lows before `end`.

    Searches only the most recent `lookback` bars to keep O(lookback) per call.
    """
    start = max(window, end - lookback)
    pivots = []
    for i in range(start, end - window):
        low = candles[i].l
        if all(candles[j].l > low for j in range(i - window, i)) and \
           all(candles[j].l > low for j in range(i + 1, i + window + 1)):
            pivots.append(i)
    return pivots[-min_count:] if len(pivots) >= min_count else []


# ── Trendline math ───────────────────────────────────────────────────────────

def _trendline_value(p1_idx: int, p1_price: float,
                     p2_idx: int, p2_price: float,
                     at_idx: int) -> float:
    """Project the trendline defined by (p1_idx, p1_price)→(p2_idx, p2_price) to at_idx."""
    if p2_idx == p1_idx:
        return p1_price
    slope = (p2_price - p1_price) / (p2_idx - p1_idx)
    return p1_price + slope * (at_idx - p1_idx)


def _count_touches(candles: List[Candle],
                   p1_idx: int, p1_price: float,
                   p2_idx: int, p2_price: float,
                   from_idx: int, to_idx: int,
                   touch_dist: float,
                   is_support: bool) -> int:
    """Count bars between from_idx and to_idx that touch the trendline."""
    touches = 0
    for j in range(from_idx, to_idx):
        line_val = _trendline_value(p1_idx, p1_price, p2_idx, p2_price, j)
        if is_support:
            dist = candles[j].l - line_val
        else:
            dist = line_val - candles[j].h
        if abs(dist) <= touch_dist:
            touches += 1
    return touches


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class Config:
    # Swing detection
    swing_window: int = 5
    min_swing_separation: int = 20
    # Touch detection
    touch_zone_pips: float = 3.0
    min_touches_for_bounce: int = 3    # 3rd touch = high probability bounce
    # Breakout settings
    breakout_confirm_pips: float = 4.0
    # RSI gates
    rsi_period: int = 14
    rsi_bounce_long_max: float = 48.0  # long bounce: RSI < 48
    rsi_bounce_short_min: float = 52.0 # short bounce: RSI > 52
    rsi_breakout_long_min: float = 50.0
    rsi_breakout_short_max: float = 50.0
    # Trend filter
    trend_sma_bars: int = 1440
    # TP / SL
    rr_min: float = 1.3
    sl_atr_mult: float = 1.0
    max_tp_atr_mult: float = 8.0       # cap TP at 8×ATR
    # Slope sanity (in pips/bar, to reject vertical or flat lines)
    min_slope_pips_per_bar: float = 0.0   # 0 = flat allowed (horizontal S/R)
    max_slope_pips_per_bar: float = 5.0   # reject near-vertical lines
    # Performance: limit pivot search to most-recent N bars (avoids O(N²))
    pivot_lookback_bars: int = 500        # ~41 hours on M5
    # General
    pip_size: float = 0.0001
    session_start_utc: int = 7
    session_end_utc: int = 20
    cooldown_bars: int = 12


class TrendlineBreakBounceV1:
    """Trendline break & bounce strategy using swing pivots."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown: int = 0
        self._sma: List[float] = []

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        s, e = self.cfg.session_start_utc, self.cfg.session_end_utc
        return s <= h < e

    def _ensure_sma(self, candles: List[Candle]) -> None:
        k = self.cfg.trend_sma_bars
        closes = [c.c for c in candles]
        sma = []
        running = 0.0
        for idx, v in enumerate(closes):
            running += v
            if idx >= k:
                running -= closes[idx - k]
            sma.append(running / min(idx + 1, k))
        self._sma = sma

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        need = (self.cfg.swing_window * 2 + self.cfg.min_swing_separation * 2
                + self.cfg.min_touches_for_bounce * 5 + 50)
        if i < need:
            return None

        c = candles[i]
        if not self._in_session(c.ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        cfg = self.cfg
        ps = cfg.pip_size
        touch_dist = cfg.touch_zone_pips * ps

        # ── ATR ─────────────────────────────────────────────────────
        window = candles[i - 30: i + 1]
        closes = [x.c for x in window]
        highs  = [x.h for x in window]
        lows   = [x.l for x in window]
        a_cur = atr(highs, lows, closes, 14)
        if not (a_cur == a_cur and a_cur > 0):
            return None
        r_val = rsi(closes, cfg.rsi_period)

        # ── Trend filter (SMA) ───────────────────────────────────────
        if len(self._sma) <= i:
            self._ensure_sma(candles)
        trend_up = (i < len(self._sma)) and (c.c > self._sma[i])

        close = c.c
        prev  = candles[i - 1]

        # ── ── SUPPORT TRENDLINE (from swing lows) ── ────────────────
        sw_lows = _find_swing_lows(candles, i - cfg.swing_window, cfg.swing_window,
                                   lookback=cfg.pivot_lookback_bars)
        if len(sw_lows) >= 2:
            p1_i, p2_i = sw_lows[-2], sw_lows[-1]
            p1_p = candles[p1_i].l
            p2_p = candles[p2_i].l

            if p2_i - p1_i >= cfg.min_swing_separation:
                # Slope check
                slope_pips = abs((p2_p - p1_p) / (p2_i - p1_i)) / max(ps, 1e-12)
                if slope_pips <= cfg.max_slope_pips_per_bar:

                    line_now = _trendline_value(p1_i, p1_p, p2_i, p2_p, i)
                    touches = _count_touches(
                        candles, p1_i, p1_p, p2_i, p2_p,
                        p2_i + 1, i, touch_dist, is_support=True
                    ) + 2  # the 2 defining pivots count as 2 touches

                    dist_to_line = close - line_now

                    # ── BOUNCE long from support ─────────────────────
                    if (touches >= cfg.min_touches_for_bounce and
                            trend_up and
                            abs(dist_to_line) <= touch_dist * 2 and
                            prev.l <= line_now + touch_dist and
                            close > prev.c and
                            r_val == r_val and r_val <= cfg.rsi_bounce_long_max):
                        sl = line_now - cfg.sl_atr_mult * a_cur
                        # TP = last swing high visible
                        sw_highs = _find_swing_highs(candles, i, cfg.swing_window,
                                                     lookback=cfg.pivot_lookback_bars)
                        if sw_highs:
                            tp = candles[sw_highs[-1]].h
                        else:
                            tp = close + cfg.rr_min * (close - sl) * 1.2
                        tp = min(tp, close + cfg.max_tp_atr_mult * a_cur)
                        risk = close - sl
                        reward = tp - close
                        if risk > 0 and reward >= cfg.rr_min * risk:
                            self._cooldown = cfg.cooldown_bars
                            return Signal(side="long", entry=close, sl=sl, tp=tp,
                                          reason=f"tl_bounce_long_t{touches}")

                    # ── BREAKOUT short through support ───────────────
                    # (support broken = bearish)
                    if (not trend_up and
                            prev.c >= line_now - touch_dist and
                            close < line_now - cfg.breakout_confirm_pips * ps and
                            r_val == r_val and r_val <= cfg.rsi_breakout_short_max):
                        sl = line_now + cfg.sl_atr_mult * a_cur
                        tp = close - cfg.rr_min * (sl - close)
                        tp = max(tp, close - cfg.max_tp_atr_mult * a_cur)
                        risk = sl - close
                        reward = close - tp
                        if risk > 0 and reward >= cfg.rr_min * risk:
                            self._cooldown = cfg.cooldown_bars
                            return Signal(side="short", entry=close, sl=sl, tp=tp,
                                          reason="tl_break_short")

        # ── ── RESISTANCE TRENDLINE (from swing highs) ── ────────────
        sw_highs = _find_swing_highs(candles, i - cfg.swing_window, cfg.swing_window,
                                     lookback=cfg.pivot_lookback_bars)
        if len(sw_highs) >= 2:
            p1_i, p2_i = sw_highs[-2], sw_highs[-1]
            p1_p = candles[p1_i].h
            p2_p = candles[p2_i].h

            if p2_i - p1_i >= cfg.min_swing_separation:
                slope_pips = abs((p2_p - p1_p) / (p2_i - p1_i)) / max(ps, 1e-12)
                if slope_pips <= cfg.max_slope_pips_per_bar:

                    line_now = _trendline_value(p1_i, p1_p, p2_i, p2_p, i)
                    touches = _count_touches(
                        candles, p1_i, p1_p, p2_i, p2_p,
                        p2_i + 1, i, touch_dist, is_support=False
                    ) + 2

                    dist_to_line = line_now - close

                    # ── BOUNCE short from resistance ─────────────────
                    if (touches >= cfg.min_touches_for_bounce and
                            not trend_up and
                            abs(dist_to_line) <= touch_dist * 2 and
                            prev.h >= line_now - touch_dist and
                            close < prev.c and
                            r_val == r_val and r_val >= cfg.rsi_bounce_short_min):
                        sl = line_now + cfg.sl_atr_mult * a_cur
                        sw_lows2 = _find_swing_lows(candles, i, cfg.swing_window,
                                                    lookback=cfg.pivot_lookback_bars)
                        if sw_lows2:
                            tp = candles[sw_lows2[-1]].l
                        else:
                            tp = close - cfg.rr_min * (sl - close) * 1.2
                        tp = max(tp, close - cfg.max_tp_atr_mult * a_cur)
                        risk = sl - close
                        reward = close - tp
                        if risk > 0 and reward >= cfg.rr_min * risk:
                            self._cooldown = cfg.cooldown_bars
                            return Signal(side="short", entry=close, sl=sl, tp=tp,
                                          reason=f"tl_bounce_short_t{touches}")

                    # ── BREAKOUT long through resistance ─────────────
                    if (trend_up and
                            prev.c <= line_now + touch_dist and
                            close > line_now + cfg.breakout_confirm_pips * ps and
                            r_val == r_val and r_val >= cfg.rsi_breakout_long_min):
                        sl = line_now - cfg.sl_atr_mult * a_cur
                        tp = close + cfg.rr_min * (close - sl)
                        tp = min(tp, close + cfg.max_tp_atr_mult * a_cur)
                        risk = close - sl
                        reward = tp - close
                        if risk > 0 and reward >= cfg.rr_min * risk:
                            self._cooldown = cfg.cooldown_bars
                            return Signal(side="long", entry=close, sl=sl, tp=tp,
                                          reason="tl_break_long")

        return None
