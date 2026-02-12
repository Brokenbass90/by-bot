#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal


def atr(candles: List[Tuple[float, float, float, float]], period: int = 14) -> float:
    """candles: list of (o,h,l,c)"""
    if len(candles) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        o, h, l, c = candles[i]
        _, _, _, prev_c = candles[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return sum(trs) / len(trs)


def ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def wick_fraction(o: float, h: float, l: float, c: float, side: str) -> float:
    rng = max(1e-12, h - l)
    if side == "long":
        return max(0.0, min(1.0, (min(o, c) - l) / rng))
    return max(0.0, min(1.0, (h - max(o, c)) / rng))


@dataclass
class BounceBTV2Config:
    atr_period_1h: int = 14
    swing_lookback_1h: int = 72
    entry_zone_atr: float = 0.35
    wick_frac_min: float = 0.30
    sl_atr_mult: float = 0.55
    rr: float = 1.4
    min_rr_to_level: float = 1.0
    ema_fast_1h: int = 20
    ema_slow_1h: int = 50
    allow_countertrend: bool = False


class BounceBTV2Strategy:
    """Bounce v2: swing levels + candle rejection + optional trend filter.

    This is a cleaner backtest-friendly approximation of live bounce.
    """

    def __init__(self, cfg: Optional[BounceBTV2Config] = None):
        self.cfg = cfg or BounceBTV2Config()

    @staticmethod
    def _swing_levels(highs: List[float], lows: List[float], window: int = 2) -> Tuple[List[float], List[float]]:
        swing_highs: List[float] = []
        swing_lows: List[float] = []
        n = len(highs)
        for i in range(window, n - window):
            h = highs[i]
            l = lows[i]
            if all(h > highs[i - j] for j in range(1, window + 1)) and all(h > highs[i + j] for j in range(1, window + 1)):
                swing_highs.append(h)
            if all(l < lows[i - j] for j in range(1, window + 1)) and all(l < lows[i + j] for j in range(1, window + 1)):
                swing_lows.append(l)
        return swing_highs, swing_lows

    @staticmethod
    def _cluster(levels: List[float], step: float) -> List[float]:
        if not levels:
            return []
        if step <= 0 or not math.isfinite(step):
            return sorted(levels)
        buckets = {}
        for x in levels:
            k = round(x / step)
            buckets.setdefault(k, []).append(x)
        out = [sum(v) / len(v) for v in buckets.values()]
        return sorted(out)

    def _trend_bias(self, closes_1h: List[float]) -> Optional[int]:
        # 2 = bull, 0 = bear, 1 = neutral
        if len(closes_1h) < max(self.cfg.ema_fast_1h, self.cfg.ema_slow_1h) + 5:
            return None
        ef = ema(closes_1h[-(self.cfg.ema_fast_1h * 3):], self.cfg.ema_fast_1h)
        es = ema(closes_1h[-(self.cfg.ema_slow_1h * 3):], self.cfg.ema_slow_1h)
        if not math.isfinite(ef) or not math.isfinite(es):
            return None
        if ef > es:
            return 2
        if ef < es:
            return 0
        return 1

    def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        symbol = getattr(store, "symbol", None) or ""

        last_5m = getattr(store, "last_5m_ohlc", None)
        if callable(last_5m):
            last_5m = last_5m()

        candles_1h_ohlc = getattr(store, "candles_1h_ohlc", None)
        if callable(candles_1h_ohlc):
            candles_1h_ohlc = candles_1h_ohlc()
        if candles_1h_ohlc is None:
            candles_1h_ohlc = []

        if not symbol or last_5m is None or not candles_1h_ohlc:
            return None
        if len(candles_1h_ohlc) < max(self.cfg.swing_lookback_1h, self.cfg.atr_period_1h + 2):
            return None

        o5, h5, l5, c5 = last_5m

        recent_1h = candles_1h_ohlc[-self.cfg.swing_lookback_1h:]
        highs = [h for (_, h, _, _) in recent_1h]
        lows = [l for (_, _, l, _) in recent_1h]
        closes = [c for (_, _, _, c) in recent_1h]

        a = atr(candles_1h_ohlc[-(self.cfg.atr_period_1h + 2):], self.cfg.atr_period_1h)
        if not math.isfinite(a) or a <= 0:
            return None

        swing_highs, swing_lows = self._swing_levels(highs, lows, window=2)
        step = a * 0.25
        res_levels = self._cluster(swing_highs, step)
        sup_levels = self._cluster(swing_lows, step)

        supports = [x for x in sup_levels if x <= c5]
        resists = [x for x in res_levels if x >= c5]

        support = max(supports) if supports else None
        resist = min(resists) if resists else None

        zone = self.cfg.entry_zone_atr * a

        bias = self._trend_bias(closes)
        if not self.cfg.allow_countertrend and bias is None:
            return None

        # LONG bounce from support
        if support is not None and abs(c5 - support) <= zone:
            if (not self.cfg.allow_countertrend) and bias == 0:
                return None
            wf = wick_fraction(o5, h5, l5, c5, "long")
            if wf >= self.cfg.wick_frac_min and c5 > o5:
                entry = c5
                sl = support - self.cfg.sl_atr_mult * a
                if sl < entry:
                    risk = entry - sl
                    # target: nearest resistance if RR ok, else fixed rr
                    tp = entry + self.cfg.rr * risk
                    if resist is not None:
                        rr_to_level = (resist - entry) / risk
                        if rr_to_level >= self.cfg.min_rr_to_level:
                            tp = resist
                    sig = TradeSignal(
                        strategy="bounce_v2",
                        symbol=symbol,
                        side="long",
                        entry=entry,
                        sl=sl,
                        tp=tp,
                        reason=f"bounce_v2 support {support:.6g}",
                    )
                    return sig if sig.validate() else None

        # SHORT bounce from resistance
        if resist is not None and abs(resist - c5) <= zone:
            if (not self.cfg.allow_countertrend) and bias == 2:
                return None
            wf = wick_fraction(o5, h5, l5, c5, "short")
            if wf >= self.cfg.wick_frac_min and c5 < o5:
                entry = c5
                sl = resist + self.cfg.sl_atr_mult * a
                if sl > entry:
                    risk = sl - entry
                    tp = entry - self.cfg.rr * risk
                    if support is not None:
                        rr_to_level = (entry - support) / risk
                        if rr_to_level >= self.cfg.min_rr_to_level:
                            tp = support
                    sig = TradeSignal(
                        strategy="bounce_v2",
                        symbol=symbol,
                        side="short",
                        entry=entry,
                        sl=sl,
                        tp=tp,
                        reason=f"bounce_v2 resist {resist:.6g}",
                    )
                    return sig if sig.validate() else None

        return None
