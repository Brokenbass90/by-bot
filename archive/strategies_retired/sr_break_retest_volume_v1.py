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
        e = v * k + e * (1 - k)
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


def sma(values: List[float], n: int) -> float:
    if n <= 0 or len(values) < n:
        return float("nan")
    return sum(values[-n:]) / float(n)


@dataclass
class SRBreakRetestVolumeV1Config:
    trend_tf: str = "60"
    trend_ema_fast: int = 20
    trend_ema_slow: int = 50
    trend_min_gap_pct: float = 0.20

    sr_lookback_bars: int = 48
    atr_period: int = 14
    vol_period: int = 20
    break_atr_mult: float = 0.18
    break_vol_mult: float = 1.15

    max_retest_bars: int = 8
    retest_touch_atr: float = 0.20
    reclaim_hold_atr: float = 0.05
    retest_vol_mult: float = 0.80
    invalidation_atr: float = 0.35

    sl_atr_mult: float = 1.30
    tp1_rr: float = 1.10
    tp2_rr: float = 2.60
    tp1_frac: float = 0.50
    tp2_frac: float = 0.30
    be_trigger_rr: float = 1.00
    be_lock_rr: float = 0.05
    trail_atr_mult: float = 1.70
    trail_atr_period: int = 14
    time_stop_bars_5m: int = 288

    cooldown_bars: int = 14
    max_signals_per_day: int = 2
    allow_longs: bool = True
    allow_shorts: bool = True


class SRBreakRetestVolumeV1Strategy:
    """Breakout -> retest -> hold with volume confirmation.

    Focused on price structure + volume; no EMA pullback entry.
    """

    def __init__(self, cfg: Optional[SRBreakRetestVolumeV1Config] = None):
        self.cfg = cfg or SRBreakRetestVolumeV1Config()

        self.cfg.trend_tf = os.getenv("SRV1_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema_fast = _env_int("SRV1_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("SRV1_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_min_gap_pct = _env_float("SRV1_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)

        self.cfg.sr_lookback_bars = _env_int("SRV1_SR_LOOKBACK_BARS", self.cfg.sr_lookback_bars)
        self.cfg.atr_period = _env_int("SRV1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.vol_period = _env_int("SRV1_VOL_PERIOD", self.cfg.vol_period)
        self.cfg.break_atr_mult = _env_float("SRV1_BREAK_ATR_MULT", self.cfg.break_atr_mult)
        self.cfg.break_vol_mult = _env_float("SRV1_BREAK_VOL_MULT", self.cfg.break_vol_mult)

        self.cfg.max_retest_bars = _env_int("SRV1_MAX_RETEST_BARS", self.cfg.max_retest_bars)
        self.cfg.retest_touch_atr = _env_float("SRV1_RETEST_TOUCH_ATR", self.cfg.retest_touch_atr)
        self.cfg.reclaim_hold_atr = _env_float("SRV1_RECLAIM_HOLD_ATR", self.cfg.reclaim_hold_atr)
        self.cfg.retest_vol_mult = _env_float("SRV1_RETEST_VOL_MULT", self.cfg.retest_vol_mult)
        self.cfg.invalidation_atr = _env_float("SRV1_INVALIDATION_ATR", self.cfg.invalidation_atr)

        self.cfg.sl_atr_mult = _env_float("SRV1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_rr = _env_float("SRV1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("SRV1_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("SRV1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_frac = _env_float("SRV1_TP2_FRAC", self.cfg.tp2_frac)
        self.cfg.be_trigger_rr = _env_float("SRV1_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("SRV1_BE_LOCK_RR", self.cfg.be_lock_rr)
        self.cfg.trail_atr_mult = _env_float("SRV1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_atr_period = _env_int("SRV1_TRAIL_ATR_PERIOD", self.cfg.trail_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("SRV1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)

        self.cfg.cooldown_bars = _env_int("SRV1_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("SRV1_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("SRV1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("SRV1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._c5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []
        self._v5: List[float] = []
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

        self._pending_long: Optional[dict] = None
        self._pending_short: Optional[dict] = None

    def _trend_bias(self, store) -> Optional[int]:
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(self.cfg.trend_ema_slow + 8, 100)) or []
        if len(rows) < self.cfg.trend_ema_slow + 2:
            return None
        closes = [float(x[4]) for x in rows]
        ef = ema(closes, self.cfg.trend_ema_fast)
        es = ema(closes, self.cfg.trend_ema_slow)
        if not math.isfinite(ef) or not math.isfinite(es) or closes[-1] <= 0:
            return None
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        if gap_pct < self.cfg.trend_min_gap_pct:
            return 1
        return 2 if ef > es else 0

    def _make_signal(self, store, side: str, entry: float, level: float, atr_now: float) -> Optional[TradeSignal]:
        if side == "long":
            sl = level - self.cfg.sl_atr_mult * atr_now
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = entry + self.cfg.tp1_rr * risk
            tp2 = entry + self.cfg.tp2_rr * risk
        else:
            sl = level + self.cfg.sl_atr_mult * atr_now
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = entry - self.cfg.tp1_rr * risk
            tp2 = entry - self.cfg.tp2_rr * risk

        return TradeSignal(
            strategy="sr_break_retest_volume_v1",
            symbol=store.symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[self.cfg.tp1_frac, self.cfg.tp2_frac],
            trailing_atr_mult=self.cfg.trail_atr_mult,
            trailing_atr_period=self.cfg.trail_atr_period,
            be_trigger_rr=self.cfg.be_trigger_rr,
            be_lock_rr=self.cfg.be_lock_rr,
            time_stop_bars=self.cfg.time_stop_bars_5m,
            reason=f"srv1_{side}_break_retest_hold",
        )

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = o
        self._c5.append(c)
        self._h5.append(h)
        self._l5.append(l)
        self._v5.append(v)

        if self._cooldown > 0:
            self._cooldown -= 1

        hist_need = max(self.cfg.sr_lookback_bars + 3, self.cfg.atr_period + 5, self.cfg.vol_period + 5)
        if len(self._c5) < hist_need:
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        bias = self._trend_bias(store)
        if bias is None:
            return None

        atr_now = atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None
        vol_avg = sma(self._v5[:-1], self.cfg.vol_period)
        if not math.isfinite(vol_avg) or vol_avg <= 0:
            return None

        i = len(self._c5) - 1

        # 1) Consume pending long retest
        if self._pending_long is not None:
            p = self._pending_long
            if i > int(p["expires_i"]):
                self._pending_long = None
            else:
                level = float(p["level"])
                touched = l <= (level + self.cfg.retest_touch_atr * atr_now)
                hold_ok = c >= (level + self.cfg.reclaim_hold_atr * atr_now)
                vol_ok = v >= vol_avg * self.cfg.retest_vol_mult
                invalid = c < (level - self.cfg.invalidation_atr * atr_now)
                if invalid:
                    self._pending_long = None
                elif touched and hold_ok and vol_ok and self._cooldown <= 0 and self.cfg.allow_longs and bias == 2:
                    sig = self._make_signal(store, "long", c, level, atr_now)
                    self._pending_long = None
                    if sig is not None:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return sig

        # 2) Consume pending short retest
        if self._pending_short is not None:
            p = self._pending_short
            if i > int(p["expires_i"]):
                self._pending_short = None
            else:
                level = float(p["level"])
                touched = h >= (level - self.cfg.retest_touch_atr * atr_now)
                hold_ok = c <= (level - self.cfg.reclaim_hold_atr * atr_now)
                vol_ok = v >= vol_avg * self.cfg.retest_vol_mult
                invalid = c > (level + self.cfg.invalidation_atr * atr_now)
                if invalid:
                    self._pending_short = None
                elif touched and hold_ok and vol_ok and self._cooldown <= 0 and self.cfg.allow_shorts and bias == 0:
                    sig = self._make_signal(store, "short", c, level, atr_now)
                    self._pending_short = None
                    if sig is not None:
                        self._cooldown = self.cfg.cooldown_bars
                        self._day_signals += 1
                        return sig

        # 3) Create new breakout states (first break, then wait retest)
        if self._cooldown <= 0:
            hi = max(self._h5[-(self.cfg.sr_lookback_bars + 1):-1])
            lo = min(self._l5[-(self.cfg.sr_lookback_bars + 1):-1])
            break_buf = self.cfg.break_atr_mult * atr_now
            vol_break_ok = v >= vol_avg * self.cfg.break_vol_mult

            if self.cfg.allow_longs and bias == 2 and vol_break_ok and c >= (hi + break_buf):
                self._pending_long = {"level": float(hi), "expires_i": int(i + self.cfg.max_retest_bars)}
                self._pending_short = None

            if self.cfg.allow_shorts and bias == 0 and vol_break_ok and c <= (lo - break_buf):
                self._pending_short = {"level": float(lo), "expires_i": int(i + self.cfg.max_retest_bars)}
                self._pending_long = None

        return None

