"""
scalper_bounce_v2 (SB2) — Высоко-качественный wick-bounce scalper.

Полный rewrite SC1.bounce mode. Главные отличия:

  • **HTF active alignment** (не passive non-conflict): 1H EMA21 ДОЛЖНА быть
    в направлении сделки. Long bounce — только при bullish 1H slope.
  • **Double pivot confirmation**: pivot level должен быть протестирован ≥ 2
    раз в lookback окне (это настоящий S/R, не случайный max/min)
  • **Volume z-score ≥ 2.5** на reject candle (versus SC1's слабый 1.0)
  • **Body retention ≥ 60%** (SC1 имел 45%)
  • **RR минимум 1.5 / 3.0** (SC1 имел 0.8 / 1.5 — слишком близко после fees)
  • **RSI confirmation**: long bounce требует RSI ≤ 40 (oversold);
    short требует RSI ≥ 60 (overbought)

Дизайн-цель: PF ≥ 1.5, DD ≤ 7%, 30-50 трейдов/мес — узкая высокая edge,
не широкая шумная mass-production.

Env vars (префикс SB2_)
-----------------------
  SB2_SYMBOL_ALLOWLIST           csv     BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT
  SB2_SIGNAL_TF                  str     5
  SB2_MACRO_TF                   str     60         (1H для EMA21 trend)
  SB2_SIGNAL_LOOKBACK            int     200
  SB2_ATR_PERIOD                 int     14
  SB2_RSI_PERIOD                 int     14
  SB2_PIVOT_LOOKBACK             int     30
  SB2_MIN_PIVOT_TOUCHES          int     2          (double pivot confirmation)
  SB2_PIVOT_TOUCH_TOLERANCE_ATR  float   0.25
  SB2_REJECT_BODY_FRAC           float   0.60       (>>0.45 SC1)
  SB2_REJECT_WICK_FRAC           float   0.35
  SB2_VOL_Z_MIN                  float   2.5        (>>1.0 SC1)
  SB2_RSI_LONG_MAX               float   40.0       (oversold required)
  SB2_RSI_SHORT_MIN              float   60.0       (overbought required)
  SB2_MACRO_EMA_PERIOD           int     21
  SB2_MIN_MACRO_SLOPE_PCT        float   0.15       (1H trend MUST align)
  SB2_MACRO_SLOPE_BARS           int     8
  SB2_MIN_ATR_PCT                float   0.25
  SB2_MAX_ATR_PCT                float   3.00
  SB2_SL_ATR_BUFFER              float   0.40
  SB2_TP1_RR                     float   1.50       (>>0.80 SC1, fee cushion)
  SB2_TP2_RR                     float   3.00       (>>1.50 SC1)
  SB2_TP1_FRAC                   float   0.50
  SB2_BE_TRIGGER_RR              float   0.80
  SB2_TIME_STOP_BARS_5M          int     48         (4h max hold)
  SB2_COOLDOWN_BARS_5M           int     24         (2h between trades per symbol)
  SB2_ALLOW_LONGS                bool    1
  SB2_ALLOW_SHORTS               bool    1

Author: Claude Opus, 2026-06-03. Rewrite of SC1.bounce — narrow + strict.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

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
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def _ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return values[:]
    k = 2.0 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1.0 - k))
    return ema


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs[-period:]) / period


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _vol_zscore(volumes: List[float], baseline_period: int = 40, recent_n: int = 1) -> float:
    if len(volumes) < baseline_period + recent_n:
        return 0.0
    base = volumes[-baseline_period - recent_n:-recent_n]
    recent = volumes[-recent_n:]
    if not base:
        return 0.0
    mean = sum(base) / len(base)
    var = sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return 0.0
    return ((sum(recent) / len(recent)) - mean) / std


def _slope_pct_per_bar(values: List[float], lookback: int, price_ref: float) -> float:
    if lookback <= 0 or len(values) < lookback + 1 or price_ref <= 0:
        return 0.0
    return ((values[-1] - values[-lookback - 1]) / price_ref) * 100.0 / lookback


def _count_pivot_touches(prices: List[float], pivot: float, tolerance: float) -> int:
    """Count how many bars within `prices` came within `tolerance` of `pivot`."""
    if tolerance <= 0:
        return 0
    return sum(1 for p in prices if abs(p - pivot) <= tolerance)


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@dataclass
class SB2Config:
    signal_tf: str = "5"
    macro_tf: str = "60"
    signal_lookback: int = 200
    atr_period: int = 14
    rsi_period: int = 14
    pivot_lookback: int = 30
    min_pivot_touches: int = 2
    pivot_touch_tolerance_atr: float = 0.25
    reject_body_frac: float = 0.60
    reject_wick_frac: float = 0.35
    vol_z_min: float = 2.5
    rsi_long_max: float = 40.0
    rsi_short_min: float = 60.0
    macro_ema_period: int = 21
    min_macro_slope_pct: float = 0.15
    macro_slope_bars: int = 8
    min_atr_pct: float = 0.25
    max_atr_pct: float = 3.00
    sl_atr_buffer: float = 0.40
    tp1_rr: float = 1.50
    tp2_rr: float = 3.00
    tp1_frac: float = 0.50
    be_trigger_rr: float = 0.80
    time_stop_bars_5m: int = 48
    cooldown_bars_5m: int = 24
    allow_longs: bool = True
    allow_shorts: bool = True


class ScalperBounceV2Strategy:
    """Wick-bounce off DOUBLE-confirmed pivot with HTF alignment + strong volume."""

    def __init__(self) -> None:
        self.cfg = SB2Config()
        self._load_env()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self.last_no_signal_reason: str = ""
        self._refresh_lists()

    def _no_signal(self, reason: str) -> None:
        self.last_no_signal_reason = str(reason or "unknown")

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("SB2_SIGNAL_TF", c.signal_tf)
        c.macro_tf = os.getenv("SB2_MACRO_TF", c.macro_tf)
        c.signal_lookback = _env_int("SB2_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("SB2_ATR_PERIOD", c.atr_period)
        c.rsi_period = _env_int("SB2_RSI_PERIOD", c.rsi_period)
        c.pivot_lookback = _env_int("SB2_PIVOT_LOOKBACK", c.pivot_lookback)
        c.min_pivot_touches = _env_int("SB2_MIN_PIVOT_TOUCHES", c.min_pivot_touches)
        c.pivot_touch_tolerance_atr = _env_float("SB2_PIVOT_TOUCH_TOLERANCE_ATR", c.pivot_touch_tolerance_atr)
        c.reject_body_frac = _env_float("SB2_REJECT_BODY_FRAC", c.reject_body_frac)
        c.reject_wick_frac = _env_float("SB2_REJECT_WICK_FRAC", c.reject_wick_frac)
        c.vol_z_min = _env_float("SB2_VOL_Z_MIN", c.vol_z_min)
        c.rsi_long_max = _env_float("SB2_RSI_LONG_MAX", c.rsi_long_max)
        c.rsi_short_min = _env_float("SB2_RSI_SHORT_MIN", c.rsi_short_min)
        c.macro_ema_period = _env_int("SB2_MACRO_EMA_PERIOD", c.macro_ema_period)
        c.min_macro_slope_pct = _env_float("SB2_MIN_MACRO_SLOPE_PCT", c.min_macro_slope_pct)
        c.macro_slope_bars = _env_int("SB2_MACRO_SLOPE_BARS", c.macro_slope_bars)
        c.min_atr_pct = _env_float("SB2_MIN_ATR_PCT", c.min_atr_pct)
        c.max_atr_pct = _env_float("SB2_MAX_ATR_PCT", c.max_atr_pct)
        c.sl_atr_buffer = _env_float("SB2_SL_ATR_BUFFER", c.sl_atr_buffer)
        c.tp1_rr = _env_float("SB2_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("SB2_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("SB2_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("SB2_BE_TRIGGER_RR", c.be_trigger_rr)
        c.time_stop_bars_5m = _env_int("SB2_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("SB2_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("SB2_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("SB2_ALLOW_SHORTS", c.allow_shorts)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set("SB2_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT")
        self._deny = _env_csv_set("SB2_SYMBOL_DENYLIST")

    def maybe_signal(
        self,
        store,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        cl: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        self.last_no_signal_reason = ""
        symbol = getattr(store, "symbol", "")
        c = self.cfg

        # Common gates
        if self._allow and symbol.upper() not in self._allow:
            self._no_signal("symbol_not_allowed")
            return None
        if self._deny and symbol.upper() in self._deny:
            self._no_signal("symbol_denied")
            return None
        if not c.allow_shorts and not c.allow_longs:
            self._no_signal("both_sides_disabled")
            return None
        if self._last_tf_ts is not None and ts_ms <= self._last_tf_ts:
            self._no_signal("same_signal_bar")
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            self._no_signal("cooldown")
            return None

        # Fetch klines
        try:
            rows_5m = store.fetch_klines(symbol, c.signal_tf, c.signal_lookback) or []
            rows_macro = store.fetch_klines(symbol, c.macro_tf, 80) or []
        except Exception:
            self._no_signal("history_short")
            return None

        if len(rows_5m) < c.pivot_lookback + 30 or len(rows_macro) < c.macro_ema_period + c.macro_slope_bars + 5:
            self._no_signal("history_short")
            return None

        opens5 = [float(r[1]) for r in rows_5m]
        highs5 = [float(r[2]) for r in rows_5m]
        lows5 = [float(r[3]) for r in rows_5m]
        closes5 = [float(r[4]) for r in rows_5m]
        volumes5 = [float(r[5]) for r in rows_5m]
        closes_macro = [float(r[4]) for r in rows_macro]

        atr = _atr(highs5, lows5, closes5, c.atr_period)
        price = closes5[-1]
        if atr <= 0 or price <= 0:
            self._no_signal("atr_invalid")
            return None
        atr_pct = (atr / price) * 100.0
        if atr_pct < c.min_atr_pct:
            self._no_signal(f"atr_too_low={atr_pct:.3f}")
            return None
        if atr_pct > c.max_atr_pct:
            self._no_signal(f"atr_too_high={atr_pct:.3f}")
            return None

        # Macro HTF EMA21 ACTIVE alignment
        macro_ema = _ema_series(closes_macro, c.macro_ema_period)
        macro_slope = _slope_pct_per_bar(macro_ema, c.macro_slope_bars, price)

        # Current bar metrics
        o, h, l, cl = opens5[-1], highs5[-1], lows5[-1], closes5[-1]
        rng = h - l
        if rng <= 0:
            self._no_signal("zero_range")
            return None
        body = abs(cl - o)
        upper_wick = h - max(o, cl)
        lower_wick = min(o, cl) - l
        body_frac = body / rng

        # Volume confirmation
        vol_z = _vol_zscore(volumes5, baseline_period=40, recent_n=1)
        if vol_z < c.vol_z_min:
            self._no_signal(f"vol_z_low={vol_z:.2f}")
            return None

        # RSI
        rsi = _rsi(closes5, c.rsi_period)

        # Find recent pivot level
        prior_lows = lows5[-c.pivot_lookback - 1:-1]
        prior_highs = highs5[-c.pivot_lookback - 1:-1]
        if not prior_lows or not prior_highs:
            self._no_signal("history_short")
            return None
        recent_low_pivot = min(prior_lows)
        recent_high_pivot = max(prior_highs)
        touch_tol = c.pivot_touch_tolerance_atr * atr

        # LONG bounce
        if c.allow_longs and macro_slope >= c.min_macro_slope_pct:
            touches_low = _count_pivot_touches(prior_lows, recent_low_pivot, touch_tol)
            touched_now = l <= recent_low_pivot + 0.20 * atr
            is_bull_reject = cl > o and body_frac >= c.reject_body_frac and (lower_wick / rng) >= c.reject_wick_frac
            rsi_oversold = rsi <= c.rsi_long_max
            if touches_low >= c.min_pivot_touches and touched_now and is_bull_reject and rsi_oversold:
                sl = recent_low_pivot - c.sl_atr_buffer * atr
                entry = cl
                risk = entry - sl
                if risk > 0:
                    tp1 = entry + c.tp1_rr * risk
                    self._last_tf_ts = ts_ms
                    self._cooldown = c.cooldown_bars_5m
                    return TradeSignal(
                        strategy="scalper_bounce_v2",
                        symbol=symbol, side="long", entry=entry, sl=sl, tp=tp1,
                        reason=(f"sb2_bounce_long pivot={recent_low_pivot:.6f} touches={touches_low} "
                                f"vol_z={vol_z:.2f} rsi={rsi:.1f} macro_slope={macro_slope:.3f}"),
                    )

        # SHORT bounce
        if c.allow_shorts and macro_slope <= -c.min_macro_slope_pct:
            touches_high = _count_pivot_touches(prior_highs, recent_high_pivot, touch_tol)
            touched_now = h >= recent_high_pivot - 0.20 * atr
            is_bear_reject = cl < o and body_frac >= c.reject_body_frac and (upper_wick / rng) >= c.reject_wick_frac
            rsi_overbought = rsi >= c.rsi_short_min
            if touches_high >= c.min_pivot_touches and touched_now and is_bear_reject and rsi_overbought:
                sl = recent_high_pivot + c.sl_atr_buffer * atr
                entry = cl
                risk = sl - entry
                if risk > 0:
                    tp1 = entry - c.tp1_rr * risk
                    self._last_tf_ts = ts_ms
                    self._cooldown = c.cooldown_bars_5m
                    return TradeSignal(
                        strategy="scalper_bounce_v2",
                        symbol=symbol, side="short", entry=entry, sl=sl, tp=tp1,
                        reason=(f"sb2_bounce_short pivot={recent_high_pivot:.6f} touches={touches_high} "
                                f"vol_z={vol_z:.2f} rsi={rsi:.1f} macro_slope={macro_slope:.3f}"),
                    )

        self._no_signal("no_setup")
        return None


class SB2Selector:
    def __init__(self):
        self._strategies: dict[str, ScalperBounceV2Strategy] = {}

    def get(self, symbol: str) -> ScalperBounceV2Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = ScalperBounceV2Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)
