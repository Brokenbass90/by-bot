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
class TrendPullbackConfig:
    trend_tf: str = "60"  # 1h
    trend_ema_fast: int = 20
    trend_ema_slow: int = 50
    entry_ema_period: int = 20  # 5m EMA for pullback
    pullback_max_pct: float = 0.35
    reclaim_pct: float = 0.05
    atr_period: int = 14
    sl_atr_mult: float = 1.0
    rr: float = 1.5
    cooldown_bars: int = 12
    allow_longs: bool = True
    allow_shorts: bool = True


class TrendPullbackStrategy:
    """Trend pullback: follow 1h EMA trend, enter on 5m pullback + reclaim."""

    def __init__(self, cfg: Optional[TrendPullbackConfig] = None):
        self.cfg = cfg or TrendPullbackConfig()

        self.cfg.trend_tf = os.getenv("TPB_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema_fast = _env_int("TPB_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("TPB_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.entry_ema_period = _env_int("TPB_ENTRY_EMA_PERIOD", self.cfg.entry_ema_period)
        self.cfg.pullback_max_pct = _env_float("TPB_PULLBACK_MAX_PCT", self.cfg.pullback_max_pct)
        self.cfg.reclaim_pct = _env_float("TPB_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.atr_period = _env_int("TPB_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.sl_atr_mult = _env_float("TPB_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("TPB_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("TPB_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.allow_longs = _env_bool("TPB_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("TPB_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._cooldown = 0
        self._c5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []

    def _trend_bias(self, store) -> Optional[int]:
        # 2 = bull, 0 = bear, 1 = neutral
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + 5, 80)) or []
        if len(rows) < self.cfg.trend_ema_slow + 2:
            return None
        closes = [float(x[4]) for x in rows]
        ef = ema(closes, self.cfg.trend_ema_fast)
        es = ema(closes, self.cfg.trend_ema_slow)
        if not math.isfinite(ef) or not math.isfinite(es) or es == 0:
            return None
        return 2 if ef > es else 0 if ef < es else 1

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = ts_ms
        _ = v

        self._c5.append(c)
        self._h5.append(h)
        self._l5.append(l)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        if len(self._c5) < max(self.cfg.entry_ema_period + 5, self.cfg.atr_period + 5):
            return None

        bias = self._trend_bias(store)
        if bias is None:
            return None

        ema5 = ema(self._c5[-(self.cfg.entry_ema_period * 2):], self.cfg.entry_ema_period)
        atr5 = atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        if not math.isfinite(ema5) or not math.isfinite(atr5) or atr5 <= 0:
            return None

        pullback_pct = abs(c - ema5) / max(1e-12, ema5) * 100.0
        reclaim = abs(c - ema5) / max(1e-12, ema5) * 100.0

        # Long: trend up, pullback to/below EMA, reclaim above EMA
        if self.cfg.allow_longs and bias == 2:
            if pullback_pct <= self.cfg.pullback_max_pct and c >= ema5 * (1.0 + self.cfg.reclaim_pct / 100.0):
                sl = c - self.cfg.sl_atr_mult * atr5
                if sl >= c:
                    return None
                tp = c + self.cfg.rr * (c - sl)
                self._cooldown = self.cfg.cooldown_bars
                return TradeSignal(
                    strategy="trend_pullback",
                    symbol=store.symbol,
                    side="long",
                    entry=c,
                    sl=sl,
                    tp=tp,
                    reason=f"tpb_long 1h-trend pullback",
                )

        # Short: trend down, pullback to/above EMA, reclaim below EMA
        if self.cfg.allow_shorts and bias == 0:
            if pullback_pct <= self.cfg.pullback_max_pct and c <= ema5 * (1.0 - self.cfg.reclaim_pct / 100.0):
                sl = c + self.cfg.sl_atr_mult * atr5
                if sl <= c:
                    return None
                tp = c - self.cfg.rr * (sl - c)
                self._cooldown = self.cfg.cooldown_bars
                return TradeSignal(
                    strategy="trend_pullback",
                    symbol=store.symbol,
                    side="short",
                    entry=c,
                    sl=sl,
                    tp=tp,
                    reason=f"tpb_short 1h-trend pullback",
                )

        return None
