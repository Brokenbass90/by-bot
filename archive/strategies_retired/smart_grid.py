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


def _ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for x in values[1:]:
        e = x * k + e * (1.0 - k)
    return e


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    if period <= 0 or len(closes) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / max(1, len(trs))


def _body_frac(o: float, h: float, l: float, c: float) -> float:
    rng = max(1e-12, h - l)
    return abs(c - o) / rng


@dataclass
class SmartGridConfig:
    lookback_bars: int = 120
    atr_period: int = 14
    range_min_pct: float = 0.8
    range_max_pct: float = 8.0

    ema_fast: int = 20
    ema_slow: int = 50
    trend_max_gap_pct: float = 0.35
    trend_slope_bars: int = 8
    trend_max_slope_pct: float = 0.12
    atr_min_pct: float = 0.25
    atr_max_pct: float = 1.80

    entry_zone_frac: float = 0.18
    touch_tolerance_pct: float = 0.08
    min_reject_body_frac: float = 0.25
    min_touches_per_side: int = 2
    touch_lookback_bars: int = 60

    sl_atr_mult: float = 1.1
    rr_min: float = 1.3
    tp2_to_opposite_frac: float = 0.90
    cooldown_bars: int = 12
    breakout_kill_atr_mult: float = 0.70
    breakout_pause_bars: int = 36
    max_signals_per_day: int = 3

    allow_longs: bool = True
    allow_shorts: bool = True


class SmartGridStrategy:
    """Grid-like mean reversion arm for range markets.

    This is a conservative v1:
    - Trades only in sideways regime (tight EMA spread + bounded local range).
    - Enters near range edges on rejection candles.
    - Uses 2 target ladder (mid-range + near opposite edge) with hard SL.

    Note: engine currently supports one open position per symbol, so this is not
    a true multi-order ladder grid. It is a safer "smart grid" proxy.
    """

    def __init__(self, cfg: Optional[SmartGridConfig] = None):
        self.cfg = cfg or SmartGridConfig()

        self.cfg.lookback_bars = _env_int("SG_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("SG_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.range_min_pct = _env_float("SG_RANGE_MIN_PCT", self.cfg.range_min_pct)
        self.cfg.range_max_pct = _env_float("SG_RANGE_MAX_PCT", self.cfg.range_max_pct)

        self.cfg.ema_fast = _env_int("SG_EMA_FAST", self.cfg.ema_fast)
        self.cfg.ema_slow = _env_int("SG_EMA_SLOW", self.cfg.ema_slow)
        self.cfg.trend_max_gap_pct = _env_float("SG_TREND_MAX_GAP_PCT", self.cfg.trend_max_gap_pct)
        self.cfg.trend_slope_bars = _env_int("SG_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.trend_max_slope_pct = _env_float("SG_TREND_MAX_SLOPE_PCT", self.cfg.trend_max_slope_pct)
        self.cfg.atr_min_pct = _env_float("SG_ATR_MIN_PCT", self.cfg.atr_min_pct)
        self.cfg.atr_max_pct = _env_float("SG_ATR_MAX_PCT", self.cfg.atr_max_pct)

        self.cfg.entry_zone_frac = _env_float("SG_ENTRY_ZONE_FRAC", self.cfg.entry_zone_frac)
        self.cfg.touch_tolerance_pct = _env_float("SG_TOUCH_TOL_PCT", self.cfg.touch_tolerance_pct)
        self.cfg.min_reject_body_frac = _env_float("SG_MIN_REJECT_BODY_FRAC", self.cfg.min_reject_body_frac)
        self.cfg.min_touches_per_side = _env_int("SG_MIN_TOUCHES_PER_SIDE", self.cfg.min_touches_per_side)
        self.cfg.touch_lookback_bars = _env_int("SG_TOUCH_LOOKBACK_BARS", self.cfg.touch_lookback_bars)

        self.cfg.sl_atr_mult = _env_float("SG_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr_min = _env_float("SG_RR_MIN", self.cfg.rr_min)
        self.cfg.tp2_to_opposite_frac = _env_float("SG_TP2_TO_OPPOSITE_FRAC", self.cfg.tp2_to_opposite_frac)
        self.cfg.cooldown_bars = _env_int("SG_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.breakout_kill_atr_mult = _env_float("SG_BREAKOUT_KILL_ATR_MULT", self.cfg.breakout_kill_atr_mult)
        self.cfg.breakout_pause_bars = _env_int("SG_BREAKOUT_PAUSE_BARS", self.cfg.breakout_pause_bars)
        self.cfg.max_signals_per_day = _env_int("SG_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self.cfg.allow_longs = _env_bool("SG_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("SG_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._o5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []
        self._c5: List[float] = []
        self._cooldown = 0
        self._regime_pause = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _sideways_regime_ok(self, atr_now: float) -> bool:
        need = max(self.cfg.ema_slow + 5, self.cfg.lookback_bars + 2)
        if len(self._c5) < need:
            return False

        closes = self._c5[-(self.cfg.ema_slow + 10):]
        ef = _ema(closes, self.cfg.ema_fast)
        es = _ema(closes, self.cfg.ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and closes[-1] > 0):
            return False
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        if gap_pct > self.cfg.trend_max_gap_pct:
            return False

        lb = max(3, int(self.cfg.trend_slope_bars))
        if len(closes) < self.cfg.ema_slow + lb + 2:
            return False
        es_prev = _ema(closes[:-lb], self.cfg.ema_slow)
        if not (math.isfinite(es_prev) and abs(es_prev) > 1e-12):
            return False
        slope_pct = abs((es - es_prev) / es_prev) * 100.0
        if slope_pct > self.cfg.trend_max_slope_pct:
            return False

        atr_pct = atr_now / max(1e-12, closes[-1]) * 100.0
        if atr_pct < self.cfg.atr_min_pct or atr_pct > self.cfg.atr_max_pct:
            return False

        return True

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (store, v)

        self._o5.append(o)
        self._h5.append(h)
        self._l5.append(l)
        self._c5.append(c)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if self._regime_pause > 0:
            self._regime_pause -= 1
            return None

        need = max(self.cfg.lookback_bars + 2, self.cfg.atr_period + 2, self.cfg.ema_slow + 5)
        if len(self._c5) < need:
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        h_prev = self._h5[-(self.cfg.lookback_bars + 1):-1]
        l_prev = self._l5[-(self.cfg.lookback_bars + 1):-1]
        hi = max(h_prev)
        lo = min(l_prev)
        width = hi - lo
        if width <= 0:
            return None

        range_pct = width / max(1e-12, c) * 100.0
        if range_pct < self.cfg.range_min_pct or range_pct > self.cfg.range_max_pct:
            return None

        atr_now = _atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None
        if not self._sideways_regime_ok(atr_now):
            return None

        # Kill-switch: if price impulsively exits local range, pause new entries.
        if c > hi + self.cfg.breakout_kill_atr_mult * atr_now or c < lo - self.cfg.breakout_kill_atr_mult * atr_now:
            self._regime_pause = max(self._regime_pause, int(self.cfg.breakout_pause_bars))
            return None

        zone = self.cfg.entry_zone_frac * width
        upper_zone = hi - zone
        lower_zone = lo + zone
        tol = self.cfg.touch_tolerance_pct / 100.0

        touched_upper = h >= hi * (1.0 - tol)
        touched_lower = l <= lo * (1.0 + tol)

        bodyf = _body_frac(o, h, l, c)
        is_bear_reject = (c < o) and (bodyf >= self.cfg.min_reject_body_frac)
        is_bull_reject = (c > o) and (bodyf >= self.cfg.min_reject_body_frac)

        # Require range "maturity": both sides should be touched multiple times recently.
        tlook = max(10, min(self.cfg.lookback_bars, int(self.cfg.touch_lookback_bars)))
        hh = self._h5[-tlook:]
        ll = self._l5[-tlook:]
        touch_hi = sum(1 for x in hh if x >= hi * (1.0 - tol))
        touch_lo = sum(1 for x in ll if x <= lo * (1.0 + tol))
        if touch_hi < int(self.cfg.min_touches_per_side) or touch_lo < int(self.cfg.min_touches_per_side):
            return None

        mid = (hi + lo) * 0.5

        if self.cfg.allow_shorts and c >= upper_zone and touched_upper and is_bear_reject:
            entry = c
            sl = max(h, hi) + self.cfg.sl_atr_mult * atr_now
            risk = sl - entry
            if risk <= 0:
                return None

            tp1 = min(mid, entry - self.cfg.rr_min * risk)
            tp2_raw = entry - self.cfg.tp2_to_opposite_frac * (entry - lo)
            tp2 = min(tp2_raw, entry - self.cfg.rr_min * risk)
            if not (tp2 < entry and tp1 < entry):
                return None
            tps = sorted({float(tp1), float(tp2)}, reverse=True)
            if len(tps) < 2:
                return None

            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="smart_grid",
                symbol=store.symbol,
                side="short",
                entry=entry,
                sl=sl,
                tp=tps[-1],
                tps=tps,
                tp_fracs=[0.6, 0.4],
                trailing_atr_mult=0.0,
                trailing_atr_period=self.cfg.atr_period,
                time_stop_bars=96,
                reason="sg_short_upper_reject",
            )

        if self.cfg.allow_longs and c <= lower_zone and touched_lower and is_bull_reject:
            entry = c
            sl = min(l, lo) - self.cfg.sl_atr_mult * atr_now
            risk = entry - sl
            if risk <= 0:
                return None

            tp1 = max(mid, entry + self.cfg.rr_min * risk)
            tp2_raw = entry + self.cfg.tp2_to_opposite_frac * (hi - entry)
            tp2 = max(tp2_raw, entry + self.cfg.rr_min * risk)
            if not (tp2 > entry and tp1 > entry):
                return None
            tps = sorted({float(tp1), float(tp2)})
            if len(tps) < 2:
                return None

            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="smart_grid",
                symbol=store.symbol,
                side="long",
                entry=entry,
                sl=sl,
                tp=tps[-1],
                tps=tps,
                tp_fracs=[0.6, 0.4],
                trailing_atr_mult=0.0,
                trailing_atr_period=self.cfg.atr_period,
                time_stop_bars=96,
                reason="sg_long_lower_reject",
            )

        return None
