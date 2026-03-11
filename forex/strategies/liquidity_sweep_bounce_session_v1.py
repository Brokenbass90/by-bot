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
    sweep_lookback: int = 36
    setup_session_utc_start: int = 0
    setup_session_utc_end: int = 6
    min_setup_bars: int = 24
    max_bars_after_setup: int = 72
    min_range_width_atr: float = 1.4
    max_range_width_atr: float = 6.0
    max_ema_gap_atr: float = 0.75
    max_slow_slope_atr: float = 0.18
    trend_slope_bars: int = 8
    min_sweep_atr: float = 0.10
    max_sweep_atr: float = 0.70
    reclaim_atr: float = 0.04
    min_reject_wick_atr: float = 0.10
    min_wick_to_body: float = 1.5
    max_body_atr: float = 0.45
    sl_pad_atr: float = 0.12
    max_risk_atr: float = 1.10
    rr: float = 1.6
    cooldown_bars: int = 18
    session_utc_start: int = 6
    session_utc_end: int = 20


class LiquiditySweepBounceSessionV1:
    """False-break bounce after a recent range edge sweep and reclaim."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        if self.cfg.session_utc_start <= self.cfg.session_utc_end:
            return self.cfg.session_utc_start <= h < self.cfg.session_utc_end
        return h >= self.cfg.session_utc_start or h < self.cfg.session_utc_end

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        need = max(self.cfg.ema_slow + self.cfg.trend_slope_bars + 5, self.cfg.sweep_lookback + 5)
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

        look_hi = max(highs[i - self.cfg.sweep_lookback : i])
        look_lo = min(lows[i - self.cfg.sweep_lookback : i])
        width = look_hi - look_lo
        if width <= 0:
            return None
        if width < self.cfg.min_range_width_atr * a or width > self.cfg.max_range_width_atr * a:
            return None

        gap_atr = ema_gap_atr(closes, self.cfg.ema_fast, self.cfg.ema_slow, a)
        if gap_atr == gap_atr and gap_atr > self.cfg.max_ema_gap_atr:
            return None
        slope_atr = slow_slope_atr(closes, self.cfg.ema_slow, self.cfg.trend_slope_bars, a)
        if slope_atr == slope_atr and slope_atr > self.cfg.max_slow_slope_atr:
            return None

        day_id = c.ts // 86400
        setup_high = float("-inf")
        setup_low = float("inf")
        setup_bars = 0
        bars_after_setup = 0
        seen_setup_end = False
        for j in range(i - 1, -1, -1):
            bar = candles[j]
            if bar.ts // 86400 != day_id:
                break
            h = (bar.ts // 3600) % 24
            if self.cfg.setup_session_utc_start <= h < self.cfg.setup_session_utc_end:
                setup_high = max(setup_high, bar.h)
                setup_low = min(setup_low, bar.l)
                setup_bars += 1
            elif h >= self.cfg.setup_session_utc_end:
                seen_setup_end = True
                bars_after_setup += 1
        if not seen_setup_end or setup_bars < self.cfg.min_setup_bars:
            return None
        if bars_after_setup <= 0 or bars_after_setup > self.cfg.max_bars_after_setup:
            return None

        # Prefer the earlier session range when available; rolling lookback stays as a fallback guard.
        look_hi = max(look_hi, setup_high)
        look_lo = min(look_lo, setup_low)
        width = look_hi - look_lo
        if width <= 0:
            return None
        if width < self.cfg.min_range_width_atr * a or width > self.cfg.max_range_width_atr * a:
            return None

        body = abs(c.c - c.o)
        if body > self.cfg.max_body_atr * a:
            return None
        body_floor = max(body, 0.02 * a)

        wick_low = min(c.o, c.c) - c.l
        sweep_low_atr = (look_lo - c.l) / a
        if (
            c.l <= look_lo - self.cfg.min_sweep_atr * a
            and sweep_low_atr <= self.cfg.max_sweep_atr
            and c.c >= look_lo + self.cfg.reclaim_atr * a
            and wick_low >= self.cfg.min_reject_wick_atr * a
            and wick_low >= self.cfg.min_wick_to_body * body_floor
        ):
            sl = c.l - self.cfg.sl_pad_atr * a
            risk = c.c - sl
            if risk > 0 and risk <= self.cfg.max_risk_atr * a:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(
                    side="long",
                    entry=c.c,
                    sl=sl,
                    tp=c.c + self.cfg.rr * risk,
                    reason="fx_liquidity_sweep_long",
                )

        wick_high = c.h - max(c.o, c.c)
        sweep_high_atr = (c.h - look_hi) / a
        if (
            c.h >= look_hi + self.cfg.min_sweep_atr * a
            and sweep_high_atr <= self.cfg.max_sweep_atr
            and c.c <= look_hi - self.cfg.reclaim_atr * a
            and wick_high >= self.cfg.min_reject_wick_atr * a
            and wick_high >= self.cfg.min_wick_to_body * body_floor
        ):
            sl = c.h + self.cfg.sl_pad_atr * a
            risk = sl - c.c
            if risk > 0 and risk <= self.cfg.max_risk_atr * a:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(
                    side="short",
                    entry=c.c,
                    sl=sl,
                    tp=c.c - self.cfg.rr * risk,
                    reason="fx_liquidity_sweep_short",
                )

        return None
