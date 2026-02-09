from __future__ import annotations

import math
from typing import List, Iterable, Optional

import numpy as np


def atr_pct_from_ohlc(
    h: List[float],
    l: List[float],
    c: List[float],
    period: int = 14,
    fallback: float = 0.8,
) -> float:
    """
    ATR как процент от цены (simple average TR%).
    Поведение совместимо с старой реализацией:
    - если баров мало -> возвращаем fallback.
    """
    if len(c) < period + 1 or len(h) < period or len(l) < period:
        return float(fallback)

    trs: List[float] = []
    for i in range(1, period + 1):
        pc = c[-i - 1]
        tr = max(h[-i] - l[-i], abs(h[-i] - pc), abs(l[-i] - pc))
        trs.append(tr / max(1e-12, pc))
    return 100.0 * sum(trs) / float(period)


def ema(series: Iterable[float], length: int) -> float:
    """
    Классическая EMA по всем значениям.
    Поведение повторяет _ema из sr_bounce: если список пустой -> 0.0.
    """
    vals = list(series)
    if not vals or length <= 0:
        return 0.0
    alpha = 2.0 / (length + 1.0)
    val = vals[0]
    for x in vals[1:]:
        val = alpha * x + (1.0 - alpha) * val
    return float(val)


def rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """
    RSI по numpy.diff, совместимо с calc_rsi из smart_pump_reversal_bot.
    """
    if len(closes) < period + 1:
        return None
    d = np.diff(closes)
    ups = d[d > 0]
    downs = -d[d < 0]
    ag = float(np.mean(ups)) if len(ups) else 0.0
    al = float(np.mean(downs)) if len(downs) else 0.0
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - (100.0 / (1.0 + rs))


def ema_incremental(prev: Optional[float], price: float, length: int) -> float:
    """
    Инкрементальная EMA (как ema_val в smart_pump_reversal_bot).
    """
    if length <= 0:
        return float(price)
    if prev is None:
        return float(price)
    k = 2.0 / (length + 1.0)
    return float(prev + k * (price - prev))


def candle_pattern(open_p: float, close_p: float, high_p: float, low_p: float) -> Optional[str]:
    """
    Упрощённые паттерны: Doji / Hammer / InvertedPin.
    Копирует старую реализацию candle_pattern из smart_pump_reversal_bot.
    """
    rng = max(1e-9, high_p - low_p)
    body = abs(close_p - open_p)
    upper = high_p - max(open_p, close_p)
    lower = min(open_p, close_p) - low_p
    if body / rng < 0.1:
        return "Doji"
    if lower > 2 * body and upper < body:
        return "Hammer"
    if upper > 2 * body and lower < body:
        return "InvertedPin"
    return None


def engulfing(prev_o: Optional[float], prev_c: Optional[float], o: float, c: float) -> bool:
    """
    Медвежье поглощение (поведение как в smart_pump_reversal_bot.engulfing).
    """
    if prev_o is None or prev_c is None:
        return False
    if c < o and prev_c > prev_o and o >= prev_c and c <= prev_o:
        return True
    return False


def trade_quality(trades: list, q_total: float) -> float:
    """
    Оценка «качества» окна: топ-20% сделок по объёму и
    доля из них, превышающих max(3000 USDT, 2% от объёма окна).

    Полностью совместимо с trade_quality из smart_pump_reversal_bot.
    """
    if not trades or q_total <= 0:
        return 0.0
    vals = sorted((t[2] for t in trades), reverse=True)
    k = max(1, int(len(vals) * 0.2))
    thr = max(3000.0, 0.02 * q_total)
    big = sum(1 for v in vals[:k] if v >= thr)
    return big / max(1, len(trades))


