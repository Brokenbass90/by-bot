"""
inplay_retest_v3 — the owner's trading approach, implemented correctly.

Why this exists (vs IVB1 / inplay_breakout):
  The old logic broke out over a ROLLING HIGH (24-bar max), then waited for a
  full RECLAIM bar to close back ABOVE the level + a buffer before entering.
  That meant: (a) the "level" was a noise extreme, not a real S/R; (b) entry
  happened AFTER the bounce, chasing the top of the move; (c) the stop floated
  far from entry, giving poor RR; (d) a wall of stacked filters strangled
  frequency -> 0 PASS.

What this does instead (the owner's described system):
  1. Detect REAL levels: horizontal S/R from clustered pivots (>=N touches,
     via bot.chart_geometry) AND a sloped trendline (regression channel).
  2. Wait for price to RETEST a level and HOLD it (a rejection bar at the
     level), then enter ON the retest — near the level, not after a reclaim.
  3. Tight stop just BEYOND the level (fixed small buffer), so RR is good.
  4. Take profit BEFORE the next opposing level ("закрытие перед уровнем"),
     then leave a runner for the continuation/impulse breakout.
  5. Minimal filters: strong level + retest-hold + volume. That's it.

A "broken level retested" (пробой с ретестом) falls out naturally: a level the
price now sits ABOVE and comes back to test from above is treated as support
(long); a level price sits BELOW and tests from below is resistance (short).

Additive / env-configurable. Same contract as the other strategies:
  Strategy(cfg).maybe_signal(store, ts_ms, o, h, l, c, v) -> Optional[TradeSignal]
  store.symbol, store.fetch_klines(symbol, interval, limit) -> [[ts,o,h,l,c,v], ...]
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .signals import TradeSignal

from bot.chart_geometry import (
    find_pivots,
    cluster_horizontal_levels,
    regression_channel,
)


# ---------- env helpers ----------
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


def _atr(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return sum(trs) / float(period) if trs else float("nan")


def _sma(values: List[float], period: int) -> float:
    tail = values[-period:] if len(values) >= period else values
    return (sum(tail) / float(len(tail))) if tail else float("nan")


# ---------- config ----------
@dataclass
class InplayRetestV3Config:
    # timeframes
    structure_tf: str = "60"     # levels are read on this TF (1h by default)
    entry_tf: str = "15"         # the retest-trigger bar TF (younger TF)
    level_lookback: int = 240    # structure bars used to map levels
    entry_lookback: int = 80     # entry bars fetched

    # level detection (REAL S/R, not rolling high)
    pivot_left: int = 2
    pivot_right: int = 2
    min_touches: int = 2         # a level must have been tested at least this many times
    level_tol_atr: float = 0.35  # pivot clustering tolerance (structure ATR)
    max_levels: int = 10

    # sloped trendline (наклонка)
    use_sloped: bool = True
    channel_lookback: int = 72
    channel_min_r2: float = 0.35

    # retest / hold trigger (вход НА ретесте, не после реклейма)
    atr_period: int = 14
    retest_band_atr: float = 0.6   # price must be within this many ATR of the level to count as "at" it
    touch_into_atr: float = 0.25   # bar must dip/poke into the level by up to this (came to test it)
    max_pierce_atr: float = 0.45   # but must not blow through the level by more than this
    reject_frac: float = 0.45      # close must sit this far into the bar away from the level (rejection wick)

    # volume confirmation (объёмный вход) — single confirmation, set 0 to disable
    vol_period: int = 20
    vol_mult: float = 1.2

    # stop / targets
    stop_buffer_atr: float = 0.35  # tight stop just beyond the level
    tp_before_level_atr: float = 0.25  # take profit this far BEFORE the next opposing level
    rr_runner: float = 2.5         # runner target in R if no further level caps it
    tp1_frac: float = 0.6          # close 60% at tp1 (before the level), runner = remainder
    min_rr_tp1: float = 1.1        # skip if tp1 doesn't even clear this RR (level too close)
    min_stop_pct: float = 0.0015
    max_stop_pct: float = 0.06

    # exit management
    be_trigger_rr: float = 1.0     # move to breakeven after +1R (protect the runner)
    be_lock_rr: float = 0.0
    trail_atr_mult: float = 0.0
    trail_activate_rr: float = 0.0
    time_stop_bars: int = 0

    # direction + frequency
    allow_long: bool = True
    allow_short: bool = True
    cooldown_bars: int = 3

    # optional, OFF by default (the whole point is to NOT over-filter)
    use_regime: bool = False

    allow_csv: str = ""
    deny_csv: str = ""


class InplayRetestV3Strategy:
    STRATEGY_NAME = "inplay_retest_v3"

    def __init__(self, cfg: Optional[InplayRetestV3Config] = None):
        self.cfg = cfg or InplayRetestV3Config()
        self.last_no_signal_reason = ""
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._allow: set[str] = set()
        self._deny: set[str] = set()
        self._load_env()

    # config is read from env so the live router can tune without code changes
    def _load_env(self) -> None:
        c = self.cfg
        c.structure_tf = os.getenv("IRV3_STRUCTURE_TF", c.structure_tf)
        c.entry_tf = os.getenv("IRV3_ENTRY_TF", c.entry_tf)
        c.level_lookback = _env_int("IRV3_LEVEL_LOOKBACK", c.level_lookback)
        c.entry_lookback = _env_int("IRV3_ENTRY_LOOKBACK", c.entry_lookback)
        c.pivot_left = _env_int("IRV3_PIVOT_LEFT", c.pivot_left)
        c.pivot_right = _env_int("IRV3_PIVOT_RIGHT", c.pivot_right)
        c.min_touches = _env_int("IRV3_MIN_TOUCHES", c.min_touches)
        c.level_tol_atr = _env_float("IRV3_LEVEL_TOL_ATR", c.level_tol_atr)
        c.max_levels = _env_int("IRV3_MAX_LEVELS", c.max_levels)
        c.use_sloped = _env_bool("IRV3_USE_SLOPED", c.use_sloped)
        c.channel_lookback = _env_int("IRV3_CHANNEL_LOOKBACK", c.channel_lookback)
        c.channel_min_r2 = _env_float("IRV3_CHANNEL_MIN_R2", c.channel_min_r2)
        c.atr_period = _env_int("IRV3_ATR_PERIOD", c.atr_period)
        c.retest_band_atr = _env_float("IRV3_RETEST_BAND_ATR", c.retest_band_atr)
        c.touch_into_atr = _env_float("IRV3_TOUCH_INTO_ATR", c.touch_into_atr)
        c.max_pierce_atr = _env_float("IRV3_MAX_PIERCE_ATR", c.max_pierce_atr)
        c.reject_frac = _env_float("IRV3_REJECT_FRAC", c.reject_frac)
        c.vol_period = _env_int("IRV3_VOL_PERIOD", c.vol_period)
        c.vol_mult = _env_float("IRV3_VOL_MULT", c.vol_mult)
        c.stop_buffer_atr = _env_float("IRV3_STOP_BUFFER_ATR", c.stop_buffer_atr)
        c.tp_before_level_atr = _env_float("IRV3_TP_BEFORE_LEVEL_ATR", c.tp_before_level_atr)
        c.rr_runner = _env_float("IRV3_RR_RUNNER", c.rr_runner)
        c.tp1_frac = _env_float("IRV3_TP1_FRAC", c.tp1_frac)
        c.min_rr_tp1 = _env_float("IRV3_MIN_RR_TP1", c.min_rr_tp1)
        c.min_stop_pct = _env_float("IRV3_MIN_STOP_PCT", c.min_stop_pct)
        c.max_stop_pct = _env_float("IRV3_MAX_STOP_PCT", c.max_stop_pct)
        c.be_trigger_rr = _env_float("IRV3_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("IRV3_BE_LOCK_RR", c.be_lock_rr)
        c.trail_atr_mult = _env_float("IRV3_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr = _env_float("IRV3_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.time_stop_bars = _env_int("IRV3_TIME_STOP_BARS", c.time_stop_bars)
        c.allow_long = _env_bool("IRV3_ALLOW_LONG", c.allow_long)
        c.allow_short = _env_bool("IRV3_ALLOW_SHORT", c.allow_short)
        c.cooldown_bars = _env_int("IRV3_COOLDOWN_BARS", c.cooldown_bars)
        c.use_regime = _env_bool("IRV3_USE_REGIME", c.use_regime)
        self._allow = _env_csv_set("IRV3_ALLOW", c.allow_csv)
        self._deny = _env_csv_set("IRV3_DENY", c.deny_csv)

    # ---------- level mapping ----------
    def _candidate_levels(self, rows: List[list], structure_atr: float) -> List[Tuple[float, float, str]]:
        """Return [(price, score, kind), ...]; kind in {support, resistance, mixed, sloped_up, sloped_dn}."""
        out: List[Tuple[float, float, str]] = []
        pivots = find_pivots(rows, left=self.cfg.pivot_left, right=self.cfg.pivot_right)
        levels = cluster_horizontal_levels(
            rows, pivots, atr=structure_atr,
            tolerance_atr=self.cfg.level_tol_atr,
            min_touches=self.cfg.min_touches,
            max_levels=self.cfg.max_levels,
        )
        for lv in levels:
            out.append((float(lv.price), float(lv.score), str(lv.side_bias)))
        if self.cfg.use_sloped:
            ch = regression_channel(rows, lookback=self.cfg.channel_lookback)
            if ch and float(ch.get("r2", 0.0)) >= self.cfg.channel_min_r2:
                slope = float(ch.get("slope_pct_per_bar", 0.0))
                # the lower band acts as dynamic support, upper band as dynamic resistance
                out.append((float(ch["lower"]), float(ch["r2"]) * float(self.cfg.min_touches),
                            "sloped_up" if slope >= 0 else "sloped_dn"))
                out.append((float(ch["upper"]), float(ch["r2"]) * float(self.cfg.min_touches),
                            "sloped_up" if slope >= 0 else "sloped_dn"))
        return out

    @staticmethod
    def _nearest_opposing(levels: List[Tuple[float, float, str]], price: float, side: str) -> Optional[float]:
        if side == "long":
            above = [p for p, _, _ in levels if p > price]
            return min(above) if above else None
        below = [p for p, _, _ in levels if p < price]
        return max(below) if below else None

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (ts_ms, o, h, l, c, v)
        self.last_no_signal_reason = ""
        self._load_env()
        cfg = self.cfg

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_not_allowed"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_denied"
            return None

        structure_rows = store.fetch_klines(sym, cfg.structure_tf, cfg.level_lookback) or []
        entry_rows = store.fetch_klines(sym, cfg.entry_tf,
                                        max(cfg.entry_lookback, cfg.vol_period + cfg.atr_period + 5)) or []
        if len(structure_rows) < (cfg.pivot_left + cfg.pivot_right + cfg.min_touches + 5):
            self.last_no_signal_reason = "not_enough_structure_bars"
            return None
        if len(entry_rows) < (cfg.atr_period + 3):
            self.last_no_signal_reason = "not_enough_entry_bars"
            return None

        bar_ts = int(float(entry_rows[-1][0]))
        if self._last_entry_ts is not None and bar_ts == self._last_entry_ts:
            self.last_no_signal_reason = "same_entry_bar"
            return None
        self._last_entry_ts = bar_ts
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None

        structure_atr = _atr(structure_rows, cfg.atr_period)
        if not (math.isfinite(structure_atr) and structure_atr > 0):
            self.last_no_signal_reason = "structure_atr_invalid"
            return None
        # Level geometry (proximity, stop buffer, tp offset) is measured in the
        # LEVEL's own scale, i.e. the structure-TF ATR — not the quiet entry feed.
        atr = structure_atr

        cur_open = float(entry_rows[-1][1])
        cur_high = float(entry_rows[-1][2])
        cur_low = float(entry_rows[-1][3])
        cur_close = float(entry_rows[-1][4])
        cur_vol = float(entry_rows[-1][5]) if len(entry_rows[-1]) > 5 else 0.0
        bar_range = max(1e-12, cur_high - cur_low)
        vols = [float(r[5]) if len(r) > 5 else 0.0 for r in entry_rows]
        vol_base = _sma(vols[:-1], cfg.vol_period)

        if cfg.vol_mult > 0:
            if not (math.isfinite(vol_base) and vol_base > 0):
                self.last_no_signal_reason = "volume_baseline_invalid"
                return None
            if cur_vol < cfg.vol_mult * vol_base:
                self.last_no_signal_reason = "no_volume"
                return None

        levels = self._candidate_levels(structure_rows, structure_atr)
        if not levels:
            self.last_no_signal_reason = "no_levels"
            return None

        price = cur_close
        band = cfg.retest_band_atr * atr
        touch = cfg.touch_into_atr * atr
        pierce = cfg.max_pierce_atr * atr

        best: Optional[Tuple[float, str, float]] = None  # (level, side, score)
        for lv_price, lv_score, _kind in levels:
            if abs(price - lv_price) > band:
                continue
            # LONG: price sits above the level, bar dipped to test it and CLOSED back above (held)
            if cfg.allow_long and price > lv_price:
                touched = cur_low <= lv_price + touch
                not_broken = cur_low >= lv_price - pierce
                held = cur_close > lv_price and (cur_close - cur_low) >= cfg.reject_frac * bar_range
                if touched and not_broken and held:
                    if best is None or lv_score > best[2]:
                        best = (lv_price, "long", lv_score)
            # SHORT: price sits below the level, bar poked up to test it and CLOSED back below (rejected)
            if cfg.allow_short and price < lv_price:
                touched = cur_high >= lv_price - touch
                not_broken = cur_high <= lv_price + pierce
                held = cur_close < lv_price and (cur_high - cur_close) >= cfg.reject_frac * bar_range
                if touched and not_broken and held:
                    if best is None or lv_score > best[2]:
                        best = (lv_price, "short", lv_score)

        if best is None:
            self.last_no_signal_reason = "no_retest_hold"
            return None

        level, side, _score = best
        if cfg.use_regime and not self._regime_ok(structure_rows, side):
            self.last_no_signal_reason = "regime_block"
            return None

        entry = float(cur_close)
        if side == "long":
            sl = level - cfg.stop_buffer_atr * atr
            if sl >= entry:
                self.last_no_signal_reason = "sl_at_or_above_entry"
                return None
            risk = entry - sl
            nxt = self._nearest_opposing(levels, entry, "long")
            tp1 = (nxt - cfg.tp_before_level_atr * atr) if nxt else (entry + cfg.min_rr_tp1 * risk)
            tp2 = max(entry + cfg.rr_runner * risk, tp1 + 0.5 * risk)
        else:
            sl = level + cfg.stop_buffer_atr * atr
            if sl <= entry:
                self.last_no_signal_reason = "sl_at_or_below_entry"
                return None
            risk = sl - entry
            nxt = self._nearest_opposing(levels, entry, "short")
            tp1 = (nxt + cfg.tp_before_level_atr * atr) if nxt else (entry - cfg.min_rr_tp1 * risk)
            tp2 = min(entry - cfg.rr_runner * risk, tp1 - 0.5 * risk)

        stop_pct = risk / max(1e-12, entry)
        if stop_pct < cfg.min_stop_pct:
            self.last_no_signal_reason = f"stop_too_tight_{stop_pct:.4f}"
            return None
        if stop_pct > cfg.max_stop_pct:
            self.last_no_signal_reason = f"stop_too_wide_{stop_pct:.4f}"
            return None

        # RR guard: tp1 must clear min_rr_tp1, else the level is too close — skip
        rr_tp1 = (tp1 - entry) / risk if side == "long" else (entry - tp1) / risk
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
            reason=f"retest_hold_{side}@{level:.6g}",
        )

    # optional, OFF by default: only allow trades aligned with the structure slope
    def _regime_ok(self, structure_rows: List[list], side: str) -> bool:
        ch = regression_channel(structure_rows, lookback=self.cfg.channel_lookback)
        if not ch:
            return True
        slope = float(ch.get("slope_pct_per_bar", 0.0))
        if side == "long":
            return slope >= -0.02
        return slope <= 0.02
