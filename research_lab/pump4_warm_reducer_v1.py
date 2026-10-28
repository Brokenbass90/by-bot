"""Resident cache of the unchanged frozen producer; never execution authority.

The journal still verifies its complete hash chain under its original lock.
Only an exact previously verified prefix may reuse warmed strategy state.
Restart rebuilds that state; failed durability poisons this instance.
"""
import copy,hashlib
from dataclasses import asdict
from research_lab.alpaca_dynamic_v1 import canonical,digest
from research_lab.pump4_closed_bar_intake_v1 import DOMAIN,_closed
from research_lab.att1_lifecycle_journal import SCHEMA
from research_lab.pump4_execution_plan_v1 import HOUR_MS
from strategies.pump_fade_v4r import PumpFadeV4RStrategy


def need(ok,reason):
 if not ok:raise ValueError('PUMP4_WARM_'+reason)

class WarmIntake:
 def __init__(self,intake):
  self.intake=intake;self.events=copy.deepcopy(intake.journal.read());self.broken=False
  self.context=intake._context();verified=intake._replay(self.events)
  self.strategy=PumpFadeV4RStrategy();bars=self.events[0]['bars']
  for b in bars[200:]:self.strategy.maybe_signal(intake.symbol,*b)
  self.history=hashlib.sha256(canonical(bars));decisions=[]
  for e in self.events[1:]:
   self.history.update(canonical(e['bar']));signal=self.strategy.maybe_signal(intake.symbol,*e['bar'])
   decisions.append(self._decision(e,signal,self.strategy,self.history))
  self.state=dict(cursor_ms=(self.events[-1]['bar'][0] if len(self.events)>1 else bars[-1][0]),cooldown_remaining=self.strategy._cooldown,seed_bars_sha256=digest(bars),decisions=decisions,historical_seed_decisions_credited=0,orders_allowed=False,money_authority=False)
  need(self.state==verified,'BOOTSTRAP_PARITY');self.prefix=canonical(self.events)

 def _decision(self,event,signal,strategy,history):
  core=dict(domain_schema=DOMAIN,symbol=self.intake.symbol,bar_open_ms=event['bar'][0],history_sha256=history.hexdigest(),source_pins=self.context['source_pins'],signal=None if signal is None else asdict(signal))
  return dict(core,decision_id='pump4-'+digest(core),available_ms=event['available_ms'],first_observed_ms=event['observed_ms'],cooldown_remaining=strategy._cooldown,clock_provenance='CALLER_PROVIDED_NOT_AUTHENTICATED',execution_admission='NOT_PERFORMED',universe_validation='NOT_PERFORMED',orders_allowed=False,money_authority=False)

 def reusable(self,intake,verified_events):
  # verified_events must come from the existing complete locked journal reader.
  return (not self.broken and intake.journal.path==self.intake.journal.path
   and intake._context()==self.context and canonical(self.events)==self.prefix
   and canonical(verified_events)==self.prefix)

 def snapshot(self):return copy.deepcopy(self.state)

 def accept(self,bar,*,available_ms,observed_ms):
  need(not self.broken,'DURABILITY_OR_PREFIX_FAILURE_REBUILD_REQUIRED')
  need(self.intake._context()==self.context and canonical(self.events)==self.prefix,'CONTEXT_OR_MEMORY_DRIFT')
  _closed(bar,available_ms,observed_ms)
  duplicate=bar[0]==self.state['cursor_ms'] and len(self.events)>1
  if duplicate:
   need(bar==self.events[-1]['bar'],'CHANGED_DUPLICATE');event=copy.deepcopy(self.events[-1])
  else:
   need(bar[0]==self.state['cursor_ms']+HOUR_MS,'GAP_OR_OLD')
   event=dict(schema_id=SCHEMA,event_id='pump4:'+self.intake.symbol+':'+str(bar[0]),**self.context,kind='CLOSED_BAR',bar=copy.deepcopy(bar),available_ms=available_ms,observed_ms=observed_ms)
  pending=[]
  def validate(events):
   need(self.intake._context()==self.context,'LOCKED_CONTEXT_DRIFT')
   if canonical(events)==self.prefix:return self.snapshot()
   need(len(events)==len(self.events)+1 and canonical(events[:-1])==self.prefix and events[-1]==event,'LOCKED_PREFIX_DRIFT')
   strategy=copy.deepcopy(self.strategy);history=self.history.copy();history.update(canonical(bar));signal=strategy.maybe_signal(self.intake.symbol,*bar)
   state=self.snapshot();state.update(cursor_ms=bar[0],cooldown_remaining=strategy._cooldown);state['decisions'].append(self._decision(event,signal,strategy,history));pending.append((strategy,history,state));return state
  try:new,state=self.intake.journal.append_checked(event,validate)
  except BaseException:
   self.broken=True;raise
  if not new and not duplicate:
   self.broken=True;raise ValueError('PUMP4_WARM_EXTERNAL_DUPLICATE_REBUILD_REQUIRED')
  if new:
   need(len(pending)==1,'VALIDATOR_COMMIT_IDENTITY');self.strategy,self.history,self.state=pending[0];self.events=(*self.events,copy.deepcopy(event));self.prefix=canonical(self.events)
  decision=next(d for d in state['decisions'] if d['bar_open_ms']==bar[0])
  return dict(new=new,decision=copy.deepcopy(decision))
