"""Fail-closed initialization for portfolio equity anchors."""

from __future__ import annotations

import math
from typing import Any, MutableMapping


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
    try:
        value = float(equity)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(value) or value <= 0.0:
        return False

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
