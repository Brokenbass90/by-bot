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


def _atr(rows: List[list], period: int = 14) -> float:
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
class BTCETHTrendFollowConfig:
    trend_tf: str = "240"
    signal_tf: str = "60"
    eval_tf_min: int = 15

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 8
    trend_min_gap_pct: float = 0.16
    trend_min_slope_pct: float = 0.10

    pullback_ema_period: int = 20
    pullback_lookback_bars: int = 10
    breakout_lookback_bars: int = 8
    breakout_atr_mult: float = 0.10

    atr_period: int = 14
    sl_atr_mult: float = 1.15
    rr: float = 2.8
    tp1_rr: float = 1.2
    tp2_rr: float = 2.8
    tp1_frac: float = 0.40
    trail_atr_mult: float = 1.6
    time_stop_bars_5m: int = 900

    cooldown_bars_5m: int = 48
    max_signals_per_day: int = 2


class BTCETHTrendFollowStrategy:
    """Trend bot: follow 4h regime and hold via runner/trailing until reversal."""

    def __init__(self, cfg: Optional[BTCETHTrendFollowConfig] = None):
        self.cfg = cfg or BTCETHTrendFollowConfig()
        self.cfg.trend_tf = os.getenv("BTF_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("BTF_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("BTF_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("BTF_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("BTF_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_slope_bars = _env_int("BTF_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.trend_min_gap_pct = _env_float("BTF_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.trend_min_slope_pct = _env_float("BTF_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.pullback_ema_period = _env_int("BTF_PULLBACK_EMA_PERIOD", self.cfg.pullback_ema_period)
        self.cfg.pullback_lookback_bars = _env_int("BTF_PULLBACK_LOOKBACK_BARS", self.cfg.pullback_lookback_bars)
        self.cfg.breakout_lookback_bars = _env_int("BTF_BREAKOUT_LOOKBACK_BARS", self.cfg.breakout_lookback_bars)
        self.cfg.breakout_atr_mult = _env_float("BTF_BREAKOUT_ATR_MULT", self.cfg.breakout_atr_mult)
        self.cfg.atr_period = _env_int("BTF_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.sl_atr_mult = _env_float("BTF_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("BTF_RR", self.cfg.rr)
        self.cfg.tp1_rr = _env_float("BTF_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("BTF_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("BTF_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("BTF_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTF_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BTF_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("BTF_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._allow = _env_csv_set("BTF_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("BTF_SYMBOL_DENYLIST")
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

        rows_4h = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + self.cfg.trend_slope_bars + 20, 280)) or []
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.pullback_ema_period + self.cfg.pullback_lookback_bars + 30, 140)) or []
        if len(rows_1h) < self.cfg.pullback_ema_period + self.cfg.pullback_lookback_bars + 5:
            return None

        bias = self._trend_bias(rows_4h)
        if bias == 1:
            return None

        highs = [float(r[2]) for r in rows_1h]
        lows = [float(r[3]) for r in rows_1h]
        closes = [float(r[4]) for r in rows_1h]
        ema1h = _ema(closes, self.cfg.pullback_ema_period)
        atr1h = _atr(rows_1h, self.cfg.atr_period)
        if not (math.isfinite(ema1h) and math.isfinite(atr1h) and atr1h > 0):
            return None

        cur = closes[-1]
        prev = closes[-2]
        pb_n = max(4, int(self.cfg.pullback_lookback_bars))
        br_n = max(4, int(self.cfg.breakout_lookback_bars))

        if bias == 2:
            touched_pb = min(lows[-pb_n:]) <= ema1h
            brk_ref = max(highs[-br_n - 1:-1])
            broke = cur > brk_ref + self.cfg.breakout_atr_mult * atr1h and prev <= brk_ref + self.cfg.breakout_atr_mult * atr1h
            if touched_pb and broke:
                swing_low = min(lows[-pb_n:])
                sl = min(swing_low - 0.10 * atr1h, cur - self.cfg.sl_atr_mult * atr1h)
                risk = cur - sl
                if risk <= 0:
                    return None
                tp = cur + self.cfg.rr * risk
                tp1 = cur + self.cfg.tp1_rr * risk
                tp2 = cur + self.cfg.tp2_rr * risk
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_trend_follow",
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
                    reason="btf_long pullback_resume_breakout",
                )

        if bias == 0:
            touched_pb = max(highs[-pb_n:]) >= ema1h
            brk_ref = min(lows[-br_n - 1:-1])
            broke = cur < brk_ref - self.cfg.breakout_atr_mult * atr1h and prev >= brk_ref - self.cfg.breakout_atr_mult * atr1h
            if touched_pb and broke:
                swing_high = max(highs[-pb_n:])
                sl = max(swing_high + 0.10 * atr1h, cur + self.cfg.sl_atr_mult * atr1h)
                risk = sl - cur
                if risk <= 0:
                    return None
                tp = cur - self.cfg.rr * risk
                tp1 = cur - self.cfg.tp1_rr * risk
                tp2 = cur - self.cfg.tp2_rr * risk
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_trend_follow",
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
                    reason="btf_short pullback_resume_breakdown",
                )
        return None
