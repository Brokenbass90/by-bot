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


def _env_csv_set(name: str) -> set[str]:
    v = os.getenv(name, "").strip()
    if not v:
        return set()
    return {p.strip().upper() for p in v.replace(";", ",").split(",") if p.strip()}


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
    trend_min_spread_pct: float = 0.20
    trend_slope_lookback: int = 5
    trend_slope_min_pct: float = 0.15
    touch_lookback_bars: int = 3
    touch_tol_pct: float = 0.05
    max_atr_pct: float = 0.90
    max_signals_per_day: int = 2
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
        self.cfg.trend_min_spread_pct = _env_float("TPB_TREND_MIN_SPREAD_PCT", self.cfg.trend_min_spread_pct)
        self.cfg.trend_slope_lookback = _env_int("TPB_TREND_SLOPE_LOOKBACK", self.cfg.trend_slope_lookback)
        self.cfg.trend_slope_min_pct = _env_float("TPB_TREND_SLOPE_MIN_PCT", self.cfg.trend_slope_min_pct)
        self.cfg.touch_lookback_bars = _env_int("TPB_TOUCH_LOOKBACK_BARS", self.cfg.touch_lookback_bars)
        self.cfg.touch_tol_pct = _env_float("TPB_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.max_atr_pct = _env_float("TPB_MAX_ATR_PCT", self.cfg.max_atr_pct)
        self.cfg.max_signals_per_day = _env_int("TPB_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("TPB_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("TPB_ALLOW_SHORTS", self.cfg.allow_shorts)
        self._deny = _env_csv_set("TPB_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._c5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, store) -> Optional[int]:
        # 2 = bull, 0 = bear, 1 = neutral
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + self.cfg.trend_slope_lookback + 8, 100)) or []
        if len(rows) < self.cfg.trend_ema_slow + 2:
            return None
        closes = [float(x[4]) for x in rows]
        ef = ema(closes, self.cfg.trend_ema_fast)
        es = ema(closes, self.cfg.trend_ema_slow)
        if not math.isfinite(ef) or not math.isfinite(es) or es == 0:
            return None
        spread_pct = abs(ef - es) / abs(es) * 100.0
        if spread_pct < self.cfg.trend_min_spread_pct:
            return 1
        # slope filter on slow EMA
        lb = max(2, self.cfg.trend_slope_lookback)
        if len(closes) < self.cfg.trend_ema_slow + lb:
            return None
        es_prev = ema(closes[:-lb], self.cfg.trend_ema_slow)
        if not math.isfinite(es_prev) or es_prev == 0:
            return None
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.trend_slope_min_pct:
            return 2
        if ef < es and slope_pct <= -self.cfg.trend_slope_min_pct:
            return 0
        return 1

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = v
        sym = str(getattr(store, "symbol", "")).upper()
        if sym in self._deny:
            return None

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

        atr_pct = atr5 / max(1e-12, abs(c)) * 100.0
        if atr_pct > self.cfg.max_atr_pct:
            return None
        # per-day signal cap
        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None
        look = max(2, min(len(self._c5), self.cfg.touch_lookback_bars))
        recent_l = self._l5[-look:]
        recent_h = self._h5[-look:]
        prev_c = self._c5[-2]

        # Long: trend up, pullback to/below EMA, reclaim above EMA
        if self.cfg.allow_longs and bias == 2:
            touched = min(recent_l) <= ema5 * (1.0 + self.cfg.touch_tol_pct / 100.0)
            close_reclaim = (prev_c <= ema5) and (c >= ema5 * (1.0 + self.cfg.reclaim_pct / 100.0))
            pullback_pct = max(0.0, (ema5 - min(recent_l)) / max(1e-12, ema5) * 100.0)
            if touched and close_reclaim and pullback_pct <= self.cfg.pullback_max_pct:
                sl = c - self.cfg.sl_atr_mult * atr5
                if sl >= c:
                    return None
                tp = c + self.cfg.rr * (c - sl)
                self._cooldown = self.cfg.cooldown_bars
                self._day_signals += 1
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
            touched = max(recent_h) >= ema5 * (1.0 - self.cfg.touch_tol_pct / 100.0)
            close_reclaim = (prev_c >= ema5) and (c <= ema5 * (1.0 - self.cfg.reclaim_pct / 100.0))
            pullback_pct = max(0.0, (max(recent_h) - ema5) / max(1e-12, ema5) * 100.0)
            if touched and close_reclaim and pullback_pct <= self.cfg.pullback_max_pct:
                sl = c + self.cfg.sl_atr_mult * atr5
                if sl <= c:
                    return None
                tp = c - self.cfg.rr * (sl - c)
                self._cooldown = self.cfg.cooldown_bars
                self._day_signals += 1
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
