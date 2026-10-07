"""Operator-only retirement of proven emergency MARKET exits while entry is HALTED.

Caller holds the existing account writer lock and supplies fresh authenticated
GET evidence. This module has no broker client, credentials or order path.
It preserves original stop/HWM and fill provenance in an immutable incident
archive before updating the two existing ledgers. It never clears HALT, invents
fee finality, creates a stop exit or changes the existing re-entry policy.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from scripts.equities_alpaca_paper_bridge import _atomic_write_json as _write


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _number(value, *, zero=False):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('invalid_number') from None
    if not n.is_finite() or n < 0 or (not zero and n == 0):
        raise ValueError('invalid_number')
    return n


def _ms(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('timestamp_requires_timezone')
        return int(dt.timestamp()*1000)
    except (TypeError, ValueError):
        raise ValueError('invalid_timestamp') from None


def _validate(source, evidence, halt, account_id, now_ms):
    if halt.get('halted') is not True or halt.get('account_id') != account_id:
        raise ValueError('entry_halt_required')
    account = evidence['account']
    if account['id'] != account_id or source['proof'].get('account_id') != account_id:
        raise ValueError('account_mismatch')
    observed = evidence['observed_ms']
    if type(observed) is not int or not 0 <= now_ms-observed <= 60000:
        raise ValueError('fresh_authenticated_snapshot_required')
    if evidence['positions'] != [] or evidence['open_orders'] != []:
        raise ValueError('global_flat_no_orders_required')
    for name in ('cash', 'accrued_fees', 'pending_reg_taf_fees'):
        _number(account[name], zero=True)
    proof, kill = source['proof'], source['kill_receipt']
    if proof.get('reason') != 'unprotected_after_reconcile' or kill.get('reason') != proof['reason']:
        raise ValueError('emergency_reason_mismatch')
    rows = proof['positions']
    symbols = [r['symbol'] for r in rows]
    if not rows or len(set(symbols)) != len(rows) or sorted(symbols) != sorted(kill['scope_symbols']):
        raise ValueError('emergency_scope_mismatch')
    if kill.get('status') != 'confirmed_flat' or kill.get('remaining_symbols') != []:
        raise ValueError('emergency_flat_receipt_required')
    close_rows = kill['order_results']
    close_ids = {r['symbol']:r['close_order_id'] for r in close_rows if r.get('close_order_id')}
    if len(close_ids) != len(symbols) or len(set(close_ids.values())) != len(symbols):
        raise ValueError('unique_emergency_close_ids_required')
    orders = evidence['orders']
    ids = {o['id']:o for o in orders}
    if len(ids) != len(orders):
        raise ValueError('duplicate_order_source')
    activities = evidence['activities']
    activity_ids = [a['id'] for a in activities]
    if len(set(activity_ids)) != len(activity_ids):
        raise ValueError('duplicate_activity_source')
    retired, gross = {}, Decimal(0)
    for row in rows:
        symbol = row['symbol']
        if symbol != symbol.upper():
            raise ValueError('invalid_symbol')
        record = source['state_before'][symbol]
        if record['account_id'] != account_id or record['entry_order_id'] != row['entry_order_id']:
            raise ValueError('owned_lineage_mismatch')
        qty, entry_price = _number(record['qty']), _number(record['entry_price'])
        if qty != _number(row['qty']) or entry_price != _number(row['avg_entry_price']):
            raise ValueError('owned_proof_quantity_mismatch')
        entry = ids[record['entry_order_id']]
        stop = ids[record['accepted_order_id']]
        exit_order = ids[close_ids[symbol]]
        if (entry['symbol'] != symbol or entry['side'] != 'buy'
            or entry['status'] not in {'filled','canceled','expired'}
            or _number(entry['filled_qty']) != qty
            or _number(entry['filled_avg_price']) != entry_price):
            raise ValueError('entry_fill_mismatch')
        if (stop['symbol'] != symbol or stop['side'] != 'sell' or stop['type'] != 'stop'
            or stop['status'] not in {'expired','canceled','rejected'}
            or _number(stop['filled_qty'], zero=True) != 0):
            raise ValueError('old_stop_must_be_terminal_unfilled')
        if (exit_order['symbol'] != symbol or exit_order['side'] != 'sell'
            or exit_order['type'] != 'market' or exit_order['status'] != 'filled'
            or _number(exit_order['qty']) != qty or _number(exit_order['filled_qty']) != qty):
            raise ValueError('full_emergency_market_fill_required')
        price = _number(exit_order['filled_avg_price'])
        exit_ms = _ms(exit_order['filled_at'])
        entry_ms = max(_ms(entry['filled_at']), _ms(record['lifecycle_first_seen_at_utc']))
        if not entry_ms <= exit_ms <= observed:
            raise ValueError('noncausal_emergency_exit')
        fills = [a for a in activities if a.get('activity_type') == 'FILL' and a.get('order_id') == exit_order['id']]
        if not fills:
            raise ValueError('exact_fill_activities_required')
        amount, filled = Decimal(0), Decimal(0)
        for fill in fills:
            if (fill['symbol'] != symbol or fill['side'] != 'sell'
                or not entry_ms <= _ms(fill['transaction_time']) <= observed):
                raise ValueError('fill_activity_mismatch')
            q = _number(fill['qty']); filled += q; amount += q*_number(fill['price'])
        if filled != qty or abs(amount/qty-price) > Decimal('.000001'):
            raise ValueError('fill_activities_quantity_price_mismatch')
        retired[exit_order['id']] = {'reason':'confirmed_emergency_market_exit',
            'account_id':account_id,'symbol':symbol,'entry_order_id':record['entry_order_id'],
            'exit_order':exit_order,'fill_activities':fills,'expired_stop':stop,
            'retired_lifecycle':record}
        gross += qty*(price-entry_price)
    return retired, gross


def reconcile(*, state_path: Path, reentry_path: Path, halt_path: Path,
              archive: Path, account_id: str, proof: dict, kill_receipt: dict,
              evidence: dict, now_ms: int, apply: bool = False) -> dict:
    """Caller must hold account writer lock. Restart is lookup/validation only."""
    state = json.loads(state_path.read_text())
    reentry = json.loads(reentry_path.read_text())
    halt = json.loads(halt_path.read_text())
    if not isinstance(state,dict) or not isinstance(reentry.get('symbols'),dict):
        raise ValueError('ledger_corrupt')
    source_path, receipt_path = archive/'source.json', archive/'receipt.json'
    if source_path.exists():
        source = json.loads(source_path.read_text())
        if source['proof'] != proof or source['kill_receipt'] != kill_receipt:
            raise ValueError('incident_source_mismatch')
    else:
        source = {'account_id':account_id,'state_before':state,'reentry_before':reentry,
            'halt_before':halt,'proof':proof,'kill_receipt':kill_receipt,'evidence':evidence}
    if source['account_id'] != account_id:
        raise ValueError('incident_account_mismatch')
    retired, gross = _validate(source,evidence,halt,account_id,now_ms)
    # Compare with the original source independently; never rewrite its broker truth.
    original_retired, original_gross = _validate(source,source['evidence'],source['halt_before'],
        account_id,source['evidence']['observed_ms'])
    if retired != original_retired or gross != original_gross:
        raise ValueError('terminal_broker_source_changed')
    after = copy.deepcopy(source['state_before'])
    for row in source['proof']['positions']:
        del after[row['symbol']]
    next_reentry = copy.deepcopy(source['reentry_before'])
    exits = next_reentry.setdefault('emergency_exits',{})
    if not isinstance(exits,dict):
        raise ValueError('emergency_ledger_corrupt')
    for identity,row in retired.items():
        if identity in exits and exits[identity] != row:
            raise ValueError('emergency_receipt_conflict')
        exits[identity] = row
    if state not in (source['state_before'],after) or reentry not in (source['reentry_before'],next_reentry):
        raise ValueError('runtime_ledger_changed')
    expected = {'status':'EMERGENCY_EXITS_RECONCILED_HALTED','broker_writes':0,
        'account_id':account_id,'source_sha256':_hash(source),
        'symbols':sorted(r['symbol'] for r in source['proof']['positions']),
        'exit_order_ids':sorted(retired),'gross_before_fees':str(gross),
        'fee_finality':'PENDING' if _number(source['evidence']['account']['pending_reg_taf_fees'],zero=True)>0 else 'NOT_PROVEN',
        'reentry_policy_changed':False,'entry_halt_preserved':True,
        'state_after_sha256':_hash(after),'reentry_after_sha256':_hash(next_reentry)}
    if receipt_path.exists() and json.loads(receipt_path.read_text()) != expected:
        raise ValueError('incident_archive_hash_mismatch')
    if not apply:
        return expected
    archive.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Persist the new directory's namespace before any ledger retirement.
    # mkdir(parents=True) may create several ancestors; sync each directory
    # and its parent rather than only the files' containing directory.
    for directory in [archive.absolute(), *archive.absolute().parents]:
        fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    if not source_path.exists():
        _write(source_path,source)
    if not receipt_path.exists():
        _write(receipt_path,expected)
    # Provenance first, then exit journal, then retirement; restart accepts only
    # either exact pre-state or exact post-state, never unknown mutations.
    if reentry != next_reentry:
        _write(reentry_path,next_reentry)
    if state != after:
        _write(state_path,after)
    return expected
