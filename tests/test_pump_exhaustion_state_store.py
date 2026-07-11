from __future__ import annotations

import json
import stat

import pytest

from bot.pump_exhaustion_state_store import (
    PumpEventStateStore,
    StateValidationError,
    _sha256_json,
)
from strategies.pump_exhaustion_unwind_short_v1 import (
    EventStage,
    FrozenHighLevels,
    PumpEventState,
    PumpExpansionEvent,
    STRATEGY_NAME,
    SleeveState,
)


SOURCE_SHA = "a" * 64


def _event(*, symbol: str = "ETHUSDT", event_id: str = "evt-1") -> PumpExpansionEvent:
    return PumpExpansionEvent(
        event_id=event_id,
        strategy=STRATEGY_NAME,
        symbol=symbol,
        side="short",
        expansion_ts=1_000,
        expansion_open=10.0,
        expansion_high=12.0,
        expansion_low=9.8,
        expansion_close=11.5,
        expansion_volume=1_000_000.0,
        base_price=9.5,
        initial_atr=0.5,
        levels=FrozenHighLevels(
            horizontal_high=10.5,
            sloped_high=10.8,
            liquidity_high=10.7,
            anchor_level=10.8,
            anchor_source="sloped_high",
            crossed_sources=("horizontal_high", "sloped_high", "liquidity_high"),
        ),
        expires_ts=100_000,
    )


def _expanded_state() -> SleeveState:
    event = _event()
    return SleeveState(
        active=PumpEventState(
            event=event,
            stage=EventStage.EXPANDED,
            last_processed_ts=1_000,
            peak_price=12.0,
        ),
        seen_event_ids=(event.event_id,),
        planned_event_ids=(),
    )


def _read_envelope(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_envelope(path, envelope):
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_state_round_trip_is_private_and_restart_safe(tmp_path):
    path = tmp_path / "pump-state.json"
    store = PumpEventStateStore(path, source_fingerprint=SOURCE_SHA)
    expected = {"ETHUSDT": _expanded_state()}

    store.save(expected)

    assert store.load() == expected
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = _read_envelope(path)
    assert envelope["strategy"] == STRATEGY_NAME
    assert envelope["side_identity"] == "short_only"
    assert envelope["source_fingerprint"] == SOURCE_SHA
    assert envelope["payload_sha256"] == _sha256_json(envelope["payload"])
    assert not list(tmp_path.glob(".pump-state.json.*.tmp"))


@pytest.mark.parametrize("field,value", [("schema", "wrong"), ("version", 999), ("side_identity", "long_only")])
def test_schema_strategy_and_side_mismatch_fail_closed(tmp_path, field, value):
    path = tmp_path / "pump-state.json"
    store = PumpEventStateStore(path, source_fingerprint=SOURCE_SHA)
    store.save({"ETHUSDT": _expanded_state()})
    envelope = _read_envelope(path)
    envelope[field] = value
    _write_envelope(path, envelope)

    with pytest.raises(StateValidationError):
        store.load()


def test_source_and_payload_checksum_mismatch_fail_closed(tmp_path):
    path = tmp_path / "pump-state.json"
    store = PumpEventStateStore(path, source_fingerprint=SOURCE_SHA)
    store.save({"ETHUSDT": _expanded_state()})

    with pytest.raises(StateValidationError, match="source fingerprint"):
        PumpEventStateStore(path, source_fingerprint="b" * 64).load()

    envelope = _read_envelope(path)
    envelope["payload"]["states"]["ETHUSDT"]["active"]["peak_price"] = 99.0
    _write_envelope(path, envelope)
    with pytest.raises(StateValidationError, match="checksum"):
        store.load()


def test_nested_noncanonical_symbol_and_nan_fail_closed(tmp_path):
    path = tmp_path / "pump-state.json"
    store = PumpEventStateStore(path, source_fingerprint=SOURCE_SHA)
    store.save({"ETHUSDT": _expanded_state()})
    envelope = _read_envelope(path)
    active = envelope["payload"]["states"]["ETHUSDT"]["active"]
    active["event"]["symbol"] = "ethusdt"
    envelope["payload_sha256"] = _sha256_json(envelope["payload"])
    _write_envelope(path, envelope)
    with pytest.raises(StateValidationError, match="symbol"):
        store.load()

    store.save({"ETHUSDT": _expanded_state()})
    envelope = _read_envelope(path)
    envelope["payload"]["states"]["ETHUSDT"]["active"]["peak_price"] = float("nan")
    _write_envelope(path, envelope)
    with pytest.raises(StateValidationError, match="canonical JSON"):
        store.load()


def test_bounded_planned_ledger_may_outlive_seen_ledger(tmp_path):
    path = tmp_path / "pump-state.json"
    store = PumpEventStateStore(path, source_fingerprint=SOURCE_SHA)
    state = SleeveState(active=None, seen_event_ids=("new-seen",), planned_event_ids=("old-plan",))

    store.save({"ETHUSDT": state})

    assert store.load()["ETHUSDT"] == state


def test_plan_emitted_requires_planned_ledger_receipt(tmp_path):
    event = _event()
    active = PumpEventState(
        event=event,
        stage=EventStage.PLAN_EMITTED,
        last_processed_ts=3_000,
        peak_price=12.2,
        exhaustion_ts=2_000,
        choch_ts=2_500,
        choch_level=10.5,
        terminal_reason="one_plan_emitted",
    )
    store = PumpEventStateStore(tmp_path / "pump-state.json", source_fingerprint=SOURCE_SHA)

    with pytest.raises(StateValidationError, match="planned_event_ids"):
        store.save(
            {
                "ETHUSDT": SleeveState(
                    active=active,
                    seen_event_ids=(event.event_id,),
                    planned_event_ids=(),
                )
            }
        )


def test_invalid_save_preserves_last_known_good_file(tmp_path):
    path = tmp_path / "pump-state.json"
    store = PumpEventStateStore(path, source_fingerprint=SOURCE_SHA)
    expected = {"ETHUSDT": _expanded_state()}
    store.save(expected)
    before = path.read_bytes()

    with pytest.raises(StateValidationError):
        store.save({"ethusdt": _expanded_state()})

    assert path.read_bytes() == before
    assert store.load() == expected


def test_state_symlink_is_rejected_without_touching_target(tmp_path):
    target = tmp_path / "real-state.json"
    target.write_text("{}\n", encoding="utf-8")
    linked = tmp_path / "pump-state.json"
    linked.symlink_to(target)
    store = PumpEventStateStore(linked, source_fingerprint=SOURCE_SHA)

    with pytest.raises(StateValidationError, match="symlink"):
        store.load()
    with pytest.raises(StateValidationError, match="symlink"):
        store.save({})

    assert target.read_text(encoding="utf-8") == "{}\n"


def test_source_fingerprint_must_be_lowercase_sha256(tmp_path):
    with pytest.raises(ValueError):
        PumpEventStateStore(tmp_path / "state.json", source_fingerprint="ABC")
