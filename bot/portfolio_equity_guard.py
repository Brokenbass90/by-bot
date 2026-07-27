"""Fail-closed initialization for portfolio equity anchors."""

from __future__ import annotations

import math
from typing import Any, MutableMapping


def is_valid_equity(equity: Any) -> bool:
    """Return whether an equity reading is finite and strictly positive."""
    try:
        value = float(equity)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value > 0.0


def initialize_equity_anchors(
    state: MutableMapping[str, Any],
    *,
    today: str,
    equity: float,
) -> bool:
    """Initialize or roll daily anchors only from a valid positive equity.

    Returning ``False`` means new entries must remain blocked.  In particular,
    a cold-start broker/API failure must not permanently store ``0`` as the
    drawdown baseline.
    """
    if not is_valid_equity(equity):
        return False
    value = float(equity)

    if state.get("start_equity") is None:
        state["start_equity"] = value
        state["day_equity_start"] = value
        state["day"] = str(today)
        state["daily_pnl_usd"] = 0.0
        state["disabled"] = False
        return True

    if state.get("day") != str(today):
        state["day"] = str(today)
        state["day_equity_start"] = value
        state["daily_pnl_usd"] = 0.0
        state["disabled"] = False
    return True
