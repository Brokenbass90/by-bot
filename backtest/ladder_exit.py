"""Canonical runner-ladder exit simulator (pure, deterministic, testable).

Models the real exit of the crypto runner strategies (ASB1/ARF1/ATT1/...):
  * partial take-profits at ordered ladder levels `tps` with weights `fracs`,
  * after TP1 the stop moves to breakeven (entry), so the runner can't turn a
    booked partial win into a loss,
  * remainder runs to the far target (TP2) or is stopped at breakeven,
  * round-trip fee/slippage charged per filled fraction, expressed in R units.

Returns realised R in units of the initial risk = |entry - sl|, plus any
fraction still open at the end of the supplied bars (caller decides time-stop).

This is the primitive both the offline efficiency harness and (when wired) the
live runner accounting can share, so backtest and live measure the same thing.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple


def simulate_ladder_exit(
    is_long: bool,
    entry: float,
    sl: float,
    tps: Sequence[float],
    fracs: Sequence[float],
    bars: Sequence[Tuple[float, float]],   # ordered forward bars as (high, low)
    *,
    fee_bps_round_trip: float = 0.0,
    move_to_breakeven_after_tp1: bool = True,
) -> Tuple[float, float]:
    """Return (realised_R, remaining_fraction_open)."""
    risk = abs(entry - sl)
    if risk <= 0 or entry <= 0 or not tps:
        return 0.0, 1.0

    def R_at(px: float) -> float:
        return ((px - entry) if is_long else (entry - px)) / risk

    remaining = 1.0
    stop = sl
    realised = 0.0
    next_tp = 0
    fee_units = 1.0  # the entry fill

    for high, low in bars:
        # stop checked first (conservative: assume worst intrabar ordering)
        hit_stop = (low <= stop) if is_long else (high >= stop)
        if hit_stop:
            realised += remaining * R_at(stop)
            fee_units += remaining
            remaining = 0.0
            break
        while next_tp < len(tps):
            tp = float(tps[next_tp])
            hit = (high >= tp) if is_long else (low <= tp)
            if not hit:
                break
            f = min(remaining, float(fracs[next_tp]) if next_tp < len(fracs) else remaining)
            realised += f * R_at(tp)
            fee_units += f
            remaining -= f
            if next_tp == 0 and move_to_breakeven_after_tp1:
                stop = entry
            next_tp += 1
        if remaining <= 1e-9:
            remaining = 0.0
            break

    fee_R = (fee_units * (fee_bps_round_trip / 10000.0)) / (risk / entry) if risk > 0 else 0.0
    return realised - fee_R, remaining
