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


def rsi(values: List[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    if losses <= 1e-12:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


@dataclass
class TrendPullbackBETrailConfig:
    trend_tf: str = "60"
    trend_ema_fast: int = 20
    trend_ema_slow: int = 55
    trend_min_spread_pct: float = 0.25
    trend_slope_lookback: int = 5
    trend_slope_min_pct: float = 0.12

    entry_ema_period: int = 20
    atr_period: int = 14
    rsi_period: int = 14
    max_atr_pct: float = 1.10

    pullback_min_pct: float = 0.08
    pullback_max_pct: float = 0.55
    reclaim_pct: float = 0.03
    touch_lookback_bars: int = 4
    touch_tol_pct: float = 0.05
    require_touch: bool = True
    require_cross: bool = True

    long_rsi_max: float = 62.0
    short_rsi_min: float = 38.0

    sl_atr_mult: float = 1.15
    tp1_rr: float = 1.10
    tp2_rr: float = 2.20
    tp1_frac: float = 0.50
    tp2_frac: float = 0.30

    be_trigger_rr: float = 0.90
    be_lock_rr: float = 0.05
    trailing_atr_mult: float = 1.60
    trailing_atr_period: int = 14
    time_stop_bars_5m: int = 288

    cooldown_bars: int = 16
    max_signals_per_day: int = 2
    allow_longs: bool = True
    allow_shorts: bool = True


class TrendPullbackBETrailStrategy:
    """Trend-following pullback with BE trigger + trailing runner."""

    def __init__(self, cfg: Optional[TrendPullbackBETrailConfig] = None):
        self.cfg = cfg or TrendPullbackBETrailConfig()

        self.cfg.trend_tf = os.getenv("TPBT_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema_fast = _env_int("TPBT_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("TPBT_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_min_spread_pct = _env_float("TPBT_TREND_MIN_SPREAD_PCT", self.cfg.trend_min_spread_pct)
        self.cfg.trend_slope_lookback = _env_int("TPBT_TREND_SLOPE_LOOKBACK", self.cfg.trend_slope_lookback)
        self.cfg.trend_slope_min_pct = _env_float("TPBT_TREND_SLOPE_MIN_PCT", self.cfg.trend_slope_min_pct)

        self.cfg.entry_ema_period = _env_int("TPBT_ENTRY_EMA_PERIOD", self.cfg.entry_ema_period)
        self.cfg.atr_period = _env_int("TPBT_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.rsi_period = _env_int("TPBT_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.max_atr_pct = _env_float("TPBT_MAX_ATR_PCT", self.cfg.max_atr_pct)

        self.cfg.pullback_min_pct = _env_float("TPBT_PULLBACK_MIN_PCT", self.cfg.pullback_min_pct)
        self.cfg.pullback_max_pct = _env_float("TPBT_PULLBACK_MAX_PCT", self.cfg.pullback_max_pct)
        self.cfg.reclaim_pct = _env_float("TPBT_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.touch_lookback_bars = _env_int("TPBT_TOUCH_LOOKBACK_BARS", self.cfg.touch_lookback_bars)
        self.cfg.touch_tol_pct = _env_float("TPBT_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.require_touch = _env_bool("TPBT_REQUIRE_TOUCH", self.cfg.require_touch)
        self.cfg.require_cross = _env_bool("TPBT_REQUIRE_CROSS", self.cfg.require_cross)

        self.cfg.long_rsi_max = _env_float("TPBT_LONG_RSI_MAX", self.cfg.long_rsi_max)
        self.cfg.short_rsi_min = _env_float("TPBT_SHORT_RSI_MIN", self.cfg.short_rsi_min)

        self.cfg.sl_atr_mult = _env_float("TPBT_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_rr = _env_float("TPBT_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("TPBT_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("TPBT_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_frac = _env_float("TPBT_TP2_FRAC", self.cfg.tp2_frac)

        self.cfg.be_trigger_rr = _env_float("TPBT_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("TPBT_BE_LOCK_RR", self.cfg.be_lock_rr)
        self.cfg.trailing_atr_mult = _env_float("TPBT_TRAIL_ATR_MULT", self.cfg.trailing_atr_mult)
        self.cfg.trailing_atr_period = _env_int("TPBT_TRAIL_ATR_PERIOD", self.cfg.trailing_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("TPBT_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)

        self.cfg.cooldown_bars = _env_int("TPBT_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("TPBT_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("TPBT_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("TPBT_ALLOW_SHORTS", self.cfg.allow_shorts)
        self._deny = _env_csv_set("TPBT_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._c5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, store) -> Optional[int]:
        rows = store.fetch_klines(
            store.symbol,
            self.cfg.trend_tf,
            max(self.cfg.trend_ema_slow + self.cfg.trend_slope_lookback + 8, 100),
        ) or []
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
        _ = (o, v)
        sym = str(getattr(store, "symbol", "")).upper()
        if sym in self._deny:
            return None

        self._c5.append(c)
        self._h5.append(h)
        self._l5.append(l)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        min_hist = max(self.cfg.entry_ema_period + 5, self.cfg.atr_period + 5, self.cfg.rsi_period + 5)
        if len(self._c5) < min_hist:
            return None

        bias = self._trend_bias(store)
        if bias is None:
            return None

        ema5 = ema(self._c5[-(self.cfg.entry_ema_period * 2):], self.cfg.entry_ema_period)
        atr5 = atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        rsi5 = rsi(self._c5, self.cfg.rsi_period)
        if not math.isfinite(ema5) or not math.isfinite(atr5) or atr5 <= 0 or not math.isfinite(rsi5):
            return None

        atr_pct = atr5 / max(1e-12, abs(c)) * 100.0
        if atr_pct > self.cfg.max_atr_pct:
            return None

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

        # Long setup
        if self.cfg.allow_longs and bias == 2:
            min_l = min(recent_l)
            touched = min_l <= ema5 * (1.0 + self.cfg.touch_tol_pct / 100.0)
            reclaim = c >= ema5 * (1.0 + self.cfg.reclaim_pct / 100.0)
            if self.cfg.require_cross:
                reclaim = (prev_c <= ema5) and reclaim
            pullback_pct = max(0.0, (ema5 - min_l) / max(1e-12, ema5) * 100.0)
            depth_ok = self.cfg.pullback_min_pct <= pullback_pct <= self.cfg.pullback_max_pct
            touch_ok = touched or (not self.cfg.require_touch)
            rsi_ok = rsi5 <= self.cfg.long_rsi_max
            if touch_ok and reclaim and depth_ok and rsi_ok:
                risk = self.cfg.sl_atr_mult * atr5
                if risk <= 0:
                    return None
                sl = c - risk
                tp1 = c + self.cfg.tp1_rr * risk
                tp2 = c + self.cfg.tp2_rr * risk
                self._cooldown = self.cfg.cooldown_bars
                self._day_signals += 1
                return TradeSignal(
                    strategy="trend_pullback_be_trail",
                    symbol=store.symbol,
                    side="long",
                    entry=c,
                    sl=sl,
                    tp=tp2,
                    tps=[tp1, tp2],
                    tp_fracs=[self.cfg.tp1_frac, self.cfg.tp2_frac],
                    trailing_atr_mult=self.cfg.trailing_atr_mult,
                    trailing_atr_period=self.cfg.trailing_atr_period,
                    be_trigger_rr=self.cfg.be_trigger_rr,
                    be_lock_rr=self.cfg.be_lock_rr,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="tpbt_long",
                )

        # Short setup
        if self.cfg.allow_shorts and bias == 0:
            max_h = max(recent_h)
            touched = max_h >= ema5 * (1.0 - self.cfg.touch_tol_pct / 100.0)
            reclaim = c <= ema5 * (1.0 - self.cfg.reclaim_pct / 100.0)
            if self.cfg.require_cross:
                reclaim = (prev_c >= ema5) and reclaim
            pullback_pct = max(0.0, (max_h - ema5) / max(1e-12, ema5) * 100.0)
            depth_ok = self.cfg.pullback_min_pct <= pullback_pct <= self.cfg.pullback_max_pct
            touch_ok = touched or (not self.cfg.require_touch)
            rsi_ok = rsi5 >= self.cfg.short_rsi_min
            if touch_ok and reclaim and depth_ok and rsi_ok:
                risk = self.cfg.sl_atr_mult * atr5
                if risk <= 0:
                    return None
                sl = c + risk
                tp1 = c - self.cfg.tp1_rr * risk
                tp2 = c - self.cfg.tp2_rr * risk
                self._cooldown = self.cfg.cooldown_bars
                self._day_signals += 1
                return TradeSignal(
                    strategy="trend_pullback_be_trail",
                    symbol=store.symbol,
                    side="short",
                    entry=c,
                    sl=sl,
                    tp=tp2,
                    tps=[tp1, tp2],
                    tp_fracs=[self.cfg.tp1_frac, self.cfg.tp2_frac],
                    trailing_atr_mult=self.cfg.trailing_atr_mult,
                    trailing_atr_period=self.cfg.trailing_atr_period,
                    be_trigger_rr=self.cfg.be_trigger_rr,
                    be_lock_rr=self.cfg.be_lock_rr,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="tpbt_short",
                )
        return None

