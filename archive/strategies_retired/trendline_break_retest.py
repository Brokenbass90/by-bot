from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    if period <= 0 or len(closes) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / float(period) if trs else float("nan")


@dataclass
class TrendlineBreakRetestConfig:
    lookback_bars: int = 180
    swing_n: int = 3
    min_touches: int = 4
    touch_tol_atr: float = 0.45
    atr_period: int = 14

    consolidation_bars: int = 24
    max_cons_range_atr: float = 2.8
    breakout_atr_mult: float = 0.45
    retest_pullback_atr: float = 0.45

    sl_atr_mult: float = 1.2
    rr: float = 1.8
    cooldown_bars: int = 72
    max_signals_per_day: int = 1


class TrendlineBreakRetestStrategy:
    """Trendline breakout after consolidation and multi-touch validation."""

    def __init__(self, cfg: Optional[TrendlineBreakRetestConfig] = None):
        self.cfg = cfg or TrendlineBreakRetestConfig()
        self.cfg.lookback_bars = _env_int("TLB_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.swing_n = _env_int("TLB_SWING_N", self.cfg.swing_n)
        self.cfg.min_touches = _env_int("TLB_MIN_TOUCHES", self.cfg.min_touches)
        self.cfg.touch_tol_atr = _env_float("TLB_TOUCH_TOL_ATR", self.cfg.touch_tol_atr)
        self.cfg.atr_period = _env_int("TLB_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.consolidation_bars = _env_int("TLB_CONS_BARS", self.cfg.consolidation_bars)
        self.cfg.max_cons_range_atr = _env_float("TLB_MAX_CONS_RANGE_ATR", self.cfg.max_cons_range_atr)
        self.cfg.breakout_atr_mult = _env_float("TLB_BREAKOUT_ATR_MULT", self.cfg.breakout_atr_mult)
        self.cfg.retest_pullback_atr = _env_float("TLB_RETEST_PULLBACK_ATR", self.cfg.retest_pullback_atr)
        self.cfg.sl_atr_mult = _env_float("TLB_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("TLB_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("TLB_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("TLB_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._h: List[float] = []
        self._l: List[float] = []
        self._c: List[float] = []
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _is_swing_high(self, i: int) -> bool:
        n = self.cfg.swing_n
        if i < n or i + n >= len(self._h):
            return False
        p = self._h[i]
        return all(self._h[i - k] <= p and self._h[i + k] <= p for k in range(1, n + 1))

    def _is_swing_low(self, i: int) -> bool:
        n = self.cfg.swing_n
        if i < n or i + n >= len(self._l):
            return False
        p = self._l[i]
        return all(self._l[i - k] >= p and self._l[i + k] >= p for k in range(1, n + 1))

    @staticmethod
    def _line(i1: int, p1: float, i2: int, p2: float) -> Tuple[float, float]:
        if i2 == i1:
            return 0.0, p2
        m = (p2 - p1) / float(i2 - i1)
        b = p2 - m * i2
        return m, b

    def _count_touches(self, pivots: List[Tuple[int, float]], m: float, b: float, tol: float) -> int:
        cnt = 0
        for i, p in pivots:
            px = m * i + b
            if abs(p - px) <= tol:
                cnt += 1
        return cnt

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (store, o, v)
        self._h.append(h)
        self._l.append(l)
        self._c.append(c)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        need = max(self.cfg.lookback_bars + self.cfg.swing_n * 2 + 5, self.cfg.atr_period + 20)
        if len(self._c) < need:
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None

        # Consolidation before breakout: last bars should be relatively compressed.
        cons_n = max(6, int(self.cfg.consolidation_bars))
        cons_hi = max(self._h[-cons_n:])
        cons_lo = min(self._l[-cons_n:])
        if (cons_hi - cons_lo) / atr_now > self.cfg.max_cons_range_atr:
            return None

        left = len(self._c) - self.cfg.lookback_bars
        right = len(self._c) - 2  # last closed bar index
        if right <= left:
            return None

        swing_highs: List[Tuple[int, float]] = []
        swing_lows: List[Tuple[int, float]] = []
        for i in range(left, right + 1):
            if self._is_swing_high(i):
                swing_highs.append((i, self._h[i]))
            if self._is_swing_low(i):
                swing_lows.append((i, self._l[i]))

        if len(swing_highs) < 2 and len(swing_lows) < 2:
            return None

        # Long: descending resistance (>=3 touches) then breakout + controlled retest.
        if len(swing_highs) >= 2:
            (i1, p1), (i2, p2) = swing_highs[-2], swing_highs[-1]
            if p2 < p1:
                m, b = self._line(i1, p1, i2, p2)
                line_now = m * right + b
                tol = self.cfg.touch_tol_atr * atr_now
                touches = self._count_touches(swing_highs, m, b, tol)
                broke = self._c[right] > line_now + self.cfg.breakout_atr_mult * atr_now
                retest_ok = (self._c[right] - line_now) <= self.cfg.retest_pullback_atr * atr_now
                if touches >= self.cfg.min_touches and broke and retest_ok:
                    entry = self._c[right]
                    sl = min(cons_lo, line_now) - self.cfg.sl_atr_mult * atr_now
                    risk = entry - sl
                    if risk > 0:
                        tp = entry + self.cfg.rr * risk
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="trendline_break_retest",
                            symbol=store.symbol,
                            side="long",
                            entry=entry,
                            sl=sl,
                            tp=tp,
                            reason=f"tlb_long touches={touches}",
                        )

        # Short: ascending support (>=3 touches) then breakdown + controlled retest.
        if len(swing_lows) >= 2:
            (i1, p1), (i2, p2) = swing_lows[-2], swing_lows[-1]
            if p2 > p1:
                m, b = self._line(i1, p1, i2, p2)
                line_now = m * right + b
                tol = self.cfg.touch_tol_atr * atr_now
                touches = self._count_touches(swing_lows, m, b, tol)
                broke = self._c[right] < line_now - self.cfg.breakout_atr_mult * atr_now
                retest_ok = (line_now - self._c[right]) <= self.cfg.retest_pullback_atr * atr_now
                if touches >= self.cfg.min_touches and broke and retest_ok:
                    entry = self._c[right]
                    sl = max(cons_hi, line_now) + self.cfg.sl_atr_mult * atr_now
                    risk = sl - entry
                    if risk > 0:
                        tp = entry - self.cfg.rr * risk
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="trendline_break_retest",
                            symbol=store.symbol,
                            side="short",
                            entry=entry,
                            sl=sl,
                            tp=tp,
                            reason=f"tlb_short touches={touches}",
                        )
        return None
