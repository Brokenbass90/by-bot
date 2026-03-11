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
    for v in vals[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    h = [float(r[2]) for r in rows]
    l = [float(r[3]) for r in rows]
    c = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return sum(trs) / float(period) if trs else float("nan")


@dataclass
class BTCETHTrendFollowV2Config:
    trend_tf: str = "240"
    signal_tf: str = "60"
    eval_tf_min: int = 60

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 10
    min_gap_pct: float = 0.22
    min_slope_pct: float = 0.16

    pullback_ema_period: int = 21
    signal_ema_slow: int = 55
    min_pullback_depth_atr: float = 0.25
    pullback_depth_atr: float = 1.2
    breakout_lookback: int = 12
    breakout_atr_mult: float = 0.20

    atr_period: int = 14
    min_atr_pct: float = 0.25
    max_atr_pct: float = 2.50
    sl_atr_mult: float = 1.30
    rr: float = 1.9
    tp1_rr: float = 1.0
    tp2_rr: float = 1.9
    tp1_frac: float = 0.45
    trail_atr_mult: float = 1.8
    time_stop_bars_5m: int = 720

    cooldown_bars_5m: int = 96
    max_signals_per_day: int = 1


class BTCETHTrendFollowV2Strategy:
    """Lower-frequency BTC/ETH trend follower with tighter quality gates."""

    def __init__(self, cfg: Optional[BTCETHTrendFollowV2Config] = None):
        self.cfg = cfg or BTCETHTrendFollowV2Config()
        self.cfg.trend_tf = os.getenv("BTF2_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("BTF2_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("BTF2_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("BTF2_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("BTF2_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_slope_bars = _env_int("BTF2_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.min_gap_pct = _env_float("BTF2_MIN_GAP_PCT", self.cfg.min_gap_pct)
        self.cfg.min_slope_pct = _env_float("BTF2_MIN_SLOPE_PCT", self.cfg.min_slope_pct)
        self.cfg.pullback_ema_period = _env_int("BTF2_PULLBACK_EMA_PERIOD", self.cfg.pullback_ema_period)
        self.cfg.signal_ema_slow = _env_int("BTF2_SIGNAL_EMA_SLOW", self.cfg.signal_ema_slow)
        self.cfg.min_pullback_depth_atr = _env_float("BTF2_MIN_PULLBACK_DEPTH_ATR", self.cfg.min_pullback_depth_atr)
        self.cfg.pullback_depth_atr = _env_float("BTF2_PULLBACK_DEPTH_ATR", self.cfg.pullback_depth_atr)
        self.cfg.breakout_lookback = _env_int("BTF2_BREAKOUT_LOOKBACK", self.cfg.breakout_lookback)
        self.cfg.breakout_atr_mult = _env_float("BTF2_BREAKOUT_ATR_MULT", self.cfg.breakout_atr_mult)
        self.cfg.atr_period = _env_int("BTF2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_atr_pct = _env_float("BTF2_MIN_ATR_PCT", self.cfg.min_atr_pct)
        self.cfg.max_atr_pct = _env_float("BTF2_MAX_ATR_PCT", self.cfg.max_atr_pct)
        self.cfg.sl_atr_mult = _env_float("BTF2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("BTF2_RR", self.cfg.rr)
        self.cfg.tp1_rr = _env_float("BTF2_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("BTF2_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("BTF2_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("BTF2_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTF2_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BTF2_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("BTF2_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._allow = _env_csv_set("BTF2_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("BTF2_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, rows_4h: List[list]) -> int:
        lb = max(4, int(self.cfg.trend_slope_bars))
        need = max(self.cfg.trend_ema_slow + lb + 5, 260)
        if len(rows_4h) < need:
            return 1
        closes = [float(r[4]) for r in rows_4h]
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        es_prev = _ema(closes[:-lb], self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)) or abs(es_prev) <= 1e-12:
            return 1
        gap_pct = abs(ef - es) / max(1e-12, abs(closes[-1])) * 100.0
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if gap_pct < self.cfg.min_gap_pct:
            return 1
        if ef > es and slope_pct >= self.cfg.min_slope_pct:
            return 2
        if ef < es and slope_pct <= -self.cfg.min_slope_pct:
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

        rows_4h = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + self.cfg.trend_slope_bars + 20, 280)) or []
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.signal_ema_slow + self.cfg.breakout_lookback + 50, 220)) or []
        if len(rows_1h) < self.cfg.signal_ema_slow + self.cfg.breakout_lookback + 8:
            return None

        bias = self._trend_bias(rows_4h)
        if bias == 1:
            return None

        highs = [float(r[2]) for r in rows_1h]
        lows = [float(r[3]) for r in rows_1h]
        closes = [float(r[4]) for r in rows_1h]
        ema1h = _ema(closes, self.cfg.pullback_ema_period)
        ema1h_slow = _ema(closes, self.cfg.signal_ema_slow)
        atr1h = _atr(rows_1h, self.cfg.atr_period)
        if not (math.isfinite(ema1h) and math.isfinite(ema1h_slow) and math.isfinite(atr1h) and atr1h > 0):
            return None
        atr_pct = atr1h / max(1e-12, abs(closes[-1])) * 100.0
        if atr_pct < self.cfg.min_atr_pct or atr_pct > self.cfg.max_atr_pct:
            return None

        cur = closes[-1]
        prev = closes[-2]
        br_n = max(4, int(self.cfg.breakout_lookback))
        br_hi = max(highs[-br_n - 1:-1])
        br_lo = min(lows[-br_n - 1:-1])

        if bias == 2:
            pb_depth = max(0.0, (ema1h - min(lows[-br_n - 4:])) / max(1e-12, atr1h))
            touched = min(lows[-br_n - 4:]) <= ema1h
            signal_trend_ok = ema1h > ema1h_slow and cur > ema1h
            broke = cur > br_hi + self.cfg.breakout_atr_mult * atr1h and prev <= br_hi + self.cfg.breakout_atr_mult * atr1h
            if touched and signal_trend_ok and self.cfg.min_pullback_depth_atr <= pb_depth <= self.cfg.pullback_depth_atr and broke:
                sl = min(min(lows[-br_n - 4:]) - 0.10 * atr1h, cur - self.cfg.sl_atr_mult * atr1h)
                risk = cur - sl
                if risk <= 0:
                    return None
                tp = cur + self.cfg.rr * risk
                tp1 = cur + self.cfg.tp1_rr * risk
                tp2 = cur + self.cfg.tp2_rr * risk
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_trend_follow_v2",
                    symbol=store.symbol,
                    side="long",
                    entry=cur,
                    sl=sl,
                    tp=tp,
                    tps=[tp1, tp2],
                    tp_fracs=[self.cfg.tp1_frac, max(0.0, 1.0 - self.cfg.tp1_frac)],
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="btf2_long_resume",
                )

        if bias == 0:
            pb_depth = max(0.0, (max(highs[-br_n - 4:]) - ema1h) / max(1e-12, atr1h))
            touched = max(highs[-br_n - 4:]) >= ema1h
            signal_trend_ok = ema1h < ema1h_slow and cur < ema1h
            broke = cur < br_lo - self.cfg.breakout_atr_mult * atr1h and prev >= br_lo - self.cfg.breakout_atr_mult * atr1h
            if touched and signal_trend_ok and self.cfg.min_pullback_depth_atr <= pb_depth <= self.cfg.pullback_depth_atr and broke:
                sl = max(max(highs[-br_n - 4:]) + 0.10 * atr1h, cur + self.cfg.sl_atr_mult * atr1h)
                risk = sl - cur
                if risk <= 0:
                    return None
                tp = cur - self.cfg.rr * risk
                tp1 = cur - self.cfg.tp1_rr * risk
                tp2 = cur - self.cfg.tp2_rr * risk
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_trend_follow_v2",
                    symbol=store.symbol,
                    side="short",
                    entry=cur,
                    sl=sl,
                    tp=tp,
                    tps=[tp1, tp2],
                    tp_fracs=[self.cfg.tp1_frac, max(0.0, 1.0 - self.cfg.tp1_frac)],
                    trailing_atr_mult=self.cfg.trail_atr_mult,
                    trailing_atr_period=self.cfg.atr_period,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason="btf2_short_resume",
                )
        return None
