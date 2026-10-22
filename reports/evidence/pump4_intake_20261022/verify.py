"""Closed-bar state + plan parity only. Never evaluate outcomes or broker API."""
import argparse,hashlib,json,socket,sys,time
from dataclasses import asdict
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--research-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
a=p.parse_args();root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
research=a.research_root.resolve();assert not a.output.resolve().is_relative_to(research)
assert not a.output.exists(),'EXCLUSIVE_OUTPUT_REQUIRED'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def denied(*a,**k):raise AssertionError('NETWORK_DENIED')
class NoNetwork(socket.socket):connect=denied;connect_ex=denied;sendto=denied
socket.socket=NoNetwork;socket.create_connection=denied
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_execution_plan_v1 import build_plan,frozen_sources,HOUR_MS as H
from strategies.pump_fade_v4r import PumpFadeV4RStrategy
from strategies.signals import TradeSignal
source={n:sha(root/n) for n in ('research_lab/pump4_closed_bar_intake_v1.py','research_lab/att1_lifecycle_journal.py','research_lab/pump4_execution_plan_v1.py',*frozen_sources())}
fixture=research/'research_lab/results/pump4_fixtures_v1_20261020.json'
assert sha(fixture)=='f6badf311e888fab05a3d4131559f98152f8589d49b35c7b034e306617726ca4'
fx=json.loads(fixture.read_bytes())['fixtures']
previous=json.loads((root/'reports/evidence/pump4_execution_plan_20261021/parity.json').read_bytes())
inputs={};loaded={};rows=[];started=time.monotonic()
scratch=a.output.parent/(a.output.stem+'-journals');scratch.mkdir()
def prefix(f):
 sym=f['sym'];ts=f['signal_bar_open_ms'];path=research/f'research_lab/data/oos_bybit_h1_20261020/{sym}.json'
 rel=str(path.relative_to(research))
 if sym not in loaded:
  inputs[rel]=sha(path);assert inputs[rel]==previous['input_files'][rel]
  loaded[sym]=json.loads(path.read_bytes())
 b=[r for r in loaded[sym] if r[0]>=ts-1000*H]
 idx=next(i for i,r in enumerate(b) if r[0]==ts)
 assert idx==1000 and hashlib.sha256(json.dumps(b[:idx+1]).encode()).hexdigest()==f['bary_sha256']
 return b,idx
for i,f in enumerate(fx):
 if f['status']!='OK':continue
 b,idx=prefix(f);sym=f['sym'];stamp=b[idx][0]
 journal=scratch/f'fixture-{i}.jsonl';intake=Pump4Intake(journal,sym)
 intake.seed(b[:idx],available_ms=stamp,observed_ms=stamp)
 result=intake.accept(b[idx],available_ms=stamp+H,observed_ms=stamp+H)
 signal=result['decision']['signal'];expected=f['signal']
 assert signal is not None and {k:signal[k] for k in expected}==expected
 assert signal['side']==f['side'] and signal['reason']==f['reason']
 plan=build_plan(TradeSignal(**signal),signal_bar_open_ms=stamp,next_open_ms=b[idx+1][0],next_open=b[idx+1][1])
 ref=f['ispolnenie_V1']
 assert [plan['entry'],plan['stop'],*plan['targets'],*plan['fractions'],plan['hold_bars']]==[ref['vhod'],ref['stop_x4'],ref['tp1'],ref['tp2'],ref['dolya_tp1'],ref['ostatok_na_tp2'],ref['uderzhanie_barov']]
 before=journal.read_bytes();again=Pump4Intake(journal,sym).accept(b[idx],available_ms=stamp+H+1,observed_ms=stamp+H+1)
 assert again['new'] is False and again['decision']==result['decision'] and journal.read_bytes()==before
 rows.append(dict(symbol=sym,bar_open_ms=stamp,signal_and_plan_match=True,restart_duplicate_preserved=True))
assert len(rows)==65
cooldown=[]
for sym in ('ZROUSDT','BLESSUSDT'):
 f=min((x for x in fx if x['status']=='OK' and x['sym']==sym),key=lambda x:x['signal_bar_open_ms'])
 b,idx=prefix(f);stamp=b[idx][0];continuous=PumpFadeV4RStrategy()
 for bar in b[200:idx]:continuous.maybe_signal(sym,*bar)
 journal=scratch/(sym+'-cooldown.jsonl');intake=Pump4Intake(journal,sym)
 intake.seed(b[:idx],available_ms=stamp,observed_ms=stamp)
 check=[]
 for j in range(idx,idx+27):
  bar=b[j];signal=continuous.maybe_signal(sym,*bar)
  result=Pump4Intake(journal,sym).accept(bar,available_ms=bar[0]+H,observed_ms=bar[0]+H)
  decision=result['decision']
  assert decision['signal']==(None if signal is None else asdict(signal))
  assert decision['cooldown_remaining']==continuous._cooldown
  if 1<=j-idx<=24:assert signal is None
  before=journal.read_bytes()
  assert Pump4Intake(journal,sym).accept(bar,available_ms=bar[0]+H+1,observed_ms=bar[0]+H+1)['new'] is False
  assert journal.read_bytes()==before
  check.append(dict(hours_from_parent=j-idx,signal_present=signal is not None,cooldown=continuous._cooldown))
 assert check[0]['signal_present'] is True
 cooldown.append(dict(symbol=sym,parent_bar_open_ms=stamp,closed_bars_checked=len(check),rows=check))
assert all(sha(research/n)==h for n,h in inputs.items()) and sha(fixture)==previous['fixture_sha256']
assert all(sha(root/n)==h for n,h in source.items())
out=dict(schema='PUMP4_CLOSED_H1_INTAKE_PARITY_RECEIPT_V1',status='CLOSED_H1_CURSOR_COOLDOWN_COMPONENT_PASS',
 source_files=source,fixture_sha256=sha(fixture),research_input_files=inputs,research_inputs_unchanged=True,
 fixture_signal_plan_matches=65,fixture_source_unavailable=1,restart_duplicate_checks=65,
 cooldown_restart_rows=54,cooldown_cases=cooldown,rows=rows,
 replay_policy='exact accepted index200 seed invocation then continuous retained history; no moving reset',
 elapsed_seconds=round(time.monotonic()-started,3),outcomes_or_pnl_computed=False,
 clock_provenance='HISTORICAL_FIXTURE_CLOCK_ONLY',full_137_universe_census='NOT_RUN',
 broker_execution='NOT_IMPLEMENTED',native_stop_execution='NOT_RUN',tiny_readiness='NOT_READY',
 broker_requests=0,broker_writes=0,orders_allowed=False,money_authority=False,network_denied=True)
with a.output.open('x') as f:json.dump(out,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('source_files','research_input_files','cooldown_cases','rows')}))
