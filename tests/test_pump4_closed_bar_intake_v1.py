"""Durable PUMP4 intake: actual producer, disposable journals, no broker."""
import copy
import json
import os
from pathlib import Path

import pytest
from research_lab import pump4_closed_bar_intake_v1 as intake
from research_lab.att1_lifecycle_journal import JournalViolation

H=3600000

def bars(n=1000):
    return [[(i+1)*H,100.,101.,99.,100.,10.] for i in range(n)]

def seeded(tmp_path):
    obj=intake.Pump4Intake(tmp_path/'pump4.jsonl','ZROUSDT')
    seed=bars();obj.seed(seed,available_ms=1001*H,observed_ms=1001*H)
    return obj,seed

def test_missing_seed_never_processes_or_creates_journal(tmp_path):
    obj=intake.Pump4Intake(tmp_path/'events','ZROUSDT')
    with pytest.raises(ValueError,match='SEED_REQUIRED'):
        obj.accept(bars(1)[0],available_ms=2*H,observed_ms=2*H)
    assert not obj.journal.path.exists()

def test_restart_duplicate_has_same_decision_and_no_second_state_transition(tmp_path):
    obj,seed=seeded(tmp_path);bar=bars(1001)[-1]
    first=obj.accept(bar,available_ms=1002*H,observed_ms=1002*H)
    before=obj.journal.path.read_bytes()
    restarted=intake.Pump4Intake(obj.journal.path,'ZROUSDT')
    again=restarted.accept(bar,available_ms=1002*H+1,observed_ms=1002*H+5)
    assert first['new'] is True and again['new'] is False
    assert first['decision']==again['decision']
    assert again['decision']['orders_allowed'] is False
    assert obj.journal.path.read_bytes()==before and len(obj.journal.read())==2

@pytest.mark.parametrize('fault',['changed_duplicate','gap','old','open','future_available','bool_time','nan','ohlc','volume','timestamp','symbol'])
def test_rejected_bar_preserves_committed_bytes(tmp_path,fault):
    obj,_=seeded(tmp_path);bar=bars(1001)[-1]
    obj.accept(bar,available_ms=1002*H,observed_ms=1002*H)
    before=obj.journal.path.read_bytes();kw=dict(available_ms=1003*H,observed_ms=1003*H)
    proposed=bars(1002)[-1]
    if fault=='changed_duplicate':proposed=copy.deepcopy(bar);proposed[4]=100.5
    elif fault=='gap':proposed=bars(1003)[-1];kw=dict(available_ms=1004*H,observed_ms=1004*H)
    elif fault=='old':proposed=bars(2)[-1]
    elif fault=='open':kw['available_ms']=proposed[0]+H-1
    elif fault=='future_available':kw['available_ms']=kw['observed_ms']+1
    elif fault=='bool_time':kw['observed_ms']=True
    elif fault=='nan':proposed[4]=float('nan')
    elif fault=='ohlc':proposed[2]=98.
    elif fault=='volume':proposed[5]=-1.
    elif fault=='timestamp':proposed[0]+=1
    else:obj=intake.Pump4Intake(obj.journal.path,'BLESSUSDT')
    with pytest.raises((ValueError,JournalViolation)):obj.accept(proposed,**kw)
    assert obj.journal.path.read_bytes()==before

@pytest.mark.parametrize('fault',['short_seed','long_seed','gap','changed_seed','pf','tail'])
def test_seed_source_and_corrupt_tail_fail_closed(tmp_path,fault,monkeypatch):
    obj,seed=seeded(tmp_path);before=obj.journal.path.read_bytes()
    if fault=='short_seed':seed=seed[:199]
    elif fault=='long_seed':seed=bars(1002)
    elif fault=='gap':seed[500][0]+=H
    elif fault=='changed_seed':seed[1][4]=100.5
    elif fault=='pf':monkeypatch.setenv('PF_COOLDOWN_BARS','0')
    else:
        with obj.journal.path.open('ab') as f:f.write(b'{')
        before=obj.journal.path.read_bytes()
    with pytest.raises((ValueError,JournalViolation)):
        obj.seed(seed,available_ms=1004*H,observed_ms=1004*H)
    assert obj.journal.path.read_bytes()==before

def test_fsync_response_loss_recovers_existing_bar_without_append(tmp_path,monkeypatch):
    obj,_=seeded(tmp_path);original=os.fsync
    def lost(fd):
        original(fd)
        raise OSError('fixture fsync reply lost after durable write')
    with monkeypatch.context() as patch:
        patch.setattr(os,'fsync',lost)
        with pytest.raises(JournalViolation):obj.accept(bars(1001)[-1],available_ms=1002*H,observed_ms=1002*H)
    before=obj.journal.path.read_bytes()
    restarted=intake.Pump4Intake(obj.journal.path,'ZROUSDT')
    out=restarted.accept(bars(1001)[-1],available_ms=1002*H+2,observed_ms=1002*H+2)
    assert out['new'] is False and len(restarted.journal.read())==2
    assert restarted.journal.path.read_bytes()==before

def test_concurrent_duplicate_returns_requested_bar_even_after_next_bar_commits(tmp_path,monkeypatch):
    obj,_=seeded(tmp_path);first=bars(1001)[-1];second=bars(1002)[-1]
    original=obj.journal.append_checked;other=intake.Pump4Intake(obj.journal.path,'ZROUSDT')
    expected=[]
    def interleave(event,validate):
        expected.append(other.accept(first,available_ms=1002*H,observed_ms=1002*H)['decision'])
        other.accept(second,available_ms=1003*H,observed_ms=1003*H)
        return original(event,validate)
    monkeypatch.setattr(obj.journal,'append_checked',interleave)
    out=obj.accept(first,available_ms=1002*H,observed_ms=1002*H)
    assert out['new'] is False and out['decision']==expected[0]
    assert out['decision']['bar_open_ms']==first[0]
    assert len(obj.journal.read())==3


def test_existing_att1_journal_cannot_be_adopted_as_pump4(tmp_path):
    from research_lab.att1_lifecycle_journal import LifecycleJournal,SCHEMA
    path=tmp_path/'foreign.jsonl';journal=LifecycleJournal(path)
    journal.append(dict(schema_id=SCHEMA,event_id='foreign',kind='ATT1_EVENT'))
    before=path.read_bytes();obj=intake.Pump4Intake(path,'ZROUSDT')
    with pytest.raises(ValueError):obj.seed(bars(),available_ms=1001*H,observed_ms=1001*H)
    assert path.read_bytes()==before
