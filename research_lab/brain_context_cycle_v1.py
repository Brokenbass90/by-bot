"""Causal existing BTC context -> versioned WAIT/defer -> future market annotation.

Descriptive market returns are not strategy outcomes, a cost estimate or a Brain
profitability test. No model/strategy/financial authority or sealed data reader.
"""
import ast,hashlib,math
from pathlib import Path
from research_lab.pump4_brain_timely_v1 import (
 FrozenBrain,POLICY_SOURCE_SHA,FROZEN_SIGNAL_PINS,read_bytes,digest,need,stamp,H,
)
from research_lab.att1_lifecycle_journal import LifecycleJournal,SCHEMA

DOMAIN='BRAIN_CONTEXT_CAUSAL_CYCLE_V1'
VERSION='EXISTING_CONTEXT_WAIT_V1'


def bars_from_events(events,*,observed_ms):
 need(isinstance(events,(tuple,list)) and 1<=len(events)<=4000,'CONTEXT_EVENT_BOUND')
 bars=[];previous=None
 for i,e in enumerate(events):
  need(e.get('schema_id')==SCHEMA and e.get('domain_schema')=='PUMP4_CLOSED_H1_INTAKE_V1'
       and e.get('symbol')=='BTCUSDT' and e.get('source_pins')==FROZEN_SIGNAL_PINS,'CONTEXT_SOURCE')
  need(e.get('kind')==('HISTORICAL_SEED' if i==0 else 'CLOSED_BAR'),'CONTEXT_EVENT_KIND')
  a,o=e.get('available_ms'),e.get('observed_ms')
  need(stamp(a) and stamp(o) and a<=o<=observed_ms,'CONTEXT_FUTURE_SOURCE')
  rows=e['bars'] if i==0 else [e['bar']]
  need(isinstance(rows,list) and len(rows)<=1000,'CONTEXT_ROWS')
  for b in rows:
   need(isinstance(b,list) and len(b)==6 and stamp(b[0]) and b[0]>0 and b[0]%H==0,'CONTEXT_BAR')
   need(all(type(v) in (int,float) and math.isfinite(v) for v in b[1:]),'CONTEXT_NUMBER')
   t,op,hi,lo,cl,vol=b
   need(0<lo<=min(op,cl)<=max(op,cl)<=hi and vol>=0 and t+H<=a,'CONTEXT_OHLC_TIME')
   need(previous is None or t==previous+H,'CONTEXT_GAP');previous=t;bars.append(b)
 need(400<=len(bars)<=5000,'CONTEXT_WARMUP')
 return bars


def frozen_context(policy_path,bars,observed_ms):
 raw=read_bytes(policy_path);need(hashlib.sha256(raw).hexdigest()==POLICY_SOURCE_SHA,'POLICY_SOURCE_PIN')
 nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='_kontekst_v1']
 need(len(nodes)==1,'CONTEXT_FUNCTION')
 env={'U':'UNKNOWN','H':H};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(policy_path),'exec'),env)
 return env['_kontekst_v1'](observed_ms,bars)


def assessment(events,census,*,policy_path,observed_ms,epoch_ms):
 need(stamp(observed_ms) and stamp(epoch_ms) and epoch_ms<=observed_ms,'CONTEXT_CLOCK')
 bars=bars_from_events(events,observed_ms=observed_ms);closed=bars[-1][0]+H
 need(0<=observed_ms-closed<H,'CONTEXT_STALE')
 need(census.get('source_complete') is True and census.get('hour_ms')==closed
      and type(census.get('expected_trading')) is int and census['expected_trading']>0
      and census.get('observations')==census['expected_trading']
      and type(census.get('signals')) is int and 0<=census['signals']<=census['observations'],'CENSUS_INCOMPLETE')
 brain=FrozenBrain(policy_path);context=frozen_context(policy_path,bars,observed_ms)
 start=(observed_ms//H+1)*H
 return dict(schema_id=SCHEMA,event_id=f'context:{closed}:{epoch_ms}',domain=DOMAIN,kind='MARKET_CONTEXT_DECISION',
  observed_ms=observed_ms,epoch_ms=epoch_ms,source_closed_ms=closed,source_events_sha256=digest(list(events)),source_prefix_events=len(events),
  source_census=census,policy_source_sha256=POLICY_SOURCE_SHA,policy_sha=brain.sha,context_version=VERSION,
  adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),context=context,
  action='WAIT_NO_FROZEN_SIGNAL' if census['signals']==0 else 'DEFER_TO_EXISTING_SIGNAL_SHADOW',
  comparison=brain.evaluate(None) if census['signals']==0 else 'UNKNOWN_REUSE_EXISTING_SIGNAL_SHADOW',
  covered_sleeve='PUMP4',other_sleeves='NOT_ASSESSED',outcome_status='PENDING_OUTCOME',
  outcome_bar_open_ms=start,outcome_bar_close_ms=start+H,
  outcome_contract='NEXT_FULL_FUTURE_BTC_H1_RETURN_DESCRIPTIVE_NOT_TRADE_PNL',
  money_authority=False,orders_allowed=False,economic_pass=False)


def durability_witness(decision,*,completed_ms,recovered=False):
 need(stamp(completed_ms) and completed_ms>=decision['observed_ms'],'CONTEXT_DURABLE_CLOCK')
 return dict(schema_id=SCHEMA,event_id=decision['event_id']+':durable',domain=DOMAIN,kind='CONTEXT_DURABILITY_WITNESS',
  decision_id=decision['event_id'],decision_sha256=digest(decision),observed_ms=completed_ms,
  before_outcome_open=completed_ms<decision['outcome_bar_open_ms'],recovered=recovered,
  economic_pass=False,money_authority=False,orders_allowed=False)


def outcome(decision,events,*,observed_ms,witness=None):
 need(decision.get('domain')==DOMAIN and decision.get('kind')=='MARKET_CONTEXT_DECISION','JOIN_DECISION')
 need(stamp(observed_ms) and observed_ms>=decision['observed_ms'],'JOIN_CLOCK')
 if observed_ms<decision['outcome_bar_close_ms']:return None
 n=decision['source_prefix_events']
 need(type(n) is int and n>0 and len(events)>=n and digest(list(events[:n]))==decision['source_events_sha256'],'SOURCE_PREFIX_CHANGED')
 if witness is None:return None
 need(witness.get('decision_sha256')==digest(decision) and witness.get('decision_id')==decision['event_id']
      and decision['observed_ms']<=witness['observed_ms']<=observed_ms,'JOIN_DURABLE_WITNESS')
 if witness.get('before_outcome_open') is not True:return None
 need(witness['observed_ms']<decision['outcome_bar_open_ms'],'JOIN_LATE_WITNESS')
 bars=bars_from_events(events,observed_ms=observed_ms)
 b=next((b for b in bars if b[0]==decision['outcome_bar_open_ms']),None)
 if b is None:return None
 need(decision['observed_ms']<b[0] and b[0]+H==decision['outcome_bar_close_ms'],'JOIN_FUTURE_ONLY')
 return dict(schema_id=SCHEMA,event_id=decision['event_id']+':outcome',domain=DOMAIN,kind='MARKET_OUTCOME_JOIN',
  decision_id=decision['event_id'],decision_sha256=digest(decision),observed_ms=observed_ms,
  source_events_sha256=digest(list(events)),bar=b,market_return_pct=(b[4]/b[1]-1)*100,
  strategy_net_comparison='NOT_APPLICABLE_NO_TRADING_OPPORTUNITY' if decision['source_census']['signals']==0 else 'UNKNOWN_NEEDS_TRADE_MODEL',
  economic_pass=False,money_authority=False,orders_allowed=False)


def reduce_events(events):
 by_id={}
 for e in events:
  need(e.get('domain')==DOMAIN and e.get('schema_id')==SCHEMA and e.get('money_authority') is False
       and e.get('orders_allowed') is False and e.get('economic_pass') is False,'CONTEXT_DOMAIN')
  need(e['event_id'] not in by_id,'CONTEXT_DUPLICATE')
  if e['kind']=='CONTEXT_DURABILITY_WITNESS':
   d=by_id.get(e.get('decision_id'))
   need(d is not None and digest(d)==e.get('decision_sha256') and stamp(e.get('observed_ms'))
        and e['observed_ms']>=d['observed_ms'] and type(e.get('before_outcome_open')) is bool
        and e['before_outcome_open']==(e['observed_ms']<d['outcome_bar_open_ms']),'DURABLE_WITNESS_LINK')
  elif e['kind']=='MARKET_OUTCOME_JOIN':
   d=by_id.get(e.get('decision_id'))
   w=by_id.get(e.get('decision_id','')+':durable')
   need(d is not None and digest(d)==e.get('decision_sha256') and e['observed_ms']>=d['outcome_bar_close_ms']
        and w is not None and w['before_outcome_open'] is True,'JOIN_LINK')
  else:need(e['kind']=='MARKET_CONTEXT_DECISION','CONTEXT_KIND')
  by_id[e['event_id']]=e
 return by_id


def record(path,event):
 journal=LifecycleJournal(path,max_bytes=8*1024*1024)
 new,_=journal.append_checked(event,reduce_events);return new
