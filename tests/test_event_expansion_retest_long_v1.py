from __future__ import annotations

from dataclasses import replace

import pytest

import strategies.event_expansion_retest_long_v1 as mod
from bot.level_snapshot_v1 import LevelSnapshotConfigV1, build_resistance_snapshot_v1


M5 = 300_000
H1 = 3_600_000
BASE_TS = 61 * H1


def _snapshot(*, count: int = 60):
    rows = []
    for index in range(count):
        close = 107.0 + 0.05 * (index % 3)
        high = 110.0 if index in {10, 25, 40} else close + 0.55
        rows.append([index * H1, close - 0.1, high, close - 0.65, close, 1_000 + index])
    result = build_resistance_snapshot_v1(
        "TESTUSDT", "H1", rows, as_of_ms=count * H1,
        provider_fingerprint="a" * 64,
        cfg=LevelSnapshotConfigV1(lookback_bars=count, max_distance_atr=5.0),
    )
    assert result is not None
    return result


def _row(index, open_, high, low, close, volume=100.0):
    return [BASE_TS + index * M5, open_, high, low, close, volume]


def _event_rows():
    rows = [_row(i, 107.0, 107.3, 106.7, 107.0) for i in range(50)]
    rows.append(_row(50, 107.0, 110.5, 106.9, 110.0, 300.0))
    return rows


def _advance_to_plan():
    cfg = mod.ExpansionRetestLongConfig()
    rows = _event_rows()
    state = mod.detect_expansion_event("TESTUSDT", rows, [_snapshot()], cfg)
    assert state is not None
    rows.append(_row(51, 110.0, 110.3, 109.3, 110.0))
    state, plan, _ = mod.advance_event(state, rows, cfg)
    assert plan is None
    rows.append(_row(52, 110.0, 110.2, 109.2, 109.9))
    state, plan, reason = mod.advance_event(state, rows, cfg)
    assert state.stage == mod.LongEventStage.HELD_ABOVE and reason == "hold_confirmed"
    rows.append(_row(53, 109.5, 109.8, 107.75, 108.0))
    state, plan, reason = mod.advance_event(state, rows, cfg)
    assert state.stage == mod.LongEventStage.FIRST_RETEST and reason == "first_retest_confirmed"
    rows.append(_row(54, 108.2, 109.5, 108.0, 109.0))
    state, plan, reason = mod.advance_event(state, rows, cfg)
    assert reason == "waiting_higher_low_confirmation"
    rows.append(_row(55, 109.0, 109.8, 108.1, 109.5))
    state, plan, reason = mod.advance_event(state, rows, cfg)
    assert state.stage == mod.LongEventStage.HIGHER_LOW_CONFIRMED
    rows.append(_row(56, 109.8, 110.8, 109.7, 110.6))
    state, plan, reason = mod.advance_event(state, rows, cfg)
    return cfg, rows, state, plan, reason


def test_long_fsm_requires_hold_first_retest_higher_low_and_later_bos() -> None:
    cfg, rows, state, plan, reason = _advance_to_plan()
    assert state.stage == mod.LongEventStage.PLAN_EMITTED
    assert reason == "plan_ready" and plan is not None
    assert plan.side == "long"
    assert plan.valid_from_ts == plan.signal_ts + cfg.interval_ms
    assert plan.entry_type == "market_next_open"
    assert plan.executable is False
    assert plan.preflight_status == "BLOCKED_RESEARCH_MECHANICS"
    terminal, duplicate, reason = mod.advance_event(state, rows, cfg)
    assert terminal == state and duplicate is None
    assert reason == "duplicate_or_old_bar"


def test_event_and_plan_reject_short_or_executable_identity() -> None:
    cfg = mod.ExpansionRetestLongConfig()
    event = mod.detect_expansion_event("TESTUSDT", _event_rows(), [_snapshot()], cfg)
    assert event is not None
    with pytest.raises(ValueError, match="long-only"):
        replace(event.event, side="short")
    _, _, _, plan, _ = _advance_to_plan()
    assert plan is not None
    with pytest.raises(ValueError, match="non-executable"):
        replace(plan, executable=True)


def test_event_id_binds_level_snapshot_source_and_strategy_config() -> None:
    rows = _event_rows()
    base = mod.detect_expansion_event(
        "TESTUSDT", rows, [_snapshot()], mod.ExpansionRetestLongConfig()
    )
    changed = mod.detect_expansion_event(
        "TESTUSDT", rows, [_snapshot()],
        mod.ExpansionRetestLongConfig(min_volume_multiple=1.1),
    )
    assert base is not None and changed is not None
    assert base.event.event_id != changed.event.event_id
    assert base.event.level_snapshot.snapshot_id == changed.event.level_snapshot.snapshot_id


def test_first_retest_before_hold_is_consumed_and_event_invalidated() -> None:
    cfg = mod.ExpansionRetestLongConfig()
    rows = _event_rows()
    state = mod.detect_expansion_event("TESTUSDT", rows, [_snapshot()], cfg)
    assert state is not None
    # The very first post-breakout pullback touches the zone; a later cleaner
    # retest may not rescue this event.
    rows.append(_row(51, 109.0, 109.2, 107.8, 108.2))
    state, plan, reason = mod.advance_event(state, rows, cfg)
    assert state.stage == mod.LongEventStage.INVALIDATED
    assert plan is None and reason == "retest_before_hold"
    assert state.event.level_snapshot.lifecycle == "flip_support"


def test_public_paths_fail_closed_on_gap_bad_ohlc_and_future_snapshot() -> None:
    cfg = mod.ExpansionRetestLongConfig()
    rows = _event_rows()
    gappy = [row for index, row in enumerate(rows) if index != 20]
    with pytest.raises(ValueError, match="gap"):
        mod.detect_expansion_event("TESTUSDT", gappy, [_snapshot()], cfg)
    bad = [list(row) for row in rows]
    bad[10][2] = bad[10][3] - 1.0
    with pytest.raises(ValueError, match="OHLCV"):
        mod.detect_expansion_event("TESTUSDT", bad, [_snapshot()], cfg)

    future = _snapshot(count=70)
    assert future.source_end_close_ms > int(rows[-1][0])
    assert mod.detect_expansion_event("TESTUSDT", rows, [future], cfg) is None


def test_closed_rows_excludes_open_tail_and_config_is_strict() -> None:
    rows = _event_rows()
    rows.append(_row(51, 110.0, 500.0, 1.0, 400.0))
    closed = mod.closed_rows_before(rows, as_of_ms=BASE_TS + 51 * M5, interval_ms=M5)
    assert len(closed) == 51
    with pytest.raises(ValueError):
        mod.ExpansionRetestLongConfig(hold_bars=0)
