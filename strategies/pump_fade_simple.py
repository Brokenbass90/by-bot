#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pump_fade_simple — exact baseline logic from commit e341055e.

This is the simple 190-line BASE-mode-only pump_fade strategy that produced
the original baseline result:
  baselines/pump_fade_v4c_240d/summary.csv → PF=1.883, 19 trades, DD=3.77%

Preserved verbatim (class/config renamed to avoid collisions with the archive
pump_fade.py). No exhaustion filter, no v3/v4/v5/v6, no RSI-override,
single-bar reversal confirmation (c < EMA9 AND c < prev_close).

Research-only — do NOT enable in live bot without further validation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from .signals import TradeSignal


def _pfs_ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _pfs_rsi(values: List[float], period: int = 14) -> float:
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


def _pfs_env_float(name: str, default: float) -> float:
    import os
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _pfs_env_int(name: str, default: int) -> int:
    import os
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


@dataclass
class PumpFadeSimpleConfig:
    interval_min: int = 5
    pump_window_min: int = 60       # lookback window to detect the pump
    pump_threshold_pct: float = 0.08  # +8% within the window
    rsi_overbought: float = 75.0
    ema_period: int = 9
    peak_lookback_min: int = 30

    stop_buffer_pct: float = 0.0025  # +0.25% above peak for shorts
    rr: float = 1.6

    cooldown_bars: int = 24           # don't re-enter for N bars after a trade


class PumpFadeSimpleStrategy:
    """Shorts a sharp pump after the first meaningful reversal bar.

    Exact replication of the baseline pump_fade logic at commit e341055e:
      - pump_window_min lookback for +8% move
      - _pumped_flag is sticky until trade or ENTRY_TOO_LATE
      - Entry: current close < EMA9 AND close < previous close
      - RSI must be >= rsi_overbought at entry bar
      - Stop: peak_high * (1 + stop_buffer_pct)
      - TP: entry - rr * risk
    """

    def __init__(self, cfg: Optional[PumpFadeSimpleConfig] = None):
        self.cfg = cfg or PumpFadeSimpleConfig()

        # Env overrides (same names as archive for compatibility with autoresearch specs)
        self.cfg.interval_min = _pfs_env_int("PF_INTERVAL_MIN", self.cfg.interval_min)
        self.cfg.pump_window_min = _pfs_env_int("PF_PUMP_WINDOW_MIN", self.cfg.pump_window_min)
        self.cfg.pump_threshold_pct = _pfs_env_float("PF_PUMP_THRESHOLD_PCT", self.cfg.pump_threshold_pct)
        self.cfg.rsi_overbought = _pfs_env_float("PF_RSI_OVERBOUGHT", self.cfg.rsi_overbought)
        self.cfg.ema_period = _pfs_env_int("PF_EMA_PERIOD", self.cfg.ema_period)
        self.cfg.peak_lookback_min = _pfs_env_int("PF_PEAK_LOOKBACK_MIN", self.cfg.peak_lookback_min)
        self.cfg.stop_buffer_pct = _pfs_env_float("PF_STOP_BUFFER_PCT", self.cfg.stop_buffer_pct)
        self.cfg.rr = _pfs_env_float("PF_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _pfs_env_int("PF_COOLDOWN_BARS", self.cfg.cooldown_bars)

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

        # Reversal confirmation: close below EMA after pump AND RSI overbought at entry bar
        ema_now = _pfs_ema(self._closes[-(self.cfg.ema_period * 4):], self.cfg.ema_period)
        rsi_now = _pfs_rsi(self._closes, 14)

        peak_bars = max(2, int(self.cfg.peak_lookback_min / self.cfg.interval_min))
        peak_high = max(self._highs[-peak_bars:])

        # if price already collapsed too far, skip (avoid late entries)
        if peak_high > 0 and (peak_high - c) / peak_high > 0.08:
            self._pumped_flag = False
            return None

        if not (rsi_now >= self.cfg.rsi_overbought):
            return None

        # reversal trigger: close below EMA9 and below previous close
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
                strategy="pump_fade_simple",
                symbol=symbol,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp,
                reason=f"pump {move_pct*100:.1f}%/{self.cfg.pump_window_min}m then reversal",
            )
            return sig if sig.validate() else None

        return None

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
