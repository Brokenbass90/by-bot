import json
import os
import shutil
import fcntl
from pathlib import Path
from types import SimpleNamespace
import pytest

from os2_bridge_fixture import bundle, signal, terminal
from research_lab.os2_shadow_bridge import BridgeBlocked
from research_lab.os2_shadow_journal import ShadowJournal


def test_restart_exact_receipt_and_conflicting_payload(tmp_path):
    root = tmp_path / "store"
    with ShadowJournal(root) as journal:
        r = journal.process(bundle())
    before = (root / "journal.jsonl").read_bytes()
    with ShadowJournal(root) as journal:
        assert journal.process(bundle()) == r
        b = bundle(); b["decision_ms"] += 1
        with pytest.raises(BridgeBlocked, match="request_identity_conflict"): journal.process(b)
    assert (root / "journal.jsonl").read_bytes() == before


def test_reservation_and_terminal_are_one_durable_transaction(tmp_path):
    root = tmp_path / "store"
    with ShadowJournal(root) as journal: journal.process(bundle())
    with ShadowJournal(root) as journal:
        b = bundle([signal("s2")]); b["request_id"] = "r2"
        r = journal.process(b)
        assert r["decisions"][0]["reason"] == "symbol_overlap"
    with ShadowJournal(root) as journal:
        b = bundle([terminal()]); b["request_id"] = "r3"
        r = journal.process(b)
        assert len(r["state_after"]["terminals"]) == 1
        assert not r["state_after"]["reservations"]


@pytest.mark.parametrize("fault", ["partial", "hash", "state", "duplicate_key"])
def test_corrupt_prefix_never_repaired_or_reapplied(tmp_path, fault):
    root = tmp_path / "store"
    with ShadowJournal(root) as journal: journal.process(bundle())
    path = root / "journal.jsonl"
    raw = path.read_bytes()
    if fault == "partial": raw += b'{"partial"'
    elif fault == "hash": raw = raw.replace(b"FIXTURE_ONLY", b"ALTERED_ONLY")
    elif fault == "state": raw = raw.replace(b'"last_decision_ms":', b'"last_decision_ms":1,"old":')
    else: raw = raw.replace(b'"sequence":1', b'"sequence":1,"sequence":1')
    path.write_bytes(raw)
    with pytest.raises(BridgeBlocked): ShadowJournal(root)
    assert path.read_bytes() == raw


def test_one_writer_and_unexpected_external_append_suspend(tmp_path):
    root = tmp_path / "store"
    with ShadowJournal(root) as journal:
        with pytest.raises(BridgeBlocked, match="writer_busy"): ShadowJournal(root)
        journal.process(bundle())
        with (root / "journal.jsonl").open("ab") as stream: stream.write(b"{}\n")
        with pytest.raises(BridgeBlocked, match="journal_changed"): journal.process(bundle())


@pytest.mark.parametrize("fault", ["symlink", "hardlink", "parent_symlink", "unexpected_file"])
def test_unsafe_paths_cannot_write_a_foreign_journal(tmp_path, fault):
    root = tmp_path / "store"; root.mkdir()
    target = tmp_path / "foreign"; target.write_bytes(b"preserve")
    if fault == "symlink": (root / "journal.jsonl").symlink_to(target)
    elif fault == "hardlink": os.link(target, root / "journal.jsonl")
    elif fault == "parent_symlink":
        link = tmp_path / "alias"; link.symlink_to(root, target_is_directory=True); root = link / "child"
    else: (root / "stranger").write_text("untouched")
    with pytest.raises(BridgeBlocked): ShadowJournal(root)
    assert target.read_bytes() == b"preserve"


def test_disk_and_byte_bounds_suspend_without_append(tmp_path, monkeypatch):
    root = tmp_path / "store"
    with ShadowJournal(root) as journal:
        journal.process(bundle()); before = (root / "journal.jsonl").read_bytes()
        monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
        b = bundle(); b["request_id"] = "r2"
        with pytest.raises(BridgeBlocked, match="disk_bound"): journal.process(b)
        assert (root / "journal.jsonl").read_bytes() == before


def test_uncertain_fsync_poison_then_restart_recovers_exact_append(tmp_path, monkeypatch):
    root = tmp_path / "store"
    with ShadowJournal(root) as journal:
        real = os.fsync
        def fail(_): raise OSError("injected uncertainty")
        monkeypatch.setattr(os, "fsync", fail)
        with pytest.raises(BridgeBlocked, match="append_uncertain"): journal.process(bundle())
        monkeypatch.setattr(os, "fsync", real)
        with pytest.raises(BridgeBlocked, match="instance_poisoned"): journal.process(bundle())
    with ShadowJournal(root) as journal:
        r = journal.process(bundle())
        assert r["sequence"] == 1
        assert len(r["state_after"]["reservations"]) == 1


def test_resource_limits_and_oversize_startup(tmp_path, monkeypatch):
    import research_lab.os2_shadow_journal as module
    root = tmp_path / "store"
    with ShadowJournal(root) as journal:
        journal.process(bundle())
        monkeypatch.setattr(module, "MAX_RECEIPTS", 1)
        b = bundle(); b["request_id"] = "r2"
        with pytest.raises(BridgeBlocked, match="receipt_bound"): journal.process(b)
    monkeypatch.setattr(module, "MAX_JOURNAL_BYTES", 10)
    with pytest.raises(BridgeBlocked, match="journal_byte_bound"): ShadowJournal(root)
