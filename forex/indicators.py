from __future__ import annotations

from math import sqrt
from typing import Iterable, List


def sma(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)


def stddev(values: Iterable[float]) -> float:
    vals = list(values)
    if len(vals) < 2:
        return 0.0
    m = sma(vals)
    var = sum((v - m) * (v - m) for v in vals) / len(vals)
    return sqrt(max(0.0, var))


def ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return float("nan")
    trs = []
    for i in range(-period, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / max(1, len(trs))


def rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if losses <= 1e-12:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))
