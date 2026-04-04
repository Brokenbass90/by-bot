from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

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
class SlopedResistanceChochV1Config:
    signal_tf: str = "60"
    signal_lookback: int = 96
    atr_period: int = 14
    rsi_period: int = 14

    min_channel_width_pct: float = 4.0
    max_channel_width_pct: float = 24.0
    min_abs_slope_pct: float = 0.05
    max_abs_slope_pct: float = 3.0
    min_r2: float = 0.24

    resistance_lookback_bars: int = 24
    resistance_touch_tolerance_atr: float = 0.35
    min_resistance_touches: int = 2
    resistance_near_upper_atr: float = 0.75

    upper_touch_atr: float = 0.30
    reject_below_atr: float = 0.14
    min_upper_wick_frac: float = 0.30
    min_body_frac: float = 0.18
    short_min_rsi: float = 56.0

    ltf_tf: str = "5"
    ltf_lookback_bars: int = 40
    ltf_ema_period: int = 20
    choch_lookback_bars: int = 10
    choch_break_atr: float = 0.05
    choch_bear_body_frac: float = 0.25

    trend_ema_fast: int = 20
    trend_ema_slow: int = 50
    allow_shorts: bool = True

    sl_atr_mult: float = 0.95
    tp1_rr: float = 1.0
    tp2_frac: float = 0.35
    tp1_frac: float = 0.50
    min_rr_to_channel: float = 1.25
    channel_tp_buffer_atr: float = 0.15
    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.05
    trail_atr_mult: float = 1.8
    trail_atr_period: int = 14
    time_stop_bars_5m: int = 288
    cooldown_tf_bars: int = 6
    max_signals_per_day: int = 2


class SlopedResistanceChochV1Strategy:
    """
    Short-only confluence setup:
    - 1H sloped regression channel
    - repeated horizontal resistance near the upper band
    - rejection candle from that zone
    - 5m bearish structure shift approximation (recent swing-low break)
    """

    NAME = "sloped_resistance_choch_v1"

    def __init__(self, cfg: Optional[SlopedResistanceChochV1Config] = None):
        self.cfg = cfg or SlopedResistanceChochV1Config()

        self.cfg.signal_tf = os.getenv("SRC1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("SRC1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.atr_period = _env_int("SRC1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.rsi_period = _env_int("SRC1_RSI_PERIOD", self.cfg.rsi_period)

        self.cfg.min_channel_width_pct = _env_float("SRC1_MIN_CHANNEL_WIDTH_PCT", self.cfg.min_channel_width_pct)
        self.cfg.max_channel_width_pct = _env_float("SRC1_MAX_CHANNEL_WIDTH_PCT", self.cfg.max_channel_width_pct)
        self.cfg.min_abs_slope_pct = _env_float("SRC1_MIN_ABS_SLOPE_PCT", self.cfg.min_abs_slope_pct)
        self.cfg.max_abs_slope_pct = _env_float("SRC1_MAX_ABS_SLOPE_PCT", self.cfg.max_abs_slope_pct)
        self.cfg.min_r2 = _env_float("SRC1_MIN_R2", self.cfg.min_r2)

        self.cfg.resistance_lookback_bars = _env_int("SRC1_RES_LOOKBACK_BARS", self.cfg.resistance_lookback_bars)
        self.cfg.resistance_touch_tolerance_atr = _env_float("SRC1_RES_TOUCH_TOLERANCE_ATR", self.cfg.resistance_touch_tolerance_atr)
        self.cfg.min_resistance_touches = _env_int("SRC1_MIN_RES_TOUCHES", self.cfg.min_resistance_touches)
        self.cfg.resistance_near_upper_atr = _env_float("SRC1_RES_NEAR_UPPER_ATR", self.cfg.resistance_near_upper_atr)

        self.cfg.upper_touch_atr = _env_float("SRC1_UPPER_TOUCH_ATR", self.cfg.upper_touch_atr)
        self.cfg.reject_below_atr = _env_float("SRC1_REJECT_BELOW_ATR", self.cfg.reject_below_atr)
        self.cfg.min_upper_wick_frac = _env_float("SRC1_MIN_UPPER_WICK_FRAC", self.cfg.min_upper_wick_frac)
        self.cfg.min_body_frac = _env_float("SRC1_MIN_BODY_FRAC", self.cfg.min_body_frac)
        self.cfg.short_min_rsi = _env_float("SRC1_SHORT_MIN_RSI", self.cfg.short_min_rsi)

        self.cfg.ltf_tf = os.getenv("SRC1_LTF_TF", self.cfg.ltf_tf)
        self.cfg.ltf_lookback_bars = _env_int("SRC1_LTF_LOOKBACK_BARS", self.cfg.ltf_lookback_bars)
        self.cfg.ltf_ema_period = _env_int("SRC1_LTF_EMA_PERIOD", self.cfg.ltf_ema_period)
        self.cfg.choch_lookback_bars = _env_int("SRC1_CHOCH_LOOKBACK_BARS", self.cfg.choch_lookback_bars)
        self.cfg.choch_break_atr = _env_float("SRC1_CHOCH_BREAK_ATR", self.cfg.choch_break_atr)
        self.cfg.choch_bear_body_frac = _env_float("SRC1_CHOCH_BEAR_BODY_FRAC", self.cfg.choch_bear_body_frac)

        self.cfg.trend_ema_fast = _env_int("SRC1_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("SRC1_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.allow_shorts = _env_bool("SRC1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self.cfg.sl_atr_mult = _env_float("SRC1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_rr = _env_float("SRC1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_frac = _env_float("SRC1_TP2_FRAC", self.cfg.tp2_frac)
        self.cfg.tp1_frac = _env_float("SRC1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.min_rr_to_channel = _env_float("SRC1_MIN_RR_TO_CHANNEL", self.cfg.min_rr_to_channel)
        self.cfg.channel_tp_buffer_atr = _env_float("SRC1_CHANNEL_TP_BUFFER_ATR", self.cfg.channel_tp_buffer_atr)
        self.cfg.be_trigger_rr = _env_float("SRC1_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("SRC1_BE_LOCK_RR", self.cfg.be_lock_rr)
        self.cfg.trail_atr_mult = _env_float("SRC1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_atr_period = _env_int("SRC1_TRAIL_ATR_PERIOD", self.cfg.trail_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("SRC1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_tf_bars = _env_int("SRC1_COOLDOWN_TF_BARS", self.cfg.cooldown_tf_bars)
        self.cfg.max_signals_per_day = _env_int("SRC1_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._allow = _env_csv_set(
            "SRC1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,AVAXUSDT,LINKUSDT,DOGEUSDT,XRPUSDT,ADAUSDT",
        )
        self._deny = _env_csv_set("SRC1_SYMBOL_DENYLIST")
        self._last_tf_ts: Optional[int] = None
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, closes: List[float]) -> int:
        if len(closes) < self.cfg.trend_ema_slow + 5:
            return 1
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        es_prev = _ema(closes[:-4], self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)):
            return 1
        if ef > es and es >= es_prev:
            return 2
        if ef < es and es <= es_prev:
            return 0
        return 1

    def _ltf_choch_ok(self, store, zone_level: float) -> bool:
        rows = store.fetch_klines(store.symbol, self.cfg.ltf_tf, self.cfg.ltf_lookback_bars) or []
        if len(rows) < max(20, self.cfg.choch_lookback_bars + 5):
            return False
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        opens = [float(r[1]) for r in rows]
        closes = [float(r[4]) for r in rows]
        last_close = closes[-1]
        last_open = opens[-1]
        last_high = highs[-1]
        last_low = lows[-1]
        bar_range = max(1e-12, last_high - last_low)
        body_frac = abs(last_close - last_open) / bar_range
        ltf_atr = _atr_from_rows(rows, max(5, self.cfg.atr_period))
        if not math.isfinite(ltf_atr) or ltf_atr <= 0:
            return False
        ema_ltf = _ema(closes[-max(self.cfg.ltf_ema_period + 3, 10):], self.cfg.ltf_ema_period)
        swing_low = min(lows[-self.cfg.choch_lookback_bars - 1:-1])
        broke_structure = last_close <= swing_low - self.cfg.choch_break_atr * ltf_atr
        below_ema = math.isfinite(ema_ltf) and last_close < ema_ltf
        bear_bar = last_close < last_open and body_frac >= self.cfg.choch_bear_body_frac
        returned_from_zone = max(highs[-4:]) >= zone_level - self.cfg.resistance_touch_tolerance_atr * ltf_atr
        return bool(broke_structure and below_ema and bear_bar and returned_from_zone)

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v)
        symbol = str(getattr(store, "symbol", "")).upper()
        if self._allow and symbol not in self._allow:
            return None
        if symbol in self._deny or not self.cfg.allow_shorts:
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
        cur = closes[-1]
        prev = closes[-2]
        open_now = opens[-1]
        high_now = highs[-1]
        low_now = lows[-1]
        if cur <= 0:
            return None

        atr_now = _atr_from_rows(rows, self.cfg.atr_period)
        rsi_now = _rsi(closes, self.cfg.rsi_period)
        if not (math.isfinite(atr_now) and atr_now > 0 and math.isfinite(rsi_now)):
            return None

        hist_closes = closes[:-1]
        hist_highs = highs[:-1]
        if len(hist_closes) < max(30, self.cfg.signal_lookback - 8):
            return None

        slope, intercept = _linear_regression(hist_closes)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None
        n_hist = len(hist_closes)
        fit_hist = [slope * i + intercept for i in range(n_hist)]
        residual_close = [c_i - f_i for c_i, f_i in zip(hist_closes, fit_hist)]
        upper_off = max(residual_close)
        lower_off = min(residual_close)
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

        recent_highs = hist_highs[-self.cfg.resistance_lookback_bars:]
        zone_level = max(recent_highs)
        touch_tol = self.cfg.resistance_touch_tolerance_atr * atr_now
        res_touches = sum(1 for x in recent_highs if abs(x - zone_level) <= touch_tol)
        zone_near_upper = abs(zone_level - upper) <= self.cfg.resistance_near_upper_atr * atr_now
        if res_touches < self.cfg.min_resistance_touches or not zone_near_upper:
            return None

        trend = self._trend_bias(closes)
        if trend == 2:
            return None

        bar_range = max(1e-12, high_now - low_now)
        body_frac = abs(cur - open_now) / bar_range
        upper_wick = high_now - max(open_now, cur)
        upper_wick_frac = upper_wick / bar_range
        touched_zone = high_now >= zone_level - self.cfg.upper_touch_atr * atr_now
        touched_upper = high_now >= upper - self.cfg.upper_touch_atr * atr_now
        rejected = cur <= min(zone_level, upper) - self.cfg.reject_below_atr * atr_now and cur < prev and cur < open_now
        if not (
            touched_zone
            and touched_upper
            and rejected
            and upper_wick_frac >= self.cfg.min_upper_wick_frac
            and body_frac >= self.cfg.min_body_frac
            and rsi_now >= self.cfg.short_min_rsi
        ):
            return None

        if not self._ltf_choch_ok(store, zone_level):
            return None

        entry = float(c)
        sl = max(zone_level, upper) + self.cfg.sl_atr_mult * atr_now
        risk = sl - entry
        if risk <= 0:
            return None

        tp_channel = lower + self.cfg.channel_tp_buffer_atr * atr_now
        rr_to_channel = (entry - tp_channel) / max(1e-12, risk)
        if tp_channel >= entry or rr_to_channel < self.cfg.min_rr_to_channel:
            return None

        tp1 = entry - self.cfg.tp1_rr * risk
        tp2 = tp_channel
        sig = TradeSignal(
            strategy=self.NAME,
            symbol=symbol,
            side="short",
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
            reason="src1_sloped_resistance_choch_short",
        )
        if not sig.validate():
            return None

        self._cooldown = max(0, int(self.cfg.cooldown_tf_bars))
        self._day_signals += 1
        return sig
