from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from bot.xau_mt5_zero_order_paper import (
    CONTROL_JOURNAL_UTC_HOUR,
    ControlAssignment,
    CostContract,
    HashChainJournal,
    JournalCorruption,
    PaperOutcome,
    PaperPosition,
    QuoteSnapshot,
    SignalEvent,
    assign_control,
    evaluate_position,
    open_position,
)


UTC = timezone.utc


def dt(hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 8, 24, hour, minute, tzinfo=UTC)


def quote(*, bid: float = 100.0, ask: float = 100.2, at: datetime | None = None, low=None, high=None, age=0.0):
    return QuoteSnapshot(
        observed_at=at or dt(),
        bid=bid,
        ask=ask,
        source_hash="quote-sha",
        freshness_age_seconds=age,
        low=low,
        high=high,
        session="london",
    )


def signal(*, side="long", at=None):
    return SignalEvent(
        signal_id="sig-1",
        strategy="session_breakout_retest",
        strategy_version="v1",
        symbol="XAUUSD",
        side=side,
        event_at=at or dt(),
        source_candle_end=at or dt(),
        data_source_hash="data-sha",
        entry=100.0,
        stop=98.0 if side == "long" else 102.0,
        take_profit=104.0 if side == "long" else 96.0,
        validity_until=(at or dt()) + timedelta(hours=2),
        regime="trend",
        feature_snapshot_hash="features-sha",
        prereg_hash="prereg-sha",
        evidence_universe_role="paper",
    )


def test_models_are_immutable_and_validate_geometry():
    s = signal()
    with pytest.raises((AttributeError, TypeError)):
        s.side = "short"
    with pytest.raises(ValueError, match="side"):
        signal(side="bad")
    with pytest.raises(ValueError, match="crossed"):
        quote(bid=101, ask=100)


def test_side_correct_fills_and_costs():
    costs = CostContract(slippage_bps=10, commission_per_unit=0.1)
    long_pos = open_position(signal(), quote(), quantity=2, costs=costs)
    short_pos = open_position(signal(side="short"), quote(), quantity=2, costs=costs)
    assert long_pos.entry_fill == pytest.approx(100.2 * 1.001)
    assert short_pos.entry_fill == pytest.approx(100.0 * (1 - 0.001))
    assert long_pos.entry_reference_price == pytest.approx(100.2)
    assert short_pos.entry_reference_price == pytest.approx(100.0)


def test_cost_contract_rejects_stress_that_can_make_a_fill_nonpositive():
    with pytest.raises(ValueError, match="combined price stress"):
        CostContract(spread_bps=10_000, slippage_bps=5_000)


def test_delayed_quote_inside_signal_window_is_a_valid_causal_entry():
    delayed = quote(at=dt(12, 1))

    position = open_position(signal(), delayed, quantity=1)

    assert position.entry_at == dt(12, 1)


def test_additional_spread_stress_is_applied_without_hiding_bid_ask():
    costs = CostContract(spread_bps=4)

    position = open_position(signal(), quote(), quantity=1, costs=costs)

    assert position.entry_fill == pytest.approx(100.2 * 1.0002)


def test_stale_missing_and_out_of_session_quotes_fail_closed():
    s = signal()
    with pytest.raises(ValueError, match="stale"):
        open_position(s, quote(age=61), quantity=1)
    with pytest.raises(ValueError, match="missing"):
        open_position(s, quote(bid=None), quantity=1)
    with pytest.raises(ValueError, match="session"):
        open_position(s, quote(), quantity=1, allowed_sessions={"new_york"})


def test_long_stop_first_when_bar_touches_stop_and_target():
    pos = open_position(signal(), quote(), quantity=1)
    outcome = evaluate_position(
        pos,
        quote(at=dt(13), bid=101, ask=101.2, low=97.5, high=104.5),
        costs=CostContract(),
    )
    assert isinstance(outcome, PaperOutcome)
    assert outcome.close_reason == "stop"
    assert outcome.stop_first_tie is True
    assert outcome.exit_fill == pytest.approx(98.0)


def test_short_take_profit_and_side_correct_exit():
    pos = open_position(signal(side="short"), quote(), quantity=1)
    outcome = evaluate_position(
        pos,
        quote(at=dt(13), bid=95.8, ask=96.0, low=95.5, high=99.0),
    )
    assert outcome.close_reason == "take_profit"
    assert outcome.exit_reference_price == pytest.approx(96.0)
    assert outcome.net_pnl > 0


def test_gap_is_not_filled_at_requested_stop():
    pos = open_position(signal(), quote(), quantity=1)
    outcome = evaluate_position(
        pos,
        quote(at=dt(14), bid=94.0, ask=94.2, low=93.8, high=94.2),
        previous_exit_reference=99.0,
    )
    assert outcome.close_reason == "gap"
    assert outcome.exit_fill == pytest.approx(94.0)
    assert outcome.gap_amount == pytest.approx(4.0)


def test_first_observed_quote_through_stop_is_gap_without_previous_reference():
    pos = open_position(signal(), quote(), quantity=1)

    outcome = evaluate_position(
        pos,
        quote(at=dt(14), bid=94.0, ask=94.2, low=93.8, high=94.2),
    )

    assert outcome.close_reason == "gap"
    assert outcome.exit_fill == pytest.approx(94.0)


def test_evaluation_before_entry_is_invalid_data_not_a_zero_time_trade():
    pos = open_position(signal(), quote(at=dt(12, 1)), quantity=1)

    outcome = evaluate_position(
        pos,
        quote(at=dt(), bid=97.0, ask=97.2, low=96.5, high=97.2),
    )

    assert outcome.close_reason == "invalid_data"
    assert outcome.data_quality == "quote_precedes_position"


def test_mae_mfe_and_r_are_recorded():
    pos = open_position(signal(), quote(), quantity=1)
    outcome = evaluate_position(
        pos,
        quote(at=dt(13), bid=103.5, ask=103.7, low=99.0, high=104.5),
    )
    assert outcome.close_reason == "take_profit"
    assert outcome.mfe_r > 0
    assert outcome.mae_r > 0
    assert outcome.r_multiple > 0


def test_nonpositive_or_nonfinite_market_values_and_invalid_position_fail_closed():
    with pytest.raises(ValueError):
        quote(bid=-1.0, ask=1.0)
    with pytest.raises(ValueError):
        quote(low=float("nan"), high=101.0)
    with pytest.raises(ValueError, match="geometry"):
        PaperPosition(
            position_id="p",
            signal_id="s",
            decision_id="d",
            symbol="XAUUSD",
            side="long",
            quantity=1,
            entry_at=dt(),
            entry_reference_price=100,
            entry_fill=100,
            stop=102,
            take_profit=104,
            point_value=1,
        )
    closed = __import__("dataclasses").replace(
        open_position(signal(), quote(), quantity=1), state="closed"
    )
    with pytest.raises(ValueError, match="open position"):
        evaluate_position(closed, quote(at=dt(13), low=97, high=101))


def test_evaluation_rejects_point_value_contract_drift():
    position = open_position(
        signal(), quote(), quantity=1, costs=CostContract(point_value=10)
    )

    with pytest.raises(ValueError, match="point_value"):
        evaluate_position(
            position,
            quote(at=dt(13), bid=98, ask=98.2, low=97.5, high=101),
            costs=CostContract(point_value=1),
        )


def test_control_assignment_is_deterministic_and_precommitted():
    a = assign_control(
        decision_id="decision-1",
        symbol="XAUUSD",
        strategy_side="long",
        event_at=dt(),
        window_start=dt(9),
        window_end=dt(16),
        prereg_hash="pre-sha",
        now=dt(10),
    )
    b = assign_control(
        decision_id="decision-1",
        symbol="XAUUSD",
        strategy_side="long",
        event_at=dt(),
        window_start=dt(9),
        window_end=dt(16),
        prereg_hash="pre-sha",
        now=dt(10),
    )
    assert a == b
    assert isinstance(a, ControlAssignment)
    assert a.control_entry_at != dt()
    assert a.commit_hash
    assert a.state in {"ready", "pending"}
    assert a.control_entry_at.tzinfo == UTC
    assert CONTROL_JOURNAL_UTC_HOUR == 6


def test_control_assignment_changes_on_collision_index_and_rejects_bad_window():
    kwargs = dict(
        decision_id="decision-1",
        symbol="XAUUSD",
        strategy_side="long",
        event_at=dt(),
        window_start=dt(9),
        window_end=dt(16),
        prereg_hash="pre-sha",
        now=dt(10),
    )
    assert assign_control(**kwargs, collision_index=0) != assign_control(**kwargs, collision_index=1)
    with pytest.raises(ValueError, match="window"):
        assign_control(**{**kwargs, "window_start": dt(16), "window_end": dt(9)})


def test_hash_chain_journal_is_append_only_idempotent_and_detects_corruption(tmp_path: Path):
    path = tmp_path / "control_0600.jsonl"
    journal = HashChainJournal(path, stream="xau_control_0600")
    first = journal.append(
        {"kind": "control_assignment", "decision_id": "d1"},
        idempotency_key="d1:control",
        prereg_hash="pre-sha",
        source_hash="source-sha",
    )
    retry = journal.append(
        {"kind": "control_assignment", "decision_id": "d1"},
        idempotency_key="d1:control",
        prereg_hash="pre-sha",
        source_hash="source-sha",
    )
    assert first == retry
    assert len(path.read_text().splitlines()) == 1
    assert path.stat().st_mode & 0o777 == 0o600
    assert journal.validate() == 1
    assert path.with_suffix(".jsonl.lock").stat().st_mode & 0o777 == 0o600
    with path.open("a") as handle:
        handle.write(json.dumps({"corrupt": True}) + "\n")
    with pytest.raises(JournalCorruption):
        journal.validate()


def test_static_safety_boundary_has_no_trade_or_private_client_surface():
    source = Path(__file__).parents[1].joinpath("bot", "xau_mt5_zero_order_paper.py").read_text()
    assert "order_send" not in source
    assert "trade_" not in source
    assert "MetaTrader" not in source
    assert "mt5" not in source.lower()
