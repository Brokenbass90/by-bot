"""Pure execution and funding contract for a causal XSEC replay.

Signals are calculated from a completed UTC daily close.  The earliest
executable rebalance is the next UTC daily open.  A positive perpetual funding
rate is paid by longs and received by shorts, so portfolio cashflow is
``-weight * rate`` for every funding event crossed while the position is open.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def next_open_period(signal_index: int, hold_days: int, bar_count: int) -> tuple[int, int] | None:
    """Return executable open indices or None when the full hold is unavailable."""
    if signal_index < 0 or hold_days <= 0:
        raise ValueError("signal_index must be >=0 and hold_days must be positive")
    entry_index = signal_index + 1
    exit_index = entry_index + hold_days
    if exit_index >= bar_count:
        return None
    return entry_index, exit_index


def funding_cashflow(
    weights: Mapping[str, float],
    funding: Mapping[str, Sequence[tuple[int, float]]],
    *,
    entry_ts_ms: int,
    exit_ts_ms: int,
) -> float:
    """Return funding PnL as a fraction of sleeve equity.

    Events exactly at entry are excluded because queue/order timing at that
    instant is not proven; events up to and including exit are included.
    """
    if exit_ts_ms <= entry_ts_ms:
        raise ValueError("exit must be after entry")
    total = 0.0
    for symbol, weight in weights.items():
        w = float(weight)
        if not math.isfinite(w):
            raise ValueError(f"{symbol}: non-finite weight")
        for ts_ms, rate in funding.get(symbol, ()):
            ts = int(ts_ms)
            r = float(rate)
            if not math.isfinite(r):
                raise ValueError(f"{symbol}: non-finite funding rate")
            if entry_ts_ms < ts <= exit_ts_ms:
                total -= w * r
    return total


def period_return(
    weights: Mapping[str, float],
    entry_open: Mapping[str, float],
    exit_open: Mapping[str, float],
    funding: Mapping[str, Sequence[tuple[int, float]]],
    *,
    entry_ts_ms: int,
    exit_ts_ms: int,
    round_trip_cost_fraction: float,
) -> dict[str, float]:
    """Causal open-to-open portfolio return with crossed funding cashflows."""
    if round_trip_cost_fraction < 0 or not math.isfinite(round_trip_cost_fraction):
        raise ValueError("round-trip cost must be finite and non-negative")
    price = 0.0
    missing = []
    for symbol, weight in weights.items():
        p1 = float(entry_open.get(symbol, float("nan")))
        p2 = float(exit_open.get(symbol, float("nan")))
        if not (math.isfinite(p1) and math.isfinite(p2) and p1 > 0 and p2 > 0):
            missing.append(symbol)
            continue
        price += float(weight) * (p2 / p1 - 1.0)
    if missing:
        raise ValueError("missing executable prices: " + ",".join(sorted(missing)))
    cashflow = funding_cashflow(
        weights, funding, entry_ts_ms=entry_ts_ms, exit_ts_ms=exit_ts_ms
    )
    cost = float(round_trip_cost_fraction)
    return {
        "price_return": price,
        "funding_cashflow": cashflow,
        "cost": cost,
        "net_return": price + cashflow - cost,
    }
