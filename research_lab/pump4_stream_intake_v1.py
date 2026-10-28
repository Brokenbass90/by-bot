"""Confirmed public WS bars into the EXISTING frozen DATA journals/outbox.

No financial owner/provider is constructed here. Positive observations retain
existing admission through independently fresh HTTPS causal_plan in TrustedSources.
"""
from contextlib import contextmanager
import hashlib,time
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.pump4_supervisor_v1 import Supervisor,read,need
from research_lab.pump4_account_owner_v1 import safe
from research_lab.pump4_bybit_sources_v1 import universe,H
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_source_probe_v1 import Probe,decode
from research_lab.pump4_warm_reducer_v1 import WarmIntake

def clock_guard(start_wall,start_mono,wall,mono):
 need(wall>=start_wall and mono>=start_mono and abs((wall-start_wall)-(mono-start_mono)/1e6)<=1000,'STREAM_WALL_MONOTONIC_DISCONTINUITY')

class StreamIntake(Supervisor):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.owned=False
 @contextmanager
 def _writer(self):
  need(not self.owned,'STREAM_REENTRANT_WRITER')
  with super()._writer():
   self.owned=True
   try:yield
   finally:self.owned=False
 def prepare(self,hour,instruments):
  need(self.owned and type(hour) is int and hour%H==0 and self.clock()<hour,'STREAM_PREBOUNDARY_PREPARE')
  previous_warm=getattr(self,'warm',{})
  self.anchor=(self.clock(),time.monotonic_ns());self.hour=hour;self.folder=safe(self.root/'ws-hours'/str(hour));self.acks=None;self.dead=False;self.frames=0;self.bytes=0;self.warm={};self.probes={};self.rows={};self.pins={};self.expected_trading=0
  publish(self.folder/'attempt.json',dict(schema='PUMP4_WS_HOUR_ATTEMPT_V1',target_ms=hour,observed_ms=self.clock(),orders_allowed=False,money_authority=False))
  for symbol in universe():
   instrument=instruments.get(symbol)
   if not instrument or any(instrument.get(k)!=v for k,v in dict(status='Trading',quoteCoin='USDT',contractType='LinearPerpetual').items()):
    self.rows[symbol]=dict(symbol=symbol,status='UNAVAILABLE_INSTRUMENT',instrument=instrument);continue
   self.expected_trading+=1
   path=safe(self.root/'intake'/(symbol+'.jsonl'))
   try:
    intake=Pump4Intake(path,symbol);events=intake.journal.read();cached=previous_warm.get(symbol)
    warm=cached if cached is not None and cached.reusable(intake,events) else WarmIntake(intake)
    epoch=read(self.root/'epochs'/(symbol+'.json'))
    need(epoch['schema']=='PUMP4_DATA_EPOCH_V1' and epoch['symbol']==symbol and epoch['financial_authority'] is False and epoch['seed_sha256']==warm.state['seed_bars_sha256'] and warm.events[0]['observed_ms']<epoch['epoch_started_ms']<=hour,'STREAM_ORIGINAL_EPOCH')
    # A committed journal with a missing outbox is always recovery, never CURRENT.
    for d in warm.state['decisions']:
     obs=safe(self.root/'observations'/(d['decision_id']+'.json'))
     if not obs.exists():publish(obs,dict(schema='PUMP4_DATA_DECISION_OBSERVATION_V1',decision=d,archive_id=digest(dict(recovered_symbol=symbol,decision_id=d['decision_id'])),mode='RECOVERY_REPLAY',status='RECOVERY_NOT_PROSPECTIVE',orders_allowed=False,money_authority=False))
    need(warm.state['cursor_ms']==hour-2*H,'STREAM_RECOVERY_REQUIRED')
    self.warm[symbol]=warm;self.probes[symbol]=Probe(hour,[symbol])
    publish(self.folder/'prefixes'/(symbol+'.json'),dict(symbol=symbol,journal_prefix_sha256=hashlib.sha256(warm.prefix).hexdigest(),cursor_ms=warm.state['cursor_ms'],epoch=epoch,prepared_ms=self.clock()))
   except (ValueError,KeyError,TypeError,OSError) as exc:self.rows[symbol]=dict(symbol=symbol,status='BLOCKED_PREFIX',reason=str(exc))
  need(self.clock()<hour,'STREAM_PRELOAD_MISSED_BOUNDARY')
  return tuple(self.probes)
 def ack(self,received_ms):
  need(self.owned and type(received_ms) is int,'STREAM_ACK')
  self.acks=received_ms
  publish(self.folder/'subscription-ack.json',dict(received_ms=received_ms,preboundary=received_ms<self.hour))
 def disconnect(self,reason):
  need(self.owned,'STREAM_WRITER_REQUIRED');self.dead=True
  publish(self.folder/'disconnect.json',dict(observed_ms=self.clock(),reason=reason,orders_allowed=False))
 def observed_now(self):
  wall=self.clock()
  try:clock_guard(*self.anchor,wall,time.monotonic_ns())
  except (ValueError,TypeError):
   self.dead=True;raise
  return wall
 def feed(self,raw,*,received_ms,received_monotonic_ns=None):
  need(self.owned and type(raw) is str and len(raw.encode())<=1000000,'STREAM_FRAME_BOUND')
  self.frames+=1;self.bytes+=len(raw.encode());need(self.frames<=50000 and self.bytes<=134217728,'STREAM_CAPTURE_BOUND')
  cap=dict(schema='PUMP4_WS_RAW_CAPTURE_V1',endpoint='wss://stream.bybit.com/v5/public/linear',connection=1,received_ms=received_ms,received_monotonic_ns=(time.monotonic_ns() if received_monotonic_ns is None else received_monotonic_ns),raw=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest())
  path=self.folder/'frames'/(str(self.frames)+'.json');publish(path,cap)
  clock_guard(*self.anchor,received_ms,cap['received_monotonic_ns'])
  self.observed_now() # A clock step during raw fsync cannot pass using receive time.
  need(not self.dead,'STREAM_DISCONNECTED_NO_SAME_HOUR_RETRY')
  value=decode(raw)
  if 'topic' not in value:return None
  topic=value['topic'];need(type(topic) is str and topic.startswith('kline.60.'),'STREAM_TOPIC');symbol=topic[9:]
  need(symbol in self.probes,'STREAM_UNSELECTED_SYMBOL');p=self.probes[symbol]
  try:p.add(raw,received_ms=received_ms,connection=1)
  except (ValueError,KeyError,TypeError) as exc:
   self.rows[symbol]=dict(symbol=symbol,status='BLOCKED_WS_SCHEMA',reason=str(exc));raise
  self.pins.setdefault(symbol,[]).append(dict(path=str(path),sha256=digest(cap)))
  summary=p.summary()['symbols'][symbol]
  opened=p.opened.get(symbol)
  if opened is not None and (opened['received_ms']<self.hour or opened['server_ms']<self.hour):
   self.rows[symbol]=dict(symbol=symbol,status='BLOCKED_PREBOUNDARY_NEW_OPEN')
   return self.rows[symbol]
  if summary['conflict']:
   self.rows[symbol]=dict(symbol=symbol,status='BLOCKED_WS_CONFLICT');return self.rows[symbol]
  if symbol in self.rows:return self.rows[symbol]
  if summary['pair_first_received_ms'] is None:return None
  need(self.acks is not None and self.acks<self.hour,'STREAM_PREBOUNDARY_ACK_REQUIRED')
  now=self.observed_now();need(now>=received_ms and now>=self.hour,'STREAM_RECEIVE_CLOCK')
  bar=[self.hour-H,*map(float,p.closed[symbol]['values'][:5])];marker=self.folder/'batches'/(symbol+'.json')
  need(not marker.exists(),'STREAM_PARTIAL_BATCH_RECOVERY_ONLY')
  identity=digest(dict(hour=self.hour,symbol=symbol,frames=self.pins[symbol]))
  publish(marker,dict(symbol=symbol,archive_id=identity,bar=bar,available_ms=summary['pair_first_received_ms'],observed_ms=now,raw_captures=self.pins[symbol],recovery_only_on_restart=True))
  try:
   result=self.warm[symbol].accept(bar,available_ms=summary['pair_first_received_ms'],observed_ms=now)
   need(result['new'],'STREAM_RECOVERED_NOT_CURRENT')
   published_now=self.observed_now() # Includes append/fsync; a failed check leaves recovery-only history.
   d=result['decision'];mode='CURRENT_CLOSED_BAR' if 0<=published_now-self.hour<=60000 else 'LATE_DATA_ONLY'
   obs=dict(schema='PUMP4_DATA_DECISION_OBSERVATION_V1',decision=d,archive_id=identity,mode=mode,status='NO_SIGNAL' if d['signal'] is None else 'STREAM_SIGNAL_REQUIRES_FRESH_HTTPS',orders_allowed=False,money_authority=False)
   publish(self.root/'observations'/(d['decision_id']+'.json'),obs)
   receipt=dict(symbol=symbol,status='CLOSED_H1_INTAKE_PASS',mode=mode,accepted_bars=1,cursor_ms=bar[0],decisions=[obs],publication_completed_ms=self.clock(),pair_received_ms=summary['pair_first_received_ms'],source_kind='CONFIRMED_WS_WITH_FROZEN_JOURNAL_PREFIX',broker_writes=0,orders_allowed=False,money_authority=False)
   publish(self.folder/'published'/(symbol+'.json'),receipt);self.rows[symbol]=receipt;return receipt
  except BaseException:
   self.warm[symbol].broken=True;raise

 def finish(self):
  need(self.owned,'STREAM_WRITER_REQUIRED')
  rows=[self.rows.get(s,dict(symbol=s,status='BLOCKED_DISCONNECT' if self.dead else 'MISSING_CONFIRMED_PAIR')) for s in universe()]
  receipt=dict(schema='PUMP4_WS_FULL137_DATA_RECEIPT_V1',source_hour_open_ms=self.hour,census=137,rows=rows,complete_pairs=sum(r['status']=='CLOSED_H1_INTAKE_PASS' for r in rows),within60s=sum(r['status']=='CLOSED_H1_INTAKE_PASS' and 0<=r['publication_completed_ms']-self.hour<=60000 for r in rows),broker_writes=0,financial_owner_constructed=False,orders_allowed=False,money_authority=False)
  receipt.update(expected_trading=self.expected_trading,disconnected=self.dead,hour_pass=(not self.dead and self.expected_trading>0 and receipt['within60s']==self.expected_trading and all(r['status'] in ('CLOSED_H1_INTAKE_PASS','UNAVAILABLE_INSTRUMENT') for r in rows)))
  publish(self.folder/'receipt.json',receipt);return receipt
