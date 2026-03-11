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


def _ema(vals: List[float], period: int) -> float:
    if not vals or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = vals[0]
    for x in vals[1:]:
        e = x * k + e * (1.0 - k)
    return e


def _atr(h: List[float], l: List[float], c: List[float], period: int) -> float:
    if period <= 0 or len(c) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return sum(trs) / float(period) if trs else float("nan")


@dataclass
class StructureShiftV2Config:
    swing_n: int = 3
    piv_lookback: int = 260
    atr_period: int = 14

    trend_ema_fast: int = 72
    trend_ema_slow: int = 200
    trend_min_gap_pct: float = 0.24
    trend_min_slope_pct: float = 0.12

    bos_atr_mult: float = 0.25
    bos_min_body_frac: float = 0.42
    retest_window_bars: int = 18
    retest_touch_atr: float = 0.45
    continuation_atr: float = 0.16
    reject_min_body_frac: float = 0.26
    impulse_min_body_frac: float = 0.38

    sl_atr_mult: float = 1.15
    rr: float = 2.0
    cooldown_bars: int = 64
    max_signals_per_day: int = 1
    min_atr_pct: float = 0.20
    max_atr_pct: float = 3.20


class StructureShiftV2Strategy:
    """BOS + retest + continuation-break (stricter than v1)."""

    def __init__(self, cfg: Optional[StructureShiftV2Config] = None):
        self.cfg = cfg or StructureShiftV2Config()
        self.cfg.swing_n = _env_int("SS2_SWING_N", self.cfg.swing_n)
        self.cfg.piv_lookback = _env_int("SS2_PIV_LOOKBACK", self.cfg.piv_lookback)
        self.cfg.atr_period = _env_int("SS2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.trend_ema_fast = _env_int("SS2_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("SS2_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_min_gap_pct = _env_float("SS2_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.trend_min_slope_pct = _env_float("SS2_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.bos_atr_mult = _env_float("SS2_BOS_ATR_MULT", self.cfg.bos_atr_mult)
        self.cfg.bos_min_body_frac = _env_float("SS2_BOS_MIN_BODY_FRAC", self.cfg.bos_min_body_frac)
        self.cfg.retest_window_bars = _env_int("SS2_RETEST_WINDOW_BARS", self.cfg.retest_window_bars)
        self.cfg.retest_touch_atr = _env_float("SS2_RETEST_TOUCH_ATR", self.cfg.retest_touch_atr)
        self.cfg.continuation_atr = _env_float("SS2_CONTINUATION_ATR", self.cfg.continuation_atr)
        self.cfg.reject_min_body_frac = _env_float("SS2_REJECT_MIN_BODY_FRAC", self.cfg.reject_min_body_frac)
        self.cfg.impulse_min_body_frac = _env_float("SS2_IMPULSE_MIN_BODY_FRAC", self.cfg.impulse_min_body_frac)
        self.cfg.sl_atr_mult = _env_float("SS2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("SS2_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("SS2_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("SS2_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.min_atr_pct = _env_float("SS2_MIN_ATR_PCT", self.cfg.min_atr_pct)
        self.cfg.max_atr_pct = _env_float("SS2_MAX_ATR_PCT", self.cfg.max_atr_pct)

        self._o: List[float] = []
        self._h: List[float] = []
        self._l: List[float] = []
        self._c: List[float] = []
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

    def _trend_bias(self) -> int:
        # 2 bull, 0 bear, 1 neutral
        need = max(self.cfg.trend_ema_slow + 16, 260)
        if len(self._c) < need:
            return 1
        sampled = self._c[::12]  # 1h proxy from 5m stream
        if len(sampled) < self.cfg.trend_ema_slow + 10:
            return 1
        ef = _ema(sampled, self.cfg.trend_ema_fast)
        es = _ema(sampled, self.cfg.trend_ema_slow)
        es_prev = _ema(sampled[:-6], self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)):
            return 1
        px = sampled[-1]
        if px <= 0:
            return 1
        gap_pct = abs(ef - es) / px * 100.0
        slope_pct = (es - es_prev) / max(1e-12, abs(es_prev)) * 100.0
        if gap_pct < self.cfg.trend_min_gap_pct:
            return 1
        if ef > es and slope_pct >= self.cfg.trend_min_slope_pct:
            return 2
        if ef < es and slope_pct <= -self.cfg.trend_min_slope_pct:
            return 0
        return 1

    def _recent_pivots(self) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
        left = max(0, len(self._c) - self.cfg.piv_lookback)
        right = len(self._c) - 2
        highs: List[Tuple[int, float]] = []
        lows: List[Tuple[int, float]] = []
        for i in range(left, right + 1):
            if self._is_swing_high(i):
                highs.append((i, self._h[i]))
            if self._is_swing_low(i):
                lows.append((i, self._l[i]))
        return highs, lows

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (store, v)
        self._o.append(o)
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

        need = max(self.cfg.piv_lookback + self.cfg.swing_n * 2 + 16, self.cfg.atr_period + 48)
        if len(self._c) < need:
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None
        atr_pct = atr_now / max(1e-12, abs(c)) * 100.0
        if atr_pct < self.cfg.min_atr_pct or atr_pct > self.cfg.max_atr_pct:
            return None

        bias = self._trend_bias()
        idx = len(self._c) - 1
        rng = max(1e-12, h - l)
        body_frac = abs(c - o) / rng

        if self._pending_long is not None:
            pd = self._pending_long
            if idx > int(pd["expire_i"]):
                self._pending_long = None
            else:
                zone = float(pd["zone"])
                cont = float(pd["cont"])
                touched = l <= zone + self.cfg.retest_touch_atr * float(pd["atr"])
                rejected = c > zone and c > o and body_frac >= self.cfg.reject_min_body_frac
                continuation = c >= cont + self.cfg.continuation_atr * float(pd["atr"])
                if touched and rejected and continuation and bias == 2 and body_frac >= self.cfg.impulse_min_body_frac:
                    sl = min(float(pd["swing_lo"]), l) - self.cfg.sl_atr_mult * float(pd["atr"])
                    risk = c - sl
                    self._pending_long = None
                    if risk > 0:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="structure_shift_v2",
                            symbol=getattr(store, "symbol", ""),
                            side="long",
                            entry=c,
                            sl=sl,
                            tp=c + self.cfg.rr * risk,
                            reason="ss2_long_bos_retest_cont",
                        )

        if self._pending_short is not None:
            pd = self._pending_short
            if idx > int(pd["expire_i"]):
                self._pending_short = None
            else:
                zone = float(pd["zone"])
                cont = float(pd["cont"])
                touched = h >= zone - self.cfg.retest_touch_atr * float(pd["atr"])
                rejected = c < zone and c < o and body_frac >= self.cfg.reject_min_body_frac
                continuation = c <= cont - self.cfg.continuation_atr * float(pd["atr"])
                if touched and rejected and continuation and bias == 0 and body_frac >= self.cfg.impulse_min_body_frac:
                    sl = max(float(pd["swing_hi"]), h) + self.cfg.sl_atr_mult * float(pd["atr"])
                    risk = sl - c
                    self._pending_short = None
                    if risk > 0:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="structure_shift_v2",
                            symbol=getattr(store, "symbol", ""),
                            side="short",
                            entry=c,
                            sl=sl,
                            tp=c - self.cfg.rr * risk,
                            reason="ss2_short_bos_retest_cont",
                        )

        highs, lows = self._recent_pivots()
        if len(highs) < 2 or len(lows) < 2:
            return None

        last_hi = highs[-1][1]
        prev_hi = highs[-2][1]
        last_lo = lows[-1][1]
        prev_lo = lows[-2][1]

        bear_struct = last_hi < prev_hi and last_lo < prev_lo
        bull_struct = last_hi > prev_hi and last_lo > prev_lo

        # Fresh BOS only: require cross through BOS level on this bar, not already above/below.
        prev_c = self._c[-2]
        bull_bos_level = last_hi + self.cfg.bos_atr_mult * atr_now
        bear_bos_level = last_lo - self.cfg.bos_atr_mult * atr_now
        bull_bos = (prev_c <= bull_bos_level) and (c > bull_bos_level)
        bear_bos = (prev_c >= bear_bos_level) and (c < bear_bos_level)
        bos_body_ok = body_frac >= self.cfg.bos_min_body_frac

        # Avoid re-arming pending setup every bar; only arm when empty.
        if self._pending_long is None and bear_struct and bull_bos and bos_body_ok and bias == 2:
            self._pending_long = {
                "zone": last_hi,
                "cont": h,
                "atr": atr_now,
                "swing_lo": last_lo,
                "expire_i": idx + max(4, int(self.cfg.retest_window_bars)),
            }

        if self._pending_short is None and bull_struct and bear_bos and bos_body_ok and bias == 0:
            self._pending_short = {
                "zone": last_lo,
                "cont": l,
                "atr": atr_now,
                "swing_hi": last_hi,
                "expire_i": idx + max(4, int(self.cfg.retest_window_bars)),
            }

        return None
