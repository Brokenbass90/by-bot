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


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for x in values[1:]:
        e = x * k + e * (1.0 - k)
    return e


def _atr(h: List[float], l: List[float], c: List[float], period: int) -> float:
    if len(c) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
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


def _sma(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period:
        return float("nan")
    w = values[-period:]
    return sum(w) / float(period) if w else float("nan")


@dataclass
class FlatBounceV3Config:
    lookback_bars: int = 220
    atr_period: int = 14
    ema_fast: int = 20
    ema_slow: int = 50
    max_ema_gap_pct: float = 0.42
    max_ema_slope_pct: float = 0.45
    min_atr_pct: float = 0.18
    max_atr_pct: float = 2.00
    min_range_width_atr: float = 2.8
    max_range_width_atr: float = 8.5

    zone_atr_mult: float = 0.42
    min_reject_wick_frac: float = 0.42
    min_reject_body_frac: float = 0.20
    min_touches: int = 3
    touches_lookback: int = 140
    rsi_period: int = 14
    rsi_oversold: float = 34.0
    rsi_overbought: float = 66.0

    vol_short_n: int = 8
    vol_long_n: int = 34
    vol_mult_min: float = 1.02

    breakout_kill_atr_mult: float = 0.70
    breakout_kill_cooldown: int = 28

    sl_atr_mult: float = 1.00
    rr1: float = 1.10
    rr2: float = 1.90
    cooldown_bars: int = 12
    max_signals_per_day: int = 2


class FlatBounceV3Strategy:
    """Flat-only bounce with stricter rejection/volume and breakout kill-switch."""

    def __init__(self, cfg: Optional[FlatBounceV3Config] = None):
        self.cfg = cfg or FlatBounceV3Config()
        self.cfg.lookback_bars = _env_int("FB3_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("FB3_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.ema_fast = _env_int("FB3_EMA_FAST", self.cfg.ema_fast)
        self.cfg.ema_slow = _env_int("FB3_EMA_SLOW", self.cfg.ema_slow)
        self.cfg.max_ema_gap_pct = _env_float("FB3_MAX_EMA_GAP_PCT", self.cfg.max_ema_gap_pct)
        self.cfg.max_ema_slope_pct = _env_float("FB3_MAX_EMA_SLOPE_PCT", self.cfg.max_ema_slope_pct)
        self.cfg.min_atr_pct = _env_float("FB3_MIN_ATR_PCT", self.cfg.min_atr_pct)
        self.cfg.max_atr_pct = _env_float("FB3_MAX_ATR_PCT", self.cfg.max_atr_pct)
        self.cfg.min_range_width_atr = _env_float("FB3_MIN_RANGE_WIDTH_ATR", self.cfg.min_range_width_atr)
        self.cfg.max_range_width_atr = _env_float("FB3_MAX_RANGE_WIDTH_ATR", self.cfg.max_range_width_atr)
        self.cfg.zone_atr_mult = _env_float("FB3_ZONE_ATR_MULT", self.cfg.zone_atr_mult)
        self.cfg.min_reject_wick_frac = _env_float("FB3_MIN_REJECT_WICK_FRAC", self.cfg.min_reject_wick_frac)
        self.cfg.min_reject_body_frac = _env_float("FB3_MIN_REJECT_BODY_FRAC", self.cfg.min_reject_body_frac)
        self.cfg.min_touches = _env_int("FB3_MIN_TOUCHES", self.cfg.min_touches)
        self.cfg.touches_lookback = _env_int("FB3_TOUCHES_LOOKBACK", self.cfg.touches_lookback)
        self.cfg.rsi_period = _env_int("FB3_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.rsi_oversold = _env_float("FB3_RSI_OVERSOLD", self.cfg.rsi_oversold)
        self.cfg.rsi_overbought = _env_float("FB3_RSI_OVERBOUGHT", self.cfg.rsi_overbought)
        self.cfg.vol_short_n = _env_int("FB3_VOL_SHORT_N", self.cfg.vol_short_n)
        self.cfg.vol_long_n = _env_int("FB3_VOL_LONG_N", self.cfg.vol_long_n)
        self.cfg.vol_mult_min = _env_float("FB3_VOL_MULT_MIN", self.cfg.vol_mult_min)
        self.cfg.breakout_kill_atr_mult = _env_float("FB3_BREAKOUT_KILL_ATR_MULT", self.cfg.breakout_kill_atr_mult)
        self.cfg.breakout_kill_cooldown = _env_int("FB3_BREAKOUT_KILL_COOLDOWN", self.cfg.breakout_kill_cooldown)
        self.cfg.sl_atr_mult = _env_float("FB3_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr1 = _env_float("FB3_RR1", self.cfg.rr1)
        self.cfg.rr2 = _env_float("FB3_RR2", self.cfg.rr2)
        self.cfg.cooldown_bars = _env_int("FB3_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("FB3_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._o: List[float] = []
        self._h: List[float] = []
        self._l: List[float] = []
        self._c: List[float] = []
        self._v: List[float] = []
        self._cooldown = 0
        self._kill_cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _is_flat_regime(self, atr_now: float) -> bool:
        need = max(self.cfg.ema_slow + 12, self.cfg.lookback_bars + 5)
        if len(self._c) < need:
            return False
        closes = self._c[-(self.cfg.ema_slow + 24):]
        ef = _ema(closes, self.cfg.ema_fast)
        es = _ema(closes, self.cfg.ema_slow)
        es_prev = _ema(closes[:-8], self.cfg.ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)) or closes[-1] <= 0:
            return False
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        slope_pct = abs((es - es_prev) / max(1e-12, abs(es_prev))) * 100.0
        atr_pct = atr_now / closes[-1] * 100.0
        return (
            gap_pct <= self.cfg.max_ema_gap_pct
            and slope_pct <= self.cfg.max_ema_slope_pct
            and self.cfg.min_atr_pct <= atr_pct <= self.cfg.max_atr_pct
        )

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = store
        self._o.append(o)
        self._h.append(h)
        self._l.append(l)
        self._c.append(c)
        self._v.append(max(0.0, float(v or 0.0)))

        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if self._kill_cooldown > 0:
            self._kill_cooldown -= 1
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        need = max(
            self.cfg.lookback_bars + 5,
            self.cfg.atr_period + 5,
            self.cfg.touches_lookback + 5,
            self.cfg.vol_long_n + 3,
        )
        if len(self._c) < need:
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None
        if not self._is_flat_regime(atr_now):
            return None

        hh = self._h[-(self.cfg.lookback_bars + 1):-1]
        ll = self._l[-(self.cfg.lookback_bars + 1):-1]
        if not hh or not ll:
            return None
        res = max(hh)
        sup = min(ll)
        if res <= sup:
            return None

        width = res - sup
        width_atr = width / atr_now
        if width_atr < self.cfg.min_range_width_atr or width_atr > self.cfg.max_range_width_atr:
            return None

        # breakout kill-switch: avoid mean reversion immediately after range escape
        prev_c = self._c[-2]
        if prev_c > (res + self.cfg.breakout_kill_atr_mult * atr_now) or prev_c < (sup - self.cfg.breakout_kill_atr_mult * atr_now):
            self._kill_cooldown = self.cfg.breakout_kill_cooldown
            return None

        zone = self.cfg.zone_atr_mult * atr_now
        near_res = abs(c - res) <= zone
        near_sup = abs(c - sup) <= zone

        # touches maturity
        touch_h = self._h[-self.cfg.touches_lookback:]
        touch_l = self._l[-self.cfg.touches_lookback:]
        t_res = sum(1 for x in touch_h if abs(x - res) <= zone)
        t_sup = sum(1 for x in touch_l if abs(x - sup) <= zone)
        if t_res < self.cfg.min_touches or t_sup < self.cfg.min_touches:
            return None

        # rejection candle quality
        rng = max(1e-12, h - l)
        body_frac = abs(c - o) / rng
        upper_wick_frac = (h - max(o, c)) / rng
        lower_wick_frac = (min(o, c) - l) / rng
        bear_reject = c < o and body_frac >= self.cfg.min_reject_body_frac and upper_wick_frac >= self.cfg.min_reject_wick_frac
        bull_reject = c > o and body_frac >= self.cfg.min_reject_body_frac and lower_wick_frac >= self.cfg.min_reject_wick_frac

        # momentum confirmation
        rsi_now = _rsi(self._c, self.cfg.rsi_period)
        if not math.isfinite(rsi_now):
            return None
        vol_s = _sma(self._v, self.cfg.vol_short_n)
        vol_l = _sma(self._v, self.cfg.vol_long_n)
        if not (math.isfinite(vol_s) and math.isfinite(vol_l) and vol_l > 0):
            return None
        vol_ok = (vol_s / vol_l) >= self.cfg.vol_mult_min
        if not vol_ok:
            return None

        mid = (res + sup) * 0.5
        dist_from_mid = abs(c - mid) / max(1e-12, width)
        if dist_from_mid < 0.30:
            return None

        if near_res and bear_reject and rsi_now >= self.cfg.rsi_overbought and h > res and c < res:
            entry = c
            sl = max(h, res) + self.cfg.sl_atr_mult * atr_now
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = min(mid, entry - self.cfg.rr1 * risk)
            tp2 = min(entry - self.cfg.rr2 * risk, res - 0.12 * width)
            if not (tp2 < tp1 < entry):
                return None
            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="flat_bounce_v3",
                symbol=getattr(store, "symbol", ""),
                side="short",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=[0.60, 0.40],
                reason="fb3_short_res_bounce",
            )

        if near_sup and bull_reject and rsi_now <= self.cfg.rsi_oversold and l < sup and c > sup:
            entry = c
            sl = min(l, sup) - self.cfg.sl_atr_mult * atr_now
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = max(mid, entry + self.cfg.rr1 * risk)
            tp2 = max(entry + self.cfg.rr2 * risk, sup + 0.12 * width)
            if not (tp2 > tp1 > entry):
                return None
            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="flat_bounce_v3",
                symbol=getattr(store, "symbol", ""),
                side="long",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=[0.60, 0.40],
                reason="fb3_long_sup_bounce",
            )
        return None

