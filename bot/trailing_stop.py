"""Trailing-stop engine — let winners run (breakeven + ATR/Chandelier trail).

Big R comes from letting winners run, not from tight fixed TPs. This engine, usable
by elder and every sleeve, manages an open position's stop:
  * BREAKEVEN — once price reaches `be_trigger_rr` R, move stop to entry (+offset);
  * TRAIL     — once `trail_activate_rr` R, trail a Chandelier stop
                (extreme_high - trail_atr_mult*ATR for long; mirror for short);
  * one-way   — the stop only ever moves in the favorable direction (never loosens);
  * EXIT      — signals exit when the bar trades through the current stop.

Stateless per-update (feed it the running position state each bar). Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class PositionTrail:
    side: str                    # "long" | "short"
    entry: float
    stop: float                  # current stop (starts at initial stop)
    risk: float                  # initial risk per unit = |entry - initial_stop|
    extreme: float               # highest high (long) / lowest low (short) since entry
    be_done: bool = False
    trail_on: bool = False


def new_trail(side: str, entry: float, initial_stop: float) -> PositionTrail:
    return PositionTrail(side=side, entry=entry, stop=initial_stop,
                         risk=abs(entry - initial_stop), extreme=entry)


def update_trail(
    pt: PositionTrail,
    high: float,
    low: float,
    *,
    atr: float,
    be_trigger_rr: float = 1.0,
    be_offset_r: float = 0.05,
    trail_activate_rr: float = 1.5,
    trail_atr_mult: float = 2.5,
) -> Dict[str, Any]:
    """Advance the trail one bar; returns {stop, moved_be, trail_active, exit, exit_price, reason}."""
    long = pt.side == "long"
    if pt.risk <= 0:
        return {"stop": pt.stop, "moved_be": False, "trail_active": pt.trail_on,
                "exit": False, "exit_price": float("nan"), "reason": "bad_risk"}

    # 1) exit against the stop that was active DURING this bar (before any raise)
    if (low <= pt.stop) if long else (high >= pt.stop):
        return {"stop": pt.stop, "moved_be": False, "trail_active": pt.trail_on,
                "exit": True, "exit_price": pt.stop,
                "reason": "trailed" if pt.trail_on else ("breakeven" if pt.be_done else "initial")}

    # 2) update favorable extreme and raise the stop for SUBSEQUENT bars
    # update favorable extreme
    pt.extreme = max(pt.extreme, high) if long else min(pt.extreme, low)
    fav_r = ((pt.extreme - pt.entry) if long else (pt.entry - pt.extreme)) / pt.risk

    moved_be = False
    # breakeven
    if not pt.be_done and fav_r >= be_trigger_rr:
        be_stop = pt.entry + be_offset_r * pt.risk if long else pt.entry - be_offset_r * pt.risk
        if (long and be_stop > pt.stop) or (not long and be_stop < pt.stop):
            pt.stop = be_stop
            moved_be = True
        pt.be_done = True

    # chandelier trail
    if fav_r >= trail_activate_rr and atr == atr and atr > 0:
        pt.trail_on = True
        trail_stop = (pt.extreme - trail_atr_mult * atr) if long else (pt.extreme + trail_atr_mult * atr)
        if (long and trail_stop > pt.stop) or (not long and trail_stop < pt.stop):
            pt.stop = trail_stop            # one-way tighten only

    return {"stop": pt.stop, "moved_be": moved_be, "trail_active": pt.trail_on,
            "exit": False, "exit_price": float("nan"),
            "reason": "trailed" if pt.trail_on else ("breakeven" if pt.be_done else "initial")}


def simulate_trail(
    rows,
    side: str,
    entry: float,
    initial_stop: float,
    *,
    atr: float,
    start_idx: int = 0,
    **cfg,
) -> Dict[str, Any]:
    """Run the trail over rows[start_idx:] (each [ts,o,h,l,c,v]); return exit R & bar."""
    pt = new_trail(side, entry, initial_stop)
    for k in range(start_idx, len(rows)):
        r = rows[k]
        out = update_trail(pt, float(r[2]), float(r[3]), atr=atr, **cfg)
        if out["exit"]:
            xr = ((out["exit_price"] - entry) if side == "long" else (entry - out["exit_price"])) / pt.risk
            return {"exit_bar": k, "exit_price": out["exit_price"], "r_multiple": round(xr, 4),
                    "trailed": out["trail_active"]}
    # closed at last bar
    last_c = float(rows[-1][4])
    xr = ((last_c - entry) if side == "long" else (entry - last_c)) / pt.risk
    return {"exit_bar": len(rows) - 1, "exit_price": last_c, "r_multiple": round(xr, 4),
            "trailed": pt.trail_on, "reason": "eod"}
