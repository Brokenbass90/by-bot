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


def _atr(h: List[float], l: List[float], c: List[float], period: int) -> float:
    if period <= 0 or len(c) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return sum(trs) / float(period) if trs else float("nan")


def _sma(vals: List[float], period: int) -> float:
    if period <= 0 or len(vals) < period:
        return float("nan")
    w = vals[-period:]
    return sum(w) / float(period) if w else float("nan")


@dataclass
class TrendlineBreakRetestV3Config:
    lookback_bars: int = 260
    swing_n: int = 3
    min_touches: int = 3
    touch_tol_atr: float = 0.40
    atr_period: int = 14

    consolidation_bars: int = 24
    max_cons_range_atr: float = 2.6
    breakout_atr_mult: float = 0.35
    min_breakout_ext_atr: float = 0.35
    retest_window_bars: int = 12
    retest_pullback_atr: float = 0.55
    retest_min_body_frac: float = 0.22

    bos_lookback_bars: int = 36
    bos_atr_mult: float = 0.15
    vol_sma_bars: int = 30
    vol_breakout_mult: float = 1.30

    sl_atr_mult: float = 1.10
    rr: float = 2.1
    cooldown_bars: int = 64
    max_signals_per_day: int = 1


class TrendlineBreakRetestV3Strategy:
    """Trendline break + structure break + retest confirmation."""

    def __init__(self, cfg: Optional[TrendlineBreakRetestV3Config] = None):
        self.cfg = cfg or TrendlineBreakRetestV3Config()
        self.cfg.lookback_bars = _env_int("TLB3_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.swing_n = _env_int("TLB3_SWING_N", self.cfg.swing_n)
        self.cfg.min_touches = _env_int("TLB3_MIN_TOUCHES", self.cfg.min_touches)
        self.cfg.touch_tol_atr = _env_float("TLB3_TOUCH_TOL_ATR", self.cfg.touch_tol_atr)
        self.cfg.atr_period = _env_int("TLB3_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.consolidation_bars = _env_int("TLB3_CONS_BARS", self.cfg.consolidation_bars)
        self.cfg.max_cons_range_atr = _env_float("TLB3_MAX_CONS_RANGE_ATR", self.cfg.max_cons_range_atr)
        self.cfg.breakout_atr_mult = _env_float("TLB3_BREAKOUT_ATR_MULT", self.cfg.breakout_atr_mult)
        self.cfg.min_breakout_ext_atr = _env_float("TLB3_MIN_BREAKOUT_EXT_ATR", self.cfg.min_breakout_ext_atr)
        self.cfg.retest_window_bars = _env_int("TLB3_RETEST_WINDOW_BARS", self.cfg.retest_window_bars)
        self.cfg.retest_pullback_atr = _env_float("TLB3_RETEST_PULLBACK_ATR", self.cfg.retest_pullback_atr)
        self.cfg.retest_min_body_frac = _env_float("TLB3_RETEST_MIN_BODY_FRAC", self.cfg.retest_min_body_frac)
        self.cfg.bos_lookback_bars = _env_int("TLB3_BOS_LOOKBACK_BARS", self.cfg.bos_lookback_bars)
        self.cfg.bos_atr_mult = _env_float("TLB3_BOS_ATR_MULT", self.cfg.bos_atr_mult)
        self.cfg.vol_sma_bars = _env_int("TLB3_VOL_SMA_BARS", self.cfg.vol_sma_bars)
        self.cfg.vol_breakout_mult = _env_float("TLB3_VOL_BREAKOUT_MULT", self.cfg.vol_breakout_mult)
        self.cfg.sl_atr_mult = _env_float("TLB3_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("TLB3_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("TLB3_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("TLB3_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._o: List[float] = []
        self._h: List[float] = []
        self._l: List[float] = []
        self._c: List[float] = []
        self._v: List[float] = []
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0
        self._pending_long: Optional[dict] = None
        self._pending_short: Optional[dict] = None

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

    @staticmethod
    def _line_px(m: float, b: float, i: int) -> float:
        return m * i + b

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = store
        self._o.append(o)
        self._h.append(h)
        self._l.append(l)
        self._c.append(c)
        self._v.append(max(0.0, float(v or 0.0)))

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

        need = max(
            self.cfg.lookback_bars + self.cfg.swing_n * 2 + 10,
            self.cfg.atr_period + 20,
            self.cfg.bos_lookback_bars + 10,
            self.cfg.vol_sma_bars + 5,
        )
        if len(self._c) < need:
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None
        idx = len(self._c) - 1

        rng = max(1e-12, h - l)
        body_frac = abs(c - o) / rng

        if self._pending_long is not None:
            pd = self._pending_long
            if idx > int(pd["expire_idx"]):
                self._pending_long = None
            else:
                line_now = self._line_px(float(pd["m"]), float(pd["b"]), idx)
                touched = l <= line_now + self.cfg.retest_pullback_atr * float(pd["atr"])
                rejected = c > line_now and c > o and body_frac >= self.cfg.retest_min_body_frac
                if touched and rejected:
                    entry = c
                    sl = min(float(pd["cons_lo"]), line_now) - self.cfg.sl_atr_mult * float(pd["atr"])
                    risk = entry - sl
                    self._pending_long = None
                    if risk > 0:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="trendline_break_retest_v3",
                            symbol=getattr(store, "symbol", ""),
                            side="long",
                            entry=entry,
                            sl=sl,
                            tp=entry + self.cfg.rr * risk,
                            reason=f"tlb3_long t={int(pd['touches'])}",
                        )

        if self._pending_short is not None:
            pd = self._pending_short
            if idx > int(pd["expire_idx"]):
                self._pending_short = None
            else:
                line_now = self._line_px(float(pd["m"]), float(pd["b"]), idx)
                touched = h >= line_now - self.cfg.retest_pullback_atr * float(pd["atr"])
                rejected = c < line_now and c < o and body_frac >= self.cfg.retest_min_body_frac
                if touched and rejected:
                    entry = c
                    sl = max(float(pd["cons_hi"]), line_now) + self.cfg.sl_atr_mult * float(pd["atr"])
                    risk = sl - entry
                    self._pending_short = None
                    if risk > 0:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="trendline_break_retest_v3",
                            symbol=getattr(store, "symbol", ""),
                            side="short",
                            entry=entry,
                            sl=sl,
                            tp=entry - self.cfg.rr * risk,
                            reason=f"tlb3_short t={int(pd['touches'])}",
                        )

        cons_n = max(10, int(self.cfg.consolidation_bars))
        cons_hi = max(self._h[-cons_n:])
        cons_lo = min(self._l[-cons_n:])
        if (cons_hi - cons_lo) / atr_now > self.cfg.max_cons_range_atr:
            return None

        left = len(self._c) - self.cfg.lookback_bars
        right = len(self._c) - 2
        if right <= left:
            return None

        highs: List[Tuple[int, float]] = []
        lows: List[Tuple[int, float]] = []
        for i in range(left, right + 1):
            if self._is_swing_high(i):
                highs.append((i, self._h[i]))
            if self._is_swing_low(i):
                lows.append((i, self._l[i]))

        tol = self.cfg.touch_tol_atr * atr_now
        vol_sma = _sma(self._v, self.cfg.vol_sma_bars)
        vol_ok = math.isfinite(vol_sma) and vol_sma > 0 and self._v[idx] >= self.cfg.vol_breakout_mult * vol_sma
        lb = max(6, int(self.cfg.bos_lookback_bars))
        bos_hi = max(self._h[-lb - 1:-1])
        bos_lo = min(self._l[-lb - 1:-1])

        if len(highs) >= self.cfg.min_touches:
            h1, h2 = highs[-2], highs[-1]
            if h2[1] < h1[1]:
                m, b = self._line(h1[0], h1[1], h2[0], h2[1])
                touches = sum(1 for i, p in highs if abs(p - self._line_px(m, b, i)) <= tol)
                if touches >= self.cfg.min_touches:
                    line_prev = self._line_px(m, b, right)
                    line_cur = self._line_px(m, b, idx)
                    ext = self._c[idx] - line_cur
                    broke_line = self._c[idx] > line_cur + self.cfg.breakout_atr_mult * atr_now
                    broke_struct = self._c[idx] > bos_hi + self.cfg.bos_atr_mult * atr_now
                    was_under = self._c[right] <= line_prev + self.cfg.breakout_atr_mult * atr_now
                    if was_under and broke_line and broke_struct and ext >= self.cfg.min_breakout_ext_atr * atr_now and vol_ok:
                        self._pending_long = {
                            "m": m,
                            "b": b,
                            "atr": atr_now,
                            "cons_lo": cons_lo,
                            "touches": touches,
                            "expire_idx": idx + max(2, int(self.cfg.retest_window_bars)),
                        }

        if len(lows) >= self.cfg.min_touches:
            l1, l2 = lows[-2], lows[-1]
            if l2[1] > l1[1]:
                m, b = self._line(l1[0], l1[1], l2[0], l2[1])
                touches = sum(1 for i, p in lows if abs(p - self._line_px(m, b, i)) <= tol)
                if touches >= self.cfg.min_touches:
                    line_prev = self._line_px(m, b, right)
                    line_cur = self._line_px(m, b, idx)
                    ext = line_cur - self._c[idx]
                    broke_line = self._c[idx] < line_cur - self.cfg.breakout_atr_mult * atr_now
                    broke_struct = self._c[idx] < bos_lo - self.cfg.bos_atr_mult * atr_now
                    was_over = self._c[right] >= line_prev - self.cfg.breakout_atr_mult * atr_now
                    if was_over and broke_line and broke_struct and ext >= self.cfg.min_breakout_ext_atr * atr_now and vol_ok:
                        self._pending_short = {
                            "m": m,
                            "b": b,
                            "atr": atr_now,
                            "cons_hi": cons_hi,
                            "touches": touches,
                            "expire_idx": idx + max(2, int(self.cfg.retest_window_bars)),
                        }
        return None
