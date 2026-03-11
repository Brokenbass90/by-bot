from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_fast: int = 55
    ema_slow: int = 220
    range_lookback: int = 48
    max_ema_gap_atr: float = 0.45
    min_range_width_atr: float = 1.0
    max_range_width_atr: float = 4.5
    zone_atr: float = 0.20
    reclaim_atr: float = 0.05
    min_reject_wick_atr: float = 0.08
    sl_pad_atr: float = 0.28
    rr: float = 1.6
    cooldown_bars: int = 18
    session_utc_start: int = 6
    session_utc_end: int = 20


class RangeBounceSessionV1:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        if self.cfg.session_utc_start <= self.cfg.session_utc_end:
            return self.cfg.session_utc_start <= h < self.cfg.session_utc_end
        return h >= self.cfg.session_utc_start or h < self.cfg.session_utc_end

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        if i < max(self.cfg.ema_slow + 5, self.cfg.range_lookback + 5):
            return None
        if not self._in_session(candles[i].ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        c = candles[i]
        closes = [x.c for x in candles[: i + 1]]
        highs = [x.h for x in candles[: i + 1]]
        lows = [x.l for x in candles[: i + 1]]

        ef = ema(closes[-(self.cfg.ema_fast * 2) :], self.cfg.ema_fast)
        es = ema(closes[-(self.cfg.ema_slow + 5) :], self.cfg.ema_slow)
        a = atr(highs, lows, closes, 14)
        if not (a > 0 and ef == ef and es == es):
            return None

        look_hi = max(highs[i - self.cfg.range_lookback : i])
        look_lo = min(lows[i - self.cfg.range_lookback : i])
        width = look_hi - look_lo
        if width <= 0:
            return None

        if abs(ef - es) > self.cfg.max_ema_gap_atr * a:
            return None
        if width < self.cfg.min_range_width_atr * a or width > self.cfg.max_range_width_atr * a:
            return None

        body = abs(c.c - c.o)
        wick_low = min(c.o, c.c) - c.l
        wick_high = c.h - max(c.o, c.c)

        near_low = c.l <= look_lo + self.cfg.zone_atr * a
        if near_low and c.c >= look_lo + self.cfg.reclaim_atr * a and wick_low >= self.cfg.min_reject_wick_atr * a:
            sl = look_lo - self.cfg.sl_pad_atr * a
            risk = c.c - sl
            if risk > 0 and body <= 2.5 * a:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(
                    side="long",
                    entry=c.c,
                    sl=sl,
                    tp=c.c + self.cfg.rr * risk,
                    reason="fx_range_bounce_long",
                )

        near_high = c.h >= look_hi - self.cfg.zone_atr * a
        if near_high and c.c <= look_hi - self.cfg.reclaim_atr * a and wick_high >= self.cfg.min_reject_wick_atr * a:
            sl = look_hi + self.cfg.sl_pad_atr * a
            risk = sl - c.c
            if risk > 0 and body <= 2.5 * a:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(
                    side="short",
                    entry=c.c,
                    sl=sl,
                    tp=c.c - self.cfg.rr * risk,
                    reason="fx_range_bounce_short",
                )

        return None
