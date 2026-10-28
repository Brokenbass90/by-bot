import copy,importlib,json
import pytest
from research_lab.pump4_bybit_sources_v1 import universe
from research_lab.pump4_supervisor_v1 import Supervisor
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.alpaca_dynamic_v1 import digest
from test_pump4_supervisor_v1 import fixture_candidate
from test_pump4_bybit_sources_v1 import NOW,H
from test_pump4_source_probe_v1 import msg


def module():
 try:return importlib.import_module('research_lab.pump4_stream_intake_v1')
 except ImportError:pytest.fail('Integrated stream intake missing')

def fixture(tmp_path):
 m=module();c=fixture_candidate(tmp_path/'source');reference=c['intake'];root=tmp_path/'state';base=Supervisor(root,clock=lambda:NOW-100)
 path=root/'intake/ZROUSDT.jsonl';path.parent.mkdir();events=reference.journal.read();seed=events[0]
 from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
 i=Pump4Intake(path,'ZROUSDT');i.seed(seed['bars'],available_ms=seed['available_ms'],observed_ms=seed['observed_ms'])
 publish(root/'epochs/ZROUSDT.json',dict(schema='PUMP4_DATA_EPOCH_V1',symbol='ZROUSDT',epoch_started_ms=NOW-1,seed_sha256=digest(seed['bars']),financial_authority=False))
 t=[NOW-100];s=m.StreamIntake(root,clock=lambda:t[0]);return s,t,events[-1]['bar'],reference.snapshot()['decisions'][-1]

def metadata():
 return {s:dict(status='Trading' if s=='ZROUSDT' else 'Settled',quoteCoin='USDT',contractType='LinearPerpetual') for s in universe()}

def frame(bar):
 rows=[dict(start=bar[0],end=bar[0]+H-1,interval='60',open=str(bar[1]),high=str(bar[2]),low=str(bar[3]),close=str(bar[4]),volume=str(bar[5]),turnover='0',confirm=True,timestamp=NOW+100),dict(start=NOW,end=NOW+H-1,interval='60',open='100',high='100',low='100',close='100',volume='0',turnover='0',confirm=False,timestamp=NOW+100)]
 return json.dumps(dict(topic='kline.60.ZROUSDT',type='snapshot',ts=NOW+100,data=rows))

def arm(s):s.prepare(NOW,metadata());s.ack(NOW-50)

def test_real_stream_reaches_same_frozen_signal_and_existing_observation_schema(tmp_path):
 s,t,bar,expected=fixture(tmp_path)
 with s._writer():
  arm(s);t[0]=NOW+200;r=s.feed(frame(bar),received_ms=NOW+150)
 assert r['status']=='CLOSED_H1_INTAKE_PASS' and r['mode']=='CURRENT_CLOSED_BAR'
 obs=json.loads((s.root/'observations'/(expected['decision_id']+'.json')).read_text());got=obs['decision'];assert {k:v for k,v in got.items() if k not in ('available_ms','first_observed_ms')}=={k:v for k,v in expected.items() if k not in ('available_ms','first_observed_ms')}
 assert obs['orders_allowed'] is False and obs['money_authority'] is False and obs['status']=='STREAM_SIGNAL_REQUIRES_FRESH_HTTPS'
 assert r['publication_completed_ms']==NOW+200
 with s._writer():assert len(s.finish()['rows'])==137

@pytest.mark.parametrize('fault',['late_ack','disconnect','malformed','unconfirmed','gap'])
def test_bad_stream_never_publishes_current_signal(tmp_path,fault):
 s,t,bar,_=fixture(tmp_path)
 with s._writer():
  s.prepare(NOW,metadata());s.ack(NOW+1 if fault=='late_ack' else NOW-50);t[0]=NOW+200
  raw=frame(bar)
  if fault=='disconnect':s.disconnect('test')
  elif fault=='malformed':raw='{bad'
  elif fault=='unconfirmed':v=json.loads(raw);v['data'][0]['confirm']=False;raw=json.dumps(v)
  elif fault=='gap':v=json.loads(raw);v['data'][0]['start']-=H;v['data'][0]['end']-=H;raw=json.dumps(v)
  try:s.feed(raw,received_ms=NOW+150)
  except ValueError:pass
 assert not list((s.root/'observations').glob('*.json'))
 assert list((s.root/'ws-hours'/str(NOW)/'frames').glob('*.json'))


def test_crash_after_journal_before_observation_is_recovery_only(tmp_path,monkeypatch):
 s,t,bar,expected=fixture(tmp_path);m=module();original=m.publish
 with s._writer():
  arm(s);t[0]=NOW+200
  def fail(path,value):
   if path.parent.name=='observations':raise OSError('injected crash')
   return original(path,value)
  monkeypatch.setattr(m,'publish',fail)
  with pytest.raises(OSError):s.feed(frame(bar),received_ms=NOW+150)
 monkeypatch.setattr(m,'publish',original);s2=m.StreamIntake(s.root,clock=lambda:NOW+H-100)
 with s2._writer():s2.prepare(NOW+H,metadata())
 obs=json.loads((s.root/'observations'/(expected['decision_id']+'.json')).read_text());assert obs['mode']=='RECOVERY_REPLAY' and obs['decision']['first_observed_ms']==NOW+200


def test_full137_existing_history_one_new_bar_and_complete_receipt(tmp_path,monkeypatch):
 from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
 m=module();root=tmp_path/'full137';s=m.StreamIntake(root,clock=lambda:NOW-100);bars=[[i*H,100.,100.,100.,100.,0.] for i in range(NOW//H-201,NOW//H-1)]
 (root/'intake').mkdir()
 for symbol in universe():
  i=Pump4Intake(root/'intake'/(symbol+'.jsonl'),symbol);i.seed(bars,available_ms=NOW-H,observed_ms=NOW-H)
  publish(root/'epochs'/(symbol+'.json'),dict(schema='PUMP4_DATA_EPOCH_V1',symbol=symbol,epoch_started_ms=NOW-1,seed_sha256=digest(bars),financial_authority=False))
 md={v:dict(status='Trading',quoteCoin='USDT',contractType='LinearPerpetual') for v in universe()}
 from types import SimpleNamespace
 monkeypatch.setattr(m,'time',SimpleNamespace(monotonic_ns=lambda:int((s.clock()-(NOW-100))*1000000)))
 with s._writer():
  assert len(s.prepare(NOW,md))==137;s.ack(NOW-50);s.clock=lambda:NOW+200
  for symbol in universe():
   raw=frame([NOW-H,100.,100.,100.,100.,0.]);v=json.loads(raw);v['topic']='kline.60.'+symbol;s.feed(json.dumps(v),received_ms=NOW+150)
  r=s.finish()
 assert r['hour_pass'] and r['within60s']==137 and r['census']==137
 assert len(list((root/'observations').glob('*.json')))==137


def test_blocked_prefix_cannot_pass_with_zero_subscriptions(tmp_path):
 s,t,bar,_=fixture(tmp_path);(s.root/'epochs/ZROUSDT.json').unlink()
 with s._writer():
  assert not s.prepare(NOW,metadata());assert not s.finish()['hour_pass']


def test_clock_step_during_receive_preserves_raw_but_no_outbox(tmp_path):
 s,t,bar,_=fixture(tmp_path)
 with s._writer():
  arm(s);t[0]=NOW+2001
  with pytest.raises(ValueError):s.feed(frame(bar),received_ms=NOW+2001)
 assert not list((s.root/'observations').glob('*.json'))
 assert list((s.root/'ws-hours'/str(NOW)/'frames').glob('*.json'))


@pytest.mark.parametrize('at',['raw','append'])
def test_clock_step_inside_processing_never_reaches_outbox(tmp_path,monkeypatch,at):
 s,t,bar,_=fixture(tmp_path);m=module();original=m.publish
 with s._writer():
  arm(s);t[0]=NOW+200
  if at=='raw':
   def moved(path,value):
    out=original(path,value)
    if path.parent.name=='frames':t[0]+=2000
    return out
   monkeypatch.setattr(m,'publish',moved)
  else:
   original_accept=s.warm['ZROUSDT'].accept
   def moved(*a,**kw):
    out=original_accept(*a,**kw);t[0]+=2000;return out
   monkeypatch.setattr(s.warm['ZROUSDT'],'accept',moved)
  with pytest.raises(ValueError):s.feed(frame(bar),received_ms=NOW+150)
 assert not list((s.root/'observations').glob('*.json'))


def test_normal_next_hour_reuses_verified_resident_without_rewarming(tmp_path,monkeypatch):
 from scripts import run_pump4_stream_v1 as cli
 from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
 s,t,bar,_=fixture(tmp_path)
 with s._writer():
  arm(s);t[0]=NOW+200;s.feed(frame(bar),received_ms=NOW+150);s.finish()
 cached=s.warm['ZROUSDT'];t[0]=NOW+H-100
 def forbidden(*a,**kw):pytest.fail('UNCHANGED_RESIDENT_MUST_NOT_REPLAY_FULL_HISTORY_EACH_HOUR')
 monkeypatch.setattr(Pump4Intake,'_replay',forbidden)
 with s._writer():
  result=cli.recover(s,NOW,metadata(),get=lambda *a:pytest.fail('No missing bars'))
  assert not result['blocked']
  assert s.prepare(NOW+H,metadata())==('ZROUSDT',)
 assert s.warm['ZROUSDT'] is cached


@pytest.mark.parametrize('server_offset,receive_offset',[(-80,-80),(10,-50),(-50,20)])
def test_preboundary_new_open_never_produces_current_or_hour_pass(tmp_path,server_offset,receive_offset):
 s,t,bar,_=fixture(tmp_path);value=json.loads(frame(bar));value['data']=value['data'][1:]
 value['ts']=NOW+server_offset;value['data'][0]['timestamp']=NOW+server_offset
 with s._writer():
  arm(s);t[0]=NOW+receive_offset
  try:s.feed(json.dumps(value),received_ms=NOW+receive_offset)
  except ValueError:pass
  value=json.loads(frame(bar));value['data']=value['data'][:1];t[0]=NOW+200
  try:s.feed(json.dumps(value),received_ms=NOW+150)
  except ValueError:pass
  assert not s.finish()['hour_pass']
 assert not list((s.root/'observations').glob('*.json'))
