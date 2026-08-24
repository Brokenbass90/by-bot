"""Pure Bybit terminal-order/execution aggregate to ``ActualFill`` adapter.

Position ``size``/``avgPrice`` is not fill-finality evidence.  This adapter
therefore requires both real shapes already exposed by ``BybitClient``:

* ``get_order``: terminal ``Filled`` order with zero leaves;
* ``get_executions``: the complete, unique execution list for that order.

It performs no API call.  It computes VWAP from executions, checks it against
the order aggregate under an explicit tolerance, and calls the existing
decision/fill policy before returning.  Missing pages, partial/cancelled orders,
position summaries, stale fills, and slow finalization all fail closed.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from bot.live_native_decision_contract import (
    ActualFill,
    ContractViolation,
    FillRebasePolicy,
    LiveNativeDecisionPlan,
    validate_fill_before_rebase,
)


LIVE_NATIVE_FILL_ADAPTER_ENABLED_BY_DEFAULT = False
M5_MS = 5 * 60 * 1000


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("invalid_integer", field)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ContractViolation("invalid_integer", field)
        try:
            number = Decimal(raw)
        except InvalidOperation as exc:
            raise ContractViolation("invalid_integer", field) from exc
    else:
        raise ContractViolation("invalid_integer", field)
    if not number.is_finite() or number != number.to_integral_value():
        raise ContractViolation("invalid_integer", field)
    return int(number)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ContractViolation("invalid_decimal", field)
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid_decimal", field) from exc
    if not number.is_finite():
        raise ContractViolation("non_finite_decimal", field)
    return number


def _nonempty(value: object, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ContractViolation("missing_bybit_fill_field", field)
    return result


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractViolation("noncanonical_bybit_execution_aggregate") from exc


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _entry_side(plan: LiveNativeDecisionPlan) -> str:
    return "Buy" if plan.side == "long" else "Sell"


def _strict_reduce_only(value: object) -> None:
    if not isinstance(value, bool):
        raise ContractViolation("invalid_bybit_reduce_only")
    if value:
        raise ContractViolation("entry_order_is_reduce_only")


def adapt_bybit_finalized_entry_fill(
    plan: LiveNativeDecisionPlan,
    policy: FillRebasePolicy,
    terminal_order: Mapping[str, object],
    executions: Sequence[Mapping[str, object]],
    *,
    expected_order_id: str,
    observed_at_ms: object,
    max_observation_lag_ms: object,
    avg_price_tolerance: Decimal | int | float | str,
) -> ActualFill:
    """Create ``ActualFill`` only from a complete terminal Bybit aggregate."""

    if not isinstance(plan, LiveNativeDecisionPlan):
        raise ContractViolation("invalid_decision_plan")
    if not isinstance(policy, FillRebasePolicy):
        raise ContractViolation("invalid_rebase_policy")
    if not isinstance(terminal_order, Mapping):
        raise ContractViolation("invalid_bybit_terminal_order")
    if isinstance(executions, (str, bytes)) or not isinstance(executions, Sequence):
        raise ContractViolation("invalid_bybit_executions")

    expected_oid = _nonempty(expected_order_id, "expected_order_id")
    order_id = _nonempty(terminal_order.get("orderId"), "orderId")
    if order_id != expected_oid:
        raise ContractViolation("bybit_order_id_mismatch")
    symbol = _nonempty(terminal_order.get("symbol"), "symbol").upper()
    if symbol != plan.symbol:
        raise ContractViolation("bybit_order_symbol_mismatch")
    side = _nonempty(terminal_order.get("side"), "side")
    if side != _entry_side(plan):
        raise ContractViolation("bybit_order_side_mismatch")
    status = _nonempty(terminal_order.get("orderStatus"), "orderStatus").lower()
    if status != "filled":
        raise ContractViolation("bybit_order_not_filled", status)
    if "reduceOnly" not in terminal_order:
        raise ContractViolation("missing_bybit_fill_field", "reduceOnly")
    _strict_reduce_only(terminal_order.get("reduceOnly"))

    order_qty = _decimal(terminal_order.get("cumExecQty"), "cumExecQty")
    leaves_qty = _decimal(terminal_order.get("leavesQty"), "leavesQty")
    order_avg = _decimal(terminal_order.get("avgPrice"), "avgPrice")
    if order_qty <= 0 or order_avg <= 0:
        raise ContractViolation("nonpositive_bybit_order_fill")
    if leaves_qty != 0:
        raise ContractViolation("bybit_filled_order_has_leaves")
    finalized_ts = _strict_int(terminal_order.get("updatedTime"), "updatedTime")
    if finalized_ts <= 0:
        raise ContractViolation("invalid_bybit_finalized_ts")

    observed = _strict_int(observed_at_ms, "observed_at_ms")
    max_lag = _strict_int(max_observation_lag_ms, "max_observation_lag_ms")
    if max_lag < 0:
        raise ContractViolation("negative_max_observation_lag")
    observation_lag = observed - finalized_ts
    if observation_lag < 0:
        raise ContractViolation("order_observed_before_finalization")
    if observation_lag > max_lag:
        raise ContractViolation("terminal_order_observation_too_old")

    tolerance = _decimal(avg_price_tolerance, "avg_price_tolerance")
    if tolerance < 0:
        raise ContractViolation("negative_avg_price_tolerance")
    if not executions:
        raise ContractViolation("missing_bybit_executions")

    expected_side = _entry_side(plan)
    seen_exec_ids: set[str] = set()
    normalized: list[dict[str, object]] = []
    total_qty = Decimal("0")
    total_value = Decimal("0")
    last_exec_ts = 0
    for raw in executions:
        if not isinstance(raw, Mapping):
            raise ContractViolation("invalid_bybit_execution")
        exec_id = _nonempty(raw.get("execId"), "execId")
        if exec_id in seen_exec_ids:
            raise ContractViolation("duplicate_bybit_execution_id", exec_id)
        seen_exec_ids.add(exec_id)
        if _nonempty(raw.get("orderId"), "execution.orderId") != order_id:
            raise ContractViolation("execution_order_id_mismatch")
        if _nonempty(raw.get("symbol"), "execution.symbol").upper() != plan.symbol:
            raise ContractViolation("execution_symbol_mismatch")
        if _nonempty(raw.get("side"), "execution.side") != expected_side:
            raise ContractViolation("execution_side_mismatch")
        if _nonempty(raw.get("execType"), "execution.execType").lower() != "trade":
            raise ContractViolation("execution_type_not_trade")

        exec_ts = _strict_int(raw.get("execTime"), "execTime")
        price = _decimal(raw.get("execPrice"), "execPrice")
        qty = _decimal(raw.get("execQty"), "execQty")
        if exec_ts <= 0 or price <= 0 or qty <= 0:
            raise ContractViolation("invalid_bybit_execution_values")
        total_qty += qty
        total_value += price * qty
        last_exec_ts = max(last_exec_ts, exec_ts)
        normalized.append(
            {
                "exec_id": exec_id,
                "exec_price": _decimal_text(price),
                "exec_qty": _decimal_text(qty),
                "exec_time": exec_ts,
            }
        )

    if total_qty != order_qty:
        raise ContractViolation("bybit_execution_quantity_mismatch")
    if last_exec_ts > finalized_ts:
        raise ContractViolation("bybit_finalized_before_last_execution")
    execution_vwap = total_value / total_qty
    if abs(execution_vwap - order_avg) > tolerance:
        raise ContractViolation("bybit_execution_vwap_mismatch")

    normalized.sort(key=lambda item: (int(item["exec_time"]), str(item["exec_id"])))
    aggregate_hash = hashlib.sha256(
        _canonical_json_bytes(
            {
                "executions": normalized,
                "order_id": order_id,
                "schema_id": "bybit_final_execution_aggregate_v1",
            }
        )
    ).hexdigest()
    fill = ActualFill(
        decision_id=plan.decision_id,
        order_id=order_id,
        fill_id=f"bybit-aggregate:{aggregate_hash}",
        lifecycle="finalized",
        fill_ts_ms=last_exec_ts,
        finalized_ts_ms=finalized_ts,
        fill_price=execution_vwap,
        cumulative_filled_qty=total_qty,
        leaves_qty=leaves_qty,
    )
    validation = validate_fill_before_rebase(plan, fill, policy)
    if not validation.accepted:
        raise ContractViolation(validation.code)
    return fill


def adapt_next_open_replay_fill(
    plan: LiveNativeDecisionPlan,
    policy: FillRebasePolicy,
    next_m5_row: Sequence[object],
    *,
    row_bytes: bytes,
    adverse_slippage_bps: Decimal | int | float | str,
    quantity: Decimal | int | float | str = Decimal("1"),
    finalization_delay_ms: object = 1,
) -> ActualFill:
    """Normalize the first pre-sealed M5 open after a closed-H1 decision."""

    if not isinstance(plan, LiveNativeDecisionPlan):
        raise ContractViolation("invalid_decision_plan")
    if not isinstance(policy, FillRebasePolicy):
        raise ContractViolation("invalid_rebase_policy")
    if isinstance(next_m5_row, (str, bytes)) or not isinstance(next_m5_row, Sequence):
        raise ContractViolation("invalid_next_open_row")
    if len(next_m5_row) < 6 or not isinstance(row_bytes, bytes) or not row_bytes:
        raise ContractViolation("invalid_next_open_row")
    try:
        decoded = json.loads(row_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("invalid_next_open_row_bytes") from exc
    if not isinstance(decoded, list) or decoded != list(next_m5_row):
        raise ContractViolation("next_open_row_bytes_mismatch")

    start_ts = _strict_int(next_m5_row[0], "next_open_ts_ms")
    if start_ts != plan.closed_h1_ts_ms or start_ts % M5_MS != 0:
        raise ContractViolation("next_open_not_first_m5_after_decision")
    raw_open = _decimal(next_m5_row[1], "next_open")
    qty = _decimal(quantity, "quantity")
    slippage = _decimal(adverse_slippage_bps, "adverse_slippage_bps")
    delay = _strict_int(finalization_delay_ms, "finalization_delay_ms")
    if raw_open <= 0 or qty <= 0 or slippage < 0 or delay < 0:
        raise ContractViolation("invalid_replay_fill_values")
    direction = Decimal("1") if plan.side == "long" else Decimal("-1")
    fill_price = raw_open * (Decimal("1") + direction * slippage / Decimal("10000"))
    if fill_price <= 0:
        raise ContractViolation("invalid_replay_fill_values")

    identity_payload = {
        "adverse_slippage_bps": _decimal_text(slippage),
        "decision_id": plan.decision_id,
        "quantity": _decimal_text(qty),
        "row_sha256": hashlib.sha256(row_bytes).hexdigest(),
        "schema_id": "next_m5_open_replay_fill_v1",
    }
    identity = hashlib.sha256(_canonical_json_bytes(identity_payload)).hexdigest()
    fill = ActualFill(
        decision_id=plan.decision_id,
        order_id=f"replay-order:{identity}",
        fill_id=f"replay-fill:{identity}",
        lifecycle="finalized",
        fill_ts_ms=start_ts,
        finalized_ts_ms=start_ts + delay,
        fill_price=fill_price,
        cumulative_filled_qty=qty,
        leaves_qty=Decimal("0"),
    )
    validation = validate_fill_before_rebase(plan, fill, policy)
    if not validation.accepted:
        raise ContractViolation(validation.code)
    return fill


__all__ = [
    "LIVE_NATIVE_FILL_ADAPTER_ENABLED_BY_DEFAULT",
    "adapt_bybit_finalized_entry_fill",
    "adapt_next_open_replay_fill",
]
