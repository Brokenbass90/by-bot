"""Volatility-aware, risk-based position sizing — make 1R the SAME on every trade.

Foundational for honest OOS numbers: if each trade risks a different amount, R
multiples are not comparable and drawdown is uncontrolled. This sizes every trade
to risk the SAME fraction of equity (in R), regardless of stop distance, then:
  * respects a PORTFOLIO risk budget (don't exceed max total open risk);
  * caps leverage (notional <= max_position_pct of equity);
  * optionally VOL-TARGETS: trims risk when ATR% is elevated (avoid oversizing in
    volatile/expansion regimes), scales up (bounded) when unusually quiet.

Returns a SizePlan the executor consumes. Pure stdlib; deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


@dataclass
class SizePlan:
    ok: bool
    place: bool
    qty: float                   # units of the asset
    notional: float              # qty * entry
    risk_amount: float           # currency at risk if stop hit
    risk_pct_effective: float    # risk_amount / equity * 100
    leverage: float              # notional / equity
    vol_scalar: float            # applied volatility adjustment (1.0 = none)
    capped: bool                 # leverage or budget cap bit
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _skip(reason: str) -> SizePlan:
    return SizePlan(ok=True, place=False, qty=0.0, notional=0.0, risk_amount=0.0,
                    risk_pct_effective=0.0, leverage=0.0, vol_scalar=1.0, capped=False,
                    reason=reason)


def plan_size(
    equity: float,
    entry: float,
    stop: float,
    *,
    risk_pct: float = 1.0,               # target risk per trade, % of equity
    atr_pct: Optional[float] = None,     # current ATR / price * 100 (for vol-target)
    target_atr_pct: Optional[float] = None,  # desired vol; if set, scale risk by target/current
    vol_scalar_floor: float = 0.5,
    vol_scalar_ceil: float = 1.5,
    max_position_pct: float = 100.0,     # notional cap as % of equity (leverage guard)
    min_notional: float = 10.0,
    open_risk_pct: float = 0.0,          # risk already deployed across open trades
    max_open_risk_pct: float = 1.5,      # portfolio open-risk budget
) -> SizePlan:
    """Size a trade to a fixed R with portfolio-budget, leverage and vol guards."""
    if not (equity == equity and equity > 0):
        return _skip("no_equity")
    if not (entry == entry and entry > 0):
        return _skip("no_entry")
    risk_per_unit = abs(entry - stop)
    if not (risk_per_unit == risk_per_unit and risk_per_unit > 0):
        return _skip("nonpositive_risk_distance")

    # vol-target: reduce risk when current vol exceeds target (and vice versa, bounded)
    vol_scalar = 1.0
    if atr_pct and target_atr_pct and atr_pct > 0:
        vol_scalar = _clamp(target_atr_pct / atr_pct, vol_scalar_floor, vol_scalar_ceil)

    target_risk_pct = risk_pct * vol_scalar

    # portfolio budget: cannot exceed remaining open-risk allowance
    remaining = max_open_risk_pct - open_risk_pct
    if remaining <= 0:
        return _skip("portfolio_risk_budget_full")
    budget_capped = target_risk_pct > remaining
    allowed_risk_pct = min(target_risk_pct, remaining)

    risk_amount = equity * allowed_risk_pct / 100.0
    qty = risk_amount / risk_per_unit
    notional = qty * entry

    # leverage cap
    lev_capped = False
    max_notional = equity * max_position_pct / 100.0
    if notional > max_notional:
        lev_capped = True
        notional = max_notional
        qty = notional / entry
        risk_amount = qty * risk_per_unit  # effective risk after cap (lower)

    if notional < min_notional:
        return _skip(f"below_min_notional_{notional:.2f}")

    return SizePlan(
        ok=True, place=True, qty=qty, notional=notional, risk_amount=risk_amount,
        risk_pct_effective=risk_amount / equity * 100.0, leverage=notional / equity,
        vol_scalar=vol_scalar, capped=bool(lev_capped or budget_capped),
        reason="sized", extra={"risk_per_unit": risk_per_unit,
                               "allowed_risk_pct": allowed_risk_pct,
                               "budget_capped": budget_capped, "lev_capped": lev_capped},
    )
