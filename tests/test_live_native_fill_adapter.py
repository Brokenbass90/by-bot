from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from bot.live_native_decision_contract import (
    ContractViolation,
    FillRebasePolicy,
    LiveNativeDecisionPlan,
)
from bot.live_native_fill_adapter import (
    LIVE_NATIVE_FILL_ADAPTER_ENABLED_BY_DEFAULT,
    adapt_bybit_finalized_entry_fill,
    adapt_next_open_replay_fill,
)


CLOSED_H1_TS_MS = 1_800_000_000_000


def _plan() -> LiveNativeDecisionPlan:
    return LiveNativeDecisionPlan(
        spec_id="att1-live-native-v2",
        sleeve_id="ATT1",
        symbol="BTCUSDT",
        side="short",
        closed_h1_ts_ms=CLOSED_H1_TS_MS,
        planned_entry=Decimal("100"),
        frozen_sl=Decimal("110"),
        planned_tps=(Decimal("88"), Decimal("75")),
        tp_fractions=(Decimal("0.55"), Decimal("0.45")),
        residual_fraction=Decimal("0"),
        time_stop_hours=336,
        config_hash="1" * 64,
        source_hash="2" * 64,
        data_hash="3" * 64,
    )


def _policy(plan: LiveNativeDecisionPlan, **updates: object) -> FillRebasePolicy:
    values: dict[str, object] = {
        "spec_id": plan.spec_id,
        "profile_hash": plan.profile_hash,
        "tick_size": Decimal("0.10"),
        "max_adverse_risk_expansion": Decimal("0.20"),
        "max_fill_age_ms": 300_000,
        "max_finalize_delay_ms": 60_000,
    }
    values.update(updates)
    return FillRebasePolicy(**values)  # type: ignore[arg-type]


def _order(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "orderId": "order-att1-1",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "orderStatus": "Filled",
        "reduceOnly": False,
        "cumExecQty": "1.0",
        "leavesQty": "0",
        "avgPrice": "99.4",
        "createdTime": str(CLOSED_H1_TS_MS + 50_000),
        "updatedTime": str(CLOSED_H1_TS_MS + 62_000),
    }
    values.update(updates)
    return values


def _executions() -> list[dict[str, object]]:
    return [
        {
            "execId": "exec-a",
            "orderId": "order-att1-1",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "execType": "Trade",
            "execTime": str(CLOSED_H1_TS_MS + 60_000),
            "execPrice": "100",
            "execQty": "0.4",
        },
        {
            "execId": "exec-b",
            "orderId": "order-att1-1",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "execType": "Trade",
            "execTime": str(CLOSED_H1_TS_MS + 61_000),
            "execPrice": "99",
            "execQty": "0.6",
        },
    ]


def _adapt(
    *,
    plan: LiveNativeDecisionPlan | None = None,
    policy: FillRebasePolicy | None = None,
    order: dict[str, object] | None = None,
    executions: list[dict[str, object]] | None = None,
    observed_at_ms: object = CLOSED_H1_TS_MS + 65_000,
    max_observation_lag_ms: object = 10_000,
    avg_price_tolerance: object = "0.00000001",
):
    source = plan or _plan()
    return adapt_bybit_finalized_entry_fill(
        source,
        policy or _policy(source),
        order or _order(),
        _executions() if executions is None else executions,
        expected_order_id="order-att1-1",
        observed_at_ms=observed_at_ms,
        max_observation_lag_ms=max_observation_lag_ms,
        avg_price_tolerance=avg_price_tolerance,  # type: ignore[arg-type]
    )


def test_terminal_order_plus_complete_executions_build_actual_fill() -> None:
    fill = _adapt()

    assert LIVE_NATIVE_FILL_ADAPTER_ENABLED_BY_DEFAULT is False
    assert fill.lifecycle == "finalized"
    assert fill.order_id == "order-att1-1"
    assert fill.fill_id.startswith("bybit-aggregate:")
    assert fill.fill_ts_ms == CLOSED_H1_TS_MS + 61_000
    assert fill.finalized_ts_ms == CLOSED_H1_TS_MS + 62_000
    assert fill.fill_price == Decimal("99.4")
    assert fill.cumulative_filled_qty == Decimal("1.0")
    assert fill.leaves_qty == 0


def test_execution_api_order_does_not_change_aggregate_identity() -> None:
    forward = _adapt()
    reverse = _adapt(executions=list(reversed(_executions())))
    assert reverse.fill_id == forward.fill_id
    assert reverse.fill_fingerprint == forward.fill_fingerprint


def test_position_summary_is_not_terminal_fill_evidence() -> None:
    position = {"symbol": "BTCUSDT", "side": "Sell", "size": "1", "avgPrice": "99.4"}
    with pytest.raises(ContractViolation, match="missing_bybit_fill_field: orderId"):
        _adapt(order=position)


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"orderStatus": "PartiallyFilled"}, "bybit_order_not_filled"),
        ({"orderStatus": "PartiallyFilledCanceled"}, "bybit_order_not_filled"),
        ({"leavesQty": "0.1"}, "bybit_filled_order_has_leaves"),
        ({"reduceOnly": True}, "entry_order_is_reduce_only"),
        ({"side": "Buy"}, "bybit_order_side_mismatch"),
        ({"symbol": "ETHUSDT"}, "bybit_order_symbol_mismatch"),
        ({"orderId": "other"}, "bybit_order_id_mismatch"),
    ],
)
def test_nonfinal_or_wrong_order_fails_closed(updates: dict[str, object], code: str) -> None:
    with pytest.raises(ContractViolation, match=code):
        _adapt(order=_order(**updates))


def test_empty_or_incomplete_execution_page_fails_closed() -> None:
    with pytest.raises(ContractViolation, match="missing_bybit_executions"):
        _adapt(executions=[])

    incomplete = _executions()[:1]
    with pytest.raises(ContractViolation, match="bybit_execution_quantity_mismatch"):
        _adapt(executions=incomplete)


def test_duplicate_execution_id_fails_closed() -> None:
    rows = _executions()
    rows[1]["execId"] = rows[0]["execId"]
    with pytest.raises(ContractViolation, match="duplicate_bybit_execution_id"):
        _adapt(executions=rows)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("orderId", "other", "execution_order_id_mismatch"),
        ("symbol", "ETHUSDT", "execution_symbol_mismatch"),
        ("side", "Buy", "execution_side_mismatch"),
        ("execType", "Funding", "execution_type_not_trade"),
    ],
)
def test_execution_identity_mismatch_fails_closed(field: str, value: str, code: str) -> None:
    rows = _executions()
    rows[0][field] = value
    with pytest.raises(ContractViolation, match=code):
        _adapt(executions=rows)


def test_execution_vwap_must_match_terminal_order_under_explicit_tolerance() -> None:
    with pytest.raises(ContractViolation, match="bybit_execution_vwap_mismatch"):
        _adapt(order=_order(avgPrice="99.5"), avg_price_tolerance="0.01")
    assert _adapt(order=_order(avgPrice="99.5"), avg_price_tolerance="0.10")


def test_policy_rejects_stale_fill_and_slow_finalization() -> None:
    stale_rows = _executions()
    stale_rows[0]["execTime"] = str(CLOSED_H1_TS_MS + 300_001)
    stale_rows[1]["execTime"] = str(CLOSED_H1_TS_MS + 300_001)
    stale_order = _order(updatedTime=str(CLOSED_H1_TS_MS + 300_002))
    with pytest.raises(ContractViolation, match="fill_too_old"):
        _adapt(
            order=stale_order,
            executions=stale_rows,
            observed_at_ms=CLOSED_H1_TS_MS + 300_003,
        )

    slow_rows = _executions()
    slow_rows[0]["execTime"] = str(CLOSED_H1_TS_MS + 1)
    slow_rows[1]["execTime"] = str(CLOSED_H1_TS_MS + 1)
    slow_order = _order(updatedTime=str(CLOSED_H1_TS_MS + 60_002))
    with pytest.raises(ContractViolation, match="fill_finalization_too_slow"):
        _adapt(
            order=slow_order,
            executions=slow_rows,
            observed_at_ms=CLOSED_H1_TS_MS + 60_003,
        )


def test_terminal_observation_age_and_chronology_are_explicit() -> None:
    with pytest.raises(ContractViolation, match="terminal_order_observation_too_old"):
        _adapt(observed_at_ms=CLOSED_H1_TS_MS + 72_001)
    with pytest.raises(ContractViolation, match="order_observed_before_finalization"):
        _adapt(observed_at_ms=CLOSED_H1_TS_MS + 61_999)

    order = _order(updatedTime=str(CLOSED_H1_TS_MS + 60_000))
    with pytest.raises(ContractViolation, match="bybit_finalized_before_last_execution"):
        _adapt(order=order)


def test_integer_timestamps_never_truncate_float_values() -> None:
    order = _order(updatedTime=float(CLOSED_H1_TS_MS + 62_000))
    with pytest.raises(ContractViolation, match="invalid_integer: updatedTime"):
        _adapt(order=order)

    rows = copy.deepcopy(_executions())
    rows[0]["execTime"] = float(CLOSED_H1_TS_MS + 60_000)
    with pytest.raises(ContractViolation, match="invalid_integer: execTime"):
        _adapt(executions=rows)


def test_next_m5_open_replay_fill_is_causal_and_side_adverse() -> None:
    plan = _plan()
    policy = _policy(plan)
    row = [plan.closed_h1_ts_ms, "100", "101", "99", "100.5", "10"]
    raw = json.dumps(row, separators=(",", ":")).encode("ascii")
    fill = adapt_next_open_replay_fill(
        plan,
        policy,
        row,
        row_bytes=raw,
        adverse_slippage_bps="2",
        finalization_delay_ms=5,
    )
    assert fill.fill_price == Decimal("99.98")
    assert fill.fill_ts_ms == plan.closed_h1_ts_ms
    assert fill.finalized_ts_ms == plan.closed_h1_ts_ms + 5


def test_next_m5_open_replay_fill_rejects_wrong_time_or_bytes() -> None:
    plan = _plan()
    policy = _policy(plan)
    late = [plan.closed_h1_ts_ms + 300_000, "100", "101", "99", "100.5", "10"]
    late_raw = json.dumps(late, separators=(",", ":")).encode("ascii")
    with pytest.raises(ContractViolation, match="next_open_not_first_m5"):
        adapt_next_open_replay_fill(
            plan, policy, late, row_bytes=late_raw, adverse_slippage_bps="0"
        )
    first = [plan.closed_h1_ts_ms, "100", "101", "99", "100.5", "10"]
    with pytest.raises(ContractViolation, match="next_open_row_bytes_mismatch"):
        adapt_next_open_replay_fill(
            plan,
            policy,
            first,
            row_bytes=late_raw,
            adverse_slippage_bps="0",
        )
