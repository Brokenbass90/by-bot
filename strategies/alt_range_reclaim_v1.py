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
class AltRangeReclaimV1Config:
    regime_tf: str = "240"
    regime_lookback: int = 60
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_max_gap_pct: float = 3.0
    regime_max_slope_pct: float = 1.8
    regime_min_atr_pct: float = 0.6
    regime_max_atr_pct: float = 5.5
    min_drawdown_from_high_pct: float = 18.0

    signal_tf: str = "60"
    signal_lookback: int = 72
    signal_ema_period: int = 20
    signal_atr_period: int = 14
    min_range_pct: float = 6.0
    max_range_pct: float = 35.0
    support_touch_buffer_atr: float = 0.35
    reclaim_above_support_atr: float = 0.10
    min_body_frac: float = 0.25
    max_dist_from_support_pct: float = 1.2
    rsi_period: int = 14
    max_rsi: float = 42.0
    min_close_vs_ema_pct: float = -0.4
    max_extension_above_ema_pct: float = 1.5

    sl_atr_mult: float = 0.80
    tp1_frac: float = 0.60
    tp2_buffer_pct: float = 0.45
    time_stop_bars_5m: int = 576
    cooldown_bars_5m: int = 72


class AltRangeReclaimV1Strategy:
    """Long-only flat/depressed-alt reclaim to the opposite side of the range."""

    def __init__(self, cfg: Optional[AltRangeReclaimV1Config] = None):
        self.cfg = cfg or AltRangeReclaimV1Config()

        self.cfg.regime_tf = os.getenv("ARR1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_lookback = _env_int("ARR1_REGIME_LOOKBACK", self.cfg.regime_lookback)
        self.cfg.regime_ema_fast = _env_int("ARR1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("ARR1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_max_gap_pct = _env_float("ARR1_REGIME_MAX_GAP_PCT", self.cfg.regime_max_gap_pct)
        self.cfg.regime_max_slope_pct = _env_float("ARR1_REGIME_MAX_SLOPE_PCT", self.cfg.regime_max_slope_pct)
        self.cfg.regime_min_atr_pct = _env_float("ARR1_REGIME_MIN_ATR_PCT", self.cfg.regime_min_atr_pct)
        self.cfg.regime_max_atr_pct = _env_float("ARR1_REGIME_MAX_ATR_PCT", self.cfg.regime_max_atr_pct)
        self.cfg.min_drawdown_from_high_pct = _env_float("ARR1_MIN_DD_FROM_HIGH_PCT", self.cfg.min_drawdown_from_high_pct)

        self.cfg.signal_tf = os.getenv("ARR1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("ARR1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.signal_ema_period = _env_int("ARR1_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.signal_atr_period = _env_int("ARR1_SIGNAL_ATR_PERIOD", self.cfg.signal_atr_period)
        self.cfg.min_range_pct = _env_float("ARR1_MIN_RANGE_PCT", self.cfg.min_range_pct)
        self.cfg.max_range_pct = _env_float("ARR1_MAX_RANGE_PCT", self.cfg.max_range_pct)
        self.cfg.support_touch_buffer_atr = _env_float("ARR1_SUPPORT_TOUCH_BUFFER_ATR", self.cfg.support_touch_buffer_atr)
        self.cfg.reclaim_above_support_atr = _env_float("ARR1_RECLAIM_ABOVE_SUPPORT_ATR", self.cfg.reclaim_above_support_atr)
        self.cfg.min_body_frac = _env_float("ARR1_MIN_BODY_FRAC", self.cfg.min_body_frac)
        self.cfg.max_dist_from_support_pct = _env_float("ARR1_MAX_DIST_FROM_SUPPORT_PCT", self.cfg.max_dist_from_support_pct)
        self.cfg.rsi_period = _env_int("ARR1_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.max_rsi = _env_float("ARR1_MAX_RSI", self.cfg.max_rsi)
        self.cfg.min_close_vs_ema_pct = _env_float("ARR1_MIN_CLOSE_VS_EMA_PCT", self.cfg.min_close_vs_ema_pct)
        self.cfg.max_extension_above_ema_pct = _env_float("ARR1_MAX_EXTENSION_ABOVE_EMA_PCT", self.cfg.max_extension_above_ema_pct)

        self.cfg.sl_atr_mult = _env_float("ARR1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_frac = _env_float("ARR1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_buffer_pct = _env_float("ARR1_TP2_BUFFER_PCT", self.cfg.tp2_buffer_pct)
        self.cfg.time_stop_bars_5m = _env_int("ARR1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("ARR1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)

        self._allow = _env_csv_set("ARR1_SYMBOL_ALLOWLIST", "ADAUSDT,DOGEUSDT,LINKUSDT,LTCUSDT")
        self._deny = _env_csv_set("ARR1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._last_regime_tf_ts: Optional[int] = None
        self._last_regime_ok: Optional[bool] = None

    def _regime_ok(self, store) -> bool:
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, max(self.cfg.regime_lookback, self.cfg.regime_ema_slow + 8)) or []
        if len(rows) < self.cfg.regime_ema_slow + 8:
            return False
        tf_ts = int(float(rows[-1][0]))
        if self._last_regime_tf_ts is not None and tf_ts == self._last_regime_tf_ts and self._last_regime_ok is not None:
            return bool(self._last_regime_ok)
        closes = [float(r[4]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        cur = closes[-1]
        if cur <= 0:
            return False

        ef = _ema(closes, self.cfg.regime_ema_fast)
        es = _ema(closes, self.cfg.regime_ema_slow)
        es_prev = _ema(closes[:-6], self.cfg.regime_ema_slow)
        atr = _atr_from_rows(rows, 14)
        if not all(math.isfinite(x) for x in (ef, es, es_prev, atr)) or atr <= 0:
            return False

        gap_pct = abs(ef - es) / cur * 100.0
        slope_pct = abs((es - es_prev) / max(1e-12, abs(es_prev))) * 100.0
        atr_pct = atr / cur * 100.0
        high_lookback = max(highs[-self.cfg.regime_lookback:])
        dd_from_high = (high_lookback - cur) / max(1e-12, high_lookback) * 100.0

        ok = (
            gap_pct <= self.cfg.regime_max_gap_pct
            and slope_pct <= self.cfg.regime_max_slope_pct
            and self.cfg.regime_min_atr_pct <= atr_pct <= self.cfg.regime_max_atr_pct
            and dd_from_high >= self.cfg.min_drawdown_from_high_pct
        )
        self._last_regime_tf_ts = tf_ts
        self._last_regime_ok = bool(ok)
        return bool(ok)

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
        if not self._regime_ok(store):
            return None

        need = max(self.cfg.signal_lookback, self.cfg.signal_ema_period + self.cfg.rsi_period + 5)
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        if len(rows) < need:
            return None

        tf_ts = int(float(rows[-1][0]))
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts
            return None
        if tf_ts == self._last_tf_ts:
            return None
        self._last_tf_ts = tf_ts

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]

        cur = closes[-1]
        prev = closes[-2]
        ema = _ema(closes, self.cfg.signal_ema_period)
        atr = _atr_from_rows(rows, self.cfg.signal_atr_period)
        rsi = _rsi(closes, self.cfg.rsi_period)
        if not all(math.isfinite(x) for x in (ema, atr, rsi)) or cur <= 0 or atr <= 0:
            return None

        support = min(lows[-self.cfg.signal_lookback:-1])
        resistance = max(highs[-self.cfg.signal_lookback:-1])
        range_pct = (resistance - support) / max(1e-12, cur) * 100.0
        if range_pct < self.cfg.min_range_pct or range_pct > self.cfg.max_range_pct:
            return None

        low_now = lows[-1]
        body = abs(cur - opens[-1])
        bar_range = max(1e-12, highs[-1] - lows[-1])
        body_frac = body / bar_range
        touched_support = low_now <= support + self.cfg.support_touch_buffer_atr * atr
        reclaimed = cur >= support + self.cfg.reclaim_above_support_atr * atr and cur > prev
        dist_from_support_pct = (cur - support) / max(1e-12, support) * 100.0
        close_vs_ema_pct = (cur - ema) / max(1e-12, ema) * 100.0
        ema_extension_pct = (cur - ema) / max(1e-12, ema) * 100.0

        if not (
            touched_support
            and reclaimed
            and body_frac >= self.cfg.min_body_frac
            and dist_from_support_pct <= self.cfg.max_dist_from_support_pct
            and rsi <= self.cfg.max_rsi
            and close_vs_ema_pct >= self.cfg.min_close_vs_ema_pct
            and ema_extension_pct <= self.cfg.max_extension_above_ema_pct
        ):
            return None

        sl = support - self.cfg.sl_atr_mult * atr
        if sl >= cur:
            return None
        tp2 = resistance * (1.0 - self.cfg.tp2_buffer_pct / 100.0)
        if tp2 <= cur:
            return None
        tp1 = cur + (tp2 - cur) * 0.55
        tp1_frac = min(0.9, max(0.1, self.cfg.tp1_frac))

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="alt_range_reclaim_v1",
            symbol=store.symbol,
            side="long",
            entry=float(c),
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=0.0,
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="arr1_alt_support_reclaim",
        )
        return sig if sig.validate() else None
