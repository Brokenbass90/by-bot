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
    session_utc_start: int = 6
    session_utc_end: int = 16
    trend_slope_bars: int = 8
    min_range_width_atr: float = 1.0
    max_range_width_atr: float = 6.0
    max_ema_gap_atr: float = 0.95
    max_slow_slope_atr: float = 0.20
    min_sweep_atr: float = 0.08
    max_sweep_atr: float = 0.85
    reclaim_close_atr: float = 0.04
    confirm_window_bars: int = 4
    min_follow_body_atr: float = 0.08
    max_entry_extension_atr: float = 0.45
    sl_pad_atr: float = 0.10
    max_risk_atr: float = 1.20
    rr: float = 1.6
    cooldown_bars: int = 18


class FailureReclaimSessionV1:
    """Session-specific false-break reclaim with follow-through confirmation."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0
        self._pending_long = None
        self._pending_short = None

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

        closes = [x.c for x in candles[: i + 1]]
        highs = [x.h for x in candles[: i + 1]]
        lows = [x.l for x in candles[: i + 1]]
        ef = ema(closes[-(self.cfg.ema_fast * 2) :], self.cfg.ema_fast)
        es = ema(closes[-(self.cfg.ema_slow + 5) :], self.cfg.ema_slow)
        a = atr(highs, lows, closes, 14)
        if not (a > 0 and ef == ef and es == es):
            return None

        day_id = c.ts // 86400
        setup_high = float("-inf")
        setup_low = float("inf")
        setup_bars = 0
        bars_after_setup = 0
        seen_setup = False
        for j in range(i - 1, -1, -1):
            bar = candles[j]
            if bar.ts // 86400 != day_id:
                break
            h = self._hour(bar.ts)
            if self.cfg.setup_session_utc_start <= h < self.cfg.setup_session_utc_end:
                seen_setup = True
                setup_high = max(setup_high, bar.h)
                setup_low = min(setup_low, bar.l)
                setup_bars += 1
            elif seen_setup:
                bars_after_setup += 1
        if setup_bars < self.cfg.min_setup_bars or bars_after_setup <= 0 or bars_after_setup > self.cfg.max_bars_after_setup:
            return None

        width = setup_high - setup_low
        if width <= 0:
            return None
        width_atr = width / a
        if width_atr < self.cfg.min_range_width_atr or width_atr > self.cfg.max_range_width_atr:
            return None

        gap = ema_gap_atr(closes, self.cfg.ema_fast, self.cfg.ema_slow, a)
        if gap == gap and gap > self.cfg.max_ema_gap_atr:
            return None
        slope = slow_slope_atr(closes, self.cfg.ema_slow, self.cfg.trend_slope_bars, a)
        if slope == slope and slope > self.cfg.max_slow_slope_atr:
            return None

        body_long = c.c - c.o
        body_short = c.o - c.c

        if self._pending_long is not None:
            p = self._pending_long
            if i > p["exp"]:
                self._pending_long = None
            else:
                extension_atr = (c.c - p["lvl"]) / a
                if (
                    c.c >= p["trigger_high"]
                    and body_long >= self.cfg.min_follow_body_atr * a
                    and c.c >= ef
                    and extension_atr <= self.cfg.max_entry_extension_atr
                    and self._cooldown <= 0
                ):
                    sl = min(p["stop_ref"], p["lvl"] - self.cfg.sl_pad_atr * a)
                    risk = c.c - sl
                    if risk > 0 and risk <= self.cfg.max_risk_atr * a:
                        self._pending_long = None
                        self._cooldown = self.cfg.cooldown_bars
                        return Signal(
                            side="long",
                            entry=c.c,
                            sl=sl,
                            tp=c.c + self.cfg.rr * risk,
                            reason="fx_failure_reclaim_long",
                        )

        if self._pending_short is not None:
            p = self._pending_short
            if i > p["exp"]:
                self._pending_short = None
            else:
                extension_atr = (p["lvl"] - c.c) / a
                if (
                    c.c <= p["trigger_low"]
                    and body_short >= self.cfg.min_follow_body_atr * a
                    and c.c <= ef
                    and extension_atr <= self.cfg.max_entry_extension_atr
                    and self._cooldown <= 0
                ):
                    sl = max(p["stop_ref"], p["lvl"] + self.cfg.sl_pad_atr * a)
                    risk = sl - c.c
                    if risk > 0 and risk <= self.cfg.max_risk_atr * a:
                        self._pending_short = None
                        self._cooldown = self.cfg.cooldown_bars
                        return Signal(
                            side="short",
                            entry=c.c,
                            sl=sl,
                            tp=c.c - self.cfg.rr * risk,
                            reason="fx_failure_reclaim_short",
                        )

        if self._cooldown > 0:
            return None

        sweep_low_atr = (setup_low - c.l) / a
        if (
            c.l <= setup_low - self.cfg.min_sweep_atr * a
            and sweep_low_atr <= self.cfg.max_sweep_atr
            and c.c >= setup_low + self.cfg.reclaim_close_atr * a
            and body_long > 0
        ):
            self._pending_long = {
                "lvl": setup_low,
                "trigger_high": c.h,
                "stop_ref": c.l,
                "exp": i + self.cfg.confirm_window_bars,
            }
            self._pending_short = None
            return None

        sweep_high_atr = (c.h - setup_high) / a
        if (
            c.h >= setup_high + self.cfg.min_sweep_atr * a
            and sweep_high_atr <= self.cfg.max_sweep_atr
            and c.c <= setup_high - self.cfg.reclaim_close_atr * a
            and body_short > 0
        ):
            self._pending_short = {
                "lvl": setup_high,
                "trigger_low": c.l,
                "stop_ref": c.h,
                "exp": i + self.cfg.confirm_window_bars,
            }
            self._pending_long = None

        return None
