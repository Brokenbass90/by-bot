#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from .signals import TradeSignal


def ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values: List[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        ch = values[i] - values[i - 1]
        if ch > 0:
            gains += ch
        else:
            losses -= ch
    if gains == 0 and losses == 0:
        return 50.0
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


@dataclass
class PumpFadeConfig:
    interval_min: int = 5
    pump_window_min: int = 60  # lookback window to detect the pump
    pump_threshold_pct: float = 0.08  # +8% within the window
    rsi_overbought: float = 75.0
    ema_period: int = 9
    peak_lookback_min: int = 30

    stop_buffer_pct: float = 0.0025  # +0.25% above peak for shorts
    rr: float = 1.6

    cooldown_bars: int = 24  # don't re-enter for N bars after a trade


class PumpFadeStrategy:
    """Shorts a *sharp pump* after first meaningful reversal.

    This is intentionally conservative and designed for backtesting.
    You can harden it later (VWAP filters, liquidity filters, etc.).
    """

    def __init__(self, cfg: Optional[PumpFadeConfig] = None):
        self.cfg = cfg or PumpFadeConfig()
        self._closes: List[float] = []
        self._highs: List[float] = []
        self._lows: List[float] = []
        self._cooldown: int = 0
        self._pumped_flag: bool = False

    def on_bar(self, symbol: str, o: float, h: float, l: float, c: float) -> Optional[TradeSignal]:
        self._closes.append(c)
        self._highs.append(h)
        self._lows.append(l)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # need enough history
        bars_in_window = max(1, int(self.cfg.pump_window_min / self.cfg.interval_min))
        if len(self._closes) < bars_in_window + 2:
            return None

        base = self._closes[-bars_in_window - 1]
        if base <= 0:
            return None
        move_pct = (c / base) - 1.0

        # Pump detection
        if move_pct >= self.cfg.pump_threshold_pct:
            self._pumped_flag = True

        if not self._pumped_flag:
            return None

        # Reversal confirmation: close below EMA after pump AND RSI was overbought recently
        ema_now = ema(self._closes[-(self.cfg.ema_period * 4):], self.cfg.ema_period)
        rsi_now = rsi(self._closes, 14)

        peak_bars = max(2, int(self.cfg.peak_lookback_min / self.cfg.interval_min))
        peak_high = max(self._highs[-peak_bars:])

        # if price already collapsed too far, skip (avoid late entries)
        if peak_high > 0 and (peak_high - c) / peak_high > 0.08:
            self._pumped_flag = False
            return None

        if not (rsi_now >= self.cfg.rsi_overbought):
            return None

        # reversal trigger
        if math.isfinite(ema_now) and c < ema_now and c < self._closes[-2]:
            entry = c
            sl = peak_high * (1.0 + self.cfg.stop_buffer_pct)
            if sl <= entry:
                self._pumped_flag = False
                return None
            tp = entry - self.cfg.rr * (sl - entry)
            if tp <= 0:
                self._pumped_flag = False
                return None

            self._cooldown = self.cfg.cooldown_bars
            self._pumped_flag = False

            sig = TradeSignal(
                strategy="pump_fade",
                symbol=symbol,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp,
                reason=f"pump {move_pct*100:.1f}%/{self.cfg.pump_window_min}m then reversal",
            )
            return sig if sig.validate() else None

        return None

    # Backwards-compatibility: backtest.run_month calls `maybe_signal(symbol, ts_ms, o, h, l, c, v)`.
    # We keep `on_bar(symbol, o, h, l, c)` as the canonical method.
    def maybe_signal(
        self,
        symbol: str,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        _ = ts_ms
        _ = v
        return self.on_bar(symbol, o, h, l, c)
