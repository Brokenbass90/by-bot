from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional

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


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def atr(values_h: List[float], values_l: List[float], values_c: List[float], period: int = 14) -> float:
    if len(values_c) < period + 1:
        return float("nan")
    trs = []
    for i in range(-period, 0):
        h = values_h[i]
        l = values_l[i]
        pc = values_c[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / max(1, len(trs))


@dataclass
class MomentumConfig:
    interval_min: int = 5
    lookback_min: int = 60
    move_threshold_pct: float = 0.8
    pullback_max_pct: float = 0.3
    ema_period: int = 20
    atr_period: int = 14
    sl_atr_mult: float = 1.0
    rr: float = 1.4
    cooldown_bars: int = 12
    allow_longs: bool = True
    allow_shorts: bool = True


class MomentumContinuationStrategy:
    """Simple momentum-continuation.

    Detects a strong move over a lookback window, then enters on shallow pullback
    while price stays above/below EMA.
    """

    def __init__(self, cfg: Optional[MomentumConfig] = None):
        self.cfg = cfg or MomentumConfig()

        self.cfg.lookback_min = _env_int("MOMO_LOOKBACK_MIN", self.cfg.lookback_min)
        self.cfg.move_threshold_pct = _env_float("MOMO_MOVE_THRESHOLD_PCT", self.cfg.move_threshold_pct)
        self.cfg.pullback_max_pct = _env_float("MOMO_PULLBACK_MAX_PCT", self.cfg.pullback_max_pct)
        self.cfg.ema_period = _env_int("MOMO_EMA_PERIOD", self.cfg.ema_period)
        self.cfg.atr_period = _env_int("MOMO_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.sl_atr_mult = _env_float("MOMO_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("MOMO_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("MOMO_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.allow_longs = _env_bool("MOMO_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("MOMO_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._closes: List[float] = []
        self._highs: List[float] = []
        self._lows: List[float] = []
        self._cooldown = 0

    def on_bar(self, symbol: str, o: float, h: float, l: float, c: float) -> Optional[TradeSignal]:
        self._closes.append(c)
        self._highs.append(h)
        self._lows.append(l)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        bars_in_window = max(2, int(self.cfg.lookback_min / self.cfg.interval_min))
        if len(self._closes) < bars_in_window + self.cfg.ema_period:
            return None

        base = self._closes[-bars_in_window - 1]
        if base <= 0:
            return None

        move_pct = (c / base - 1.0) * 100.0
        ema_now = ema(self._closes[-(self.cfg.ema_period * 2):], self.cfg.ema_period)
        atr_now = atr(self._highs, self._lows, self._closes, self.cfg.atr_period)

        if not math.isfinite(ema_now) or not math.isfinite(atr_now):
            return None

        # Long continuation
        if self.cfg.allow_longs and move_pct >= self.cfg.move_threshold_pct:
            pullback_pct = (max(self._highs[-bars_in_window:]) - c) / max(1e-12, c) * 100.0
            if pullback_pct <= self.cfg.pullback_max_pct and c > ema_now:
                sl = c - self.cfg.sl_atr_mult * atr_now
                if sl >= c:
                    return None
                tp = c + self.cfg.rr * (c - sl)
                self._cooldown = self.cfg.cooldown_bars
                return TradeSignal(
                    strategy="momentum",
                    symbol=symbol,
                    side="long",
                    entry=c,
                    sl=sl,
                    tp=tp,
                    reason=f"momo_long {move_pct:.2f}%/{self.cfg.lookback_min}m",
                )

        # Short continuation
        if self.cfg.allow_shorts and move_pct <= -self.cfg.move_threshold_pct:
            pullback_pct = (c - min(self._lows[-bars_in_window:])) / max(1e-12, c) * 100.0
            if pullback_pct <= self.cfg.pullback_max_pct and c < ema_now:
                sl = c + self.cfg.sl_atr_mult * atr_now
                if sl <= c:
                    return None
                tp = c - self.cfg.rr * (sl - c)
                self._cooldown = self.cfg.cooldown_bars
                return TradeSignal(
                    strategy="momentum",
                    symbol=symbol,
                    side="short",
                    entry=c,
                    sl=sl,
                    tp=tp,
                    reason=f"momo_short {move_pct:.2f}%/{self.cfg.lookback_min}m",
                )

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
