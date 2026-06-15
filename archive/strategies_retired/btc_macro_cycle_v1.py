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


@dataclass
class BTCMacroCycleV1Config:
    regime_tf: str = "240"
    daily_group: int = 6
    weekly_group: int = 42  # 42 x 4h ~= 1 week
    daily_ema_fast: int = 20
    daily_ema_slow: int = 50
    daily_slope_days: int = 5
    daily_min_gap_pct: float = 0.80
    daily_min_slope_pct: float = 0.30
    daily_max_gap_pct: float = 4.20
    daily_max_slope_pct: float = 2.60
    weekly_ema_fast: int = 8
    weekly_ema_slow: int = 21
    weekly_slope_weeks: int = 3
    weekly_min_slope_pct: float = 0.25

    signal_tf: str = "240"
    ema_period: int = 20
    atr_period: int = 14
    breakout_lookback_bars: int = 12
    swing_lookback_bars: int = 10
    touch_tol_pct: float = 0.20
    reclaim_pct: float = 0.10
    max_pullback_pct: float = 1.50
    max_atr_pct_4h: float = 3.20
    breakout_buffer_atr: float = 0.12
    breakout_hold_atr: float = 0.05
    breakout_sl_buffer_atr: float = 0.30
    body_min_frac: float = 0.30
    max_extension_above_level_pct: float = 1.10

    sl_atr_mult: float = 1.20
    swing_sl_buffer_atr: float = 0.15
    tp1_rr: float = 1.00
    tp2_rr: float = 3.20
    tp1_frac: float = 0.45
    trail_atr_mult: float = 0.0
    time_stop_bars_5m: int = 1152  # ~4 days

    cooldown_bars_5m: int = 96
    allow_longs: bool = True
    allow_shorts: bool = False


class BTCMacroCycleV1Strategy:
    """BTC-only long module using weekly/daily cycle regime and two long entry types."""

    def __init__(self, cfg: Optional[BTCMacroCycleV1Config] = None):
        self.cfg = cfg or BTCMacroCycleV1Config()

        self.cfg.regime_tf = os.getenv("BTCM1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.daily_group = _env_int("BTCM1_DAILY_GROUP", self.cfg.daily_group)
        self.cfg.weekly_group = _env_int("BTCM1_WEEKLY_GROUP", self.cfg.weekly_group)
        self.cfg.daily_ema_fast = _env_int("BTCM1_DAILY_EMA_FAST", self.cfg.daily_ema_fast)
        self.cfg.daily_ema_slow = _env_int("BTCM1_DAILY_EMA_SLOW", self.cfg.daily_ema_slow)
        self.cfg.daily_slope_days = _env_int("BTCM1_DAILY_SLOPE_DAYS", self.cfg.daily_slope_days)
        self.cfg.daily_min_gap_pct = _env_float("BTCM1_DAILY_MIN_GAP_PCT", self.cfg.daily_min_gap_pct)
        self.cfg.daily_min_slope_pct = _env_float("BTCM1_DAILY_MIN_SLOPE_PCT", self.cfg.daily_min_slope_pct)
        self.cfg.daily_max_gap_pct = _env_float("BTCM1_DAILY_MAX_GAP_PCT", self.cfg.daily_max_gap_pct)
        self.cfg.daily_max_slope_pct = _env_float("BTCM1_DAILY_MAX_SLOPE_PCT", self.cfg.daily_max_slope_pct)
        self.cfg.weekly_ema_fast = _env_int("BTCM1_WEEKLY_EMA_FAST", self.cfg.weekly_ema_fast)
        self.cfg.weekly_ema_slow = _env_int("BTCM1_WEEKLY_EMA_SLOW", self.cfg.weekly_ema_slow)
        self.cfg.weekly_slope_weeks = _env_int("BTCM1_WEEKLY_SLOPE_WEEKS", self.cfg.weekly_slope_weeks)
        self.cfg.weekly_min_slope_pct = _env_float("BTCM1_WEEKLY_MIN_SLOPE_PCT", self.cfg.weekly_min_slope_pct)

        self.cfg.signal_tf = os.getenv("BTCM1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.ema_period = _env_int("BTCM1_EMA_PERIOD", self.cfg.ema_period)
        self.cfg.atr_period = _env_int("BTCM1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.breakout_lookback_bars = _env_int("BTCM1_BREAKOUT_LOOKBACK_BARS", self.cfg.breakout_lookback_bars)
        self.cfg.swing_lookback_bars = _env_int("BTCM1_SWING_LOOKBACK_BARS", self.cfg.swing_lookback_bars)
        self.cfg.touch_tol_pct = _env_float("BTCM1_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.reclaim_pct = _env_float("BTCM1_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.max_pullback_pct = _env_float("BTCM1_MAX_PULLBACK_PCT", self.cfg.max_pullback_pct)
        self.cfg.max_atr_pct_4h = _env_float("BTCM1_MAX_ATR_PCT_4H", self.cfg.max_atr_pct_4h)
        self.cfg.breakout_buffer_atr = _env_float("BTCM1_BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)
        self.cfg.breakout_hold_atr = _env_float("BTCM1_BREAKOUT_HOLD_ATR", self.cfg.breakout_hold_atr)
        self.cfg.breakout_sl_buffer_atr = _env_float("BTCM1_BREAKOUT_SL_BUFFER_ATR", self.cfg.breakout_sl_buffer_atr)
        self.cfg.body_min_frac = _env_float("BTCM1_BODY_MIN_FRAC", self.cfg.body_min_frac)
        self.cfg.max_extension_above_level_pct = _env_float("BTCM1_MAX_EXTENSION_ABOVE_LEVEL_PCT", self.cfg.max_extension_above_level_pct)

        self.cfg.sl_atr_mult = _env_float("BTCM1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.swing_sl_buffer_atr = _env_float("BTCM1_SWING_SL_BUFFER_ATR", self.cfg.swing_sl_buffer_atr)
        self.cfg.tp1_rr = _env_float("BTCM1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("BTCM1_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("BTCM1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("BTCM1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTCM1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)

        self.cfg.cooldown_bars_5m = _env_int("BTCM1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("BTCM1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BTCM1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BTCM1_SYMBOL_ALLOWLIST", "BTCUSDT")
        self._deny = _env_csv_set("BTCM1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_signal_tf_ts: Optional[int] = None

    def _regime_ok(self, store) -> bool:
        need_daily = max(self.cfg.daily_ema_slow + self.cfg.daily_slope_days + 5, 70)
        need_weekly = max(self.cfg.weekly_ema_slow + self.cfg.weekly_slope_weeks + 5, 40)
        need_4h = max(
            int(need_daily * max(1, self.cfg.daily_group)) + 6,
            int(need_weekly * max(1, self.cfg.weekly_group)) + 6,
        )
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, need_4h) or []
        if len(rows) < need_4h - 4:
            return False

        closes_daily = _compress_closes(rows, max(1, self.cfg.daily_group))
        closes_weekly = _compress_closes(rows, max(1, self.cfg.weekly_group))
        if len(closes_daily) < self.cfg.daily_ema_slow + self.cfg.daily_slope_days + 2:
            return False
        if len(closes_weekly) < self.cfg.weekly_ema_slow + self.cfg.weekly_slope_weeks + 2:
            return False

        d_fast = _ema(closes_daily, self.cfg.daily_ema_fast)
        d_slow = _ema(closes_daily, self.cfg.daily_ema_slow)
        d_prev = _ema(closes_daily[:-max(1, self.cfg.daily_slope_days)], self.cfg.daily_ema_slow)
        d_cur = closes_daily[-1]
        if not (math.isfinite(d_fast) and math.isfinite(d_slow) and math.isfinite(d_prev) and d_cur > 0 and d_prev != 0):
            return False
        d_gap = abs(d_fast - d_slow) / d_cur * 100.0
        d_slope = (d_slow - d_prev) / abs(d_prev) * 100.0
        daily_ok = (
            d_fast > d_slow
            and self.cfg.daily_min_gap_pct <= d_gap <= self.cfg.daily_max_gap_pct
            and self.cfg.daily_min_slope_pct <= d_slope <= self.cfg.daily_max_slope_pct
        )
        if not daily_ok:
            return False

        w_fast = _ema(closes_weekly, self.cfg.weekly_ema_fast)
        w_slow = _ema(closes_weekly, self.cfg.weekly_ema_slow)
        w_prev = _ema(closes_weekly[:-max(1, self.cfg.weekly_slope_weeks)], self.cfg.weekly_ema_slow)
        w_cur = closes_weekly[-1]
        if not (math.isfinite(w_fast) and math.isfinite(w_slow) and math.isfinite(w_prev) and w_cur > 0 and w_prev != 0):
            return False
        w_slope = (w_slow - w_prev) / abs(w_prev) * 100.0
        return (w_fast > w_slow) and (w_cur >= w_slow) and (w_slope >= self.cfg.weekly_min_slope_pct)

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, v, ts_ms)
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny or not self.cfg.allow_longs:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if not self._regime_ok(store):
            return None

        need = max(self.cfg.ema_period + self.cfg.breakout_lookback_bars + self.cfg.swing_lookback_bars + 8, 96)
        rows_4h = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        if len(rows_4h) < self.cfg.ema_period + self.cfg.breakout_lookback_bars + 4:
            return None

        t_last = int(float(rows_4h[-1][0]))
        if self._last_signal_tf_ts is None:
            self._last_signal_tf_ts = t_last
            return None
        if t_last == self._last_signal_tf_ts:
            return None
        self._last_signal_tf_ts = t_last

        highs = [float(r[2]) for r in rows_4h]
        lows = [float(r[3]) for r in rows_4h]
        closes = [float(r[4]) for r in rows_4h]
        opens = [float(r[1]) for r in rows_4h]

        ema4h = _ema(closes, self.cfg.ema_period)
        atr4h = _atr_from_rows(rows_4h, self.cfg.atr_period)
        if not (math.isfinite(ema4h) and math.isfinite(atr4h) and atr4h > 0):
            return None

        cur_c = closes[-1]
        prev_c = closes[-2]
        prev_o = opens[-2]
        prev_h = highs[-2]
        prev_l = lows[-2]
        atr_pct = atr4h / max(1e-12, abs(cur_c)) * 100.0
        if atr_pct > self.cfg.max_atr_pct_4h:
            return None

        look = max(4, min(len(rows_4h) - 1, int(self.cfg.swing_lookback_bars)))
        swing_low = min(lows[-look:])
        breakout_level = max(highs[-self.cfg.breakout_lookback_bars - 2: -2])
        pullback_pct = max(0.0, (ema4h - swing_low) / max(1e-12, ema4h) * 100.0)

        touched = swing_low <= ema4h * (1.0 + self.cfg.touch_tol_pct / 100.0)
        reclaimed = (cur_c >= ema4h * (1.0 + self.cfg.reclaim_pct / 100.0)) and (prev_c <= ema4h * 1.003)
        pullback_mode = touched and reclaimed and pullback_pct <= self.cfg.max_pullback_pct

        body_frac = abs(prev_c - prev_o) / max(1e-12, prev_h - prev_l)
        breakout_close_ok = prev_c > breakout_level + self.cfg.breakout_buffer_atr * atr4h
        breakout_body_ok = body_frac >= self.cfg.body_min_frac
        breakout_hold_ok = lows[-1] >= breakout_level - self.cfg.breakout_sl_buffer_atr * atr4h and cur_c >= breakout_level + self.cfg.breakout_hold_atr * atr4h
        level_extension_pct = (cur_c - breakout_level) / max(1e-12, breakout_level) * 100.0
        continuation_mode = breakout_close_ok and breakout_body_ok and breakout_hold_ok and level_extension_pct <= self.cfg.max_extension_above_level_pct

        if not (pullback_mode or continuation_mode):
            return None

        if continuation_mode and not pullback_mode:
            sl = breakout_level - self.cfg.breakout_sl_buffer_atr * atr4h
            reason = "btcm1_long_macro_continuation"
        else:
            swing_sl = swing_low - self.cfg.swing_sl_buffer_atr * atr4h
            atr_sl = float(c) - self.cfg.sl_atr_mult * atr4h
            sl = min(swing_sl, atr_sl)
            reason = "btcm1_long_macro_pullback"

        if sl >= float(c):
            return None

        risk = float(c) - sl
        tp1 = float(c) + self.cfg.tp1_rr * risk
        tp2 = float(c) + self.cfg.tp2_rr * risk
        tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="btc_macro_cycle_v1",
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
            reason=reason,
        )
        return sig if sig.validate() else None
