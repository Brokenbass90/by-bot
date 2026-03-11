from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema
from forex.strategy_filters import atr_pct, ema_gap_atr, slow_slope_atr
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_fast: int = 34
    ema_slow: int = 144
    breakout_lookback: int = 24
    breakout_atr: float = 0.10
    min_body_atr: float = 0.12
    max_chase_atr: float = 0.70
    sl_atr_mult: float = 1.3
    rr: float = 1.9
    cooldown_bars: int = 14
    session_utc_start: int = 6
    session_utc_end: int = 20
    trend_slope_bars: int = 8
    min_ema_gap_atr: float = 0.0
    min_slow_slope_atr: float = 0.0
    min_range_width_atr: float = 0.0
    max_atr_pct: float = 0.0


class BreakoutContinuationSessionV1:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        if self.cfg.session_utc_start <= self.cfg.session_utc_end:
            return self.cfg.session_utc_start <= h < self.cfg.session_utc_end
        return h >= self.cfg.session_utc_start or h < self.cfg.session_utc_end

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        if i < max(self.cfg.ema_slow + 5, self.cfg.breakout_lookback + 5):
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
        if self.cfg.max_atr_pct > 0:
            cur_atr_pct = atr_pct(a, c.c)
            if cur_atr_pct == cur_atr_pct and cur_atr_pct > self.cfg.max_atr_pct:
                return None

        gap_atr = ema_gap_atr(closes, self.cfg.ema_fast, self.cfg.ema_slow, a)
        if self.cfg.min_ema_gap_atr > 0 and (gap_atr != gap_atr or gap_atr < self.cfg.min_ema_gap_atr):
            return None

        slope_atr = slow_slope_atr(closes, self.cfg.ema_slow, self.cfg.trend_slope_bars, a)
        if self.cfg.min_slow_slope_atr > 0 and (slope_atr != slope_atr or slope_atr < self.cfg.min_slow_slope_atr):
            return None

        look_hi = max(highs[i - self.cfg.breakout_lookback : i])
        look_lo = min(lows[i - self.cfg.breakout_lookback : i])
        body = abs(c.c - c.o)
        range_width_atr = (look_hi - look_lo) / max(1e-12, a)
        if self.cfg.min_range_width_atr > 0 and range_width_atr < self.cfg.min_range_width_atr:
            return None

        if ef > es:
            broke = c.c >= look_hi + self.cfg.breakout_atr * a
            impulse = (c.c - c.o) >= self.cfg.min_body_atr * a
            not_late = (c.c - look_hi) <= self.cfg.max_chase_atr * a
            if broke and impulse and not_late:
                sl = c.c - self.cfg.sl_atr_mult * a
                risk = c.c - sl
                if risk > 0 and body <= 3.0 * a:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="long",
                        entry=c.c,
                        sl=sl,
                        tp=c.c + self.cfg.rr * risk,
                        reason="fx_breakout_continuation_long",
                    )

        if ef < es:
            broke = c.c <= look_lo - self.cfg.breakout_atr * a
            impulse = (c.o - c.c) >= self.cfg.min_body_atr * a
            not_late = (look_lo - c.c) <= self.cfg.max_chase_atr * a
            if broke and impulse and not_late:
                sl = c.c + self.cfg.sl_atr_mult * a
                risk = sl - c.c
                if risk > 0 and body <= 3.0 * a:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="short",
                        entry=c.c,
                        sl=sl,
                        tp=c.c - self.cfg.rr * risk,
                        reason="fx_breakout_continuation_short",
                    )

        return None
