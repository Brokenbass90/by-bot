"""Next-entry ORDERS_OFF assembly using the unchanged weekly Dynamic planner.

Unlike the sealed first-canary adapter, an existing proven child may coexist.
All prospective book changes occur in a disposable SQLite copy. This module
cannot reserve a production plan, create a GO, clear HALT or send an order.
"""
import hashlib
import sqlite3
import tempfile
from pathlib import Path
from research_lab.alpaca_dynamic_v1 import DynamicBook, digest, positive, dec
from research_lab.alpaca_dynamic_live_intake_v1 import compile_intake, SCHEMA, COMPATIBILITY
from research_lab.alpaca_dynamic_live_runtime_v1 import safe_path
from research_lab.alpaca_first_entry_assembly_v1 import role_sources


def preview_next_snapshot(policy,binding,snapshot,now_ms,*,ranking=None):
    sources=role_sources(binding)
    source=safe_path(binding['source_book'],exists=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
        meta=dict(db.execute('SELECT key,value FROM meta'))
        if meta.get('policy')!=digest(policy) or meta.get('runtime_kind')!='LIVE_DYNAMIC_SEPARATE':
            raise ValueError('LIVE_SOURCE_BOOK_IDENTITY')
        with tempfile.TemporaryDirectory(prefix='alpaca-next-preview-') as folder:
            temp=Path(folder).resolve()/'book.sqlite'
            with sqlite3.connect(temp) as target:db.backup(target)
            book=DynamicBook(temp,policy)
            if ranking is not None:book.seal_ranking(ranking,policy['calendar_sessions'],now_ms)
            plan=book.propose(snapshot,policy['calendar_sessions'],now_ms)
    if plan['status']!='RESERVED_ORDERS_OFF':return {**plan,'source_book_writes':0,'broker_writes':0}
    symbol=plan['symbol'];quote=snapshot['quotes'][symbol]
    actual=snapshot['source_evidence']['account'];gate=snapshot['gates'][symbol]
    from scripts import alpaca_protective_exit_manager as manager
    scope=dict(schema=SCHEMA,endpoint=binding['endpoint'],account_id=policy['account_id'],
        policy_sha256=digest(policy),plan_sha256=digest(plan),source_plan_sha256=digest(plan),
        source_book_kind='LIVE_DYNAMIC_SEPARATE',compatibility=COMPATIBILITY,
        paper_lifecycle_status=sources['paper']['status'],paper_lifecycle_sha256=binding['sources']['paper']['sha256'],
        old_terminal_entry_order_id=sources['old_terminal']['entry_order_id'],old_terminal_qty=sources['old_terminal']['qty'],
        old_terminal_account_id=sources['old_terminal']['account_id'],old_terminal_evidence_kind=sources['old_terminal']['evidence_kind'],
        old_terminal_sha256=binding['sources']['old_terminal']['sha256'],original_shared_lock_sha256=binding['sources']['authority']['sha256'],
        native_manager_source_sha256=hashlib.sha256(Path(manager.__file__).read_bytes()).hexdigest(),cost_source_sha256=binding['sources']['cost']['sha256'],
        single_entry_owner_verified=sources['authority']['single_entry_owner_verified'],old_monthly_entries_off=sources['authority']['old_monthly_entries_off'],
        single_manager_verified=sources['authority']['single_manager_verified'],gross_before_usd=str(sum(abs(dec(p['market_value'])) for p in snapshot['positions'])),
        positions_before=len(snapshot['positions']),session_entries_before=0,cash_usd=actual['cash'],nonmarginable_cash_usd=actual['non_marginable_buying_power'],
        liability_reserve_usd=snapshot['liability_reserve_usd'],quote_cts_ms=quote['quote_ms'],observed_ms=snapshot['observed_ms'],
        tradable=quote['tradable'],fractionable=quote['fractionable'],earnings=gate['earnings'],concentration=gate['concentration'],
        reentry=symbol not in snapshot['blocked_symbols'],protection=gate['protection'],owner_go=False)
    intake=compile_intake(plan,policy,scope,now_ms)
    if intake['status']!='LIVE_INTAKE_PREPARED_ORDERS_OFF':return {**intake,'source_book_writes':0,'broker_writes':0}
    return dict(status='NEXT_ENTRY_PREVIEW_ONLY',intake=intake,binding={**binding,'intake_sha256':intake['intake_sha256']},
        broker_writes=0,source_book_writes=0,money_authority=False,orders_allowed=False,
        actual_source_plan_reserved=False,live_activation_ready=False)
