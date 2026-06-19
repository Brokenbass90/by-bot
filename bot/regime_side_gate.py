"""Pure direction gate for strategies controlled by a market regime label."""
from __future__ import annotations


def regime_side_allowed(side: str, regime: str, *, enabled: bool = True) -> bool:
    """Return whether an exchange side is compatible with the current regime.

    Bull and bear labels include both trend and chop variants. Neutral and
    unknown labels preserve the strategy's own side configuration.
    """
    if not enabled:
        return True

    normalized_side = str(side or "").strip().lower()
    normalized_regime = str(regime or "").strip().lower()

    is_long = normalized_side in {"buy", "long"}
    is_short = normalized_side in {"sell", "short"}
    if not (is_long or is_short):
        return False

    if "bull" in normalized_regime:
        return is_long
    if "bear" in normalized_regime:
        return is_short
    return True
