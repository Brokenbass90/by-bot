"""Pure, fail-closed regime gate for strategy-level capital decisions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class StrategyRegimeGateDecision:
    allowed: bool
    reason: str
    regime: str


def strategy_regime_gate_decision(
    regime: str,
    *,
    overlay_fresh: bool,
    allowed_regimes: Iterable[str],
    enabled: bool = True,
    fail_closed: bool = True,
) -> StrategyRegimeGateDecision:
    """Return a deterministic strategy gate decision.

    The gate is deliberately separate from enable flags and risk multipliers:
    an old or neutral regime overlay must not silently re-enable a directional
    money sleeve.
    """
    normalized_regime = str(regime or "").strip().upper()
    allowed = {
        str(value or "").strip().upper()
        for value in allowed_regimes
        if str(value or "").strip()
    }

    if not enabled:
        return StrategyRegimeGateDecision(True, "gate_disabled", normalized_regime)
    if not overlay_fresh:
        return StrategyRegimeGateDecision(
            not fail_closed,
            "overlay_stale_or_missing",
            normalized_regime,
        )
    if not normalized_regime:
        return StrategyRegimeGateDecision(
            not fail_closed,
            "regime_missing",
            normalized_regime,
        )
    if normalized_regime not in allowed:
        return StrategyRegimeGateDecision(
            False,
            f"regime_not_allowed:{normalized_regime}",
            normalized_regime,
        )
    return StrategyRegimeGateDecision(True, "allowed", normalized_regime)
