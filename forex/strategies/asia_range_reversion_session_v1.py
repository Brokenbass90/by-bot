from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema
from forex.strategy_filters import ema_gap_atr, slow_slope_atr
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_fast: int = 34
    ema_slow: int = 144
    setup_session_utc_start: int = 0
    setup_session_utc_end: int = 6
    min_setup_bars: int = 24
    max_bars_after_setup: int = 72
    trend_slope_bars: int = 8
    min_range_width_atr: float = 1.0
    max_range_width_atr: float = 5.5
    max_ema_gap_atr: float = 0.55
    max_slow_slope_atr: float = 0.12
    max_setup_drift_atr: float = 0.75
    edge_zone_atr: float = 0.22
    reclaim_atr: float = 0.05
    min_reject_wick_atr: float = 0.08
    min_body_atr: float = 0.02
    max_body_atr: float = 0.75
    sl_pad_atr: float = 0.12
    tp_buffer_atr: float = 0.06
    rr_cap: float = 1.8
    cooldown_bars: int = 18
    session_utc_start: int = 6
    session_utc_end: int = 16


class AsiaRangeReversionSessionV1:
    """Flat-classified Asia-range reversion during the follow-through session."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0

    @staticmethod
    def _hour(ts: int) -> int:
        return (ts // 3600) % 24

    def _in_session(self, ts: int) -> bool:
        h = self._hour(ts)
        if self.cfg.session_utc_start <= self.cfg.session_utc_end:
            return self.cfg.session_utc_start <= h < self.cfg.session_utc_end
        return h >= self.cfg.session_utc_start or h < self.cfg.session_utc_end

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        need = max(self.cfg.ema_slow + self.cfg.trend_slope_bars + 5, self.cfg.min_setup_bars + 10)
        if i < need:
            return None
        c = candles[i]
        if not self._in_session(c.ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        closes = [x.c for x in candles[: i + 1]]
        highs = [x.h for x in candles[: i + 1]]
        lows = [x.l for x in candles[: i + 1]]
        ef = ema(closes[-(self.cfg.ema_fast * 2) :], self.cfg.ema_fast)
        es = ema(closes[-(self.cfg.ema_slow + 5) :], self.cfg.ema_slow)
        a = atr(highs, lows, closes, 14)
        if not (a > 0 and ef == ef and es == es):
            return None

        gap = ema_gap_atr(closes, self.cfg.ema_fast, self.cfg.ema_slow, a)
        if gap == gap and gap > self.cfg.max_ema_gap_atr:
            return None
        slope = slow_slope_atr(closes, self.cfg.ema_slow, self.cfg.trend_slope_bars, a)
        if slope == slope and slope > self.cfg.max_slow_slope_atr:
            return None

        day_id = c.ts // 86400
        day_bars: List[Candle] = []
        for j in range(i - 1, -1, -1):
            bar = candles[j]
            if bar.ts // 86400 != day_id:
                break
            day_bars.append(bar)
        if not day_bars:
            return None
        day_bars.reverse()

        setup_bars: List[Candle] = []
        bars_after_setup = 0
        for bar in day_bars:
            h = self._hour(bar.ts)
            if self.cfg.setup_session_utc_start <= h < self.cfg.setup_session_utc_end:
                setup_bars.append(bar)
            elif setup_bars:
                bars_after_setup += 1

        if len(setup_bars) < self.cfg.min_setup_bars:
            return None
        if bars_after_setup <= 0 or bars_after_setup > self.cfg.max_bars_after_setup:
            return None

        setup_high = max(x.h for x in setup_bars)
        setup_low = min(x.l for x in setup_bars)
        width = setup_high - setup_low
        if width <= 0:
            return None
        width_atr = width / a
        if width_atr < self.cfg.min_range_width_atr or width_atr > self.cfg.max_range_width_atr:
            return None

        setup_drift_atr = abs(setup_bars[-1].c - setup_bars[0].o) / a
        if setup_drift_atr > self.cfg.max_setup_drift_atr:
            return None

        midpoint = (setup_high + setup_low) / 2.0
        body = abs(c.c - c.o)
        if body < self.cfg.min_body_atr * a or body > self.cfg.max_body_atr * a:
            return None

        wick_low = min(c.o, c.c) - c.l
        if (
            c.l <= setup_low + self.cfg.edge_zone_atr * a
            and c.c >= setup_low + self.cfg.reclaim_atr * a
            and wick_low >= self.cfg.min_reject_wick_atr * a
            and c.c > c.o
            and c.c < midpoint - self.cfg.tp_buffer_atr * a
        ):
            sl = min(c.l, setup_low - self.cfg.sl_pad_atr * a)
            risk = c.c - sl
            tp = min(midpoint - self.cfg.tp_buffer_atr * a, c.c + self.cfg.rr_cap * risk)
            if risk > 0 and tp > c.c:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(
                    side="long",
                    entry=c.c,
                    sl=sl,
                    tp=tp,
                    reason="fx_asia_range_reversion_long",
                )

        wick_high = c.h - max(c.o, c.c)
        if (
            c.h >= setup_high - self.cfg.edge_zone_atr * a
            and c.c <= setup_high - self.cfg.reclaim_atr * a
            and wick_high >= self.cfg.min_reject_wick_atr * a
            and c.c < c.o
            and c.c > midpoint + self.cfg.tp_buffer_atr * a
        ):
            sl = max(c.h, setup_high + self.cfg.sl_pad_atr * a)
            risk = sl - c.c
            tp = max(midpoint + self.cfg.tp_buffer_atr * a, c.c - self.cfg.rr_cap * risk)
            if risk > 0 and tp < c.c:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(
                    side="short",
                    entry=c.c,
                    sl=sl,
                    tp=tp,
                    reason="fx_asia_range_reversion_short",
                )

        return None
