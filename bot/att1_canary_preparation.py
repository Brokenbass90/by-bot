"""Inert ATT1 cash/command preparation. No broker sender or money authority.

Hashes and pure validation establish consistency of declared evidence only.
The trusted GET collector and independent acceptance receipts establish its
provenance; neither this module nor a binding can authorize an order.
"""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import re
import hashlib
import json
from pathlib import Path

from bot.att1_coordinator_adapter import AdapterViolation, _number
from research_lab.att1_lifecycle_coordinator import digest
from research_lab.att1_lifecycle_profile import _decimal_text

DAY_MS = 86_400_000
MAX_EVIDENCE_AGE_MS = 60_000
BASE_PROFILE_SHA = '79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050'
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _mapping(value, fields, name):
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise AdapterViolation('invalid ' + name + ' fields')
    return dict(value)


def _sha(value, name):
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise AdapterViolation('invalid ' + name + ' hash')
    return value


def _clock(value, now, name):
    if type(value) is not int or not 0 < value <= now or now - value > MAX_EVIDENCE_AGE_MS:
        raise AdapterViolation('stale/invalid ' + name + ' clock')


def _day(now):
    try:
        return datetime.fromtimestamp(now // 1000, timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError) as exc:
        raise AdapterViolation('invalid UTC clock') from exc


def validate_canary_budget_inputs(binding: Mapping, old_budget_evidence: Mapping,
                                 cash_evidence: Mapping, *, now_ms: int) -> dict:
    """Validate declared source-bound inputs; no claim of authentication."""
    if type(now_ms) is not int or now_ms <= 0:
        raise AdapterViolation('invalid budget clock')
    b = _mapping(binding, {
        'base_profile_sha256', 'account_fingerprint_sha256', 'broker_truth_sha256',
        'account_mode', 'observed_ms', 'absolute_risk_cap', 'old_budget_ceiling',
        'max_notional', 'daily_loss_cap', 'max_concurrent_positions', 'send_enabled',
    }, 'binding')
    for key in ('base_profile_sha256', 'account_fingerprint_sha256', 'broker_truth_sha256'):
        _sha(b[key], key)
    _clock(b['observed_ms'], now_ms, 'binding')
    r = _number(b['absolute_risk_cap'], 'risk', positive=True)
    old_cap = _number(b['old_budget_ceiling'], 'OLD ceiling', positive=True)
    n = _number(b['max_notional'], 'notional', positive=True)
    daily = _number(b['daily_loss_cap'], 'daily cap', positive=True)
    if (b['base_profile_sha256'] != BASE_PROFILE_SHA or r > old_cap or n > 100
            or daily != 2 * r or b['account_mode'] != 'UNIFIED_ONE_WAY_USDT'
            or type(b['max_concurrent_positions']) is not int or b['max_concurrent_positions'] != 1
            or b['send_enabled'] is not False):
        raise AdapterViolation('unsafe inert binding')
    o = _mapping(old_budget_evidence, {
        'schema_id', 'account_fingerprint_sha256', 'broker_truth_sha256', 'observed_ms',
        'sizing_source_sha256', 'config_sha256', 'raw_source_sha256',
        'effective_equity_usdt', 'risk_per_trade_pct', 'att1_risk_mult',
        'breaker_risk_mult', 'voladj_mult', 'breaker_blocked',
        'cap_notional_to_equity', 'leverage', 'reserve_equity_frac', 'max_positions',
        'taker_fee_rate', 'fee_source_sha256', 'funding_cost_reserve_rate', 'funding_source_sha256',
    }, 'OLD budget')
    if (o['schema_id'] != 'att1_canary_old_budget_v1'
            or o['account_fingerprint_sha256'] != b['account_fingerprint_sha256']
            or o['broker_truth_sha256'] != b['broker_truth_sha256']
            or o['observed_ms'] != b['observed_ms'] or o['breaker_blocked'] is not False):
        raise AdapterViolation('OLD risk input identity/availability mismatch')
    _clock(o['observed_ms'], now_ms, 'OLD')
    for key in ('sizing_source_sha256', 'config_sha256', 'raw_source_sha256', 'fee_source_sha256', 'funding_source_sha256'):
        _sha(o[key], key)
    eq = _number(o['effective_equity_usdt'], 'equity', positive=True)
    pct = _number(o['risk_per_trade_pct'], 'risk pct', positive=True)
    mult = _number(o['att1_risk_mult'], 'ATT1 multiplier', positive=True)
    breaker = _number(o['breaker_risk_mult'], 'breaker', positive=True)
    vol = _number(o['voladj_mult'], 'volatility', positive=True)
    # Matches the deployed legacy cash-risk calculation. The .1 clamp is not
    # permission to bypass a blocked breaker or non-positive strategy size.
    computed_cap = eq * pct / 100 * max(Fraction('0.1'), mult * breaker) * vol
    leverage = _number(o['leverage'], 'leverage', positive=True)
    reserve = _number(o['reserve_equity_frac'], 'equity reserve', nonnegative=True)
    slots = o['max_positions']
    if (type(o['cap_notional_to_equity']) is not bool or type(slots) is not int
            or slots < 0 or reserve >= 1 or pct > 100 or computed_cap != old_cap):
        raise AdapterViolation('OLD risk input calculation mismatch')
    notional_cap = eq * (1 if o['cap_notional_to_equity'] else leverage) * (1 - reserve)
    if slots > 1:
        notional_cap /= slots
    if n > notional_cap:
        raise AdapterViolation('OLD notional ceiling exceeded')
    for key in ('taker_fee_rate', 'funding_cost_reserve_rate'):
        rate = _number(o[key], key, nonnegative=True)
        if rate >= 1:
            raise AdapterViolation('invalid cost reserve rate')
    cash_fields = {
        'schema_id', 'account_fingerprint_sha256', 'observed_ms', 'coverage_start_ms',
        'coverage_end_ms', 'owners', 'complete', 'unresolved_prior_day_costs', 'source_sha256', 'events',
    }
    if isinstance(cash_evidence, Mapping) and 'prior_day_coverage_sha256' in cash_evidence:
        cash_fields.add('prior_day_coverage_sha256')
    c = _mapping(cash_evidence, cash_fields, 'cash coverage')
    if 'prior_day_coverage_sha256' in c:
        _sha(c['prior_day_coverage_sha256'], 'prior-day coverage')
    _clock(c['observed_ms'], now_ms, 'cash')
    _sha(c['source_sha256'], 'cash source')
    start = now_ms // DAY_MS * DAY_MS
    if (c['schema_id'] != 'att1_canary_cash_coverage_v1'
            or c['account_fingerprint_sha256'] != b['account_fingerprint_sha256']
            or c['complete'] is not True or c['unresolved_prior_day_costs'] is not False
            or not isinstance(c['owners'], list) or sorted(c['owners']) != ['NEW', 'OLD']
            or type(c['coverage_start_ms']) is not int or c['coverage_start_ms'] != start
            or type(c['coverage_end_ms']) is not int or c['coverage_end_ms'] != c['observed_ms']
            or not start <= c['coverage_end_ms'] <= now_ms or not isinstance(c['events'], list)):
        raise AdapterViolation('cash coverage incomplete')
    seen, spent, normalized = {}, Fraction(0), []
    for value in c['events']:
        fields = {
            'source_id', 'source_sha256', 'account_fingerprint_sha256', 'owner',
            'economic_ms', 'received_ms', 'gross_realized_usdt', 'execution_fee_usdt', 'funding_cash_usdt',
        }
        if isinstance(value, Mapping) and 'command_sha256' in value:
            fields.add('command_sha256')
        row = _mapping(value, fields, 'cash event')
        if 'command_sha256' in row:
            _sha(row['command_sha256'], 'cash command')
        sid = row['source_id']
        if not isinstance(sid, str) or not 1 <= len(sid) <= 256:
            raise AdapterViolation('cash event identity missing')
        _sha(row['source_sha256'], 'cash event')
        ex, rx = row['economic_ms'], row['received_ms']
        if (row['owner'] not in {'OLD', 'NEW'} or row['account_fingerprint_sha256'] != b['account_fingerprint_sha256']
                or type(ex) is not int or type(rx) is not int or not start <= ex <= rx <= c['observed_ms']):
            raise AdapterViolation('cash event outside complete coverage')
        economic = {k: v for k, v in row.items() if k != 'received_ms'}
        if sid in seen:
            if seen[sid] != economic:
                raise AdapterViolation('conflicting cash event identity')
            continue
        seen[sid] = economic
        gross = _number(row['gross_realized_usdt'], 'gross realized')
        fee = _number(row['execution_fee_usdt'], 'execution fee', nonnegative=True)
        funding = _number(row['funding_cash_usdt'], 'funding cash')
        spent += max(-gross, 0) + fee + max(-funding, 0)
        normalized.append(row)
    c['events'] = normalized
    out = {'schema_id': 'att1_canary_validated_budget_v1', 'binding': deepcopy(b),
           'old_budget_evidence': deepcopy(o), 'cash_evidence': deepcopy(c),
           'now_ms': now_ms, 'day_utc': _day(now_ms), 'spent_usdt': _decimal_text(spent),
           'binding_sha256': digest(b), 'cash_coverage_sha256': digest(c),
           'source_ids': sorted(seen), 'orders_allowed': False}
    out['validation_sha256'] = digest(out)
    return out


def _revalidate(validated):
    if not isinstance(validated, Mapping):
        raise AdapterViolation('validated budget required')
    try:
        value = validate_canary_budget_inputs(validated['binding'], validated['old_budget_evidence'],
                                              validated['cash_evidence'], now_ms=validated['now_ms'])
        if 'handoff_binding' in validated:
            value = bind_canary_handoff(value, **validated['handoff_binding']['inputs'])
        if 'command_binding' in validated:
            attachment = validated['command_binding']
            value = bind_canary_command_budget(value, attachment['profile'], attachment['intent'],
                                                order_link_id=attachment['command']['orderLinkId'])
    except KeyError as exc:
        raise AdapterViolation('validated budget malformed') from exc
    if value != validated:
        raise AdapterViolation('validated budget projection/provenance changed')
    return value


def bind_canary_command_budget(validated: Mapping, profile: Mapping, intent: Mapping, *,
                               order_link_id: str) -> dict:
    """Bind reserves to exact frozen admission/quantity and an inert payload."""
    from research_lab.att1_lifecycle_profile import admit_signal
    v = _revalidate(validated)
    if 'command_binding' in v:
        raise AdapterViolation('command already bound')
    if (not isinstance(profile, Mapping) or profile.get('broker_binding') != v['binding']
            or not isinstance(intent, Mapping) or intent.get('submit_ms') != v['now_ms']
            or not isinstance(order_link_id, str) or not 1 <= len(order_link_id) <= 36):
        raise AdapterViolation('command execution binding mismatch')
    try:
        admitted = admit_signal(profile, intent['signal'], intent['instrument'], intent['book_state'],
                                book=intent['book'], submit_ms=intent['submit_ms'])
    except (KeyError, ValueError, TypeError) as exc:
        raise AdapterViolation('invalid command admission inputs') from exc
    if not admitted['accepted']:
        raise AdapterViolation('command admission rejected: ' + admitted['code'])
    plan = admitted['plan']
    qty = _number(plan['requested_qty'], 'command qty', positive=True)
    stop = _number(plan['original_stop'], 'command stop', positive=True)
    entry = _number(plan['nominal_entry'], 'command entry', positive=True)
    expansion = _number(profile['execution']['max_adverse_risk_expansion'], 'expansion', nonnegative=True)
    risk = qty * (stop - entry) * (1 + expansion)
    old = v['old_budget_evidence']
    costs = qty * stop * (2 * _number(old['taker_fee_rate'], 'fee rate')
                           + _number(old['funding_cost_reserve_rate'], 'funding reserve'))
    command = {'category': 'linear', 'symbol': plan['symbol'], 'side': 'Sell',
               'orderType': 'Market', 'timeInForce': 'IOC', 'qty': plan['requested_qty'],
               'positionIdx': 0, 'reduceOnly': False, 'orderLinkId': order_link_id,
               'account_fingerprint_sha256': v['binding']['account_fingerprint_sha256'],
               'execution_binding_sha256': v['binding_sha256'],
               'profile_sha256': profile['profile_sha256'], 'decision_id': plan['decision_id'],
               'h1_close_ms': plan['bar_close_ms'], 'nominal_entry': plan['nominal_entry'],
               'original_stop': plan['original_stop'], 'orders_allowed': False}
    v = deepcopy(v)
    v.pop('validation_sha256')
    v['command_binding'] = {'profile': deepcopy(dict(profile)), 'intent': deepcopy(dict(intent)),
                            'command': command, 'command_sha256': digest(command),
                            'required_risk_usdt': _decimal_text(risk),
                            'required_cost_reserve_usdt': _decimal_text(costs)}
    v['validation_sha256'] = digest(v)
    return v


def project_att1_daily_budget(validated: Mapping, occupied: list[Mapping], *,
                             proposed_risk_usdt: str, proposed_cost_reserve_usdt: str) -> dict:
    v = _revalidate(validated)
    if not isinstance(occupied, list):
        raise AdapterViolation('occupied reservation inventory required')
    risk = _number(proposed_risk_usdt, 'proposed risk', nonnegative=True)
    costs = _number(proposed_cost_reserve_usdt, 'proposed costs', nonnegative=True)
    spent = _number(v['spent_usdt'], 'spent', nonnegative=True)
    reserved, unknown = Fraction(0), False
    for row in occupied:
        if not isinstance(row, Mapping):
            raise AdapterViolation('invalid occupied reservation')
        if row.get('risk_reserve_usdt') is None or row.get('cost_reserve_usdt') is None:
            unknown = True
            continue
        reserved += _number(row['risk_reserve_usdt'], 'occupied risk', nonnegative=True)
        reserved += _number(row['cost_reserve_usdt'], 'occupied costs', nonnegative=True)
    remaining = _number(v['binding']['daily_loss_cap'], 'daily cap') - spent - reserved
    reason = ('UNKNOWN_OCCUPIED_RISK' if unknown else
              'ABSOLUTE_RISK_CAP_EXCEEDED' if risk > _number(v['binding']['absolute_risk_cap'], 'risk cap') else
              'DAILY_BUDGET_EXCEEDED' if risk + costs > remaining else 'ADMITTED_ORDERS_OFF')
    out = {'admitted': reason == 'ADMITTED_ORDERS_OFF', 'reason': reason,
           'day_utc': v['day_utc'], 'spent_usdt': _decimal_text(spent),
           'reserved_usdt': _decimal_text(reserved), 'remaining_usdt': _decimal_text(remaining),
           'binding_sha256': v['binding_sha256'], 'budget_evidence_sha256': v['validation_sha256'],
           'orders_allowed': False}
    out['projection_sha256'] = digest(out)
    return out


def validate_canary_handoff(*, pause_snapshot: Mapping, broker_snapshot: Mapping,
                            old_intent_inventory: Mapping, old_watermarks: Mapping,
                            now_ms: int) -> dict:
    """Validate declarations of complete drain, without activating a route."""
    from bot.att1_coordinator_adapter import _require_account, ATT1_H1_MS
    if type(now_ms) is not int or now_ms <= 0:
        raise AdapterViolation('invalid handoff clock')
    p = _mapping(pause_snapshot, {'account','observed_ms','source_sha256','control'}, 'pause')
    b = _mapping(broker_snapshot, {'schema_id','account','observed_ms','position_count',
                                  'order_count','flat_no_orders','source_sha256'}, 'broker snapshot')
    o = _mapping(old_intent_inventory, {'account','observed_ms','source_sha256','complete',
            'finality_complete','costs_complete','unresolved','drained_at_ms'}, 'OLD inventory')
    w = _mapping(old_watermarks, {'account','observed_ms','source_sha256','complete',
                                 'last_old_h1_ms','symbols'}, 'OLD watermarks')
    account = _require_account(p['account'])
    for name, obj in (('pause',p), ('broker',b), ('inventory',o), ('watermarks',w)):
        if obj['account'] != account:
            raise AdapterViolation('handoff account mismatch')
        _clock(obj['observed_ms'], now_ms, name)
        _sha(obj['source_sha256'], name)
    control = _mapping(p['control'], {'exists','scope','read_error','paused_sleeves'}, 'pause control')
    if (control['exists'] is not True or control['read_error'] is not None
            or control['scope'] != 'new_entries_only' or not isinstance(control['paused_sleeves'], list)
            or 'att1' not in control['paused_sleeves']):
        raise AdapterViolation('valid OLD entry pause required')
    if (b['schema_id'] != 'att1_broker_snapshot_v1' or b['flat_no_orders'] is not True
            or type(b['position_count']) is not int or b['position_count'] != 0
            or type(b['order_count']) is not int or b['order_count'] != 0):
        raise AdapterViolation('handoff broker is not flat/no orders')
    drain = o['drained_at_ms']; last = w['last_old_h1_ms']
    if (o['complete'] is not True or o['finality_complete'] is not True
            or o['costs_complete'] is not True or o['unresolved'] != []
            or type(drain) is not int or not 0 < drain <= o['observed_ms']
            or w['complete'] is not True or type(last) is not int
            or not 0 < last <= drain or last % ATT1_H1_MS):
        raise AdapterViolation('OLD drain/finality/watermarks incomplete')
    rows = w['symbols']
    symbols = {'ADAUSDT','BTCUSDT','DOTUSDT','ETHUSDT','LINKUSDT','LTCUSDT','SOLUSDT','SUIUSDT'}
    if not isinstance(rows, list) or len(rows) != len(symbols):
        raise AdapterViolation('OLD symbol watermarks incomplete')
    seen = set()
    for row in rows:
        r = _mapping(row, {'symbol','latest_h1_ms','cooldown_until_ms','last_terminal_ms'}, 'watermark')
        if r['symbol'] not in symbols or r['symbol'] in seen:
            raise AdapterViolation('OLD symbol watermark mismatch')
        seen.add(r['symbol'])
        h1, cooldown, terminal = r['latest_h1_ms'], r['cooldown_until_ms'], r['last_terminal_ms']
        if (type(h1) is not int or not 0 <= h1 <= last or h1 % ATT1_H1_MS
                or type(cooldown) is not int or cooldown < h1
                or type(terminal) is not int or not 0 <= terminal <= drain
                or cooldown < terminal):
            raise AdapterViolation('invalid OLD symbol watermark/cooldown')
    out = {'account':account, 'drained_at_ms':drain, 'last_old_h1_ms':last,
           'minimum_cutover_ms':(max(drain,last)//ATT1_H1_MS+1)*ATT1_H1_MS,
           'symbols':deepcopy(rows), 'orders_allowed':False}
    out['handoff_sha256'] = digest({'pause':p,'broker':b,'inventory':o,'watermarks':w,'now_ms':now_ms})
    return out


def bind_canary_handoff(validated: Mapping, **inputs) -> dict:
    v = _revalidate(validated)
    if 'handoff_binding' in v or 'command_binding' in v:
        raise AdapterViolation('handoff must precede command binding')
    result = validate_canary_handoff(**inputs)
    from bot.att1_coordinator_adapter import att1_broker_account_fingerprint
    if (inputs['now_ms'] != v['now_ms'] or att1_broker_account_fingerprint(result['account'])
            != v['binding']['account_fingerprint_sha256']):
        raise AdapterViolation('handoff budget account/clock mismatch')
    v.pop('validation_sha256')
    v['handoff_binding'] = {'inputs':deepcopy(inputs), 'result':result}
    v['validation_sha256'] = digest(v)
    return v


def preparation_implementation_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    files = ('bot/att1_canary_preparation.py','bot/att1_coordinator_adapter.py')
    from research_lab.att1_lifecycle_session import implementation_hash
    return digest({'preparation':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files},
                   'lifecycle_implementation_sha256':implementation_hash()})


def prepare_new_att1_entry(con, account: str, *, profile: Mapping, intent: Mapping,
                           validated_budget: Mapping, now_ms: int) -> dict:
    from bot import att1_coordinator_adapter as a
    try:
        key = a._decision_key((account,a.ATT1_FAMILY,intent['signal']['symbol'],'SELL',intent['signal']['bar_close_ms']))
    except (KeyError, TypeError) as exc:
        raise AdapterViolation('invalid entry intent') from exc
    # Existing uncertain command is recovery-owned. Do not pass new-entry gates
    # or expose another command, even after a crash before a journal START.
    saved = con.execute('''SELECT owner,order_link_id,preparation_json,command_sha256,terminal_at_ms
        FROM att1_decisions WHERE account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?''',key).fetchone()
    if saved is not None:
        if saved[0] != 'NEW' or not saved[2]:
            raise AdapterViolation('decision occupied without NEW preparation provenance')
        state = json.loads(saved[2])
        if (state['profile'] != profile or state['intent'] != intent
                or digest(state['command']) != saved[3]
                or state['implementation_sha256'] != preparation_implementation_hash()):
            raise AdapterViolation('persisted preparation identity changed')
        return {'status':'RECOVERY_REQUIRED_LOOKUP_ONLY','commands':[], 'order_link_id':saved[1],
                'orders_allowed':False, 'preparation':state}
    v = _revalidate(validated_budget)
    handoff = v.get('handoff_binding', {}).get('result')
    if not handoff or handoff['account'] != account or now_ms != v['now_ms']:
        raise AdapterViolation('fresh source-bound handoff required')
    route = a.read_att1_route(con, account)
    if route['owner'] != 'NEW_READY' or route['cutover_ms'] < handoff['minimum_cutover_ms']:
        raise AdapterViolation('NEW route/drain cutover mismatch')
    v = bind_canary_command_budget(v,profile,intent,order_link_id=a._stable_link_id(key[0],key[2],key[3],key[4]))
    attachment = v['command_binding']
    reservation = a.reserve_new_att1_preparation(con,account,symbol=key[2],side=key[3],h1_close_ms=key[4],
        now_ms=now_ms,validated_budget=v,proposed_risk_usdt=attachment['required_risk_usdt'],
        proposed_cost_reserve_usdt=attachment['required_cost_reserve_usdt'])
    return {'status':'PREPARED_ORDERS_OFF','commands':[deepcopy(attachment['command'])],
            'reservation':reservation, 'orders_allowed':False, 'broker_order_id':None,
            'execution_evidence':'CAPTURED_COMMAND_NO_BROKER_ORDER',
            'implementation_sha256':preparation_implementation_hash()}


def prepare_new_att1_management(*, session, coordinator_intent: Mapping,
                                binding: Mapping, now_ms: int) -> dict:
    from bot import att1_coordinator_adapter as a
    from research_lab.att1_lifecycle_session import LifecycleSession
    if not isinstance(session, LifecycleSession) or not isinstance(binding, Mapping):
        raise AdapterViolation('owned lifecycle session/binding required')
    account = binding.get('reservation_account')
    frozen = {k:v for k,v in binding.items() if k != 'reservation_account'}
    if frozen != session.profile.get('broker_binding'):
        raise AdapterViolation('management execution binding mismatch')
    receipt = session.refresh()
    key = a._decision_key((account,a.ATT1_FAMILY,receipt['plan']['symbol'],'SELL',receipt['plan']['bar_close_ms']))
    a._validate_new_lifecycle_session(session,key)
    records = session.journal.read()
    if (type(now_ms) is not int or now_ms <= 0
            or any(e.get('received_ms',0)>now_ms for e in records)):
        raise AdapterViolation('management clock precedes journal')
    if coordinator_intent != {'intents':receipt['intents'], 'pending_exit':receipt['pending_exit']}:
        raise AdapterViolation('coordinator intent changed/stale')
    shared = {'category':'linear','symbol':key[2],'positionIdx':0,'orders_allowed':False,
              'account_fingerprint_sha256':frozen['account_fingerprint_sha256'],
              'execution_binding_sha256':digest(frozen), 'profile_sha256':session.profile['profile_sha256'],
              'decision_id':receipt['plan']['decision_id']}
    commands, lookup = [], []
    protect = Fraction(receipt['intents']['protect_qty'])
    held = Fraction(receipt['held_qty'])
    if protect:
        if protect != held:
            raise AdapterViolation('protection must cover actual remainder')
        commands.append({**shared,'kind':'NATIVE_PROTECTION','tpslMode':'Full',
                         'size':_decimal_text(held),'stopLoss':receipt['plan']['original_stop']})
    entry_link = a._stable_link_id(key[0],key[2],key[3],key[4])
    if receipt['intents']['cancel_entry']:
        commands.append({**shared,'kind':'CANCEL_ENTRY','orderLinkId':entry_link})
    pending = receipt['pending_exit']
    if pending:
        link = a.att1_exit_order_link_id(key,pending['exit_order_id'])
        remaining = Fraction(pending['remaining_qty'])
        if remaining > held:
            raise AdapterViolation('exit exceeds actual held remainder')
        if receipt['intents']['cancel_exit']:
            commands.append({**shared,'kind':'CANCEL_EXIT','orderLinkId':link})
            lookup.append(link)
        elif pending['acknowledged'] or remaining != Fraction(pending['qty']) or not remaining:
            lookup.append(link)
        else:
            commands.append({**shared,'kind':'EXIT','side':'Buy','orderType':'Market','timeInForce':'IOC',
                             'qty':_decimal_text(remaining),'reduceOnly':True,'orderLinkId':link,
                             'exit_order_id':pending['exit_order_id'],'reason':pending['reason']})
    return {'status':'RECOVERY_REQUIRED_LOOKUP_ONLY' if lookup else 'PREPARED_ORDERS_OFF',
            'orders_allowed':False, 'commands':commands, 'lookup_order_links':lookup,
            'execution_evidence':'CAPTURED_COMMAND_NO_BROKER_ORDER', 'broker_order_id':None}
