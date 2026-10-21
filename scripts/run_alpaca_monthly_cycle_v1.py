#!/usr/bin/env python3
"""One pinned Monthly entrypoint. Default source/preview remains ORDERS_OFF.

Explicit --dispatch additionally requires a separately signed standing scope,
exact operational configuration and the existing native custody/permit checks.
It never activates a service, clears HALT or adopts legacy NET.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager
from research_lab import alpaca_monthly_source_ops_v1 as ops
from scripts.run_alpaca_monthly_source_ops_v1 import load_calendar
from research_lab.alpaca_dynamic_v1 import digest

RUNNER_SCHEMA='ALPACA_MONTHLY_OWNED_RUNNER_V1'
RUNNER_CONFIG_FIELDS=('manager','source_captures','broker_root','profile',
    'native_binding','native','costs','notifications','legacy_handoff')


def runner_config_sha256(spec):
    # Authority references are separate: scope->config and spec->scope must not
    # create a circular hash. Every operational input is included here.
    return digest(dict(schema='ALPACA_MONTHLY_RUNNER_CONFIG_V1',
        **{k:spec.get(k) for k in RUNNER_CONFIG_FIELDS}))


def verify(path,pin,*,dispatch=False):
    p=ops.safe_path(path);raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('CYCLE_SPEC_PIN')
    spec=json.loads(raw)
    _verify_mode(spec,dispatch=dispatch)
    required={'research_lab/alpaca_monthly_cycle_v1.py','research_lab/alpaca_monthly_source_ops_v1.py',
        'research_lab/alpaca_monthly_binding_v1.py','research_lab/alpaca_monthly_native_binding_v1.py',
        'scripts/run_alpaca_monthly_cycle_v1.py'}
    if not required.issubset(spec['files']):raise ValueError('CYCLE_SOURCE_CLOSURE_REQUIRED')
    for name,pin_ in spec['files'].items():
        p=ops.safe_path(ROOT/name)
        if not p.is_relative_to(ROOT) or ops.sha(p)!=pin_:raise ValueError('CYCLE_SOURCE_PIN:'+name)
    return spec


def _verify_mode(spec,*,dispatch):
    schema=RUNNER_SCHEMA if dispatch else 'ALPACA_MONTHLY_CYCLE_DISABLED_V1'
    if (spec.get('schema')!=schema or any(spec.get(k) is not dispatch
        for k in ('enabled','orders_allowed','money_authority'))):
        raise ValueError('CYCLE_EXPLICIT_STANDING_DISPATCH_REQUIRED' if dispatch else 'CYCLE_ORDERS_OFF_SPEC_REQUIRED')


def pinned_input(row):
    p=ops.safe_path(row['path'])
    if ops.sha(p)!=row['sha256']:raise ValueError('RUNNER_INPUT_PIN')
    return p


def runner_authority(spec):
    from research_lab.alpaca_monthly_native_binding_v1 import STANDING_SCHEMA,standing_source_pins
    _verify_mode(spec,dispatch=True)
    if spec['files']!=standing_source_pins():raise ValueError('RUNNER_EXACT_SOURCE_CLOSURE')
    auth=spec['authority'];raw=ops.safe_path(auth['scope_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=auth['scope_sha256']:raise ValueError('RUNNER_OWNER_SCOPE_PIN')
    scope=json.loads(raw)
    from research_lab.alpaca_monthly_handoff_v1 import validate_policy
    validate_policy(spec.get('legacy_handoff'))
    if scope.get('legacy_handoff')!=spec['legacy_handoff']:raise ValueError('RUNNER_HANDOFF_OWNER_POLICY_CONFLICT')
    if scope.get('legacy_cost_transition')!=(spec.get('costs') or {}).get('legacy_transition'):
        raise ValueError('RUNNER_LEGACY_COST_OWNER_POLICY_CONFLICT')
    if (scope.get('legacy_cost_transition') is not None and
        scope.get('legacy_pending_cost_inputs')!={k:spec['costs'][k] for k in ('after','protocol','calendar','assets')}):
        raise ValueError('RUNNER_LEGACY_PENDING_SOURCE_POLICY_CONFLICT')
    if (scope.get('schema')!=STANDING_SCHEMA
        or scope.get('runner_config_sha256')!=runner_config_sha256(spec)):
        raise ValueError('RUNNER_SEPARATE_CONFIG_AUTHORITY_REQUIRED')
    go=json.loads(ops.safe_path(auth['owner_go_path']).read_bytes())
    if go!=dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=auth['scope_sha256'],
        owner_go_text='GO ALPACA_MONTHLY_STANDING '+auth['scope_sha256']):
        raise ValueError('RUNNER_SEPARATE_OWNER_GO_REQUIRED')
    return scope


@contextmanager
def monthly_environment(spec):
    binding=pinned_input(spec['native_binding'])
    values=dict(ALPACA_INTENDED_PAPER='0',ALPACA_INTENDED_LIVE='1',
        ALPACA_INTENDED_LIVE_BINDING_PATH=str(binding),ALPACA_INTENDED_LIVE_ACK='INTENDED_LIVE_CANARY',
        ALPACA_LIVE_ACCOUNT_ROLE='monthly_v38',ALPACA_LIVE_CONFIRM='MONTHLY_V38_LIVE',
        ALPACA_LIVE_MAX_CAPITAL_USD=str(spec['manager']['capital']))
    saved={k:os.environ.get(k) for k in values};os.environ.update(values)
    try:yield
    finally:
        for k,v in saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


def production_client(spec):
    from research_lab.alpaca_monthly_binding_v1 import CONTRACT
    from scripts.run_alpaca_dynamic_live_v1 import load_client
    profile=pinned_input(spec['profile'])
    return load_client(profile,dict(broker_root=spec['broker_root'],
        lock_path=spec['manager']['account_lock_path']),apply=True,order_contract=CONTRACT['schema'])


def dispatch_cycle(spec,*,client_factory=None,now_ms=None,bundle_loader=None):
    """Actual production path; injectable I/O only for isolated acceptance tests."""
    from research_lab.alpaca_monthly_binding_v1 import CONTRACT
    from research_lab.alpaca_monthly_native_binding_v1 import STANDING_SCHEMA
    from research_lab.alpaca_monthly_cost_source_v1 import capture_and_produce_cost_sources
    from research_lab.alpaca_dynamic_live_runtime_v1 import LIVE
    runner_authority(spec)  # before profile loading or constructing owned state
    native_args=spec['native']
    if set(native_args)!={'liability_reserve_usd','pending_fee_admission'}:
        raise ValueError('RUNNER_NATIVE_OPTIONS')
    auth=spec['authority'];start=time.monotonic()
    at=time.time_ns()//1000000 if now_ms is None else now_ms
    clock=lambda:at+int((time.monotonic()-start)*1000)
    load=bundle_loader or latest_bundle
    with monthly_environment(spec):
        m=MonthlyManager(**spec['manager'])
        if not (m.root/'book/monthly-orders-off.sqlite').is_file():
            m.source(load(spec['source_captures'],clock()),now_ms=clock())
        options=dict(live_scope_path=auth['scope_path'],live_scope_sha256=auth['scope_sha256'],
            owner_go_path=auth['owner_go_path'],**native_args)
        # Existing complete custody check is local-only. No transport/GET is
        # created until account/book/lock/source/GO identity has been accepted.
        probe=m.native(SimpleNamespace(base_url=LIVE,order_contract=CONTRACT['schema']),base_url=LIVE,**options)
        if probe._live_custody()['schema']!=STANDING_SCHEMA:raise ValueError('RUNNER_STANDING_ONLY')
        client=(client_factory or production_client)(spec)
        bound=m.native(client,base_url=LIVE,**options)
        def costs(exits):
            config=spec['costs']
            if not exits and config.get('legacy_transition') is None:return {}
            paths={name+'_path':pinned_input(config[name]) for name in ('protocol','calendar','assets')}
            return capture_and_produce_cost_sources(bound,after=config['after'],
                allow_pending=bound.pending_fee_admission,legacy_transition=config.get('legacy_transition'),**paths)
        out=m.tick(bound,now_ms=clock(),apply=True,source_loader=lambda:load(spec['source_captures'],clock()),
            cost_sources=costs,notifications=spec.get('notifications'))
        out['production_entrypoint']=True
        out['runner_config_sha256']=runner_config_sha256(spec)
        # Do not invent zero writes: applying stages use the existing durable
        # dispatch journal as the authoritative execution count/source.
        out['broker_write_count_source']='EXISTING_OWNED_DISPATCH_JOURNAL'
        return out


def latest_bundle(root,now):
    root=ops.safe_path(root)
    folders=[p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and p.name.isdigit()]
    if not folders:raise ValueError('CYCLE_NO_COMPLETED_CAPTURE')
    cache=max(folders,key=lambda p:int(p.name))
    cap=json.loads(ops.safe_path(cache/'capture.json').read_bytes())
    calendar=load_calendar(json.loads(ops.safe_path(cache/'calendar.json').read_bytes()),now)
    return ops.compile_source(cache,cap,calendar,now_ms=now)


def main(argv=None,*,client_factory=None,now_ms=None,bundle_loader=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',required=True);p.add_argument('--spec-sha256',required=True)
    p.add_argument('--source',action='store_true');p.add_argument('--verify-only',action='store_true')
    p.add_argument('--dispatch',action='store_true',help='requires a new exact standing/config authority; not installed or activated by this flag')
    a=p.parse_args(argv);spec=None;dispatch_started=False;trusted_notifications=None
    try:
        if a.dispatch and a.source:raise ValueError('RUNNER_SOURCE_AND_DISPATCH_EXCLUSIVE')
        spec=verify(a.spec,a.spec_sha256,dispatch=a.dispatch);now=time.time_ns()//1000000 if now_ms is None else now_ms
        if a.verify_only:out=dict(status='MONTHLY_CYCLE_PACKAGE_VERIFIED_ORDERS_OFF',source_files=len(spec['files']))
        elif a.dispatch:
            runner_authority(spec)
            trusted_notifications=spec.get('notifications')
            dispatch_started=True
            out=dispatch_cycle(spec,client_factory=client_factory,now_ms=now,bundle_loader=bundle_loader)
        else:
            trusted_notifications=spec.get('notifications')
            m=MonthlyManager(**spec['manager'])
            out=m.source(latest_bundle(spec['source_captures'],now),now_ms=now) if a.source else m.preview(now_ms=now)
        if not a.dispatch or a.verify_only:out={**out,'broker_writes':0,'orders_allowed':False,'money_authority':False}
        if not a.dispatch and not a.verify_only and spec.get('notifications'):
            from research_lab.alpaca_monthly_notifications_v1 import event_delivery
            out['notification']=event_delivery(spec['notifications'],now_ms=now,component='source' if a.source else 'manager')
    except (ValueError,KeyError,TypeError,OSError) as exc:
        out=dict(status='MONTHLY_CYCLE_BLOCKED',reason=str(exc),broker_writes=None if dispatch_started else 0,
            orders_allowed=False,money_authority=False)
        if dispatch_started:out['broker_write_count_source']='EXISTING_OWNED_DISPATCH_JOURNAL'
        if trusted_notifications:
            from research_lab.alpaca_monthly_notifications_v1 import event_delivery
            try:out['notification']=event_delivery(trusted_notifications,now_ms=time.time_ns()//1000000,
                failure_code='MONTHLY_CYCLE_'+type(exc).__name__.upper(),component='source' if a.source else 'manager')
            except Exception as notify_error:out['notification']=dict(status='DELIVERY_UNKNOWN_NO_RETRY',error_type=type(notify_error).__name__)
    print(json.dumps(out,sort_keys=True,allow_nan=False))
    return 2 if out['status']=='MONTHLY_CYCLE_BLOCKED' or out.get('issues') else 0


if __name__=='__main__':raise SystemExit(main())
