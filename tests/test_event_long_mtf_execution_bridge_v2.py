"""Window/aggregate provenance regression; all execution prices synthetic."""
from dataclasses import asdict, replace
from pathlib import Path
import gzip
import hashlib
import json

import pytest

from bot.event_long_mtf_execution_bridge_v1 import (
    bridge_mtf_research_plan_v1, EventLongMTFBridgeError as V1Error,
)
from bot.event_long_mtf_execution_bridge_v2 import (
    bridge_mtf_research_plan_v2, EventLongMTFBridgeError, _verify_source_window,
)
from bot.event_long_execution_v1 import simulate_frozen_long_plan_v1
from strategies import event_expansion_retest_long_mtf_v1 as mtf
from tests.test_event_long_mtf_execution_bridge_v1 import (
    _children, _through_expansion, _append_m15, _step, _golden_path,
    _unsafe_replace, H1, M5,
)


def _long_path():
    # Original 60h fixture did not reach the frozen MTF 120h lookback. Add only
    # prehistory, keeping exactly the existing expansion/retest geometry.
    rows = []
    for i in range(240):
        rows.extend(_children(i * H1, 107., 107.4, 106.35, 107., 1200.))
    for row in _through_expansion():
        rows.append([row[0] + 240 * H1, *row[1:]])
    step = _step(rows)
    for bar in (
        (111.0, 111.2, 110.45, 110.8), (110.8, 111.1, 110.45, 110.9),
        (110.8, 110.9, 109.85, 110.10), (110.3, 110.7, 110.22, 110.5),
        (110.5, 110.6, 110.15, 110.3), (110.3, 110.7, 110.25, 110.4),
        (110.4, 110.9, 110.30, 110.6), (110.6, 111.8, 110.50, 111.5),
    ):
        _append_m15(rows, *bar)
        step = _step(rows, step.state)
    assert step.plan is not None
    level = step.state.active.event.level_snapshot
    assert level.source_provenance.output_count > 240
    assert level.source_provenance.output_sha256 != level.source_bars_sha256
    return rows, step


def test_long_history_level_window_is_not_full_aggregate():
    rows, step = _long_path()
    with pytest.raises(V1Error, match="aggregation evidence"):
        bridge_mtf_research_plan_v1(step.plan, step.state)
    original_plan = asdict(step.plan)
    result = bridge_mtf_research_plan_v2(step.plan, step.state, raw_closed_m5=rows)
    assert result.frozen_plan.entry_reference == step.plan.entry_reference
    assert result.frozen_plan.frozen_stop == step.plan.stop_price
    assert asdict(step.plan) == original_plan
    level = step.state.active.event.level_snapshot
    assert result.receipt.level_window_count == 120
    assert result.receipt.level_window_sha256 == level.source_bars_sha256
    assert result.receipt.level_output_sha256 == level.source_provenance.output_sha256
    assert result.receipt.level_window_sha256 != result.receipt.level_output_sha256
    assert result.receipt.executable is False


def test_short_history_v2_preserves_geometry_and_synthetic_execution_economics():
    rows, step = _golden_path()
    before = mtf.state_to_json(step.state)
    old = bridge_mtf_research_plan_v1(step.plan, step.state)
    new = bridge_mtf_research_plan_v2(step.plan, step.state, raw_closed_m5=rows)
    assert new.receipt.schema.endswith('_v2')
    assert new.frozen_plan.plan_id != old.frozen_plan.plan_id
    assert new.receipt.mtf_plan_id == old.receipt.mtf_plan_id
    assert new.receipt.level_window_sha256 == new.receipt.level_output_sha256
    assert new.receipt.broker_calls is False
    assert new.frozen_plan.research_only is True
    actual = new.frozen_plan.entry_reference + .5
    risk = actual - new.frozen_plan.frozen_stop
    bar = [new.frozen_plan.valid_from_ts, actual, actual + 2*risk + .1,
           actual - .1, actual + 2*risk, 1000.]
    outcomes = [simulate_frozen_long_plan_v1(p.frozen_plan, [bar],
                as_of_ms=bar[0]+M5, scenario='base') for p in (old, new)]
    for field in ('status', 'entry_price', 'initial_risk', 'target_1', 'target_2',
                  'exit_reason', 'gross_r', 'net_r', 'fee_cost_r', 'slippage_cost_r'):
        assert getattr(outcomes[0], field) == getattr(outcomes[1], field)
    assert mtf.state_to_json(step.state) == before


def test_long_receipt_is_identical_after_restart_and_detects_tamper():
    rows, step = _long_path()
    first = bridge_mtf_research_plan_v2(step.plan, step.state, raw_closed_m5=rows)
    restored = mtf.state_from_json(mtf.state_to_json(step.state),
        expected_provider_fingerprint=step.state.provider_fingerprint,
        expected_cfg=mtf.EventExpansionRetestLongMTFConfigV1())
    second = bridge_mtf_research_plan_v2(restored.plan_outbox[0], restored, raw_closed_m5=rows)
    assert first == second
    with pytest.raises(EventLongMTFBridgeError, match='does not bind evidence'):
        replace(first.receipt, level_window_sha256='b'*64)
    with pytest.raises(EventLongMTFBridgeError, match='does not bind evidence'):
        replace(first.receipt, level_output_sha256='b'*64)


@pytest.mark.parametrize('mutation', ('old_volume', 'window_volume', 'gap', 'future', 'shortened'))
def test_invalid_raw_prefix_is_rejected(mutation):
    rows, step = _long_path()
    bad = [list(r) for r in rows]
    if mutation == 'old_volume': bad[0][5] += 1
    elif mutation == 'window_volume': bad[-300][5] += 1
    elif mutation == 'gap': del bad[100]
    elif mutation == 'future': bad.append([bad[-1][0]+M5, *bad[-1][1:]])
    else: bad = bad[48:]
    with pytest.raises(EventLongMTFBridgeError, match='raw'):
        bridge_mtf_research_plan_v2(step.plan, step.state, raw_closed_m5=bad)


def test_window_hash_is_checked_independently_of_full_aggregate():
    rows, step = _long_path()
    level = step.state.active.event.level_snapshot
    bad_level = _unsafe_replace(level, source_bars_sha256='b'*64)
    bad_event = _unsafe_replace(step.state.active.event, level_snapshot=bad_level)
    state = replace(step.state, active=replace(step.state.active, event=bad_event))
    # Exercise the narrow membership checker separately from the outer envelope.
    with pytest.raises(EventLongMTFBridgeError, match='lookback window'):
        _verify_source_window(step.plan, state, rows)


def test_full_provenance_hash_is_checked_independently_of_window():
    rows, step = _long_path()
    level = step.state.active.event.level_snapshot
    bad_level = _unsafe_replace(level, source_provenance=replace(
        level.source_provenance, output_sha256='b'*64))
    event = _unsafe_replace(step.state.active.event, level_snapshot=bad_level)
    state = replace(step.state, active=replace(step.state.active, event=event))
    with pytest.raises(EventLongMTFBridgeError, match='full level aggregation'):
        _verify_source_window(step.plan, state, rows)


def test_acknowledged_outbox_still_blocks_v2():
    rows, step = _long_path()
    ack = mtf.acknowledge_plan(step.state, step.plan.plan_id)
    with pytest.raises(EventLongMTFBridgeError, match='atomic outbox'):
        bridge_mtf_research_plan_v2(step.plan, ack, raw_closed_m5=rows)


def test_h4_window_membership_uses_h4_not_h1_interval():
    from bot.closed_bar_aggregation_v1 import (
        aggregate_closed_m5_bars, ClosedBarAggregationConfigV1,
    )
    from bot.level_snapshot_v1 import build_resistance_snapshot_v1, LevelSnapshotConfigV1
    rows, step = _long_path()
    event = step.state.active.event
    cut = [r for r in rows if r[0]+M5 <= event.expansion_open_ts_ms]
    full = aggregate_closed_m5_bars(cut, as_of_ms=event.expansion_open_ts_ms,
        provider_identity=step.state.provider_identity,
        provider_fingerprint=step.state.provider_fingerprint,
        config=ClosedBarAggregationConfigV1(target_timeframe='H4'))
    # Component fixture only; never changes the frozen MTF production config.
    level = build_resistance_snapshot_v1(step.state.symbol, 'H4', full.output_bars,
        as_of_ms=event.expansion_open_ts_ms,
        provider_fingerprint=step.state.provider_fingerprint,
        cfg=LevelSnapshotConfigV1(lookback_bars=40, max_distance_atr=5.),
        aggregation_result=full)
    assert level is not None and level.source_bars_sha256 != full.output_sha256
    altered_event = _unsafe_replace(event, level_snapshot=level)
    state = replace(step.state, active=replace(step.state.active, event=altered_event))
    window = _verify_source_window(step.plan, state, rows)
    assert len(window) == 40 and window[-1][0]+4*H1 == level.source_end_close_ms


@pytest.mark.parametrize('case_index', (0, 1))
def test_archived_avax_real_plan_is_source_bound_and_restart_exact(case_index):
    root = Path(__file__).resolve().parents[1]
    base = root / 'reports/evidence/breakout_bridge_v2_20261012'
    receipt = json.loads((base/'replay_receipt.json').read_bytes())
    zipped = (base/'avax_decision_prefix.json.gz').read_bytes()
    assert hashlib.sha256(zipped).hexdigest() == receipt['fixture_compressed_sha256']
    raw = gzip.decompress(zipped)
    assert hashlib.sha256(raw).hexdigest() == receipt['fixture_canonical_sha256']
    cases_raw = (base/'cases.json').read_bytes()
    assert hashlib.sha256(cases_raw).hexdigest() == receipt['cases_sha256']
    for path, pin in receipt['unchanged_core_pins'].items():
        assert hashlib.sha256((root/path).read_bytes()).hexdigest() == pin
    case = json.loads(cases_raw)[case_index]
    state = mtf.state_from_json(case['state_pri_plane'],
        expected_provider_fingerprint=receipt['provider_manifest_sha256'],
        expected_cfg=mtf.EventExpansionRetestLongMTFConfigV1())
    plan = state.plan_outbox[0]
    assert plan.plan_id == case['mtf_plan_id']
    rows = json.loads(raw)[:case['raw_prefix_count']]
    with pytest.raises(V1Error, match='aggregation evidence'):
        bridge_mtf_research_plan_v1(plan, state)
    result = bridge_mtf_research_plan_v2(plan, state, raw_closed_m5=rows)
    assert json.dumps(asdict(result), sort_keys=True) == json.dumps(case['v2_result'], sort_keys=True)
    assert result.receipt.level_window_count < case['full_aggregate_count']
    assert result.frozen_plan.entry_reference == plan.entry_reference
    assert result.frozen_plan.frozen_stop == plan.stop_price
