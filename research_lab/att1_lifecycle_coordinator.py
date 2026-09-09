"""Pure ATT1 lifecycle coordinator. All orders/fills are simulated evidence.

Admission is recomputed from full source inputs; immutable raw events remain the
recovery authority. No broker, process, filesystem or network capability.
"""
from dataclasses import asdict, replace
from fractions import Fraction
import hashlib
import json
from typing import Mapping

from research_lab.att1_lifecycle_profile import (
    ProfileViolation, admit_signal, _decimal_text, _sha_text,
)
from research_lab.att1_ets2s_lifecycle import (
    ExposurePlan, ExposureEvent, LifecycleViolation, initial_state, apply_event,
)
from research_lab.att1_ets2s_accounting import (
    AccountingPlan, AccountingViolation, Execution, EntryFinal, FundingSettlement, FundingCashSettlement,
    FundingSchedule, replay_accounting, _decimal as number,
)

AUTHORITY = {'money_authority': False, 'orders_allowed': False,
             'private_api_allowed': False, 'promotion_authority': False}
COMMON = {'schema_id', 'event_id', 'kind', 'exchange_ms', 'received_ms', 'source_sha256'}
FILL = {'execution_id', 'qty', 'price', 'fee_amount', 'fee_source_sha256', 'liquidity'}
FIELDS = {
    'ENTRY_ACK': set(), 'CANCEL_REQUEST': set(), 'UNKNOWN_PROTECTION': set(), 'CLOCK': set(),
    'ENTRY_FILL': FILL, 'ENTRY_FINAL': {'status'}, 'PROTECTION_ACK': {'qty', 'stop'},
    'PRICE': {'bid', 'ask'}, 'EXIT_ACK': {'exit_order_id'},
    'EXIT_FILL': FILL | {'exit_order_id'}, 'EXIT_FINAL': {'exit_order_id', 'status'},
    'FUNDING': {'settlement_id', 'settlement_ms', 'qty_at_settlement', 'mark_price', 'rate'},
    'FUNDING_CASH': {'settlement_id', 'settlement_ms', 'qty_at_settlement', 'cash_amount', 'currency'},
    'FUNDING_COVERAGE': {'start_ms', 'end_ms', 'settlement_ms', 'complete'},
    'RECOVERY_GAP': {'reason'},
}


class CoordinatorViolation(ValueError):
    """Reject an unprovable transition without publishing any derived state."""


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    except (TypeError, ValueError, RecursionError) as exc:
        raise CoordinatorViolation('noncanonical JSON') from exc


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def text(value, field):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise CoordinatorViolation(f'invalid {field}')
    return value


def integer(value, field):
    if type(value) is not int or value < 0:
        raise CoordinatorViolation(f'invalid {field}')
    return value


def _event(value):
    if not isinstance(value, Mapping):
        raise CoordinatorViolation('event must be mapping')
    kind = value.get('kind')
    if not isinstance(kind, str) or kind not in FIELDS or set(value) != COMMON | FIELDS[kind]:
        raise CoordinatorViolation('event fields/kind')
    if value['schema_id'] != 'att1_lifecycle_event_v1':
        raise CoordinatorViolation('event schema')
    text(value['event_id'], 'event_id')
    _sha_text(value['source_sha256'], 'source_sha256')
    ex = integer(value['exchange_ms'], 'exchange_ms')
    rx = integer(value['received_ms'], 'received_ms')
    if ex > rx:
        raise CoordinatorViolation('exchange after receive')
    raw = canonical(value)
    if len(raw) > 65536:
        raise CoordinatorViolation('event size limit')
    return json.loads(raw)


def json_value(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Mapping):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    return value


def _execution_identity(e):
    fields = {k: v for k, v in e.items() if k not in {'event_id', 'received_ms'}}
    for name in ('qty', 'price', 'fee_amount'):
        if fields[name] is not None:
            fields[name] = str(number(fields[name], name))
    return digest(fields)


def replay_lifecycle(profile, intent, events):
    """Return exact JSON state; original inputs are never mutated."""
    try:
        return _replay(profile, intent, events)
    except (ProfileViolation, LifecycleViolation, AccountingViolation) as exc:
        raise CoordinatorViolation(str(exc)) from exc


def _replay(profile, intent, events):
    if not isinstance(intent, Mapping) or set(intent) != {'signal','instrument','book_state','book','submit_ms'}:
        raise CoordinatorViolation('intent fields')
    if not isinstance(events, (tuple, list)) or len(events) > 8192:
        raise CoordinatorViolation('event count limit')
    admission = admit_signal(profile, intent['signal'], intent['instrument'], intent['book_state'],
                             book=intent['book'], submit_ms=intent['submit_ms'])
    if not admission['accepted']:
        if events:
            raise CoordinatorViolation('events for rejected admission')
        return {'schema_id':'att1_lifecycle_receipt_v1','admission':admission,'authority':dict(AUTHORITY)}
    p = admission['plan']
    broker_replay = p['profile_id'] == 'BROKER_REPLAY_ATT1_V1'
    exposure = initial_state(ExposurePlan(p['book'],'ATT1',p['symbol'],p['decision_id'],p['order_id'],
                                         p['profile_id'],p['qty_step'],p['requested_qty'],p['submit_ms']))
    account_plan = AccountingPlan(p['profile_id'],p['original_stop'],p['planned_risk_amount'],'USDT',p['signal_source_sha256'])
    ledger = []
    schedule = None
    original_stop = number(p['original_stop'],'stop',positive=True)
    nominal_entry = number(p['nominal_entry'],'entry',positive=True)
    step = number(p['qty_step'],'qty_step',positive=True)
    tick = number(p['price_tick'],'price_tick',positive=True)
    first_fill = deadline = None
    targets = []
    protection_stop = None
    unprotected_since = None
    entry_status = 'PENDING'
    pending_exit = None
    forced_reason = None
    tp1_goal = tp1_filled = Fraction(0)
    cancel_entry = cancel_exit = False
    incidents = set()
    accepted_ids, executions, settlements = {}, {}, {}
    last_rx = last_exchange = p['submit_ms']
    last_ask = None
    valuation_horizon = None
    entry_final_seen = False

    def held():
        return Fraction(exposure.held_qty)

    def expose(e, kind, qty=None):
        nonlocal exposure
        exposure = apply_event(exposure, ExposureEvent(e['event_id'],kind,p['order_id'],
            e['exchange_ms'],e['received_ms'],e.get('execution_id') if kind in {'ENTRY_FILL','EXIT_FILL'} else None,
            qty))

    def account():
        result = replay_accounting(account_plan, ledger, schedule,
            mark_price=_decimal_text(last_ask) if last_ask is not None else None,
            reconcile_delayed_funding=True)
        if (result.held_qty > 0 and valuation_horizon is not None
                and (schedule is None or schedule.end_ms < valuation_horizon)):
            result = replace(result, funding_coverage_complete=False, costs_complete=False,
                             net_realized=None, net_equity_change=None, closed_net_r=None,
                             issues=result.issues | {'FUNDING_COVERAGE_INCOMPLETE'})
        return result

    def request_exit(reason, e):
        nonlocal pending_exit, cancel_entry, cancel_exit
        if not exposure.entry_final:
            cancel_entry = True
        if pending_exit is not None:
            if reason in {'SL','TIME','INCIDENT'} and pending_exit['reason'] not in {'SL','TIME','INCIDENT'}:
                cancel_exit = True
            return
        quantity = min(held(), max(Fraction(0), tp1_goal-tp1_filled)) if reason == 'TP1' else held()
        if quantity <= 0:
            return
        oid = 'research-exit:' + digest({'decision':p['decision_id'],'trigger':e['event_id'],'reason':reason})
        pending_exit = {'exit_order_id':oid,'reason':reason,'qty':quantity,
                        'remaining_qty':quantity,'submit_ms':e['received_ms'],'acknowledged':False}

    for raw in events:
        e = _event(raw)
        kind, ex, rx = e['kind'], e['exchange_ms'], e['received_ms']
        fingerprint = digest(e)
        prior = accepted_ids.get(e['event_id'])
        if prior is not None:
            if prior != fingerprint:
                raise CoordinatorViolation('conflicting event_id')
            continue
        if rx < last_rx or rx < p['submit_ms']:
            raise CoordinatorViolation('decreasing receive clock')
        duplicate_execution = False
        if kind in {'ENTRY_FILL','EXIT_FILL'}:
            text(e['execution_id'],'execution_id')
            fp = _execution_identity(e)
            old = executions.get(e['execution_id'])
            if old is not None:
                if old != fp:
                    raise CoordinatorViolation('conflicting execution economics')
                duplicate_execution = True
            else:
                executions[e['execution_id']] = fp
        if duplicate_execution:
            accepted_ids[e['event_id']] = fingerprint
            last_rx = rx
            continue
        if kind not in {'FUNDING','FUNDING_CASH','FUNDING_COVERAGE','CLOCK','RECOVERY_GAP'}:
            if ex < last_exchange:
                raise CoordinatorViolation('decreasing exchange clock')
            last_exchange = ex
        if kind not in {'FUNDING','FUNDING_CASH','FUNDING_COVERAGE'} and ex < p['submit_ms']:
            raise CoordinatorViolation('event before submit')
        if unprotected_since is not None and held() > 0 and rx-unprotected_since > 2000:
            incidents.add('PROTECTION_ACK_TIMEOUT')
            forced_reason = 'INCIDENT'

        if kind in {'ENTRY_ACK','CANCEL_REQUEST'}:
            if exposure.entry_final:
                raise CoordinatorViolation('entry event after finality')
            expose(e,kind)
            if kind == 'ENTRY_ACK': entry_status = 'ACKNOWLEDGED'
            if kind == 'CANCEL_REQUEST': cancel_entry = True
        elif kind in {'ENTRY_FILL','EXIT_FILL'}:
            quantity = number(e['qty'],'qty',positive=True)
            price = number(e['price'],'price',positive=True)
            if quantity % step:
                raise CoordinatorViolation('fill quantity step')
            if kind == 'EXIT_FILL':
                if pending_exit is None or e['exit_order_id'] != pending_exit['exit_order_id']:
                    raise CoordinatorViolation('foreign exit execution')
                if ex < pending_exit['submit_ms'] or quantity > pending_exit['remaining_qty']:
                    raise CoordinatorViolation('exit execution precedes request or overfills it')
            expose(e,kind,_decimal_text(quantity))
            ledger.append(Execution(e['event_id'],e['execution_id'],'ENTRY' if kind=='ENTRY_FILL' else 'EXIT',
                _decimal_text(quantity),_decimal_text(price),e['fee_amount'],'USDT',e['fee_source_sha256'],
                e['liquidity'],ex,rx,e['source_sha256']))
            if kind == 'ENTRY_FILL':
                if broker_replay:
                    a = account()
                    aggregate_risk = (a.aggregate_entry_qty * abs(
                        a.aggregate_entry_notional / a.aggregate_entry_qty - original_stop
                    ) if a.aggregate_entry_qty else Fraction(0))
                    if aggregate_risk > number(profile['execution']['risk_amount'],'risk_amount',positive=True):
                        incidents.add('ABSOLUTE_RISK_CAP_EXCEEDED')
                    if a.aggregate_entry_notional > number(profile['execution']['max_notional'],'max_notional',positive=True):
                        incidents.add('NOTIONAL_CAP_EXCEEDED')
                if first_fill is None:
                    first_fill = ex
                    deadline = ex + 336*3600000
                if exposure.unprotected_qty > 0 and unprotected_since is None:
                    unprotected_since = rx
                entry_status = entry_status if exposure.entry_final else 'PARTIAL' if exposure.pending_entry_qty > 0 else 'FILLED_AWAITING_FINAL'
                if ex > p['submit_ms']+profile['execution']['entry_ioc_lifetime_ms']:
                    incidents.add('ENTRY_IOC_LATE_FILL')
                if price >= original_stop or (original_stop-price)/(original_stop-nominal_entry) > Fraction('1.1'):
                    incidents.add('ENTRY_RISK_VIOLATION')
                if exposure.incidents or incidents:
                    forced_reason = 'INCIDENT'
            else:
                pending_exit['remaining_qty'] -= quantity
                if pending_exit['reason']=='TP1': tp1_filled += quantity
                if held()==0: unprotected_since = None
        elif kind == 'ENTRY_FINAL':
            status = e['status']
            if status not in {'FILLED','CANCELLED','REJECTED','EXPIRED'} or entry_final_seen:
                raise CoordinatorViolation('invalid/multiple entry final')
            if status=='FILLED' and exposure.pending_entry_qty != 0:
                raise CoordinatorViolation('filled status with pending entry quantity')
            if status=='REJECTED' and exposure.entry_filled_qty != 0:
                raise CoordinatorViolation('rejected entry has fills')
            if status=='EXPIRED' and ex < p['submit_ms']+profile['execution']['entry_ioc_lifetime_ms']:
                raise CoordinatorViolation('entry expiry before IOC deadline')
            expose(e,'ENTRY_FINAL')
            ledger.append(EntryFinal(e['event_id'],ex,rx,e['source_sha256']))
            entry_final_seen, entry_status, cancel_entry = True, status, False
            a = account()
            if a.aggregate_entry_qty > 0:
                vwap = a.aggregate_entry_notional/a.aggregate_entry_qty
                risk = original_stop-vwap
                targets = [((vwap-rr*risk)//tick)*tick for rr in (Fraction('1.2'),Fraction('2.5'))]
                if risk <= 0 or not 0 < targets[1] < targets[0] < vwap:
                    incidents.add('FINAL_GEOMETRY_INVALID'); forced_reason='INCIDENT'
                    targets=[]
                tp1_goal = ((a.aggregate_entry_qty*Fraction('.55'))//step)*step
        elif kind == 'PROTECTION_ACK':
            stop = number(e['stop'],'stop',positive=True)
            if stop != original_stop:
                raise CoordinatorViolation('frozen stop changed; BE/trailing disabled')
            expose(e,kind,_decimal_text(number(e['qty'],'qty',positive=True)))
            protection_stop=stop
            if exposure.unprotected_qty == 0: unprotected_since=None
        elif kind == 'UNKNOWN_PROTECTION':
            expose(e,kind)
            protection_stop=None
            incidents.add('UNKNOWN_PROTECTION'); forced_reason='INCIDENT'
            if held()>0 and unprotected_since is None: unprotected_since=rx
        elif kind in {'PRICE','CLOCK','RECOVERY_GAP'}:
            valuation_horizon = rx
            if kind=='RECOVERY_GAP':
                text(e['reason'],'reason'); incidents.add('RECOVERY_GAP'); forced_reason='INCIDENT'
            if kind=='PRICE':
                bid, ask = number(e['bid'],'bid',positive=True), number(e['ask'],'ask',positive=True)
                if bid>ask or rx-ex > profile['execution']['market_observation_max_age_ms']:
                    raise CoordinatorViolation('crossed/stale executable observation')
                last_ask=ask
                if held()>0 and exposure.unprotected_qty>0:
                    incidents.add('UNPROTECTED_MARKET'); forced_reason='INCIDENT'
                if held()>0 and ask>=original_stop and forced_reason!='INCIDENT':
                    forced_reason='SL'
            if not exposure.entry_final and rx>=p['submit_ms']+profile['execution']['entry_ioc_lifetime_ms']:
                cancel_entry=True
            if deadline is not None and rx>=deadline and forced_reason not in {'SL','INCIDENT'}:
                forced_reason='TIME'
            if held()>0:
                if forced_reason: request_exit(forced_reason,e)
                elif kind=='PRICE' and targets:
                    if tp1_filled < tp1_goal and last_ask<=targets[0]: request_exit('TP1',e)
                    elif tp1_filled>=tp1_goal and last_ask<=targets[1]: request_exit('TP2',e)
        elif kind in {'EXIT_ACK','EXIT_FINAL'}:
            if pending_exit is None or e['exit_order_id']!=pending_exit['exit_order_id'] or ex<pending_exit['submit_ms']:
                raise CoordinatorViolation('foreign/early exit order receipt')
            if kind=='EXIT_ACK': pending_exit['acknowledged']=True
            else:
                if e['status'] not in {'FILLED','CANCELLED','REJECTED'}:
                    raise CoordinatorViolation('exit status')
                if e['status']=='FILLED' and pending_exit['remaining_qty']!=0:
                    raise CoordinatorViolation('exit FILLED before remaining quantity zero')
                if e['status']=='REJECTED' and pending_exit['remaining_qty']!=pending_exit['qty']:
                    raise CoordinatorViolation('rejected exit has fills')
                pending_exit=None; cancel_exit=False
        elif kind == 'FUNDING':
            if broker_replay:
                raise CoordinatorViolation('synthetic funding is not allowed for broker replay')
            text(e['settlement_id'],'settlement_id')
            economic = {k:v for k,v in e.items() if k not in {'event_id','received_ms'}}
            old=settlements.get(e['settlement_id'])
            if old is not None:
                if old!=digest(economic): raise CoordinatorViolation('conflicting funding settlement')
            else:
                settlements[e['settlement_id']]=digest(economic)
                ledger.append(FundingSettlement(e['event_id'],e['settlement_id'],e['settlement_ms'],ex,rx,
                    e['qty_at_settlement'],e['mark_price'],e['rate'],e['source_sha256']))
        elif kind == 'FUNDING_CASH':
            if not broker_replay:
                raise CoordinatorViolation('broker funding cash is not allowed for synthetic profile')
            text(e['settlement_id'],'settlement_id')
            economic = {k:v for k,v in e.items() if k not in {'event_id','received_ms'}}
            old=settlements.get(e['settlement_id'])
            if old is not None:
                if old!=digest(economic): raise CoordinatorViolation('conflicting funding settlement')
            else:
                settlements[e['settlement_id']]=digest(economic)
                ledger.append(FundingCashSettlement(e['event_id'],e['settlement_id'],e['settlement_ms'],ex,rx,
                    e['qty_at_settlement'],e['cash_amount'],e['currency'],e['source_sha256']))
        elif kind == 'FUNDING_COVERAGE':
            start, end=integer(e['start_ms'],'coverage start'),integer(e['end_ms'],'coverage end')
            if end>rx or not isinstance(e['settlement_ms'],list) or type(e['complete']) is not bool:
                raise CoordinatorViolation('coverage times/type')
            times=tuple(integer(t,'settlement timestamp') for t in e['settlement_ms'])
            if times!=tuple(sorted(set(times))) or any(t<start or t>end for t in times):
                raise CoordinatorViolation('coverage settlement order/window')
            if schedule is not None and (start>schedule.start_ms or end<schedule.end_ms or not set(schedule.settlement_ms)<=set(times)):
                raise CoordinatorViolation('coverage history cannot shrink')
            schedule=FundingSchedule(times,start,end,e['source_sha256'],e['complete'])
        incidents.update(exposure.incidents)
        if incidents and held()>0:
            forced_reason='INCIDENT'
            request_exit(forced_reason,e)
        accounting = account()
        if accounting.held_qty != held():
            raise CoordinatorViolation('L2/L3 quantity mismatch')
        accepted_ids[e['event_id']]=fingerprint
        last_rx=rx

    accounting=account()
    clean = (entry_final_seen and exposure.entry_filled_qty>0 and held()==0 and pending_exit is None
             and not incidents and not accounting.issues and accounting.closed_net_r is not None)
    nonfill = entry_final_seen and exposure.entry_filled_qty==0 and held()==0 and pending_exit is None and not incidents
    return json_value({
        'schema_id':'att1_lifecycle_receipt_v1','admission':admission,'plan':p,'authority':dict(AUTHORITY),
        'execution_evidence':'BROKER_REPLAY_INPUTS_NOT_AUTHENTICATED' if broker_replay else 'SIMULATED_NOT_BROKER_FILLS',
        'actual_account_costs_verified':False,
        'entry_status':entry_status,'held_qty':held(),'pending_entry_qty':Fraction(exposure.pending_entry_qty),
        'protected_qty':Fraction(exposure.protected_qty),'protection_stop':protection_stop,
        'first_fill_ms':first_fill,'time_deadline_ms':deadline,'targets':targets,'pending_exit':pending_exit,
        'intents':{'protect_qty':held() if held()>0 and exposure.unprotected_qty>0 else Fraction(0),
                   'cancel_entry':cancel_entry,'cancel_exit':cancel_exit},
        'accounting':asdict(accounting),'incidents':incidents,'exposure_terminal':exposure.terminal_eligible,
        'terminal_nonfill':nonfill,'lifecycle_terminal':bool(clean),
        'final_net_r':accounting.closed_net_r if clean else None,
    })
