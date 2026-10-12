"""Frozen A3/A4 causal research ticks. No client, credentials or order path.

Reuses the A1/A2 context/scorer/caps and existing journal; does not resimulate
B3 streams, read outcomes, fit tables or authorize production policy.
"""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal, Context, localcontext
from types import MappingProxyType

from research_lab.brain_v2_frozen_primitives import (
    HOUR, ARMS, Opportunity, BrainBlocked, digest, _require, _pin, _time,
)
from research_lab import brain_v2_a1 as a1
from research_lab.os2_shadow_journal import ShadowJournal
from research_lab.os2_shadow_bridge import BridgeBlocked

TICK=HOUR//4
VERSION='BRAIN_V2_A3_A4_ORDERS_OFF'
A3_PIN='2740b6bad02f724eca1da94c695d9d2a08d341eb82c04ca355834f54e69ede21'
A4_PIN='45be1c5455423e8414900c5c11db759028906066d49cfbf79b97e824754bb9a4'
COST_MODEL='BRAIN_V2_A3_STREAM_R_NET6BP_2BP_BYBIT_FUNDING'
PINS=MappingProxyType({**a1.PINS,'addendum_a3_sha256':A3_PIN,'addendum_a4_sha256':A4_PIN})
SCOPE='RESEARCH_EXACT_15M_TICKS_SUPPLIED_SOURCES_NOT_BROKER_AUTHORITY'
_decimal=a1._decimal
_seal=a1._seal_state


def _request_fields(request):
    _require(isinstance(request,dict),'request_schema')
    common={'request_id','kind','source_hash','positions_known','protection_known'}
    allowed=(common|{'initial_equity_usd','epoch_start_ms','capital_known'} if request.get('kind')=='INIT'
             else common|{'tick_ms','known_at_ms','coverage_end_ms','batch_complete','terminals_complete',
                          'opportunities','contexts','entries','terminals'})
    _require(set(request)<=allowed,'unknown_request_fields')


def empty_brain_state():
    return _seal(dict(schema='BRAIN_V2_A3_STATE',version=VERSION,pins=dict(PINS),
                      epoch_start_ms=None,last_tick_ms=None,arms={},opportunities={},
                      terminals={},orders_allowed=False))


def _equity(arm):
    # A4 UNKNOWN cash is excluded entirely, not zero-priced or partly credited.
    return sum((_decimal(arm['closed'][k]['net_usd'],'state_terminal_cash')
                for k in sorted(arm['closed']) if arm['closed'][k]['status']=='KNOWN'),
               _decimal(arm['initial_equity_usd'],'state_initial_capital'))


def _validate_state(state):
    _require(isinstance(state,dict) and state.get('schema')=='BRAIN_V2_A3_STATE'
             and state.get('version')==VERSION and state.get('pins')==PINS
             and state.get('orders_allowed') is False,'state_identity')
    _require(_seal(state)['state_sha256']==state.get('state_sha256'),'state_hash')
    if state['epoch_start_ms'] is None:
        _require(state==empty_brain_state(),'state_uninitialized');return
    _require(set(state['arms'])==set(ARMS),'state_arms')
    for arm in state['arms'].values():
        _require(_decimal(arm['initial_equity_usd'],'state_initial_capital')>0
                 and _equity(arm)==_decimal(arm['realized_equity_usd'],'state_capital'),
                 'state_cash_identity')
        _require(set(arm['positions']).isdisjoint(arm['closed']),'state_finality_conflict')
        symbols=set()
        for key,p in arm['positions'].items():
            _require(key in state['opportunities'] and p['opportunity_id']==key
                     and p['symbol'] not in symbols and p['side'] in ('long','short')
                     and p['sleeve'] in a1.BAR_MS and _decimal(p['risk_usd'],'state_risk')>0
                     and _decimal(p['lev'],'state_lev')>0
                     and _decimal(p['notional_usd'],'state_notional')==
                         _decimal(p['risk_usd'],'state_risk')*_decimal(p['lev'],'state_lev'),
                     'state_position_identity')
            symbols.add(p['symbol'])
        for key,c in arm['closed'].items():
            _require(key in state['terminals'] and c['status'] in ('KNOWN','FUNDING_UNKNOWN'),
                     'state_terminal_identity')
            if c['status']=='FUNDING_UNKNOWN':
                _require(all(c[k] is None for k in ('net_usd','r_pnl_usd','slippage_usd','funding_usd')),
                         'state_unknown_cash')


def funding_summary(evidence, op, release_ms, tick_ms):
    """Require an independently pinned complete settlement calendar.

The adapter must retain actual calendar/archive bytes. No assumed8h interval,
empty-array coverage inference or receive-time replacement of publication time.
Only rates available by release are used; later rates remain missing per A4.
"""
    _require(isinstance(evidence,dict) and evidence.get('schema')=='BRAIN_V2_A3_FUNDING'
             and evidence.get('venue')=='bybit' and evidence.get('symbol')==op.symbol
             and _pin(evidence.get('source_hash')) and _pin(evidence.get('calendar_sha256'))
             and evidence.get('calendar_complete') is True
             and evidence.get('start_ms')==op.t_available and evidence.get('end_ms')==release_ms
             and _time(evidence.get('known_at_ms')) and evidence['known_at_ms']<=tick_ms,
             'funding_source_calendar_or_window_unknown')
    expected=evidence.get('expected_settlements');rates=evidence.get('rates')
    _require(isinstance(expected,list) and isinstance(rates,list) and len(expected)<=1000
             and len(rates)<=1000 and all(_time(t) and op.t_available<t<=release_ms for t in expected)
             and expected==sorted(set(expected)),'funding_settlement_calendar')
    seen=set();values={}
    for row in rates:
        _require(isinstance(row,dict) and set(row)=={'settlement_ms','rate','available_ms'},
                 'funding_rate_schema')
        t=row['settlement_ms'];available=row['available_ms']
        _require(_time(t) and t in expected and t not in seen and _time(available)
                 and available>=t,'funding_rate_identity_or_duplicate')
        seen.add(t)
        if row['rate'] is None or available>min(tick_ms,release_ms,evidence['known_at_ms']):
            continue
        values[t]=_decimal(row['rate'],'funding_rate_nonfinite')
    missing=sorted(set(expected)-set(values))
    with localcontext(Context(prec=50)):
        total=None if missing else str(sum((values[t] for t in sorted(values)),Decimal(0)))
    return dict(status='FUNDING_UNKNOWN' if missing else 'KNOWN',rate_sum=total,
                missing_settlements=missing,expected_count=len(expected),known_count=len(values),
                source_hash=evidence['source_hash'],calendar_sha256=evidence['calendar_sha256'],
                payload_sha256=digest(evidence))


def terminal_cash(risk,lev,R,side,funding):
    """A3 stream R already includes6bp/side. A4 unknown excludes whole cash."""
    with localcontext(Context(prec=50)):
        risk=_decimal(risk,'terminal_risk');lev=_decimal(lev,'terminal_lev')
        R=_decimal(R,'terminal_R');_require(risk>0 and lev>0 and side in ('long','short'),
                                          'terminal_sizing_or_side')
        _require(funding.get('status') in ('KNOWN','FUNDING_UNKNOWN'),'funding_summary_unknown')
        if funding['status']=='FUNDING_UNKNOWN':
            _require(funding.get('rate_sum') is None,'unknown_funding_not_zero')
            return dict(status='FUNDING_UNKNOWN',r_pnl_usd=None,slippage_usd=None,
                        funding_usd=None,net_usd=None)
        notional=risk*lev
        r_pnl=R*risk;slippage=Decimal('.0004')*notional
        paid=(1 if side=='long' else -1)*notional*_decimal(funding['rate_sum'],'funding_sum')
        return dict(status='KNOWN',r_pnl_usd=str(r_pnl),slippage_usd=str(slippage),
                    funding_usd=str(paid),net_usd=str(r_pnl-slippage-paid))


def funding_population_status(counts):
    """Coverage diagnostic only, never an admission gate or research judge."""
    _require(isinstance(counts,dict) and set(counts)==set(ARMS),'funding_arm_population')
    arms={};blocked=[];pending=[]
    for arm in ARMS:
        row=counts[arm];n=row.get('evaluated');unknown=row.get('funding_unknown')
        _require(type(n) is int and type(unknown) is int and 0<=unknown<=n,'funding_count')
        # Integer comparison makes exactly5% distinct from greater than5%.
        if n and unknown*20>n:blocked.append(arm)
        if n==0:pending.append(arm)
        arms[arm]={**row,'unknown_fraction':unknown/n if n else None}
    return dict(status='BLOCKED_DATA' if blocked else 'PENDING_POPULATION' if pending
                else 'FUNDING_COVERAGE_PASS',blocked_arms=blocked,pending_arms=pending,arms=arms)


def _coverage(state):
    rows={}
    for arm,a in state['arms'].items():
        unknown=[c for k,c in sorted(a['closed'].items()) if c['status']=='FUNDING_UNKNOWN']
        rows[arm]=dict(evaluated=len(a['closed']),funding_unknown=len(unknown),
                       unknown_slot_hours=str(sum((Decimal(c['hours']) for c in unknown),Decimal(0))),
                       unknown_risk_usd=str(sum((_decimal(c['risk_usd'],'risk') for c in unknown),Decimal(0))))
    return funding_population_status(rows)


def _release(events,state,tick):
    _require(isinstance(events,list) and len(events)<=1000,'terminal_population_unknown_or_bound')
    seen=set()
    for event in sorted(events,key=lambda e:e['opportunity_id']):
        key=event['opportunity_id']
        _require(key not in seen and key not in state['terminals'],'duplicate_terminal');seen.add(key)
        _require(key in state['opportunities'],'terminal_opportunity_unknown')
        op=Opportunity(**state['opportunities'][key]);hours=event.get('hours')
        _require(type(hours) is int and 1<=hours<=op.max_hold_h,'terminal_stream_hours')
        release=op.t_available+hours*HOUR
        # A complete sequential replay must provide the terminal on its scheduled
        # tick. Late outcome arrival cannot rewrite the intervening arm equity.
        _require(release==tick and _time(event.get('available_ms'))
                 and op.t_available<=event['available_ms']<=tick,'terminal_late_or_future')
        _require(event.get('source_hash')==op.source_hash and event.get('cost_model_id')==COST_MODEL,
                 'terminal_stream_source_cost')
        R=_decimal(event.get('R'),'terminal_R')
        funding=funding_summary(event.get('funding'),op,release,tick)
        for arm,a in state['arms'].items():
            if key not in a['positions']:continue
            p=a['positions'].pop(key)
            cash=terminal_cash(p['risk_usd'],p['lev'],str(R),p['side'],funding)
            a['closed'][key]={**cash,'opportunity_id':key,'arm':arm,'release_time':release,
                              'hours':hours,'risk_usd':p['risk_usd'],'notional_usd':p['notional_usd'],
                              'stream_sha256':op.source_hash,'event_sha256':digest(event),
                              'funding':funding,'included_in_cash_metrics':cash['status']=='KNOWN'}
            a['realized_equity_usd']=str(_equity(a))
        state['terminals'][key]=digest(event)


def _entry(op,entry):
    _require(isinstance(entry,dict) and set(entry)=={'lev','source_hash','t_available','entry_rule'}
             and entry.get('source_hash')==op.source_hash and entry.get('t_available')==op.t_available
             and entry.get('entry_rule')==op.entry_rule=='next_open','entry_source_time_or_outcome_fields')
    lev=_decimal(entry['lev'],'entry_lev_unknown');_require(lev>0,'entry_lev_nonpositive')
    return lev


def _assess_request(request,state):
    _validate_state(state)
    _request_fields(request)
    _require(isinstance(request,dict) and _pin(request.get('source_hash')),'request_source_unknown')
    _require(request.get('positions_known') is True and request.get('protection_known') is True,
             'positions_or_protection_unknown')
    after=deepcopy(state);decisions={};closed={}
    if request.get('kind')=='INIT':
        _require(state['epoch_start_ms'] is None,'epoch_already_initialized')
        equity=_decimal(request.get('initial_equity_usd'),'initial_capital_unknown')
        start=request.get('epoch_start_ms')
        _require(request.get('capital_known') is True and equity>0 and _time(start)
                 and start%TICK==0 and start>=a1.CUTOFF_MS,'initial_capital_or_epoch_unknown')
        after['epoch_start_ms']=start
        after['arms']={arm:dict(initial_equity_usd=str(equity),realized_equity_usd=str(equity),
                                positions={},closed={}) for arm in ARMS}
        status='EPOCH_INITIALIZED_ORDERS_OFF'
    else:
        _require(request.get('kind')=='TICK' and state['epoch_start_ms'] is not None,'request_kind_or_epoch')
        tick=request.get('tick_ms')
        expected=state['epoch_start_ms'] if state['last_tick_ms'] is None else state['last_tick_ms']+TICK
        _require(_time(tick) and tick==expected and tick%TICK==0,'tick_sequence')
        _require(request.get('known_at_ms')==tick and request.get('coverage_end_ms')==tick
                 and request.get('batch_complete') is True,'tick_unsealed_or_population_unknown')
        _require(request.get('terminals_complete') is True,'terminal_population_unknown')
        raw=request.get('opportunities')
        _require(isinstance(raw,list) and len(raw)<=1000,'opportunity_population_unknown_or_bound')
        xs=[Opportunity(**o) for o in raw]
        _require(len({o.id for o in xs})==len(xs) and
                 not any(o.id in state['opportunities'] for o in xs),'duplicate_opportunity')
        valid=[];offgrid=[]
        for op in xs:
            if op.t_available%TICK:offgrid.append(op);continue
            _require(op.t_available==tick,'opportunity_not_exact_tick')
            _require(op.cost_model_id==COST_MODEL and
                     a1.signal_available_ms(op.sleeve,op.t_signal)==op.t_available,
                     'opportunity_frozen_time_cost')
            valid.append(op)
        contexts=request.get('contexts');entries=request.get('entries')
        _require(isinstance(contexts,dict) and isinstance(entries,dict) and
                 set(contexts)==set(entries)=={op.id for op in xs},'context_entry_population')
        table=a1.load_table(a1.TABLE_PATH.read_bytes());hour=tick//HOUR*HOUR
        scores={o.id:a1.score_a1(o,table,*a1._context_labels(contexts[o.id],o,hour)) for o in valid}
        levs={o.id:_entry(o,entries[o.id]) for o in valid}
        before={arm:set(a['closed']) for arm,a in after['arms'].items()}
        _release(request.get('terminals'),after,tick)
        for arm in ARMS:
            a=after['arms'][arm];equity=_decimal(a['realized_equity_usd'],'capital_unknown')
            _require(equity>0,'realized_capital_nonpositive')
            ordered=sorted(valid,key=(lambda o:(-scores[o.id].z,o.t_available,o.id)) if arm=='BRAIN_DET'
                           else (lambda o:(o.t_available,o.id)))
            decisions[arm]=[]
            for op in ordered:
                s=scores[op.id];mult=s.multiplier if arm=='BRAIN_DET' else 1
                risk=Decimal('.005')*equity*_decimal(mult,'multiplier');lev=levs[op.id]
                p=dict(opportunity_id=op.id,symbol=op.symbol,sleeve=op.sleeve,side=op.side,
                       risk_usd=str(risk),notional_usd=str(risk*lev),lev=str(lev),entry_ms=tick,
                       entry_rule='next_open',context_hour_ms=hour,source_hash=op.source_hash)
                reason=a1._first_reject(a['positions'],p,equity,arm)
                decisions[arm].append({**p,'arm':arm,'accepted':reason is None,'reason':reason or 'accepted',
                    'multiplier':mult,'z':s.z,'mu_s':s.mu_s,'mu_context':s.mu_context,
                    'context_status':s.context_status,'context_sha256':contexts[op.id]['sha256'],
                    'equity_at_batch_usd':str(equity),'budget_usd':str(Decimal('.06')*equity)})
                if reason is None:a['positions'][op.id]=p
            decisions[arm].extend(dict(opportunity_id=o.id,arm=arm,accepted=False,reason='off_grid')
                                  for o in sorted(offgrid,key=lambda o:(o.t_available,o.id)))
            closed[arm]={k:a['closed'][k] for k in sorted(set(a['closed'])-before[arm])}
        after['opportunities'].update({op.id:asdict(op) for op in xs})
        after['last_tick_ms']=tick;status='TICK_RECORDED_ORDERS_OFF'
    after=_seal(after);_validate_state(after)
    return dict(status=status,version=VERSION,pins=dict(PINS),orders_allowed=False,money_authority=False,
                state_after=after,decisions=decisions,closed=closed,funding_coverage=_coverage(after),
                request=deepcopy(request),scope=SCOPE)


def assess_request(request,state):
    try:
        with localcontext(Context(prec=50)):return _assess_request(request,state)
    except BrainBlocked:raise
    except (KeyError,TypeError,ValueError,ArithmeticError,OSError) as error:
        raise BrainBlocked(f'malformed_or_unavailable_input:{type(error).__name__}') from error


class BrainJournal(ShadowJournal):
    receipt_schema='BRAIN_V2_A3_RECEIPT'
    state_schema='BRAIN_V2_A3_STATE'

    def initial_state(self):return empty_brain_state()

    def process(self,bundle):
        # Unknown top-level fields are rejected before append, including a
        # mistakenly supplied credential field. No hidden outcome override.
        try:_request_fields(bundle)
        except BrainBlocked as error:raise BridgeBlocked('BLOCKED_DATA',str(error)) from error
        return super().process(bundle)

    @staticmethod
    def evaluate(request,state):
        try:return assess_request(request,state)
        except BrainBlocked as error:
            return dict(status='BLOCKED_DATA',reason=str(error),version=VERSION,pins=dict(PINS),
                        orders_allowed=False,money_authority=False,state_after=deepcopy(state),
                        decisions={},closed={},funding_coverage=None,request=deepcopy(request),scope=SCOPE)

    def assess(self,bundle):return self.evaluate(bundle,self.state)

    def _load(self):
        super()._load();state=self.initial_state()
        for receipt in self.receipts.values():
            try:
                request=receipt['request'];expected=self.evaluate(request,state)
                valid=(request['request_id']==receipt['request_id'] and digest(request)==receipt['input_sha256']
                       and all(receipt[k]==v for k,v in expected.items())
                       and set(receipt)==set(expected)|{'schema','sequence','request_id','input_sha256',
                                                        'previous_sha256','sha256'})
                if not valid:raise ValueError('semantic replay mismatch')
                state=expected['state_after']
            except (ValueError,KeyError,TypeError) as error:
                raise BridgeBlocked('BLOCKED_DATA','brain_a3_journal_semantic_replay_mismatch') from error
        self.state=state
