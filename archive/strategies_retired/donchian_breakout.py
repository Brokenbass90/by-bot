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
    if len(closes) < period + 1:
        return float("nan")
    trs = []
    for i in range(-period, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / max(1, len(trs))


def _sma(values: List[float], n: int) -> float:
    if n <= 0 or len(values) < n:
        return float("nan")
    return sum(values[-n:]) / float(n)


def _tf_minutes(tf: str) -> int:
    try:
        m = int(str(tf).strip())
        return m if m > 0 else 60
    except Exception:
        return 60


@dataclass
class DonchianBreakoutConfig:
    tf: str = "240"
    entry_len: int = 55
    ema_fast: int = 20
    ema_slow: int = 100
    atr_period: int = 20

    atr_min_pct: float = 0.20
    atr_max_pct: float = 4.00
    vol_period: int = 20
    vol_mult: float = 1.10
    max_ema_dist_pct: float = 3.00
    ema_slope_min_pct: float = 0.00

    sl_atr_mult: float = 2.8
    rr1: float = 1.6
    rr2: float = 3.0
    partial_fracs: str = "0.5,0.5"

    trail_atr_mult: float = 1.8
    trail_atr_period: int = 20
    time_stop_bars_5m: int = 576  # ~2 days

    cooldown_htf_bars: int = 3
    max_signals_per_day: int = 1
    allow_longs: bool = True
    allow_shorts: bool = True


class DonchianBreakoutStrategy:
    """HTF Donchian breakout v2.

    Improvements vs v1:
    - signal only once per *new* HTF closed candle;
    - volume + ATR%% filters;
    - late-entry guard (distance from EMA);
    - partial TP + ATR trailing + time stop.
    """

    def __init__(self, cfg: Optional[DonchianBreakoutConfig] = None):
        self.cfg = cfg or DonchianBreakoutConfig()

        self.cfg.tf = os.getenv("DB_TF", self.cfg.tf)
        self.cfg.entry_len = _env_int("DB_ENTRY_LEN", self.cfg.entry_len)
        self.cfg.ema_fast = _env_int("DB_EMA_FAST", self.cfg.ema_fast)
        self.cfg.ema_slow = _env_int("DB_EMA_SLOW", self.cfg.ema_slow)
        self.cfg.atr_period = _env_int("DB_ATR_PERIOD", self.cfg.atr_period)

        self.cfg.atr_min_pct = _env_float("DB_ATR_MIN_PCT", self.cfg.atr_min_pct)
        self.cfg.atr_max_pct = _env_float("DB_ATR_MAX_PCT", self.cfg.atr_max_pct)
        self.cfg.vol_period = _env_int("DB_VOL_PERIOD", self.cfg.vol_period)
        self.cfg.vol_mult = _env_float("DB_VOL_MULT", self.cfg.vol_mult)
        self.cfg.max_ema_dist_pct = _env_float("DB_MAX_EMA_DIST_PCT", self.cfg.max_ema_dist_pct)
        self.cfg.ema_slope_min_pct = _env_float("DB_EMA_SLOPE_MIN_PCT", self.cfg.ema_slope_min_pct)

        self.cfg.sl_atr_mult = _env_float("DB_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr1 = _env_float("DB_RR1", self.cfg.rr1)
        self.cfg.rr2 = _env_float("DB_RR2", self.cfg.rr2)
        self.cfg.partial_fracs = os.getenv("DB_PARTIAL_FRACS", self.cfg.partial_fracs)

        self.cfg.trail_atr_mult = _env_float("DB_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_atr_period = _env_int("DB_TRAIL_ATR_PERIOD", self.cfg.trail_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("DB_TIME_STOP_BARS", self.cfg.time_stop_bars_5m)

        self.cfg.cooldown_htf_bars = _env_int("DB_COOLDOWN_HTF_BARS", self.cfg.cooldown_htf_bars)
        self.cfg.max_signals_per_day = _env_int("DB_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("DB_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("DB_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._cooldown_5m = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0
        self._last_htf_ts: Optional[int] = None

    @staticmethod
    def _parse_fracs(s: str) -> List[float]:
        out: List[float] = []
        for p in str(s or "").replace(";", ",").split(","):
            p = p.strip()
            if not p:
                continue
            try:
                out.append(float(p))
            except Exception:
                pass
        if not out:
            return [0.5, 0.5]
        sm = sum(x for x in out if x > 0)
        if sm <= 0:
            return [0.5, 0.5]
        return [x / sm for x in out]

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, v)

        if self._cooldown_5m > 0:
            self._cooldown_5m -= 1
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        need = max(self.cfg.entry_len + 3, self.cfg.ema_slow + 3, self.cfg.atr_period + 3, self.cfg.vol_period + 3)
        rows = store.fetch_klines(store.symbol, self.cfg.tf, need)
        if not rows or len(rows) < need:
            return None

        tss = [int(float(r[0])) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        vols = [float(r[5]) if len(r) > 5 else 0.0 for r in rows]

        # Signal only once per fresh HTF close.
        last_htf_ts = tss[-1]
        if self._last_htf_ts is None:
            self._last_htf_ts = last_htf_ts
            return None
        if last_htf_ts == self._last_htf_ts:
            return None
        self._last_htf_ts = last_htf_ts

        upper = max(highs[-(self.cfg.entry_len + 1):-1])
        lower = min(lows[-(self.cfg.entry_len + 1):-1])
        if not (math.isfinite(upper) and math.isfinite(lower) and upper > lower > 0):
            return None

        atr_now = _atr(highs, lows, closes, self.cfg.atr_period)
        if not (math.isfinite(atr_now) and atr_now > 0):
            return None
        last_close = closes[-1]
        atr_pct = atr_now / max(1e-12, last_close) * 100.0
        if atr_pct < self.cfg.atr_min_pct or atr_pct > self.cfg.atr_max_pct:
            return None

        vol_avg = _sma(vols[:-1], self.cfg.vol_period)
        if not math.isfinite(vol_avg) or vol_avg <= 0:
            return None
        if vols[-1] < vol_avg * self.cfg.vol_mult:
            return None

        series = closes[-(self.cfg.ema_slow + 3):]
        ef_now = _ema(series, self.cfg.ema_fast)
        es_now = _ema(series, self.cfg.ema_slow)
        ef_prev = _ema(series[:-1], self.cfg.ema_fast)
        es_prev = _ema(series[:-1], self.cfg.ema_slow)
        if not all(math.isfinite(x) for x in [ef_now, es_now, ef_prev, es_prev]):
            return None

        ef_slope_pct = ((ef_now / max(1e-12, ef_prev)) - 1.0) * 100.0
        es_slope_pct = ((es_now / max(1e-12, es_prev)) - 1.0) * 100.0

        # Use HTF close as entry proxy (avoids laggy 5m late entry).
        entry = float(last_close)
        ema_dist_pct = abs(entry - ef_now) / max(1e-12, entry) * 100.0
        if ema_dist_pct > self.cfg.max_ema_dist_pct:
            return None

        fracs = self._parse_fracs(self.cfg.partial_fracs)
        tfm = _tf_minutes(self.cfg.tf)
        cooldown_5m = max(1, int(round(self.cfg.cooldown_htf_bars * tfm / 5.0)))

        if self.cfg.allow_longs and entry > upper and ef_now > es_now and ef_slope_pct >= self.cfg.ema_slope_min_pct and es_slope_pct >= 0:
            sl = entry - self.cfg.sl_atr_mult * atr_now
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = entry + self.cfg.rr1 * risk
            tp2 = entry + self.cfg.rr2 * risk
            sig = TradeSignal(
                strategy="donchian_breakout",
                symbol=store.symbol,
                side="long",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=fracs[:2] if len(fracs) >= 2 else [0.5, 0.5],
                trailing_atr_mult=self.cfg.trail_atr_mult,
                trailing_atr_period=self.cfg.trail_atr_period,
                time_stop_bars=self.cfg.time_stop_bars_5m,
                reason="dbv2_long_breakout",
            )
            if sig.validate():
                self._cooldown_5m = cooldown_5m
                self._day_signals += 1
                return sig

        if self.cfg.allow_shorts and entry < lower and ef_now < es_now and (-ef_slope_pct) >= self.cfg.ema_slope_min_pct and es_slope_pct <= 0:
            sl = entry + self.cfg.sl_atr_mult * atr_now
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = entry - self.cfg.rr1 * risk
            tp2 = entry - self.cfg.rr2 * risk
            sig = TradeSignal(
                strategy="donchian_breakout",
                symbol=store.symbol,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=fracs[:2] if len(fracs) >= 2 else [0.5, 0.5],
                trailing_atr_mult=self.cfg.trail_atr_mult,
                trailing_atr_period=self.cfg.trail_atr_period,
                time_stop_bars=self.cfg.time_stop_bars_5m,
                reason="dbv2_short_breakout",
            )
            if sig.validate():
                self._cooldown_5m = cooldown_5m
                self._day_signals += 1
                return sig

        return None
