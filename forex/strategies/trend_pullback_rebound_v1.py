from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema, rsi
from forex.strategy_filters import atr_pct, ema_gap_atr, slow_slope_atr
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_fast: int = 34
    ema_slow: int = 144
    pullback_zone_atr: float = 0.30
    reclaim_atr: float = 0.05
    rsi_period: int = 14
    rsi_long_max: float = 52.0
    rsi_short_min: float = 48.0
    sl_atr_mult: float = 1.35
    rr: float = 2.0
    cooldown_bars: int = 16
    session_utc_start: int = 6
    session_utc_end: int = 20
    trend_slope_bars: int = 8
    min_ema_gap_atr: float = 0.0
    min_slow_slope_atr: float = 0.0
    max_atr_pct: float = 0.0
    min_rebound_body_atr: float = 0.0
    max_pullthrough_slow_atr: float = 0.0


class TrendPullbackReboundV1:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        if self.cfg.session_utc_start <= self.cfg.session_utc_end:
            return self.cfg.session_utc_start <= h < self.cfg.session_utc_end
        return h >= self.cfg.session_utc_start or h < self.cfg.session_utc_end

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        if i < max(self.cfg.ema_slow + 5, self.cfg.rsi_period + 5):
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
        r = rsi(closes, self.cfg.rsi_period)
        if not (a > 0 and ef == ef and es == es and r == r):
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

        if ef > es:
            pulled = c.l <= ef + self.cfg.pullback_zone_atr * a
            reclaimed = c.c >= ef + self.cfg.reclaim_atr * a
            body = c.c - c.o
            deep_pull = self.cfg.max_pullthrough_slow_atr > 0 and c.l < es - self.cfg.max_pullthrough_slow_atr * a
            if pulled and reclaimed and r <= self.cfg.rsi_long_max and body >= self.cfg.min_rebound_body_atr * a and not deep_pull:
                sl = c.c - self.cfg.sl_atr_mult * a
                risk = c.c - sl
                if risk > 0:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="long",
                        entry=c.c,
                        sl=sl,
                        tp=c.c + self.cfg.rr * risk,
                        reason="fx_trend_pullback_long",
                    )

        if ef < es:
            pulled = c.h >= ef - self.cfg.pullback_zone_atr * a
            reclaimed = c.c <= ef - self.cfg.reclaim_atr * a
            body = c.o - c.c
            deep_pull = self.cfg.max_pullthrough_slow_atr > 0 and c.h > es + self.cfg.max_pullthrough_slow_atr * a
            if pulled and reclaimed and r >= self.cfg.rsi_short_min and body >= self.cfg.min_rebound_body_atr * a and not deep_pull:
                sl = c.c + self.cfg.sl_atr_mult * a
                risk = sl - c.c
                if risk > 0:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="short",
                        entry=c.c,
                        sl=sl,
                        tp=c.c - self.cfg.rr * risk,
                        reason="fx_trend_pullback_short",
                    )

        return None
