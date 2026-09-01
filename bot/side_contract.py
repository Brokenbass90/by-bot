"""Pure direction vocabulary shared by research, backtests, and broker boundaries."""

from __future__ import annotations

from typing import Literal


InternalSide = Literal["long", "short"]
ExchangeSide = Literal["Buy", "Sell"]


class SideContractError(ValueError):
    """Raised when a direction is outside the declared vocabulary."""


_ALIASES: dict[str, InternalSide] = {
    "long": "long",
    "buy": "long",
    "short": "short",
    "sell": "short",
}


def normalize_side(value: object) -> InternalSide:
    """Return the canonical internal direction or fail closed."""
    if not isinstance(value, str):
        raise SideContractError(f"unsupported side: {value!r}")
    normalized = _ALIASES.get(value.strip().lower())
    if normalized is None:
        raise SideContractError(f"unsupported side: {value!r}")
    return normalized


def to_exchange_side(value: object) -> ExchangeSide:
    """Translate a declared direction to the exact Bybit order vocabulary."""
    return "Buy" if normalize_side(value) == "long" else "Sell"
