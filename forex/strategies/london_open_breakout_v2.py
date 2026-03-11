from __future__ import annotations

"""
London Open Breakout V2 — with EMA trend filter (fast, precomputed)
====================================================================
Improvement over V1:
  - EMA trend filter: only long when H1-eq uptrend, only short in downtrend
    (EMA(240) vs EMA(600) on M5 — precomputed on first call, O(n))
  - Tighter range: 10–45 pips (avoids wild sessions)
  - Higher RR: 2.5
  - ATR-based SL (tighter than full opposite range)
  - Breakout must be a strong bar: close > open (longs) or close < open (shorts)
  - Only first London breakout per day
"""

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr
from forex.types import Candle, Signal


@dataclass
class Config:
    asian_start_utc: int = 0
    asian_end_utc: int = 7
    london_start_utc: int = 7
    london_end_utc: int = 11
    min_range_pips: float = 10.0
    max_range_pips: float = 45.0
    breakout_buffer_pips: float = 2.0
    rr: float = 2.5
    min_asian_bars: int = 24
    asian_lookback: int = 120
    pip_size: float = 0.0001
    min_atr_pips: float = 3.0
    # Trend filter: only trade with EMA(ema_fast) vs EMA(ema_slow) direction
    ema_fast: int = 240    # M5 bars ≈ H1 EMA20
    ema_slow: int = 600    # M5 bars ≈ H1 EMA50
    use_trend_filter: bool = True
    # SL: ATR-based from entry (avoids overly wide opposite-range SL)
    sl_atr_mult: float = 1.2
    one_trade_per_day: bool = True


def _ema_series(values: list, period: int) -> list:
    """Compute EMA over a list, returning a list of same length."""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


class LondonOpenBreakoutV2:
    """LOB with trend filter — precomputes EMA on first call for O(1) per bar."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._last_trade_day: int = -1
        # Precomputed EMA arrays (lazy, built on first call)
        self._ef: Optional[list] = None   # EMA_fast values indexed by bar
        self._es: Optional[list] = None   # EMA_slow values indexed by bar
        self._last_candle_count: int = 0

    def _utc_hour(self, ts: int) -> int:
        return (ts // 3600) % 24

    def _utc_day(self, ts: int) -> int:
        return ts // 86400

    def _in_asian(self, ts: int) -> bool:
        h = self._utc_hour(ts)
        return self.cfg.asian_start_utc <= h < self.cfg.asian_end_utc

    def _in_london(self, ts: int) -> bool:
        h = self._utc_hour(ts)
        return self.cfg.london_start_utc <= h < self.cfg.london_end_utc

    def _ensure_ema(self, candles: List[Candle]) -> None:
        """Precompute EMA arrays over all candles (once)."""
        n = len(candles)
        if self._ef is not None and n == self._last_candle_count:
            return
        closes = [c.c for c in candles]
        self._ef = _ema_series(closes, self.cfg.ema_fast)
        self._es = _ema_series(closes, self.cfg.ema_slow)
        self._last_candle_count = n

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        if i < max(50, self.cfg.asian_lookback, self.cfg.ema_slow + 10):
            return None

        c = candles[i]
        if not self._in_london(c.ts):
            return None

        cur_day = self._utc_day(c.ts)
        if self.cfg.one_trade_per_day and cur_day == self._last_trade_day:
            return None

        # ── Trend filter ───────────────────────────────────────────────
        if self.cfg.use_trend_filter:
            self._ensure_ema(candles)
            ef_now = self._ef[i]
            es_now = self._es[i]
            if ef_now != ef_now or es_now != es_now:
                return None
            trend_up   = ef_now > es_now
            trend_down = ef_now < es_now
        else:
            trend_up = trend_down = True   # no filter

        # ── Collect Asian bars ──────────────────────────────────────────
        asian_bars: List[Candle] = []
        for j in range(i - 1, max(0, i - self.cfg.asian_lookback), -1):
            prev = candles[j]
            if self._in_asian(prev.ts):
                asian_bars.append(prev)

        if len(asian_bars) < self.cfg.min_asian_bars:
            return None

        ps = self.cfg.pip_size
        range_high = max(b.h for b in asian_bars)
        range_low  = min(b.l for b in asian_bars)
        range_pips = (range_high - range_low) / max(ps, 1e-12)

        if range_pips < self.cfg.min_range_pips or range_pips > self.cfg.max_range_pips:
            return None

        # ── ATR gate ───────────────────────────────────────────────────
        closes = [x.c for x in candles[i - 30: i + 1]]
        highs  = [x.h for x in candles[i - 30: i + 1]]
        lows   = [x.l for x in candles[i - 30: i + 1]]
        a = atr(highs, lows, closes, 14)
        if not (a == a and a > 0):
            return None
        atr_pips = a / max(ps, 1e-12)
        if atr_pips < self.cfg.min_atr_pips:
            return None

        close = c.c
        buf_break = self.cfg.breakout_buffer_pips * ps
        sl_dist   = self.cfg.sl_atr_mult * a

        # ── Long breakout ──────────────────────────────────────────────
        if trend_up and close > range_high + buf_break and c.c > c.o:
            sl   = close - sl_dist
            risk = close - sl
            if risk <= 0:
                return None
            tp = close + self.cfg.rr * risk
            self._last_trade_day = cur_day
            return Signal(side="long", entry=close, sl=sl, tp=tp,
                          reason="lob2_long")

        # ── Short breakout ─────────────────────────────────────────────
        if trend_down and close < range_low - buf_break and c.c < c.o:
            sl   = close + sl_dist
            risk = sl - close
            if risk <= 0:
                return None
            tp = close - self.cfg.rr * risk
            self._last_trade_day = cur_day
            return Signal(side="short", entry=close, sl=sl, tp=tp,
                          reason="lob2_short")

        return None
