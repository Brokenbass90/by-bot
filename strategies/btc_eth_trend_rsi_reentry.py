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


def _rsi(vals: List[float], period: int = 14) -> float:
    if len(vals) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        d = vals[i] - vals[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    if losses <= 1e-12:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


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
class BTCETHTrendRSIReentryConfig:
    trend_tf: str = "60"
    signal_tf: str = "15"
    eval_tf_min: int = 15

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 8
    min_gap_pct: float = 0.10
    min_slope_pct: float = 0.05

    signal_ema_period: int = 20
    rsi_period: int = 14
    long_pullback_rsi_max: float = 38.0
    long_reclaim_rsi_min: float = 45.0
    short_pullback_rsi_min: float = 62.0
    short_reclaim_rsi_max: float = 55.0

    swing_lookback: int = 12
    atr_period: int = 14
    sl_atr_mult: float = 1.10
    rr: float = 1.9

    cooldown_bars_5m: int = 48
    max_signals_per_day: int = 3


class BTCETHTrendRSIReentryStrategy:
    """BTC/ETH trend continuation with RSI pullback/reclaim entries (long+short)."""

    def __init__(self, cfg: Optional[BTCETHTrendRSIReentryConfig] = None):
        self.cfg = cfg or BTCETHTrendRSIReentryConfig()
        self.cfg.trend_tf = os.getenv("TRR_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("TRR_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("TRR_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("TRR_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("TRR_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_slope_bars = _env_int("TRR_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.min_gap_pct = _env_float("TRR_MIN_GAP_PCT", self.cfg.min_gap_pct)
        self.cfg.min_slope_pct = _env_float("TRR_MIN_SLOPE_PCT", self.cfg.min_slope_pct)
        self.cfg.signal_ema_period = _env_int("TRR_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.rsi_period = _env_int("TRR_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.long_pullback_rsi_max = _env_float("TRR_LONG_PULLBACK_RSI_MAX", self.cfg.long_pullback_rsi_max)
        self.cfg.long_reclaim_rsi_min = _env_float("TRR_LONG_RECLAIM_RSI_MIN", self.cfg.long_reclaim_rsi_min)
        self.cfg.short_pullback_rsi_min = _env_float("TRR_SHORT_PULLBACK_RSI_MIN", self.cfg.short_pullback_rsi_min)
        self.cfg.short_reclaim_rsi_max = _env_float("TRR_SHORT_RECLAIM_RSI_MAX", self.cfg.short_reclaim_rsi_max)
        self.cfg.swing_lookback = _env_int("TRR_SWING_LOOKBACK", self.cfg.swing_lookback)
        self.cfg.atr_period = _env_int("TRR_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.sl_atr_mult = _env_float("TRR_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("TRR_RR", self.cfg.rr)
        self.cfg.cooldown_bars_5m = _env_int("TRR_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("TRR_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._allow = _env_csv_set("TRR_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("TRR_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, rows: List[list]) -> int:
        lb = max(4, int(self.cfg.trend_slope_bars))
        need = max(self.cfg.trend_ema_slow + lb + 2, 260)
        if len(rows) < need:
            return 1
        closes = [float(r[4]) for r in rows]
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

        rows_tr = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + self.cfg.trend_slope_bars + 20, 280)) or []
        rows_sig = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.signal_ema_period + self.cfg.swing_lookback + 25, 120)) or []
        if len(rows_sig) < self.cfg.signal_ema_period + self.cfg.swing_lookback + 5:
            return None

        bias = self._trend_bias(rows_tr)
        if bias == 1:
            return None

        highs = [float(r[2]) for r in rows_sig]
        lows = [float(r[3]) for r in rows_sig]
        closes = [float(r[4]) for r in rows_sig]
        ema_sig = _ema(closes, self.cfg.signal_ema_period)
        rsi_cur = _rsi(closes, self.cfg.rsi_period)
        rsi_prev = _rsi(closes[:-1], self.cfg.rsi_period)
        atr = _atr(rows_sig, self.cfg.atr_period)
        if not (math.isfinite(ema_sig) and math.isfinite(rsi_cur) and math.isfinite(rsi_prev) and math.isfinite(atr) and atr > 0):
            return None

        cur = closes[-1]
        prev = closes[-2]
        look = max(4, int(self.cfg.swing_lookback))
        swing_low = min(lows[-look:])
        swing_high = max(highs[-look:])

        if bias == 2:
            pullback = rsi_prev <= self.cfg.long_pullback_rsi_max
            reclaim = (rsi_cur >= self.cfg.long_reclaim_rsi_min) and (cur >= ema_sig) and (prev <= ema_sig * 1.01)
            if pullback and reclaim:
                sl = min(swing_low - 0.10 * atr, cur - self.cfg.sl_atr_mult * atr)
                if sl >= cur:
                    return None
                tp = cur + self.cfg.rr * (cur - sl)
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_trend_rsi_reentry",
                    symbol=store.symbol,
                    side="long",
                    entry=cur,
                    sl=sl,
                    tp=tp,
                    reason=f"trr_long rsi={rsi_cur:.1f}",
                )

        if bias == 0:
            pullback = rsi_prev >= self.cfg.short_pullback_rsi_min
            reclaim = (rsi_cur <= self.cfg.short_reclaim_rsi_max) and (cur <= ema_sig) and (prev >= ema_sig * 0.99)
            if pullback and reclaim:
                sl = max(swing_high + 0.10 * atr, cur + self.cfg.sl_atr_mult * atr)
                if sl <= cur:
                    return None
                tp = cur - self.cfg.rr * (sl - cur)
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                return TradeSignal(
                    strategy="btc_eth_trend_rsi_reentry",
                    symbol=store.symbol,
                    side="short",
                    entry=cur,
                    sl=sl,
                    tp=tp,
                    reason=f"trr_short rsi={rsi_cur:.1f}",
                )
        return None
