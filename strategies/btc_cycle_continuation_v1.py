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
class BTCCycleContinuationV1Config:
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
    atr_period: int = 14
    ema_period: int = 20
    breakout_lookback_bars: int = 12
    breakout_buffer_atr: float = 0.12
    max_atr_pct_4h: float = 3.20
    max_extension_above_ema_pct: float = 1.60
    max_extension_above_level_pct: float = 1.30
    hold_above_level_atr: float = 0.05
    body_min_frac: float = 0.35
    min_room_pct: float = 2.00
    target_lookback_bars: int = 60
    target_buffer_pct: float = 0.18

    sl_atr_mult: float = 1.15
    level_sl_buffer_atr: float = 0.18
    tp1_frac: float = 0.45
    trail_atr_mult: float = 0.0
    time_stop_bars_5m: int = 864

    cooldown_bars_5m: int = 96
    allow_longs: bool = True
    allow_shorts: bool = False


class BTCCycleContinuationV1Strategy:
    """BTC-only moderate-regime continuation after fresh 4h breakout hold."""

    def __init__(self, cfg: Optional[BTCCycleContinuationV1Config] = None):
        self.cfg = cfg or BTCCycleContinuationV1Config()

        self.cfg.regime_tf = os.getenv("BTCC2_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_daily_group = _env_int("BTCC2_REGIME_DAILY_GROUP", self.cfg.regime_daily_group)
        self.cfg.regime_ema_fast = _env_int("BTCC2_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BTCC2_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_slope_days = _env_int("BTCC2_REGIME_SLOPE_DAYS", self.cfg.regime_slope_days)
        self.cfg.regime_min_gap_pct = _env_float("BTCC2_REGIME_MIN_GAP_PCT", self.cfg.regime_min_gap_pct)
        self.cfg.regime_slope_min_pct = _env_float("BTCC2_REGIME_SLOPE_MIN_PCT", self.cfg.regime_slope_min_pct)
        self.cfg.regime_max_gap_pct = _env_float("BTCC2_REGIME_MAX_GAP_PCT", self.cfg.regime_max_gap_pct)
        self.cfg.regime_max_slope_pct = _env_float("BTCC2_REGIME_MAX_SLOPE_PCT", self.cfg.regime_max_slope_pct)

        self.cfg.signal_tf = os.getenv("BTCC2_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.atr_period = _env_int("BTCC2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.ema_period = _env_int("BTCC2_EMA_PERIOD", self.cfg.ema_period)
        self.cfg.breakout_lookback_bars = _env_int("BTCC2_BREAKOUT_LOOKBACK_BARS", self.cfg.breakout_lookback_bars)
        self.cfg.breakout_buffer_atr = _env_float("BTCC2_BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)
        self.cfg.max_atr_pct_4h = _env_float("BTCC2_MAX_ATR_PCT_4H", self.cfg.max_atr_pct_4h)
        self.cfg.max_extension_above_ema_pct = _env_float("BTCC2_MAX_EXTENSION_ABOVE_EMA_PCT", self.cfg.max_extension_above_ema_pct)
        self.cfg.max_extension_above_level_pct = _env_float("BTCC2_MAX_EXTENSION_ABOVE_LEVEL_PCT", self.cfg.max_extension_above_level_pct)
        self.cfg.hold_above_level_atr = _env_float("BTCC2_HOLD_ABOVE_LEVEL_ATR", self.cfg.hold_above_level_atr)
        self.cfg.body_min_frac = _env_float("BTCC2_BODY_MIN_FRAC", self.cfg.body_min_frac)
        self.cfg.min_room_pct = _env_float("BTCC2_MIN_ROOM_PCT", self.cfg.min_room_pct)
        self.cfg.target_lookback_bars = _env_int("BTCC2_TARGET_LOOKBACK_BARS", self.cfg.target_lookback_bars)
        self.cfg.target_buffer_pct = _env_float("BTCC2_TARGET_BUFFER_PCT", self.cfg.target_buffer_pct)

        self.cfg.sl_atr_mult = _env_float("BTCC2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.level_sl_buffer_atr = _env_float("BTCC2_LEVEL_SL_BUFFER_ATR", self.cfg.level_sl_buffer_atr)
        self.cfg.tp1_frac = _env_float("BTCC2_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("BTCC2_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTCC2_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)

        self.cfg.cooldown_bars_5m = _env_int("BTCC2_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("BTCC2_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BTCC2_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BTCC2_SYMBOL_ALLOWLIST", "BTCUSDT")
        self._deny = _env_csv_set("BTCC2_SYMBOL_DENYLIST")
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
        if gap_pct < self.cfg.regime_min_gap_pct:
            return 1
        if gap_pct > max(self.cfg.regime_min_gap_pct, self.cfg.regime_max_gap_pct):
            return 1
        if ef > es and slope_pct >= self.cfg.regime_slope_min_pct:
            if abs(slope_pct) > max(self.cfg.regime_slope_min_pct, self.cfg.regime_max_slope_pct):
                return 1
            return 2
        if ef < es and slope_pct <= -self.cfg.regime_slope_min_pct:
            if abs(slope_pct) > max(self.cfg.regime_slope_min_pct, self.cfg.regime_max_slope_pct):
                return 1
            return 0
        return 1

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

        bias = self._regime_bias(store)
        if bias != 2:
            return None

        need = max(self.cfg.ema_period + self.cfg.target_lookback_bars + self.cfg.breakout_lookback_bars + 8, 96)
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

        level = max(highs[-self.cfg.breakout_lookback_bars - 2: -2])
        body = abs(prev_c - prev_o)
        body_frac = body / max(1e-12, prev_h - prev_l)
        breakout_ok = prev_c > level + self.cfg.breakout_buffer_atr * atr4h and body_frac >= self.cfg.body_min_frac
        hold_ok = cur_c >= level + self.cfg.hold_above_level_atr * atr4h and lows[-1] >= level - 0.10 * atr4h
        ext_ema_pct = (cur_c - ema4h) / max(1e-12, ema4h) * 100.0
        ext_level_pct = (cur_c - level) / max(1e-12, level) * 100.0
        if not breakout_ok or not hold_ok:
            return None
        if ext_ema_pct > self.cfg.max_extension_above_ema_pct:
            return None
        if ext_level_pct > self.cfg.max_extension_above_level_pct:
            return None

        future_highs = [x for x in highs[:-1][-self.cfg.target_lookback_bars:] if x > cur_c]
        if not future_highs:
            return None
        resistance = min(future_highs)
        room_pct = (resistance - cur_c) / max(1e-12, cur_c) * 100.0
        if room_pct < self.cfg.min_room_pct:
            return None

        sl = min(
            level - self.cfg.level_sl_buffer_atr * atr4h,
            cur_c - self.cfg.sl_atr_mult * atr4h,
        )
        if sl >= cur_c:
            return None

        tp2 = resistance * (1.0 - self.cfg.target_buffer_pct / 100.0)
        if tp2 <= cur_c:
            return None
        tp1 = cur_c + (tp2 - cur_c) * 0.40
        if tp1 <= cur_c:
            return None

        tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="btc_cycle_continuation_v1",
            symbol=store.symbol,
            side="long",
            entry=float(cur_c),
            sl=float(sl),
            tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(10, int(self.cfg.atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"btcc2_long_cycle_continuation_lvl={level:.2f}",
        )
        return sig if sig.validate() else None
