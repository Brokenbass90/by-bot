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


def _sma(vals: List[float], period: int) -> float:
    if period <= 0 or len(vals) < period:
        return float("nan")
    w = vals[-period:]
    return sum(w) / float(period) if w else float("nan")


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
class TVATRTrendV2Config:
    trend_tf: str = "240"
    signal_tf: str = "60"
    eval_tf_min: int = 240

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_lookback: int = 8
    trend_min_gap_pct: float = 0.30
    trend_min_slope_pct: float = 0.12

    signal_ema_period: int = 20
    breakout_lookback: int = 24
    pullback_lookback: int = 10
    atr_period: int = 14
    min_atr_pct: float = 0.25
    max_atr_pct: float = 2.20
    vol_period: int = 20
    vol_mult: float = 1.20

    sl_atr_mult: float = 2.0
    tp1_atr_mult: float = 3.0
    tp2_atr_mult: float = 6.0
    tp1_frac: float = 0.45
    tp2_frac: float = 0.35
    trail_atr_mult: float = 2.2
    time_stop_bars_5m: int = 864

    cooldown_bars_5m: int = 144
    max_signals_per_day: int = 1
    allow_longs: bool = True
    allow_shorts: bool = True


class TVATRTrendV2Strategy:
    """Stricter TV-like ATR trend strategy with low trade frequency."""

    def __init__(self, cfg: Optional[TVATRTrendV2Config] = None):
        self.cfg = cfg or TVATRTrendV2Config()
        self.cfg.trend_tf = os.getenv("TVATR2_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("TVATR2_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("TVATR2_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("TVATR2_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("TVATR2_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_slope_lookback = _env_int("TVATR2_TREND_SLOPE_LOOKBACK", self.cfg.trend_slope_lookback)
        self.cfg.trend_min_gap_pct = _env_float("TVATR2_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.trend_min_slope_pct = _env_float("TVATR2_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.signal_ema_period = _env_int("TVATR2_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.breakout_lookback = _env_int("TVATR2_BREAKOUT_LOOKBACK", self.cfg.breakout_lookback)
        self.cfg.pullback_lookback = _env_int("TVATR2_PULLBACK_LOOKBACK", self.cfg.pullback_lookback)
        self.cfg.atr_period = _env_int("TVATR2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_atr_pct = _env_float("TVATR2_MIN_ATR_PCT", self.cfg.min_atr_pct)
        self.cfg.max_atr_pct = _env_float("TVATR2_MAX_ATR_PCT", self.cfg.max_atr_pct)
        self.cfg.vol_period = _env_int("TVATR2_VOL_PERIOD", self.cfg.vol_period)
        self.cfg.vol_mult = _env_float("TVATR2_VOL_MULT", self.cfg.vol_mult)
        self.cfg.sl_atr_mult = _env_float("TVATR2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_atr_mult = _env_float("TVATR2_TP1_ATR_MULT", self.cfg.tp1_atr_mult)
        self.cfg.tp2_atr_mult = _env_float("TVATR2_TP2_ATR_MULT", self.cfg.tp2_atr_mult)
        self.cfg.tp1_frac = _env_float("TVATR2_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_frac = _env_float("TVATR2_TP2_FRAC", self.cfg.tp2_frac)
        self.cfg.trail_atr_mult = _env_float("TVATR2_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("TVATR2_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("TVATR2_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("TVATR2_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = str(os.getenv("TVATR2_ALLOW_LONGS", "1")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.allow_shorts = str(os.getenv("TVATR2_ALLOW_SHORTS", "1")).strip().lower() in {"1", "true", "yes", "on"}

        self._allow = _env_csv_set("TVATR2_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("TVATR2_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, rows_4h: List[list]) -> int:
        need = max(self.cfg.trend_ema_slow + self.cfg.trend_slope_lookback + 10, 280)
        if len(rows_4h) < need:
            return 1
        closes = [float(r[4]) for r in rows_4h]
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        es_prev = _ema(closes[:-self.cfg.trend_slope_lookback], self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)) or closes[-1] <= 0:
            return 1
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        slope_pct = (es - es_prev) / max(1e-12, abs(es_prev)) * 100.0
        if gap_pct < self.cfg.trend_min_gap_pct:
            return 1
        if ef > es and slope_pct >= self.cfg.trend_min_slope_pct:
            return 2
        if ef < es and slope_pct <= -self.cfg.trend_min_slope_pct:
            return 0
        return 1

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

        rows_4h = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + self.cfg.trend_slope_lookback + 20, 320)) or []
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.signal_ema_period + self.cfg.breakout_lookback + self.cfg.pullback_lookback + 50, 220)) or []
        if len(rows_1h) < self.cfg.signal_ema_period + self.cfg.breakout_lookback + self.cfg.pullback_lookback + 5:
            return None

        bias = self._trend_bias(rows_4h)
        if bias == 1:
            return None

        highs = [float(r[2]) for r in rows_1h]
        lows = [float(r[3]) for r in rows_1h]
        closes = [float(r[4]) for r in rows_1h]
        vols = [float(r[5]) for r in rows_1h]
        cur = closes[-1]
        prev = closes[-2]
        ema1h = _ema(closes, self.cfg.signal_ema_period)
        atr1h = _atr_rows(rows_1h, self.cfg.atr_period)
        vol_sma = _sma(vols, self.cfg.vol_period)
        if not (math.isfinite(ema1h) and math.isfinite(atr1h) and atr1h > 0 and math.isfinite(vol_sma) and vol_sma > 0):
            return None
        atr_pct = atr1h / max(1e-12, abs(cur)) * 100.0
        if atr_pct < self.cfg.min_atr_pct or atr_pct > self.cfg.max_atr_pct:
            return None
        if vols[-1] < self.cfg.vol_mult * vol_sma:
            return None

        n = max(6, int(self.cfg.breakout_lookback))
        pb = max(4, int(self.cfg.pullback_lookback))
        br_hi = max(highs[-n - 1:-1])
        br_lo = min(lows[-n - 1:-1])

        long_pullback = min(lows[-pb - 1:-1]) <= ema1h
        short_pullback = max(highs[-pb - 1:-1]) >= ema1h

        if self.cfg.allow_longs and bias == 2 and long_pullback and cur > ema1h and prev <= br_hi and cur > br_hi:
            sl = cur - self.cfg.sl_atr_mult * atr1h
            tp1 = cur + self.cfg.tp1_atr_mult * atr1h
            tp2 = cur + self.cfg.tp2_atr_mult * atr1h
            if sl < cur < tp1 < tp2:
                self._cooldown = self.cfg.cooldown_bars_5m
                self._day_signals += 1
                return TradeSignal(
                    strategy="tv_atr_trend_v2",
                    symbol=store.symbol,
                    side="long",
                    entry=cur,
                    sl=sl,
                    tp=tp2,
                    tps=[tp1, tp2],
                    tp_fracs=[self.cfg.tp1_frac, self.cfg.tp2_frac],
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="tvatr2_long",
                )

        if self.cfg.allow_shorts and bias == 0 and short_pullback and cur < ema1h and prev >= br_lo and cur < br_lo:
            sl = cur + self.cfg.sl_atr_mult * atr1h
            tp1 = cur - self.cfg.tp1_atr_mult * atr1h
            tp2 = cur - self.cfg.tp2_atr_mult * atr1h
            if tp2 < tp1 < cur < sl:
                self._cooldown = self.cfg.cooldown_bars_5m
                self._day_signals += 1
                return TradeSignal(
                    strategy="tv_atr_trend_v2",
                    symbol=store.symbol,
                    side="short",
                    entry=cur,
                    sl=sl,
                    tp=tp2,
                    tps=[tp1, tp2],
                    tp_fracs=[self.cfg.tp1_frac, self.cfg.tp2_frac],
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="tvatr2_short",
                )
        return None

