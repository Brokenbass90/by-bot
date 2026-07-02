"""Research adapter for the shared smart-grid planner.

This is not a live multi-order grid executor.  The live bot does not get a new
risk path from this file.

Purpose:
    make ``--strategies smart_grid`` use the new ``bot.smart_grid.grid_plan``
    instead of the retired archive implementation, so we can run portfolio
    backtests/OOS gates on the new range-only + kill-switch mechanics.

Execution model for backtest:
    - if the shared planner says the market is in a valid range, place one
      limit order at the nearest grid level on the appropriate side;
    - stop is beyond the channel boundary plus kill buffer;
    - target is the channel midpoint;
    - the portfolio engine handles limit fill/expiry via ``entry_order_type``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from bot.smart_grid import grid_plan
from strategies.signals import TradeSignal


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SmartGridConfig:
    lookback: int = 60
    n_levels: int = 6
    kill_buffer_atr: float = 0.75
    min_width_atr: float = 2.0
    require_flat_regime: bool = True
    allow_longs: bool = True
    allow_shorts: bool = True
    limit_validity_bars: int = 3
    cooldown_bars: int = 6
    min_rr: float = 0.60
    min_stop_pct: float = 0.001
    max_stop_pct: float = 0.08


def _load_cfg() -> SmartGridConfig:
    c = SmartGridConfig()
    c.lookback = _env_int("SG_LOOKBACK", _env_int("SG_LOOKBACK_BARS", c.lookback))
    c.n_levels = _env_int("SG_LEVELS", c.n_levels)
    c.kill_buffer_atr = _env_float("SG_KILL_BUFFER_ATR", c.kill_buffer_atr)
    c.min_width_atr = _env_float("SG_MIN_WIDTH_ATR", c.min_width_atr)
    c.require_flat_regime = _env_bool("SG_REQUIRE_FLAT_REGIME", c.require_flat_regime)
    c.allow_longs = _env_bool("SG_ALLOW_LONGS", c.allow_longs)
    c.allow_shorts = _env_bool("SG_ALLOW_SHORTS", c.allow_shorts)
    c.limit_validity_bars = _env_int("SG_LIMIT_VALIDITY_BARS", c.limit_validity_bars)
    c.cooldown_bars = _env_int("SG_COOLDOWN_BARS", c.cooldown_bars)
    c.min_rr = _env_float("SG_MIN_RR", c.min_rr)
    c.min_stop_pct = _env_float("SG_MIN_STOP_PCT", c.min_stop_pct)
    c.max_stop_pct = _env_float("SG_MAX_STOP_PCT", c.max_stop_pct)
    return c


class SmartGridStrategy:
    """Thin portfolio-backtest strategy wrapper around ``bot.smart_grid``."""

    def __init__(self, cfg: Optional[SmartGridConfig] = None):
        self.cfg = cfg or _load_cfg()
        self.rows: List[List[float]] = []
        self._cooldown = 0
        self._last_ts: Optional[int] = None
        self.last_no_signal_reason = ""

    def _no(self, reason: str) -> None:
        self.last_no_signal_reason = reason

    def _build(self, store, side: str, entry: float, sl: float, tp: float, reason: str) -> Optional[TradeSignal]:
        c = self.cfg
        risk = (entry - sl) if side == "long" else (sl - entry)
        reward = (tp - entry) if side == "long" else (entry - tp)
        if risk <= 0 or reward <= 0:
            self._no("invalid_geometry")
            return None
        rr = reward / max(1e-12, risk)
        if rr < c.min_rr:
            self._no(f"rr_low_{rr:.2f}")
            return None
        stop_pct = risk / max(1e-12, entry)
        if stop_pct < c.min_stop_pct:
            self._no("stop_too_tight")
            return None
        if stop_pct > c.max_stop_pct:
            self._no("stop_too_wide")
            return None

        sig = TradeSignal(
            strategy="smart_grid",
            symbol=getattr(store, "symbol", ""),
            side=side,
            entry=float(entry),
            sl=float(sl),
            tp=float(tp),
            tps=[float(tp)],
            tp_fracs=[1.0],
            reason=reason,
        )
        if not sig.validate():
            self._no("signal_invalid")
            return None
        sig.entry_order_type = "limit"
        sig.limit_validity_bars = max(1, int(c.limit_validity_bars))
        return sig

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0):
        # Protect against duplicate calls on the same bar in live/replay loops.
        ts_i = int(ts_ms)
        if self._last_ts == ts_i:
            self._no("duplicate_bar")
            return None
        self._last_ts = ts_i

        self.rows.append([float(ts_ms), float(o), float(h), float(l), float(c), float(v or 0.0)])
        if len(self.rows) > max(300, self.cfg.lookback * 4):
            self.rows = self.rows[-max(300, self.cfg.lookback * 4):]

        if self._cooldown > 0:
            self._cooldown -= 1
            self._no("cooldown")
            return None

        g = grid_plan(
            self.rows,
            lookback=self.cfg.lookback,
            n_levels=self.cfg.n_levels,
            kill_buffer_atr=self.cfg.kill_buffer_atr,
            min_width_atr=self.cfg.min_width_atr,
            require_flat_regime=self.cfg.require_flat_regime,
        )
        if not g.active:
            self._no(g.reason or "grid_inactive")
            return None

        price = float(c)
        mid = (g.lower + g.upper) / 2.0
        atr_est = (g.upper - g.lower) / max(1e-12, float(g.extra.get("width_atr", 1.0) or 1.0))

        # One-order proxy: below midpoint we bid the nearest buy level; above
        # midpoint we offer the nearest sell level.  Full multi-order execution
        # belongs in a dedicated executor, not inside TradeSignal.
        if price <= mid and self.cfg.allow_longs and g.buy_levels:
            entry = max(g.buy_levels)
            sl = g.lower - self.cfg.kill_buffer_atr * atr_est
            tp = mid
            sig = self._build(
                store,
                "long",
                entry,
                sl,
                tp,
                f"smart_grid_long regime={g.regime} lower={g.lower:.6f} upper={g.upper:.6f} width_atr={g.extra.get('width_atr'):.2f}",
            )
        elif price >= mid and self.cfg.allow_shorts and g.sell_levels:
            entry = min(g.sell_levels)
            sl = g.upper + self.cfg.kill_buffer_atr * atr_est
            tp = mid
            sig = self._build(
                store,
                "short",
                entry,
                sl,
                tp,
                f"smart_grid_short regime={g.regime} lower={g.lower:.6f} upper={g.upper:.6f} width_atr={g.extra.get('width_atr'):.2f}",
            )
        else:
            self._no("no_side_level")
            return None

        if sig is None:
            return None
        self._cooldown = max(0, int(self.cfg.cooldown_bars))
        return sig

