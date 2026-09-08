from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

import pytest

from research_lab.att1_lifecycle_journal import JournalViolation, LifecycleJournal


def event(eid='e1', **changes):
    return {'schema_id': 'att1_lifecycle_event_v1', 'event_id': eid, 'kind': 'ENTRY_ACK', **changes}


def test_missing_read_is_empty_without_creating_file(tmp_path):
    path = tmp_path / 'events.jsonl'
    journal = LifecycleJournal(path)
    assert journal.read() == ()
    assert journal.tip() == {'rows': 0, 'tip_hash': '0' * 64}
    assert not path.exists()


def test_append_reopen_and_exact_idempotence(tmp_path):
    path = tmp_path / 'events.jsonl'
    journal = LifecycleJournal(path)
    assert journal.append(event()) is True
    original = path.read_bytes()
    assert journal.append(event()) is False
    assert path.read_bytes() == original
    assert journal.append(event('e2', qty='0.1')) is True
    assert LifecycleJournal(path).read() == (event(), event('e2', qty='0.1'))
    assert journal.tip()['rows'] == 2
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(JournalViolation, match='conflict'):
        journal.append(event(qty='2'))


@pytest.mark.parametrize('damage', ['truncate', 'sequence', 'previous', 'event', 'hash', 'duplicate_key', 'noncanonical'])
def test_corrupted_evidence_fails_without_repair(tmp_path, damage):
    path = tmp_path / 'events.jsonl'
    journal = LifecycleJournal(path)
    journal.append(event())
    raw = path.read_bytes()
    row = json.loads(raw)
    if damage == 'truncate':
        broken = raw[:-1]
    elif damage == 'duplicate_key':
        broken = raw.replace(b'"seq":1', b'"seq":1,"seq":1')
    elif damage == 'noncanonical':
        broken = b' ' + raw
    else:
        if damage == 'sequence': row['seq'] = 2
        if damage == 'previous': row['prev_hash'] = 'a' * 64
        if damage == 'event': row['event']['kind'] = 'EXIT_FILL'
        if damage == 'hash': row['hash'] = 'b' * 64
        broken = json.dumps(row, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    assert broken != raw
    path.write_bytes(broken)
    with pytest.raises(JournalViolation): journal.read()
    with pytest.raises(JournalViolation): journal.append(event('e2'))
    assert path.read_bytes() == broken


@pytest.mark.parametrize('invalid', [event('', qty='1'), event('x'*257), event(v=float('nan')), event(v=float('inf')), event(v=object()), {'schema_id':'wrong','event_id':'e'}])
def test_invalid_events_never_create_a_journal(tmp_path, invalid):
    path = tmp_path / 'events.jsonl'
    with pytest.raises(JournalViolation): LifecycleJournal(path).append(invalid)
    assert not path.exists()


def test_file_and_parent_symlinks_and_hardlinks_rejected(tmp_path):
    real = tmp_path / 'real'; real.mkdir()
    path = real / 'events.jsonl'
    LifecycleJournal(path).append(event())
    original = path.read_bytes()
    link = tmp_path / 'filelink'; link.symlink_to(path)
    parentlink = tmp_path / 'dirlink'; parentlink.symlink_to(real, target_is_directory=True)
    for p in (link, parentlink/'events.jsonl'):
        with pytest.raises(JournalViolation): LifecycleJournal(p).read()
        with pytest.raises(JournalViolation): LifecycleJournal(p).append(event('e2'))
    hard = tmp_path / 'hard'; os.link(path, hard)
    with pytest.raises(JournalViolation): LifecycleJournal(path).read()
    with pytest.raises(JournalViolation): LifecycleJournal(hard).append(event('e2'))
    assert path.read_bytes() == original


def test_mode_nonregular_and_competing_writer_fail(tmp_path):
    path = tmp_path / 'events.jsonl'; journal = LifecycleJournal(path)
    journal.append(event())
    path.chmod(0o644)
    with pytest.raises(JournalViolation, match='mode'): journal.read()
    path.chmod(0o600)
    with path.open('rb') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(JournalViolation, match='locked'): journal.read()
        with pytest.raises(JournalViolation, match='locked'): journal.append(event('e2'))
    directory = tmp_path / 'directory'; directory.mkdir()
    with pytest.raises(JournalViolation): LifecycleJournal(directory).read()
    fifo = tmp_path / 'fifo'; os.mkfifo(fifo, 0o600)
    with pytest.raises(JournalViolation): LifecycleJournal(fifo).read()


def test_size_bounds_are_enforced_without_repair(tmp_path):
    path = tmp_path / 'events.jsonl'; journal = LifecycleJournal(path)
    journal.append(event())
    original = path.read_bytes()
    with pytest.raises(JournalViolation, match='size'): LifecycleJournal(path, max_bytes=len(original)-1).read()
    with pytest.raises(JournalViolation, match='size'): LifecycleJournal(path, max_bytes=len(original)).append(event('e2'))
    with pytest.raises(JournalViolation, match='record'): LifecycleJournal(path, max_record_bytes=30).read()
    with pytest.raises(JournalViolation, match='record'): LifecycleJournal(path, max_record_bytes=30).append(event('e2'))
    assert path.read_bytes() == original
    for kwargs in ({'max_bytes': True}, {'max_bytes': 0}, {'max_record_bytes': -1}):
        with pytest.raises(JournalViolation): LifecycleJournal(path, **kwargs)


def test_nested_duplicate_key_and_nonfinite_json_rejected(tmp_path):
    path = tmp_path / 'events.jsonl'; journal = LifecycleJournal(path)
    journal.append(event())
    raw = path.read_bytes()
    for broken in (raw.replace(b'"kind":"ENTRY_ACK"', b'"kind":"ENTRY_ACK","kind":"ENTRY_ACK"'), raw.replace(b'"kind":"ENTRY_ACK"', b'"kind":NaN')):
        path.write_bytes(broken)
        with pytest.raises(JournalViolation): journal.read()
