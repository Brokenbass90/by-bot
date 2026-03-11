from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema
from forex.strategy_filters import atr_pct, ema_gap_atr, slow_slope_atr
from forex.types import Candle, Signal


@dataclass
class Config:
    ema_fast: int = 48
    ema_slow: int = 220
    breakout_lookback: int = 36
    retest_window_bars: int = 8
    sl_atr_mult: float = 1.2
    rr: float = 1.8
    cooldown_bars: int = 24
    session_utc_start: int = 6
    session_utc_end: int = 20
    trend_slope_bars: int = 8
    min_ema_gap_atr: float = 0.10
    min_slow_slope_atr: float = 0.05
    min_range_width_atr: float = 1.2
    max_range_width_atr: float = 8.0
    max_atr_pct: float = 0.0
    breakout_buffer_atr: float = 0.10
    min_breakout_body_atr: float = 0.12
    max_breakout_body_atr: float = 1.20
    retest_touch_atr: float = 0.18
    retest_hold_atr: float = 0.05
    min_retest_body_atr: float = 0.04
    min_retest_reject_wick_atr: float = 0.04
    max_entry_extension_atr: float = 0.45
    level_sl_pad_atr: float = 0.10
    max_risk_atr: float = 1.8


class TrendRetestSessionV2:
    """Quality-gated breakout and retest with structure-width filters."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0
        self._pending_long = None
        self._pending_short = None

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        return self.cfg.session_utc_start <= h < self.cfg.session_utc_end

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        if i < max(self.cfg.ema_slow + self.cfg.trend_slope_bars + 5, self.cfg.breakout_lookback + 5):
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
        width = look_hi - look_lo
        if width <= 0:
            return None
        width_atr = width / a
        if width_atr < self.cfg.min_range_width_atr or width_atr > self.cfg.max_range_width_atr:
            return None

        body_long = c.c - c.o
        body_short = c.o - c.c
        wick_low = min(c.o, c.c) - c.l
        wick_high = c.h - max(c.o, c.c)

        if self._pending_long is not None:
            p = self._pending_long
            if i > p["exp"]:
                self._pending_long = None
            else:
                lvl = p["lvl"]
                touched = c.l <= lvl + self.cfg.retest_touch_atr * a
                held = close >= max(lvl + self.cfg.retest_hold_atr * a, ef)
                extension_atr = (close - lvl) / a
                if (
                    touched
                    and held
                    and body_long >= self.cfg.min_retest_body_atr * a
                    and wick_low >= self.cfg.min_retest_reject_wick_atr * a
                    and extension_atr <= self.cfg.max_entry_extension_atr
                    and self._cooldown <= 0
                ):
                    sl = min(c.l, lvl - self.cfg.level_sl_pad_atr * a)
                    risk = close - sl
                    if risk > 0 and risk <= self.cfg.max_risk_atr * a:
                        self._pending_long = None
                        self._cooldown = self.cfg.cooldown_bars
                        return Signal(
                            side="long",
                            entry=close,
                            sl=sl,
                            tp=close + self.cfg.rr * risk,
                            reason="fx_long_retest_v2",
                        )

        if self._pending_short is not None:
            p = self._pending_short
            if i > p["exp"]:
                self._pending_short = None
            else:
                lvl = p["lvl"]
                touched = c.h >= lvl - self.cfg.retest_touch_atr * a
                held = close <= min(lvl - self.cfg.retest_hold_atr * a, ef)
                extension_atr = (lvl - close) / a
                if (
                    touched
                    and held
                    and body_short >= self.cfg.min_retest_body_atr * a
                    and wick_high >= self.cfg.min_retest_reject_wick_atr * a
                    and extension_atr <= self.cfg.max_entry_extension_atr
                    and self._cooldown <= 0
                ):
                    sl = max(c.h, lvl + self.cfg.level_sl_pad_atr * a)
                    risk = sl - close
                    if risk > 0 and risk <= self.cfg.max_risk_atr * a:
                        self._pending_short = None
                        self._cooldown = self.cfg.cooldown_bars
                        return Signal(
                            side="short",
                            entry=close,
                            sl=sl,
                            tp=close - self.cfg.rr * risk,
                            reason="fx_short_retest_v2",
                        )

        if self._cooldown <= 0:
            if (
                ef > es
                and close >= look_hi + self.cfg.breakout_buffer_atr * a
                and body_long >= self.cfg.min_breakout_body_atr * a
                and body_long <= self.cfg.max_breakout_body_atr * a
            ):
                self._pending_long = {"lvl": look_hi, "exp": i + self.cfg.retest_window_bars}
                self._pending_short = None
            if (
                ef < es
                and close <= look_lo - self.cfg.breakout_buffer_atr * a
                and body_short >= self.cfg.min_breakout_body_atr * a
                and body_short <= self.cfg.max_breakout_body_atr * a
            ):
                self._pending_short = {"lvl": look_lo, "exp": i + self.cfg.retest_window_bars}
                self._pending_long = None

        return None
