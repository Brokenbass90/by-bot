from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema, rsi
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_mid: int = 100
    ema_slow: int = 220
    grid_step_atr: float = 1.0
    trend_guard_atr: float = 0.9
    rsi_period: int = 14
    rsi_long_max: float = 42.0
    rsi_short_min: float = 58.0
    tp_to_ema_buffer_atr: float = 0.08
    sl_atr_mult: float = 1.2
    rr_cap: float = 2.2
    cooldown_bars: int = 16
    session_utc_start: int = 6
    session_utc_end: int = 20


class GridReversionSessionV1:
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

        em = ema(closes[-(self.cfg.ema_mid * 2) :], self.cfg.ema_mid)
        es = ema(closes[-(self.cfg.ema_slow + 5) :], self.cfg.ema_slow)
        a = atr(highs, lows, closes, 14)
        r = rsi(closes, self.cfg.rsi_period)
        if not (a > 0 and em == em and es == es and r == r):
            return None

        if abs(em - es) > self.cfg.trend_guard_atr * a:
            return None

        z = (c.c - em) / max(1e-12, a)

        if z <= -self.cfg.grid_step_atr and r <= self.cfg.rsi_long_max:
            sl = c.c - self.cfg.sl_atr_mult * a
            risk = c.c - sl
            if risk > 0:
                raw_tp = em - self.cfg.tp_to_ema_buffer_atr * a
                rr_tp = c.c + self.cfg.rr_cap * risk
                tp = min(raw_tp, rr_tp)
                if tp > c.c:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="long",
                        entry=c.c,
                        sl=sl,
                        tp=tp,
                        reason="fx_grid_reversion_long",
                    )

        if z >= self.cfg.grid_step_atr and r >= self.cfg.rsi_short_min:
            sl = c.c + self.cfg.sl_atr_mult * a
            risk = sl - c.c
            if risk > 0:
                raw_tp = em + self.cfg.tp_to_ema_buffer_atr * a
                rr_tp = c.c - self.cfg.rr_cap * risk
                tp = max(raw_tp, rr_tp)
                if tp < c.c:
                    self._cooldown = self.cfg.cooldown_bars
                    return Signal(
                        side="short",
                        entry=c.c,
                        sl=sl,
                        tp=tp,
                        reason="fx_grid_reversion_short",
                    )

        return None
