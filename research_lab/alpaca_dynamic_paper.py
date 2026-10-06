"""PAPER-only adapter for an immutable Dynamic V1 plan.

No LIVE endpoint, promotion or account-wide flatten operation exists here. A
dispatch is persisted *before* POST; an ambiguous result is looked up, never
resent. Broker paper fills remain separate from synthetic DynamicBook slots.
"""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_CEILING
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time

from research_lab.alpaca_dynamic_v1 import (
    canonical, dec, digest, instant, pin, policy_check, positive, session_at,
    source_check,
)

PAPER = 'https://paper-api.alpaca.markets'
CORE = ('epoch_sha256 slot_entry_order_id symbol qty reference_ask stop_price '
        'risk_distance notional_usd modeled_stop_risk_usd protection_qty '
        'notional_limit_usd funding_limit_usd fee_rate protection_tif '
        'ranking_sha256 snapshot_sha256 source_sha256 session prepared_ms').split()


def earnings_check(dates, session):
    """Unknown calendar is unsafe; keep the existing five-calendar-day guard."""
    today = date.fromisoformat(session)
    try:
        future = sorted(date.fromisoformat(d) for d in dates if date.fromisoformat(d) >= today)
    except (ValueError, TypeError):
        return {'safe': False, 'reason': 'INVALID_EARNINGS_SOURCE'}
    if not future:
        return {'safe': False, 'reason': 'EARNINGS_UNKNOWN'}
    return {'safe': (future[0] - today).days > 5, 'next_date': future[0].isoformat()}


def result(status, **fields):
    return {'status': status, 'money_authority': False, 'live_orders_allowed': False,
            'evidence_kind': 'BROKER_PAPER', **fields}


def _plan_check(plan, policy):
    policy_check(policy)
    source_check(policy, policy['calendar_sessions'])
    core = {key: plan[key] for key in CORE}
    identity = digest(core)
    if (plan['receipt_id'] != identity or plan['client_order_id'] != 'dyn1-' + identity[:32]
        or plan['epoch_sha256'] != digest(policy) or plan['status'] != 'RESERVED_ORDERS_OFF'
        or plan['money_authority'] is not False or plan['orders_allowed'] is not False):
        raise ValueError('PLAN_IDENTITY_OR_AUTHORITY')
    for field in ('ranking_sha256', 'snapshot_sha256', 'source_sha256'):
        pin(plan[field])
    slot = next(s for s in policy['inherited_slots'] if s['entry_order_id'] == plan['slot_entry_order_id'])
    qty, ask, stop, distance = (positive(plan[k]) for k in ('qty', 'reference_ask', 'stop_price', 'risk_distance'))
    fee = dec(plan['fee_rate'])
    if (plan['symbol'] not in policy['universe'] or plan['symbol'] in {'SPY', 'QQQ'}
        or qty != positive(plan['protection_qty']) or ask - stop != distance or fee < 0
        or qty * ask != positive(plan['notional_usd']) or qty * distance != positive(plan['modeled_stop_risk_usd'])
        or qty * ask > positive(plan['notional_limit_usd']) or qty * ask > positive(slot['notional_cap'])
        or qty * distance > positive(slot['risk_cap'])
        or qty * ask * (1 + fee) > positive(plan['funding_limit_usd'])
        or positive(plan['notional_limit_usd']) > positive(slot['notional_cap'])
        or positive(plan['funding_limit_usd']) > positive(plan['notional_limit_usd']) * (1 + fee)
        or plan['protection_tif'] != ('gtc' if qty == qty.to_integral_value() else 'day')
        or qty.as_tuple().exponent < -9 or qty * ask < 1):
        raise ValueError('PLAN_QUANTITY_OR_BUDGET')
    window = session_at(policy['calendar_sessions'], instant(plan['prepared_ms']))
    if not window or window['session'] != plan['session'] or window['open_ms'] < policy['first_window_ms']:
        raise ValueError('PLAN_WINDOW')
    return core, slot


@contextmanager
def _store(runtime):
    path = Path(runtime).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('STATE_SYMLINK')
    path.mkdir(parents=True, exist_ok=True)
    for name in ('paper.lock', 'paper.sqlite'):
        p = path / name
        if p.exists() and (not p.is_file() or p.stat().st_nlink != 1 or p.stat().st_uid != os.getuid()):
            raise ValueError('STATE_IDENTITY')
    with (path / 'paper.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = sqlite3.connect(path / 'paper.sqlite')
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE IF NOT EXISTS intents (id TEXT PRIMARY KEY, account TEXT NOT NULL, slot TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(account,slot))')
            db.commit()
            (path / 'paper.sqlite').chmod(0o600)
            yield db, path
        finally:
            db.close()


def _save(db, item):
    db.execute('INSERT OR REPLACE INTO intents VALUES (?,?,?,?)',
               (item['id'], item['account'], item['slot'], canonical(item).decode()))
    db.commit()


def _same_position(client, symbol, qty):
    rows = [p for p in client.list_positions() if p['symbol'] == symbol]
    if len(rows) != 1 or positive(rows[0]['qty']) != qty:
        raise ValueError('PAPER_POSITION_OWNERSHIP_MISMATCH')


def execute_paper(plan, policy, client, expected_paper_id, runtime, now_ms, *, send=False):
    """Default GET-only. Caller must hold the shared broker-account writer lock.

    Recovery of a previously dispatched entry/protection is allowed after the
    selection window, but a new entry never is. It cannot release/reprice slots.
    """
    started = time.monotonic()
    dispatched = False
    try:
        if client.base_url != PAPER or not expected_paper_id or expected_paper_id == policy['account_id']:
            raise ValueError('EXACT_DISTINCT_PAPER_ENDPOINT_REQUIRED')
        _plan_check(plan, policy)
        now_ms = instant(now_ms)
        account = client.get_account()
        if account['id'] != expected_paper_id:
            raise ValueError('PAPER_ACCOUNT_MISMATCH')
        identity = digest({'parent': plan['receipt_id'], 'paper_account': account['id']})
        cid, stop_cid = 'dyp-' + identity[:32], 'dys-' + identity[:32]
        with _store(runtime) as (db, path):
            row = db.execute('SELECT payload FROM intents WHERE id=?', (identity,)).fetchone()
            item = json.loads(row[0]) if row else None
            dispatched = item is not None
            if item and item['plan'] != plan:
                raise ValueError('PAPER_INTENT_CONFLICT')
            if item and item.get('receipt'):
                receipt = item['receipt']
                if receipt['status'] == 'PAPER_PROTECTED':
                    from scripts.equities_alpaca_paper_bridge import _confirmed_intended_stop
                    _same_position(client, plan['symbol'], positive(receipt['filled_qty']))
                    _confirmed_intended_stop(client, {'id': receipt['stop_order_id']}, symbol=plan['symbol'],
                                             qty=float(receipt['filled_qty']), requested_stop=float(receipt['stop_price']))
                    return receipt
            if not item:
                if (account.get('trading_blocked') is not False or account.get('account_blocked') is not False
                    or dec(account['cash']) < positive(plan['funding_limit_usd'])):
                    raise ValueError('PAPER_CASH_OR_ACCOUNT_BLOCKED')
                clock = client.get_clock()
                clock_ms = int(datetime.fromisoformat(clock['timestamp'].replace('Z', '+00:00')).timestamp() * 1000)
                window = session_at(policy['calendar_sessions'], now_ms)
                if (clock.get('is_open') is not True or not window or window['session'] != plan['session']
                    or not 0 <= now_ms - plan['prepared_ms'] <= policy['max_snapshot_age_ms']
                    or abs(now_ms - clock_ms) > 5000):
                    raise ValueError('PAPER_ENTRY_WINDOW_OR_CLOCK')
                orders = client.list_orders(status='open', limit=100, symbols=[plan['symbol']])
                if len(orders) >= 100 or any(p['symbol'] == plan['symbol'] for p in client.list_positions()) or any(o['symbol'] == plan['symbol'] for o in orders):
                    return result('BLOCKED_EXECUTION', reason='FOREIGN_PAPER_SYMBOL_OR_ORDER')
                if db.execute('SELECT 1 FROM intents').fetchone() or (path/'protective_exit_hwm.json').exists():
                    return result('BLOCKED_EXECUTION', reason='PAPER_ONE_LIFECYCLE_BOUND')
                if client.get_order_by_client_id(cid) is not None or client.get_order_by_client_id(stop_cid) is not None:
                    return result('BLOCKED_EXECUTION', reason='UNOWNED_CLIENT_ID_EXISTS')
                if not send:
                    return result('PAPER_READ_ONLY_READY', parent_receipt_id=plan['receipt_id'], paper_account_id=account['id'])
                clock = client.get_clock()
                effective_ms = now_ms + int((time.monotonic()-started)*1000)
                clock_ms = int(datetime.fromisoformat(clock['timestamp'].replace('Z','+00:00')).timestamp()*1000)
                if (clock.get('is_open') is not True or not session_at(policy['calendar_sessions'],effective_ms)
                    or abs(effective_ms-clock_ms)>5000
                    or effective_ms-plan['prepared_ms']>policy['max_snapshot_age_ms']):
                    raise ValueError('PAPER_DISPATCH_WINDOW_OR_CLOCK_EXPIRED')
                item = {'id': identity, 'account': account['id'], 'slot': plan['slot_entry_order_id'], 'plan': plan,
                        'entry_cid': cid, 'stop_cid': stop_cid, 'phase': 'ENTRY_DISPATCHED'}
                _save(db, item)  # irreversible local dispatch boundary before network POST
                dispatched = True
                if session_at(policy['calendar_sessions'],now_ms+int((time.monotonic()-started)*1000)) is None:
                    return result('BLOCKED_EXECUTION',reason='PERSISTED_DISPATCH_EXPIRED_NO_RESEND')
                limit = positive(plan['reference_ask']).quantize(Decimal('.01'), rounding=ROUND_DOWN)
                order = client._request('POST', '/v2/orders', {'symbol': plan['symbol'], 'side': 'buy', 'type': 'limit',
                    'qty': plan['qty'], 'limit_price': format(limit, '.2f'), 'time_in_force': 'day', 'client_order_id': cid})
            else:
                order = client.get_order_by_client_id(cid)
            if not order:
                return result('BLOCKED_EXECUTION', reason='UNCERTAIN_ENTRY_NO_RESEND', parent_receipt_id=plan['receipt_id'])
            from scripts.equities_alpaca_paper_bridge import (
                _terminal_intended_entry, _persist_intended_pending_fill,
                _complete_intended_paper_simple_stop, _persistent_exit_tif_for_qty,
            )
            if not send:
                return result('PAPER_RECOVERY_REQUIRED', reason='READ_ONLY_NO_CANCEL_OR_PROTECTION', parent_receipt_id=plan['receipt_id'])
            checked = client.get_order(order['id'])
            if (checked.get('id')!=order['id'] or checked.get('client_order_id')!=cid or checked.get('symbol')!=plan['symbol']
                or checked.get('side')!='buy' or checked.get('type')!='limit'
                or positive(checked['qty'])!=positive(plan['qty'])
                or positive(checked['limit_price'])!=positive(plan['reference_ask']).quantize(Decimal('.01'),rounding=ROUND_DOWN)):
                raise ValueError('PAPER_PRE_CANCEL_OWNERSHIP_CONFLICT')
            entry = _terminal_intended_entry(client, order, expected_symbol=plan['symbol'], timeout_sec=2)
            qty, price = positive(entry['filled_qty']), positive(entry['filled_avg_price'])
            limit = positive(plan['reference_ask']).quantize(Decimal('.01'), rounding=ROUND_DOWN)
            if entry.get('client_order_id') != cid or entry.get('type') != 'limit' or positive(entry['qty']) != positive(plan['qty']) or positive(entry['limit_price']) != limit:
                raise ValueError('PAPER_ENTRY_READBACK_CONTRACT')
            _same_position(client, plan['symbol'], qty)
            ledger = path / 'protective_exit_hwm.json'
            if not ledger.exists():
                _persist_intended_pending_fill(ledger, symbol=plan['symbol'], account_id=account['id'], entry=entry)
            floor = (price - positive(plan['risk_distance'])).quantize(Decimal('.01'), rounding=ROUND_CEILING)
            if not 0 < floor < price:
                raise ValueError('PAPER_INVALID_FILL_FLOOR')
            stop = client.get_order_by_client_id(stop_cid)
            if stop is None:
                if item['phase'] == 'STOP_DISPATCHED':
                    return result('BLOCKED_EXECUTION', reason='UNCERTAIN_STOP_NO_RESEND', entry_order_id=entry['id'])
                item['phase'] = 'STOP_DISPATCHED'
                _save(db, item)
                stop = client.submit_stop_sell(plan['symbol'], qty=float(qty), stop_price=float(floor),
                    time_in_force=_persistent_exit_tif_for_qty('', float(qty)), client_order_id=stop_cid)
            if stop.get('client_order_id') != stop_cid:
                raise ValueError('PAPER_STOP_OWNERSHIP_CONFLICT')
            confirmed = _complete_intended_paper_simple_stop(client=client, base_url=PAPER, state_dir=path,
                ledger_path=ledger, account_id=account['id'], entry_order=entry, stop_order=stop,
                symbol=plan['symbol'], requested_stop=float(floor))
            within = (qty <= positive(plan['qty']) and price <= limit and qty * price <= positive(plan['notional_limit_usd'])
                      and qty * price * (1 + dec(plan['fee_rate'])) <= positive(plan['funding_limit_usd']))
            receipt = result('PAPER_PROTECTED' if within else 'BLOCKED_EXECUTION', reason='NATIVE_STOP_CONFIRMED' if within else 'PROTECTED_FILL_EXCEEDS_PLAN',
                parent_receipt_id=plan['receipt_id'], paper_account_id=account['id'], symbol=plan['symbol'],
                entry_order_id=entry['id'], stop_order_id=stop['id'], filled_qty=str(qty), filled_price=str(price),
                stop_price=str(floor), protection_tif=_persistent_exit_tif_for_qty('', float(qty)),
                native_ledger_sha256=digest(confirmed), strategy_promotion_allowed=False)
            item['phase'], item['receipt'] = 'PROTECTED', receipt
            _save(db, item)
            return receipt
    except Exception as error:
        return result('BLOCKED_EXECUTION' if dispatched or isinstance(error, (TimeoutError, ConnectionError, BlockingIOError)) else 'BLOCKED_DATA',
                      reason=str(error) or type(error).__name__)
