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


def ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def atr(values_h: List[float], values_l: List[float], values_c: List[float], period: int = 14) -> float:
    if len(values_c) < period + 1:
        return float("nan")
    trs = []
    for i in range(-period, 0):
        h = values_h[i]
        l = values_l[i]
        pc = values_c[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / max(1, len(trs))


@dataclass
class AdaptiveRangeShortConfig:
    lookback_bars: int = 96
    atr_period: int = 14

    range_min_pct: float = 0.7
    range_max_pct: float = 8.0

    entry_zone_frac: float = 0.18
    touch_tol_pct: float = 0.08
    wick_min_frac: float = 0.18

    sl_atr_mult: float = 1.0
    min_rr: float = 1.4
    tp_frac_to_other_side: float = 0.60

    breakout_kill_atr_mult: float = 0.8
    kill_cooldown_bars: int = 36
    cooldown_bars: int = 10
    max_signals_per_day: int = 2

    trend_tf: str = "60"
    trend_ema_fast: int = 20
    trend_ema_slow: int = 50
    trend_gap_pct: float = 0.30

    allow_longs: bool = True
    allow_shorts: bool = True
    allow_countertrend: bool = False


class AdaptiveRangeShortStrategy:
    """Range mean-reversion with trend gate and hard kill-switch.

    - Trades only when local 5m range is valid.
    - In strong trend, trades only with trend unless allow_countertrend=1.
    - If price breaks range by breakout_kill_atr_mult*ATR, strategy pauses entries.
    """

    def __init__(self, cfg: Optional[AdaptiveRangeShortConfig] = None):
        self.cfg = cfg or AdaptiveRangeShortConfig()

        self.cfg.lookback_bars = _env_int("ARS_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("ARS_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.range_min_pct = _env_float("ARS_RANGE_MIN_PCT", self.cfg.range_min_pct)
        self.cfg.range_max_pct = _env_float("ARS_RANGE_MAX_PCT", self.cfg.range_max_pct)

        self.cfg.entry_zone_frac = _env_float("ARS_ENTRY_ZONE_FRAC", self.cfg.entry_zone_frac)
        self.cfg.touch_tol_pct = _env_float("ARS_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.wick_min_frac = _env_float("ARS_WICK_MIN_FRAC", self.cfg.wick_min_frac)

        self.cfg.sl_atr_mult = _env_float("ARS_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.min_rr = _env_float("ARS_MIN_RR", self.cfg.min_rr)
        self.cfg.tp_frac_to_other_side = _env_float("ARS_TP_FRAC_TO_OTHER", self.cfg.tp_frac_to_other_side)

        self.cfg.breakout_kill_atr_mult = _env_float("ARS_BREAKOUT_KILL_ATR_MULT", self.cfg.breakout_kill_atr_mult)
        self.cfg.kill_cooldown_bars = _env_int("ARS_KILL_COOLDOWN_BARS", self.cfg.kill_cooldown_bars)
        self.cfg.cooldown_bars = _env_int("ARS_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("ARS_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self.cfg.trend_tf = os.getenv("ARS_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema_fast = _env_int("ARS_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("ARS_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_gap_pct = _env_float("ARS_TREND_GAP_PCT", self.cfg.trend_gap_pct)

        self.cfg.allow_longs = _env_bool("ARS_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("ARS_ALLOW_SHORTS", self.cfg.allow_shorts)
        self.cfg.allow_countertrend = _env_bool("ARS_ALLOW_COUNTERTREND", self.cfg.allow_countertrend)

        self._c5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []
        self._o5: List[float] = []
        self._cooldown = 0
        self._kill_cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, store) -> int:
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + 10, 100)) or []
        if len(rows) < self.cfg.trend_ema_slow + 2:
            return 1
        closes = [float(x[4]) for x in rows]
        ef = ema(closes, self.cfg.trend_ema_fast)
        es = ema(closes, self.cfg.trend_ema_slow)
        if not math.isfinite(ef) or not math.isfinite(es) or closes[-1] <= 0:
            return 1
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        if gap_pct < self.cfg.trend_gap_pct:
            return 1
        return 2 if ef > es else 0

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = v

        self._o5.append(o)
        self._h5.append(h)
        self._l5.append(l)
        self._c5.append(c)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if self._kill_cooldown > 0:
            self._kill_cooldown -= 1
            return None

        n = len(self._c5)
        need = max(self.cfg.lookback_bars + 2, self.cfg.atr_period + 2)
        if n < need:
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        # Use previous bars for static range frame, current bar for trigger
        h_prev = self._h5[-(self.cfg.lookback_bars + 1):-1]
        l_prev = self._l5[-(self.cfg.lookback_bars + 1):-1]
        if not h_prev or not l_prev:
            return None

        hi = max(h_prev)
        lo = min(l_prev)
        width = hi - lo
        if width <= 0:
            return None
        range_pct = width / max(1e-12, c) * 100.0
        if range_pct < self.cfg.range_min_pct or range_pct > self.cfg.range_max_pct:
            return None

        atr5 = atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        if not math.isfinite(atr5) or atr5 <= 0:
            return None

        # Hard kill-switch when range is violated by a meaningful breakout
        if c > hi + self.cfg.breakout_kill_atr_mult * atr5 or c < lo - self.cfg.breakout_kill_atr_mult * atr5:
            self._kill_cooldown = self.cfg.kill_cooldown_bars
            return None

        bias = self._trend_bias(store)  # 0 bear, 1 neutral/range, 2 bull
        side_allowed_long = self.cfg.allow_longs and (bias in (1, 2) or self.cfg.allow_countertrend)
        side_allowed_short = self.cfg.allow_shorts and (bias in (0, 1) or self.cfg.allow_countertrend)

        zone = self.cfg.entry_zone_frac * width
        upper_zone = hi - zone
        lower_zone = lo + zone
        tol = self.cfg.touch_tol_pct / 100.0

        rng = max(1e-12, h - l)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        upper_wick_frac = upper_wick / rng
        lower_wick_frac = lower_wick / rng

        touched_upper = h >= hi * (1.0 - tol)
        touched_lower = l <= lo * (1.0 + tol)

        # Short from upper boundary (primary balance leg)
        if side_allowed_short and c >= upper_zone and touched_upper and c < o and upper_wick_frac >= self.cfg.wick_min_frac:
            sl = max(h, hi) + self.cfg.sl_atr_mult * atr5
            risk = sl - c
            if risk <= 0:
                return None

            tp_struct = c - self.cfg.tp_frac_to_other_side * (c - lo)
            tp_rr = c - self.cfg.min_rr * risk
            tp = min(tp_struct, tp_rr)
            if tp <= 0 or tp >= c:
                return None

            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="adaptive_range_short",
                symbol=store.symbol,
                side="short",
                entry=c,
                sl=sl,
                tp=tp,
                reason="ars_short_reject_upper",
            )

        # Long from lower boundary (optional balance leg)
        if side_allowed_long and c <= lower_zone and touched_lower and c > o and lower_wick_frac >= self.cfg.wick_min_frac:
            sl = min(l, lo) - self.cfg.sl_atr_mult * atr5
            risk = c - sl
            if risk <= 0:
                return None

            tp_struct = c + self.cfg.tp_frac_to_other_side * (hi - c)
            tp_rr = c + self.cfg.min_rr * risk
            tp = max(tp_struct, tp_rr)
            if tp <= c:
                return None

            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="adaptive_range_short",
                symbol=store.symbol,
                side="long",
                entry=c,
                sl=sl,
                tp=tp,
                reason="ars_long_reject_lower",
            )

        return None
