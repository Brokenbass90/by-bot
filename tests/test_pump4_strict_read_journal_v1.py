import copy,json,hashlib
from pathlib import Path
import pytest
from research_lab import att1_lifecycle_journal as base
from research_lab.pump4_strict_read_journal_v1 import Pump4StrictReadJournal as Fast

E=dict(schema_id=base.SCHEMA,event_id='one',payload={'values':[1,2.5,None]})
def chain(events):
 tip=base.GENESIS;out=b''
 for seq,e in enumerate(events,1):
  core=dict(seq=seq,prev_hash=tip,event=e,event_sha256=base._hash(e));tip=base._hash(core);out+=base._canonical(dict(core,hash=tip))+b'\n'
 return out

def result(cls,path,**limits):
 try:
  j=cls(path,**limits);return ('OK',j.read(),j.tip())
 except Exception as e:return (type(e).__name__,str(e))

def test_full_read_decodes_each_row_once_without_event_roundtrip(tmp_path,monkeypatch):
 p=tmp_path/'j';p.write_bytes(chain([E,dict(E,event_id='two')]));p.chmod(0o600);calls=[];old=base.json.loads
 def counted(*a,**k):calls.append(1);return old(*a,**k)
 monkeypatch.setattr(base.json,'loads',counted)
 assert len(Fast(p).read())==2
 assert len(calls)==2,'Full strict row decode already validates JSON-native values'

def corpus():
 good=chain([E,dict(E,event_id='two')]);one=chain([E])
 cases=[b'',one,good,chain([dict(E,payload=-0.0)]),chain([dict(E,payload='\ud800')]),chain([dict(E,payload=2**100)]),
 good[:-1],good+b'\n',good.replace(b'"seq":1',b'"seq":true'),good.replace(b'"seq":2',b'"seq":3'),good.replace(b'"event_id":"one"',b'"event_id":"changed"'),
 good.replace(b'"values":[1,2.5,null]',b'"values":[1,NaN,null]'),good.replace(b'"values":[1,2.5,null]',b'"values":[1,1e309,null]'),
 good.replace(b'"values":[1,2.5,null]',b'"values":[1,1e-999,null]'),good.replace(b'"event_id":"one"',b'"event_id":"one","event_id":"one"'),
 good.replace(b'"values":[1,2.5,null]',b'"values":[1,2.5,null],"values":[]'),chain([E,E]),one.replace(b'{',b'{ ',1),
 one.replace(b'"event":{',b'"extra":0,"event":{',1),one.replace(b'"schema_id":"'+base.SCHEMA.encode()+b'"',b'"schema_id":"foreign"'),
 one.replace(b'"event_id":"one"',b'"event_id":false'),chain([dict(E,event_id='')]),chain([dict(E,event_id='x'*257)]),
 one.replace(b'"payload":{"values":[1,2.5,null]}',b'"payload":Infinity'),one.replace(b'"event":',b'"event":null,"unused":',1)]
 return cases

@pytest.mark.parametrize('raw',corpus())
def test_exact_original_acceptance_full_result_and_error(tmp_path,raw):
 p=tmp_path/'j';p.write_bytes(raw);p.chmod(0o600)
 assert result(Fast,p)==result(base.LifecycleJournal,p)
 assert p.read_bytes()==raw

@pytest.mark.parametrize('limits',[{'max_bytes':10},{'max_record_bytes':10}])
def test_original_size_bounds(tmp_path,limits):
 p=tmp_path/'j';p.write_bytes(chain([E]));p.chmod(0o600)
 assert result(Fast,p,**limits)==result(base.LifecycleJournal,p,**limits)

def test_original_writer_identity_python_validation_and_aliases(tmp_path):
 assert Fast._append is base.LifecycleJournal._append and Fast._locked is base.LifecycleJournal._locked
 p=tmp_path/'j';j=Fast(p)
 for bad in [dict(E,payload=(1,2)),dict(E,payload={1:'x','1':'y'})]:
  with pytest.raises(base.JournalViolation):j.append(bad)
  assert not p.exists()
 mutable=copy.deepcopy(E);assert j.append(mutable);before=p.read_bytes();mutable['payload']['values'].append(99)
 assert j.read()[0]==E and p.read_bytes()==before
 view=j.read();view[0]['payload']['values'].append(77);assert j.read()[0]==E
 assert j.append(copy.deepcopy(E)) is False
 with pytest.raises(base.JournalViolation):j.append(dict(E,payload='conflict'))
 assert p.read_bytes()==before

def test_copied_real_btc_prefix_append_restart_and_exact_state(tmp_path):
 from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
 from research_lab.pump4_warm_reducer_v1 import WarmIntake
 p=Path(__file__).parent/'fixtures/pump4_btc_journal_prefix_20261103.jsonl.gz'
 import gzip
 raw=gzip.decompress(p.read_bytes());assert hashlib.sha256(raw).hexdigest()=='f41c50d88a0cc407dc2a0e55ff1a59b7c64076521ab9881e0c9cb030acdb16a7';lines=raw.splitlines(keepends=True);event=json.loads(lines[-1])['event'];outputs=[]
 for cls,name in [(base.LifecycleJournal,'reference'),(Fast,'fast')]:
  f=tmp_path/name;f.write_bytes(b''.join(lines[:-1]));f.chmod(0o600);i=Pump4Intake(f,'BTCUSDT');i.journal=cls(f);w=WarmIntake(i)
  got=w.accept(event['bar'],available_ms=event['available_ms'],observed_ms=event['observed_ms'])
  assert f.read_bytes()==raw;outputs.append((got,w.snapshot(),WarmIntake(i).snapshot()))
 assert outputs[0]==outputs[1]

def test_source_corruption_and_partial_tail_never_repaired(tmp_path):
 p=tmp_path/'j';p.write_bytes(chain([E]));p.chmod(0o600);j=Fast(p);j.read()
 for raw in [chain([E])+b'{',chain([E]).replace(b'2.5',b'2.6')]:
  p.write_bytes(raw)
  with pytest.raises(base.JournalViolation):j.append(dict(E,event_id='two'))
  assert p.read_bytes()==raw


def test_data_intake_binding_does_not_change_other_journal_users(tmp_path,monkeypatch):
 from research_lab import pump4_closed_bar_intake_v1 as intake
 from research_lab import pump4_account_owner_v1 as owner
 monkeypatch.setattr(intake,'LifecycleJournal',Fast)
 assert isinstance(intake.Pump4Intake(tmp_path/'data','BTCUSDT').journal,Fast)
 assert owner.LifecycleJournal is base.LifecycleJournal
 assert base.LifecycleJournal._load is not Fast._load


def test_failed_fsync_poisoning_is_preserved_in_warm_state(tmp_path,monkeypatch):
 from test_pump4_warm_reducer_v1 import seed
 from research_lab.pump4_warm_reducer_v1 import WarmIntake
 _,i,bar=seed(tmp_path);i.journal=Fast(i.journal.path);w=WarmIntake(i);state=w.snapshot()
 def fail(*args):raise OSError('injected fsync failure')
 monkeypatch.setattr(base.os,'fsync',fail)
 with pytest.raises(base.JournalViolation):w.accept(bar,available_ms=bar[0]+3600001,observed_ms=bar[0]+3600002)
 assert w.snapshot()==state and w.broken
 with pytest.raises(ValueError,match='REBUILD_REQUIRED'):w.accept(bar,available_ms=bar[0]+3600001,observed_ms=bar[0]+3600002)
