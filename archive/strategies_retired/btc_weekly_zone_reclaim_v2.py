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


def _compress_rows(rows: List[list], group_n: int) -> List[dict]:
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


def _find_pivot_low(
    rows: List[dict],
    *,
    left: int,
    right: int,
    max_age: int,
    cur_close: float,
) -> Optional[int]:
    start = max(left, len(rows) - max_age - right - 1)
    end = len(rows) - right
    for i in range(end - 1, start - 1, -1):
        low_i = rows[i]["l"]
        if low_i >= cur_close:
            continue
        if all(low_i < rows[j]["l"] for j in range(i - left, i)) and all(
            low_i <= rows[j]["l"] for j in range(i + 1, i + right + 1)
        ):
            return i
    return None


def _find_next_pivot_high(
    rows: List[dict],
    *,
    left: int,
    right: int,
    max_age: int,
    cur_close: float,
) -> Optional[float]:
    start = max(left, len(rows) - max_age - right - 1)
    end = len(rows) - right
    candidates: List[float] = []
    for i in range(start, end):
        hi_i = rows[i]["h"]
        if hi_i <= cur_close:
            continue
        if all(hi_i > rows[j]["h"] for j in range(i - left, i)) and all(
            hi_i >= rows[j]["h"] for j in range(i + 1, i + right + 1)
        ):
            candidates.append(hi_i)
    if candidates:
        return min(candidates)
    fallback = [x["h"] for x in rows[max(0, len(rows) - max_age):] if x["h"] > cur_close]
    return min(fallback) if fallback else None


@dataclass
class BTCWeeklyZoneReclaimV2Config:
    regime_tf: str = "240"
    daily_group: int = 6
    weekly_group: int = 42
    weekly_ema_fast: int = 10
    weekly_ema_slow: int = 20
    weekly_slope_weeks: int = 3
    weekly_gap_min_pct: float = 1.10
    weekly_slope_min_pct: float = 0.40

    signal_tf: str = "240"
    signal_ema_period: int = 20
    atr_period: int = 14
    max_signal_atr_pct: float = 3.40

    daily_pivot_left: int = 2
    daily_pivot_right: int = 2
    daily_support_max_age: int = 45
    daily_resistance_max_age: int = 70
    weekly_support_max_age: int = 16
    support_zone_atr: float = 0.40
    reclaim_pct: float = 0.10
    min_room_to_target_pct: float = 1.80

    sl_atr_mult: float = 1.20
    support_sl_buffer_atr: float = 0.20
    tp1_frac: float = 0.40
    target_buffer_pct: float = 0.18
    trail_atr_mult: float = 0.0
    time_stop_bars_5m: int = 2304

    cooldown_bars_5m: int = 96
    allow_longs: bool = True
    allow_shorts: bool = False


class BTCWeeklyZoneReclaimV2Strategy:
    """BTC long-cycle reclaim using weekly regime + daily/4h zones."""

    def __init__(self, cfg: Optional[BTCWeeklyZoneReclaimV2Config] = None):
        self.cfg = cfg or BTCWeeklyZoneReclaimV2Config()

        self.cfg.regime_tf = os.getenv("BTCW2_REGIME_TF", self.cfg.regime_tf)
        self.cfg.daily_group = _env_int("BTCW2_DAILY_GROUP", self.cfg.daily_group)
        self.cfg.weekly_group = _env_int("BTCW2_WEEKLY_GROUP", self.cfg.weekly_group)
        self.cfg.weekly_ema_fast = _env_int("BTCW2_WEEKLY_EMA_FAST", self.cfg.weekly_ema_fast)
        self.cfg.weekly_ema_slow = _env_int("BTCW2_WEEKLY_EMA_SLOW", self.cfg.weekly_ema_slow)
        self.cfg.weekly_slope_weeks = _env_int("BTCW2_WEEKLY_SLOPE_WEEKS", self.cfg.weekly_slope_weeks)
        self.cfg.weekly_gap_min_pct = _env_float("BTCW2_WEEKLY_GAP_MIN_PCT", self.cfg.weekly_gap_min_pct)
        self.cfg.weekly_slope_min_pct = _env_float("BTCW2_WEEKLY_SLOPE_MIN_PCT", self.cfg.weekly_slope_min_pct)

        self.cfg.signal_tf = os.getenv("BTCW2_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_ema_period = _env_int("BTCW2_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.atr_period = _env_int("BTCW2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.max_signal_atr_pct = _env_float("BTCW2_MAX_SIGNAL_ATR_PCT", self.cfg.max_signal_atr_pct)

        self.cfg.daily_pivot_left = _env_int("BTCW2_DAILY_PIVOT_LEFT", self.cfg.daily_pivot_left)
        self.cfg.daily_pivot_right = _env_int("BTCW2_DAILY_PIVOT_RIGHT", self.cfg.daily_pivot_right)
        self.cfg.daily_support_max_age = _env_int("BTCW2_DAILY_SUPPORT_MAX_AGE", self.cfg.daily_support_max_age)
        self.cfg.daily_resistance_max_age = _env_int("BTCW2_DAILY_RESISTANCE_MAX_AGE", self.cfg.daily_resistance_max_age)
        self.cfg.weekly_support_max_age = _env_int("BTCW2_WEEKLY_SUPPORT_MAX_AGE", self.cfg.weekly_support_max_age)
        self.cfg.support_zone_atr = _env_float("BTCW2_SUPPORT_ZONE_ATR", self.cfg.support_zone_atr)
        self.cfg.reclaim_pct = _env_float("BTCW2_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.min_room_to_target_pct = _env_float("BTCW2_MIN_ROOM_TO_TARGET_PCT", self.cfg.min_room_to_target_pct)

        self.cfg.sl_atr_mult = _env_float("BTCW2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.support_sl_buffer_atr = _env_float("BTCW2_SUPPORT_SL_BUFFER_ATR", self.cfg.support_sl_buffer_atr)
        self.cfg.tp1_frac = _env_float("BTCW2_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.target_buffer_pct = _env_float("BTCW2_TARGET_BUFFER_PCT", self.cfg.target_buffer_pct)
        self.cfg.trail_atr_mult = _env_float("BTCW2_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTCW2_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)

        self.cfg.cooldown_bars_5m = _env_int("BTCW2_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("BTCW2_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BTCW2_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BTCW2_SYMBOL_ALLOWLIST", "BTCUSDT")
        self._deny = _env_csv_set("BTCW2_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_signal_tf_ts: Optional[int] = None
        self._ctx_tf_ts: Optional[int] = None
        self._ctx_cache: Optional[dict] = None

    def _build_context(self, store) -> Optional[dict]:
        need_weeks = max(self.cfg.weekly_ema_slow + self.cfg.weekly_slope_weeks + self.cfg.weekly_support_max_age + 4, 48)
        need_days = max(self.cfg.daily_resistance_max_age + self.cfg.daily_support_max_age + 8, 120)
        need_4h = max(
            need_weeks * max(1, self.cfg.weekly_group) + 8,
            need_days * max(1, self.cfg.daily_group) + 8,
        )
        rows_4h = store.fetch_klines(store.symbol, self.cfg.regime_tf, need_4h) or []
        if len(rows_4h) < max(self.cfg.weekly_group * (self.cfg.weekly_ema_slow + 2), self.cfg.daily_group * 60):
            return None

        daily = _compress_rows(rows_4h, self.cfg.daily_group)
        weekly = _compress_rows(rows_4h, self.cfg.weekly_group)
        if len(daily) < self.cfg.daily_pivot_right + self.cfg.daily_support_max_age + 3:
            return None
        if len(weekly) < self.cfg.weekly_ema_slow + self.cfg.weekly_slope_weeks + 2:
            return None

        weekly_closes = [x["c"] for x in weekly]
        wf = _ema(weekly_closes, self.cfg.weekly_ema_fast)
        ws = _ema(weekly_closes, self.cfg.weekly_ema_slow)
        ws_prev = _ema(weekly_closes[:-max(1, self.cfg.weekly_slope_weeks)], self.cfg.weekly_ema_slow)
        cur_close = weekly_closes[-1]
        if not (math.isfinite(wf) and math.isfinite(ws) and math.isfinite(ws_prev) and cur_close > 0 and ws_prev != 0):
            return None

        gap_pct = abs(wf - ws) / cur_close * 100.0
        slope_pct = (ws - ws_prev) / abs(ws_prev) * 100.0
        bullish = wf > ws and slope_pct >= self.cfg.weekly_slope_min_pct and gap_pct >= self.cfg.weekly_gap_min_pct
        if not bullish:
            return {"bias": 1}

        daily_support_idx = _find_pivot_low(
            daily,
            left=self.cfg.daily_pivot_left,
            right=self.cfg.daily_pivot_right,
            max_age=self.cfg.daily_support_max_age,
            cur_close=daily[-1]["c"],
        )
        weekly_support_idx = _find_pivot_low(
            weekly,
            left=1,
            right=1,
            max_age=self.cfg.weekly_support_max_age,
            cur_close=weekly[-1]["c"],
        )
        if daily_support_idx is None:
            return {"bias": 1}

        support = float(daily[daily_support_idx]["l"])
        if weekly_support_idx is not None:
            support = max(support, float(weekly[weekly_support_idx]["l"]))

        daily_resistance = _find_next_pivot_high(
            daily,
            left=self.cfg.daily_pivot_left,
            right=self.cfg.daily_pivot_right,
            max_age=self.cfg.daily_resistance_max_age,
            cur_close=daily[-1]["c"],
        )
        weekly_resistance = _find_next_pivot_high(
            weekly,
            left=1,
            right=1,
            max_age=max(8, self.cfg.weekly_support_max_age + 6),
            cur_close=weekly[-1]["c"],
        )
        candidates = [x for x in (daily_resistance, weekly_resistance) if x is not None]
        if not candidates:
            return {"bias": 1}
        resistance = float(min(candidates))

        return {
            "bias": 2,
            "support": support,
            "resistance": resistance,
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

        rows_4h = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(self.cfg.signal_ema_period + 20, 80)) or []
        if len(rows_4h) < self.cfg.signal_ema_period + self.cfg.atr_period + 3:
            return None

        t_last = int(float(rows_4h[-1][0]))
        if self._last_signal_tf_ts is None:
            self._last_signal_tf_ts = t_last
            return None
        if t_last == self._last_signal_tf_ts:
            return None
        self._last_signal_tf_ts = t_last

        if self._ctx_tf_ts != t_last:
            self._ctx_cache = self._build_context(store)
            self._ctx_tf_ts = t_last
        ctx = self._ctx_cache
        if not ctx or ctx.get("bias") != 2:
            return None

        highs = [float(r[2]) for r in rows_4h]
        lows = [float(r[3]) for r in rows_4h]
        closes = [float(r[4]) for r in rows_4h]
        ema4h = _ema(closes, self.cfg.signal_ema_period)
        atr4h = _atr_from_rows(rows_4h, self.cfg.atr_period)
        if not (math.isfinite(ema4h) and math.isfinite(atr4h) and atr4h > 0):
            return None

        cur_c = float(closes[-1])
        prev_c = float(closes[-2])
        atr_pct = atr4h / max(1e-12, abs(cur_c)) * 100.0
        if atr_pct > self.cfg.max_signal_atr_pct:
            return None

        support = float(ctx["support"])
        resistance = float(ctx["resistance"])
        zone_high = support + self.cfg.support_zone_atr * atr4h
        touched = lows[-1] <= zone_high
        reclaimed = cur_c >= zone_high * (1.0 + self.cfg.reclaim_pct / 100.0) and prev_c <= max(zone_high * 1.008, ema4h * 1.01)
        trend_ok = cur_c >= ema4h
        room_pct = (resistance - cur_c) / max(1e-12, cur_c) * 100.0
        if not (touched and reclaimed and trend_ok and room_pct >= self.cfg.min_room_to_target_pct):
            return None

        sl = min(
            support - self.cfg.support_sl_buffer_atr * atr4h,
            cur_c - self.cfg.sl_atr_mult * atr4h,
        )
        if sl >= cur_c:
            return None

        tp2 = resistance * (1.0 - self.cfg.target_buffer_pct / 100.0)
        if tp2 <= cur_c:
            return None
        tp1 = cur_c + (tp2 - cur_c) * 0.45
        if tp1 <= cur_c:
            return None

        tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        return TradeSignal(
            strategy="btc_weekly_zone_reclaim_v2",
            symbol=store.symbol,
            side="long",
            entry=cur_c,
            sl=float(sl),
            tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(1, int(self.cfg.atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"btc_w2_supp={support:.2f}_res={resistance:.2f}",
        )
