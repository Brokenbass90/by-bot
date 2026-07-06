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


def planned_tpsl_after_fill(
    side: str,
    *,
    fill_price: Optional[float],
    planned_entry: Optional[float],
    planned_tp: Optional[float],
    planned_sl: Optional[float],
    current_tp: Optional[float],
    current_sl: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Return strategy-planned TP/SL for post-fill exchange placement.

    The planned order-submission levels are the source of truth. If a fill gaps
    through a planned level, preserve the planned distance from the real fill
    instead of silently compressing to one tick.
    """
    tp = planned_tp if planned_tp is not None else current_tp
    sl = planned_sl if planned_sl is not None else current_sl

    try:
        fill = float(fill_price) if fill_price is not None else None
        entry = float(planned_entry) if planned_entry is not None else None
    except (TypeError, ValueError):
        return tp, sl
    if fill is None or entry is None or fill <= 0 or entry <= 0:
        return tp, sl

    side_norm = str(side or "").strip()
    try:
        if side_norm == "Buy":
            if planned_sl is not None and float(planned_sl) < entry and sl is not None and float(sl) >= fill:
                sl = fill - abs(entry - float(planned_sl))
            if planned_tp is not None and float(planned_tp) > entry and tp is not None and float(tp) <= fill:
                tp = fill + abs(float(planned_tp) - entry)
        elif side_norm == "Sell":
            if planned_sl is not None and float(planned_sl) > entry and sl is not None and float(sl) <= fill:
                sl = fill + abs(float(planned_sl) - entry)
            if planned_tp is not None and float(planned_tp) < entry and tp is not None and float(tp) >= fill:
                tp = fill - abs(entry - float(planned_tp))
    except (TypeError, ValueError):
        return tp, sl
    return tp, sl


def protective_stop_is_live(
    side: str,
    stop: Optional[float],
    current_price: Optional[float],
    *,
    tick: float = 0.0,
) -> bool:
    """Return whether a stop can still protect the position from here.

    For a long, a protective stop must be below the current market. For a short,
    it must be above the current market. This intentionally checks current price,
    not entry, because runner/breakeven stops are allowed to lock profit after a
    trade moves in our favor.
    """
    try:
        stop_f = float(stop) if stop is not None else None
        price_f = float(current_price) if current_price is not None else None
        tick_f = max(0.0, float(tick or 0.0))
    except (TypeError, ValueError):
        return False
    if stop_f is None or price_f is None or stop_f <= 0 or price_f <= 0:
        return False
    side_norm = str(side or "").strip()
    if side_norm == "Buy":
        return stop_f < price_f - tick_f
    if side_norm == "Sell":
        return stop_f > price_f + tick_f
    return False


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
