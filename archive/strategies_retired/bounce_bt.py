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


def wick_fraction(o: float, h: float, l: float, c: float, side: str) -> float:
    rng = max(1e-12, h - l)
    if side == "long":
        # lower wick fraction
        return max(0.0, min(1.0, (min(o, c) - l) / rng))
    else:
        # upper wick fraction
        return max(0.0, min(1.0, (h - max(o, c)) / rng))


@dataclass
class BounceBTConfig:
    # Use 1h structure + 5m confirmation
    atr_period_1h: int = 14
    swing_lookback_1h: int = 72  # last N hours to form levels
    entry_zone_atr: float = 0.35  # how close to level (in ATR units)

    wick_frac_min: float = 0.25

    sl_atr_mult: float = 0.55
    rr: float = 1.5


class BounceBTStrategy:
    """Backtest-oriented bounce strategy.

    Goal: approximate the live bounce idea without requiring the live LevelsService.
    It forms rough S/R from recent swing highs/lows on 1h candles, then confirms on 5m.
    """

    def __init__(self, cfg: Optional[BounceBTConfig] = None):
        self.cfg = cfg or BounceBTConfig()

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

    def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        """Backtest-compatible entry point.

        The runner invokes strategies as maybe_signal(store, ts_ms, last_price).
        We derive the required inputs from KlineStore.
        """

        symbol = getattr(store, "symbol", None) or ""

        # KlineStore exposes helpers as callables; other runners may pass raw data.
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

        swing_highs, swing_lows = self._swing_levels(highs, lows, window=2)

        a = atr(candles_1h_ohlc[-(self.cfg.atr_period_1h + 2):], self.cfg.atr_period_1h)
        if not math.isfinite(a) or a <= 0:
            return None

        # cluster swings to reduce noise
        step = a * 0.25
        res_levels = self._cluster(swing_highs, step)
        sup_levels = self._cluster(swing_lows, step)

        # nearest levels around current price
        supports = [x for x in sup_levels if x <= c5]
        resists = [x for x in res_levels if x >= c5]

        support = max(supports) if supports else None
        resist = min(resists) if resists else None

        zone = self.cfg.entry_zone_atr * a

        # LONG bounce from support
        if support is not None and abs(c5 - support) <= zone:
            wf = wick_fraction(o5, h5, l5, c5, "long")
            if wf >= self.cfg.wick_frac_min and c5 > o5:
                entry = c5
                sl = support - self.cfg.sl_atr_mult * a
                if sl < entry:
                    tp = entry + self.cfg.rr * (entry - sl)
                    sig = TradeSignal(
                        strategy="bounce",
                        symbol=symbol,
                        side="long",
                        entry=entry,
                        sl=sl,
                        tp=tp,
                        reason=f"bounce near support {support:.6g} (ATR={a:.6g})",
                    )
                    return sig if sig.validate() else None

        # SHORT bounce from resistance
        if resist is not None and abs(resist - c5) <= zone:
            wf = wick_fraction(o5, h5, l5, c5, "short")
            if wf >= self.cfg.wick_frac_min and c5 < o5:
                entry = c5
                sl = resist + self.cfg.sl_atr_mult * a
                if sl > entry:
                    tp = entry - self.cfg.rr * (sl - entry)
                    if tp > 0:
                        sig = TradeSignal(
                            strategy="bounce",
                            symbol=symbol,
                            side="short",
                            entry=entry,
                            sl=sl,
                            tp=tp,
                            reason=f"bounce near resist {resist:.6g} (ATR={a:.6g})",
                        )
                        return sig if sig.validate() else None

        return None
