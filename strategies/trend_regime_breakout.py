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
class TrendRegimeBreakoutConfig:
    trend_tf: str = "60"
    ema_fast: int = 20
    ema_slow: int = 50
    min_gap_pct: float = 0.25

    lookback_bars: int = 12  # 5m bars to define range
    atr_period: int = 14
    break_atr_mult: float = 0.15
    sl_atr_mult: float = 1.2
    rr: float = 1.6
    cooldown_bars: int = 12

    allow_longs: bool = True
    allow_shorts: bool = True


class TrendRegimeBreakoutStrategy:
    """Breakout only when 1h trend is strong (EMA gap filter)."""

    def __init__(self, cfg: Optional[TrendRegimeBreakoutConfig] = None):
        self.cfg = cfg or TrendRegimeBreakoutConfig()

        self.cfg.trend_tf = os.getenv("TRB_TREND_TF", self.cfg.trend_tf)
        self.cfg.ema_fast = _env_int("TRB_EMA_FAST", self.cfg.ema_fast)
        self.cfg.ema_slow = _env_int("TRB_EMA_SLOW", self.cfg.ema_slow)
        self.cfg.min_gap_pct = _env_float("TRB_MIN_GAP_PCT", self.cfg.min_gap_pct)
        self.cfg.lookback_bars = _env_int("TRB_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("TRB_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.break_atr_mult = _env_float("TRB_BREAK_ATR_MULT", self.cfg.break_atr_mult)
        self.cfg.sl_atr_mult = _env_float("TRB_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("TRB_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("TRB_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.allow_longs = _env_bool("TRB_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("TRB_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._cooldown = 0
        self._c5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []

    def _trend_bias(self, store) -> Optional[int]:
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.ema_slow + 5, 80)) or []
        if len(rows) < self.cfg.ema_slow + 2:
            return None
        closes = [float(x[4]) for x in rows]
        ef = ema(closes, self.cfg.ema_fast)
        es = ema(closes, self.cfg.ema_slow)
        if not math.isfinite(ef) or not math.isfinite(es) or es == 0:
            return None
        gap_pct = abs(ef - es) / max(1e-12, closes[-1]) * 100.0
        if gap_pct < self.cfg.min_gap_pct:
            return 1  # neutral
        return 2 if ef > es else 0

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = ts_ms
        _ = v
        self._c5.append(c)
        self._h5.append(h)
        self._l5.append(l)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        if len(self._c5) < max(self.cfg.lookback_bars + 2, self.cfg.atr_period + 2):
            return None

        bias = self._trend_bias(store)
        if bias is None or bias == 1:
            return None

        atr5 = atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        if not math.isfinite(atr5) or atr5 <= 0:
            return None

        hi = max(self._h5[-self.cfg.lookback_bars:])
        lo = min(self._l5[-self.cfg.lookback_bars:])
        break_buf = self.cfg.break_atr_mult * atr5

        # Long breakout in uptrend
        if self.cfg.allow_longs and bias == 2:
            if c >= hi + break_buf:
                sl = c - self.cfg.sl_atr_mult * atr5
                if sl >= c:
                    return None
                tp = c + self.cfg.rr * (c - sl)
                self._cooldown = self.cfg.cooldown_bars
                return TradeSignal(
                    strategy="trend_breakout",
                    symbol=store.symbol,
                    side="long",
                    entry=c,
                    sl=sl,
                    tp=tp,
                    reason="trend_breakout long",
                )

        # Short breakout in downtrend
        if self.cfg.allow_shorts and bias == 0:
            if c <= lo - break_buf:
                sl = c + self.cfg.sl_atr_mult * atr5
                if sl <= c:
                    return None
                tp = c - self.cfg.rr * (sl - c)
                self._cooldown = self.cfg.cooldown_bars
                return TradeSignal(
                    strategy="trend_breakout",
                    symbol=store.symbol,
                    side="short",
                    entry=c,
                    sl=sl,
                    tp=tp,
                    reason="trend_breakout short",
                )

        return None
