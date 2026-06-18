"""Maker-first entry execution with fail-closed market fallback.

The orchestrator is exchange-client agnostic.  The client is expected to expose
``place_post_only``, ``get_order``, ``cancel_order``, ``get_position_summary``,
``get_last_price`` and ``place_market`` methods.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


_DONE = {"filled"}
_CANCELLED = {
    "cancelled",
    "canceled",
    "partiallyfilledcancelled",
    "partiallyfilledcanceled",
    "rejected",
    "deactivated",
}


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if math.isfinite(parsed) else default


def _order_status(order: dict[str, Any] | None) -> str:
    return str((order or {}).get("orderStatus") or "").strip().lower()


def _filled_qty(order: dict[str, Any] | None) -> float:
    return max(0.0, _finite_float((order or {}).get("cumExecQty")))


def _fill_price(order: dict[str, Any] | None) -> float | None:
    value = _finite_float((order or {}).get("avgPrice"))
    return value if value > 0.0 else None


@dataclass(frozen=True)
class RiskAssessment:
    allowed: bool
    planned_risk_usd: float
    actual_risk_usd: float
    expansion_ratio: float
    adverse_bps: float
    reason: str = ""


def assess_entry_risk(
    *,
    side: str,
    qty: float,
    planned_entry: float,
    actual_entry: float,
    stop_price: float,
    max_risk_expansion: float,
    max_adverse_bps: float | None = None,
) -> RiskAssessment:
    """Check that an actual/fallback entry still respects planned stop risk."""
    side_n = str(side or "").strip().lower()
    qty_f = max(0.0, _finite_float(qty))
    planned = _finite_float(planned_entry)
    actual = _finite_float(actual_entry)
    stop = _finite_float(stop_price)
    if qty_f <= 0 or planned <= 0 or actual <= 0 or stop <= 0:
        return RiskAssessment(False, 0.0, 0.0, math.inf, math.inf, "invalid_input")
    if side_n in {"buy", "long"}:
        geometry_ok = planned > stop and actual > stop
        adverse_bps = (actual - planned) / planned * 10000.0
    elif side_n in {"sell", "short"}:
        geometry_ok = planned < stop and actual < stop
        adverse_bps = (planned - actual) / planned * 10000.0
    else:
        return RiskAssessment(False, 0.0, 0.0, math.inf, math.inf, "invalid_side")
    if not geometry_ok:
        return RiskAssessment(False, 0.0, 0.0, math.inf, adverse_bps, "stop_crossed")

    planned_risk = qty_f * abs(planned - stop)
    actual_risk = qty_f * abs(actual - stop)
    if planned_risk <= 0:
        return RiskAssessment(False, planned_risk, actual_risk, math.inf, adverse_bps, "zero_planned_risk")
    expansion = actual_risk / planned_risk
    if expansion > max(1.0, float(max_risk_expansion)) + 1e-12:
        return RiskAssessment(False, planned_risk, actual_risk, expansion, adverse_bps, "risk_expansion")
    if max_adverse_bps is not None and adverse_bps > float(max_adverse_bps) + 1e-12:
        return RiskAssessment(False, planned_risk, actual_risk, expansion, adverse_bps, "adverse_move")
    return RiskAssessment(True, planned_risk, actual_risk, expansion, adverse_bps)


@dataclass(frozen=True)
class MakerExecutionResult:
    ok: bool
    order_id: str = ""
    qty: float = 0.0
    mode: str = ""
    limit_price: float | None = None
    fill_price: float | None = None
    maker_order_id: str = ""
    cancel_confirmed: bool = False
    reason: str = ""
    risk: RiskAssessment | None = None


async def execute_maker_first(
    client: Any,
    *,
    symbol: str,
    side: str,
    qty: float,
    reference_price: float,
    stop_price: float,
    offset_bps: float = 2.0,
    wait_sec: float = 8.0,
    poll_sec: float = 1.0,
    cancel_settle_sec: float = 0.5,
    max_adverse_bps: float = 10.0,
    max_risk_expansion: float = 1.15,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> MakerExecutionResult:
    """Place Post-Only, then cancel and fall back only after a confirmed cancel.

    A partial maker fill is accepted after cancellation; the remainder is not
    crossed because mixing two fills obscures risk and makes retries ambiguous.
    """
    maker_order_id = ""
    try:
        maker_order_id, submitted_qty, limit_price = await asyncio.to_thread(
            client.place_post_only,
            symbol,
            side,
            qty,
            reference_price,
            offset_bps,
        )
    except Exception as exc:
        return MakerExecutionResult(False, reason=f"maker_submit_failed:{exc}")

    attempts = max(1, int(math.ceil(max(0.0, wait_sec) / max(0.05, poll_sec))))
    latest_order: dict[str, Any] | None = None
    status_error = ""
    for attempt in range(attempts):
        try:
            latest_order = await asyncio.to_thread(client.get_order, symbol, maker_order_id)
        except Exception as exc:
            status_error = str(exc)
            break
        status = _order_status(latest_order)
        if status in _DONE:
            filled = _filled_qty(latest_order) or float(submitted_qty)
            return MakerExecutionResult(
                True,
                order_id=maker_order_id,
                qty=filled,
                mode="maker",
                limit_price=float(limit_price),
                fill_price=_fill_price(latest_order),
                maker_order_id=maker_order_id,
            )
        if status in _CANCELLED:
            break
        if attempt + 1 < attempts:
            await sleep(max(0.0, poll_sec))

    status = _order_status(latest_order)
    cancel_confirmed = status in _CANCELLED
    if not cancel_confirmed:
        try:
            cancelled = await asyncio.to_thread(client.cancel_order, symbol, maker_order_id)
        except Exception as exc:
            return MakerExecutionResult(
                False,
                maker_order_id=maker_order_id,
                limit_price=limit_price,
                reason=f"maker_cancel_failed:{exc}",
            )
        if not cancelled:
            return MakerExecutionResult(
                False,
                maker_order_id=maker_order_id,
                limit_price=limit_price,
                reason=(f"maker_status_unknown:{status_error}" if status_error else "maker_cancel_failed"),
            )
        await sleep(max(0.0, cancel_settle_sec))
        try:
            latest_order = await asyncio.to_thread(client.get_order, symbol, maker_order_id)
        except Exception as exc:
            return MakerExecutionResult(
                False,
                maker_order_id=maker_order_id,
                limit_price=limit_price,
                reason=f"maker_cancel_unconfirmed:{exc}",
            )
        status = _order_status(latest_order)
        cancel_confirmed = status in _CANCELLED or status in _DONE

    try:
        position_size, position_side, _, _, _, position_avg = await asyncio.to_thread(
            client.get_position_summary, symbol
        )
    except Exception as exc:
        return MakerExecutionResult(
            False,
            maker_order_id=maker_order_id,
            limit_price=limit_price,
            cancel_confirmed=cancel_confirmed,
            reason=f"maker_position_unknown:{exc}",
        )

    filled = max(_filled_qty(latest_order), max(0.0, _finite_float(position_size)))
    expected_side = "buy" if str(side).lower() in {"buy", "long"} else "sell"
    if filled > 0.0:
        if position_side and str(position_side).strip().lower() != expected_side:
            return MakerExecutionResult(
                False,
                maker_order_id=maker_order_id,
                limit_price=limit_price,
                cancel_confirmed=cancel_confirmed,
                reason="maker_position_side_mismatch",
            )
        return MakerExecutionResult(
            True,
            order_id=maker_order_id,
            qty=filled,
            mode="maker_partial" if status not in _DONE else "maker",
            limit_price=float(limit_price),
            fill_price=_fill_price(latest_order) or (_finite_float(position_avg) or None),
            maker_order_id=maker_order_id,
            cancel_confirmed=cancel_confirmed,
        )

    if not cancel_confirmed:
        return MakerExecutionResult(
            False,
            maker_order_id=maker_order_id,
            limit_price=limit_price,
            reason="maker_cancel_unconfirmed",
        )

    try:
        price_now = float(await asyncio.to_thread(client.get_last_price, symbol))
    except Exception as exc:
        return MakerExecutionResult(
            False,
            maker_order_id=maker_order_id,
            limit_price=limit_price,
            cancel_confirmed=True,
            reason=f"fallback_price_failed:{exc}",
        )
    risk = assess_entry_risk(
        side=side,
        qty=float(submitted_qty),
        planned_entry=reference_price,
        actual_entry=price_now,
        stop_price=stop_price,
        max_risk_expansion=max_risk_expansion,
        max_adverse_bps=max_adverse_bps,
    )
    if not risk.allowed:
        return MakerExecutionResult(
            False,
            maker_order_id=maker_order_id,
            limit_price=limit_price,
            cancel_confirmed=True,
            reason=f"fallback_blocked:{risk.reason}",
            risk=risk,
        )

    try:
        fallback_id, fallback_qty = await asyncio.to_thread(
            client.place_market,
            symbol,
            side,
            float(submitted_qty),
            False,
        )
    except Exception as exc:
        return MakerExecutionResult(
            False,
            maker_order_id=maker_order_id,
            limit_price=limit_price,
            cancel_confirmed=True,
            reason=f"fallback_submit_failed:{exc}",
            risk=risk,
        )
    return MakerExecutionResult(
        True,
        order_id=str(fallback_id),
        qty=float(fallback_qty),
        mode="market_fallback",
        limit_price=float(limit_price),
        fill_price=price_now,
        maker_order_id=maker_order_id,
        cancel_confirmed=True,
        risk=risk,
    )
