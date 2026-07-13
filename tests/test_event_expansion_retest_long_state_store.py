from __future__ import annotations

import hashlib
import json
import stat

import pytest

from bot.event_expansion_retest_long_state_store import (
    LongEventStateStore,
    LongStateValidationError,
)
from strategies.event_expansion_retest_long_v1 import (
    ExpansionRetestLongConfig,
    LongEventStage,
    LongSleeveState,
    advance_event,
    detect_expansion_event,
)
from tests.test_event_expansion_retest_long_v1 import _event_rows, _row, _snapshot


SOURCE_SHA = "e" * 64


def _first_retest_state():
    cfg = ExpansionRetestLongConfig()
    rows = _event_rows()
    state = detect_expansion_event("TESTUSDT", rows, [_snapshot()], cfg)
    assert state is not None
    rows.append(_row(51, 110.0, 110.3, 109.3, 110.0))
    state, _, _ = advance_event(state, rows, cfg)
    rows.append(_row(52, 110.0, 110.2, 109.2, 109.9))
    state, _, _ = advance_event(state, rows, cfg)
    rows.append(_row(53, 109.5, 109.8, 107.75, 108.0))
    state, _, _ = advance_event(state, rows, cfg)
    assert state.stage == LongEventStage.FIRST_RETEST
    return state


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _payload_sha(payload):
    data = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def test_first_retest_and_event_ledgers_survive_restart(tmp_path) -> None:
    active = _first_retest_state()
    expected = {
        "TESTUSDT": LongSleeveState(
            active=active,
            seen_event_ids=(active.event.event_id,),
            planned_event_ids=(),
        )
    }
    path = tmp_path / "long-event-state.json"
    store = LongEventStateStore(path, source_fingerprint=SOURCE_SHA)
    store.save(expected)
    assert store.load() == expected
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_missing_first_retest_evidence_fails_even_with_resealed_envelope(tmp_path) -> None:
    active = _first_retest_state()
    path = tmp_path / "long-event-state.json"
    store = LongEventStateStore(path, source_fingerprint=SOURCE_SHA)
    store.save({
        "TESTUSDT": LongSleeveState(
            active, (active.event.event_id,), (),
        )
    })
    envelope = _read(path)
    envelope["payload"]["states"]["TESTUSDT"]["active"]["retest_low"] = None
    envelope["payload_sha256"] = _payload_sha(envelope["payload"])
    _write(path, envelope)
    with pytest.raises(LongStateValidationError, match="first-retest"):
        store.load()


def test_checksum_side_identity_and_source_mismatch_fail_closed(tmp_path) -> None:
    active = _first_retest_state()
    path = tmp_path / "long-event-state.json"
    store = LongEventStateStore(path, source_fingerprint=SOURCE_SHA)
    state = LongSleeveState(active, (active.event.event_id,), ())
    store.save({"TESTUSDT": state})
    envelope = _read(path)
    envelope["payload"]["states"]["TESTUSDT"]["active"]["hold_count"] = 99
    _write(path, envelope)
    with pytest.raises(LongStateValidationError, match="checksum"):
        store.load()

    store.save({"TESTUSDT": state})
    envelope = _read(path)
    envelope["side_identity"] = "short_only"
    _write(path, envelope)
    with pytest.raises(LongStateValidationError, match="identity"):
        store.load()

    store.save({"TESTUSDT": state})
    with pytest.raises(LongStateValidationError, match="source fingerprint"):
        LongEventStateStore(path, source_fingerprint="f" * 64).load()


def test_planned_receipt_is_required_and_symlink_is_rejected(tmp_path) -> None:
    active = _first_retest_state()
    emitted = LongSleeveState(
        active=active.__class__(
            event=active.event,
            stage=LongEventStage.PLAN_EMITTED,
            last_processed_ts=active.last_processed_ts + active.event.signal_interval_ms,
            hold_count=active.hold_count,
            first_retest_ts=active.first_retest_ts,
            retest_low=active.retest_low,
            structure_level=active.structure_level,
            terminal_reason="one_plan_emitted",
        ),
        seen_event_ids=(active.event.event_id,),
        planned_event_ids=(),
    )
    with pytest.raises(LongStateValidationError, match="planned_event_ids"):
        LongEventStateStore(
            tmp_path / "state.json", source_fingerprint=SOURCE_SHA
        ).save({"TESTUSDT": emitted})

    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    store = LongEventStateStore(link, source_fingerprint=SOURCE_SHA)
    with pytest.raises(LongStateValidationError, match="symlink"):
        store.load()
    assert target.read_text(encoding="utf-8") == "{}\n"
