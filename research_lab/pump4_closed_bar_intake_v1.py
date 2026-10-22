"""PUMP4 closed-H1 cursor/cooldown, ORDERS_OFF; no broker or strategy changes.

Reuses the existing fsynced, locked hash-chain storage in a separate per-symbol
journal. Its historical ATT1 envelope name is storage only: domain/schema checks
reject foreign events. No ATT1 runtime or journal is opened by this module.
"""
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import re

from research_lab.alpaca_dynamic_v1 import canonical, digest
from research_lab.att1_lifecycle_journal import LifecycleJournal, SCHEMA
from research_lab.pump4_execution_plan_v1 import HOUR_MS, frozen_sources
from strategies.pump_fade_v4r import PumpFadeV4RStrategy

DOMAIN='PUMP4_CLOSED_H1_INTAKE_V1'
REPLAY_POLICY='FROZEN_RESEARCH_INDEX_200_THEN_CONTINUOUS_NO_WINDOW_RESET'


def _require(ok, reason):
    if not ok:raise ValueError('PUMP4_INTAKE_'+reason)


def _bar(bar):
    _require(isinstance(bar,list) and len(bar)==6,'BAR_SCHEMA')
    ts,*values=bar
    _require(type(ts) is int and ts>0 and ts%HOUR_MS==0,'BAR_TIME')
    _require(all(type(v) in (int,float) and math.isfinite(v) for v in values),'BAR_NUMBER')
    o,h,l,c,v=values
    _require(0<l<=min(o,c)<=max(o,c)<=h and v>=0,'BAR_OHLC_VOLUME')
    return bar


def _closed(bar, available, observed):
    _bar(bar)
    _require(type(available) is int and type(observed) is int
        and bar[0]+HOUR_MS<=available<=observed,'BAR_NOT_CLOSED_OR_CLOCK')


class Pump4Intake:
    """Caller-supplied clocks/source are not authenticated execution admission.

    Explicit seed bars are historical, never actionable decisions. Fresh records
    are returned only after journal fsync. Consumers must reconcile stable
    decision IDs after response loss; `new` alone is not an execution outbox.
    """
    def __init__(self,path,symbol):
        _require(isinstance(symbol,str) and re.fullmatch(r'[A-Z0-9]{1,24}USDT',symbol),'SYMBOL')
        self.symbol=symbol
        self.journal=LifecycleJournal(path)

    def _context(self):
        return dict(domain_schema=DOMAIN,symbol=self.symbol,source_pins=frozen_sources(),
            intake_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            replay_policy=REPLAY_POLICY)

    def _replay(self,events):
        _require(bool(events),'SEED_REQUIRED')
        context=self._context();seed=events[0]
        common={'schema_id','event_id',*context,'kind','available_ms','observed_ms'}
        for e in events:
            _require(all(e.get(k)==v for k,v in context.items()),'DOMAIN_OR_SOURCE_CONFLICT')
        _require(seed.get('kind')=='HISTORICAL_SEED'
            and set(seed)==common|{'bars'}
            and seed['event_id']=='pump4:'+self.symbol+':seed','SEED_SCHEMA')
        bars=seed['bars']
        _require(isinstance(bars,list) and 200<=len(bars)<=1000,'SEED_LENGTH')
        previous=None
        for b in bars:
            _closed(b,seed['available_ms'],seed['observed_ms'])
            _require(previous is None or b[0]==previous+HOUR_MS,'SEED_GAP')
            previous=b[0]
        strategy=PumpFadeV4RStrategy()
        # Exact accepted fixture/pereschet call sequence, not a new warmup rule.
        for b in bars[200:]:strategy.maybe_signal(self.symbol,*b)
        history=hashlib.sha256(canonical(bars));decisions=[]
        for e in events[1:]:
            _require(e.get('kind')=='CLOSED_BAR' and set(e)==common|{'bar'},'EVENT_SCHEMA')
            b=e['bar'];_closed(b,e['available_ms'],e['observed_ms'])
            _require(e['event_id']=='pump4:'+self.symbol+':'+str(b[0]),'EVENT_IDENTITY')
            _require(b[0]==previous+HOUR_MS,'BAR_GAP_OR_OLD')
            signal=strategy.maybe_signal(self.symbol,*b)
            history.update(canonical(b));previous=b[0]
            value=None if signal is None else asdict(signal)
            core=dict(domain_schema=DOMAIN,symbol=self.symbol,bar_open_ms=b[0],
                history_sha256=history.hexdigest(),source_pins=context['source_pins'],signal=value)
            decisions.append(dict(core,decision_id='pump4-'+digest(core),
                available_ms=e['available_ms'],first_observed_ms=e['observed_ms'],
                cooldown_remaining=strategy._cooldown,
                clock_provenance='CALLER_PROVIDED_NOT_AUTHENTICATED',
                execution_admission='NOT_PERFORMED',universe_validation='NOT_PERFORMED',
                orders_allowed=False,money_authority=False))
        return dict(cursor_ms=previous,cooldown_remaining=strategy._cooldown,
            seed_bars_sha256=digest(bars),decisions=decisions,
            historical_seed_decisions_credited=0,orders_allowed=False,money_authority=False)

    def seed(self,bars,*,available_ms,observed_ms):
        context=self._context()
        event=dict(schema_id=SCHEMA,event_id='pump4:'+self.symbol+':seed',**context,
            kind='HISTORICAL_SEED',bars=bars,available_ms=available_ms,observed_ms=observed_ms)
        self._replay((event,)) # Reject malformed seed before creating storage.
        existing=self.journal.read()
        if existing:
            state=self._replay(existing)
            _require(canonical(existing[0]['bars'])==canonical(bars),'SEED_CONFLICT')
            return dict(new=False,**state)
        new,state=self.journal.append_checked(event,self._replay)
        return dict(new=new,**state)

    def accept(self,bar,*,available_ms,observed_ms):
        _closed(bar,available_ms,observed_ms)
        context=self._context();events=self.journal.read()
        state=self._replay(events)
        for event,decision in zip(events[1:],state['decisions']):
            if event['bar'][0]==bar[0]:
                _require(canonical(event['bar'])==canonical(bar),'CHANGED_DUPLICATE')
                return dict(new=False,decision=decision)
        _require(bar[0]==state['cursor_ms']+HOUR_MS,'BAR_GAP_OR_OLD')
        event=dict(schema_id=SCHEMA,event_id='pump4:'+self.symbol+':'+str(bar[0]),**context,
            kind='CLOSED_BAR',bar=bar,available_ms=available_ms,observed_ms=observed_ms)
        new,state=self.journal.append_checked(event,self._replay)
        # A concurrent duplicate can be discovered only under the append lock,
        # after another caller has also committed later hours. Return this bar.
        decision=next(d for d in state['decisions'] if d['bar_open_ms']==bar[0])
        return dict(new=new,decision=decision)

    def snapshot(self):
        """Read only; no creation or tail repair. Rebuild exact producer state."""
        return self._replay(self.journal.read())
