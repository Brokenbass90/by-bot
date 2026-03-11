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
class StructureShiftV1Config:
    swing_n: int = 3
    piv_lookback: int = 220
    atr_period: int = 14

    trend_ema_fast: int = 48
    trend_ema_slow: int = 144
    trend_min_gap_pct: float = 0.20
    trend_min_slope_pct: float = 0.10

    bos_atr_mult: float = 0.18
    pullback_window_bars: int = 14
    pullback_atr_mult: float = 0.60
    reject_min_body_frac: float = 0.22

    sl_atr_mult: float = 1.10
    rr: float = 1.9
    cooldown_bars: int = 50
    max_signals_per_day: int = 1


class StructureShiftV1Strategy:
    """CHOCH/BOS + pullback + continuation."""

    def __init__(self, cfg: Optional[StructureShiftV1Config] = None):
        self.cfg = cfg or StructureShiftV1Config()
        self.cfg.swing_n = _env_int("SS1_SWING_N", self.cfg.swing_n)
        self.cfg.piv_lookback = _env_int("SS1_PIV_LOOKBACK", self.cfg.piv_lookback)
        self.cfg.atr_period = _env_int("SS1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.trend_ema_fast = _env_int("SS1_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("SS1_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_min_gap_pct = _env_float("SS1_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.trend_min_slope_pct = _env_float("SS1_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.bos_atr_mult = _env_float("SS1_BOS_ATR_MULT", self.cfg.bos_atr_mult)
        self.cfg.pullback_window_bars = _env_int("SS1_PULLBACK_WINDOW_BARS", self.cfg.pullback_window_bars)
        self.cfg.pullback_atr_mult = _env_float("SS1_PULLBACK_ATR_MULT", self.cfg.pullback_atr_mult)
        self.cfg.reject_min_body_frac = _env_float("SS1_REJECT_MIN_BODY_FRAC", self.cfg.reject_min_body_frac)
        self.cfg.sl_atr_mult = _env_float("SS1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("SS1_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("SS1_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("SS1_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

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
        need = max(self.cfg.trend_ema_slow + 10, 220)
        if len(self._c) < need:
            return 1
        sampled = self._c[::12]  # ~1h proxy on 5m feed
        if len(sampled) < self.cfg.trend_ema_slow + 8:
            return 1
        ef = _ema(sampled, self.cfg.trend_ema_fast)
        es = _ema(sampled, self.cfg.trend_ema_slow)
        es_prev = _ema(sampled[:-4], self.cfg.trend_ema_slow)
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

        need = max(self.cfg.piv_lookback + self.cfg.swing_n * 2 + 10, self.cfg.atr_period + 40)
        if len(self._c) < need:
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None
        idx = len(self._c) - 1
        bias = self._trend_bias()
        rng = max(1e-12, h - l)
        body_frac = abs(c - o) / rng

        if self._pending_long is not None:
            pd = self._pending_long
            if idx > int(pd["expire_i"]):
                self._pending_long = None
            else:
                zone = float(pd["zone"])
                touched = l <= zone + self.cfg.pullback_atr_mult * float(pd["atr"])
                rejected = c > zone and c > o and body_frac >= self.cfg.reject_min_body_frac
                if touched and rejected and bias != 0:
                    sl = min(float(pd["swing_lo"]), l) - self.cfg.sl_atr_mult * float(pd["atr"])
                    risk = c - sl
                    self._pending_long = None
                    if risk > 0:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="structure_shift_v1",
                            symbol=getattr(store, "symbol", ""),
                            side="long",
                            entry=c,
                            sl=sl,
                            tp=c + self.cfg.rr * risk,
                            reason="ss1_long_pullback_after_bos",
                        )

        if self._pending_short is not None:
            pd = self._pending_short
            if idx > int(pd["expire_i"]):
                self._pending_short = None
            else:
                zone = float(pd["zone"])
                touched = h >= zone - self.cfg.pullback_atr_mult * float(pd["atr"])
                rejected = c < zone and c < o and body_frac >= self.cfg.reject_min_body_frac
                if touched and rejected and bias != 2:
                    sl = max(float(pd["swing_hi"]), h) + self.cfg.sl_atr_mult * float(pd["atr"])
                    risk = sl - c
                    self._pending_short = None
                    if risk > 0:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return TradeSignal(
                            strategy="structure_shift_v1",
                            symbol=getattr(store, "symbol", ""),
                            side="short",
                            entry=c,
                            sl=sl,
                            tp=c - self.cfg.rr * risk,
                            reason="ss1_short_pullback_after_bos",
                        )

        highs, lows = self._recent_pivots()
        if len(highs) < 2 or len(lows) < 2:
            return None

        last_hi = highs[-1][1]
        prev_hi = highs[-2][1]
        last_lo = lows[-1][1]
        prev_lo = lows[-2][1]

        # Long setup: bearish structure (lower highs/lows) then bullish BOS.
        bear_struct = last_hi < prev_hi and last_lo < prev_lo
        bull_bos = c > last_hi + self.cfg.bos_atr_mult * atr_now
        if bear_struct and bull_bos and bias != 0:
            self._pending_long = {
                "zone": last_hi,
                "atr": atr_now,
                "swing_lo": last_lo,
                "expire_i": idx + max(3, int(self.cfg.pullback_window_bars)),
            }

        # Short setup: bullish structure (higher highs/lows) then bearish BOS.
        bull_struct = last_hi > prev_hi and last_lo > prev_lo
        bear_bos = c < last_lo - self.cfg.bos_atr_mult * atr_now
        if bull_struct and bear_bos and bias != 2:
            self._pending_short = {
                "zone": last_lo,
                "atr": atr_now,
                "swing_hi": last_hi,
                "expire_i": idx + max(3, int(self.cfg.pullback_window_bars)),
            }

        return None
