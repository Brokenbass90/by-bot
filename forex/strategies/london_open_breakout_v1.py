from __future__ import annotations

"""
London Open Breakout V1
=======================
Classic session range breakout: mark the Asian/pre-London range (00:00–07:00 UTC),
then trade a clean breakout at the London open (07:00–11:00 UTC).

Long:  price breaks above Asian range high  → buy, SL = Asian low - buffer, TP = 2.0× risk
Short: price breaks below Asian range low   → sell, SL = Asian high + buffer, TP = 2.0× risk

One trade per day, per direction.

Why this works vs existing strategies:
- Uses clear market-session structure (London open volatility surge)
- Defined risk anchored to overnight range (not noisy ATR)
- Not over-traded: at most one entry per session
"""

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr
from forex.types import Candle, Signal


@dataclass
class Config:
    # Asian range: 00:00–07:00 UTC
    asian_start_utc: int = 0
    asian_end_utc: int = 7
    # London entry window: 07:00–11:00 UTC
    london_start_utc: int = 7
    london_end_utc: int = 11
    # Range size limits in pips (pip_size resolved per instrument)
    min_range_pips: float = 8.0
    max_range_pips: float = 60.0
    # Buffer beyond range before treating as breakout (pips)
    breakout_buffer_pips: float = 1.5
    # SL = opposite range edge - this buffer (pips)
    sl_buffer_pips: float = 3.0
    # Risk:reward
    rr: float = 2.0
    # How many Asian bars required before we trust the range
    min_asian_bars: int = 24      # ≥ 2H worth of M5 bars
    # Max lookback to find Asian bars (bars)
    asian_lookback: int = 120     # 10H back at M5
    # Pip size; set per instrument or use default
    pip_size: float = 0.0001
    # ATR filter: current ATR must be ≥ min_atr_pips pips (avoid flat market)
    min_atr_pips: float = 3.0
    # Do not re-enter if a trade already placed today
    one_trade_per_day: bool = True


class LondonOpenBreakoutV1:
    """London session range breakout — one entry per day per direction."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        # Track which calendar day (UTC) the last trade was taken
        self._last_trade_day: int = -1

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        if i < max(50, self.cfg.asian_lookback):
            return None

        c = candles[i]

        # Only trade during London window
        if not self._in_london(c.ts):
            return None

        cur_day = self._utc_day(c.ts)
        if self.cfg.one_trade_per_day and cur_day == self._last_trade_day:
            return None

        # ── Collect Asian bars ──────────────────────────────────────────
        asian_bars: List[Candle] = []
        for j in range(i - 1, max(0, i - self.cfg.asian_lookback), -1):
            prev = candles[j]
            if self._in_asian(prev.ts):
                asian_bars.append(prev)
            elif self._in_london(prev.ts):
                # Earlier London bars from a previous run — skip, don't stop
                continue

        if len(asian_bars) < self.cfg.min_asian_bars:
            return None

        range_high = max(b.h for b in asian_bars)
        range_low  = min(b.l for b in asian_bars)
        ps = self.cfg.pip_size
        range_pips = (range_high - range_low) / max(ps, 1e-12)

        if range_pips < self.cfg.min_range_pips or range_pips > self.cfg.max_range_pips:
            return None

        # ── ATR gate ─────────────────────────────── (use last 30 bars only)
        win = candles[max(0, i - 29): i + 1]
        closes = [x.c for x in win]
        highs  = [x.h for x in win]
        lows   = [x.l for x in win]
        a = atr(highs, lows, closes, 14)
        if not (a == a and a > 0):   # nan check
            return None
        atr_pips = a / max(ps, 1e-12)
        if atr_pips < self.cfg.min_atr_pips:
            return None

        close = c.c
        buf_break = self.cfg.breakout_buffer_pips * ps
        buf_sl    = self.cfg.sl_buffer_pips * ps

        # ── Long breakout ──────────────────────────────────────────────
        if close > range_high + buf_break:
            sl   = range_low - buf_sl
            risk = close - sl
            if risk <= 0:
                return None
            tp = close + self.cfg.rr * risk
            self._last_trade_day = cur_day
            return Signal(side="long", entry=close, sl=sl, tp=tp,
                          reason="lob_long")

        # ── Short breakout ─────────────────────────────────────────────
        if close < range_low - buf_break:
            sl   = range_high + buf_sl
            risk = sl - close
            if risk <= 0:
                return None
            tp = close - self.cfg.rr * risk
            self._last_trade_day = cur_day
            return Signal(side="short", entry=close, sl=sl, tp=tp,
                          reason="lob_short")

        return None
