from __future__ import annotations

from dataclasses import replace

import pytest

from bot.event_long_execution_v1 import (
    EventLongExecutionError,
    M5_MS,
    M15_MS,
    make_frozen_long_plan_v1,
    make_historical_funding_event_v1,
    simulate_frozen_long_plan_v1,
    verify_trade_receipt_v1,
)


SIGNAL_OPEN = 100 * M15_MS
VALID_FROM = SIGNAL_OPEN + M15_MS
SOURCE = "a" * 64
FUNDING_SOURCE = "b" * 64


def _plan(**overrides):
    values = {
        "event_id": "event-001",
        "level_id": "level-001",
        "strategy": "event_expansion_retest_long_v1",
        "symbol": "TESTUSDT",
        "signal_open_ts": SIGNAL_OPEN,
        "entry_reference": 100.0,
        "frozen_stop": 95.0,
        "source_fingerprint": SOURCE,
    }
    values.update(overrides)
    return make_frozen_long_plan_v1(**values)


def _row(index, open_=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0):
    return [VALID_FROM + index * M5_MS, open_, high, low, close, volume]


def _run(rows, *, plan=None, scenario="base", funding=()):
    return simulate_frozen_long_plan_v1(
        plan or _plan(),
        rows,
        as_of_ms=int(rows[-1][0]) + M5_MS if rows else VALID_FROM + M5_MS,
        scenario=scenario,
        funding_events=funding,
    )


def _funding(index, rate):
    return make_historical_funding_event_v1(
        symbol="TESTUSDT",
        timestamp_ms=VALID_FROM + index * M5_MS,
        signed_rate=rate,
        source_fingerprint=FUNDING_SOURCE,
    )


def test_m15_open_known_at_and_exact_next_m5_boundary_are_distinct() -> None:
    plan = _plan()
    assert plan.signal_open_ts == SIGNAL_OPEN
    assert plan.signal_known_at_ts == SIGNAL_OPEN + M15_MS
    assert plan.valid_from_ts == plan.signal_known_at_ts
    assert plan.execution_interval_ms == M5_MS
    assert plan.research_only is True and plan.broker_calls is False


def test_missing_exact_next_open_is_rejected_not_shifted_forward() -> None:
    receipt = _run(
        [[VALID_FROM + M5_MS, 100.0, 101.0, 99.0, 100.0, 1000.0]]
    )
    assert receipt.status == "rejected_missing_exact_next_open"
    assert receipt.trade_id is None and receipt.bars_held == 0


def test_actual_open_reanchors_targets_for_favorable_and_adverse_entry_gaps() -> None:
    favorable = _run([_row(0, 98.0, 104.1, 97.0, 103.0)])
    assert favorable.entry_price == 98.0
    assert favorable.initial_risk == 3.0
    assert favorable.target_1 == 101.0 and favorable.target_2 == 104.0
    assert favorable.exit_reason == "tp1_tp2" and favorable.gross_r == 1.5

    adverse = _run([_row(0, 104.0, 105.0, 103.0, 104.0)])
    assert adverse.status == "censored_snapshot_end"
    assert adverse.initial_risk == 9.0
    assert adverse.target_1 == 113.0 and adverse.target_2 == 122.0


def test_entry_open_at_or_through_frozen_stop_is_an_execution_rejection() -> None:
    receipt = _run([_row(0, 94.0, 96.0, 93.0, 95.0)])
    assert receipt.status == "rejected_gap_through_frozen_stop"
    assert receipt.trade_id is None and receipt.cost_legs == ()


def test_same_bar_target_stop_ambiguity_is_stop_first() -> None:
    receipt = _run([_row(0, 100.0, 111.0, 94.0, 108.0)])
    assert receipt.status == "filled_closed"
    assert receipt.exit_reason == "stop"
    assert receipt.gross_r == -1.0
    assert [leg.reason for leg in receipt.cost_legs] == ["actual_next_open", "stop"]


def test_later_adverse_stop_gap_fills_at_actual_open() -> None:
    rows = [
        _row(0),
        _row(1, 93.0, 94.0, 92.0, 93.0),
    ]
    receipt = _run(rows)
    assert receipt.exit_reason == "stop_gap"
    exit_leg = receipt.cost_legs[-1]
    assert exit_leg.price == 93.0
    assert exit_leg.unit_r == pytest.approx(-1.4)
    assert receipt.gross_r == pytest.approx(-1.4)


def test_tp1_then_stop_and_tp1_then_tp2_paths() -> None:
    stopped = _run(
        [
            _row(0, 100.0, 105.1, 99.0, 104.0),
            _row(1, 100.0, 101.0, 94.0, 96.0),
        ]
    )
    assert stopped.exit_reason == "tp1_then_stop"
    assert stopped.gross_r == pytest.approx(0.0)
    assert [leg.fraction for leg in stopped.cost_legs] == [1.0, 0.5, 0.5]

    won = _run(
        [
            _row(0, 100.0, 105.1, 99.0, 104.0),
            _row(1, 104.0, 110.1, 103.0, 109.0),
        ]
    )
    assert won.exit_reason == "tp1_tp2"
    assert won.gross_r == pytest.approx(1.5)
    assert won.remaining_fraction == 0.0


def test_max_hold_is_exactly_96_m5_bars_with_or_without_tp1() -> None:
    flat = [_row(index, 100.0, 101.0, 99.0, 101.0) for index in range(96)]
    receipt = _run(flat)
    assert receipt.exit_reason == "max_hold" and receipt.bars_held == 96
    assert receipt.exit_ts == VALID_FROM + 95 * M5_MS
    assert receipt.gross_r == pytest.approx(0.2)

    partial = [_row(0, 100.0, 105.1, 99.0, 104.0)]
    partial.extend(
        _row(index, 104.0, 104.5, 99.0, 102.0) for index in range(1, 96)
    )
    receipt = _run(partial)
    assert receipt.exit_reason == "tp1_then_max_hold" and receipt.bars_held == 96
    assert receipt.gross_r == pytest.approx(0.7)
    assert [leg.fraction for leg in receipt.cost_legs] == [1.0, 0.5, 0.5]


def test_partial_exit_fee_and_slippage_are_charged_per_actual_leg_not_twice_full() -> None:
    receipt = _run([_row(0, 100.0, 111.0, 99.0, 109.0)])
    assert receipt.gross_r == 1.5
    # 6 bps fee and 2 bps slip: entry 100 plus half of 105 and 110,
    # all divided by the initial $5 risk.
    assert receipt.fee_cost_r == pytest.approx(0.0249)
    assert receipt.slippage_cost_r == pytest.approx(0.0083)
    assert receipt.net_r == pytest.approx(1.4668)

    stress = _run([_row(0, 100.0, 111.0, 99.0, 109.0)], scenario="stress")
    assert stress.fee_cost_r == pytest.approx(0.0415)
    assert stress.slippage_cost_r == pytest.approx(0.02075)
    assert stress.trade_id == receipt.trade_id
    assert stress.net_r < receipt.net_r


def test_exact_signed_funding_uses_position_fraction_and_stress_policy() -> None:
    rows = [
        _row(0, 100.0, 105.1, 99.0, 104.0),  # TP1; funding at entry is excluded.
        _row(1, 100.0, 101.0, 99.0, 100.0),
        _row(2, 100.0, 110.1, 99.0, 109.0),
    ]
    events = (
        _funding(0, 0.01),
        _funding(1, 0.0001),
        _funding(2, -0.0002),
    )
    base = _run(rows, funding=events)
    assert len(base.funding_charges) == 2
    assert [charge.position_fraction for charge in base.funding_charges] == [0.5, 0.5]
    assert base.funding_pnl_r == pytest.approx(0.001)
    assert [charge.applied_signed_rate for charge in base.funding_charges] == [
        pytest.approx(0.0001), pytest.approx(-0.0002)
    ]

    stress = _run(rows, scenario="stress", funding=events)
    assert stress.funding_pnl_r == pytest.approx(-0.005)
    assert [charge.applied_signed_rate for charge in stress.funding_charges] == [
        pytest.approx(0.0005), pytest.approx(0.0)
    ]


def test_contiguous_closed_m5_only_and_no_future_funding() -> None:
    with pytest.raises(EventLongExecutionError, match="gappy"):
        _run([_row(0), _row(2)])

    with pytest.raises(EventLongExecutionError, match="open or future"):
        simulate_frozen_long_plan_v1(
            _plan(), [_row(0)], as_of_ms=VALID_FROM, scenario="base"
        )

    future = _funding(2, 0.0001)
    with pytest.raises(EventLongExecutionError, match="future funding"):
        _run([_row(0)], funding=(future,))


def test_plan_trade_receipt_and_funding_ids_fail_closed_on_tamper() -> None:
    plan = _plan()
    again = _plan()
    assert plan.plan_id == again.plan_id
    with pytest.raises(EventLongExecutionError, match="plan_id"):
        replace(plan, frozen_stop=94.0)
    with pytest.raises(EventLongExecutionError, match="long-only"):
        replace(plan, side="short")

    receipt = _run([_row(0, 100.0, 111.0, 99.0, 109.0)], plan=plan)
    same = _run([_row(0, 100.0, 111.0, 99.0, 109.0)], plan=again)
    assert receipt.trade_id == same.trade_id
    assert receipt.receipt_sha256 == same.receipt_sha256
    verify_trade_receipt_v1(receipt)
    with pytest.raises(EventLongExecutionError, match="checksum"):
        replace(receipt, strategy="tampered")

    event = _funding(1, 0.0001)
    with pytest.raises(EventLongExecutionError, match="funding_id"):
        replace(event, signed_rate=0.0002)
