"""
alt_support_bounce_v1 — Long counterpart of alt_resistance_fade_v1

LONG strategy that buys at key support levels when market is in uptrend
or range-bound. Mirror logic of ARF1 but for longs.

Key features:
- 4h regime check: EMA20/EMA50 gap small (flat) OR EMA20 > EMA50 (uptrend)
- 1h signal: price touches 72-bar low support, then bounces with bullish bar
- RSI(14) on 1h <= 42 (oversold area)
- Bullish confirmation: close > open, body >= 22% of range
- Close within 1.4% below 20-period EMA (not too extended)
- SL: below support - 0.85 × ATR
- TP1: 55% to resistance
- TP2: resistance - 0.45% buffer

Typical env config:
    ASB1_SYMBOL_ALLOWLIST=ETHUSDT,ADAUSDT,DOTUSDT
    ASB1_MIN_RSI=30.0
    ASB1_MAX_RSI=42.0
    ASB1_SL_ATR_MULT=0.85
    ASB1_TP1_FRAC=0.60
    ASB1_ALLOW_LONGS=1
    ASB1_ALLOW_SHORTS=0
"""
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
    return v.strip().lower() in {"1", "true", "yes", "on"}


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
class AltSupportBounceV1Config:
    # Regime check on 4h
    regime_tf: str = "240"
    regime_lookback: int = 60
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_max_gap_pct: float = 3.2
    regime_max_slope_pct: float = 1.8
    regime_min_atr_pct: float = 0.8
    regime_max_atr_pct: float = 6.5

    # Signal on 1h
    signal_tf: str = "60"
    signal_lookback: int = 72
    signal_ema_period: int = 20
    signal_atr_period: int = 14
    min_range_pct: float = 5.0
    max_range_pct: float = 30.0
    support_touch_buffer_atr: float = 0.35
    reclaim_above_supp_atr: float = 0.12
    min_body_frac: float = 0.22
    max_close_vs_ema_pct: float = 1.4
    rsi_period: int = 14
    min_rsi: float = 30.0
    max_rsi: float = 42.0

    # Exit management
    sl_atr_mult: float = 0.85
    tp1_frac: float = 0.60
    tp2_buffer_pct: float = 0.45
    trail_atr_mult: float = 0.0
    trail_atr_period: int = 14
    time_stop_bars_5m: int = 576
    cooldown_bars_5m: int = 72
    allow_longs: bool = True
    allow_shorts: bool = False


class AltSupportBounceV1Strategy:
    """Long-only support bounce strategy for uptrend/range regimes."""

    def __init__(self, cfg: Optional[AltSupportBounceV1Config] = None):
        self.cfg = cfg or AltSupportBounceV1Config()

        self.cfg.regime_tf = os.getenv("ASB1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_lookback = _env_int("ASB1_REGIME_LOOKBACK", self.cfg.regime_lookback)
        self.cfg.regime_ema_fast = _env_int("ASB1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("ASB1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_max_gap_pct = _env_float("ASB1_REGIME_MAX_GAP_PCT", self.cfg.regime_max_gap_pct)
        self.cfg.regime_max_slope_pct = _env_float("ASB1_REGIME_MAX_SLOPE_PCT", self.cfg.regime_max_slope_pct)
        self.cfg.regime_min_atr_pct = _env_float("ASB1_REGIME_MIN_ATR_PCT", self.cfg.regime_min_atr_pct)
        self.cfg.regime_max_atr_pct = _env_float("ASB1_REGIME_MAX_ATR_PCT", self.cfg.regime_max_atr_pct)

        self.cfg.signal_tf = os.getenv("ASB1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("ASB1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.signal_ema_period = _env_int("ASB1_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.signal_atr_period = _env_int("ASB1_SIGNAL_ATR_PERIOD", self.cfg.signal_atr_period)
        self.cfg.min_range_pct = _env_float("ASB1_MIN_RANGE_PCT", self.cfg.min_range_pct)
        self.cfg.max_range_pct = _env_float("ASB1_MAX_RANGE_PCT", self.cfg.max_range_pct)
        self.cfg.support_touch_buffer_atr = _env_float("ASB1_SUPP_TOUCH_BUFFER_ATR", self.cfg.support_touch_buffer_atr)
        self.cfg.reclaim_above_supp_atr = _env_float("ASB1_RECLAIM_ABOVE_SUPP_ATR", self.cfg.reclaim_above_supp_atr)
        self.cfg.min_body_frac = _env_float("ASB1_MIN_BODY_FRAC", self.cfg.min_body_frac)
        self.cfg.max_close_vs_ema_pct = _env_float("ASB1_MAX_CLOSE_VS_EMA_PCT", self.cfg.max_close_vs_ema_pct)
        self.cfg.rsi_period = _env_int("ASB1_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.min_rsi = _env_float("ASB1_MIN_RSI", self.cfg.min_rsi)
        self.cfg.max_rsi = _env_float("ASB1_MAX_RSI", self.cfg.max_rsi)

        self.cfg.sl_atr_mult = _env_float("ASB1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_frac = _env_float("ASB1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_buffer_pct = _env_float("ASB1_TP2_BUFFER_PCT", self.cfg.tp2_buffer_pct)
        self.cfg.trail_atr_mult = _env_float("ASB1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_atr_period = _env_int("ASB1_TRAIL_ATR_PERIOD", self.cfg.trail_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("ASB1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("ASB1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("ASB1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("ASB1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("ASB1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ASB1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._last_regime_tf_ts: Optional[int] = None
        self._last_regime_ok: Optional[bool] = None
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("ASB1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ASB1_SYMBOL_DENYLIST")

    def _regime_ok(self, store) -> bool:
        """Check if regime is bullish/flat (EMA20 >= EMA50 or gap small on 4h)."""
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

        ema_fast = _ema(closes, self.cfg.regime_ema_fast)
        ema_slow = _ema(closes, self.cfg.regime_ema_slow)
        ema_slow_prev = _ema(closes[:-6], self.cfg.regime_ema_slow)
        atr = _atr_from_rows(rows, 14)
        if not all(math.isfinite(x) for x in (ema_fast, ema_slow, ema_slow_prev, atr)) or atr <= 0:
            return False

        gap_pct = abs(ema_fast - ema_slow) / cur * 100.0
        slope_pct = abs((ema_slow - ema_slow_prev) / max(1e-12, abs(ema_slow_prev))) * 100.0
        atr_pct = atr / cur * 100.0

        # Bullish: EMA20 > EMA50 OR gap very small (flat)
        ok = (ema_fast >= ema_slow or gap_pct <= 1.0) and slope_pct <= self.cfg.regime_max_slope_pct and self.cfg.regime_min_atr_pct <= atr_pct <= self.cfg.regime_max_atr_pct

        self._last_regime_tf_ts = tf_ts
        self._last_regime_ok = bool(ok)
        return bool(ok)

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, v)
        self._refresh_runtime_allowlists()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if not self.cfg.allow_longs:
            return None

        if not self._regime_ok(store):
            self.last_no_signal_reason = "regime_not_bullish"
            return None

        need = max(self.cfg.signal_lookback, self.cfg.signal_ema_period + self.cfg.rsi_period + 5)
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        if len(rows) < need:
            self.last_no_signal_reason = "not_enough_signal_bars"
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
            self.last_no_signal_reason = "calc_error"
            return None

        support = min(lows[-self.cfg.signal_lookback:-1])
        resistance = max(highs[-self.cfg.signal_lookback:-1])
        range_pct = (resistance - support) / max(1e-12, cur) * 100.0
        if range_pct < self.cfg.min_range_pct or range_pct > self.cfg.max_range_pct:
            self.last_no_signal_reason = f"range_invalid_{range_pct:.1f}pct"
            return None

        # RSI must be in oversold region
        if rsi < self.cfg.min_rsi or rsi > self.cfg.max_rsi:
            self.last_no_signal_reason = f"rsi_invalid_{rsi:.1f}"
            return None

        low_now = lows[-1]
        body = abs(cur - opens[-1])
        bar_range = max(1e-12, highs[-1] - lows[-1])
        body_frac = body / bar_range

        # Touched support
        touched_supp = low_now <= support + self.cfg.support_touch_buffer_atr * atr
        # Reclaimed above support (bullish)
        reclaimed_above = cur >= support + self.cfg.reclaim_above_supp_atr * atr and cur > prev and cur > opens[-1]
        # Close vs EMA
        close_vs_ema_pct = (cur - ema) / max(1e-12, ema) * 100.0

        if not (
            touched_supp
            and reclaimed_above
            and body_frac >= self.cfg.min_body_frac
            and close_vs_ema_pct <= self.cfg.max_close_vs_ema_pct
        ):
            self.last_no_signal_reason = f"entry_conditions_not_met"
            return None

        # SL below support
        sl = support - self.cfg.sl_atr_mult * atr
        entry_price = float(c)

        if sl >= entry_price:
            self.last_no_signal_reason = "sl_above_entry"
            return None

        # TP2 at resistance with buffer
        tp2 = resistance * (1.0 - self.cfg.tp2_buffer_pct / 100.0)
        if tp2 <= entry_price:
            self.last_no_signal_reason = "tp_invalid"
            return None

        # TP1 at 55% to resistance
        tp1 = entry_price + (tp2 - entry_price) * 0.55
        tp1_frac = min(0.9, max(0.1, self.cfg.tp1_frac))

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="alt_support_bounce_v1",
            symbol=store.symbol,
            side="long",
            entry=entry_price,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="asb1_support_bounce",
        )
        return sig if sig.validate() else None
