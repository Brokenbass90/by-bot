"""
spike_fade_v3 — пампы/дампы под логику реальных уровней.

Owner's idea: a sharp vertical move (pump/dump) that runs INTO a strong level
and then shows exhaustion is a high-probability fade — 2-3% per operation.

  PUMP FADE (short): fast run-UP into a strong RESISTANCE, then a rejection bar
    (closes in the lower part of its range) -> short. Stop just above the spike
    high; take profit toward the level/mean below.
  DUMP RECLAIM (long): fast flush-DOWN into a strong SUPPORT, then a reclaim bar
    (closes in the upper part) -> long. Stop just below the spike low.

Key discipline vs the old pump_fade_* family: we ONLY fade when the spike tags a
REAL level (from bot.chart_geometry), never into open space. Reuses the v3
machinery (levels, closed-candle history, same Signal contract).
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal
from .inplay_retest_v3 import (
    _env_float, _env_int, _env_bool, _env_csv_set,
    _atr, _sma, _closed_rows_before, _interval_ms, _row_ts_ms,
)
from bot.chart_geometry import find_pivots, cluster_horizontal_levels


@dataclass
class SpikeFadeV3Config:
    structure_tf: str = "60"
    entry_tf: str = "15"
    level_lookback: int = 240
    entry_lookback: int = 80

    pivot_left: int = 2
    pivot_right: int = 2
    min_touches: int = 2
    level_tol_atr: float = 0.35
    max_levels: int = 10

    atr_period: int = 14
    # spike detection (on the entry TF, over the last N bars incl. current)
    spike_lookback: int = 6
    spike_min_pct: float = 4.0      # min vertical move to call it a pump/dump
    tag_level_atr: float = 0.6      # spike extreme must reach within this of a real level
    pierce_atr: float = 0.8         # but must not blow far past it
    reject_frac: float = 0.5        # close must retrace this fraction of the bar back
    vol_period: int = 20
    vol_spike_mult: float = 0.0     # optional: require spike-bar volume >= this*baseline (0=off)

    stop_buffer_atr: float = 0.4    # stop beyond the spike extreme
    rr_runner: float = 2.0
    tp1_frac: float = 0.6
    min_rr_tp1: float = 1.1
    min_stop_pct: float = 0.0015
    max_stop_pct: float = 0.08      # pump bars are big -> allow a wider stop than v3

    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.0
    trail_atr_mult: float = 0.0
    trail_activate_rr: float = 0.0
    time_stop_bars: int = 0

    allow_long: bool = True         # dump reclaim
    allow_short: bool = True        # pump fade
    cooldown_bars: int = 3
    allow_csv: str = ""
    deny_csv: str = ""


class SpikeFadeV3Strategy:
    STRATEGY_NAME = "spike_fade_v3"

    def __init__(self, cfg: Optional[SpikeFadeV3Config] = None):
        self.cfg = cfg or SpikeFadeV3Config()
        self.last_no_signal_reason = ""
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._allow: set[str] = set()
        self._deny: set[str] = set()
        self._load_env()

    def _load_env(self) -> None:
        c = self.cfg
        c.structure_tf = os.getenv("SFV3_STRUCTURE_TF", c.structure_tf)
        c.entry_tf = os.getenv("SFV3_ENTRY_TF", c.entry_tf)
        c.level_lookback = _env_int("SFV3_LEVEL_LOOKBACK", c.level_lookback)
        c.entry_lookback = _env_int("SFV3_ENTRY_LOOKBACK", c.entry_lookback)
        c.pivot_left = _env_int("SFV3_PIVOT_LEFT", c.pivot_left)
        c.pivot_right = _env_int("SFV3_PIVOT_RIGHT", c.pivot_right)
        c.min_touches = _env_int("SFV3_MIN_TOUCHES", c.min_touches)
        c.level_tol_atr = _env_float("SFV3_LEVEL_TOL_ATR", c.level_tol_atr)
        c.max_levels = _env_int("SFV3_MAX_LEVELS", c.max_levels)
        c.atr_period = _env_int("SFV3_ATR_PERIOD", c.atr_period)
        c.spike_lookback = _env_int("SFV3_SPIKE_LOOKBACK", c.spike_lookback)
        c.spike_min_pct = _env_float("SFV3_SPIKE_MIN_PCT", c.spike_min_pct)
        c.tag_level_atr = _env_float("SFV3_TAG_LEVEL_ATR", c.tag_level_atr)
        c.pierce_atr = _env_float("SFV3_PIERCE_ATR", c.pierce_atr)
        c.reject_frac = _env_float("SFV3_REJECT_FRAC", c.reject_frac)
        c.vol_period = _env_int("SFV3_VOL_PERIOD", c.vol_period)
        c.vol_spike_mult = _env_float("SFV3_VOL_SPIKE_MULT", c.vol_spike_mult)
        c.stop_buffer_atr = _env_float("SFV3_STOP_BUFFER_ATR", c.stop_buffer_atr)
        c.rr_runner = _env_float("SFV3_RR_RUNNER", c.rr_runner)
        c.tp1_frac = _env_float("SFV3_TP1_FRAC", c.tp1_frac)
        c.min_rr_tp1 = _env_float("SFV3_MIN_RR_TP1", c.min_rr_tp1)
        c.min_stop_pct = _env_float("SFV3_MIN_STOP_PCT", c.min_stop_pct)
        c.max_stop_pct = _env_float("SFV3_MAX_STOP_PCT", c.max_stop_pct)
        c.be_trigger_rr = _env_float("SFV3_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("SFV3_BE_LOCK_RR", c.be_lock_rr)
        c.trail_atr_mult = _env_float("SFV3_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr = _env_float("SFV3_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.time_stop_bars = _env_int("SFV3_TIME_STOP_BARS", c.time_stop_bars)
        c.allow_long = _env_bool("SFV3_ALLOW_LONG", c.allow_long)
        c.allow_short = _env_bool("SFV3_ALLOW_SHORT", c.allow_short)
        c.cooldown_bars = _env_int("SFV3_COOLDOWN_BARS", c.cooldown_bars)
        self._allow = _env_csv_set("SFV3_ALLOW", c.allow_csv)
        self._deny = _env_csv_set("SFV3_DENY", c.deny_csv)

    def _levels(self, rows: List[list], atr: float) -> List[Tuple[float, float, str]]:
        pivots = find_pivots(rows, left=self.cfg.pivot_left, right=self.cfg.pivot_right)
        levels = cluster_horizontal_levels(
            rows, pivots, atr=atr, tolerance_atr=self.cfg.level_tol_atr,
            min_touches=self.cfg.min_touches, max_levels=self.cfg.max_levels,
        )
        return [(float(lv.price), float(lv.score), str(lv.side_bias)) for lv in levels]

    @staticmethod
    def _nearest(levels, price, side):
        if side == "long":   # target above
            above = [p for p, _, _ in levels if p > price]
            return min(above) if above else None
        below = [p for p, _, _ in levels if p < price]
        return max(below) if below else None

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        self.last_no_signal_reason = ""
        self._load_env()
        cfg = self.cfg
        try:
            signal_ts_ms = int(float(ts_ms))
        except Exception:
            self.last_no_signal_reason = "invalid_ts"
            return None

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_not_allowed"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_denied"
            return None

        structure_raw = store.fetch_klines(sym, cfg.structure_tf, cfg.level_lookback + 2) or []
        entry_need = max(cfg.entry_lookback, cfg.spike_lookback + cfg.vol_period + cfg.atr_period + 5)
        entry_raw = store.fetch_klines(sym, cfg.entry_tf, entry_need + 2) or []
        structure_rows = _closed_rows_before(
            structure_raw,
            signal_ts_ms,
            cfg.level_lookback,
            interval_ms=_interval_ms(cfg.structure_tf),
        )
        entry_closed_rows = _closed_rows_before(
            entry_raw,
            signal_ts_ms,
            entry_need + 1,
            interval_ms=_interval_ms(cfg.entry_tf),
        )
        if len(structure_rows) < (cfg.pivot_left + cfg.pivot_right + cfg.min_touches + 5):
            self.last_no_signal_reason = "not_enough_closed_structure_bars"
            return None
        min_entry_history = max(
            cfg.spike_lookback,
            cfg.atr_period,
            cfg.vol_period if cfg.vol_spike_mult > 0 else 3,
        )
        if len(entry_closed_rows) < min_entry_history + 1:
            self.last_no_signal_reason = "not_enough_closed_entry_bars"
            return None

        trigger_row = entry_closed_rows[-1]
        entry_history = entry_closed_rows[:-1]
        trigger_ts = _row_ts_ms(trigger_row)
        if trigger_ts is None:
            self.last_no_signal_reason = "invalid_entry_bar_ts"
            return None
        if self._last_entry_ts is not None and trigger_ts == self._last_entry_ts:
            self.last_no_signal_reason = "same_entry_bar"
            return None
        self._last_entry_ts = trigger_ts
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None

        atr = _atr(structure_rows, cfg.atr_period)
        if not (math.isfinite(atr) and atr > 0):
            self.last_no_signal_reason = "structure_atr_invalid"
            return None
        entry_atr_rows = entry_history + [trigger_row]
        entry_atr = _atr(entry_atr_rows, cfg.atr_period)
        if not (math.isfinite(entry_atr) and entry_atr > 0):
            self.last_no_signal_reason = "entry_atr_invalid"
            return None

        cur_open = float(trigger_row[1])
        cur_high = float(trigger_row[2])
        cur_low = float(trigger_row[3])
        cur_close = float(trigger_row[4])
        cur_vol = float(trigger_row[5]) if len(trigger_row) > 5 else 0.0
        bar_range = max(1e-12, cur_high - cur_low)

        # recent extremes over the spike window (closed history + current bar)
        recent_lows = [float(r[3]) for r in entry_history[-cfg.spike_lookback:]] + [cur_low]
        recent_highs = [float(r[2]) for r in entry_history[-cfg.spike_lookback:]] + [cur_high]
        ref_low = min(recent_lows)
        ref_high = max(recent_highs)
        pump_pct = (cur_high / ref_low - 1.0) * 100.0 if ref_low > 0 else 0.0
        dump_pct = (1.0 - cur_low / ref_high) * 100.0 if ref_high > 0 else 0.0

        levels = self._levels(structure_rows, atr)
        if not levels:
            self.last_no_signal_reason = "no_levels"
            return None

        tag = cfg.tag_level_atr * atr
        pierce = cfg.pierce_atr * atr

        # optional volume-spike confirmation
        if cfg.vol_spike_mult > 0:
            vb = _sma([float(r[5]) if len(r) > 5 else 0.0 for r in entry_history], cfg.vol_period)
            if math.isfinite(vb) and vb > 0 and cur_vol < cfg.vol_spike_mult * vb:
                self.last_no_signal_reason = "no_volume_spike"
                return None

        side = None
        level = None
        # PUMP FADE (short): up-spike into a resistance, rejection close in lower part
        if cfg.allow_short and pump_pct >= cfg.spike_min_pct:
            res = [(p, s) for p, s, sb in levels if sb in ("resistance", "mixed")
                   and (p - tag) <= cur_high <= (p + pierce)]
            rejected = (cur_high - cur_close) >= cfg.reject_frac * bar_range and cur_close < cur_high
            if res and rejected:
                level = max(res, key=lambda ps: ps[1])[0]
                side = "short"
        # DUMP RECLAIM (long): down-spike into a support, reclaim close in upper part
        if side is None and cfg.allow_long and dump_pct >= cfg.spike_min_pct:
            sup = [(p, s) for p, s, sb in levels if sb in ("support", "mixed")
                   and (p - pierce) <= cur_low <= (p + tag)]
            reclaimed = (cur_close - cur_low) >= cfg.reject_frac * bar_range and cur_close > cur_low
            if sup and reclaimed:
                level = min(sup, key=lambda ps: ps[1])[0]
                side = "long"

        if side is None:
            self.last_no_signal_reason = "no_spike_fade_setup"
            return None

        entry = float(cur_close)
        if side == "short":
            sl = max(cur_high, level) + cfg.stop_buffer_atr * entry_atr
            if sl <= entry:
                self.last_no_signal_reason = "sl_at_or_below_entry"
                return None
            risk = sl - entry
            nxt = self._nearest(levels, entry, "short")
            tp1 = nxt if (nxt and (entry - nxt) / risk >= cfg.min_rr_tp1) else (entry - cfg.min_rr_tp1 * risk)
            tp2 = min(entry - cfg.rr_runner * risk, tp1 - 0.25 * risk)
            rr_tp1 = (entry - tp1) / risk
        else:
            sl = min(cur_low, level) - cfg.stop_buffer_atr * entry_atr
            if sl >= entry:
                self.last_no_signal_reason = "sl_at_or_above_entry"
                return None
            risk = entry - sl
            nxt = self._nearest(levels, entry, "long")
            tp1 = nxt if (nxt and (nxt - entry) / risk >= cfg.min_rr_tp1) else (entry + cfg.min_rr_tp1 * risk)
            tp2 = max(entry + cfg.rr_runner * risk, tp1 + 0.25 * risk)
            rr_tp1 = (tp1 - entry) / risk

        stop_pct = risk / max(1e-12, entry)
        if stop_pct < cfg.min_stop_pct:
            self.last_no_signal_reason = f"stop_too_tight_{stop_pct:.4f}"
            return None
        if stop_pct > cfg.max_stop_pct:
            self.last_no_signal_reason = f"stop_too_wide_{stop_pct:.4f}"
            return None
        if rr_tp1 < cfg.min_rr_tp1:
            self.last_no_signal_reason = f"tp1_rr_too_low_{rr_tp1:.2f}"
            return None

        self._cooldown = max(0, cfg.cooldown_bars)
        return TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=sym,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[cfg.tp1_frac, max(0.0, 1.0 - cfg.tp1_frac)],
            trailing_atr_mult=cfg.trail_atr_mult,
            trailing_atr_period=cfg.atr_period,
            trail_activate_rr=cfg.trail_activate_rr,
            be_trigger_rr=max(0.0, float(cfg.be_trigger_rr)),
            be_lock_rr=max(0.0, float(cfg.be_lock_rr)),
            time_stop_bars=cfg.time_stop_bars,
            reason=f"spike_fade_{side}@{level:.6g}",
        )
