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
