import copy,importlib
from pathlib import Path
import pytest
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from test_pump4_supervisor_v1 import fixture_candidate
from test_pump4_bybit_sources_v1 import NOW,H

def warm(intake):
 try:m=importlib.import_module('research_lab.pump4_warm_reducer_v1')
 except ImportError:pytest.fail('Warm reducer is missing')
 return m.WarmIntake(intake)

def seed(tmp_path):
 source=fixture_candidate(tmp_path/'fixture')['intake'];other=Pump4Intake(tmp_path/'warm.jsonl','ZROUSDT');events=source.journal.read()
 other.seed(events[0]['bars'],available_ms=events[0]['available_ms'],observed_ms=events[0]['observed_ms'])
 return source,other,events[1]['bar']

def test_same_full_decision_and_bytes_as_frozen_replay(tmp_path):
 reference,intake,bar=seed(tmp_path);w=warm(intake)
 expected=reference.snapshot()['decisions'][-1];got=w.accept(bar,available_ms=expected['available_ms'],observed_ms=expected['first_observed_ms'])
 assert got==dict(new=True,decision=expected)
 assert intake.journal.path.read_bytes()==reference.journal.path.read_bytes()
 assert w.snapshot()==reference.snapshot()

@pytest.mark.parametrize('fault',['prefix','gap','ambient'])
def test_drift_never_appends_or_mutates_warm_state(tmp_path,monkeypatch,fault):
 _,intake,bar=seed(tmp_path);w=warm(intake);before=intake.journal.path.read_bytes();state=w.snapshot()
 if fault=='prefix':w.events[0]['bars'][0][-1]+=1
 elif fault=='gap':bar=copy.deepcopy(bar);bar[0]+=H
 else:monkeypatch.setenv('PF_TEST_DRIFT','1')
 with pytest.raises(ValueError):w.accept(bar,available_ms=NOW+H,observed_ms=NOW+H)
 assert intake.journal.path.read_bytes()==before
 if fault!='prefix':assert w.snapshot()==state

def test_failed_fsync_does_not_advance_memory(tmp_path,monkeypatch):
 _,intake,bar=seed(tmp_path);w=warm(intake);state=w.snapshot()
 def fail(*a):raise OSError('injected fsync failure')
 monkeypatch.setattr('research_lab.att1_lifecycle_journal.os.fsync',fail)
 with pytest.raises(ValueError):w.accept(bar,available_ms=NOW,observed_ms=NOW+2)
 assert w.snapshot()==state

def test_external_append_invalidates_cache(tmp_path):
 _,intake,bar=seed(tmp_path);w=warm(intake);intake.accept(bar,available_ms=NOW,observed_ms=NOW+2)
 nextbar=copy.deepcopy(bar);nextbar[0]+=H
 with pytest.raises(ValueError):w.accept(nextbar,available_ms=NOW+H,observed_ms=NOW+H+2)
 assert len(intake.journal.read())==2


def test_continuation_positive_cooldown_negative_duplicate_and_restart_match(tmp_path):
 reference,intake,bar=seed(tmp_path);w=warm(intake);first=reference.snapshot()['decisions'][-1]
 assert w.accept(bar,available_ms=first['available_ms'],observed_ms=first['first_observed_ms'])['decision']==first
 for index in range(1,31):
  nextbar=copy.deepcopy(bar);nextbar[0]+=index*H;available=nextbar[0]+H+1
  expected=reference.accept(nextbar,available_ms=available,observed_ms=available)
  assert w.accept(nextbar,available_ms=available,observed_ms=available)==expected
  assert intake.journal.path.read_bytes()==reference.journal.path.read_bytes()
  assert w.snapshot()==reference.snapshot()
  if index==8:w=warm(intake)
 assert w.accept(nextbar,available_ms=available+500,observed_ms=available+500)['new'] is False
 assert w.snapshot()==reference.snapshot()
