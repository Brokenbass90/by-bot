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


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for x in values[1:]:
        e = x * k + e * (1.0 - k)
    return e


def _sma(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period:
        return float("nan")
    w = values[-period:]
    return sum(w) / float(period) if w else float("nan")


def _atr(h: List[float], l: List[float], c: List[float], period: int) -> float:
    if period <= 0 or len(c) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return sum(trs) / float(period) if trs else float("nan")


def _rsi(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period + 1:
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
    rs = (gains / float(period)) / (losses / float(period))
    return 100.0 - (100.0 / (1.0 + rs))


@dataclass
class TripleScreenV132BConfig:
    trend_tf: str = "240"
    eval_tf_min: int = 120
    trend_ema_len: int = 55
    trend_slope_lookback: int = 8
    trend_min_gap_pct: float = 0.20
    trend_min_slope_pct: float = 0.10

    osc_period: int = 10
    osc_ob: float = 68.0
    osc_os: float = 32.0

    atr_period: int = 14
    min_atr_pct: float = 0.20
    max_atr_pct: float = 2.20

    sl_atr_mult: float = 1.8
    tp_atr_mult: float = 4.2
    trail_atr_mult: float = 1.6

    use_vol_filter: bool = True
    vol_mult: float = 1.0
    max_signals_per_day: int = 1
    cooldown_bars: int = 24
    time_stop_bars_5m: int = 576

    allow_longs: bool = True
    allow_shorts: bool = False
    exec_mode: str = "optimistic"  # optimistic|eth|alts


class TripleScreenV132BStrategy:
    """Stricter version focused on execution robustness.

    Key differences vs v132:
    - HTF trend on 4h + slope+gap filter
    - RSI cross only (no aggressive mode)
    - default long-only
    - tighter frequency and volatility filters
    - more realistic TP/trailing balance
    """

    def __init__(self, cfg: Optional[TripleScreenV132BConfig] = None):
        self.cfg = cfg or TripleScreenV132BConfig()

        self.cfg.trend_tf = os.getenv("TS132B_TREND_TF", self.cfg.trend_tf)
        self.cfg.eval_tf_min = _env_int("TS132B_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_len = _env_int("TS132B_TREND_EMA_LEN", self.cfg.trend_ema_len)
        self.cfg.trend_slope_lookback = _env_int("TS132B_TREND_SLOPE_LOOKBACK", self.cfg.trend_slope_lookback)
        self.cfg.trend_min_gap_pct = _env_float("TS132B_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.trend_min_slope_pct = _env_float("TS132B_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)

        self.cfg.osc_period = _env_int("TS132B_OSC_PERIOD", self.cfg.osc_period)
        self.cfg.osc_ob = _env_float("TS132B_OSC_OB", self.cfg.osc_ob)
        self.cfg.osc_os = _env_float("TS132B_OSC_OS", self.cfg.osc_os)

        self.cfg.atr_period = _env_int("TS132B_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_atr_pct = _env_float("TS132B_MIN_ATR_PCT", self.cfg.min_atr_pct)
        self.cfg.max_atr_pct = _env_float("TS132B_MAX_ATR_PCT", self.cfg.max_atr_pct)

        self.cfg.sl_atr_mult = _env_float("TS132B_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp_atr_mult = _env_float("TS132B_TP_ATR_MULT", self.cfg.tp_atr_mult)
        self.cfg.trail_atr_mult = _env_float("TS132B_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)

        self.cfg.use_vol_filter = str(os.getenv("TS132B_USE_VOL_FILTER", "1")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.vol_mult = _env_float("TS132B_VOL_MULT", self.cfg.vol_mult)
        self.cfg.max_signals_per_day = _env_int("TS132B_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.cooldown_bars = _env_int("TS132B_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.time_stop_bars_5m = _env_int("TS132B_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)

        self.cfg.allow_longs = str(os.getenv("TS132B_ALLOW_LONGS", "1")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.allow_shorts = str(os.getenv("TS132B_ALLOW_SHORTS", "0")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.exec_mode = str(os.getenv("TS132B_EXEC_MODE", self.cfg.exec_mode)).strip().lower()

        self._c: List[float] = []
        self._h: List[float] = []
        self._l: List[float] = []
        self._v: List[float] = []
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0
        self._last_eval_bucket: Optional[int] = None

    def _slip_adj(self) -> float:
        if self.cfg.exec_mode == "eth":
            return 0.0002
        if self.cfg.exec_mode == "alts":
            return 0.0006
        return 0.0

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = o
        self._c.append(float(c))
        self._h.append(float(h))
        self._l.append(float(l))
        self._v.append(max(0.0, float(v or 0.0)))

        need = max(self.cfg.atr_period + 2, self.cfg.osc_period + 3, 60)
        if len(self._c) < need:
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        bucket = ts_sec // max(1, int(self.cfg.eval_tf_min * 60))
        if self._last_eval_bucket == bucket:
            return None
        self._last_eval_bucket = bucket

        rows_t = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_len + self.cfg.trend_slope_lookback + 30, 160)) or []
        if len(rows_t) < self.cfg.trend_ema_len + self.cfg.trend_slope_lookback + 5:
            return None
        t_close = [float(r[4]) for r in rows_t]
        ema_t = _ema(t_close, self.cfg.trend_ema_len)
        ema_t_prev = _ema(t_close[:-self.cfg.trend_slope_lookback], self.cfg.trend_ema_len)
        if not (math.isfinite(ema_t) and math.isfinite(ema_t_prev)):
            return None

        px = self._c[-1]
        if px <= 0:
            return None
        trend_gap_pct = abs(px - ema_t) / px * 100.0
        trend_slope_pct = (ema_t - ema_t_prev) / max(1e-12, abs(ema_t_prev)) * 100.0
        trend_up = (px > ema_t) and (trend_gap_pct >= self.cfg.trend_min_gap_pct) and (trend_slope_pct >= self.cfg.trend_min_slope_pct)
        trend_down = (px < ema_t) and (trend_gap_pct >= self.cfg.trend_min_gap_pct) and (trend_slope_pct <= -self.cfg.trend_min_slope_pct)

        rsi = _rsi(self._c, self.cfg.osc_period)
        rsi_prev = _rsi(self._c[:-1], self.cfg.osc_period) if len(self._c) > self.cfg.osc_period + 1 else float("nan")
        if not (math.isfinite(rsi) and math.isfinite(rsi_prev)):
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not (math.isfinite(atr_now) and atr_now > 0):
            return None
        atr_pct = atr_now / px * 100.0
        if atr_pct < self.cfg.min_atr_pct or atr_pct > self.cfg.max_atr_pct:
            return None

        if self.cfg.use_vol_filter:
            vavg = _sma(self._v, 20)
            if not (math.isfinite(vavg) and self._v[-1] >= vavg * self.cfg.vol_mult):
                return None

        long_signal = trend_up and (rsi_prev <= self.cfg.osc_os and rsi > self.cfg.osc_os)
        short_signal = trend_down and (rsi_prev >= self.cfg.osc_ob and rsi < self.cfg.osc_ob)

        slip_adj = self._slip_adj()

        if self.cfg.allow_longs and long_signal:
            sl = px - atr_now * self.cfg.sl_atr_mult
            tp = px + atr_now * self.cfg.tp_atr_mult
            sl *= (1.0 - slip_adj)
            tp *= (1.0 - slip_adj)
            if sl < px < tp:
                self._cooldown = self.cfg.cooldown_bars
                self._day_signals += 1
                return TradeSignal(
                    strategy="triple_screen_v132b",
                    symbol=getattr(store, "symbol", ""),
                    side="long",
                    entry=px,
                    sl=sl,
                    tp=tp,
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="ts132b_long",
                )

        if self.cfg.allow_shorts and short_signal:
            sl = px + atr_now * self.cfg.sl_atr_mult
            tp = px - atr_now * self.cfg.tp_atr_mult
            sl *= (1.0 + slip_adj)
            tp *= (1.0 + slip_adj)
            if tp < px < sl:
                self._cooldown = self.cfg.cooldown_bars
                self._day_signals += 1
                return TradeSignal(
                    strategy="triple_screen_v132b",
                    symbol=getattr(store, "symbol", ""),
                    side="short",
                    entry=px,
                    sl=sl,
                    tp=tp,
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="ts132b_short",
                )

        return None
