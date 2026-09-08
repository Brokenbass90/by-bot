from copy import deepcopy
import pytest

from research_lab.att1_lifecycle_session import LifecycleSession, SessionViolation
from research_lab.att1_lifecycle_journal import LifecycleJournal, JournalViolation
from research_lab.att1_lifecycle_coordinator import replay_lifecycle, CoordinatorViolation
from test_att1_lifecycle_coordinator import fixture, ev, fill, start, exit_events, coverage, T


def test_restart_replay_matches_every_durable_boundary(tmp_path):
    profile,intent=fixture();path=tmp_path/'events.jsonl'
    events=start()+[ev('PRICE',100,bid='87.99',ask='88')]
    events+=exit_events(events,102,'0.05','88','0.0044')
    events.append(ev('PRICE',200,bid='74.99',ask='75'))
    events+=exit_events(events,202,'0.05','75','0.00375')
    events.append(coverage(300))
    session=LifecycleSession(path,profile,intent=intent)
    for i,event in enumerate(events):
        result=session.apply(event)
        restored=LifecycleSession(path,profile)
        assert result==restored.receipt==replay_lifecycle(profile,intent,events[:i+1])
        session=restored
    assert session.receipt['final_net_r']=='36637/20000'
    assert len(LifecycleJournal(path).read())==len(events)+1


def test_conflicts_or_invalid_transition_do_not_append(tmp_path):
    profile,intent=fixture();path=tmp_path/'events.jsonl'
    session=LifecycleSession(path,profile,intent=intent)
    session.apply(ev('ENTRY_ACK',31));before=path.read_bytes()
    assert session.apply(ev('ENTRY_ACK',31))==session.receipt
    assert path.read_bytes()==before
    bad=ev('ENTRY_ACK',31);bad['source_sha256']='b'*64
    with pytest.raises((CoordinatorViolation,JournalViolation)):session.apply(bad)
    with pytest.raises(CoordinatorViolation):session.apply(fill('EXIT_FILL',40,'0.1','90',exit_order_id='foreign'))
    assert path.read_bytes()==before


def test_stale_session_uses_latest_locked_journal_not_stale_memory(tmp_path):
    profile,intent=fixture();path=tmp_path/'events.jsonl'
    first=LifecycleSession(path,profile,intent=intent)
    second=LifecycleSession(path,profile)
    first.apply(fill('ENTRY_FILL',40,'0.04','100'))
    updated=second.apply(fill('ENTRY_FILL',42,'0.06','100'))
    assert updated['held_qty']=='1/10'
    assert LifecycleSession(path,profile).receipt==updated


def test_crash_after_fsync_before_publication_recovers_written_event(tmp_path,monkeypatch):
    profile,intent=fixture();path=tmp_path/'events.jsonl'
    session=LifecycleSession(path,profile,intent=intent)
    previous=deepcopy(session.receipt)
    original=session.journal.append_checked
    def crash(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('simulated crash after durable write')
    monkeypatch.setattr(session.journal,'append_checked',crash)
    with pytest.raises(RuntimeError):session.apply(fill('ENTRY_FILL',40,'0.1','100'))
    assert session.receipt==previous
    assert LifecycleSession(path,profile).receipt['held_qty']=='1/10'


def test_restart_cannot_change_intent_profile_or_runtime_code(tmp_path,monkeypatch):
    profile,intent=fixture();path=tmp_path/'events.jsonl'
    LifecycleSession(path,profile,intent=intent)
    other=deepcopy(intent);other['book']='another'
    with pytest.raises(SessionViolation):LifecycleSession(path,profile,intent=other)
    import research_lab.att1_lifecycle_session as module
    monkeypatch.setattr(module,'implementation_hash',lambda:'f'*64)
    with pytest.raises(SessionViolation,match='implementation'):LifecycleSession(path,profile)


def test_no_missing_journal_reset_and_no_torn_record_repair(tmp_path):
    profile,intent=fixture();path=tmp_path/'events.jsonl'
    with pytest.raises(SessionViolation):LifecycleSession(path,profile)
    assert not path.exists()
    LifecycleSession(path,profile,intent=intent)
    raw=path.read_bytes()[:-1];path.write_bytes(raw)
    with pytest.raises(JournalViolation):LifecycleSession(path,profile,intent=intent)
    assert path.read_bytes()==raw
