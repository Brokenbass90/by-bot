"""
breakdown_retest_v3 — "слом поддержки" under real-level logic (hedge for range).

Why: range ("пила во флэте") bleeds exactly when the market BREAKS a level
instead of bouncing between borders — that's its red bear month. The natural
counter-phase hedge is a short that triggers on a broken support: a level that
WAS support, price closed below it, then price retests it from below and fails
to reclaim → short, tight stop just above the (now resistance) level, take
profit before the next support down, runner beyond.

Shares the v3 approach: real levels from clustered pivots (bot.chart_geometry),
enter ON the retest near the level (entry-distance cap = tight risk), anti-
lookahead (levels from strictly-closed history). Short-only by design.

Contract identical to the other strategies:
  Strategy(cfg).maybe_signal(store, ts_ms, o, h, l, c, v) -> Optional[TradeSignal]
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal
from .inplay_retest_v3 import (
    _env_float, _env_int, _env_bool, _env_csv_set,
    _atr, _sma, _closed_rows_before,
)
from bot.chart_geometry import find_pivots, cluster_horizontal_levels


@dataclass
class BreakdownRetestV3Config:
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
    # a support counts as "broken" only if the latest closed structure bar is at
    # least this many ATR BELOW it (confirmed loss, not an intrabar wick)
    break_confirm_atr: float = 0.5
    retest_band_atr: float = 0.6   # price must be within this many ATR of the broken level
    touch_into_atr: float = 0.25   # bar must poke up into the level
    max_pierce_atr: float = 0.45   # but must not reclaim far above it
    reject_frac: float = 0.45      # close must sit this far down the bar (rejection)
    max_entry_dist_atr: float = 0.5  # entry (close) must be AT the level => tight stop

    # optional weak-retest filter: skip if the retest bar volume is too HIGH
    # (a strong retest often reclaims). 0 disables.
    vol_period: int = 20
    retest_vol_max_mult: float = 0.0

    stop_buffer_atr: float = 0.35
    tp_before_level_atr: float = 0.25
    rr_runner: float = 2.5
    tp1_frac: float = 0.6
    min_rr_tp1: float = 1.1
    min_stop_pct: float = 0.0015
    max_stop_pct: float = 0.06

    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.0
    trail_atr_mult: float = 0.0
    trail_activate_rr: float = 0.0
    time_stop_bars: int = 0

    cooldown_bars: int = 3
    allow_csv: str = ""
    deny_csv: str = ""


class BreakdownRetestV3Strategy:
    STRATEGY_NAME = "breakdown_retest_v3"

    def __init__(self, cfg: Optional[BreakdownRetestV3Config] = None):
        self.cfg = cfg or BreakdownRetestV3Config()
        self.last_no_signal_reason = ""
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._allow: set[str] = set()
        self._deny: set[str] = set()
        self._load_env()

    def _load_env(self) -> None:
        c = self.cfg
        c.structure_tf = os.getenv("BRV3_STRUCTURE_TF", c.structure_tf)
        c.entry_tf = os.getenv("BRV3_ENTRY_TF", c.entry_tf)
        c.level_lookback = _env_int("BRV3_LEVEL_LOOKBACK", c.level_lookback)
        c.entry_lookback = _env_int("BRV3_ENTRY_LOOKBACK", c.entry_lookback)
        c.pivot_left = _env_int("BRV3_PIVOT_LEFT", c.pivot_left)
        c.pivot_right = _env_int("BRV3_PIVOT_RIGHT", c.pivot_right)
        c.min_touches = _env_int("BRV3_MIN_TOUCHES", c.min_touches)
        c.level_tol_atr = _env_float("BRV3_LEVEL_TOL_ATR", c.level_tol_atr)
        c.max_levels = _env_int("BRV3_MAX_LEVELS", c.max_levels)
        c.atr_period = _env_int("BRV3_ATR_PERIOD", c.atr_period)
        c.break_confirm_atr = _env_float("BRV3_BREAK_CONFIRM_ATR", c.break_confirm_atr)
        c.retest_band_atr = _env_float("BRV3_RETEST_BAND_ATR", c.retest_band_atr)
        c.touch_into_atr = _env_float("BRV3_TOUCH_INTO_ATR", c.touch_into_atr)
        c.max_pierce_atr = _env_float("BRV3_MAX_PIERCE_ATR", c.max_pierce_atr)
        c.reject_frac = _env_float("BRV3_REJECT_FRAC", c.reject_frac)
        c.max_entry_dist_atr = _env_float("BRV3_MAX_ENTRY_DIST_ATR", c.max_entry_dist_atr)
        c.vol_period = _env_int("BRV3_VOL_PERIOD", c.vol_period)
        c.retest_vol_max_mult = _env_float("BRV3_RETEST_VOL_MAX_MULT", c.retest_vol_max_mult)
        c.stop_buffer_atr = _env_float("BRV3_STOP_BUFFER_ATR", c.stop_buffer_atr)
        c.tp_before_level_atr = _env_float("BRV3_TP_BEFORE_LEVEL_ATR", c.tp_before_level_atr)
        c.rr_runner = _env_float("BRV3_RR_RUNNER", c.rr_runner)
        c.tp1_frac = _env_float("BRV3_TP1_FRAC", c.tp1_frac)
        c.min_rr_tp1 = _env_float("BRV3_MIN_RR_TP1", c.min_rr_tp1)
        c.min_stop_pct = _env_float("BRV3_MIN_STOP_PCT", c.min_stop_pct)
        c.max_stop_pct = _env_float("BRV3_MAX_STOP_PCT", c.max_stop_pct)
        c.be_trigger_rr = _env_float("BRV3_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("BRV3_BE_LOCK_RR", c.be_lock_rr)
        c.trail_atr_mult = _env_float("BRV3_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr = _env_float("BRV3_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.time_stop_bars = _env_int("BRV3_TIME_STOP_BARS", c.time_stop_bars)
        c.cooldown_bars = _env_int("BRV3_COOLDOWN_BARS", c.cooldown_bars)
        self._allow = _env_csv_set("BRV3_ALLOW", c.allow_csv)
        self._deny = _env_csv_set("BRV3_DENY", c.deny_csv)

    def _levels(self, rows: List[list], atr: float) -> List[Tuple[float, float, str]]:
        pivots = find_pivots(rows, left=self.cfg.pivot_left, right=self.cfg.pivot_right)
        levels = cluster_horizontal_levels(
            rows, pivots, atr=atr, tolerance_atr=self.cfg.level_tol_atr,
            min_touches=self.cfg.min_touches, max_levels=self.cfg.max_levels,
        )
        return [(float(lv.price), float(lv.score), str(lv.side_bias)) for lv in levels]

    @staticmethod
    def _nearest_support_below(levels: List[Tuple[float, float, str]], price: float) -> Optional[float]:
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
        entry_need = max(cfg.entry_lookback, cfg.vol_period + cfg.atr_period + 5)
        entry_raw = store.fetch_klines(sym, cfg.entry_tf, entry_need + 2) or []
        structure_rows = _closed_rows_before(structure_raw, signal_ts_ms, cfg.level_lookback)
        entry_history_rows = _closed_rows_before(entry_raw, signal_ts_ms, entry_need)
        if len(structure_rows) < (cfg.pivot_left + cfg.pivot_right + cfg.min_touches + 5):
            self.last_no_signal_reason = "not_enough_closed_structure_bars"
            return None
        if len(entry_history_rows) < max(3, cfg.vol_period if cfg.retest_vol_max_mult > 0 else 3):
            self.last_no_signal_reason = "not_enough_closed_entry_bars"
            return None

        bar_ts = signal_ts_ms
        if self._last_entry_ts is not None and bar_ts == self._last_entry_ts:
            self.last_no_signal_reason = "same_entry_bar"
            return None
        self._last_entry_ts = bar_ts
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None

        atr = _atr(structure_rows, cfg.atr_period)
        if not (math.isfinite(atr) and atr > 0):
            self.last_no_signal_reason = "structure_atr_invalid"
            return None

        cur_open, cur_high, cur_low, cur_close = float(o), float(h), float(l), float(c)
        cur_vol = float(v or 0.0)
        bar_range = max(1e-12, cur_high - cur_low)
        last_structure_close = float(structure_rows[-1][4])

        levels = self._levels(structure_rows, atr)
        if not levels:
            self.last_no_signal_reason = "no_levels"
            return None

        # find a BROKEN support near current price (now acting as resistance)
        band = cfg.retest_band_atr * atr
        touch = cfg.touch_into_atr * atr
        pierce = cfg.max_pierce_atr * atr
        broken: Optional[Tuple[float, float]] = None  # (level, score)
        for lv_price, lv_score, side_bias in levels:
            if side_bias not in ("support", "mixed"):
                continue
            if last_structure_close >= lv_price - cfg.break_confirm_atr * atr:
                continue  # not confirmed broken
            if abs(cur_close - lv_price) > band:
                continue
            if broken is None or lv_score > broken[1]:
                broken = (lv_price, lv_score)
        if broken is None:
            self.last_no_signal_reason = "no_broken_support_near_price"
            return None

        level = broken[0]
        # short retest-hold: poked UP to the broken level, closed back BELOW (rejected)
        touched = cur_high >= level - touch
        not_reclaimed = cur_high <= level + pierce
        held_below = cur_close < level and (cur_high - cur_close) >= cfg.reject_frac * bar_range
        if not (touched and not_reclaimed and held_below):
            self.last_no_signal_reason = "no_breakdown_retest"
            return None
        if abs(cur_close - level) > cfg.max_entry_dist_atr * atr:
            self.last_no_signal_reason = "entry_too_far_from_level"
            return None

        # optional weak-retest volume filter (skip strong/high-volume retests)
        if cfg.retest_vol_max_mult > 0:
            vol_base = _sma([float(r[5]) if len(r) > 5 else 0.0 for r in entry_history_rows], cfg.vol_period)
            if math.isfinite(vol_base) and vol_base > 0 and cur_vol > cfg.retest_vol_max_mult * vol_base:
                self.last_no_signal_reason = "retest_volume_too_high"
                return None

        entry = float(cur_close)
        sl = level + cfg.stop_buffer_atr * atr
        if sl <= entry:
            self.last_no_signal_reason = "sl_at_or_below_entry"
            return None
        risk = sl - entry
        nxt = self._nearest_support_below(levels, entry)
        tp1 = (nxt + cfg.tp_before_level_atr * atr) if nxt else (entry - cfg.min_rr_tp1 * risk)
        tp2 = min(entry - cfg.rr_runner * risk, tp1 - 0.5 * risk)

        stop_pct = risk / max(1e-12, entry)
        if stop_pct < cfg.min_stop_pct:
            self.last_no_signal_reason = f"stop_too_tight_{stop_pct:.4f}"
            return None
        if stop_pct > cfg.max_stop_pct:
            self.last_no_signal_reason = f"stop_too_wide_{stop_pct:.4f}"
            return None
        rr_tp1 = (entry - tp1) / risk
        if rr_tp1 < cfg.min_rr_tp1:
            self.last_no_signal_reason = f"tp1_rr_too_low_{rr_tp1:.2f}"
            return None

        self._cooldown = max(0, cfg.cooldown_bars)
        return TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=sym,
            side="short",
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
            reason=f"breakdown_retest_short@{level:.6g}",
        )
