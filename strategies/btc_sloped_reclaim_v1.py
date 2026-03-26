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


def _compress_closes(rows: List[list], group_n: int) -> List[float]:
    out: List[float] = []
    if group_n <= 1:
        return [float(r[4]) for r in rows]
    for i in range(0, len(rows), group_n):
        chunk = rows[i:i + group_n]
        if len(chunk) < group_n:
            break
        out.append(float(chunk[-1][4]))
    return out


def _linear_regression(values: List[float]) -> Tuple[float, float]:
    n = len(values)
    if n < 2:
        return float("nan"), float("nan")
    xs = list(range(n))
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / float(n)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den <= 1e-12:
        return 0.0, y_mean
    m = num / den
    b = y_mean - m * x_mean
    return m, b


@dataclass
class BTCSlopedReclaimV1Config:
    regime_tf: str = "240"
    regime_daily_group: int = 6
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_slope_days: int = 5
    regime_min_gap_pct: float = 0.80
    regime_slope_min_pct: float = 0.35
    regime_max_gap_pct: float = 4.00
    regime_max_slope_pct: float = 2.40

    signal_tf: str = "240"
    signal_lookback: int = 72
    atr_period: int = 14
    min_channel_width_pct: float = 4.0
    max_channel_width_pct: float = 16.0
    min_abs_slope_pct: float = 0.08
    max_abs_slope_pct: float = 2.40
    min_range_r2: float = 0.18
    touch_buffer_atr: float = 0.45
    reclaim_atr: float = 0.12
    max_close_above_fit_pct: float = 1.15
    max_signal_atr_pct: float = 3.20

    sl_atr_mult: float = 1.10
    tp1_frac: float = 0.45
    tp2_buffer_pct: float = 0.45
    trail_atr_mult: float = 0.0
    time_stop_bars_5m: int = 864

    cooldown_bars_5m: int = 96
    allow_longs: bool = True
    allow_shorts: bool = False


class BTCSlopedReclaimV1Strategy:
    """BTC-only long reclaim inside a bullish sloped 4h channel."""

    def __init__(self, cfg: Optional[BTCSlopedReclaimV1Config] = None):
        self.cfg = cfg or BTCSlopedReclaimV1Config()

        self.cfg.regime_tf = os.getenv("BTCS1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_daily_group = _env_int("BTCS1_REGIME_DAILY_GROUP", self.cfg.regime_daily_group)
        self.cfg.regime_ema_fast = _env_int("BTCS1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BTCS1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_slope_days = _env_int("BTCS1_REGIME_SLOPE_DAYS", self.cfg.regime_slope_days)
        self.cfg.regime_min_gap_pct = _env_float("BTCS1_REGIME_MIN_GAP_PCT", self.cfg.regime_min_gap_pct)
        self.cfg.regime_slope_min_pct = _env_float("BTCS1_REGIME_SLOPE_MIN_PCT", self.cfg.regime_slope_min_pct)
        self.cfg.regime_max_gap_pct = _env_float("BTCS1_REGIME_MAX_GAP_PCT", self.cfg.regime_max_gap_pct)
        self.cfg.regime_max_slope_pct = _env_float("BTCS1_REGIME_MAX_SLOPE_PCT", self.cfg.regime_max_slope_pct)

        self.cfg.signal_tf = os.getenv("BTCS1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("BTCS1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.atr_period = _env_int("BTCS1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_channel_width_pct = _env_float("BTCS1_MIN_CHANNEL_WIDTH_PCT", self.cfg.min_channel_width_pct)
        self.cfg.max_channel_width_pct = _env_float("BTCS1_MAX_CHANNEL_WIDTH_PCT", self.cfg.max_channel_width_pct)
        self.cfg.min_abs_slope_pct = _env_float("BTCS1_MIN_ABS_SLOPE_PCT", self.cfg.min_abs_slope_pct)
        self.cfg.max_abs_slope_pct = _env_float("BTCS1_MAX_ABS_SLOPE_PCT", self.cfg.max_abs_slope_pct)
        self.cfg.min_range_r2 = _env_float("BTCS1_MIN_RANGE_R2", self.cfg.min_range_r2)
        self.cfg.touch_buffer_atr = _env_float("BTCS1_TOUCH_BUFFER_ATR", self.cfg.touch_buffer_atr)
        self.cfg.reclaim_atr = _env_float("BTCS1_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.max_close_above_fit_pct = _env_float("BTCS1_MAX_CLOSE_ABOVE_FIT_PCT", self.cfg.max_close_above_fit_pct)
        self.cfg.max_signal_atr_pct = _env_float("BTCS1_MAX_SIGNAL_ATR_PCT", self.cfg.max_signal_atr_pct)

        self.cfg.sl_atr_mult = _env_float("BTCS1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_frac = _env_float("BTCS1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_buffer_pct = _env_float("BTCS1_TP2_BUFFER_PCT", self.cfg.tp2_buffer_pct)
        self.cfg.trail_atr_mult = _env_float("BTCS1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTCS1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BTCS1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("BTCS1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BTCS1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BTCS1_SYMBOL_ALLOWLIST", "BTCUSDT")
        self._deny = _env_csv_set("BTCS1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_signal_tf_ts: Optional[int] = None

    def _regime_bias(self, store) -> Optional[int]:
        need_daily = max(self.cfg.regime_ema_slow + self.cfg.regime_slope_days + 5, 70)
        need_4h = int(need_daily * max(1, self.cfg.regime_daily_group)) + 6
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, need_4h) or []
        closes_daily = _compress_closes(rows, max(1, int(self.cfg.regime_daily_group)))
        if len(closes_daily) < self.cfg.regime_ema_slow + self.cfg.regime_slope_days + 2:
            return None

        ef = _ema(closes_daily, self.cfg.regime_ema_fast)
        es = _ema(closes_daily, self.cfg.regime_ema_slow)
        es_prev = _ema(closes_daily[:-max(1, self.cfg.regime_slope_days)], self.cfg.regime_ema_slow)
        cur = closes_daily[-1]
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev) and cur > 0 and es_prev != 0):
            return None

        gap_pct = abs(ef - es) / cur * 100.0
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.regime_slope_min_pct:
            if gap_pct > max(self.cfg.regime_min_gap_pct, self.cfg.regime_max_gap_pct):
                return 1
            if abs(slope_pct) > max(self.cfg.regime_slope_min_pct, self.cfg.regime_max_slope_pct):
                return 1
            return 2
        return 1

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, v)
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

        bias = self._regime_bias(store)
        if bias != 2:
            return None

        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, self.cfg.signal_lookback) or []
        if len(rows) < self.cfg.signal_lookback:
            return None

        t_last = int(float(rows[-1][0]))
        if self._last_signal_tf_ts is None:
            self._last_signal_tf_ts = t_last
            return None
        if t_last == self._last_signal_tf_ts:
            return None
        self._last_signal_tf_ts = t_last

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]
        cur = closes[-1]
        prev = closes[-2]
        atr = _atr_from_rows(rows, self.cfg.atr_period)
        if not (math.isfinite(atr) and atr > 0 and cur > 0):
            return None
        atr_pct = atr / cur * 100.0
        if atr_pct > self.cfg.max_signal_atr_pct:
            return None

        slope, intercept = _linear_regression(closes)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None
        n = len(closes)
        fit = [slope * i + intercept for i in range(n)]
        residual_high = [h_i - f_i for h_i, f_i in zip(highs, fit)]
        residual_low = [l_i - f_i for l_i, f_i in zip(lows, fit)]
        upper_off = max(residual_high)
        lower_off = min(residual_low)
        fit_now = fit[-1]
        if not all(math.isfinite(x) for x in (upper_off, lower_off, fit_now)):
            return None

        upper = fit_now + upper_off
        lower = fit_now + lower_off
        width = upper - lower
        width_pct = width / max(1e-12, cur) * 100.0
        slope_pct = abs(slope) / max(1e-12, abs(fit_now)) * 100.0 * 24.0
        if width <= 0:
            return None
        if width_pct < self.cfg.min_channel_width_pct or width_pct > self.cfg.max_channel_width_pct:
            return None
        if slope_pct < self.cfg.min_abs_slope_pct or slope_pct > self.cfg.max_abs_slope_pct:
            return None
        if slope <= 0:
            return None

        y_mean = sum(closes) / float(n)
        ss_tot = sum((x - y_mean) ** 2 for x in closes)
        ss_res = sum((x - f) ** 2 for x, f in zip(closes, fit))
        r2 = 1.0 - ss_res / max(1e-12, ss_tot)
        if r2 < self.cfg.min_range_r2:
            return None

        low_now = lows[-1]
        high_now = highs[-1]
        body = abs(cur - opens[-1])
        bar_range = max(1e-12, high_now - low_now)
        body_frac = body / bar_range
        if body_frac < 0.18:
            return None

        touched_lower = low_now <= lower + self.cfg.touch_buffer_atr * atr
        reclaimed_lower = cur >= lower + self.cfg.reclaim_atr * atr and cur > prev
        close_above_fit_pct = (cur - fit_now) / max(1e-12, fit_now) * 100.0
        if not (touched_lower and reclaimed_lower):
            return None
        if close_above_fit_pct > self.cfg.max_close_above_fit_pct:
            return None

        sl = min(low_now, lower) - self.cfg.sl_atr_mult * atr
        tp2 = upper - self.cfg.tp2_buffer_pct / 100.0 * width
        if not (sl < cur < tp2):
            return None
        tp1 = cur + (tp2 - cur) * 0.50
        tp1_frac = min(0.9, max(0.1, self.cfg.tp1_frac))

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="btc_sloped_reclaim_v1",
            symbol=store.symbol,
            side="long",
            entry=float(c),
            sl=float(sl),
            tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(5, int(self.cfg.atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="btcs1_sloped_reclaim_long",
        )
        return sig if sig.validate() else None
