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


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr_from_rows(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / float(period) if trs else float("nan")


@dataclass
class BTCETHMidtermPullbackConfig:
    trend_tf: str = "240"  # 4h
    signal_tf: str = "60"  # 1h
    eval_tf_min: int = 15  # evaluate every 15m bucket

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 8
    trend_slope_min_pct: float = 0.25

    signal_ema_period: int = 20
    atr_period: int = 14
    max_pullback_pct: float = 1.20
    touch_tol_pct: float = 0.20
    reclaim_pct: float = 0.08
    swing_lookback_bars: int = 10

    sl_atr_mult: float = 1.20
    swing_sl_buffer_atr: float = 0.15
    rr: float = 2.2

    cooldown_bars_5m: int = 48
    max_signals_per_day: int = 2
    allow_longs: bool = True
    allow_shorts: bool = True


class BTCETHMidtermPullbackStrategy:
    """BTC/ETH medium-term pullback: 4h trend + 1h pullback/reclaim entry."""

    def __init__(self, cfg: Optional[BTCETHMidtermPullbackConfig] = None):
        self.cfg = cfg or BTCETHMidtermPullbackConfig()

        self.cfg.trend_tf = os.getenv("MTPB_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("MTPB_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("MTPB_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("MTPB_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("MTPB_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_slope_bars = _env_int("MTPB_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.trend_slope_min_pct = _env_float("MTPB_TREND_SLOPE_MIN_PCT", self.cfg.trend_slope_min_pct)
        self.cfg.signal_ema_period = _env_int("MTPB_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.atr_period = _env_int("MTPB_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.max_pullback_pct = _env_float("MTPB_MAX_PULLBACK_PCT", self.cfg.max_pullback_pct)
        self.cfg.touch_tol_pct = _env_float("MTPB_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.reclaim_pct = _env_float("MTPB_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.swing_lookback_bars = _env_int("MTPB_SWING_LOOKBACK_BARS", self.cfg.swing_lookback_bars)
        self.cfg.sl_atr_mult = _env_float("MTPB_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.swing_sl_buffer_atr = _env_float("MTPB_SWING_SL_BUFFER_ATR", self.cfg.swing_sl_buffer_atr)
        self.cfg.rr = _env_float("MTPB_RR", self.cfg.rr)
        self.cfg.cooldown_bars_5m = _env_int("MTPB_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("MTPB_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("MTPB_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("MTPB_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("MTPB_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("MTPB_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, store) -> Optional[int]:
        lb = max(4, int(self.cfg.trend_slope_bars))
        need = max(self.cfg.trend_ema_slow + lb + 5, 260)
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, need) or []
        if len(rows) < self.cfg.trend_ema_slow + lb + 2:
            return None

        closes = [float(r[4]) for r in rows]
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        es_prev = _ema(closes[:-lb], self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)):
            return None
        if es_prev == 0:
            return None

        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.trend_slope_min_pct:
            return 2  # uptrend
        if ef < es and slope_pct <= -self.cfg.trend_slope_min_pct:
            return 0  # downtrend
        return 1  # neutral

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

        bias = self._trend_bias(store)
        if bias is None or bias == 1:
            return None

        need_1h = max(self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 5, 90)
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, need_1h) or []
        if len(rows_1h) < self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 2:
            return None

        highs = [float(r[2]) for r in rows_1h]
        lows = [float(r[3]) for r in rows_1h]
        closes = [float(r[4]) for r in rows_1h]
        ema1h = _ema(closes, self.cfg.signal_ema_period)
        atr1h = _atr_from_rows(rows_1h, self.cfg.atr_period)
        if not (math.isfinite(ema1h) and math.isfinite(atr1h) and atr1h > 0):
            return None

        prev_c = closes[-2]
        cur_c = closes[-1]
        look = max(3, min(len(rows_1h), int(self.cfg.swing_lookback_bars)))
        swing_low = min(lows[-look:])
        swing_high = max(highs[-look:])

        # Long: 4h uptrend + 1h pullback to EMA20 + reclaim.
        if self.cfg.allow_longs and bias == 2:
            touched = swing_low <= ema1h * (1.0 + self.cfg.touch_tol_pct / 100.0)
            reclaimed = (cur_c >= ema1h * (1.0 + self.cfg.reclaim_pct / 100.0)) and (prev_c <= ema1h * 1.003)
            pullback_pct = max(0.0, (ema1h - swing_low) / max(1e-12, ema1h) * 100.0)
            if touched and reclaimed and pullback_pct <= self.cfg.max_pullback_pct:
                swing_sl = swing_low - self.cfg.swing_sl_buffer_atr * atr1h
                atr_sl = float(c) - self.cfg.sl_atr_mult * atr1h
                sl = min(swing_sl, atr_sl)
                if sl >= float(c):
                    return None
                tp = float(c) + self.cfg.rr * (float(c) - sl)
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_midterm_pullback",
                    symbol=store.symbol,
                    side="long",
                    entry=float(c),
                    sl=float(sl),
                    tp=float(tp),
                    reason=f"mtpb_long trend4h pullback1h ema={self.cfg.signal_ema_period}",
                )

        # Short: 4h downtrend + 1h pullback to EMA20 + reclaim below EMA.
        if self.cfg.allow_shorts and bias == 0:
            touched = swing_high >= ema1h * (1.0 - self.cfg.touch_tol_pct / 100.0)
            reclaimed = (cur_c <= ema1h * (1.0 - self.cfg.reclaim_pct / 100.0)) and (prev_c >= ema1h * 0.997)
            pullback_pct = max(0.0, (swing_high - ema1h) / max(1e-12, ema1h) * 100.0)
            if touched and reclaimed and pullback_pct <= self.cfg.max_pullback_pct:
                swing_sl = swing_high + self.cfg.swing_sl_buffer_atr * atr1h
                atr_sl = float(c) + self.cfg.sl_atr_mult * atr1h
                sl = max(swing_sl, atr_sl)
                if sl <= float(c):
                    return None
                tp = float(c) - self.cfg.rr * (sl - float(c))
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_midterm_pullback",
                    symbol=store.symbol,
                    side="short",
                    entry=float(c),
                    sl=float(sl),
                    tp=float(tp),
                    reason=f"mtpb_short trend4h pullback1h ema={self.cfg.signal_ema_period}",
                )

        return None
