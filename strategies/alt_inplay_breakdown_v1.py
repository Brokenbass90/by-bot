"""
alt_inplay_breakdown_v1 — independent bearish continuation / failed-reclaim short

This is intentionally no longer a mirror of the long-side in-play breakout.
The short side in crypto behaves more like:
1) a real support break / dump on 1h structure,
2) a weak reclaim back into broken support, or
3) immediate continuation while price is still compressed under that level.

The strategy keeps the existing BREAKDOWN_* env namespace so the live bot and
portfolio harness do not need a config migration.
"""
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


@dataclass
class AltInplayBreakdownV1Config:
    structure_tf: str = "60"
    entry_tf: str = "5"
    lookback_h: int = 48
    atr_period: int = 14
    break_buffer_atr: float = 0.10
    min_break_atr: float = 0.20
    min_break_body_frac: float = 0.35
    retest_touch_atr: float = 0.35
    reclaim_atr: float = 0.12
    entry_body_min_frac: float = 0.18
    max_dist_atr: float = 2.0
    rsi_max: float = 55.0
    reject_vol_mult: float = 0.0
    reject_vol_avg_bars: int = 5

    allow_failed_reclaim: bool = True
    allow_continuation: bool = True
    allow_shorts: bool = True

    regime_mode: str = "off"
    regime_tf: str = "240"
    regime_ema_fast: int = 21
    regime_ema_slow: int = 55

    sl_atr: float = 1.8
    rr: float = 2.0
    tp1_frac: float = 0.50
    next_level_tp_enable: bool = True
    next_level_lookback_mult: float = 2.0
    next_level_buffer_atr: float = 0.30
    time_stop_bars_5m: int = 288
    cooldown_bars_5m: int = 48
    max_wait_bars_5m: int = 30


def _find_next_support_below(
    lows: List[float],
    current_level: float,
    atr: float,
    min_gap_atr: float = 1.0,
) -> Optional[float]:
    if not lows or not math.isfinite(current_level) or not math.isfinite(atr) or atr <= 0:
        return None
    threshold = current_level - max(0.5, float(min_gap_atr)) * atr
    candidates = sorted((float(x) for x in lows if math.isfinite(float(x)) and float(x) < threshold), reverse=True)
    if not candidates:
        return None

    clusters: List[List[float]] = [[candidates[0]]]
    cluster_gap = 0.5 * atr
    for val in candidates[1:]:
        if clusters[-1][-1] - val <= cluster_gap:
            clusters[-1].append(val)
        else:
            clusters.append([val])

    ranked = sorted(
        (
            {
                "upper": max(cluster),
                "count": len(cluster),
            }
            for cluster in clusters
        ),
        key=lambda x: (x["count"], x["upper"]),
        reverse=True,
    )
    if not ranked:
        return None

    best_count = ranked[0]["count"]
    nearest = sorted((item for item in ranked if item["count"] >= max(2, best_count)), key=lambda x: x["upper"], reverse=True)
    chosen = nearest[0] if nearest else ranked[0]
    return float(chosen["upper"])


class AltInplayBreakdownV1Strategy:
    """
    Short-only setup built around bearish structure breaks.

    Entry families:
    - failed reclaim: 1h support breaks, 5m bounces back, fails under broken level
    - dump continuation: after a real 1h break, 5m keeps selling without meaningful reclaim
    """

    STRATEGY_NAME = "alt_inplay_breakdown_v1"

    def __init__(self, cfg: Optional[AltInplayBreakdownV1Config] = None):
        self.cfg = cfg or AltInplayBreakdownV1Config()

        self.cfg.structure_tf = os.getenv("BREAKDOWN_TF_BREAK", self.cfg.structure_tf)
        self.cfg.entry_tf = os.getenv("BREAKDOWN_TF_ENTRY", self.cfg.entry_tf)
        self.cfg.lookback_h = _env_int("BREAKDOWN_LOOKBACK_H", self.cfg.lookback_h)
        self.cfg.atr_period = _env_int("BREAKDOWN_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.break_buffer_atr = _env_float("BREAKDOWN_BUFFER_ATR", self.cfg.break_buffer_atr)
        self.cfg.min_break_atr = _env_float("BREAKDOWN_MIN_BREAK_ATR", self.cfg.min_break_atr)
        self.cfg.min_break_body_frac = _env_float("BREAKDOWN_IMPULSE_BODY_MIN_FRAC", self.cfg.min_break_body_frac)
        self.cfg.retest_touch_atr = _env_float("BREAKDOWN_RETEST_TOUCH_ATR", self.cfg.retest_touch_atr)
        self.cfg.reclaim_atr = _env_float("BREAKDOWN_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.entry_body_min_frac = _env_float("BREAKDOWN_ENTRY_BODY_MIN_FRAC", self.cfg.entry_body_min_frac)
        self.cfg.max_dist_atr = _env_float("BREAKDOWN_MAX_DIST_ATR", self.cfg.max_dist_atr)
        self.cfg.rsi_max = _env_float("BREAKDOWN_RSI_MAX", self.cfg.rsi_max)
        self.cfg.reject_vol_mult = _env_float(
            "BREAKDOWN_REJECT_VOL_MULT",
            _env_float("BREAKDOWN_IMPULSE_VOL_MULT", self.cfg.reject_vol_mult),
        )
        self.cfg.reject_vol_avg_bars = _env_int("BREAKDOWN_REJECT_VOL_AVG_BARS", self.cfg.reject_vol_avg_bars)
        self.cfg.allow_failed_reclaim = _env_bool("BREAKDOWN_ALLOW_FAILED_RECLAIM", self.cfg.allow_failed_reclaim)
        self.cfg.allow_continuation = _env_bool("BREAKDOWN_ALLOW_CONTINUATION", self.cfg.allow_continuation)
        self.cfg.allow_shorts = _env_bool("BREAKDOWN_ALLOW_SHORTS", self.cfg.allow_shorts)

        self.cfg.regime_mode = os.getenv("BREAKDOWN_REGIME_MODE", self.cfg.regime_mode)
        self.cfg.regime_tf = os.getenv("BREAKDOWN_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("BREAKDOWN_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BREAKDOWN_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)

        self.cfg.sl_atr = _env_float("BREAKDOWN_SL_ATR", self.cfg.sl_atr)
        self.cfg.rr = _env_float("BREAKDOWN_RR", self.cfg.rr)
        self.cfg.tp1_frac = _env_float("BREAKDOWN_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.next_level_tp_enable = _env_bool("BREAKDOWN_NEXT_LEVEL_TP_ENABLE", self.cfg.next_level_tp_enable)
        self.cfg.next_level_lookback_mult = _env_float("BREAKDOWN_NEXT_LEVEL_LOOKBACK_MULT", self.cfg.next_level_lookback_mult)
        self.cfg.next_level_buffer_atr = _env_float("BREAKDOWN_NEXT_LEVEL_BUFFER_ATR", self.cfg.next_level_buffer_atr)
        self.cfg.time_stop_bars_5m = _env_int("BREAKDOWN_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BREAKDOWN_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_wait_bars_5m = _env_int("BREAKDOWN_MAX_RETEST_BARS", self.cfg.max_wait_bars_5m)

        self._allow = _env_csv_set("BREAKDOWN_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("BREAKDOWN_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_structure_ts: Optional[int] = None
        self._last_entry_ts: Optional[int] = None
        self._armed: Optional[dict] = None
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("BREAKDOWN_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("BREAKDOWN_SYMBOL_DENYLIST")

    def _regime_ok(self, store) -> bool:
        if str(self.cfg.regime_mode).strip().lower() != "ema":
            return True
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, max(100, self.cfg.regime_ema_slow + 20)) or []
        if len(rows) < self.cfg.regime_ema_slow + 20:
            self.last_no_signal_reason = "regime_history_short"
            return False
        closes = [float(r[4]) for r in rows]
        ema_fast = _ema(closes, self.cfg.regime_ema_fast)
        ema_slow = _ema(closes, self.cfg.regime_ema_slow)
        if not all(math.isfinite(x) for x in (ema_fast, ema_slow)):
            self.last_no_signal_reason = "regime_invalid"
            return False
        return ema_fast < ema_slow

    def _arm_structure(self, store, entry_ts: int) -> None:
        lookback = max(24, int(self.cfg.lookback_h))
        rows = store.fetch_klines(store.symbol, self.cfg.structure_tf, lookback + 10) or []
        if len(rows) < lookback + 2:
            self.last_no_signal_reason = "structure_history_short"
            return

        structure_ts = int(float(rows[-1][0]))
        if self._last_structure_ts is not None and structure_ts == self._last_structure_ts:
            return
        self._last_structure_ts = structure_ts

        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]

        atr = _atr_from_rows(rows, self.cfg.atr_period)
        rsi = _rsi(closes, 14)
        if not all(math.isfinite(x) for x in (atr, rsi)) or atr <= 0:
            self.last_no_signal_reason = "structure_invalid"
            return

        support = min(lows[-(lookback + 1):-1])
        last_open = opens[-1]
        last_close = closes[-1]
        last_high = highs[-1]
        last_low = lows[-1]
        last_range = max(1e-12, last_high - last_low)
        body_frac = abs(last_close - last_open) / last_range
        dist_atr = (support - last_close) / atr

        broke_support = last_close < support - self.cfg.break_buffer_atr * atr
        bearish_impulse = last_close < last_open and body_frac >= self.cfg.min_break_body_frac

        if not self.cfg.allow_shorts:
            self.last_no_signal_reason = "shorts_disabled"
            return
        if not self._regime_ok(store):
            self.last_no_signal_reason = "regime_not_bearish"
            return
        if rsi > self.cfg.rsi_max:
            self.last_no_signal_reason = f"rsi_too_high_{rsi:.1f}"
            return
        if not broke_support:
            self.last_no_signal_reason = "no_real_break"
            return
        if not bearish_impulse:
            self.last_no_signal_reason = f"weak_break_body_{body_frac:.2f}"
            return
        if dist_atr < self.cfg.min_break_atr:
            self.last_no_signal_reason = f"break_too_small_{dist_atr:.2f}atr"
            return
        if dist_atr > self.cfg.max_dist_atr * 1.5:
            self.last_no_signal_reason = f"break_too_extended_{dist_atr:.2f}atr"
            return

        next_support = None
        if self.cfg.next_level_tp_enable:
            wider_lookback = max(lookback + 10, int(math.ceil(float(lookback) * max(1.0, float(self.cfg.next_level_lookback_mult))))) 
            rows_wide = store.fetch_klines(store.symbol, self.cfg.structure_tf, wider_lookback + 10) or []
            if rows_wide:
                all_lows = [float(r[3]) for r in rows_wide[:-1]] if len(rows_wide) > 1 else [float(r[3]) for r in rows_wide]
                next_support = _find_next_support_below(all_lows, support, atr)

        self._armed = {
            "level": support,
            "next_support": next_support,
            "atr": atr,
            "break_close": last_close,
            "break_high": last_high,
            "entry_armed_ts": int(entry_ts),
            "structure_ts": structure_ts,
        }
        self.last_no_signal_reason = "armed_breakdown"

    def _signal_from_entry_bar(self, store, rows_5m: List[list]) -> Optional[TradeSignal]:
        if self._armed is None:
            return None

        level = float(self._armed["level"])
        atr = float(self._armed["atr"])
        break_close = float(self._armed["break_close"])

        open_5m = float(rows_5m[-1][1])
        high_5m = float(rows_5m[-1][2])
        low_5m = float(rows_5m[-1][3])
        close_5m = float(rows_5m[-1][4])
        prev_close = float(rows_5m[-2][4]) if len(rows_5m) >= 2 else close_5m

        body = abs(close_5m - open_5m)
        bar_range = max(1e-12, high_5m - low_5m)
        body_frac = body / bar_range
        bearish_body = close_5m < open_5m and body_frac >= self.cfg.entry_body_min_frac

        vol_ok = True
        if self.cfg.reject_vol_mult > 0 and len(rows_5m) >= self.cfg.reject_vol_avg_bars + 1:
            tail = rows_5m[-(self.cfg.reject_vol_avg_bars + 1):-1]
            base = sum(float(r[5]) for r in tail) / float(len(tail))
            cur_vol = float(rows_5m[-1][5])
            vol_ok = base > 0 and cur_vol >= self.cfg.reject_vol_mult * base

        touched_reclaim_zone = high_5m >= level - self.cfg.retest_touch_atr * atr
        reclaimed_below = close_5m <= level - self.cfg.reclaim_atr * atr
        extension_atr = (level - close_5m) / max(1e-12, atr)

        if close_5m > level + self.cfg.reclaim_atr * atr:
            self._armed = None
            self.last_no_signal_reason = "reclaim_invalidated"
            return None
        if extension_atr > self.cfg.max_dist_atr * 1.5:
            self._armed = None
            self.last_no_signal_reason = f"entry_too_late_{extension_atr:.2f}atr"
            return None

        reason = ""
        if (
            self.cfg.allow_failed_reclaim
            and touched_reclaim_zone
            and reclaimed_below
            and bearish_body
            and vol_ok
        ):
            reason = "bd1_failed_reclaim"
        elif (
            self.cfg.allow_continuation
            and extension_atr >= self.cfg.min_break_atr
            and extension_atr <= self.cfg.max_dist_atr
            and bearish_body
            and vol_ok
            and close_5m < prev_close
            and close_5m <= break_close + 0.25 * atr
        ):
            reason = "bd1_dump_continuation"
        else:
            self.last_no_signal_reason = "entry_not_confirmed"
            return None

        entry = close_5m
        sl_base = max(high_5m, level + 0.10 * atr)
        sl = sl_base + max(0.10, self.cfg.sl_atr * 0.25) * atr
        if sl <= entry:
            self.last_no_signal_reason = "sl_invalid"
            return None

        risk = sl - entry
        atr_tp2 = entry - self.cfg.rr * risk
        tp2 = atr_tp2
        if tp2 >= entry:
            self.last_no_signal_reason = "tp_invalid"
            return None
        tp1_rr = max(0.8, float(self.cfg.rr) * min(0.8, max(0.1, float(self.cfg.tp1_frac))))
        tp1 = entry - tp1_rr * risk
        tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
        level_tp_applied = False

        next_support = self._armed.get("next_support") if self._armed else None
        if (
            self.cfg.next_level_tp_enable
            and next_support is not None
            and math.isfinite(float(next_support))
            and float(next_support) < entry
            and float(next_support) > atr_tp2
        ):
            level_tp = float(next_support) + max(0.05, float(self.cfg.next_level_buffer_atr)) * atr
            if atr_tp2 < level_tp < entry:
                tp2 = level_tp
                tp1 = entry - (entry - tp2) * 0.5
                level_tp_applied = True

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._armed = None
        sig = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=store.symbol,
            side="short",
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"{reason}+level_tp" if level_tp_applied else reason,
        )
        return sig if sig.validate() else None

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        return self._run(store, ts_ms, last_price)

    async def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        return self._run(store, ts_ms, last_price)

    def _run(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        _ = last_price
        self._refresh_runtime_allowlists()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_not_allowed"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_denied"
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None

        rows_5m = store.fetch_klines(store.symbol, self.cfg.entry_tf, 32) or []
        if len(rows_5m) < max(6, self.cfg.reject_vol_avg_bars + 1):
            self.last_no_signal_reason = "entry_history_short"
            return None
        entry_ts = int(float(rows_5m[-1][0]))
        if self._last_entry_ts is not None and entry_ts == self._last_entry_ts:
            return None
        self._last_entry_ts = entry_ts

        self._arm_structure(store, entry_ts)

        if self._armed is None:
            return None

        armed_ts = int(self._armed.get("entry_armed_ts", entry_ts))
        max_wait_ms = max(1, int(self.cfg.max_wait_bars_5m)) * 5 * 60_000
        if entry_ts - armed_ts > max_wait_ms:
            self._armed = None
            self.last_no_signal_reason = "setup_timeout"
            return None

        return self._signal_from_entry_bar(store, rows_5m)
