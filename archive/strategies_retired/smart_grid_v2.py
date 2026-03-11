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


def _rsi(closes: List[float], period: int) -> float:
    if period <= 0 or len(closes) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    if losses <= 1e-12:
        return 100.0
    rs = (gains / period) / max(1e-12, (losses / period))
    return 100.0 - (100.0 / (1.0 + rs))


def _body_frac(o: float, h: float, l: float, c: float) -> float:
    rng = max(1e-12, h - l)
    return abs(c - o) / rng


@dataclass
class SmartGridV2Config:
    lookback_bars: int = 144
    atr_period: int = 14

    ema_mid: int = 64
    ema_slow: int = 160
    trend_guard_atr: float = 0.75
    trend_slope_bars: int = 12
    trend_slope_atr: float = 0.45

    atr_min_pct: float = 0.18
    atr_max_pct: float = 1.60
    range_min_pct: float = 0.8
    range_max_pct: float = 6.0

    entry_z_atr: float = 1.10
    reclaim_z_atr: float = 0.70
    wick_frac_min: float = 0.28
    body_frac_min: float = 0.22
    rsi_period: int = 14
    rsi_long_max: float = 40.0
    rsi_short_min: float = 60.0

    sl_atr_mult: float = 1.10
    tp_to_mean_buffer_atr: float = 0.06
    rr_cap: float = 1.9
    be_trigger_rr: float = 0.90
    time_stop_bars: int = 72

    breakout_kill_atr: float = 1.15
    breakout_pause_bars: int = 48
    cooldown_bars: int = 18
    max_signals_per_day: int = 2

    allow_longs: bool = True
    allow_shorts: bool = True


class SmartGridV2Strategy:
    """Safer flat-regime mean reversion arm.

    Unlike the legacy smart grid, this version trades only one clean excursion
    back to the local mean and pauses aggressively after range breaks.
    """

    def __init__(self, cfg: Optional[SmartGridV2Config] = None):
        self.cfg = cfg or SmartGridV2Config()

        self.cfg.lookback_bars = _env_int("SG2_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("SG2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.ema_mid = _env_int("SG2_EMA_MID", self.cfg.ema_mid)
        self.cfg.ema_slow = _env_int("SG2_EMA_SLOW", self.cfg.ema_slow)
        self.cfg.trend_guard_atr = _env_float("SG2_TREND_GUARD_ATR", self.cfg.trend_guard_atr)
        self.cfg.trend_slope_bars = _env_int("SG2_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.trend_slope_atr = _env_float("SG2_TREND_SLOPE_ATR", self.cfg.trend_slope_atr)

        self.cfg.atr_min_pct = _env_float("SG2_ATR_MIN_PCT", self.cfg.atr_min_pct)
        self.cfg.atr_max_pct = _env_float("SG2_ATR_MAX_PCT", self.cfg.atr_max_pct)
        self.cfg.range_min_pct = _env_float("SG2_RANGE_MIN_PCT", self.cfg.range_min_pct)
        self.cfg.range_max_pct = _env_float("SG2_RANGE_MAX_PCT", self.cfg.range_max_pct)

        self.cfg.entry_z_atr = _env_float("SG2_ENTRY_Z_ATR", self.cfg.entry_z_atr)
        self.cfg.reclaim_z_atr = _env_float("SG2_RECLAIM_Z_ATR", self.cfg.reclaim_z_atr)
        self.cfg.wick_frac_min = _env_float("SG2_WICK_FRAC_MIN", self.cfg.wick_frac_min)
        self.cfg.body_frac_min = _env_float("SG2_BODY_FRAC_MIN", self.cfg.body_frac_min)
        self.cfg.rsi_period = _env_int("SG2_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.rsi_long_max = _env_float("SG2_RSI_LONG_MAX", self.cfg.rsi_long_max)
        self.cfg.rsi_short_min = _env_float("SG2_RSI_SHORT_MIN", self.cfg.rsi_short_min)

        self.cfg.sl_atr_mult = _env_float("SG2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp_to_mean_buffer_atr = _env_float("SG2_TP_TO_MEAN_BUFFER_ATR", self.cfg.tp_to_mean_buffer_atr)
        self.cfg.rr_cap = _env_float("SG2_RR_CAP", self.cfg.rr_cap)
        self.cfg.be_trigger_rr = _env_float("SG2_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.time_stop_bars = _env_int("SG2_TIME_STOP_BARS", self.cfg.time_stop_bars)

        self.cfg.breakout_kill_atr = _env_float("SG2_BREAKOUT_KILL_ATR", self.cfg.breakout_kill_atr)
        self.cfg.breakout_pause_bars = _env_int("SG2_BREAKOUT_PAUSE_BARS", self.cfg.breakout_pause_bars)
        self.cfg.cooldown_bars = _env_int("SG2_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("SG2_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self.cfg.allow_longs = _env_bool("SG2_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("SG2_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._o5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []
        self._c5: List[float] = []
        self._cooldown = 0
        self._pause = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _flat_regime_ok(self, atr_now: float, mean_now: float) -> bool:
        need = max(self.cfg.lookback_bars + 2, self.cfg.ema_slow + self.cfg.trend_slope_bars + 4)
        if len(self._c5) < need:
            return False

        hi = max(self._h5[-self.cfg.lookback_bars :])
        lo = min(self._l5[-self.cfg.lookback_bars :])
        width_pct = (hi - lo) / max(1e-12, mean_now) * 100.0
        if width_pct < self.cfg.range_min_pct or width_pct > self.cfg.range_max_pct:
            return False

        atr_pct = atr_now / max(1e-12, mean_now) * 100.0
        if atr_pct < self.cfg.atr_min_pct or atr_pct > self.cfg.atr_max_pct:
            return False

        closes = self._c5[-(self.cfg.ema_slow + self.cfg.trend_slope_bars + 6) :]
        em_mid = _ema(closes, self.cfg.ema_mid)
        em_slow = _ema(closes, self.cfg.ema_slow)
        if not (math.isfinite(em_mid) and math.isfinite(em_slow)):
            return False

        if abs(em_mid - em_slow) > self.cfg.trend_guard_atr * atr_now:
            return False

        em_prev = _ema(closes[: -self.cfg.trend_slope_bars], self.cfg.ema_mid)
        if not math.isfinite(em_prev):
            return False
        slope_abs = abs(em_mid - em_prev)
        if slope_abs > self.cfg.trend_slope_atr * atr_now:
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
        if self._pause > 0:
            self._pause -= 1
            return None

        need = max(self.cfg.lookback_bars + 2, self.cfg.ema_slow + self.cfg.trend_slope_bars + 6, self.cfg.rsi_period + 2)
        if len(self._c5) < need:
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        atr_now = _atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        mean_now = _ema(self._c5[-(self.cfg.ema_mid * 2) :], self.cfg.ema_mid)
        rsi_now = _rsi(self._c5, self.cfg.rsi_period)
        if not (math.isfinite(atr_now) and atr_now > 0 and math.isfinite(mean_now) and mean_now > 0 and math.isfinite(rsi_now)):
            return None

        if not self._flat_regime_ok(atr_now, mean_now):
            return None

        z_close = (c - mean_now) / max(1e-12, atr_now)
        z_low = (l - mean_now) / max(1e-12, atr_now)
        z_high = (h - mean_now) / max(1e-12, atr_now)

        # Strong break from the local mean => pause instead of fading.
        if z_close >= self.cfg.breakout_kill_atr or z_close <= -self.cfg.breakout_kill_atr:
            self._pause = max(self._pause, int(self.cfg.breakout_pause_bars))
            return None

        rng = max(1e-12, h - l)
        body_frac = _body_frac(o, h, l, c)
        upper_wick_frac = (h - max(o, c)) / rng
        lower_wick_frac = (min(o, c) - l) / rng

        if (
            self.cfg.allow_longs
            and z_low <= -self.cfg.entry_z_atr
            and z_close >= -self.cfg.reclaim_z_atr
            and c > o
            and body_frac >= self.cfg.body_frac_min
            and lower_wick_frac >= self.cfg.wick_frac_min
            and rsi_now <= self.cfg.rsi_long_max
        ):
            entry = c
            sl = min(l, entry - self.cfg.sl_atr_mult * atr_now)
            risk = entry - sl
            if risk <= 0:
                return None
            mean_tp = mean_now - self.cfg.tp_to_mean_buffer_atr * atr_now
            rr_tp = entry + self.cfg.rr_cap * risk
            tp = min(mean_tp, rr_tp)
            if tp <= entry:
                return None
            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="smart_grid_v2",
                symbol=store.symbol,
                side="long",
                entry=entry,
                sl=sl,
                tp=tp,
                be_trigger_rr=self.cfg.be_trigger_rr,
                time_stop_bars=self.cfg.time_stop_bars,
                reason="sg2_long_reclaim",
            )

        if (
            self.cfg.allow_shorts
            and z_high >= self.cfg.entry_z_atr
            and z_close <= self.cfg.reclaim_z_atr
            and c < o
            and body_frac >= self.cfg.body_frac_min
            and upper_wick_frac >= self.cfg.wick_frac_min
            and rsi_now >= self.cfg.rsi_short_min
        ):
            entry = c
            sl = max(h, entry + self.cfg.sl_atr_mult * atr_now)
            risk = sl - entry
            if risk <= 0:
                return None
            mean_tp = mean_now + self.cfg.tp_to_mean_buffer_atr * atr_now
            rr_tp = entry - self.cfg.rr_cap * risk
            tp = max(mean_tp, rr_tp)
            if tp >= entry:
                return None
            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="smart_grid_v2",
                symbol=store.symbol,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp,
                be_trigger_rr=self.cfg.be_trigger_rr,
                time_stop_bars=self.cfg.time_stop_bars,
                reason="sg2_short_reclaim",
            )

        return None
