"""One-intent source-plan/intake glue. Preview is memory-only, never a sender.

Only explicit --reserve plus the separately supplied exact owner file can write
an opening source plan. Broker transport is always GET-only in this module.
HALT, services, native ledger and monetary permits are never modified here.
"""
import argparse,hashlib,json,sqlite3,time
from pathlib import Path
from research_lab.alpaca_dynamic_v1 import DynamicBook,canonical,digest,positive
from research_lab.alpaca_dynamic_live_intake_v1 import compile_intake,SCHEMA,COMPATIBILITY
from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,safe_path,custody,account_lock
from research_lab.alpaca_dynamic_first_intent_v1 import check_first_intent,intent_permit


def role_sources(binding):
    rows={}
    for name,pin in binding['sources'].items():
        path=safe_path(pin['path'],exists=True)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('ASSEMBLY_SOURCE_DRIFT:'+name)
        rows[name]=read_json(str(path))
    return rows


def preview_existing(intake,policy,binding,now_ms):
    try:
        custody(binding,intake,policy)
        result=compile_intake(intake['plan'],policy,intake['scope'],now_ms)
        if result['status']!='LIVE_INTAKE_PREPARED_ORDERS_OFF':return result
        return dict(status='FIRST_ENTRY_NO_SEND_READY',broker_writes=0,source_book_writes=0,money_authority=False)
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError) as e:
        return dict(status='BLOCKED_DATA',reason=str(e),broker_writes=0,source_book_writes=0)


def _memory_plan(book_path,policy,snapshot,now_ms):
    memory=sqlite3.connect(':memory:')
    try:
        with sqlite3.connect(safe_path(book_path,exists=True).as_uri()+'?mode=ro',uri=True) as db:
            db.backup(memory)
        meta=dict(memory.execute('SELECT key,value FROM meta'))
        if meta.get('policy')!=digest(policy) or meta.get('runtime_kind')!='LIVE_DYNAMIC_SEPARATE':raise ValueError('LIVE_SOURCE_BOOK_IDENTITY')
        if DynamicBook.active_from_db(memory):raise ValueError('FIRST_INTENT_ALREADY_RESERVED')
        book=object.__new__(DynamicBook);book.policy=policy;book.policy_hash=digest(policy)
        return book._propose(memory,snapshot,policy['calendar_sessions'],now_ms)
    finally:memory.close()


def preview_snapshot(policy,binding,intent,snapshot,now_ms):
    """Exercise unchanged planner in an in-memory backup; no real reservation."""
    sources=role_sources(binding)
    symbol=intent['symbol'];quote=snapshot['quotes'][symbol]
    if positive(quote['ask'])>positive(intent['max_limit_price']):raise ValueError('FIRST_INTENT_PRICE_CAP')
    plan=_memory_plan(binding['source_book'],policy,snapshot,now_ms)
    if plan['status']!='RESERVED_ORDERS_OFF':return plan
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
        single_manager_verified=sources['authority']['single_manager_verified'],gross_before_usd=str(sum(abs(__import__('decimal').Decimal(p['market_value'])) for p in snapshot['positions'])),
        positions_before=len(snapshot['positions']),session_entries_before=0,cash_usd=actual['cash'],nonmarginable_cash_usd=actual['non_marginable_buying_power'],
        liability_reserve_usd=snapshot['liability_reserve_usd'],quote_cts_ms=quote['quote_ms'],observed_ms=snapshot['observed_ms'],
        tradable=quote['tradable'],fractionable=quote['fractionable'],earnings=gate['earnings'],concentration=gate['concentration'],
        reentry=symbol not in snapshot['blocked_symbols'],protection=gate['protection'],owner_go=False)
    intake=compile_intake(plan,policy,scope,now_ms)
    if intake['status']!='LIVE_INTAKE_PREPARED_ORDERS_OFF':return intake
    final_binding={**binding,'intake_sha256':intake['intake_sha256']}
    check_first_intent(intent,final_binding,intake,policy)
    return dict(status='FIRST_ENTRY_PREVIEW_ONLY',intake=intake,binding=final_binding,
        broker_writes=0,source_book_writes=0,money_authority=False,actual_source_plan_reserved=False)


def reserve_and_export(preview,policy,binding,intent,snapshot,now_ms,go_path,output_dir):
    if preview['status']!='FIRST_ENTRY_PREVIEW_ONLY':raise ValueError('PREVIEW_NOT_READY')
    intent_permit(read_json(str(go_path)),intent,preview['binding'],preview['intake'],policy)
    # Existing runtime HALT condition is checked before consuming a source slot.
    if safe_path(binding['halt_path']).exists():raise ValueError('ENTRY_HALTED')
    with account_lock(binding):
        actual=DynamicBook(binding['source_book'],policy).propose(snapshot,policy['calendar_sessions'],now_ms)
        if actual!=preview['intake']['plan']:raise ValueError('FROZEN_SOURCE_PLAN_CONFLICT_NO_SEND')
        folder=Path(output_dir);folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        from research_lab.alpaca_live_readiness_v1 import write_new
        write_new(folder/'intake.json',canonical(preview['intake']));write_new(folder/'binding.json',canonical(preview['binding']))
    return dict(status='FIRST_ENTRY_SOURCE_PLAN_EXPORTED',broker_writes=0,monetary_permit_created=False,
        source_plan_reserved=True,intake_sha256=preview['intake']['intake_sha256'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',required=True);p.add_argument('--reserve',action='store_true');p.add_argument('--owner-go');p.add_argument('--output-dir')
    a=p.parse_args(argv)
    try:
        spec=read_json(a.spec)
        for row in spec['static_files']:
            if hashlib.sha256(safe_path(row['path'],exists=True).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('STATIC_FILE_DRIFT')
        policy=read_json(spec['policy']);binding=read_json(spec['binding']);intent=read_json(spec['intent'])
        if a.reserve and (not a.owner_go or not a.output_dir):raise ValueError('SEPARATE_OWNER_GO_AND_EXCLUSIVE_OUTPUT_REQUIRED')
        from scripts.run_alpaca_dynamic_live_v1 import load_client
        from research_lab.alpaca_open_dispatch_v2 import PreloadedSourcePublisher
        from research_lab.alpaca_dynamic_paper import earnings_check
        template=read_json(spec['template']);protocol=read_json(spec['protocol']);calendar=read_json(spec['calendar'])
        if not earnings_check([calendar['next_net_earnings']],intent['session'])['safe']:raise ValueError('EXISTING_EARNINGS_GATE_REJECT')
        template['gates'][intent['symbol']]['earnings']=True
        client=load_client(spec['live_profile'],binding,apply=False)
        def quote(symbol):
            q=client.latest_quote(symbol)
            return dict(quote=q,received_ms=time.time_ns()//1000000,raw_sha256=digest(q))
        publisher=PreloadedSourcePublisher(policy,template,protocol,intent['symbol'],client,quote)
        snapshot=publisher.capture();now=time.time_ns()//1000000
        result=preview_snapshot(policy,binding,intent,snapshot,now)
        if a.reserve:result=reserve_and_export(result,policy,binding,intent,snapshot,now,a.owner_go,a.output_dir)
        else:result={k:v for k,v in result.items() if k not in {'binding','intake'}}
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError,StopIteration) as e:result=dict(status='BLOCKED_DATA',reason=str(e),broker_writes=0,source_book_writes=0)
    print(json.dumps(result));return 2 if result['status'].startswith('BLOCKED') else 0
