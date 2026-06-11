"""Pure TP/SL restoration policy helpers."""

from __future__ import annotations

from typing import Optional, TypeVar


T = TypeVar("T")


def restored_position_manual_lock(
    strategy: str,
    *,
    tp_present: bool,
    sl_present: bool,
) -> bool:
    """Return whether exchange TP/SL should be treated as manually complete.

    A bootstrap position has no trusted local lifecycle. One protection side
    must not lock the missing side out of automatic repair.
    """
    if str(strategy or "").strip().lower() == "bootstrap":
        return bool(tp_present and sl_present)
    return bool(tp_present or sl_present)


def preserve_existing_tpsl(
    current_tp: Optional[T],
    current_sl: Optional[T],
    default_tp: T,
    default_sl: T,
) -> tuple[T, T]:
    """Fill only missing TP/SL values and preserve broker-known protection."""
    tp = current_tp if current_tp is not None else default_tp
    sl = current_sl if current_sl is not None else default_sl
    return tp, sl


def should_preserve_strategy_tpsl(
    strategy: Optional[str],
    *,
    has_strategy_levels: bool,
    legacy_pct_strategies,
) -> bool:
    """Decide how to set TP/SL at fill time.

    Returns True  -> keep the strategy-designed TP/SL (only re-round vs avg).
    Returns False -> use the global TP_PCT/SL_PCT percentage fallback.

    P0-fix (2026-06-08): historically only a tiny hard-coded whitelist kept
    their own levels; every other strategy had its stop overwritten with the
    legacy pump 0.3% stop at fill, destroying its designed risk/reward. Now the
    default is to preserve, and only explicit legacy pump strategies (or trades
    that never supplied any level) fall back to the percentage model. Runner
    strategies intentionally have no fixed TP, but their strategy SL is still a
    real level and must be preserved.
    """
    name = str(strategy or "pump")
    if name in set(legacy_pct_strategies or ()):  # explicit legacy pump family
        return False
    return bool(has_strategy_levels)
