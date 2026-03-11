from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema
from forex.strategy_filters import atr_pct, ema_gap_atr, slow_slope_atr
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_fast: int = 48
    ema_slow: int = 200
    breakout_lookback: int = 36
    retest_window_bars: int = 6
    sl_atr_mult: float = 1.5
    rr: float = 2.2
    cooldown_bars: int = 24
    session_utc_start: int = 6
    session_utc_end: int = 20
    trend_slope_bars: int = 8
    min_ema_gap_atr: float = 0.0
    min_slow_slope_atr: float = 0.0
    max_atr_pct: float = 0.0
    min_breakout_body_atr: float = 0.0
    max_entry_extension_atr: float = 0.0


class TrendRetestSessionV1:
    """Conservative session-based breakout/retest for Forex pilot."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0
        self._pending_long = None
        self._pending_short = None

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        return self.cfg.session_utc_start <= h < self.cfg.session_utc_end

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        if i < max(self.cfg.ema_slow + 5, self.cfg.breakout_lookback + 5):
            return None

        c = candles[i]
        if not self._in_session(c.ts):
            return None
        if self._cooldown > 0:
            self._cooldown -= 1

        closes = [x.c for x in candles[: i + 1]]
        highs = [x.h for x in candles[: i + 1]]
        lows = [x.l for x in candles[: i + 1]]

        ef = ema(closes[-(self.cfg.ema_fast * 2) :], self.cfg.ema_fast)
        es = ema(closes[-(self.cfg.ema_slow + 5) :], self.cfg.ema_slow)
        a = atr(highs, lows, closes, 14)
        if not (a > 0 and ef == ef and es == es):
            return None
        close = c.c
        if self.cfg.max_atr_pct > 0:
            cur_atr_pct = atr_pct(a, close)
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

        if self._pending_long is not None:
            p = self._pending_long
            if i > p["exp"]:
                self._pending_long = None
            else:
                lvl = p["lvl"]
                touched = c.l <= lvl + 0.15 * a
                held = close >= lvl + 0.04 * a
                extension_atr = (close - lvl) / a
                if touched and held and self._cooldown <= 0:
                    if self.cfg.max_entry_extension_atr > 0 and extension_atr > self.cfg.max_entry_extension_atr:
                        self._pending_long = None
                        return None
                    sl = lvl - self.cfg.sl_atr_mult * a
                    risk = close - sl
                    if risk > 0:
                        self._pending_long = None
                        self._cooldown = self.cfg.cooldown_bars
                        return Signal(side="long", entry=close, sl=sl, tp=close + self.cfg.rr * risk, reason="fx_long_retest")

        if self._pending_short is not None:
            p = self._pending_short
            if i > p["exp"]:
                self._pending_short = None
            else:
                lvl = p["lvl"]
                touched = c.h >= lvl - 0.15 * a
                held = close <= lvl - 0.04 * a
                extension_atr = (lvl - close) / a
                if touched and held and self._cooldown <= 0:
                    if self.cfg.max_entry_extension_atr > 0 and extension_atr > self.cfg.max_entry_extension_atr:
                        self._pending_short = None
                        return None
                    sl = lvl + self.cfg.sl_atr_mult * a
                    risk = sl - close
                    if risk > 0:
                        self._pending_short = None
                        self._cooldown = self.cfg.cooldown_bars
                        return Signal(side="short", entry=close, sl=sl, tp=close - self.cfg.rr * risk, reason="fx_short_retest")

        # Create pending only on clean breakout in trend direction.
        if self._cooldown <= 0:
            long_body = c.c - c.o
            short_body = c.o - c.c
            if ef > es and close >= look_hi + 0.12 * a and long_body >= self.cfg.min_breakout_body_atr * a:
                self._pending_long = {"lvl": look_hi, "exp": i + self.cfg.retest_window_bars}
            if ef < es and close <= look_lo - 0.12 * a and short_body >= self.cfg.min_breakout_body_atr * a:
                self._pending_short = {"lvl": look_lo, "exp": i + self.cfg.retest_window_bars}

        return None
