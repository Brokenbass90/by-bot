from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import strategies.pump_exhaustion_unwind_short_v1 as mod
from bot.pump_exhaustion import ImpulseFadeState
from bot.retest_quality import RetestScore
from bot.structure_break import StructureBreak


STEP = 300_000


def _row(i: int, close: float, *, open_: float | None = None, high: float | None = None,
         low: float | None = None, volume: float = 100.0) -> list[float]:
    o = float(close if open_ is None else open_)
    h = float(max(o, close) + 0.8 if high is None else high)
    l = float(min(o, close) - 0.8 if low is None else low)
    return [float(i * STEP), o, h, l, float(close), float(volume)]


def _history(n: int = 70) -> list[list[float]]:
    rows = []
    for i in range(n):
        close = 100.0 + (0.35 if i % 4 in (1, 2) else -0.35)
        rows.append(_row(i, close, open_=close - 0.1, high=close + 0.7, low=close - 0.7))
    return rows


def _levels() -> mod.FrozenHighLevels:
    return mod.FrozenHighLevels(
        horizontal_high=101.0,
        sloped_high=None,
        liquidity_high=101.2,
        anchor_level=101.2,
        anchor_source="liquidity",
        crossed_sources=("horizontal", "liquidity"),
    )


def _event(expansion_ts: int, *, expires_ts: int | None = None) -> mod.PumpExpansionEvent:
    levels = _levels()
    return mod.PumpExpansionEvent(
        event_id=mod.make_event_id("TESTUSDT", expansion_ts, levels),
        strategy=mod.STRATEGY_NAME,
        symbol="TESTUSDT",
        side="short",
        expansion_ts=expansion_ts,
        expansion_open=100.0,
        expansion_high=108.0,
        expansion_low=99.5,
        expansion_close=106.5,
        expansion_volume=800.0,
        base_price=100.0,
        initial_atr=1.5,
        levels=levels,
        expires_ts=expires_ts if expires_ts is not None else expansion_ts + 100 * STEP,
    )


def _shared_short_ok() -> ImpulseFadeState:
    return ImpulseFadeState(
        ok=True,
        impulse=True,
        direction="up",
        exhausted=True,
        confirmed=True,
        fade_side="short",
        short_ok=True,
        long_ok=False,
        impulse_pct=0.08,
        vol_mult=2.5,
        peak_fade=0.4,
        retrace_frac=0.35,
        rejection_frac=0.4,
        reason="fade_confirmed",
    )


def _quality_short_ok() -> RetestScore:
    return RetestScore(
        ok=True,
        entry_ok=True,
        side="short",
        long_ok=False,
        short_ok=True,
        level=104.0,
        dist_atr=0.1,
        freshness_bars=1,
        touches=2,
        quality=0.8,
        freshness_score=1.0,
        proximity_score=0.8,
        strength_score=0.7,
        rejection_score=0.8,
        volume_score=0.6,
        reason="retest_ok",
    )


def test_closed_rows_excludes_open_bar_and_duplicate() -> None:
    rows = [_row(0, 100), _row(1, 101), _row(1, 101.5), _row(2, 102)]
    closed = mod.closed_rows_before(rows, as_of_ms=2 * STEP, interval_ms=STEP)
    assert [int(row[0]) for row in closed] == [0, STEP]
    assert closed[-1][4] == 101.0


def test_expansion_event_is_deterministic_frozen_and_short_only() -> None:
    rows = _history(70)
    rows.append(
        _row(
            70,
            105.0,
            open_=100.0,
            high=105.5,
            low=99.8,
            volume=1_500.0,
        )
    )
    cfg = mod.PumpUnwindConfig(
        level_lookback=48,
        liquidity_lookback=24,
        volume_recent_bars=2,
        volume_baseline_bars=24,
        min_recent_quote_usd=0.0,
        min_inflow_mult=1.2,
        min_inflow_z=0.0,
        min_expansion_pct=0.02,
        min_event_body_frac=0.4,
        min_event_range_atr=1.0,
    )
    first = mod.detect_expansion_event("testusdt", rows, cfg)
    second = mod.detect_expansion_event("TESTUSDT", rows, cfg)
    assert first is not None and second is not None
    assert first.event.event_id == second.event.event_id
    assert first.event.side == "short"
    assert first.event.levels.liquidity_high < first.event.expansion_close
    assert first.event.levels.anchor_source in first.event.levels.crossed_sources
    with pytest.raises(FrozenInstanceError):
        first.event.event_id = "mutated"  # type: ignore[misc]


def test_event_and_plan_reject_any_long_side() -> None:
    event = _event(50 * STEP)
    with pytest.raises(ValueError, match="short-only"):
        mod.PumpExpansionEvent(**{**event.__dict__, "side": "long"})
    with pytest.raises(ValueError, match="short-only"):
        mod.PumpUnwindShortPlan(
            event_id=event.event_id,
            strategy=mod.STRATEGY_NAME,
            symbol=event.symbol,
            side="long",
            signal_ts=51 * STEP,
            valid_from_ts=52 * STEP,
            entry_type="market_next_open",
            entry_reference=103.0,
            stop=108.0,
            target_1=98.0,
            target_2=93.0,
            risk=5.0,
            choch_level=104.0,
            event_peak=108.0,
            reason="bad side",
        )


def test_event_specific_exhaustion_reuses_shared_detector() -> None:
    rows = [_row(i, 100.0, open_=100.0, high=100.5, low=99.5, volume=100.0) for i in range(32)]
    sequence = [
        (100.0, 101.0, 99.8, 100.8, 400.0),
        (100.8, 103.0, 100.5, 102.8, 500.0),
        (102.8, 105.0, 102.5, 104.8, 600.0),
        (104.8, 108.0, 104.5, 107.5, 700.0),
        (107.5, 109.0, 106.5, 108.2, 500.0),
        (108.2, 110.0, 106.0, 107.0, 250.0),
        (107.0, 109.0, 104.5, 105.5, 150.0),
        (105.5, 108.0, 103.5, 104.5, 100.0),
    ]
    for i, (o, h, l, c, v) in enumerate(sequence, 32):
        rows.append(_row(i, c, open_=o, high=h, low=l, volume=v))

    levels = mod.FrozenHighLevels(None, None, 101.0, 101.0, "liquidity", ("liquidity",))
    event_ts = 35 * STEP
    event = mod.PumpExpansionEvent(
        event_id=mod.make_event_id("TESTUSDT", event_ts, levels),
        strategy=mod.STRATEGY_NAME,
        symbol="TESTUSDT",
        side="short",
        expansion_ts=event_ts,
        expansion_open=104.8,
        expansion_high=108.0,
        expansion_low=104.5,
        expansion_close=107.5,
        expansion_volume=700.0,
        base_price=100.0,
        initial_atr=1.0,
        levels=levels,
        expires_ts=100 * STEP,
    )
    state = mod.PumpEventState(event, mod.EventStage.EXPANDED, event_ts, 108.0)
    cfg = mod.PumpUnwindConfig(
        exhaustion_min_vol_mult=1.2,
        exhaustion_min_impulse_pct=0.03,
        exhaustion_confirm_retrace=0.25,
        exhaustion_peak_fade_ratio=0.75,
        exhaustion_min_rejection_frac=0.20,
        require_shared_exhaustion=True,
    )
    evidence = mod.exhaustion_evidence(state, rows, cfg)
    assert evidence.passed
    assert evidence.shared.short_ok
    assert evidence.shared.reason == "fade_confirmed"
    assert evidence.retrace_frac >= cfg.exhaustion_confirm_retrace


def test_fsm_emits_at_most_one_plan_for_event(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _history(54)
    event = _event(50 * STEP)
    state = mod.PumpEventState(
        event=event,
        stage=mod.EventStage.EXPANDED,
        last_processed_ts=50 * STEP,
        peak_price=108.0,
    )

    monkeypatch.setattr(
        mod,
        "exhaustion_evidence",
        lambda *_args, **_kwargs: mod.ExhaustionEvidence(
            True, 108.0, 0.35, 0.4, 0.4, _shared_short_ok(), "exhaustion_confirmed"
        ),
    )
    rows[51] = _row(51, 106.0, open_=107.0, high=108.0, low=105.5, volume=200)
    exhausted, plan, _ = mod.advance_event(state, rows[:52], mod.PumpUnwindConfig())
    assert exhausted.stage == mod.EventStage.EXHAUSTED
    assert plan is None

    monkeypatch.setattr(
        mod,
        "bearish_choch",
        lambda *_args, **_kwargs: StructureBreak(
            True, "choch", "down", "up", 104.0, "short", False, True, "choch_down"
        ),
    )
    rows[52] = _row(52, 103.5, open_=105.0, high=105.2, low=103.0, volume=180)
    choch, plan, _ = mod.advance_event(exhausted, rows[:53], mod.PumpUnwindConfig())
    assert choch.stage == mod.EventStage.CHOCH_CONFIRMED
    assert plan is None

    monkeypatch.setattr(
        mod,
        "failed_reclaim_evidence",
        lambda *_args, **_kwargs: mod.RetestEvidence(
            True, _quality_short_ok(), True, True, True, "failed_reclaim_confirmed"
        ),
    )
    rows[53] = _row(53, 103.0, open_=104.0, high=104.2, low=102.7, volume=160)
    planned, plan, _ = mod.advance_event(choch, rows[:54], mod.PumpUnwindConfig())
    assert planned.stage == mod.EventStage.PLAN_EMITTED
    assert plan is not None
    assert plan.side == "short"
    assert plan.valid_from_ts == 54 * STEP

    same_state, duplicate, reason = mod.advance_event(planned, rows[:54], mod.PumpUnwindConfig())
    assert same_state == planned
    assert duplicate is None
    assert reason == "duplicate_or_old_bar"

    rows.append(_row(54, 102.5))
    terminal, duplicate, reason = mod.advance_event(planned, rows[:55], mod.PumpUnwindConfig())
    assert terminal == planned
    assert duplicate is None
    assert reason == "terminal:plan_emitted"


def test_sleeve_plan_ledger_blocks_duplicate_even_if_transition_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _history(55)
    event = _event(50 * STEP)
    active = mod.PumpEventState(
        event=event,
        stage=mod.EventStage.CHOCH_CONFIRMED,
        last_processed_ts=53 * STEP,
        peak_price=108.0,
        exhaustion_ts=51 * STEP,
        choch_ts=52 * STEP,
        choch_level=104.0,
    )
    plan = mod.PumpUnwindShortPlan(
        event_id=event.event_id,
        strategy=mod.STRATEGY_NAME,
        symbol=event.symbol,
        side="short",
        signal_ts=54 * STEP,
        valid_from_ts=55 * STEP,
        entry_type="market_next_open",
        entry_reference=103.0,
        stop=108.0,
        target_1=98.0,
        target_2=93.0,
        risk=5.0,
        choch_level=104.0,
        event_peak=108.0,
        reason="test",
    )
    monkeypatch.setattr(
        mod,
        "advance_event",
        lambda *_args, **_kwargs: (
            active,
            plan,
            "plan_ready",
        ),
    )
    prior = mod.SleeveState(
        active=active,
        seen_event_ids=(event.event_id,),
        planned_event_ids=(event.event_id,),
    )
    result = mod.sleeve_step(event.symbol, rows, prior, mod.PumpUnwindConfig())
    assert result.plan is None
    assert result.reason == "plan_already_emitted"
    assert result.state.planned_event_ids.count(event.event_id) == 1


def test_explicit_event_expiry_and_post_choch_invalidation() -> None:
    rows = _history(55)
    event = _event(50 * STEP, expires_ts=52 * STEP)
    expanded = mod.PumpEventState(
        event=event,
        stage=mod.EventStage.EXPANDED,
        last_processed_ts=51 * STEP,
        peak_price=108.0,
    )
    expired, plan, reason = mod.advance_event(expanded, rows[:54], mod.PumpUnwindConfig())
    assert expired.stage == mod.EventStage.EXPIRED
    assert expired.terminal_reason == "event_expiry"
    assert plan is None and reason == "event_expired"

    live_event = _event(50 * STEP)
    choch = mod.PumpEventState(
        event=live_event,
        stage=mod.EventStage.CHOCH_CONFIRMED,
        last_processed_ts=53 * STEP,
        peak_price=108.0,
        exhaustion_ts=51 * STEP,
        choch_ts=52 * STEP,
        choch_level=104.0,
    )
    rows[54] = _row(54, 105.0, open_=103.5, high=105.3, low=103.2)
    invalid, plan, reason = mod.advance_event(choch, rows[:55], mod.PumpUnwindConfig())
    assert invalid.stage == mod.EventStage.INVALIDATED
    assert invalid.terminal_reason == "reclaimed_above_choch_level"
    assert plan is None and reason == "choch_reclaim_invalidated"


def test_failed_reclaim_requires_a_later_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _history(54)
    event = _event(50 * STEP)
    state = mod.PumpEventState(
        event=event,
        stage=mod.EventStage.CHOCH_CONFIRMED,
        last_processed_ts=52 * STEP,
        peak_price=108.0,
        exhaustion_ts=51 * STEP,
        choch_ts=53 * STEP,
        choch_level=104.0,
    )
    same_bar = mod.failed_reclaim_evidence(state, rows[:54], mod.PumpUnwindConfig())
    assert not same_bar.passed
    assert same_bar.reason == "before_or_same_as_choch"

    monkeypatch.setattr(mod, "score_retest", lambda *_args, **_kwargs: _quality_short_ok())
    rows.append(_row(54, 103.8, open_=104.1, high=104.2, low=103.4, volume=150))
    later = mod.failed_reclaim_evidence(state, rows, mod.PumpUnwindConfig())
    assert later.passed
    assert later.touch and later.closed_below and later.rejected
