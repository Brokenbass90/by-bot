"""Conservative aggregation of Bybit closed-PnL rows for one logical position.

Bybit emits one ``closed-pnl`` row per close order.  Runner-managed positions
can therefore have several rows (partial take-profits plus the final exit).
The helpers in this module keep the exchange-specific matching logic pure and
testable; they never call the exchange.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable


BYBIT_CLOSED_PNL_MAX_WINDOW_MS = 7 * 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class ClosedPnlAggregate:
    pnl: float
    fees: float
    closed_size: float
    latest_exit_price: float | None
    rows: tuple[dict[str, Any], ...]


def closed_pnl_query_windows(
    start_ms: int,
    end_ms: int,
    *,
    max_window_ms: int = BYBIT_CLOSED_PNL_MAX_WINDOW_MS,
) -> tuple[tuple[int, int], ...]:
    """Split an inclusive Bybit query range into API-valid windows.

    Bybit limits ``endTime - startTime`` to seven days.  ATT1's maximum
    holding period is also seven days, and the finalizer deliberately adds a
    small timestamp buffer, so a single request can otherwise exceed the API
    contract exactly when a time-stop closes.  Adjacent windows use ``+1 ms``
    to avoid both gaps and duplicate boundary timestamps.
    """
    start = _int(start_ms)
    end = _int(end_ms)
    window = _int(max_window_ms)
    if start <= 0 or end < start or window <= 0:
        return ()
    out: list[tuple[int, int]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + window)
        out.append((cursor, chunk_end))
        cursor = chunk_end + 1
    return tuple(out)


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _event_time_ms(row: dict[str, Any]) -> int:
    # updatedTime is the actual close/update time for conditional TP/SL orders;
    # createdTime can be as early as the moment the protective order was armed.
    return _int(row.get("updatedTime") or row.get("createdTime"))


def _row_fees(row: dict[str, Any]) -> float:
    """Read exactly one Bybit fee-field family, newest to legacy.

    Different account/API generations expose aliases for the same fees.  Adding
    every populated alias would double-count, so the first available family is
    authoritative for that row.
    """
    open_fee = _float(row.get("openFee"))
    close_fee = _float(row.get("closeFee"))
    if open_fee is not None or close_fee is not None:
        return float(open_fee or 0.0) + float(close_fee or 0.0)

    entry_fee = _float(row.get("cumEntryFee"))
    exit_fee = _float(row.get("cumExitFee"))
    if entry_fee is not None or exit_fee is not None:
        return float(entry_fee or 0.0) + float(exit_fee or 0.0)

    total_fee = _float(row.get("totalFee"))
    if total_fee is not None:
        return float(total_fee)
    legacy_fee = _float(row.get("fee"))
    return float(legacy_fee or 0.0)


def _row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    order_id = str(row.get("orderId") or "").strip()
    if order_id:
        return ("order", order_id)
    # The API normally supplies orderId.  This conservative fallback prevents
    # duplicated snapshots of the same anonymous row from double-counting PnL.
    return (
        "row",
        _event_time_ms(row),
        str(row.get("closedSize") or ""),
        str(row.get("closedPnl") or ""),
        str(row.get("avgExitPrice") or ""),
    )


def aggregate_closed_pnl(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str,
    position_side: str,
    entry_time_ms: int,
    entry_price: float,
    expected_size: float | None = None,
    entry_price_rel_tol: float = 1e-6,
) -> ClosedPnlAggregate | None:
    """Return the complete realized PnL for one logical Bybit position.

    Identity is deliberately fail-closed: symbol, opposite closing-order side,
    close/update time since entry, normal Trade execution type, and exchange
    average entry price must all agree.  ``expected_size`` is mandatory, and
    the function waits until the matched rows account for the whole position.
    This prevents the finalizer from publishing only the first closed-PnL row
    that becomes eventually visible or aggregating an unbounded lifecycle.
    """
    target_symbol = str(symbol or "").upper().strip()
    side = str(position_side or "").strip().lower()
    close_side = {"buy": "sell", "sell": "buy"}.get(side)
    entry_ms = max(0, _int(entry_time_ms))
    expected_entry = _float(entry_price)
    target_size = _float(expected_size)
    if (
        not target_symbol
        or close_side is None
        or entry_ms <= 0
        or expected_entry is None
        or expected_entry <= 0.0
    ):
        return None
    if target_size is None or target_size <= 0.0:
        # Without the position's expected size there is no bounded lifecycle:
        # same-symbol rows after entry could include another position/restart.
        return None

    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        if str(row.get("symbol") or "").upper().strip() != target_symbol:
            continue
        if str(row.get("side") or "").strip().lower() != close_side:
            continue
        if _event_time_ms(row) < entry_ms:
            continue
        exec_type = str(row.get("execType") or "Trade").strip().lower()
        if exec_type != "trade":
            continue

        row_entry = _float(row.get("avgEntryPrice"))
        if row_entry is None or row_entry <= 0.0:
            continue
        if not math.isclose(
            row_entry,
            expected_entry,
            rel_tol=max(0.0, float(entry_price_rel_tol)),
            abs_tol=max(1e-12, abs(expected_entry) * 1e-10),
        ):
            continue

        size = _float(row.get("closedSize"))
        if size is None or size <= 0.0:
            continue
        key = _row_key(row)
        old = deduped.get(key)
        if old is None or _event_time_ms(row) >= _event_time_ms(old):
            deduped[key] = row

    ordered = sorted(
        deduped.values(),
        key=lambda row: (_event_time_ms(row), str(row.get("orderId") or "")),
    )
    selected: list[dict[str, Any]] = []
    closed_size = 0.0
    size_tol = max(1e-12, abs(target_size) * 1e-6)
    for row in ordered:
        size = float(_float(row.get("closedSize")) or 0.0)
        if closed_size + size > target_size + size_tol:
            # A row which would over-close this logical position belongs to a
            # different lifecycle (or the evidence is inconsistent).  Do not
            # let it contaminate the trade record.
            continue
        selected.append(row)
        closed_size += size
        if closed_size >= target_size - size_tol:
            break

    if not selected:
        return None
    if closed_size < target_size - size_tol:
        return None

    pnl = 0.0
    for row in selected:
        row_pnl = _float(row.get("closedPnl"))
        if row_pnl is None:
            return None
        pnl += row_pnl

    latest = max(selected, key=_event_time_ms)
    latest_exit_price = _float(
        latest.get("avgExitPrice")
        or latest.get("exitPrice")
        or latest.get("avgClosePrice")
        or latest.get("closeAvgPrice")
    )
    return ClosedPnlAggregate(
        pnl=float(pnl),
        fees=float(sum(_row_fees(row) for row in selected)),
        closed_size=float(closed_size),
        latest_exit_price=latest_exit_price,
        rows=tuple(selected),
    )
