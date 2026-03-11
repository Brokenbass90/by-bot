from __future__ import annotations

import math
from typing import List

from .indicators import ema


def atr_pct(atr_value: float, close: float) -> float:
    if not math.isfinite(atr_value) or atr_value <= 0 or not math.isfinite(close) or close == 0:
        return float("nan")
    return abs(atr_value / close) * 100.0


def ema_gap_atr(closes: List[float], ema_fast: int, ema_slow: int, atr_value: float) -> float:
    if len(closes) < max(ema_slow + 5, ema_fast * 2):
        return float("nan")
    if not math.isfinite(atr_value) or atr_value <= 0:
        return float("nan")
    ef = ema(closes[-(ema_fast * 2) :], ema_fast)
    es = ema(closes[-(ema_slow + 5) :], ema_slow)
    if not (math.isfinite(ef) and math.isfinite(es)):
        return float("nan")
    return abs(ef - es) / atr_value


def slow_slope_atr(closes: List[float], ema_slow: int, slope_bars: int, atr_value: float) -> float:
    slope_bars = max(1, int(slope_bars))
    if len(closes) < ema_slow + slope_bars + 5:
        return float("nan")
    if not math.isfinite(atr_value) or atr_value <= 0:
        return float("nan")
    cur_slice = closes[-(ema_slow + 5) :]
    prev_slice = closes[-(ema_slow + slope_bars + 5) : -slope_bars]
    cur = ema(cur_slice, ema_slow)
    prev = ema(prev_slice, ema_slow)
    if not (math.isfinite(cur) and math.isfinite(prev)):
        return float("nan")
    return abs(cur - prev) / atr_value
