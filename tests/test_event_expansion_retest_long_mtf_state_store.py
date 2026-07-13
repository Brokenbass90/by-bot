from __future__ import annotations

import json
import stat
from dataclasses import replace

import pytest

import bot.event_expansion_retest_long_mtf_state_store as store_mod
from bot.event_expansion_retest_long_mtf_state_store import (
    EventExpansionRetestLongMTFStateStore,
    MTFStatePersistenceError,
    PersistedEventExpansionRetestLongMTFV1Research,
)
from strategies.event_expansion_retest_long_mtf_v1 import (
    EventExpansionRetestLongMTFConfigV1,
)
from tests.test_event_expansion_retest_long_mtf_v1 import _append_m15, _golden_path


PROVIDER_SHA = "a" * 64


def _state_with_plan():
    rows, step, _ = _golden_path()
    assert step.plan is not None and len(step.state.plan_outbox) == 1
    return rows, step.state


def _store(path, *, provider=PROVIDER_SHA, cfg=None):
    return EventExpansionRetestLongMTFStateStore(
        path,
        expected_provider_fingerprint=provider,
        expected_cfg=cfg,
    )


def test_state_and_outbox_survive_restart_as_one_0600_file(tmp_path) -> None:
    _, state = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    _store(path).save(state)

    restarted = _store(path)
    assert restarted.load() == state
    assert restarted.load().plan_outbox == state.plan_outbox
    info = path.stat()
    assert stat.S_ISREG(info.st_mode)
    assert stat.S_IMODE(info.st_mode) == 0o600


def test_ack_is_persisted_before_return_and_duplicate_ack_fails_closed(tmp_path) -> None:
    _, state = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    store = _store(path)
    store.save(state)
    plan_id = state.plan_outbox[0].plan_id

    acknowledged = store.acknowledge_plan(plan_id)
    assert acknowledged.plan_outbox == ()
    assert acknowledged.acknowledged_plan_ids[-1] == plan_id
    assert _store(path).load() == acknowledged

    durable_before = path.read_bytes()
    with pytest.raises(MTFStatePersistenceError, match="acknowledgement rejected"):
        store.acknowledge_plan(plan_id)
    assert path.read_bytes() == durable_before


def test_tamper_is_not_silently_reset_even_by_a_later_save(tmp_path) -> None:
    _, state = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    store = _store(path)
    store.save(state)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["source_count"] += 1
    path.write_text(json.dumps(envelope), encoding="utf-8")
    tampered = path.read_bytes()

    with pytest.raises(MTFStatePersistenceError, match="checksum"):
        store.load()
    with pytest.raises(MTFStatePersistenceError, match="checksum"):
        store.save(state)
    assert path.read_bytes() == tampered


def test_provider_and_config_pins_fail_closed(tmp_path) -> None:
    _, state = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    _store(path).save(state)

    with pytest.raises(MTFStatePersistenceError, match="provider/config mismatch"):
        _store(path, provider="b" * 64).load()
    changed_cfg = EventExpansionRetestLongMTFConfigV1(min_volume_multiple=1.30)
    with pytest.raises(MTFStatePersistenceError, match="provider/config mismatch"):
        _store(path, cfg=changed_cfg).load()


def test_target_symlink_and_non_regular_target_are_rejected(tmp_path) -> None:
    _, state = _state_with_plan()
    target = tmp_path / "real-state.json"
    target.write_text("do not touch\n", encoding="utf-8")
    link = tmp_path / "state-link.json"
    link.symlink_to(target)

    linked_store = _store(link)
    with pytest.raises(MTFStatePersistenceError, match="symlink"):
        linked_store.load()
    with pytest.raises(MTFStatePersistenceError, match="symlink"):
        linked_store.save(state)
    assert target.read_text(encoding="utf-8") == "do not touch\n"

    directory_target = tmp_path / "directory-state.json"
    directory_target.mkdir()
    with pytest.raises(MTFStatePersistenceError, match="not a regular file"):
        _store(directory_target).load()
    with pytest.raises(MTFStatePersistenceError, match="not a regular file"):
        _store(directory_target).save(state)


def test_parent_symlink_is_rejected_without_writing_through_it(tmp_path) -> None:
    _, state = _state_with_plan()
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    store = _store(linked_parent / "state.json")

    with pytest.raises(MTFStatePersistenceError, match="parent component"):
        store.load()
    with pytest.raises(MTFStatePersistenceError, match="parent component"):
        store.save(state)
    assert not (real_parent / "state.json").exists()


def test_insecure_mode_is_rejected_on_load_and_save(tmp_path) -> None:
    _, state = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    store = _store(path)
    store.save(state)
    path.chmod(0o640)
    before = path.read_bytes()

    with pytest.raises(MTFStatePersistenceError, match="exactly 0600"):
        store.load()
    with pytest.raises(MTFStatePersistenceError, match="exactly 0600"):
        store.save(state)
    assert path.read_bytes() == before


def test_invalid_or_regressive_save_preserves_last_known_good_state(tmp_path) -> None:
    _, state = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    store = _store(path)
    store.save(state)
    before = path.read_bytes()

    invalid = replace(state, provider_fingerprint="b" * 64)
    with pytest.raises(MTFStatePersistenceError, match="invalid MTF state"):
        store.save(invalid)
    assert path.read_bytes() == before

    regressed = replace(state, source_count=state.source_count - 1)
    with pytest.raises(MTFStatePersistenceError):
        store.save(regressed)
    assert path.read_bytes() == before
    assert store.load() == state


def test_failed_replace_keeps_last_good_file_and_cleans_temp(tmp_path, monkeypatch) -> None:
    _, state = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    store = _store(path)
    store.save(state)
    before = path.read_bytes()

    def fail_replace(*args, **kwargs):
        raise OSError("injected replace failure")

    monkeypatch.setattr(store_mod.os, "replace", fail_replace)
    with pytest.raises(MTFStatePersistenceError, match="atomic MTF state write failed"):
        store.save(state)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".event-long-mtf-state.json.*.tmp"))


def test_pending_outbox_blocks_restart_replay_until_durable_ack(tmp_path) -> None:
    rows, _ = _state_with_plan()
    path = tmp_path / "event-long-mtf-state.json"
    first_owner = PersistedEventExpansionRetestLongMTFV1Research(
        state_path=path,
        provider_identity="synthetic",
        provider_fingerprint=PROVIDER_SHA,
    )
    first = first_owner.process_closed_m5(
        "TESTUSDT", rows, as_of_ms=rows[-1][0] + 300_000,
    )
    assert first.plan is not None and len(first.state.plan_outbox) == 1

    restarted = PersistedEventExpansionRetestLongMTFV1Research(
        state_path=path,
        provider_identity="synthetic",
        provider_fingerprint=PROVIDER_SHA,
    )
    assert restarted.pending_plans() == first.state.plan_outbox
    before = path.read_bytes()
    _append_m15(rows, 111.5, 112.0, 111.0, 111.8)
    with pytest.raises(MTFStatePersistenceError, match="durably acknowledged"):
        restarted.process_closed_m5(
            "TESTUSDT", rows, as_of_ms=rows[-1][0] + 300_000,
        )
    assert path.read_bytes() == before
    assert _store(path).load().plan_outbox == first.state.plan_outbox

    plan_id = restarted.pending_plans()[0].plan_id
    acknowledged = restarted.acknowledge_plan(plan_id)
    assert not acknowledged.plan_outbox
    resumed = restarted.process_closed_m5(
        "TESTUSDT", rows, as_of_ms=rows[-1][0] + 300_000,
    )
    assert resumed.plan is None
    assert resumed.state.source_count > first.state.source_count
    assert resumed.state.acknowledged_plan_ids == (plan_id,)


def test_missing_parent_and_missing_state_are_distinct(tmp_path) -> None:
    assert _store(tmp_path / "missing.json").load() is None
    with pytest.raises(MTFStatePersistenceError, match="missing state parent"):
        _store(tmp_path / "absent" / "state.json").load()


def test_store_declares_research_only_single_writer_contract() -> None:
    assert EventExpansionRetestLongMTFStateStore.RESEARCH_ONLY is True
    assert EventExpansionRetestLongMTFStateStore.LIVE_READY is False
    assert EventExpansionRetestLongMTFStateStore.SUPPORTS_INTERPROCESS_WRITERS is False
    assert PersistedEventExpansionRetestLongMTFV1Research.RESEARCH_ONLY is True
    assert PersistedEventExpansionRetestLongMTFV1Research.LIVE_READY is False
