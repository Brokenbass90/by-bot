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


def median(values: List[float]) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0


@dataclass
class VolBreakoutConfig:
    lookback_bars: int = 20
    atr_period: int = 14
    atr_med_bars: int = 60
    atr_mult: float = 1.5
    break_atr_mult: float = 0.1
    sl_atr_mult: float = 1.1
    rr: float = 1.5
    cooldown_bars: int = 12
    allow_longs: bool = True
    allow_shorts: bool = True


class VolatilityBreakoutStrategy:
    """Breakout only when ATR expands vs recent median."""

    def __init__(self, cfg: Optional[VolBreakoutConfig] = None):
        self.cfg = cfg or VolBreakoutConfig()

        self.cfg.lookback_bars = _env_int("VBR_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("VBR_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.atr_med_bars = _env_int("VBR_ATR_MED_BARS", self.cfg.atr_med_bars)
        self.cfg.atr_mult = _env_float("VBR_ATR_MULT", self.cfg.atr_mult)
        self.cfg.break_atr_mult = _env_float("VBR_BREAK_ATR_MULT", self.cfg.break_atr_mult)
        self.cfg.sl_atr_mult = _env_float("VBR_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("VBR_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("VBR_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.allow_longs = _env_bool("VBR_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("VBR_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._cooldown = 0
        self._c5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = ts_ms
        _ = v
        self._c5.append(c)
        self._h5.append(h)
        self._l5.append(l)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        need = max(self.cfg.lookback_bars + 2, self.cfg.atr_period + 2, self.cfg.atr_med_bars + 2)
        if len(self._c5) < need:
            return None

        atr5 = atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        if not math.isfinite(atr5) or atr5 <= 0:
            return None

        atr_hist = []
        for i in range(-self.cfg.atr_med_bars, 0):
            a = atr(self._h5[:i], self._l5[:i], self._c5[:i], self.cfg.atr_period)
            if math.isfinite(a) and a > 0:
                atr_hist.append(a)
        if not atr_hist:
            return None
        atr_med = median(atr_hist)
        if not math.isfinite(atr_med) or atr_med <= 0:
            return None

        if atr5 < atr_med * self.cfg.atr_mult:
            return None

        hi = max(self._h5[-self.cfg.lookback_bars:])
        lo = min(self._l5[-self.cfg.lookback_bars:])
        break_buf = self.cfg.break_atr_mult * atr5

        if self.cfg.allow_longs and c >= hi + break_buf:
            sl = c - self.cfg.sl_atr_mult * atr5
            if sl >= c:
                return None
            tp = c + self.cfg.rr * (c - sl)
            self._cooldown = self.cfg.cooldown_bars
            return TradeSignal(
                strategy="vol_breakout",
                symbol=store.symbol,
                side="long",
                entry=c,
                sl=sl,
                tp=tp,
                reason="vol_breakout long",
            )

        if self.cfg.allow_shorts and c <= lo - break_buf:
            sl = c + self.cfg.sl_atr_mult * atr5
            if sl <= c:
                return None
            tp = c - self.cfg.rr * (sl - c)
            self._cooldown = self.cfg.cooldown_bars
            return TradeSignal(
                strategy="vol_breakout",
                symbol=store.symbol,
                side="short",
                entry=c,
                sl=sl,
                tp=tp,
                reason="vol_breakout short",
            )

        return None
