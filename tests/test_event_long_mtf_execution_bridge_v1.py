from __future__ import annotations

from dataclasses import fields, replace

import pytest

from bot.event_long_execution_v1 import (
    make_frozen_long_plan_v1,
    simulate_frozen_long_plan_v1,
    verify_trade_receipt_v1,
)
from bot.event_long_mtf_execution_bridge_v1 import (
    BRIDGE_STATUS,
    EventLongMTFBridgeError,
    PENDING_OUTBOX_DELIVERY_REQUIREMENT,
    bridge_mtf_research_plan_v1,
)
import strategies.event_expansion_retest_long_mtf_v1 as mtf


M5, M15, H1 = mtf.M5, mtf.M15, mtf.H1
PROVIDER_SHA = "a" * 64
SYMBOL = "TESTUSDT"


def _children(ts, o, h, low, c, volume):
    rows = []
    previous = o
    for child in range(12):
        close = o + (c - o) * (child + 1) / 12
        high = max(previous, close) + 0.03
        child_low = min(previous, close) - 0.03
        if child == 3:
            high = h
        if child == 4:
            child_low = low
        rows.append([ts + child * M5, previous, high, child_low, close, volume / 12])
        previous = close
    return rows


def _m15_children(ts, o, h, low, c, volume=300.0):
    rows = []
    previous = o
    for child in range(3):
        close = o + (c - o) * (child + 1) / 3
        child_high = max(previous, close) + 0.02
        child_low = min(previous, close) - 0.02
        if child == 1:
            child_high = max(h, previous, close)
            child_low = min(low, previous, close)
        rows.append([ts + child * M5, previous, child_high, child_low, close, volume / 3])
        previous = close
    return rows


def _through_expansion():
    rows = []
    for index in range(60):
        close = 107.0
        high = 110.0 if index in {10, 25, 40} else close + 0.4
        rows.extend(_children(index * H1, close, high, close - 0.65, close, 1_200.0))
    rows.extend(_children(60 * H1, 107.0, 111.5, 106.8, 111.0, 3_600.0))
    return rows


def _step(rows, prior=None):
    return mtf.process_closed_m5_prefix(
        SYMBOL,
        rows,
        as_of_ms=rows[-1][0] + M5,
        provider_identity="synthetic",
        provider_fingerprint=PROVIDER_SHA,
        prior=prior,
    )


def _append_m15(rows, o, h, low, c):
    rows.extend(_m15_children(rows[-1][0] + M5, o, h, low, c))


def _golden_path():
    rows = _through_expansion()
    step = _step(rows)
    for bar in (
        (111.0, 111.2, 110.45, 110.8),
        (110.8, 111.1, 110.45, 110.9),
        (110.8, 110.9, 109.85, 110.10),
        (110.3, 110.7, 110.22, 110.5),
        (110.5, 110.6, 110.15, 110.3),
        (110.3, 110.7, 110.25, 110.4),
        (110.4, 110.9, 110.30, 110.6),
        (110.6, 111.8, 110.50, 111.5),
    ):
        _append_m15(rows, *bar)
        step = _step(rows, step.state)
    assert step.plan is not None
    assert step.state.active is not None
    assert step.state.active.stage == mtf.MTFStage.PLAN_EMITTED
    return rows, step


def _unsafe_replace(instance, **updates):
    """Model a decoder that bypassed a frozen dataclass's post-init hook."""
    clone = object.__new__(type(instance))
    for item in fields(instance):
        object.__setattr__(
            clone,
            item.name,
            updates.get(item.name, getattr(instance, item.name)),
        )
    return clone


def test_bridge_is_deterministic_complete_and_keeps_plan_identities_distinct() -> None:
    _, step = _golden_path()
    first = bridge_mtf_research_plan_v1(step.plan, step.state)
    second = bridge_mtf_research_plan_v1(step.plan, step.state)

    assert first == second
    assert first.receipt.status == BRIDGE_STATUS
    assert first.receipt.research_only is True
    assert first.receipt.executable is False
    assert first.receipt.broker_calls is False
    assert first.receipt.performance_claims is False
    assert first.frozen_plan.research_only is True
    assert first.frozen_plan.broker_calls is False
    assert first.frozen_plan.plan_id != first.receipt.mtf_plan_id
    assert first.frozen_plan.source_fingerprint == first.receipt.source_fingerprint
    assert first.receipt.mtf_plan_id == step.plan.plan_id
    assert first.receipt.event_id == step.state.active.event.event_id
    assert first.receipt.level_id == step.state.active.event.level_snapshot.level_id
    assert first.receipt.level_snapshot_id == step.state.active.event.level_snapshot.snapshot_id
    assert first.receipt.raw_m5_source_sha256 == step.state.source_sha256
    assert first.receipt.h1_source_sha256 == step.state.active.event.h1_source_sha256
    assert first.receipt.m15_source_sha256 == step.plan.m15_source_sha256
    assert first.receipt.valid_from_m5_open_ts_ms == step.plan.known_at_ms
    assert first.receipt.m5_watermark_close_ms == step.plan.known_at_ms
    assert first.frozen_plan.frozen_stop == step.plan.stop_price


def test_bridge_rejects_acknowledged_missing_or_nonmatching_atomic_outbox() -> None:
    _, step = _golden_path()
    acknowledged = mtf.acknowledge_plan(step.state, step.plan.plan_id)
    with pytest.raises(EventLongMTFBridgeError, match="atomic outbox"):
        bridge_mtf_research_plan_v1(step.plan, acknowledged)

    without_active = replace(step.state, active=None)
    with pytest.raises(EventLongMTFBridgeError, match="outer active state"):
        bridge_mtf_research_plan_v1(step.plan, without_active)


def test_bridge_rejects_late_conversion_after_exact_next_open_was_observed() -> None:
    rows, step = _golden_path()
    prior = step.state
    next_open = rows[-1][0] + M5
    rows.append([next_open, 111.5, 111.7, 111.3, 111.6, 100.0])
    late = _step(rows, prior)
    assert late.state.plan_outbox == prior.plan_outbox
    assert late.state.m5_watermark_close_ms == step.plan.known_at_ms + M5
    assert "freeze source advancement" in PENDING_OUTBOX_DELIVERY_REQUIREMENT
    assert "only then atomically" in PENDING_OUTBOX_DELIVERY_REQUIREMENT
    with pytest.raises(EventLongMTFBridgeError, match="exact closed-M15 / next-M5"):
        bridge_mtf_research_plan_v1(step.plan, late.state)


def test_bridge_revalidates_plan_event_and_level_after_decoder_tamper() -> None:
    _, step = _golden_path()
    short = _unsafe_replace(step.plan, side="short")
    tampered_short_state = replace(step.state, plan_outbox=(short,))
    with pytest.raises(EventLongMTFBridgeError, match="long-only"):
        bridge_mtf_research_plan_v1(short, tampered_short_state)

    event = step.state.active.event
    bad_event = _unsafe_replace(event, h1_output_sha256="b" * 64)
    bad_active = replace(step.state.active, event=bad_event)
    bad_event_state = replace(step.state, active=bad_active)
    with pytest.raises(EventLongMTFBridgeError, match="event_id"):
        bridge_mtf_research_plan_v1(step.plan, bad_event_state)

    level = event.level_snapshot
    bad_level = _unsafe_replace(level, lifecycle="resistance", flipped_at_ms=None)
    level_event = _unsafe_replace(event, level_snapshot=bad_level)
    level_active = replace(step.state.active, event=level_event)
    bad_level_state = replace(step.state, active=level_active)
    with pytest.raises(EventLongMTFBridgeError, match="event/level"):
        bridge_mtf_research_plan_v1(step.plan, bad_level_state)


def test_receipt_and_result_detect_post_bridge_tamper() -> None:
    _, step = _golden_path()
    bridged = bridge_mtf_research_plan_v1(step.plan, step.state)

    with pytest.raises(EventLongMTFBridgeError, match="does not bind evidence"):
        replace(bridged.receipt, m15_source_sha256="b" * 64)
    with pytest.raises(EventLongMTFBridgeError, match="long-only"):
        replace(bridged.receipt, side="short")

    foreign = make_frozen_long_plan_v1(
        event_id=bridged.receipt.event_id,
        level_id=bridged.receipt.level_id,
        strategy=bridged.receipt.mtf_strategy,
        symbol=bridged.receipt.symbol,
        signal_open_ts=bridged.receipt.signal_open_ts_ms,
        entry_reference=bridged.receipt.entry_reference,
        frozen_stop=bridged.receipt.frozen_stop,
        source_fingerprint="b" * 64,
    )
    with pytest.raises(EventLongMTFBridgeError, match="not bound"):
        replace(bridged, frozen_plan=foreign)


def test_outer_provider_identity_is_bound_into_the_receipt_fingerprint() -> None:
    _, step = _golden_path()
    baseline = bridge_mtf_research_plan_v1(step.plan, step.state)
    renamed_state = replace(step.state, provider_identity="synthetic-renamed")
    renamed = bridge_mtf_research_plan_v1(step.plan, renamed_state)

    assert renamed.receipt.provider_identity == "synthetic-renamed"
    assert renamed.receipt.source_fingerprint != baseline.receipt.source_fingerprint
    assert renamed.frozen_plan.plan_id != baseline.frozen_plan.plan_id


def test_bridge_output_runs_exact_execution_contract_and_reanchors_at_actual_open() -> None:
    _, step = _golden_path()
    bridged = bridge_mtf_research_plan_v1(step.plan, step.state)
    plan = bridged.frozen_plan
    actual_open = plan.entry_reference + 0.5
    actual_risk = actual_open - plan.frozen_stop
    target_1 = actual_open + actual_risk
    target_2 = actual_open + 2 * actual_risk
    exact_row = [
        plan.valid_from_ts,
        actual_open,
        target_2 + 0.1,
        actual_open - 0.1,
        target_2,
        1_000.0,
    ]
    filled = simulate_frozen_long_plan_v1(
        plan,
        [exact_row],
        as_of_ms=plan.valid_from_ts + M5,
        scenario="base",
    )

    assert filled.status == "filled_closed"
    assert filled.entry_price == actual_open
    assert filled.initial_risk == pytest.approx(actual_risk)
    assert filled.target_1 == pytest.approx(target_1)
    assert filled.target_2 == pytest.approx(target_2)
    assert filled.exit_reason == "tp1_tp2"
    verify_trade_receipt_v1(filled)

    missing = simulate_frozen_long_plan_v1(
        plan,
        [[plan.valid_from_ts + M5, actual_open, actual_open + 0.1,
          actual_open - 0.1, actual_open, 1_000.0]],
        as_of_ms=plan.valid_from_ts + 2 * M5,
        scenario="base",
    )
    assert missing.status == "rejected_missing_exact_next_open"
    assert missing.trade_id is None
