"""Reconcile proven LIVE fills into the existing Dynamic planner's slot lineage.

This is accounting of an existing fill, not an entry, exit, vacancy or permit.
Broker and dispatch journal remain financial truth. No PAPER fill method, HALT
change, order writer or strategy/rounding change is used. Default is preview.
"""
import json
import sqlite3
from pathlib import Path

from research_lab.alpaca_dynamic_v1 import canonical, digest, instant, positive, dec, DynamicBook
from research_lab.alpaca_dynamic_live_runtime_v1 import (
    LIVE, account_lock, safe_path, read_json, custody, order_contract,
)
from research_lab.alpaca_live_readiness_v1 import execution_identity_v1
from scripts import equities_alpaca_paper_bridge as native


def _read_db(path):
    return sqlite3.connect(safe_path(str(path),exists=True).as_uri()+'?mode=ro',uri=True)


def reconcile_live_lineage(binding, policy, client, *, now_ms, apply=False):
    now=instant(now_ms)
    if type(apply) is not bool or client.base_url!=LIVE:
        raise ValueError('LIVE_LINEAGE_SCOPE')
    # A real transport must be explicitly read-only. Test brokers have no flag.
    if getattr(client,'writes_enabled',False) is not False:
        raise ValueError('GET_ONLY_LINEAGE_CLIENT_REQUIRED')
    with account_lock(binding):
        if client.get_account()['id']!=binding['account_id'] or binding['account_id']!=policy['account_id']:
            raise ValueError('LIVE_LINEAGE_ACCOUNT')
        with _read_db(Path(binding['runtime'])/'live.sqlite') as db:
            items=[json.loads(r[0]) for r in db.execute('SELECT payload FROM intents')]
        with _read_db(binding['source_book']) as db:
            meta=dict(db.execute('SELECT key,value FROM meta'))
            if meta.get('policy')!=digest(policy) or meta.get('runtime_kind')!='LIVE_DYNAMIC_SEPARATE':
                raise ValueError('LIVE_LINEAGE_SOURCE_BOOK')
            plans={p['receipt_id']:p for p in DynamicBook.active_from_db(db)}
            parents={k:json.loads(v) for k,v in db.execute('SELECT entry,payload FROM slots')}
        if not items or len(items)>policy['max_positions']:
            raise ValueError('LIVE_LINEAGE_RUNTIME_CARDINALITY')
        ledger=read_json(binding['ledger_path'])
        positions=client.list_positions()
        if len({p['symbol'] for p in positions})!=len(positions):
            raise ValueError('LIVE_LINEAGE_DUPLICATE_POSITION')
        held={p['symbol']:p for p in positions}
        children=[];seen=set()
        for item in items:
            intake=item['intake'];plan=intake['plan'];symbol=plan['symbol']
            if (item['account']!=binding['account_id'] or item['phase']!='PROTECTED'
                or item.get('initial_full_protection_proven') is not True
                or plans.get(plan['receipt_id'])!=plan or symbol in seen):
                raise ValueError('LIVE_LINEAGE_UNCONFIRMED_RUNTIME')
            # Validate the original sources, payload and source-book membership.
            original_binding=dict(binding,intake_sha256=intake['intake_sha256'])
            if item['binding_sha256']!=digest(original_binding):
                raise ValueError('LIVE_LINEAGE_BINDING_CHANGED')
            custody(original_binding,intake,policy)
            current=client.get_order(item['entry']['id'])
            order_contract(current,intake['entry_payload'])
            execution_identity_v1(item['entry'],current)
            if current['status']!='filled' or positive(current['filled_qty'])!=positive(current['qty']):
                raise ValueError('LIVE_LINEAGE_ENTRY_NOT_FINAL')
            qty=positive(current['filled_qty']);price=positive(current['filled_avg_price'])
            stamp=native._parse_iso_utc(current['filled_at'])
            if stamp is None or not plan['prepared_ms']<=int(stamp.timestamp()*1000)<=now:
                raise ValueError('LIVE_LINEAGE_FILL_TIME')
            record=native._validated_existing_intended_lifecycle(ledger[symbol],binding['account_id'])
            initial=item['native_record'];floor=positive(initial['accepted_stop_floor'])
            if (record['entry_order_id']!=current['id'] or initial['entry_order_id']!=current['id']
                or record.get('dynamic_intake_sha256')!=intake['intake_sha256']
                or initial.get('dynamic_intake_sha256')!=intake['intake_sha256']
                or dec(record['qty'])!=qty or dec(record['entry_price'])!=price
                or dec(record['accepted_stop_floor'])<floor or not 0<floor<price):
                raise ValueError('LIVE_LINEAGE_NATIVE_CONFLICT')
            position=held.get(symbol)
            if (not position or position.get('side','long')!='long' or positive(position['qty'])!=qty
                or positive(position['avg_entry_price'])!=price):
                raise ValueError('LIVE_LINEAGE_POSITION_CONFLICT')
            parent=parents[plan['slot_entry_order_id']]
            notional=qty*price;risk=qty*(price-floor)
            if (qty>positive(plan['qty']) or notional>positive(plan['notional_limit_usd'])
                or notional>positive(parent['notional_cap']) or risk>positive(parent['risk_cap'])
                or floor<price-positive(plan['risk_distance'])):
                raise ValueError('LIVE_LINEAGE_SLOT_CAP')
            children.append(dict(entry_ms=int(stamp.timestamp()*1000),entry_order_id=current['id'],
                symbol=symbol,qty=str(qty),entry_price=str(price),notional_cap=str(notional),risk_cap=str(risk),
                parent_receipt_id=plan['receipt_id'],live_intake_sha256=intake['intake_sha256']))
            seen.add(symbol)
        if seen!=set(held):
            raise ValueError('LIVE_LINEAGE_FOREIGN_POSITION')
        inserted=0
        if apply:
            with sqlite3.connect(safe_path(binding['source_book'],exists=True)) as db:
                db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
                for child in children:
                    existing=[json.loads(v) for v, in db.execute('SELECT payload FROM slots')
                              if json.loads(v).get('parent_receipt_id')==child['parent_receipt_id']]
                    if existing and existing!=[child]:
                        raise ValueError('LIVE_LINEAGE_CHILD_CONFLICT')
                    if not existing:
                        db.execute('INSERT INTO slots VALUES (?,?)',(child['entry_order_id'],canonical(child).decode()))
                        inserted+=1
        return dict(schema='ALPACA_DYNAMIC_LIVE_LINEAGE_V1',
                    status='LIVE_LINEAGE_RECONCILED' if apply else 'LIVE_LINEAGE_PREVIEW',
                    observed_ms=now,children=children,inserted=inserted,
                    current_native_protection_certified=False,source_book_writes=inserted,
                    broker_writes=0,orders_allowed=False,money_authority=False)
