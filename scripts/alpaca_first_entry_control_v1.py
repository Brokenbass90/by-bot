#!/usr/bin/env python3
"""Thin one-session wiring of existing opening controller, assembler and runtime.

Prepare/ready/rehearsal never create a monetary permit or source reservation.
Entry requires an external exact human GO, the original HALT already cleared
by its separately scoped activation, and all original opening/runtime gates.
"""
import argparse,hashlib,importlib.util,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def load_spec(path):
    spec=json.loads(Path(path).read_bytes())
    app_root=Path(spec.get('app_root',ROOT)).absolute()
    if not app_root.is_dir() or app_root.is_symlink():raise ValueError('APP_ROOT_CUSTODY')
    if str(app_root) not in sys.path:sys.path.insert(0,str(app_root))
    for row in spec['static_files']:
        p=Path(row['path'])
        if (not p.is_file() or any(x.is_symlink() for x in (p,*p.parents))
            or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']):raise ValueError('STATIC_SOURCE_DRIFT:'+str(p))
    def module(name,path):
        s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
    module('research_lab.alpaca_dynamic_live_runtime_v1',spec['runtime_overlay'])
    module('research_lab.alpaca_open_dispatch_v2',spec['publisher_module'])
    module('research_lab.alpaca_first_entry_assembly_v1',spec['assembly_module'])
    return spec


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec',required=True)
    modes=p.add_mutually_exclusive_group(required=True)
    for name in ('prepare','ready','entry','maintenance','kill','rehearse'):modes.add_argument('--'+name,action='store_true')
    p.add_argument('--owner-go');a=p.parse_args(argv)
    try:
        spec=load_spec(a.spec)
        from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,run_once
        from research_lab.alpaca_dynamic_v1 import canonical,digest
        from research_lab.alpaca_open_dispatch_v2 import OpeningDispatcher,PreloadedSourcePublisher
        from research_lab.alpaca_first_entry_assembly_v1 import preview_snapshot,reserve_and_export
        from research_lab.alpaca_dynamic_first_intent_v1 import intent_permit
        from scripts.run_alpaca_dynamic_live_v1 import load_client
        policy=read_json(spec['policy']);binding=read_json(spec['binding']);intent=read_json(spec['intent'])
        if intent['intent_sha256']!=spec['intent_sha256']:raise ValueError('EXACT_FIRST_INTENT_REQUIRED')
        controller=OpeningDispatcher(spec['dispatch_state'],policy,intent['open_ms'],
            {str(i):r['path'] for i,r in enumerate(spec['static_files'])},spec['checks'],plan_store=binding['source_book'])
        if a.prepare:result=controller.prepare()
        elif a.ready:result=controller.ready()
        elif a.maintenance or a.kill:
            if not a.owner_go:raise ValueError('SEPARATE_EXACT_OWNER_GO_REQUIRED')
            b=read_json(str(Path(spec['session_dir'])/'binding.json'));intake=read_json(str(Path(spec['session_dir'])/'intake.json'))
            result=run_once(intake=intake,policy=policy,binding=b,client=load_client(spec['live_profile'],b,apply=True),
                now_ms=time.time_ns()//1000000,apply=True,owner_go_path=a.owner_go,maintenance=True,kill=a.kill,
                first_intent_path=spec['intent'])
        elif a.rehearse:
            # Uses retained recorded data in RAM; never authenticates future data.
            source=read_json(spec['replay_source']);now=source['observed_ms']
            result=preview_snapshot(policy,binding,intent,source,now)
            result={k:v for k,v in result.items() if k not in {'intake','binding'}}
            result.update(rehearsal=True,future_market_proven=False,broker_writes=0,source_book_writes=0)
        else:
            if not a.owner_go:raise ValueError('SEPARATE_EXACT_OWNER_GO_REQUIRED')
            # Static envelope check before any source reservation or application.
            go=read_json(a.owner_go)
            expected=dict(schema='ALPACA_DYNAMIC_FIRST_INTENT_OWNER_GO_V1',account_id=intent['account_id'],endpoint=intent['endpoint'],
                intent_sha256=intent['intent_sha256'],static_binding_sha256=intent['static_binding_sha256'],
                session=intent['session'],
                owner_go_text='GO ALPACA_DYNAMIC_FIRST_INTENT_V1 '+intent['intent_sha256'])
            if go!=expected:raise ValueError('FIRST_INTENT_SEPARATE_EXACT_OWNER_GO_REQUIRED')
            if Path(binding['halt_path']).exists():raise ValueError('ENTRY_HALTED')
            template=read_json(spec['template']);protocol=read_json(spec['protocol'])
            from research_lab.alpaca_dynamic_paper import earnings_check
            calendar=read_json(spec['calendar'])
            if not earnings_check([calendar['next_net_earnings']],intent['session'])['safe']:raise ValueError('EXISTING_EARNINGS_GATE_REJECT')
            template['gates'][intent['symbol']]['earnings']=True
            reader=load_client(spec['live_profile'],binding,apply=False)
            def quote(symbol):
                q=reader.latest_quote(symbol)
                return dict(quote=q,received_ms=time.time_ns()//1000000,structured_quote_sha256=digest(q))
            publisher=PreloadedSourcePublisher(policy,template,protocol,intent['symbol'],reader,quote)
            staged={}
            def reserve(snapshot):
                now=time.time_ns()//1000000
                preview=preview_snapshot(policy,binding,intent,snapshot,now)
                if preview['status']!='FIRST_ENTRY_PREVIEW_ONLY':return preview
                # Reuse intent_permit rather than turning a declaration into GO.
                intent_permit(go,intent,preview['binding'],preview['intake'],policy)
                reserve_and_export(preview,policy,binding,intent,snapshot,now,a.owner_go,spec['session_dir'])
                staged.update(preview)
                return preview['intake']['plan']
            def execute(plan):
                b=staged['binding'];intake=staged['intake']
                return run_once(intake=intake,policy=policy,binding=b,client=load_client(spec['live_profile'],b,apply=True),
                    now_ms=time.time_ns()//1000000,apply=True,owner_go_path=a.owner_go,first_intent_path=spec['intent'])
            result=controller.run(fresh=publisher.capture,reserve=reserve,execute=execute)
    except Exception as e:result=dict(status='BLOCKED_DATA',reason=str(e),orders_allowed=False)
    print(json.dumps(result));return 2 if result['status'].startswith('BLOCKED') else 0

if __name__=='__main__':raise SystemExit(main())
