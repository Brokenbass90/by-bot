from __future__ import annotations

import math
import os
import statistics
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
class BTCETHVolExpansionConfig:
    trend_tf: str = "60"  # 1h
    signal_tf: str = "15"  # 15m
    eval_tf_min: int = 15

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    min_trend_gap_pct: float = 0.15

    bb_period: int = 20
    bb_dev: float = 2.0
    squeeze_lookback: int = 80
    squeeze_pctile: float = 0.25  # width must be in lowest 25%

    breakout_lookback: int = 16
    atr_period: int = 14
    sl_atr_mult: float = 1.20
    rr: float = 2.0
    cooldown_bars_5m: int = 30
    max_signals_per_day: int = 3


class BTCETHVolExpansionStrategy:
    """BTC/ETH volatility expansion: squeeze on 1h + breakout on 15m in trend direction."""

    def __init__(self, cfg: Optional[BTCETHVolExpansionConfig] = None):
        self.cfg = cfg or BTCETHVolExpansionConfig()

        self.cfg.trend_tf = os.getenv("VE_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("VE_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("VE_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("VE_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("VE_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.min_trend_gap_pct = _env_float("VE_MIN_TREND_GAP_PCT", self.cfg.min_trend_gap_pct)
        self.cfg.bb_period = _env_int("VE_BB_PERIOD", self.cfg.bb_period)
        self.cfg.bb_dev = _env_float("VE_BB_DEV", self.cfg.bb_dev)
        self.cfg.squeeze_lookback = _env_int("VE_SQUEEZE_LOOKBACK", self.cfg.squeeze_lookback)
        self.cfg.squeeze_pctile = _env_float("VE_SQUEEZE_PCTILE", self.cfg.squeeze_pctile)
        self.cfg.breakout_lookback = _env_int("VE_BREAKOUT_LOOKBACK", self.cfg.breakout_lookback)
        self.cfg.atr_period = _env_int("VE_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.sl_atr_mult = _env_float("VE_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("VE_RR", self.cfg.rr)
        self.cfg.cooldown_bars_5m = _env_int("VE_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("VE_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._allow = _env_csv_set("VE_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("VE_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, rows_1h: List[list]) -> int:
        if len(rows_1h) < self.cfg.trend_ema_slow + 5:
            return 1
        closes = [float(r[4]) for r in rows_1h]
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es)):
            return 1
        gap_pct = abs(ef - es) / max(1e-12, abs(closes[-1])) * 100.0
        if gap_pct < self.cfg.min_trend_gap_pct:
            return 1
        return 2 if ef > es else 0

    def _squeeze_ok(self, rows_1h: List[list]) -> bool:
        p = max(10, int(self.cfg.bb_period))
        need = max(p + 5, int(self.cfg.squeeze_lookback))
        if len(rows_1h) < need:
            return False
        closes = [float(r[4]) for r in rows_1h]
        widths: List[float] = []
        for i in range(p, len(closes)):
            w = closes[i - p:i]
            ma = sum(w) / float(p)
            if ma == 0:
                continue
            sd = statistics.pstdev(w) if len(w) > 1 else 0.0
            bb_w = (2.0 * self.cfg.bb_dev * sd) / abs(ma) * 100.0
            widths.append(bb_w)
        if len(widths) < 10:
            return False
        cur = widths[-1]
        ranked = sorted(widths[-int(self.cfg.squeeze_lookback):])
        idx = max(0, min(len(ranked) - 1, int(len(ranked) * self.cfg.squeeze_pctile)))
        thr = ranked[idx]
        return cur <= thr

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

        rows_1h = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + 20, self.cfg.squeeze_lookback + 20)) or []
        rows_15 = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.breakout_lookback + self.cfg.atr_period + 8, 80)) or []
        if len(rows_15) < self.cfg.breakout_lookback + self.cfg.atr_period + 2:
            return None

        bias = self._trend_bias(rows_1h)
        if bias == 1:
            return None
        if not self._squeeze_ok(rows_1h):
            return None

        highs = [float(r[2]) for r in rows_15]
        lows = [float(r[3]) for r in rows_15]
        closes = [float(r[4]) for r in rows_15]
        atr15 = _atr(rows_15, self.cfg.atr_period)
        if not math.isfinite(atr15) or atr15 <= 0:
            return None

        brk_n = max(5, int(self.cfg.breakout_lookback))
        hi = max(highs[-brk_n - 1:-1])
        lo = min(lows[-brk_n - 1:-1])
        cur = closes[-1]
        prev = closes[-2]

        if bias == 2 and cur > hi and prev <= hi:
            sl = cur - self.cfg.sl_atr_mult * atr15
            if sl >= cur:
                return None
            tp = cur + self.cfg.rr * (cur - sl)
            self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
            self._day_signals += 1
            return TradeSignal(
                strategy="btc_eth_vol_expansion",
                symbol=store.symbol,
                side="long",
                entry=cur,
                sl=sl,
                tp=tp,
                reason="ve_long squeeze_breakout",
            )

        if bias == 0 and cur < lo and prev >= lo:
            sl = cur + self.cfg.sl_atr_mult * atr15
            if sl <= cur:
                return None
            tp = cur - self.cfg.rr * (sl - cur)
            self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
            self._day_signals += 1
            return TradeSignal(
                strategy="btc_eth_vol_expansion",
                symbol=store.symbol,
                side="short",
                entry=cur,
                sl=sl,
                tp=tp,
                reason="ve_short squeeze_breakdown",
            )
        return None
