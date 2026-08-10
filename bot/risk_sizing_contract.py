"""Pure risk-sizing contract shared by research and, after parity review, live.

The function intentionally knows nothing about exchange clients, balances or
environment variables.  Callers must materialize those inputs first, which
makes the calculation reproducible in tests and receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RiskSizeDecision:
    accepted: bool
    qty: float
    desired_risk_usd: float
    effective_risk_usd: float
    desired_notional_usd: float
    effective_notional_usd: float
    fill_fraction: float
    binding_constraint: str
    reason: str


def calculate_risk_size(
    *,
    equity: float,
    entry: float,
    stop: float,
    side: str | None = None,
    target_risk_fraction: float,
    max_notional_usd: Optional[float],
    min_fill_fraction: float = 0.40,
) -> RiskSizeDecision:
    """Return the exact fixed-R size and expose every binding constraint."""
    values = (equity, entry, stop, target_risk_fraction, min_fill_fraction)
    if any(not (float(v) == float(v)) for v in values):
        return _reject("non_finite_input")
    if equity <= 0 or entry <= 0 or target_risk_fraction <= 0:
        return _reject("nonpositive_input")
    normalized_side = str(side or "").strip().lower()
    if normalized_side == "long":
        stop_distance = entry - stop
    elif normalized_side == "short":
        stop_distance = stop - entry
    else:
        stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return _reject("nonpositive_stop_distance")

    desired_risk = equity * target_risk_fraction
    desired_qty = desired_risk / stop_distance
    desired_notional = desired_qty * entry

    effective_notional = desired_notional
    binding = "risk_target"
    if max_notional_usd is not None and max_notional_usd > 0:
        if effective_notional > max_notional_usd:
            effective_notional = float(max_notional_usd)
            binding = "notional_cap"

    qty = effective_notional / entry
    effective_risk = qty * stop_distance
    fill = effective_notional / desired_notional if desired_notional > 0 else 0.0
    accepted = fill >= max(0.0, min(1.0, min_fill_fraction))
    return RiskSizeDecision(
        accepted=accepted,
        qty=qty if accepted else 0.0,
        desired_risk_usd=desired_risk,
        effective_risk_usd=effective_risk if accepted else 0.0,
        desired_notional_usd=desired_notional,
        effective_notional_usd=effective_notional if accepted else 0.0,
        fill_fraction=fill,
        binding_constraint=binding,
        reason="sized" if accepted else "below_min_fill_fraction",
    )


def calculate_notional_from_stop_pct(
    *,
    equity: float,
    stop_pct: float,
    target_risk_fraction: float,
    risk_multiplier: float,
    volatility_multiplier: float,
    max_notional_usd: Optional[float],
    min_fill_fraction: float = 0.40,
) -> RiskSizeDecision:
    """Resolve the live stop-percent model through the shared fixed-R contract.

    A synthetic entry of 1.0 makes quantity numerically equal to notional. This
    keeps the stop-percent live interface while guaranteeing that cap and
    minimum-fill behavior are identical to the backtest sizing engine.
    Exchange qty-step rounding deliberately remains a later execution layer.
    """
    try:
        distance_fraction = float(stop_pct) / 100.0
        combined_risk_fraction = (
            float(target_risk_fraction)
            * float(risk_multiplier)
            * float(volatility_multiplier)
        )
    except (TypeError, ValueError):
        return _reject("non_finite_input")
    return calculate_risk_size(
        equity=float(equity),
        entry=1.0,
        stop=1.0 - distance_fraction,
        target_risk_fraction=combined_risk_fraction,
        max_notional_usd=max_notional_usd,
        min_fill_fraction=min_fill_fraction,
    )


def _reject(reason: str) -> RiskSizeDecision:
    return RiskSizeDecision(
        accepted=False,
        qty=0.0,
        desired_risk_usd=0.0,
        effective_risk_usd=0.0,
        desired_notional_usd=0.0,
        effective_notional_usd=0.0,
        fill_fraction=0.0,
        binding_constraint="invalid_input",
        reason=reason,
    )
