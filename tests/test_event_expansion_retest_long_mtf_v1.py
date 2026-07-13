from __future__ import annotations

import json
from dataclasses import replace

import pytest

import strategies.event_expansion_retest_long_mtf_v1 as mod


M5, M15, H1 = mod.M5, mod.M15, mod.H1
PROVIDER_SHA = "a" * 64
SYMBOL = "TESTUSDT"
GOLDEN_M15_BARS = (
    (111.0, 111.2, 110.45, 110.8),
    (110.8, 111.1, 110.45, 110.9),
    (110.8, 110.9, 109.85, 110.10),
    (110.3, 110.7, 110.22, 110.5),
    (110.5, 110.6, 110.15, 110.3),
    (110.3, 110.7, 110.25, 110.4),
    (110.4, 110.9, 110.30, 110.6),
    (110.6, 111.8, 110.50, 111.5),
)


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
    return mod.process_closed_m5_prefix(
        SYMBOL, rows, as_of_ms=rows[-1][0] + M5,
        provider_identity="synthetic", provider_fingerprint=PROVIDER_SHA,
        prior=prior,
    )


def _append_m15(rows, o, h, low, c):
    rows.extend(_m15_children(rows[-1][0] + M5, o, h, low, c))


def _golden_path():
    rows = _through_expansion()
    step = _step(rows)
    assert step.state.active is not None
    stages = [step.state.active.stage]
    for bar in GOLDEN_M15_BARS:
        _append_m15(rows, *bar)
        step = _step(rows, step.state)
        assert step.state.active is not None
        stages.append(step.state.active.stage)
    return rows, step, stages


def test_exact_mtf_sequence_is_causal_distinct_and_long_only() -> None:
    rows, step, stages = _golden_path()
    assert stages == [
        mod.MTFStage.EXPANDED,
        mod.MTFStage.EXPANDED,
        mod.MTFStage.HELD_ABOVE,
        mod.MTFStage.FIRST_RETEST_CONSUMED,
        mod.MTFStage.FIRST_RETEST_CONSUMED,
        mod.MTFStage.FIRST_RETEST_CONSUMED,
        mod.MTFStage.FIRST_RETEST_CONSUMED,
        mod.MTFStage.HIGHER_LOW_CONFIRMED,
        mod.MTFStage.PLAN_EMITTED,
    ]
    plan = step.plan
    assert plan is not None and plan.side == "long" and plan.executable is False
    assert plan.known_at_ms == plan.bos_bar_open_ts_ms + M15
    assert plan.valid_from_m5_open_ts_ms == plan.known_at_ms == rows[-1][0] + M5
    assert plan.valid_until_m5_open_ts_ms == plan.valid_from_m5_open_ts_ms + M5
    assert plan.stop_price < min(
        step.state.active.first_retest_low,
        step.state.active.event.level_snapshot.zone_low,
    )
    assert plan.tp1_price == pytest.approx(plan.entry_reference + plan.risk_distance)
    assert plan.tp2_price == pytest.approx(plan.entry_reference + 2 * plan.risk_distance)
    assert step.state.active.higher_low_open_ts_ms != step.state.active.first_retest_open_ts_ms
    assert plan.known_at_ms == step.state.active.higher_low_confirmed_at_ms + M15
    with pytest.raises(mod.MTFContractError, match="long-only"):
        replace(plan, side="short")


def test_level_is_frozen_before_h1_expansion_and_uses_aggregation_receipt() -> None:
    step = _step(_through_expansion())
    event = step.state.active.event
    snapshot = event.level_snapshot
    assert event.known_at_ms == event.expansion_open_ts_ms + H1
    assert snapshot.source_end_close_ms <= event.expansion_open_ts_ms
    assert snapshot.flipped_at_ms == event.known_at_ms
    assert snapshot.source_provenance.mode == "closed_bar_aggregation_v1"
    assert snapshot.source_provenance.output_timeframe == snapshot.timeframe
    assert event.h1_source_sha256 != event.h1_output_sha256


def test_first_m15_retest_is_durably_consumed_and_cannot_be_rescued() -> None:
    rows = _through_expansion()
    step = _step(rows)
    for bar in (
        (111.0, 111.2, 110.45, 110.8),
        (110.8, 111.1, 110.45, 110.9),
    ):
        _append_m15(rows, *bar)
        step = _step(rows, step.state)
    _append_m15(rows, 110.8, 110.9, 109.2, 109.4)
    step = _step(rows, step.state)
    assert step.state.active.stage == mod.MTFStage.INVALIDATED
    assert step.reason in {"first_retest_failed", "flip_close_failed"}
    assert len(step.state.consumed_retest_ids) == 1
    consumed = step.state.consumed_retest_ids

    _append_m15(rows, 110.0, 110.8, 109.9, 110.4)
    later = _step(rows, step.state)
    assert later.plan is None and later.state.consumed_retest_ids == consumed


def test_restart_duplicate_and_history_mutation_fail_closed() -> None:
    rows, step, _ = _golden_path()
    assert step.plan is not None and len(step.state.plan_outbox) == 1
    encoded = mod.state_to_json(step.state)
    restored = mod.state_from_json(
        encoded, expected_provider_fingerprint=PROVIDER_SHA,
        expected_cfg=mod.EventExpansionRetestLongMTFConfigV1(),
    )
    duplicate = _step(rows, restored)
    assert duplicate.plan is None
    assert duplicate.state.plan_outbox == restored.plan_outbox

    mutated = [list(row) for row in rows]
    mutated[100][2] += 0.01
    with pytest.raises(mod.MTFContractError, match="historical M5 prefix changed"):
        _step(mutated, restored)

    acknowledged = mod.acknowledge_plan(restored, restored.plan_outbox[0].plan_id)
    assert not acknowledged.plan_outbox
    assert len(acknowledged.acknowledged_plan_ids) == 1


def test_gap_open_tail_and_future_mutation_are_rejected_or_irrelevant() -> None:
    prefix = _through_expansion()
    before = _step(prefix)
    future = _m15_children(prefix[-1][0] + M5, 111.0, 999.0, 0.5, 500.0)
    future[0][2] = 1_234.0
    again = _step(prefix)
    assert before.state.active.event.event_id == again.state.active.event.event_id
    with pytest.raises(mod.MTFContractError, match="exact final M5 close"):
        mod.process_closed_m5_prefix(
            SYMBOL, prefix + future, as_of_ms=prefix[-1][0] + M5,
            provider_identity="synthetic", provider_fingerprint=PROVIDER_SHA,
        )

    gappy = list(prefix)
    del gappy[20]
    with pytest.raises(mod.MTFContractError, match="gap"):
        mod.process_closed_m5_prefix(
            SYMBOL, gappy, as_of_ms=prefix[-1][0] + M5,
            provider_identity="synthetic", provider_fingerprint=PROVIDER_SHA,
        )


def test_no_same_bar_collapse_when_replaying_multiple_new_m15_after_restart() -> None:
    rows = _through_expansion()
    first = _step(rows)
    # Add hold, hold and a failing first retest while the process is down.
    _append_m15(rows, 111.0, 111.2, 110.45, 110.8)
    _append_m15(rows, 110.8, 111.1, 110.45, 110.9)
    _append_m15(rows, 110.8, 110.9, 109.2, 109.4)
    replayed = _step(rows, first.state)
    assert replayed.state.active.stage == mod.MTFStage.INVALIDATED
    assert len(replayed.state.consumed_retest_ids) == 1
    assert replayed.plan is None


def test_partial_h4_tail_is_explicitly_excluded_from_level_evidence() -> None:
    rows = _through_expansion()
    _append_m15(rows, 111.0, 111.2, 110.45, 110.8)
    explicit_as_of = rows[-1][0] + M5
    h4_boundary = explicit_as_of - explicit_as_of % mod.H4
    receipt = mod._aggregate_to(
        rows, boundary_ms=h4_boundary, timeframe="H4",
        provider_identity="synthetic", provider_fingerprint=PROVIDER_SHA,
    )
    assert receipt is not None
    assert receipt.source_end_close_ts_ms == h4_boundary == 60 * H1
    assert receipt.as_of_ms == h4_boundary
    assert all(bar[0] + mod.H4 <= h4_boundary for bar in receipt.output_bars)


def test_corrupted_checksum_provider_config_and_timeframe_pins_fail_closed() -> None:
    state = _step(_through_expansion()).state
    encoded = mod.state_to_json(state)
    with pytest.raises(mod.MTFContractError, match="provider/config mismatch"):
        mod.state_from_json(
            encoded, expected_provider_fingerprint="b" * 64,
            expected_cfg=mod.EventExpansionRetestLongMTFConfigV1(),
        )
    with pytest.raises(mod.MTFContractError, match="provider/config mismatch"):
        mod.state_from_json(
            encoded, expected_provider_fingerprint=PROVIDER_SHA,
            expected_cfg=mod.EventExpansionRetestLongMTFConfigV1(min_volume_multiple=1.30),
        )

    corrupted = json.loads(encoded)
    corrupted["payload"]["source_count"] += 1
    with pytest.raises(mod.MTFContractError, match="checksum"):
        mod.state_from_json(
            json.dumps(corrupted), expected_provider_fingerprint=PROVIDER_SHA,
            expected_cfg=mod.EventExpansionRetestLongMTFConfigV1(),
        )

    wrong_tf = json.loads(encoded)
    wrong_tf["payload"]["aggregation_config_fingerprints"][0][0] = "M5"
    wrong_tf["payload_sha256"] = mod._sha(wrong_tf["payload"])
    with pytest.raises(mod.MTFContractError, match="timeframe/config"):
        mod.state_from_json(
            json.dumps(wrong_tf), expected_provider_fingerprint=PROVIDER_SHA,
            expected_cfg=mod.EventExpansionRetestLongMTFConfigV1(),
        )


def test_restart_replay_with_new_m5_gap_fails_before_any_stage_transition() -> None:
    rows = _through_expansion()
    first = _step(rows)
    _append_m15(rows, 111.0, 111.2, 110.45, 110.8)
    del rows[-2]
    with pytest.raises(mod.MTFContractError, match="gap"):
        _step(rows, first.state)


def test_outer_state_is_strictly_bound_to_active_event_watermarks_and_span() -> None:
    state = _step(_through_expansion()).state
    assert state.active is not None

    with pytest.raises(mod.MTFContractError, match="symbol/provider/config"):
        mod._validate_state(replace(state, symbol="OTHERUSDT"))
    with pytest.raises(mod.MTFContractError, match="symbol/provider/config"):
        mod._validate_state(replace(state, provider_fingerprint="b" * 64))
    with pytest.raises(mod.MTFContractError, match="symbol/provider/config"):
        mod._validate_state(replace(state, config_sha256="b" * 64))
    with pytest.raises(mod.MTFContractError, match="active M15 watermark"):
        mod._validate_state(
            replace(state, active=replace(state.active, last_m15_close_ms=state.active.last_m15_close_ms + 1))
        )
    with pytest.raises(mod.MTFContractError, match="exact floor"):
        mod._validate_state(replace(state, m15_watermark_close_ms=state.m15_watermark_close_ms - M15))
    with pytest.raises(mod.MTFContractError, match="count/span"):
        mod._validate_state(replace(state, source_count=state.source_count + 1))
    with pytest.raises(mod.MTFContractError, match="canonical 32-character"):
        mod._validate_state(replace(state, seen_event_ids=("g" * 32,)))


def test_outer_state_is_strictly_bound_to_each_outbox_plan_and_seen_event() -> None:
    _, step, _ = _golden_path()
    state = step.state
    assert state.plan_outbox

    with pytest.raises(mod.MTFContractError, match="outbox plan.*symbol/config"):
        mod._validate_state(replace(state, active=None, config_sha256="b" * 64))
    with pytest.raises(mod.MTFContractError, match="absent from durable seen"):
        mod._validate_state(replace(state, active=None, seen_event_ids=()))


def test_rehashed_malicious_envelope_still_cannot_break_nested_state_links() -> None:
    state = _step(_through_expansion()).state
    envelope = json.loads(mod.state_to_json(state))
    envelope["payload"]["symbol"] = "OTHERUSDT"
    envelope["payload_sha256"] = mod._sha(envelope["payload"])
    with pytest.raises(mod.MTFContractError, match="symbol/provider/config"):
        mod.state_from_json(
            json.dumps(envelope), expected_provider_fingerprint=PROVIDER_SHA,
            expected_cfg=mod.EventExpansionRetestLongMTFConfigV1(),
        )

    envelope = json.loads(mod.state_to_json(state))
    envelope["payload"]["m15_watermark_close_ms"] -= M15
    envelope["payload_sha256"] = mod._sha(envelope["payload"])
    with pytest.raises(mod.MTFContractError, match="exact floor"):
        mod.state_from_json(
            json.dumps(envelope), expected_provider_fingerprint=PROVIDER_SHA,
            expected_cfg=mod.EventExpansionRetestLongMTFConfigV1(),
        )


def test_downtime_replay_freezes_at_plan_then_resumes_same_tail_only_after_ack() -> None:
    from bot.event_long_mtf_execution_bridge_v1 import bridge_mtf_research_plan_v1

    rows = _through_expansion()
    before_downtime = _step(rows)
    for bar in GOLDEN_M15_BARS:
        _append_m15(rows, *bar)
    expected_plan_boundary = rows[-1][0] + M5
    # These bars are already present when the process wakes, but they must not
    # be observed in the same transaction that discovers the plan.
    _append_m15(rows, 111.5, 112.0, 111.1, 111.8)
    _append_m15(rows, 111.8, 112.2, 111.4, 112.0)
    full_as_of = rows[-1][0] + M5

    caught_up = _step(rows, before_downtime.state)
    assert caught_up.plan is not None
    assert caught_up.plan.known_at_ms == expected_plan_boundary
    assert caught_up.state.m5_watermark_close_ms == expected_plan_boundary
    assert caught_up.state.m15_watermark_close_ms == expected_plan_boundary
    assert caught_up.state.source_count < len(rows)
    assert caught_up.state.source_count * M5 == expected_plan_boundary
    bridged = bridge_mtf_research_plan_v1(caught_up.plan, caught_up.state)
    assert bridged.receipt.m5_watermark_close_ms == expected_plan_boundary

    with pytest.raises(mod.MTFContractError, match="durably acknowledged"):
        _step(rows, caught_up.state)

    acknowledged = mod.acknowledge_plan(caught_up.state, caught_up.plan.plan_id)
    resumed = _step(rows, acknowledged)
    assert resumed.plan is None
    assert resumed.state.m5_watermark_close_ms == full_as_of
    assert resumed.state.source_count == len(rows)
    assert resumed.state.acknowledged_plan_ids == (caught_up.plan.plan_id,)
