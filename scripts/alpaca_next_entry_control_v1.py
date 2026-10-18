#!/usr/bin/env python3
"""Bounded next-entry wiring; default operation is a read-only preflight.

The human personally arms a single specified session. Preparation does not
create that arm or clear HALT. Existing weekly selector, source book, opening
controller, exact-intake runtime, account lock and native management are reused.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def load_spec(path,pin):
    from research_lab.alpaca_dynamic_live_runtime_v1 import safe_path,read_json
    p=safe_path(str(path),exists=True)
    if hashlib.sha256(p.read_bytes()).hexdigest()!=pin:raise ValueError('NEXT_CONTROL_SPEC_PIN')
    spec=read_json(p)
    if spec['schema']!='ALPACA_NEXT_SESSION_CONTROL_V1':raise ValueError('NEXT_CONTROL_SCHEMA')
    for row in spec['static_files']:
        target=safe_path(row['path'],exists=True)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('NEXT_CONTROL_SOURCE_PIN')
    return spec


def verify_selected_units(spec,spec_pin):
    if not spec.get('selected_unit_pins'):raise ValueError('NEXT_SELECTED_UNITS_UNBOUND')
    for row in spec['selected_unit_pins']:
        if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('NEXT_SELECTED_UNIT_DRIFT')
    for row in spec.get('selected_unit_templates',[]):
        template=Path(row['template']).read_bytes()
        if hashlib.sha256(template).hexdigest()!=row['template_sha256']:
            raise ValueError('NEXT_SELECTED_UNIT_TEMPLATE_DRIFT')
        if Path(row['path']).read_bytes()!=template.replace(b'<CONTROL_SPEC_SHA256>',spec_pin.encode()):
            raise ValueError('NEXT_SELECTED_UNIT_DRIFT')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',required=True);p.add_argument('--spec-sha256',required=True)
    modes=p.add_mutually_exclusive_group()
    for mode in ('preflight','prepare','ready','entry','maintenance'):modes.add_argument('--'+mode,action='store_true')
    args=p.parse_args(argv)
    try:
        spec=load_spec(args.spec,args.spec_sha256)
        if args.prepare or args.ready or args.entry or args.maintenance:
            verify_selected_units(spec,args.spec_sha256)
        from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,run_once,account_lock,safe_path
        from research_lab.alpaca_dynamic_v1 import canonical,digest,DynamicBook,session_at
        from research_lab.alpaca_dynamic_live_lineage_v1 import reconcile_live_lineage
        from research_lab.alpaca_dynamic_portfolio_admission_v1 import check_owned_portfolio
        from research_lab.alpaca_next_entry_assembly_v1 import preview_next_snapshot
        from research_lab.alpaca_next_entry_scope_v1 import check_scope,check_preview,validate_personal_arm,compatibility_go
        from research_lab.alpaca_owned_open_dispatch_v1 import OwnedOpeningDispatcher
        from research_lab.alpaca_open_dispatch_v2 import PreloadedSourcePublisher
        from research_lab.alpaca_live_readiness_v1 import write_new
        from scripts.run_alpaca_dynamic_live_v1 import load_client
        policy=read_json(spec['policy']);binding=read_json(spec['binding']);scope=read_json(spec['scope'])
        ranking=read_json(spec['ranking']);check_scope(scope,policy)
        if digest(ranking)!=scope['ranking_sha256']:raise ValueError('NEXT_RANKING_SCOPE_PIN')
        session=next(r for r in policy['calendar_sessions'] if r['session']==scope['session'])
        controller=OwnedOpeningDispatcher(spec['dispatch_state'],policy,session['open_ms'],
            {str(i):r['path'] for i,r in enumerate(spec['static_files'])},spec['checks'],
            plan_store=binding['source_book'],resolved_source_plans=spec['resolved_source_plans'])
        folder=Path(spec['session_dir'])
        if args.prepare:out=controller.prepare()
        elif args.ready:out=controller.ready()
        elif args.maintenance:
            if not (folder/'intake.json').exists():out=dict(status='NO_NEXT_OWNED_INTENT',broker_writes=0)
            else:
                actual=read_json(folder/'binding.json');intake=read_json(folder/'intake.json')
                check_preview(scope,dict(status='NEXT_ENTRY_PREVIEW_ONLY',binding=actual,intake=intake),policy)
                validate_personal_arm(scope,read_json(spec['personal_arm']))
                out=run_once(intake=intake,policy=policy,binding=actual,client=load_client(spec['live_profile'],actual,apply=True),
                    now_ms=time.time_ns()//1000000,apply=True,owner_go_path=folder/'owner-compatibility-go.json',maintenance=True)
        else:
            if args.entry and controller._read('terminal.json'):
                print(json.dumps(controller._read('terminal.json'),sort_keys=True));return 0 if not controller._read('terminal.json')['status'].startswith('BLOCKED') else 2
            reader=load_client(spec['live_profile'],binding,apply=False)
            # Reconcile the already existing original LIVE child independently.
            old_binding=read_json(binding['portfolio_bindings'][0]['path'])
            lineage=reconcile_live_lineage(old_binding,policy,reader,now_ms=time.time_ns()//1000000)
            known=spec['resolved_source_plans']
            if (len(lineage['children'])!=len(known) or any(not any(
                child['entry_order_id']==r['child_entry_order_id'] and child['live_intake_sha256']==r['live_intake_sha256']
                for r in known) for child in lineage['children'])):raise ValueError('NEXT_EXISTING_LIVE_LINEAGE_CHANGED')
            if not args.entry:
                account=reader.get_account();positions=reader.list_positions();orders=reader.list_orders(status='open',limit=500)
                if account['id']!=policy['account_id'] or len(orders)>=500:raise ValueError('NEXT_ACCOUNT_OR_ORDER_SCOPE')
                out=dict(status='NEXT_SESSION_PREFLIGHT_ORDERS_OFF',observed_ms=time.time_ns()//1000000,
                    target_session=scope['session'],open_ms=session['open_ms'],end_ms=session['open_ms']+300000,
                    symbol=scope['symbol'],max_notional_usd=scope['max_notional_usd'],max_risk_usd=scope['max_risk_usd'],
                    held_symbols=sorted(p['symbol'] for p in positions),open_order_count=len(orders),
                    source_lineage_status=lineage['status'],halt_present=Path(binding['halt_path']).exists(),
                    personal_arm_present=Path(spec['personal_arm']).exists(),
                    actual_opening_admission_proven=False,broker_writes=0,source_book_writes=0)
            else:
                arm=read_json(spec['personal_arm']);validate_personal_arm(scope,arm)
                if safe_path(binding['halt_path']).exists():raise ValueError('ENTRY_HALTED')
                template=read_json(spec['template']);protocol=read_json(spec['protocol']);calendar=read_json(spec['calendar'])
                from research_lab.alpaca_dynamic_paper import earnings_check
                if not earnings_check(calendar['earnings_dates'],scope['session'])['safe']:raise ValueError('NEXT_EARNINGS_GATE')
                template['gates'][scope['symbol']]['earnings']=True
                def quote(symbol):
                    row=reader.latest_quote(symbol)
                    return dict(quote=row,received_ms=time.time_ns()//1000000,structured_quote_sha256=digest(row))
                publisher=PreloadedSourcePublisher(policy,template,protocol,scope['symbol'],reader,quote)
                staged={}
                def fresh():
                    # This blocks a new buy unless NET was re-armed successfully
                    # by the original manager in THIS actual regular session.
                    with account_lock(binding):
                        with sqlite3.connect(safe_path(str(Path(binding['runtime'])/'live.sqlite'),exists=True).as_uri()+'?mode=ro',uri=True) as db:
                            check_owned_portfolio(db,binding,policy,reader,positions=reader.list_positions(),
                                orders=reader.list_orders(status='open',limit=500),target_symbol=scope['symbol'],
                                observed_ms=time.time_ns()//1000000)
                    return publisher.capture()
                def reserve(snapshot):
                    now=time.time_ns()//1000000
                    preview=preview_next_snapshot(policy,binding,snapshot,now,ranking=ranking)
                    check_preview(scope,preview,policy)
                    go=compatibility_go(scope,preview,policy,arm)
                    with account_lock(binding):
                        if safe_path(binding['halt_path']).exists():raise ValueError('ENTRY_HALTED')
                        book=DynamicBook(binding['source_book'],policy)
                        book.seal_ranking(ranking,policy['calendar_sessions'],now)
                        actual=book.propose(snapshot,policy['calendar_sessions'],now)
                        if actual!=preview['intake']['plan']:raise ValueError('NEXT_ACTUAL_SOURCE_PLAN_CONFLICT')
                        folder.mkdir(parents=True,mode=0o700,exist_ok=True)
                        for name,value in [('intake.json',preview['intake']),('binding.json',preview['binding']),
                                           ('owner-compatibility-go.json',go),('go-derivation.json',dict(
                                               schema='ALPACA_NEXT_GO_DERIVATION_V1',scope_sha256=scope['scope_sha256'],
                                               personal_arm_sha256=digest(arm),owner_approval_text_sha256=hashlib.sha256(scope['owner_approval_text'].encode()).hexdigest(),
                                               generated_compatibility_token_is_not_verbatim_human_text=True))]:
                            write_new(folder/name,canonical(value))
                    staged.update(preview)
                    return actual
                def execute(plan):
                    actual=staged['binding'];intake=staged['intake']
                    return run_once(intake=intake,policy=policy,binding=actual,client=load_client(spec['live_profile'],actual,apply=True),
                        now_ms=time.time_ns()//1000000,apply=True,owner_go_path=folder/'owner-compatibility-go.json')
                out=controller.run(fresh=fresh,reserve=reserve,execute=execute)
    except Exception as exc:
        out=dict(status='BLOCKED_DATA',reason=str(exc) or type(exc).__name__,broker_writes=0,
                 orders_allowed=False,no_blind_retry=True)
    print(json.dumps(out,sort_keys=True));return 2 if out['status'].startswith('BLOCKED') else 0


if __name__=='__main__':raise SystemExit(main())
