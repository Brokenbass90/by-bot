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


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _ema(vals: List[float], period: int) -> float:
    if not vals or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = vals[0]
    for x in vals[1:]:
        e = x * k + e * (1.0 - k)
    return e


def _atr_rows(rows: List[list], period: int) -> float:
    if period <= 0 or len(rows) < period + 1:
        return float("nan")
    h = [float(r[2]) for r in rows]
    l = [float(r[3]) for r in rows]
    c = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return sum(trs) / float(period) if trs else float("nan")


@dataclass
class TVATRTrendV1Config:
    trend_tf: str = "240"
    signal_tf: str = "60"
    eval_tf_min: int = 60

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_min_gap_pct: float = 0.18

    signal_ema_period: int = 20
    breakout_lookback: int = 12
    atr_period: int = 14
    sl_atr_mult: float = 2.0
    tp_atr_mult: float = 9.0
    trail_atr_mult: float = 2.0
    time_stop_bars_5m: int = 576  # ~2 days

    cooldown_bars_5m: int = 72
    max_signals_per_day: int = 1
    allow_longs: bool = True
    allow_shorts: bool = True


class TVATRTrendV1Strategy:
    """TV-like ATR trend strategy for R&D contour."""

    def __init__(self, cfg: Optional[TVATRTrendV1Config] = None):
        self.cfg = cfg or TVATRTrendV1Config()
        self.cfg.trend_tf = os.getenv("TVATR_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("TVATR_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("TVATR_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("TVATR_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("TVATR_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_min_gap_pct = _env_float("TVATR_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.signal_ema_period = _env_int("TVATR_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.breakout_lookback = _env_int("TVATR_BREAKOUT_LOOKBACK", self.cfg.breakout_lookback)
        self.cfg.atr_period = _env_int("TVATR_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.sl_atr_mult = _env_float("TVATR_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp_atr_mult = _env_float("TVATR_TP_ATR_MULT", self.cfg.tp_atr_mult)
        self.cfg.trail_atr_mult = _env_float("TVATR_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("TVATR_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("TVATR_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("TVATR_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = str(os.getenv("TVATR_ALLOW_LONGS", "1")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.allow_shorts = str(os.getenv("TVATR_ALLOW_SHORTS", "1")).strip().lower() in {"1", "true", "yes", "on"}

        self._allow = _env_csv_set("TVATR_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("TVATR_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, rows_4h: List[list]) -> int:
        need = max(self.cfg.trend_ema_slow + 5, 260)
        if len(rows_4h) < need:
            return 1
        closes = [float(r[4]) for r in rows_4h]
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es)) or closes[-1] <= 0:
            return 1
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        if gap_pct < self.cfg.trend_min_gap_pct:
            return 1
        return 2 if ef > es else 0

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, v)
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
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

        rows_4h = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + 20, 280)) or []
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.signal_ema_period + self.cfg.breakout_lookback + 40, 180)) or []
        if len(rows_1h) < self.cfg.signal_ema_period + self.cfg.breakout_lookback + 6:
            return None

        bias = self._trend_bias(rows_4h)
        if bias == 1:
            return None

        highs = [float(r[2]) for r in rows_1h]
        lows = [float(r[3]) for r in rows_1h]
        closes = [float(r[4]) for r in rows_1h]
        cur = closes[-1]
        prev = closes[-2]
        ema1h = _ema(closes, self.cfg.signal_ema_period)
        atr1h = _atr_rows(rows_1h, self.cfg.atr_period)
        if not (math.isfinite(ema1h) and math.isfinite(atr1h) and atr1h > 0):
            return None

        n = max(4, int(self.cfg.breakout_lookback))
        br_hi = max(highs[-n - 1:-1])
        br_lo = min(lows[-n - 1:-1])

        if self.cfg.allow_longs and bias == 2 and cur > ema1h and prev <= br_hi and cur > br_hi:
            sl = cur - self.cfg.sl_atr_mult * atr1h
            tp = cur + self.cfg.tp_atr_mult * atr1h
            if sl < cur < tp:
                self._cooldown = self.cfg.cooldown_bars_5m
                self._day_signals += 1
                return TradeSignal(
                    strategy="tv_atr_trend_v1",
                    symbol=store.symbol,
                    side="long",
                    entry=cur,
                    sl=sl,
                    tp=tp,
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="tvatr_long_breakout",
                )

        if self.cfg.allow_shorts and bias == 0 and cur < ema1h and prev >= br_lo and cur < br_lo:
            sl = cur + self.cfg.sl_atr_mult * atr1h
            tp = cur - self.cfg.tp_atr_mult * atr1h
            if tp < cur < sl:
                self._cooldown = self.cfg.cooldown_bars_5m
                self._day_signals += 1
                return TradeSignal(
                    strategy="tv_atr_trend_v1",
                    symbol=store.symbol,
                    side="short",
                    entry=cur,
                    sl=sl,
                    tp=tp,
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="tvatr_short_breakout",
                )
        return None

