"""Instrument-aware FX/CFD specifications for V2 research.

Values are deliberately conservative research assumptions, not broker truth.
Promotion requires calibration from the target broker's quotes and fills.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict

from bot.fx_contracts import FxExecutionCosts, FxInstrumentSpec


def _costs(spread: float, *, cfd: bool = False) -> tuple[FxExecutionCosts, FxExecutionCosts]:
    base = FxExecutionCosts(
        spread_bps=spread,
        commission_bps_per_side=0.10 if not cfd else 0.15,
        market_entry_slippage_bps=0.20 if not cfd else 0.35,
        limit_entry_slippage_bps=0.05 if not cfd else 0.10,
        exit_slippage_bps=0.25 if not cfd else 0.40,
        financing_bps_per_day=0.04 if not cfd else 0.35,
        label="base",
    )
    stress = FxExecutionCosts(
        spread_bps=spread * 1.75,
        commission_bps_per_side=base.commission_bps_per_side * 1.5,
        market_entry_slippage_bps=base.market_entry_slippage_bps * 2.0,
        limit_entry_slippage_bps=base.limit_entry_slippage_bps * 2.0,
        exit_slippage_bps=base.exit_slippage_bps * 2.0,
        financing_bps_per_day=base.financing_bps_per_day * 1.5,
        label="stress",
    )
    return base, stress


def _fx(symbol: str, pip: float, precision: int, spread_bps: float, steps: tuple[float, ...]) -> FxInstrumentSpec:
    base, stress = _costs(spread_bps)
    return FxInstrumentSpec(
        symbol=symbol,
        asset_class="fx",
        pip_size=pip,
        price_precision=precision,
        schedule="fx_24x5",
        round_steps=steps,
        base_costs=base,
        stress_costs=stress,
        notes="Research costs; calibrate against target broker before demo promotion.",
    )


_SPECS: Dict[str, FxInstrumentSpec] = {
    "EURUSD": _fx("EURUSD", 0.0001, 5, 0.90, (0.005, 0.010)),
    "GBPUSD": _fx("GBPUSD", 0.0001, 5, 1.15, (0.005, 0.010)),
    "USDJPY": _fx("USDJPY", 0.01, 3, 0.90, (0.50, 1.00)),
    "EURJPY": _fx("EURJPY", 0.01, 3, 1.20, (0.50, 1.00)),
    "GBPJPY": _fx("GBPJPY", 0.01, 3, 1.55, (0.50, 1.00)),
    "USDCAD": _fx("USDCAD", 0.0001, 5, 1.15, (0.005, 0.010)),
    "AUDUSD": _fx("AUDUSD", 0.0001, 5, 1.10, (0.005, 0.010)),
    "NZDUSD": _fx("NZDUSD", 0.0001, 5, 1.35, (0.005, 0.010)),
    "USDCHF": _fx("USDCHF", 0.0001, 5, 1.20, (0.005, 0.010)),
    "EURGBP": _fx("EURGBP", 0.0001, 5, 1.10, (0.005, 0.010)),
    "AUDJPY": _fx("AUDJPY", 0.01, 3, 1.30, (0.50, 1.00)),
    "CADJPY": _fx("CADJPY", 0.01, 3, 1.35, (0.50, 1.00)),
}

_xau_base, _xau_stress = _costs(1.50, cfd=True)
_SPECS["XAUUSD"] = FxInstrumentSpec(
    symbol="XAUUSD",
    asset_class="cfd",
    pip_size=0.10,
    price_precision=2,
    schedule="xau_23x5",
    round_steps=(10.0, 50.0),
    base_costs=_xau_base,
    stress_costs=_xau_stress,
    notes="Generic spot-gold CFD assumptions; broker contract and financing remain a promotion gate.",
)


def get_instrument(symbol: str) -> FxInstrumentSpec:
    key = str(symbol).upper().replace("/", "")
    if key not in _SPECS:
        raise KeyError(f"unsupported FX/CFD instrument: {symbol}")
    return _SPECS[key]


def all_instruments() -> Dict[str, FxInstrumentSpec]:
    return dict(_SPECS)


def instrument_round_levels(spec: FxInstrumentSpec, price: float, *, radius: int = 2) -> tuple[float, ...]:
    """Return explicit instrument-aware grids (never infer scale from price)."""
    out: set[float] = set()
    if not (price > 0):
        return ()
    for step in spec.round_steps:
        if step <= 0:
            continue
        base = round(price / step) * step
        for k in range(-int(radius), int(radius) + 1):
            value = base + k * step
            if value > 0:
                out.add(round(value, spec.price_precision))
    return tuple(sorted(out))


def with_costs(spec: FxInstrumentSpec, *, base: FxExecutionCosts, stress: FxExecutionCosts) -> FxInstrumentSpec:
    """Explicit test/live calibration hook; never mutates the canonical table."""
    return replace(spec, base_costs=base, stress_costs=stress)
