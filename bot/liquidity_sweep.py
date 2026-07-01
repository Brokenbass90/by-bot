"""Liquidity-sweep / density detector — fade the stop-run OR follow the break.

Liquidity pools sit just beyond recent swing highs/lows (stop clusters) and at
order-book density walls. Two outcomes, and this tells them apart:
  * SWEEP + REVERSAL — price spikes BEYOND the pool (grabs stops) then closes back
    INSIDE -> the move was a liquidity grab -> FADE it (bounce). This is the
    "liquidity hunter" entry: tight stop beyond the sweep extreme, big R on reversal.
  * BREAK + HOLD — price closes BEYOND the pool and stays (wall absorbed) -> genuine
    breakout -> FOLLOW it.

So a density/pool drives BOTH bounces and breakouts; the bar's close vs the pool
decides which. Side split: sweep-of-highs -> SHORT fade / sweep-of-lows -> LONG fade;
break above -> LONG / break below -> SHORT. Row [ts,o,h,l,c,v]. Pure stdlib + atr.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from bot.market_context import atr, OPEN, HIGH, LOW, CLOSE


def _f(row: Sequence[float], i: int) -> float:
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


@dataclass
class SweepState:
    ok: bool
    event: str                 # "sweep_reversal" | "break_hold" | "none"
    direction: str             # for sweep: side of the pool swept; for break: break dir
    pool_level: float
    side: str                  # "long" | "short" | "none"
    long_ok: bool
    short_ok: bool
    penetration_atr: float     # how far beyond the pool the extreme reached
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def liquidity_sweep(
    rows: Sequence[Sequence[float]],
    *,
    pool_lookback: int = 20,
    min_penetration_atr: float = 0.10,   # must actually poke beyond the pool
    hold_atr: float = 0.10,              # close this far beyond = genuine break
    atr_value: Optional[float] = None,
) -> SweepState:
    """Classify the latest bar vs recent liquidity pools; emit a one-sided gate."""
    n = len(rows)
    if n < pool_lookback + 2:
        return SweepState(False, "none", "none", float("nan"), "none", False, False,
                          float("nan"), "insufficient_data")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0):
        return SweepState(False, "none", "none", float("nan"), "none", False, False,
                          float("nan"), "no_atr")

    prior = rows[-pool_lookback - 1:-1]
    pool_high = max(_f(r, HIGH) for r in prior)
    pool_low = min(_f(r, LOW) for r in prior)
    bar = rows[-1]
    h, l, c = _f(bar, HIGH), _f(bar, LOW), _f(bar, CLOSE)

    # sweep of highs: poked above pool_high but closed back below it -> short fade
    if h > pool_high + min_penetration_atr * a and c < pool_high:
        return SweepState(True, "sweep_reversal", "high", pool_high, "short", False, True,
                          (h - pool_high) / a, "swept_highs_reversal")
    # sweep of lows: poked below pool_low but closed back above -> long fade
    if l < pool_low - min_penetration_atr * a and c > pool_low:
        return SweepState(True, "sweep_reversal", "low", pool_low, "long", True, False,
                          (pool_low - l) / a, "swept_lows_reversal")
    # break + hold above -> long continuation
    if c > pool_high + hold_atr * a:
        return SweepState(True, "break_hold", "up", pool_high, "long", True, False,
                          (c - pool_high) / a, "break_hold_up")
    # break + hold below -> short continuation
    if c < pool_low - hold_atr * a:
        return SweepState(True, "break_hold", "down", pool_low, "short", False, True,
                          (pool_low - c) / a, "break_hold_down")

    return SweepState(True, "none", "none", float("nan"), "none", False, False,
                      float("nan"), "inside_pools")
