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


def _compress_4h_to_daily(rows: List[list], group_n: int) -> List[dict]:
    out: List[dict] = []
    g = max(1, int(group_n))
    for i in range(0, len(rows), g):
        chunk = rows[i:i + g]
        if len(chunk) < g:
            break
        out.append(
            {
                "ts": int(float(chunk[0][0])),
                "o": float(chunk[0][1]),
                "h": max(float(r[2]) for r in chunk),
                "l": min(float(r[3]) for r in chunk),
                "c": float(chunk[-1][4]),
            }
        )
    return out


def _find_pivot_low_idx(daily: List[dict], left: int, right: int, max_age: int, cur_close: float) -> Optional[int]:
    start = max(left, len(daily) - max_age - right - 1)
    end = len(daily) - right
    for i in range(end - 1, start - 1, -1):
        low_i = daily[i]["l"]
        if low_i >= cur_close:
            continue
        if all(low_i < daily[j]["l"] for j in range(i - left, i)) and all(low_i <= daily[j]["l"] for j in range(i + 1, i + right + 1)):
            return i
    return None


def _find_resistance_from_pivots(daily: List[dict], left: int, right: int, start_idx: int, cur_close: float, max_age: int) -> Optional[float]:
    start = max(left, len(daily) - max_age - right - 1, start_idx + 1)
    end = len(daily) - right
    candidates: List[float] = []
    for i in range(start, end):
        hi_i = daily[i]["h"]
        if hi_i <= cur_close:
            continue
        if all(hi_i > daily[j]["h"] for j in range(i - left, i)) and all(hi_i >= daily[j]["h"] for j in range(i + 1, i + right + 1)):
            candidates.append(hi_i)
    if candidates:
        return min(candidates)
    fallback = [x["h"] for x in daily[max(0, len(daily) - max_age):] if x["h"] > cur_close]
    return min(fallback) if fallback else None


@dataclass
class BTCSwingZoneReclaimV1Config:
    regime_tf: str = "240"
    daily_group: int = 6
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_slope_days: int = 5
    regime_min_gap_pct: float = 0.80
    regime_slope_min_pct: float = 0.30

    signal_tf: str = "240"
    atr_period: int = 14
    pivot_left: int = 2
    pivot_right: int = 2
    support_max_age_days: int = 25
    resistance_max_age_days: int = 50
    support_zone_atr: float = 0.30
    reclaim_pct: float = 0.12
    min_room_to_resistance_pct: float = 1.50
    max_signal_atr_pct: float = 3.00

    sl_atr_mult: float = 1.20
    support_sl_buffer_atr: float = 0.15
    tp1_frac: float = 0.35
    target_buffer_pct: float = 0.15
    trail_atr_mult: float = 0.0
    time_stop_bars_5m: int = 1152

    cooldown_bars_5m: int = 96
    allow_longs: bool = True
    allow_shorts: bool = False


class BTCSwingZoneReclaimV1Strategy:
    """BTC long-only support-zone reclaim with resistance-zone target."""

    def __init__(self, cfg: Optional[BTCSwingZoneReclaimV1Config] = None):
        self.cfg = cfg or BTCSwingZoneReclaimV1Config()

        self.cfg.regime_tf = os.getenv("BTCS1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.daily_group = _env_int("BTCS1_DAILY_GROUP", self.cfg.daily_group)
        self.cfg.regime_ema_fast = _env_int("BTCS1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BTCS1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_slope_days = _env_int("BTCS1_REGIME_SLOPE_DAYS", self.cfg.regime_slope_days)
        self.cfg.regime_min_gap_pct = _env_float("BTCS1_REGIME_MIN_GAP_PCT", self.cfg.regime_min_gap_pct)
        self.cfg.regime_slope_min_pct = _env_float("BTCS1_REGIME_SLOPE_MIN_PCT", self.cfg.regime_slope_min_pct)

        self.cfg.signal_tf = os.getenv("BTCS1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.atr_period = _env_int("BTCS1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.pivot_left = _env_int("BTCS1_PIVOT_LEFT", self.cfg.pivot_left)
        self.cfg.pivot_right = _env_int("BTCS1_PIVOT_RIGHT", self.cfg.pivot_right)
        self.cfg.support_max_age_days = _env_int("BTCS1_SUPPORT_MAX_AGE_DAYS", self.cfg.support_max_age_days)
        self.cfg.resistance_max_age_days = _env_int("BTCS1_RESISTANCE_MAX_AGE_DAYS", self.cfg.resistance_max_age_days)
        self.cfg.support_zone_atr = _env_float("BTCS1_SUPPORT_ZONE_ATR", self.cfg.support_zone_atr)
        self.cfg.reclaim_pct = _env_float("BTCS1_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.min_room_to_resistance_pct = _env_float("BTCS1_MIN_ROOM_TO_RESISTANCE_PCT", self.cfg.min_room_to_resistance_pct)
        self.cfg.max_signal_atr_pct = _env_float("BTCS1_MAX_SIGNAL_ATR_PCT", self.cfg.max_signal_atr_pct)

        self.cfg.sl_atr_mult = _env_float("BTCS1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.support_sl_buffer_atr = _env_float("BTCS1_SUPPORT_SL_BUFFER_ATR", self.cfg.support_sl_buffer_atr)
        self.cfg.tp1_frac = _env_float("BTCS1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.target_buffer_pct = _env_float("BTCS1_TARGET_BUFFER_PCT", self.cfg.target_buffer_pct)
        self.cfg.trail_atr_mult = _env_float("BTCS1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTCS1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BTCS1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("BTCS1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BTCS1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BTCS1_SYMBOL_ALLOWLIST", "BTCUSDT")
        self._deny = _env_csv_set("BTCS1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_signal_tf_ts: Optional[int] = None

    def _daily_context(self, store) -> Optional[dict]:
        need_days = max(self.cfg.regime_ema_slow + self.cfg.regime_slope_days + self.cfg.resistance_max_age_days + 5, 120)
        need_4h = need_days * max(1, self.cfg.daily_group) + 6
        rows_4h = store.fetch_klines(store.symbol, self.cfg.regime_tf, need_4h) or []
        daily = _compress_4h_to_daily(rows_4h, self.cfg.daily_group)
        if len(daily) < self.cfg.regime_ema_slow + self.cfg.regime_slope_days + self.cfg.pivot_right + 5:
            return None

        closes = [x["c"] for x in daily]
        ef = _ema(closes, self.cfg.regime_ema_fast)
        es = _ema(closes, self.cfg.regime_ema_slow)
        es_prev = _ema(closes[:-max(1, self.cfg.regime_slope_days)], self.cfg.regime_ema_slow)
        cur_close = closes[-1]
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev) and cur_close > 0 and es_prev != 0):
            return None

        gap_pct = abs(ef - es) / cur_close * 100.0
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        bullish = ef > es and slope_pct >= self.cfg.regime_slope_min_pct and gap_pct >= self.cfg.regime_min_gap_pct
        if not bullish:
            return {"bias": 1}

        support_idx = _find_pivot_low_idx(daily, self.cfg.pivot_left, self.cfg.pivot_right, self.cfg.support_max_age_days, cur_close)
        if support_idx is None:
            return {"bias": 1}

        resistance = _find_resistance_from_pivots(
            daily,
            self.cfg.pivot_left,
            self.cfg.pivot_right,
            support_idx,
            cur_close,
            self.cfg.resistance_max_age_days,
        )
        if resistance is None:
            return {"bias": 1}

        return {
            "bias": 2,
            "support": float(daily[support_idx]["l"]),
            "resistance": float(resistance),
        }

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, v)
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny or not self.cfg.allow_longs:
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ctx = self._daily_context(store)
        if not ctx or ctx.get("bias") != 2:
            return None

        rows_sig = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.atr_period + 5, 60)) or []
        if len(rows_sig) < self.cfg.atr_period + 3:
            return None

        t_last = int(float(rows_sig[-1][0]))
        if self._last_signal_tf_ts is None:
            self._last_signal_tf_ts = t_last
            return None
        if t_last == self._last_signal_tf_ts:
            return None
        self._last_signal_tf_ts = t_last

        atr_sig = _atr_from_rows(rows_sig, self.cfg.atr_period)
        if not (math.isfinite(atr_sig) and atr_sig > 0):
            return None
        atr_pct = atr_sig / max(1e-12, abs(c)) * 100.0
        if atr_pct > self.cfg.max_signal_atr_pct:
            return None

        support = float(ctx["support"])
        resistance = float(ctx["resistance"])
        room_pct = (resistance - float(c)) / max(1e-12, float(c)) * 100.0
        if room_pct < self.cfg.min_room_to_resistance_pct:
            return None

        zone_high = support + self.cfg.support_zone_atr * atr_sig
        touched = float(rows_sig[-1][3]) <= zone_high
        reclaimed = float(rows_sig[-1][4]) >= zone_high * (1.0 + self.cfg.reclaim_pct / 100.0)
        if not (touched and reclaimed):
            return None

        sl = min(
            support - self.cfg.support_sl_buffer_atr * atr_sig,
            float(c) - self.cfg.sl_atr_mult * atr_sig,
        )
        if sl >= float(c):
            return None

        tp2 = resistance * (1.0 - self.cfg.target_buffer_pct / 100.0)
        if tp2 <= float(c):
            return None
        tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
        tp1 = float(c) + (tp2 - float(c)) * 0.5
        if tp1 <= float(c):
            return None

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="btc_swing_zone_reclaim_v1",
            symbol=store.symbol,
            side="long",
            entry=float(c),
            sl=float(sl),
            tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(10, int(self.cfg.atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="btcs1_swing_zone_reclaim",
        )
        return sig if sig.validate() else None
