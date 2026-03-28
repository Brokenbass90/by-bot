from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _tf_to_seconds(tf: str) -> int:
    raw = str(tf or "").strip().lower()
    if not raw:
        return 3600
    try:
        if raw.endswith("m"):
            return max(60, int(float(raw[:-1])) * 60)
        if raw.endswith("h"):
            return max(3600, int(float(raw[:-1])) * 3600)
        if raw.endswith("d"):
            return max(86400, int(float(raw[:-1])) * 86400)
        return max(60, int(float(raw)) * 60)
    except Exception:
        return 3600


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


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _linear_regression(values: List[float]) -> Tuple[float, float]:
    n = len(values)
    if n < 2:
        return float("nan"), float("nan")
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / float(n)
    num = 0.0
    den = 0.0
    for i, v in enumerate(values):
        dx = i - x_mean
        num += dx * (v - y_mean)
        den += dx * dx
    if den <= 1e-12:
        return 0.0, y_mean
    m = num / den
    b = y_mean - m * x_mean
    return m, b


@dataclass
class SlopedBreakRetestV1Config:
    signal_tf: str = "60"
    signal_lookback: int = 96
    atr_period: int = 14
    vol_period: int = 20

    min_channel_width_pct: float = 4.0
    max_channel_width_pct: float = 24.0
    min_abs_slope_pct: float = 0.05
    max_abs_slope_pct: float = 3.2
    min_r2: float = 0.24

    breakout_atr_mult: float = 0.18
    min_breakout_ext_atr: float = 0.12
    min_breakout_body_frac: float = 0.36
    breakout_vol_mult: float = 1.00

    retest_window_bars: int = 8
    retest_touch_atr: float = 0.22
    reclaim_hold_atr: float = 0.06
    retest_min_body_frac: float = 0.24
    retest_vol_mult: float = 0.80
    invalidation_atr: float = 0.40

    trend_ema_fast: int = 20
    trend_ema_slow: int = 50
    trend_min_gap_pct: float = 0.08
    allow_longs: bool = True
    allow_shorts: bool = True

    sl_atr_mult: float = 1.15
    tp1_rr: float = 1.10
    tp2_rr: float = 2.60
    tp1_frac: float = 0.50
    tp2_frac: float = 0.30
    be_trigger_rr: float = 1.00
    be_lock_rr: float = 0.05
    trail_atr_mult: float = 1.70
    trail_atr_period: int = 14
    time_stop_bars_5m: int = 288
    cooldown_tf_bars: int = 6
    max_signals_per_day: int = 2


class SlopedBreakRetestV1Strategy:
    """Breakout of a sloped regression channel, then retest of the broken band."""

    def __init__(self, cfg: Optional[SlopedBreakRetestV1Config] = None):
        self.cfg = cfg or SlopedBreakRetestV1Config()

        self.cfg.signal_tf = os.getenv("SBR1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("SBR1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.atr_period = _env_int("SBR1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.vol_period = _env_int("SBR1_VOL_PERIOD", self.cfg.vol_period)

        self.cfg.min_channel_width_pct = _env_float("SBR1_MIN_CHANNEL_WIDTH_PCT", self.cfg.min_channel_width_pct)
        self.cfg.max_channel_width_pct = _env_float("SBR1_MAX_CHANNEL_WIDTH_PCT", self.cfg.max_channel_width_pct)
        self.cfg.min_abs_slope_pct = _env_float("SBR1_MIN_ABS_SLOPE_PCT", self.cfg.min_abs_slope_pct)
        self.cfg.max_abs_slope_pct = _env_float("SBR1_MAX_ABS_SLOPE_PCT", self.cfg.max_abs_slope_pct)
        self.cfg.min_r2 = _env_float("SBR1_MIN_R2", self.cfg.min_r2)

        self.cfg.breakout_atr_mult = _env_float("SBR1_BREAKOUT_ATR_MULT", self.cfg.breakout_atr_mult)
        self.cfg.min_breakout_ext_atr = _env_float("SBR1_MIN_BREAKOUT_EXT_ATR", self.cfg.min_breakout_ext_atr)
        self.cfg.min_breakout_body_frac = _env_float("SBR1_MIN_BREAKOUT_BODY_FRAC", self.cfg.min_breakout_body_frac)
        self.cfg.breakout_vol_mult = _env_float("SBR1_BREAKOUT_VOL_MULT", self.cfg.breakout_vol_mult)

        self.cfg.retest_window_bars = _env_int("SBR1_RETEST_WINDOW_BARS", self.cfg.retest_window_bars)
        self.cfg.retest_touch_atr = _env_float("SBR1_RETEST_TOUCH_ATR", self.cfg.retest_touch_atr)
        self.cfg.reclaim_hold_atr = _env_float("SBR1_RECLAIM_HOLD_ATR", self.cfg.reclaim_hold_atr)
        self.cfg.retest_min_body_frac = _env_float("SBR1_RETEST_MIN_BODY_FRAC", self.cfg.retest_min_body_frac)
        self.cfg.retest_vol_mult = _env_float("SBR1_RETEST_VOL_MULT", self.cfg.retest_vol_mult)
        self.cfg.invalidation_atr = _env_float("SBR1_INVALIDATION_ATR", self.cfg.invalidation_atr)

        self.cfg.trend_ema_fast = _env_int("SBR1_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("SBR1_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_min_gap_pct = _env_float("SBR1_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.allow_longs = _env_bool("SBR1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("SBR1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self.cfg.sl_atr_mult = _env_float("SBR1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_rr = _env_float("SBR1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("SBR1_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("SBR1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_frac = _env_float("SBR1_TP2_FRAC", self.cfg.tp2_frac)
        self.cfg.be_trigger_rr = _env_float("SBR1_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("SBR1_BE_LOCK_RR", self.cfg.be_lock_rr)
        self.cfg.trail_atr_mult = _env_float("SBR1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_atr_period = _env_int("SBR1_TRAIL_ATR_PERIOD", self.cfg.trail_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("SBR1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_tf_bars = _env_int("SBR1_COOLDOWN_TF_BARS", self.cfg.cooldown_tf_bars)
        self.cfg.max_signals_per_day = _env_int("SBR1_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._allow = _env_csv_set(
            "SBR1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,AVAXUSDT,LINKUSDT,SUIUSDT,ATOMUSDT,LTCUSDT",
        )
        self._deny = _env_csv_set("SBR1_SYMBOL_DENYLIST")
        self._last_tf_ts: Optional[int] = None
        self._tf_seconds = _tf_to_seconds(self.cfg.signal_tf)
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0
        self._pending_long: Optional[Dict[str, float]] = None
        self._pending_short: Optional[Dict[str, float]] = None

    def _trend_bias(self, closes: List[float]) -> int:
        if len(closes) < self.cfg.trend_ema_slow + 5:
            return 1
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        es_prev = _ema(closes[:-4], self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)):
            return 1
        px = max(1e-12, closes[-1])
        gap = abs(ef - es) / px * 100.0
        if gap < self.cfg.trend_min_gap_pct:
            return 1
        if ef > es and es >= es_prev:
            return 2
        if ef < es and es <= es_prev:
            return 0
        return 1

    def _make_signal(self, symbol: str, side: str, entry: float, level: float, atr_now: float) -> Optional[TradeSignal]:
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

        sig = TradeSignal(
            strategy="sloped_break_retest_v1",
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[self.cfg.tp1_frac, self.cfg.tp2_frac],
            be_trigger_rr=self.cfg.be_trigger_rr,
            be_lock_rr=self.cfg.be_lock_rr,
            trailing_atr_mult=self.cfg.trail_atr_mult,
            trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"sbr1_{side}_channel_break_retest",
        )
        return sig if sig.validate() else None

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v)
        symbol = str(getattr(store, "symbol", "")).upper()
        if self._allow and symbol not in self._allow:
            return None
        if symbol in self._deny:
            return None

        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, self.cfg.signal_lookback) or []
        if len(rows) < self.cfg.signal_lookback:
            return None

        tf_ts = int(float(rows[-1][0]))
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts
            return None
        if tf_ts == self._last_tf_ts:
            return None
        self._last_tf_ts = tf_ts

        if self._cooldown > 0:
            self._cooldown -= 1

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        opens = [float(r[1]) for r in rows]
        closes = [float(r[4]) for r in rows]
        vols = [float(r[5]) if len(r) > 5 and r[5] not in (None, "", "nan") else 0.0 for r in rows]

        atr_now = _atr_from_rows(rows, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None

        cur = closes[-1]
        prev = closes[-2]
        high_now = highs[-1]
        low_now = lows[-1]
        open_now = opens[-1]
        if cur <= 0:
            return None

        hist_closes = closes[:-1]
        hist_highs = highs[:-1]
        hist_lows = lows[:-1]
        if len(hist_closes) < max(20, self.cfg.signal_lookback - 8):
            return None

        slope, intercept = _linear_regression(hist_closes)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None
        n_hist = len(hist_closes)
        fit_hist = [slope * i + intercept for i in range(n_hist)]
        residual_close = [c_i - f_i for c_i, f_i in zip(hist_closes, fit_hist)]
        upper_off = max(residual_close)
        lower_off = min(residual_close)
        prev_upper = fit_hist[-1] + upper_off
        prev_lower = fit_hist[-1] + lower_off
        upper = (slope * n_hist + intercept) + upper_off
        lower = (slope * n_hist + intercept) + lower_off
        width = upper - lower
        if width <= 0:
            return None

        width_pct = width / max(1e-12, cur) * 100.0
        slope_pct = abs(slope) / max(1e-12, abs(fit_hist[-1])) * 100.0 * 24.0
        if width_pct < self.cfg.min_channel_width_pct or width_pct > self.cfg.max_channel_width_pct:
            return None
        if slope_pct < self.cfg.min_abs_slope_pct or slope_pct > self.cfg.max_abs_slope_pct:
            return None

        y_mean = sum(hist_closes) / float(n_hist)
        ss_tot = sum((x - y_mean) ** 2 for x in hist_closes)
        ss_res = sum((x - f) ** 2 for x, f in zip(hist_closes, fit_hist))
        r2 = 1.0 - ss_res / max(1e-12, ss_tot)
        if r2 < self.cfg.min_r2:
            return None

        vol_hist = [x for x in vols[-self.cfg.vol_period - 1:-1] if math.isfinite(x) and x > 0]
        vol_avg = sum(vol_hist) / float(len(vol_hist)) if vol_hist else 0.0
        breakout_vol_ok = vol_avg <= 0 or vols[-1] >= vol_avg * self.cfg.breakout_vol_mult
        retest_vol_ok = vol_avg <= 0 or vols[-1] >= vol_avg * self.cfg.retest_vol_mult

        body_frac = abs(cur - open_now) / max(1e-12, high_now - low_now)
        trend = self._trend_bias(closes)
        if self._pending_long is not None:
            p = self._pending_long
            if tf_ts > int(p["expire_ts"]):
                self._pending_long = None
            else:
                level = float(p["level"])
                touched = low_now <= level + self.cfg.retest_touch_atr * float(p["atr"])
                held = cur >= level + self.cfg.reclaim_hold_atr * float(p["atr"])
                invalid = cur < level - self.cfg.invalidation_atr * float(p["atr"])
                if invalid:
                    self._pending_long = None
                elif (
                    self.cfg.allow_longs
                    and touched
                    and held
                    and body_frac >= self.cfg.retest_min_body_frac
                    and retest_vol_ok
                    and trend != 0
                    and self._cooldown <= 0
                ):
                    self._pending_long = None
                    sig = self._make_signal(symbol, "long", cur, level, float(p["atr"]))
                    if sig is not None:
                        self._cooldown = max(0, int(self.cfg.cooldown_tf_bars))
                        self._day_signals += 1
                        return sig

        if self._pending_short is not None:
            p = self._pending_short
            if tf_ts > int(p["expire_ts"]):
                self._pending_short = None
            else:
                level = float(p["level"])
                touched = high_now >= level - self.cfg.retest_touch_atr * float(p["atr"])
                held = cur <= level - self.cfg.reclaim_hold_atr * float(p["atr"])
                invalid = cur > level + self.cfg.invalidation_atr * float(p["atr"])
                if invalid:
                    self._pending_short = None
                elif (
                    self.cfg.allow_shorts
                    and touched
                    and held
                    and body_frac >= self.cfg.retest_min_body_frac
                    and retest_vol_ok
                    and trend != 2
                    and self._cooldown <= 0
                ):
                    self._pending_short = None
                    sig = self._make_signal(symbol, "short", cur, level, float(p["atr"]))
                    if sig is not None:
                        self._cooldown = max(0, int(self.cfg.cooldown_tf_bars))
                        self._day_signals += 1
                        return sig

        if self._cooldown > 0:
            return None

        broke_up = (
            self.cfg.allow_longs
            and breakout_vol_ok
            and body_frac >= self.cfg.min_breakout_body_frac
            and prev <= prev_upper + self.cfg.breakout_atr_mult * atr_now
            and cur >= upper + self.cfg.breakout_atr_mult * atr_now
            and (cur - upper) >= self.cfg.min_breakout_ext_atr * atr_now
            and trend != 0
        )
        if broke_up:
            self._pending_long = {
                "level": float(upper),
                "atr": float(atr_now),
                "expire_ts": float(
                    tf_ts + max(2, int(self.cfg.retest_window_bars)) * int(self._tf_seconds)
                ),
            }
            self._pending_short = None

        broke_down = (
            self.cfg.allow_shorts
            and breakout_vol_ok
            and body_frac >= self.cfg.min_breakout_body_frac
            and prev >= prev_lower - self.cfg.breakout_atr_mult * atr_now
            and cur <= lower - self.cfg.breakout_atr_mult * atr_now
            and (lower - cur) >= self.cfg.min_breakout_ext_atr * atr_now
            and trend != 2
        )
        if broke_down:
            self._pending_short = {
                "level": float(lower),
                "atr": float(atr_now),
                "expire_ts": float(
                    tf_ts + max(2, int(self.cfg.retest_window_bars)) * int(self._tf_seconds)
                ),
            }
            self._pending_long = None

        return None
