"""Durable, no-send ten-leg controller for EXECUTION_MICRO_LIVE preparation.

Consumes normalized evidence and proposes actions; no credential loader, HTTP,
service or broker writer exists here. Event hashes prove consistency, never
broker authentication. Both the preserved guarantee policy and the separately
owner-approved V2 exit-threshold policy remain replayable. Neither grants GO.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from decimal import Decimal, InvalidOperation

from bot.kity_m3_orders_off import digest, _levels, _vwap
from research_lab.kity_execution_micro_v1 import numeric, common_source_clock

BASKET = (('BTWUSDT', 'Buy'), ('XAUUSDT', 'Buy'), ('LTCUSDT', 'Buy'),
          ('VVVUSDT', 'Buy'), ('BNBUSDT', 'Buy'), ('XAUTUSDT', 'Sell'),
          ('XPLUSDT', 'Sell'), ('XAGUSDT', 'Sell'), ('GRASSUSDT', 'Sell'), ('SPCXUSDT', 'Sell'))
_SHA = re.compile(r'[0-9a-f]{64}\Z')
TERMINAL = {'Filled', 'Cancelled', 'Rejected', 'PartiallyFilledCanceled', 'Deactivated'}
# Official create-order validation/auth/funds refusals, not timeout/server/duplicate codes.
DEFINITE_CREATE_REJECT={10001,10002,10003,10004,10005,10007,10008,10009,10010,
    10024,10027,10028,10029,100028,110003,110004,110006,110007,110009,110012,
    110017,110020,110021,110023,110029,110032,30208,30209,30228}


def text(value):
    return format(value, 'f')


def signed(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('INVALID_CASH_NUMBER')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('INVALID_CASH_NUMBER') from exc
    if not number.is_finite():
        raise ValueError('INVALID_CASH_NUMBER')
    return number


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def integer(value):
    if type(value) is not int or value <= 0:
        raise ValueError('INVALID_EVENT_CLOCK')
    return value


def _owner_bounds(bounds):
    b = copy.deepcopy(bounds)
    v3 = b.get('schema') == 'kity_execution_micro_owner_bounds_v3'
    expected = {'max_gross_usdt': Decimal('215' if v3 else '210'), 'max_all_in_loss_usdt': Decimal('15'),
                'max_rounding_shortfall_fraction': Decimal('.203')}
    if any(numeric(b.get(k)) != v for k, v in expected.items()):
        raise ValueError('OWNER_BOUND_CONFLICT')
    legacy = (b.get('schema') == 'kity_execution_micro_owner_bounds_v1'
              and b.get('hard_final_loss_cap_required') is True)
    amended = (b.get('schema') == 'kity_execution_micro_owner_bounds_v2'
        and b.get('hard_final_loss_cap_required') is False
        and b.get('loss_policy') == 'IMMEDIATE_ALL_IN_EXIT_THRESHOLD'
        and b.get('allow_execution_overshoot') is True
        and b.get('source_reply_id') == 'call_6b8bf99c313243c1b85f5c3504a5c292'
        and b.get('supersedes_policy_sha256') == '53fce5006627658facd3d9521c1aad34f210423d09609684001f37adb157331a')
    integrated = (v3 and b.get('hard_final_loss_cap_required') is False
        and b.get('loss_policy') == 'IMMEDIATE_ALL_IN_EXIT_THRESHOLD'
        and b.get('allow_execution_overshoot') is True
        and b.get('source_reply_id') == 'call_6b8bf99c313243c1b85f5c3504a5c292'
        and b.get('source_owner_message') == '2026-10-15 GO KITY MICRO-LIVE EXECUTION INTEGRATION — ORDERS OFF'
        and b.get('supersedes_policy_sha256') == '49bf03e4733711d3c97c684ec2436fff988817e8fb6d9cef351b71708a882bb3')
    if (not (legacy or amended or integrated)
            or b.get('duration_ms') != 1800000 or type(b.get('duration_ms')) is not int
            or b.get('one_experiment_only') is not True or b.get('purpose') != 'EXECUTION_MICRO_LIVE'
            or b.get('owner_money_go') is not False
            or any(b.get(k) is not False for k in ('allow_scaling', 'allow_averaging', 'allow_reentry',
                                                'research_evidence_eligible', 'counts_toward_C1_C2_C3'))):
        raise ValueError('OWNER_BOUND_CONFLICT')
    for key, value in expected.items():
        b[key] = text(value)
    return b


def prepare_micro_plan(dossier, bounds):
    b = _owner_bounds(bounds)
    expected = {key: Decimal(b[key]) for key in ('max_gross_usdt', 'max_all_in_loss_usdt', 'max_rounding_shortfall_fraction')}
    candidates = [p for p in dossier['profiles'] if p['profile'] == 'VENUE_FLOOR_DIAGNOSTIC']
    if len(candidates) != 1:
        raise ValueError('EXACT_TEN_PROFILE_REQUIRED')
    source = candidates[0]
    if [(l['symbol'], l['side']) for l in source['legs']] != list(BASKET):
        raise ValueError('EXACT_TEN_BASKET_REQUIRED')
    reasons, legs = [], []
    target = numeric(source['common_reference_target'])
    for leg in source['legs']:
        deviation = (target - numeric(leg['entry_reference_notional'])) / target
        if (deviation < 0 or deviation != numeric(leg['rounding_shortfall_fraction'], zero=True)
                or deviation > expected['max_rounding_shortfall_fraction']):
            raise ValueError('ROUNDING_LIMIT_EXCEEDED')
        quantity = numeric(leg['quantity'])
        req = copy.deepcopy(leg['draft_entry'])
        if (req.get('symbol') != leg['symbol'] or req.get('side') != leg['side']
                or req.get('category') != 'linear' or req.get('orderType') != 'Limit'
                or req.get('timeInForce') != 'IOC' or req.get('positionIdx') != 0
                or type(req.get('positionIdx')) is not int or req.get('reduceOnly') is not False
                or numeric(req.get('qty')) != quantity):
            raise ValueError('ENTRY_TEMPLATE_CONFLICT')
        numeric(req['price'])
        legs.append(dict(symbol=leg['symbol'], side=leg['side'], quantity=text(quantity),
            rounding_shortfall_fraction=leg['rounding_shortfall_fraction'], request=req))
    gross = numeric(source['observed_depth_gross'])
    limit_gross = sum((numeric(l['request']['qty']) * numeric(l['request']['price']) for l in legs), Decimal(0))
    if max(gross, limit_gross) > expected['max_gross_usdt']:
        reasons.append('GROSS_CAP_EXCEEDED')
    plan = dict(schema='kity_execution_micro_plan_v1', purpose='EXECUTION_MICRO_LIVE',
                bounds=b, legs=legs, source_dossier_sha256=digest(dossier),
                captured_source_sha256=dossier['private_capture_sha256'],
                c2_reconstruction_receipt_sha256=dossier['c2_reconstruction_receipt_sha256'],
                reference_source_ms=integer(dossier['observed_end_ms']),
                reference_gross_usdt=text(gross), planned_limit_gross_usdt=text(limit_gross),
                blocked_reasons=reasons, orders_allowed=False, research_evidence_eligible=False,
                counts_toward_C1_C2_C3=False, real_transport_bound=False)
    namespace = digest(plan)[:12]
    for index, leg in enumerate(plan['legs']):
        leg['request']['orderLinkId'] = f'KXM1-{namespace}-E{index:02d}'
        leg['exit_prefix'] = f'KXM1-{namespace}-X{index:02d}'
    plan['plan_id'] = digest(plan)
    return plan


def assess_micro_readiness(plan, account):
    validate_plan(plan)
    reasons = list(plan['blocked_reasons'])
    if plan['bounds']['hard_final_loss_cap_required']:
        reasons.append('HARD_FINAL_LOSS_CAP_NOT_ENFORCEABLE_ON_PERPETUALS')
    reasons += ['REAL_TRANSPORT_AND_EXCLUSIVE_WRITER_BINDING_REQUIRED',
                'FRESH_ACCOUNT_AND_COMMON_2S_BASKET_REQUIRED', 'SEPARATE_EXACT_OWNER_GO_REQUIRED']
    if account.get('marginMode') == 'REGULAR_MARGIN' and plan['bounds']['hard_final_loss_cap_required']:
        reasons.append('CURRENT_ACCOUNT_USES_SHARED_CROSS_COLLATERAL')
    result = dict(status='BLOCKED_EXECUTION', reasons=reasons, orders_allowed=False,
                requested_hard_loss_cap_usdt=plan['bounds']['max_all_in_loss_usdt'],
                guaranteed_final_loss_cap=False, local_controller_available=True,
                research_evidence_eligible=False)
    if not plan['bounds']['hard_final_loss_cap_required']:
        result.pop('requested_hard_loss_cap_usdt')
        result.update(loss_policy='IMMEDIATE_ALL_IN_EXIT_THRESHOLD', loss_threshold_usdt='15',
                      execution_overshoot_accepted=True,
                      shared_cross_collateral_observed=account.get('marginMode') == 'REGULAR_MARGIN')
    return result


def validate_plan(plan):
    _owner_bounds(plan['bounds'])
    body = {k: v for k, v in plan.items() if k != 'plan_id'}
    if (plan.get('plan_id') != digest(body) or plan.get('purpose') != 'EXECUTION_MICRO_LIVE'
            or plan.get('orders_allowed') is not False or plan.get('real_transport_bound') is not False
            or plan.get('research_evidence_eligible') is not False or plan.get('counts_toward_C1_C2_C3') is not False
            or [(l['symbol'], l['side']) for l in plan['legs']] != list(BASKET)):
        raise ValueError('PLAN_PIN_CONFLICT')
    gross=Decimal(0)
    for leg in plan['legs']:
        req=leg['request'];quantity=numeric(leg['quantity'])
        if (req.get('symbol')!=leg['symbol'] or req.get('side')!=leg['side']
            or req.get('category')!='linear' or req.get('orderType')!='Limit' or req.get('timeInForce')!='IOC'
            or type(req.get('positionIdx')) is not int or req['positionIdx']!=0 or req.get('reduceOnly') is not False
            or numeric(req.get('qty'))!=quantity
            or numeric(leg['rounding_shortfall_fraction'],zero=True)>Decimal(plan['bounds']['max_rounding_shortfall_fraction'])):
            raise ValueError('PLAN_BOUND_OR_REQUEST_CONFLICT')
        gross+=quantity*numeric(req.get('price'))
        if 'stopLoss' in req:
            stop=numeric(req['stopLoss']);price=numeric(req['price'])
            if (req.get('tpslMode')!='Full' or req.get('slOrderType')!='Market' or req.get('slTriggerBy')!='LastPrice'
                or (stop>=price if leg['side']=='Buy' else stop<=price)):
                raise ValueError('PLAN_BOUND_OR_NATIVE_GUARD_CONFLICT')
    exceeded=max(gross,numeric(plan['reference_gross_usdt']))>Decimal(plan['bounds']['max_gross_usdt'])
    if gross!=numeric(plan['planned_limit_gross_usdt']) or exceeded!=('GROSS_CAP_EXCEEDED' in plan['blocked_reasons']):
        raise ValueError('PLAN_BOUND_OR_GROSS_CONFLICT')


def initial(plan):
    state = dict(schema='kity_micro_lifecycle_replay_v1', phase='PREPARED', plan_id=plan['plan_id'],
        held={s: '0' for s, _ in BASKET}, entries={}, exits={}, fills={}, funding={},
        trade_cash_usdt='0', fees_usdt='0', funding_cash_usdt='0', fee_unknown_execution_ids=[],
        first_send_ms=None, deadline_ms=None, entry_blocked=False, ownership_conflict=False,
        broker_flat_proven=False, last_fill_ms=None, last_snapshot_ms=None,
        orders_allowed=False, research_evidence_eligible=False, counts_toward_C1_C2_C3=False,
        terminal_net_usdt=None, all_ten_complete=False)
    if not plan['bounds']['hard_final_loss_cap_required']:
        state.update(loss_policy='IMMEDIATE_ALL_IN_EXIT_THRESHOLD', loss_threshold_usdt='15',
                     execution_overshoot_accepted=True, guaranteed_final_loss_cap=False,
                     leg_rounding_shortfalls={l['symbol']: l['rounding_shortfall_fraction'] for l in plan['legs']})
    return state


def _money_add(state, key, amount):
    state[key] = text(signed(state[key]) + amount)


def _entry_complete(order):
    return order['terminal'] and Decimal(order['terminal_quantity']) == Decimal(order['filled'])


def _accounted(order):
    return _entry_complete(order)


def _order_for_fill(state, e, exit):
    order = state['exits'].get(e['order_link_id']) if exit else state['entries'].get(e['symbol'])
    if (not order or order['symbol'] != e['symbol'] or order['link'] != e['order_link_id']
            or (order['order_id'] is not None and order['order_id'] != e['order_id'])):
        raise ValueError('EXECUTION_OWNERSHIP_CONFLICT')
    if not isinstance(e['order_id'], str) or not e['order_id']:
        raise ValueError('BROKER_ORDER_ID_REQUIRED')
    return order


def apply_event(plan, state, e):
    s = copy.deepcopy(state)
    at = integer(e.get('at_ms'))
    if not isinstance(e.get('event_id'), str) or not e['event_id'] or not _SHA.fullmatch(e.get('source_sha256', '')):
        raise ValueError('EVENT_PROVENANCE_REQUIRED')
    kind, symbol = e['kind'], e.get('symbol')
    legs = {l['symbol']: l for l in plan['legs']}
    if symbol is not None and symbol not in legs:
        raise ValueError('UNKNOWN_OWNED_SYMBOL')
    if s['phase'] == 'TERMINAL':
        if kind not in ('ENTRY_FILL', 'EXIT_FILL') or e.get('execution_id') not in s['fills']:
            raise ValueError('ENTRY_BLOCKED_TERMINAL' if kind == 'ENTRY_INTENT' else 'TERMINAL_IMMUTABLE')
    if kind == 'ENTRY_INTENT':
        if (plan['blocked_reasons'] or s['entry_blocked'] or s['ownership_conflict'] or symbol in s['entries']
                or (s['deadline_ms'] is not None and at >= s['deadline_ms'])):
            raise ValueError('ENTRY_BLOCKED')
        if any(not _entry_complete(o) or Decimal(o['protected']) != Decimal(o['filled']) for o in s['entries'].values()):
            raise ValueError('ENTRY_RECONCILIATION_REQUIRED')
        s['entries'][symbol] = dict(symbol=symbol, link=legs[symbol]['request']['orderLinkId'], order_id=None,
            filled='0', terminal=False, terminal_quantity=None, protected='0', stop_id=None)
        if s['first_send_ms'] is None:
            s['first_send_ms'], s['deadline_ms'] = at, at + plan['bounds']['duration_ms']
        s['phase'] = 'ENTERING'
    elif kind == 'EXIT_INTENT':
        entry = s['entries'].get(symbol)
        if not entry or not _entry_complete(entry):
            raise ValueError('ENTRY_RECONCILIATION_REQUIRED')
        quantity = numeric(e['quantity'])
        if quantity > Decimal(s['held'][symbol]) or s['ownership_conflict']:
            raise ValueError('EXIT_QUANTITY_OR_OWNERSHIP_CONFLICT')
        prior = [v for v in s['exits'].values() if v['symbol'] == symbol]
        if any(not _accounted(o) and not o.get('is_native_protection') for o in prior):
            raise ValueError('EXIT_RECONCILIATION_REQUIRED')
        link = legs[symbol]['exit_prefix'] + f'-{len(prior)}'
        s['exits'][link] = dict(symbol=symbol, link=link, order_id=None, quantity=text(quantity),
            filled='0', terminal=False, terminal_quantity=None)
        s['entry_blocked'], s['phase'] = True, 'UNWINDING'
    elif kind in ('ENTRY_ACK', 'EXIT_ACK', 'DISPATCH_UNKNOWN'):
        exit = e['order_link_id'] in s['exits']
        order = s['exits'].get(e['order_link_id']) if exit else s['entries'].get(symbol)
        if not order or order['link'] != e['order_link_id'] or order['symbol'] != symbol:
            raise ValueError('ORDER_OWNERSHIP_CONFLICT')
        if kind == 'DISPATCH_UNKNOWN':
            s['entry_blocked'], s['phase'] = True, 'UNWINDING'
        elif kind == ('EXIT_ACK' if exit else 'ENTRY_ACK'):
            if order['order_id'] not in (None, e['order_id']):
                raise ValueError('ORDER_ID_CONFLICT')
            order['order_id'] = e['order_id']
        else:
            raise ValueError('ORDER_ROLE_CONFLICT')
    elif kind == 'DISPATCH_REJECTED':
        if type(e.get('ret_code')) is not int or e['ret_code'] not in DEFINITE_CREATE_REJECT:
            raise ValueError('DEFINITE_REJECTION_SOURCE_REQUIRED')
        order=s['exits'].get(e['order_link_id']) or s['entries'].get(symbol)
        if not order or order['link']!=e['order_link_id'] or order['order_id'] is not None or Decimal(order['filled'])!=0:
            raise ValueError('DEFINITE_REJECTION_CONFLICT')
        order.update(terminal=True,terminal_quantity='0',definite_rejection=e['ret_code'])
        s['entry_blocked'],s['phase']=True,'UNWINDING'
    elif kind in ('ENTRY_FILL', 'EXIT_FILL'):
        exit = kind == 'EXIT_FILL'
        order = _order_for_fill(s, e, exit)
        quantity, price = numeric(e['quantity']), numeric(e['price'])
        fee = None if e.get('fee_usdt') is None else signed(e['fee_usdt'])
        execution = e['execution_id']
        if not isinstance(execution, str) or not execution:
            raise ValueError('EXECUTION_ID_REQUIRED')
        normalized = dict(kind=kind, symbol=symbol, link=e['order_link_id'], order_id=e['order_id'],
                          quantity=text(quantity), price=text(price), fee_usdt=None if fee is None else text(fee),
                          source_execution_ms=e.get('source_execution_ms'))
        if execution in s['fills']:
            old = s['fills'][execution]
            if {k:v for k,v in old.items() if k != 'fee_usdt'} != {k:v for k,v in normalized.items() if k != 'fee_usdt'}:
                raise ValueError('EXECUTION_CONFLICT')
            if old['fee_usdt'] is None and fee is not None:
                old['fee_usdt'] = text(fee); _money_add(s, 'fees_usdt', fee)
                s['fee_unknown_execution_ids'].remove(execution)
            elif fee is not None and signed(old['fee_usdt']) != fee:
                raise ValueError('EXECUTION_FEE_CONFLICT')
            return s
        if at < s['first_send_ms']:
            raise ValueError('EXECUTION_BEFORE_INTENT')
        held = Decimal(s['held'][symbol])
        maximum = Decimal(order['quantity']) if exit else Decimal(legs[symbol]['quantity'])
        filled = Decimal(order['filled']) + quantity
        if filled > maximum or (order['terminal'] and filled > Decimal(order['terminal_quantity'])):
            raise ValueError('EXECUTION_EXCEEDS_ORDER')
        if exit and quantity > held:
            raise ValueError('EXIT_EXCEEDS_HELD')
        order['order_id'], order['filled'] = e['order_id'], text(filled)
        s['held'][symbol] = text(held - quantity if exit else held + quantity)
        direction = Decimal(1) if legs[symbol]['side'] == 'Buy' else Decimal(-1)
        _money_add(s, 'trade_cash_usdt', direction * quantity * price * (1 if exit else -1))
        if fee is None:
            s['fee_unknown_execution_ids'].append(execution)
        else:
            _money_add(s, 'fees_usdt', fee)
        s['fills'][execution] = normalized
        s['last_fill_ms'] = max(at, s['last_fill_ms'] or at)
        s['broker_flat_proven'] = False
        if exit and order.get('is_native_protection'):
            s['entry_blocked'],s['phase']=True,'UNWINDING'
        gross = sum((Decimal(v['quantity']) * Decimal(v['price']) for v in s['fills'].values() if v['kind'] == 'ENTRY_FILL'), Decimal(0))
        if gross > Decimal(plan['bounds']['max_gross_usdt']):
            s['entry_blocked'], s['phase'] = True, 'UNWINDING'
    elif kind in ('ENTRY_TERMINAL', 'EXIT_TERMINAL'):
        exit = kind == 'EXIT_TERMINAL'
        order = _order_for_fill(s, e, exit)
        quantity = numeric(e['filled_quantity'], zero=True)
        expected = Decimal(order['quantity']) if exit else Decimal(legs[symbol]['quantity'])
        if (e['status'] not in TERMINAL or quantity < Decimal(order['filled']) or quantity > expected
                or (e['status'] == 'Filled' and quantity != expected)
                or (e['status'] == 'Rejected' and quantity != 0)):
            raise ValueError('ORDER_TERMINAL_CONFLICT')
        if order['terminal'] and Decimal(order['terminal_quantity']) != quantity:
            raise ValueError('ORDER_TERMINAL_CONFLICT')
        order.update(order_id=e['order_id'], terminal=True, terminal_quantity=text(quantity))
        if not exit and quantity != expected:
            s['entry_blocked'], s['phase'] = True, 'UNWINDING'
        if exit and order.get('is_native_protection') and Decimal(s['held'][symbol])>0:
            s['entry_blocked'],s['phase']=True,'UNWINDING'
    elif kind == 'NATIVE_PROTECTION_RESIZE':
        order=s['exits'].get(e['order_link_id']);q=numeric(e['quantity'])
        if (not order or not order.get('is_native_protection') or order['order_id']!=e['order_id']
            or order['symbol']!=symbol or q>Decimal(order['quantity']) or q<Decimal(order['filled'])):
            raise ValueError('NATIVE_RESIZE_IDENTITY_CONFLICT')
        order['quantity']=text(q)
    elif kind == 'NATIVE_PROTECTION_BIND':
        entry=s['entries'].get(symbol);req=legs[symbol]['request'];quantity=numeric(e['quantity'])
        if (not entry or not _entry_complete(entry) or quantity!=Decimal(s['held'][symbol])
            or req.get('tpslMode')!='Full' or req.get('slOrderType')!='Market'
            or req.get('slTriggerBy')!='LastPrice' or numeric(e['trigger_price'])!=numeric(req.get('stopLoss'))
            or e.get('side')!=('Sell' if legs[symbol]['side']=='Buy' else 'Buy')
            or e.get('reduce_only') is not True or type(e.get('position_idx')) is not int or e['position_idx']!=0
            or not isinstance(e.get('order_id'),str) or not e['order_id'] or e['order_id']==entry['order_id']):
            raise ValueError('NATIVE_PROTECTION_IDENTITY_CONFLICT')
        link=legs[symbol]['exit_prefix']+'-SL'
        if link in s['exits']:
            old=s['exits'][link]
            if old['order_id']!=e['order_id'] or Decimal(old['quantity'])!=quantity:
                raise ValueError('NATIVE_PROTECTION_IDENTITY_CONFLICT')
        else:
            s['exits'][link]=dict(symbol=symbol,link=link,order_id=e['order_id'],quantity=text(quantity),
                filled='0',terminal=False,terminal_quantity=None,is_native_protection=True,cancel_sent=False)
        entry['protected'],entry['stop_id']=text(quantity),e['order_id']
    elif kind == 'NATIVE_CANCEL_INTENT':
        order=s['exits'].get(e.get('order_link_id'))
        if not order or not order.get('is_native_protection') or order['symbol']!=symbol or order['cancel_sent']:
            raise ValueError('NATIVE_PROTECTION_CANCEL_CONFLICT')
        order['cancel_sent']=True
    elif kind == 'PROTECTION_READBACK':
        order = s['entries'].get(symbol)
        quantity = numeric(e['quantity'])
        if (not order or quantity != Decimal(s['held'][symbol]) or not e['stop_id']
                or e['side'] != ('Sell' if legs[symbol]['side'] == 'Buy' else 'Buy')
                or order['stop_id'] not in (None, e['stop_id'])):
            raise ValueError('PROTECTION_OWNERSHIP_CONFLICT')
        order['protected'], order['stop_id'] = text(quantity), e['stop_id']
    elif kind == 'FUNDING_CASH':
        if not isinstance(e['settlement_id'], str) or not e['settlement_id']:
            raise ValueError('FUNDING_ID_REQUIRED')
        key = canonical([symbol, e['settlement_id']])
        cash = signed(e['cash_usdt'])
        row = dict(symbol=symbol, cash_usdt=text(cash), settlement_ms=integer(e['settlement_ms']))
        if symbol not in s['entries'] or Decimal(s['entries'][symbol]['filled']) <= 0:
            raise ValueError('FUNDING_OWNERSHIP_REQUIRED')
        if key in s['funding']:
            if s['funding'][key] != row:
                raise ValueError('FUNDING_CONFLICT')
        else:
            s['funding'][key] = row; _money_add(s, 'funding_cash_usdt', cash)
    elif kind == 'RISK_OBSERVATION':
        value = current_valuation(s, e['books'], e['exit_fee_rates'],
                                  funding_reserve_usdt=e['funding_reserve_usdt'], now_ms=at)
        s['last_risk_observation'] = dict(value, observed_ms=at, source_sha256=e['source_sha256'])
        if value['action'] != 'MONITOR':
            s['entry_blocked'], s['phase'] = True, 'UNWINDING'
    elif kind == 'RISK_SOURCE_UNKNOWN':
        s['last_risk_observation'] = dict(net_usdt=None, action='UNWIND_DATA_UNKNOWN',
            observed_ms=at, reason=e['reason'], orders_allowed=False, source_sha256=e['source_sha256'])
        s['entry_blocked'], s['phase'] = True, 'UNWINDING'
    elif kind == 'CLOCK':
        if s['deadline_ms'] is not None and at >= s['deadline_ms']:
            s['entry_blocked'], s['phase'] = True, 'UNWINDING'
    elif kind == 'UNWIND':
        if not isinstance(e.get('reason'), str) or not e['reason']:
            raise ValueError('UNWIND_REASON_REQUIRED')
        s['entry_blocked'], s['phase'] = True, 'UNWINDING'
    elif kind == 'BROKER_SNAPSHOT':
        if set(e['positions']) != set(legs):
            raise ValueError('COMPLETE_SYMBOL_SNAPSHOT_REQUIRED')
        expected = {symbol: Decimal(s['held'][symbol]) * (1 if side == 'Buy' else -1) for symbol, side in BASKET}
        match = all(signed(e['positions'][symbol]) == qty for symbol, qty in expected.items())
        known = {v['link'] for v in s['entries'].values()} | set(s['exits'])
        unknown = bool(set(e['open_order_links']) - known)
        s['ownership_conflict'] = not match or unknown
        if s['ownership_conflict']:
            s['entry_blocked'] = True
        s['broker_flat_proven'] = match and not unknown and not any(expected.values()) and not e['open_order_links']
        s['last_snapshot_ms'] = at
    elif kind == 'FINALITY_NO_SEND':
        if (not s['broker_flat_proven'] or not s['entry_blocked'] or s['entries'] or s['exits']
            or s['fills'] or s['first_send_ms'] is not None):
            raise ValueError('NO_SEND_FINALITY_NOT_PROVEN')
        s.update(phase='TERMINAL',terminal_net_usdt='0',execution_verdict='NO_SEND_NOT_LIFECYCLE_PASS')
    elif kind == 'FINALITY_NO_EXECUTIONS':
        if (not s['broker_flat_proven'] or s['fills'] or not s['entries']
            or any(not _accounted(o) for o in list(s['entries'].values())+list(s['exits'].values()))
            or e.get('complete_cash_source_no_owned_rows') is not True):
            raise ValueError('NO_EXECUTION_FINALITY_NOT_PROVEN')
        s.update(phase='TERMINAL',entry_blocked=True,terminal_net_usdt='0',
                 execution_verdict='NO_EXECUTION_NOT_LIFECYCLE_PASS')
    elif kind == 'FINALITY':
        if (not s['broker_flat_proven'] or any(Decimal(v) for v in s['held'].values())
                or any(not _accounted(o) for o in list(s['entries'].values()) + list(s['exits'].values()))
                or s['fee_unknown_execution_ids'] or not s['entries']
                or (s['last_fill_ms'] is not None and s['last_snapshot_ms'] < s['last_fill_ms'])):
            raise ValueError('FINALITY_NOT_PROVEN')
        if e.get('funding_complete') is not True:
            raise ValueError('FUNDING_FINALITY_UNKNOWN')
        net = signed(s['trade_cash_usdt']) + signed(s['funding_cash_usdt']) - signed(s['fees_usdt'])
        if net != signed(e['net_cash_usdt']):
            raise ValueError('CASH_RECONCILIATION_CONFLICT')
        s['terminal_net_usdt'], s['phase'], s['entry_blocked'] = text(net), 'TERMINAL', True
        s['finality_observed_ms'] = at
        s['flat_readback_observed_ms'] = s['last_snapshot_ms']
        s['flat_readback_after_deadline_ms'] = max(0, s['last_snapshot_ms'] - s['deadline_ms'])
        exceeded = net < -Decimal(plan['bounds']['max_all_in_loss_usdt'])
        if plan['bounds']['hard_final_loss_cap_required']:
            s['requested_loss_bound_breached'] = exceeded
            s['terminal_verdict'] = 'LOSS_BOUND_BREACHED' if exceeded else 'REPLAY_FINALITY_COMPLETE'
        else:
            s['all_in_exit_threshold_exceeded'] = exceeded
            s['terminal_verdict'] = 'EXIT_THRESHOLD_OVERSHOOT' if exceeded else 'REPLAY_FINALITY_COMPLETE'
        s['all_ten_complete'] = len(s['entries']) == 10 and all(
            Decimal(s['entries'][symbol]['filled']) == Decimal(legs[symbol]['quantity']) for symbol in legs)
    else:
        raise ValueError('UNKNOWN_EVENT_KIND')
    return s


class MicroJournal:
    """One isolated replay experiment. No transport method or live enable flag."""
    def __init__(self, path, plan):
        validate_plan(plan)
        self.plan = copy.deepcopy(plan)
        self._cache = None
        p = Path(path)
        if p.is_symlink() or any(parent.is_symlink() for parent in p.absolute().parents):
            raise ValueError('JOURNAL_SYMLINK')
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd); created = True
        except FileExistsError:
            created = False
        self.db = sqlite3.connect(p, isolation_level=None)
        if not created and self.db.execute('PRAGMA application_id').fetchone()[0] != 0x4B584D31:
            self.db.close(); raise ValueError('JOURNAL_IDENTITY_CONFLICT')
        if created:
            self.db.execute('PRAGMA application_id=1264078129')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS meta(plan TEXT,head TEXT,n INTEGER);'
            'CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,event_id TEXT UNIQUE,body TEXT,hash TEXT);')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT plan FROM meta').fetchone()
            if row is None:
                self.db.execute('INSERT INTO meta VALUES(?,?,0)', (canonical(plan), plan['plan_id']))
            elif row[0] != canonical(plan):
                raise ValueError('JOURNAL_PLAN_CONFLICT')
            self._replay(); self.db.commit()
        except Exception:
            self.db.rollback(); self.db.close(); raise

    def _replay(self):
        stamp=(self.db.execute('PRAGMA data_version').fetchone()[0],self.db.total_changes)
        if self._cache is not None and self._cache[0]==stamp:
            return copy.deepcopy(self._cache[1])
        meta = self.db.execute('SELECT plan,head,n FROM meta').fetchall()
        if len(meta) != 1 or meta[0][0] != canonical(self.plan):
            raise ValueError('JOURNAL_PLAN_CONFLICT')
        state, previous, n = initial(self.plan), self.plan['plan_id'], 0
        for seq, event_id, raw, pin in self.db.execute('SELECT seq,event_id,body,hash FROM events ORDER BY seq'):
            n += 1
            e = json.loads(raw)
            if seq != n or e['event_id'] != event_id or pin != hashlib.sha256((previous + raw).encode()).hexdigest():
                raise ValueError('JOURNAL_CHAIN_CONFLICT')
            state = apply_event(self.plan, state, e); previous = pin
        if previous != meta[0][1] or n != meta[0][2]:
            raise ValueError('JOURNAL_HEAD_CONFLICT')
        self._cache=(stamp,copy.deepcopy((state,previous,n)))
        return state, previous, n

    def snapshot(self):
        self.db.execute('BEGIN')
        try:
            state = self._replay()[0]; self.db.commit(); return state
        except Exception:
            self.db.rollback(); raise

    def append(self, event):
        raw = canonical(event)
        if len(raw.encode()) > 131072:
            raise ValueError('EVENT_SIZE_BOUND')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            prior = self.db.execute('SELECT body FROM events WHERE event_id=?', (event['event_id'],)).fetchone()
            if prior:
                if prior[0] != raw:
                    raise ValueError('EVENT_CONFLICT')
                self._replay(); self.db.commit(); return False
            state, previous, n = self._replay()
            verified_version=self._cache[0][0]
            updated=apply_event(self.plan, state, event)
            pin = hashlib.sha256((previous + raw).encode()).hexdigest()
            self.db.execute('INSERT INTO events VALUES(?,?,?,?)', (n + 1, event['event_id'], raw, pin))
            self.db.execute('UPDATE meta SET head=?,n=?', (pin, n + 1))
            self.db.commit()
            # Do not stamp an outside commit occurring just after ours as verified.
            stamp=(verified_version,self.db.total_changes)
            self._cache=(stamp,copy.deepcopy((updated,pin,n+1)))
            return True
        except Exception:
            self.db.rollback(); raise

    def actions(self, now_ms):
        state = self.snapshot(); integer(now_ms)
        if state['phase'] == 'TERMINAL':
            return []
        if self.plan['blocked_reasons'] and not state['entries']:
            return [dict(kind='BLOCKED_PLAN', reasons=self.plan['blocked_reasons'], orders_allowed=False)]
        if state['deadline_ms'] is not None and now_ms >= state['deadline_ms'] and not state['entry_blocked']:
            self.append(dict(kind='CLOCK', at_ms=now_ms, event_id='deadline-' + str(state['deadline_ms']),
                             source_sha256=self.plan['plan_id']))
            state = self.snapshot()
        if state['ownership_conflict']:
            return [dict(kind='OWNERSHIP_CONFLICT', orders_allowed=False)]
        orders = list(state['entries'].values()) + list(state['exits'].values())
        pending = [o for o in orders if not _accounted(o) and not o.get('is_native_protection')]
        unwind = state['entry_blocked'] or (state['deadline_ms'] is not None and now_ms >= state['deadline_ms'])
        if unwind:
            result = []
            for leg in self.plan['legs']:
                symbol = leg['symbol']; qty = state['held'][symbol]
                if any(o['symbol'] == symbol for o in pending):
                    result.append(dict(kind='RECONCILE', symbol=symbol, orders_allowed=False))
                    continue
                if Decimal(qty) > 0:
                    if any(o.get('definite_rejection') for o in state['exits'].values() if o['symbol']==symbol):
                        result.append(dict(kind='RECONCILE',symbol=symbol,reason='OWNED_EXIT_REJECTED_OWNER_ACTION',orders_allowed=False))
                        continue
                    count = sum(v['symbol'] == symbol for v in state['exits'].values())
                    request = dict(category='linear', symbol=symbol, side='Sell' if leg['side'] == 'Buy' else 'Buy',
                        qty=qty, orderType='Market', positionIdx=0, reduceOnly=True,
                        orderLinkId=leg['exit_prefix'] + f'-{count}')
                    result.append(dict(kind='EXIT', symbol=symbol, quantity=qty, request=request, orders_allowed=False))
                else:
                    for native in state['exits'].values():
                        if native['symbol']==symbol and native.get('is_native_protection') and not _accounted(native):
                            if native['cancel_sent']:
                                result.append(dict(kind='RECONCILE',symbol=symbol,orders_allowed=False))
                            else:
                                result.append(dict(kind='CANCEL_NATIVE_PROTECTION',symbol=symbol,
                                    order_link_id=native['link'],request=dict(category='linear',symbol=symbol,
                                        orderId=native['order_id']),orders_allowed=False))
            return result or [dict(kind='FINALITY_READBACK', orders_allowed=False)]
        if pending:
            result = [dict(kind='RECONCILE', symbol=o['symbol'], orders_allowed=False) for o in pending]
            result.extend(dict(kind='PROTECTION_READBACK', symbol=symbol, orders_allowed=False)
                for symbol, order in state['entries'].items()
                if Decimal(state['held'][symbol]) > Decimal(order['protected']))
            return result
        for leg in self.plan['legs']:
            order = state['entries'].get(leg['symbol'])
            if order is None:
                return [dict(kind='ENTRY', symbol=leg['symbol'], request=leg['request'], orders_allowed=False)]
            if Decimal(order['protected']) != Decimal(order['filled']):
                return [dict(kind='PROTECTION_READBACK', symbol=leg['symbol'], orders_allowed=False)]
        return [dict(kind='MONITOR', deadline_ms=state['deadline_ms'], orders_allowed=False)]

    def observe_risk(self, books, exit_fee_rates, *, funding_reserve_usdt, now_ms):
        """Persist the market observation/kill decision; never submit an order.

        Raw source custody/authentication belongs to the future bound reader.
        Replayed price recovery cannot undo the first recorded unwind decision.
        """
        integer(now_ms)
        payload = dict(books=books, exit_fee_rates=exit_fee_rates,
                       funding_reserve_usdt=funding_reserve_usdt)
        try:
            pin = digest(payload)
        except (ValueError, TypeError):
            pin = digest(dict(reason='INVALID_RISK_SOURCE', observed_ms=now_ms))
            e = dict(kind='RISK_SOURCE_UNKNOWN', reason='INVALID_RISK_SOURCE')
        else:
            e = dict(kind='RISK_OBSERVATION', **payload)
        e.update(at_ms=now_ms, source_sha256=pin, event_id='risk-' + digest(dict(pin=pin, at_ms=now_ms)))
        if len(canonical(e).encode()) > 131072:
            e = dict(kind='RISK_SOURCE_UNKNOWN', reason='RISK_SOURCE_SIZE_BOUND',
                     at_ms=now_ms, source_sha256=pin, event_id=e['event_id'])
        self.append(e)
        return self.snapshot()['last_risk_observation']

    def close(self):
        self.db.close()


def record_funding_cash(journal,row,observed_ms):
    """One actual settlement, regardless of later GET observation time/metadata."""
    symbol=row['symbol'];identifier=row['id'];t=int(row['transactionTime'])
    expected=dict(symbol=symbol,cash_usdt=text(signed(row['funding'])),settlement_ms=integer(t))
    if signed(row['funding'])!=signed(row['change']):raise ValueError('FUNDING_CASH_SOURCE_CONFLICT')
    prior=journal.snapshot()['funding'].get(canonical([symbol,identifier]))
    if prior is not None:
        if prior!=expected:raise ValueError('FUNDING_CONFLICT')
        return
    journal.append(dict(kind='FUNDING_CASH',symbol=symbol,settlement_id=identifier,
        settlement_ms=t,cash_usdt=expected['cash_usdt'],at_ms=observed_ms,
        source_sha256=digest(row),event_id='funding-'+digest(row)))


def liquidation_value(state, books, *, funding_reserve_usdt):
    unknown = dict(net_usdt=None, action='UNWIND_DATA_UNKNOWN', guaranteed_final_loss_cap=False,
                   orders_allowed=False, research_evidence_eligible=False)
    if state['fee_unknown_execution_ids'] or funding_reserve_usdt is None:
        return unknown
    try:
        reserve = numeric(funding_reserve_usdt, zero=True)
        value, estimated_fees = Decimal(0), Decimal(0)
        for symbol, side in BASKET:
            quantity = Decimal(state['held'][symbol])
            if quantity <= 0:
                continue
            row = books[symbol]
            bids, asks = _levels(row['bids'], True), _levels(row['asks'], False)
            fee = numeric(row['exit_taker_fee'], zero=True)
            if bids[0][0] >= asks[0][0]:
                raise ValueError('INVALID_BOOK')
            _, notional = _vwap(bids if side == 'Buy' else asks, quantity)
            value += notional * (1 if side == 'Buy' else -1)
            estimated_fees += notional * fee
        net = signed(state['trade_cash_usdt']) + value + signed(state['funding_cash_usdt']) - signed(state['fees_usdt']) - estimated_fees - reserve
        return dict(net_usdt=text(net), estimated_exit_fees_usdt=text(estimated_fees),
            funding_reserve_usdt=text(reserve), action='UNWIND_LOSS_LIMIT' if net <= -15 else 'MONITOR',
            guaranteed_final_loss_cap=False, orders_allowed=False, research_evidence_eligible=False,
            source_freshness_checked=False, slippage_already_in_fill_and_liquidation_prices=True)
    except (KeyError, ValueError, InvalidOperation):
        return unknown


def current_valuation(state, captures, fees, *, funding_reserve_usdt, now_ms):
    unknown = dict(net_usdt=None, action='UNWIND_DATA_UNKNOWN', orders_allowed=False,
                   research_evidence_eligible=False, guaranteed_final_loss_cap=False)
    held = {s for s, qty in state['held'].items() if Decimal(qty) > 0}
    try:
        if not isinstance(captures, dict) or not isinstance(fees, dict) or set(captures) != held or set(fees) != held:
            return unknown
        normalized = {}
        for symbol, cap in captures.items():
            if (not isinstance(cap, dict) or not isinstance(cap.get('params'), dict)
                    or not isinstance(cap.get('body'), dict)
                    or not isinstance(cap['body'].get('result'), dict)
                    or cap.get('endpoint') != '/v5/market/orderbook'
                    or cap['params'].get('category') != 'linear' or cap['params'].get('symbol') != symbol
                    or type(cap['body'].get('retCode')) is not int or cap['body']['retCode'] != 0
                    or cap['body']['result'].get('s') != symbol):
                return unknown
            book = cap['body']['result']
            normalized[symbol] = dict(bids=book['b'], asks=book['a'], exit_taker_fee=fees[symbol])
        if held:
            clock = common_source_clock(list(captures.values()), now_ms)
            if clock['status'] != 'OBSERVED_COMMON_2S_PASS':
                return dict(unknown, source_clock_status=clock['status'])
        result = liquidation_value(state, normalized, funding_reserve_usdt=funding_reserve_usdt)
        result['source_freshness_checked'] = True
        return result
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return unknown
