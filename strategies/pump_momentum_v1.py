#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pump_momentum_v1 — Long-only pump momentum rider.

Strategy concept
----------------
Detects when a symbol is experiencing an abnormal upward impulse
(price up >= MIN_PUMP_PCT from recent low within LOOKBACK_BARS, supported
by a volume spike), and enters a LONG position at market to ride the
remaining momentum.  The trade is managed with an ATR-based trailing stop
that arms after the price moves +TRAIL_ACTIVATE_RR risk-multiples above
entry.  A hard time-stop (TIME_STOP_BARS) prevents open exposure when a
pump dies quietly.

Entry conditions (all required on the trigger bar):
  1. pump_pct  = (close - min_close_in_lookback) / min_close_in_lookback
                 >= PM_MIN_PUMP_PCT  (default 8 %)
  2. pump_pct  <= PM_MAX_PUMP_PCT    (default 50 %) — skip if already ran
  3. vol_spike = current_volume / SMA(volume, PM_VOL_PERIOD)
                 >= PM_VOL_MULT      (default 2.5×) — volume confirmation
  4. Last closed bar is bullish: close > open (disabled by PM_REQUIRE_BULLISH=0)
  5. Body fraction >= PM_MIN_BODY_FRAC (default 0.30) — no doji on trigger bar
  6. Stop loss within PM_MIN_STOP_PCT–PM_MAX_STOP_PCT range

Exit plan:
  - Stop loss    : entry − PM_SL_ATR_MULT × ATR(14)
  - Take profit  : entry + PM_RR × risk
  - Trailing stop: ATR-based, arms after +PM_TRAIL_ACTIVATE_RR × risk
  - Time stop    : PM_TIME_STOP_BARS bars (default 96 = 8 h on 5 m)
  - Cooldown     : PM_COOLDOWN_BARS bars after any signal (default 24)

Environment variables (prefix PM_):
  PM_INTERVAL_MIN          int   bar size in minutes         [5]
  PM_LOOKBACK_BARS         int   pump detection window        [12]
  PM_MIN_PUMP_PCT          float minimum pump pct (decimal)  [0.08]
  PM_MAX_PUMP_PCT          float skip if pumped more          [0.50]
  PM_VOL_MULT              float volume spike multiplier      [2.5]
  PM_VOL_PERIOD            int   volume SMA baseline period   [20]
  PM_REQUIRE_BULLISH       bool  trigger bar must be bullish  [1]
  PM_MIN_BODY_FRAC         float min body/range on entry bar  [0.30]
  PM_ATR_PERIOD            int   ATR lookback                 [14]
  PM_SL_ATR_MULT           float stop loss width in ATR       [2.0]
  PM_RR                    float risk-reward for TP           [2.0]
  PM_MIN_STOP_PCT          float reject if SL% < this         [0.02]
  PM_MAX_STOP_PCT          float reject if SL% > this         [0.12]
  PM_TRAIL_ATR_MULT        float trailing stop width in ATR   [1.8]
  PM_TRAIL_ACTIVATE_RR     float activate trailing at +N×R    [1.0]
  PM_TIME_STOP_BARS        int   hard time stop in 5m bars     [96]
  PM_COOLDOWN_BARS         int   bars between signals          [24]
  PM_SYMBOL_ALLOWLIST      str   CSV allowlist (empty=all)    [""]
  PM_SYMBOL_DENYLIST       str   CSV denylist                  [""]
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _pm_ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _pm_sma(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    tail = values[-period:] if len(values) >= period else values
    return sum(tail) / len(tail)


def _pm_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    """Average True Range over the last `period` completed bars."""
    if len(closes) < 2:
        return float("nan")
    trs: List[float] = []
    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return float("nan")
    tail = trs[-period:] if len(trs) >= period else trs
    return sum(tail) / len(tail)


def _pm_env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _pm_env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _pm_env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _pm_env_csv_set(name: str) -> Set[str]:
    raw = os.getenv(name, "") or ""
    return {p.strip().upper() for p in str(raw).split(",") if p.strip()}


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class PumpMomentumConfig:
    # Bar timeframe
    interval_min: int = 5

    # Pump detection
    lookback_bars: int = 12          # 12 × 5 m = 60 min window
    min_pump_pct: float = 0.08       # 8 % rise from recent low
    max_pump_pct: float = 0.50       # skip if already +50 % (too late)

    # Volume confirmation
    vol_mult: float = 2.5            # volume must be 2.5× SMA baseline
    vol_period: int = 20             # SMA baseline period

    # Entry bar quality
    require_bullish: bool = True     # trigger bar close > open
    min_body_frac: float = 0.30      # body >= 30 % of bar range

    # ATR / risk
    atr_period: int = 14
    sl_atr_mult: float = 2.0         # SL = entry − sl_atr × ATR
    rr: float = 2.0                  # TP = entry + rr × risk
    min_stop_pct: float = 0.02       # minimum stop as fraction of entry
    max_stop_pct: float = 0.12       # maximum stop as fraction of entry

    # Trailing stop
    trail_atr_mult: float = 1.8      # trailing stop width in ATR (0 = disabled)
    trail_activate_rr: float = 1.0   # arm trailing after +1×R profit

    # Time management
    time_stop_bars: int = 96         # hard time stop: 96 × 5 m = 8 h
    cooldown_bars: int = 24          # bars between new signals per symbol

    # Symbol filter
    symbol_allowlist: str = ""
    symbol_denylist: str = ""


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------

class PumpMomentumV1Strategy:
    """
    Long-only pump momentum rider.

    Call ``maybe_signal(symbol, ts_ms, o, h, l, c, v)`` on every completed bar.
    Maintains per-symbol rolling state (closes, highs, lows, volumes, cooldown).

    Returns a TradeSignal when a pump + continuation bar is detected,
    or None otherwise.
    """

    STRATEGY_NAME = "pump_momentum_v1"

    def __init__(self, cfg: Optional[PumpMomentumConfig] = None) -> None:
        self.cfg = cfg or PumpMomentumConfig()

        # Apply env overrides
        c = self.cfg
        c.interval_min       = _pm_env_int  ("PM_INTERVAL_MIN",      c.interval_min)
        c.lookback_bars      = _pm_env_int  ("PM_LOOKBACK_BARS",      c.lookback_bars)
        c.min_pump_pct       = _pm_env_float("PM_MIN_PUMP_PCT",       c.min_pump_pct)
        c.max_pump_pct       = _pm_env_float("PM_MAX_PUMP_PCT",       c.max_pump_pct)
        c.vol_mult           = _pm_env_float("PM_VOL_MULT",           c.vol_mult)
        c.vol_period         = _pm_env_int  ("PM_VOL_PERIOD",         c.vol_period)
        c.require_bullish    = _pm_env_bool ("PM_REQUIRE_BULLISH",    c.require_bullish)
        c.min_body_frac      = _pm_env_float("PM_MIN_BODY_FRAC",      c.min_body_frac)
        c.atr_period         = _pm_env_int  ("PM_ATR_PERIOD",         c.atr_period)
        c.sl_atr_mult        = _pm_env_float("PM_SL_ATR_MULT",        c.sl_atr_mult)
        c.rr                 = _pm_env_float("PM_RR",                 c.rr)
        c.min_stop_pct       = _pm_env_float("PM_MIN_STOP_PCT",       c.min_stop_pct)
        c.max_stop_pct       = _pm_env_float("PM_MAX_STOP_PCT",       c.max_stop_pct)
        c.trail_atr_mult     = _pm_env_float("PM_TRAIL_ATR_MULT",     c.trail_atr_mult)
        c.trail_activate_rr  = _pm_env_float("PM_TRAIL_ACTIVATE_RR",  c.trail_activate_rr)
        c.time_stop_bars     = _pm_env_int  ("PM_TIME_STOP_BARS",     c.time_stop_bars)
        c.cooldown_bars      = _pm_env_int  ("PM_COOLDOWN_BARS",      c.cooldown_bars)
        c.symbol_allowlist   = os.getenv    ("PM_SYMBOL_ALLOWLIST",   c.symbol_allowlist) or ""
        c.symbol_denylist    = os.getenv    ("PM_SYMBOL_DENYLIST",    c.symbol_denylist)  or ""

        self._allow: Set[str] = _pm_env_csv_set("PM_SYMBOL_ALLOWLIST")
        self._deny:  Set[str] = _pm_env_csv_set("PM_SYMBOL_DENYLIST")

        # Per-symbol rolling history  {symbol: list}
        self._closes:    Dict[str, List[float]] = {}
        self._highs:     Dict[str, List[float]] = {}
        self._lows:      Dict[str, List[float]] = {}
        self._volumes:   Dict[str, List[float]] = {}
        self._cooldown:  Dict[str, int]         = {}

        # Last skip reason (for diagnostics / autoresearch)
        self.last_no_signal_reason: str = ""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def maybe_signal(
        self,
        symbol: str,
        ts_ms: int,        # unused – kept for interface compatibility
        o: float,
        h: float,
        l: float,
        c: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        """Process one completed bar and return a signal if conditions met."""
        _ = ts_ms
        sym = str(symbol).upper()

        # Symbol filter
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None

        # Update rolling history
        if sym not in self._closes:
            self._closes[sym]  = []
            self._highs[sym]   = []
            self._lows[sym]    = []
            self._volumes[sym] = []
            self._cooldown[sym] = 0

        self._closes[sym].append(c)
        self._highs[sym].append(h)
        self._lows[sym].append(l)
        self._volumes[sym].append(v)

        # Keep only what we need (avoid unbounded growth)
        max_hist = self.cfg.lookback_bars + self.cfg.vol_period + self.cfg.atr_period + 10
        if len(self._closes[sym]) > max_hist:
            trim = len(self._closes[sym]) - max_hist
            self._closes[sym]  = self._closes[sym][trim:]
            self._highs[sym]   = self._highs[sym][trim:]
            self._lows[sym]    = self._lows[sym][trim:]
            self._volumes[sym] = self._volumes[sym][trim:]

        # Cooldown
        if self._cooldown[sym] > 0:
            self._cooldown[sym] -= 1
            self.last_no_signal_reason = "cooldown"
            return None

        return self._evaluate(sym, o, h, l, c, v)

    # ------------------------------------------------------------------
    # Core signal evaluation
    # ------------------------------------------------------------------

    def _evaluate(
        self, sym: str, o: float, h: float, l: float, c: float, v: float
    ) -> Optional[TradeSignal]:
        cfg   = self.cfg
        cls   = self._closes[sym]
        highs = self._highs[sym]
        lows  = self._lows[sym]
        vols  = self._volumes[sym]

        min_needed = cfg.lookback_bars + cfg.atr_period + 2
        if len(cls) < min_needed:
            self.last_no_signal_reason = "insufficient_history"
            return None

        # ------------------------------------------------------------------
        # 1. Pump detection: current close vs lowest close in lookback window
        # ------------------------------------------------------------------
        window_cls = cls[-(cfg.lookback_bars + 1):-1]   # exclude current bar
        recent_low = min(window_cls)
        if recent_low <= 0:
            self.last_no_signal_reason = "zero_price"
            return None

        pump_pct = (c - recent_low) / recent_low

        if pump_pct < cfg.min_pump_pct:
            self.last_no_signal_reason = f"pump_too_small:{pump_pct*100:.1f}%"
            return None

        if pump_pct > cfg.max_pump_pct:
            self.last_no_signal_reason = f"pump_too_large:{pump_pct*100:.1f}%"
            return None

        # ------------------------------------------------------------------
        # 2. Volume confirmation
        # ------------------------------------------------------------------
        if cfg.vol_mult > 0 and len(vols) >= cfg.vol_period + 1:
            baseline_vol = _pm_sma(vols[-(cfg.vol_period + 1):-1], cfg.vol_period)
            if baseline_vol > 0 and v < cfg.vol_mult * baseline_vol:
                self.last_no_signal_reason = (
                    f"vol_weak:{v/baseline_vol:.2f}x<{cfg.vol_mult:.1f}x"
                )
                return None

        # ------------------------------------------------------------------
        # 3. Entry bar quality: bullish + body fraction
        # ------------------------------------------------------------------
        if cfg.require_bullish and c <= o:
            self.last_no_signal_reason = "bar_not_bullish"
            return None

        bar_range = h - l
        if bar_range > 0 and cfg.min_body_frac > 0:
            body = abs(c - o)
            if body / bar_range < cfg.min_body_frac:
                self.last_no_signal_reason = f"body_too_small:{body/bar_range:.2f}"
                return None

        # ------------------------------------------------------------------
        # 4. ATR-based stop / risk computation
        # ------------------------------------------------------------------
        atr = _pm_atr(highs, lows, cls, cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "atr_invalid"
            return None

        entry = c
        sl    = entry - cfg.sl_atr_mult * atr
        if sl <= 0:
            self.last_no_signal_reason = "sl_below_zero"
            return None

        risk  = entry - sl
        tp    = entry + cfg.rr * risk

        # Validate stop size
        stop_pct = risk / entry
        if stop_pct < cfg.min_stop_pct:
            self.last_no_signal_reason = f"stop_too_tight:{stop_pct:.3f}"
            return None
        if stop_pct > cfg.max_stop_pct:
            self.last_no_signal_reason = f"stop_too_wide:{stop_pct:.3f}"
            return None

        # ------------------------------------------------------------------
        # 5. Build TradeSignal with trailing stop
        # ------------------------------------------------------------------
        self._cooldown[sym] = cfg.cooldown_bars
        self.last_no_signal_reason = ""

        sig = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=sym,
            side="long",
            entry=entry,
            sl=sl,
            tp=tp,
            trailing_atr_mult=cfg.trail_atr_mult,
            trailing_atr_period=cfg.atr_period,
            trail_activate_rr=cfg.trail_activate_rr,
            time_stop_bars=cfg.time_stop_bars,
            reason=f"pump:{pump_pct*100:.1f}%|vol:{v/(max(1e-9, _pm_sma(vols[-(cfg.vol_period+1):-1], cfg.vol_period))):.1f}x",
        )
        return sig if sig.validate() else None
