"""Future ONE GET-only observation and offline closure of the existing lifecycle.

Run only from the pinned inert kit. No polling, order client, owner permit,
reservation, service/config mutation or automatic retry. Never run on Oct13.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import sys
import time
from datetime import datetime,timezone

BASE=Path('/opt/bybot-research/alpaca-dynamic-live-20261013')
KIT=BASE/'control/fee-to-live-v1'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod


def main(expected_kit_pin,*,verify_only=False):
    sys.path.insert(0,str(BASE/'app'))
    from research_lab.alpaca_dynamic_v1 import canonical,digest,dec
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,safe_path
    from research_lab import alpaca_live_readiness_v1 as readiness
    kit=read_json(str(KIT/'kit.json'))
    if kit.get('kit_sha256')!=expected_kit_pin or expected_kit_pin!=digest({k:v for k,v in kit.items() if k!='kit_sha256'}):
        raise ValueError('EXTERNAL_KIT_PIN_CONFLICT')
    def check(rows):
        for row in rows:
            if hashlib.sha256(safe_path(row['path'],exists=True).read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError('CLOSURE_STATIC_SOURCE_DRIFT')
    check(kit['files'])
    manifest=read_json(str(KIT/'manifest.json'));check(manifest['code_files']);check(manifest['inputs'].values())
    deployment=read_json(manifest['inputs']['deployment']['path'])
    readiness._physical_sources(deployment['source_files'],deployment['source_manifest_sha256'])
    if verify_only:
        print(json.dumps(dict(status='FEE_TO_LIVE_STATIC_PINS_VERIFIED_NOT_OBSERVED',kit_sha256=expected_kit_pin,
            package_sha256=deployment['package_sha256'],files=len(kit['files']),broker_queries=0,orders_allowed=False)))
        return 0
    module('research_lab.alpaca_orders_off_handoff_v2',BASE/'control/orders_off_helper_v2.py')
    closure=module('alpaca_fee_closure_control',KIT/'closure.py')
    output=closure.unused_output(manifest['output_dir'])
    session=read_json(str(KIT/'publisher-session.json'));policy=read_json(manifest['inputs']['policy']['path'])
    today=datetime.now(timezone.utc).date().isoformat()
    now=time.time_ns()//1000000
    opening=next(r['open_ms'] for r in policy['calendar_sessions'] if r['session']==session['session'])
    if today!=session['session'] or now>=opening:raise ValueError('EXACT_PREOPEN_SESSION_REQUIRED')
    def captured_query(filename):
        stream=io.StringIO()
        code=safe_path(str(KIT/filename),exists=True).read_bytes()
        with contextlib.redirect_stdout(stream):exec(compile(code,filename,'exec'),{'__name__':'one_get_readback'})
        response=json.loads(stream.getvalue())
        return dict(query_sha256=hashlib.sha256(code).hexdigest(),response=response)
    # First only the same fully closed NET PAPER lifecycle. At most one fee observation.
    terminal=captured_query('finality-query.py')
    terminal_path=KIT/'terminal-capture.json';readiness.write_new(terminal_path,canonical(terminal))
    paths={n:r['path'] for n,r in manifest['inputs'].items()}
    try:
        fee=readiness.derive_paper_posted_cost_closure_v2(cash_before_path=paths['cash_before'],initial_path=paths['initial'],
            rearm_path=paths['rearm'],terminal_path=str(terminal_path),protocol_path=paths['protocol'],now_ms=time.time_ns()//1000000)
    except (ValueError,KeyError,TypeError,OSError):
        # The original strict checker creates the exact terminal BLOCKED below.
        fee=None
    preparation_path=KIT/'live-preparation.json'
    if fee is not None:
        try:
            fresh_authority=captured_query('authority-query.py')
            readiness.write_new(KIT/'fresh-authority-capture.json',canonical(fresh_authority))
            old=read_json(str(KIT/'authority-capture.json'))['response'];fresh=fresh_authority['response']
            for key in ('profiles','writers','cron','units'):
                if fresh[key]!=old[key]:raise ValueError('ACTUAL_AUTHORITY_SOURCE_DRIFT:'+key)
            if fresh['original_live_lock']!=old['original_live_lock'] or any(p['send_orders'] or p['apply'] for p in fresh['processes']):
                raise ValueError('EXCLUSIVE_DISABLED_AUTHORITY_CONFLICT')
            for name in ('bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service'):
                if fresh['services'][name]!=old['services'][name]:raise ValueError('UNRELATED_PRODUCTION_STATE_CHANGED')
            from dotenv import dotenv_values
            from research_lab.alpaca_dynamic_live_runtime_v1 import DynamicLiveClient
            from research_lab.alpaca_open_dispatch_v2 import PreloadedSourcePublisher
            from research_lab.alpaca_dynamic_paper import earnings_check
            template=read_json(str(KIT/'publisher-template.json'));protocol=read_json(str(KIT/'publisher-protocol.json'))
            calendar=read_json(str(KIT/'publisher-source_binding.json'))
            if not earnings_check([calendar['next_net_earnings']],session['session'])['safe']:
                raise ValueError('EXISTING_EARNINGS_GATE_REJECT')
            template['gates'][session['ticker']]['earnings']=True
            env=dotenv_values('/root/by-bot/configs/alpaca_live_v38.env',interpolate=False)
            if env['ALPACA_BASE_URL']!='https://api.alpaca.markets' or env.get('ALPACA_SEND_ORDERS')!='0':
                raise ValueError('ORIGINAL_LIVE_PROFILE_OFF_REQUIRED')
            # The original client GET methods only; no submission/write methods called.
            client=DynamicLiveClient(env['ALPACA_API_KEY_ID'],env['ALPACA_API_SECRET_KEY'],writes_enabled=False)
            import urllib.request
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*a,**kw):raise ValueError('REDIRECT_REFUSED')
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            def quote(symbol):
                req=urllib.request.Request('https://data.alpaca.markets/v2/stocks/'+symbol+'/quotes/latest?feed=iex',method='GET',
                    headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
                with opener.open(req,timeout=8) as reply:raw=reply.read(1000001)
                if len(raw)>=1000000:raise ValueError('QUOTE_SOURCE_BOUND')
                return dict(**json.loads(raw),received_ms=time.time_ns()//1000000,raw_sha256=hashlib.sha256(raw).hexdigest())
            publisher=PreloadedSourcePublisher(policy,template,protocol,session['ticker'],client,quote)
            source=publisher.capture();raw=publisher.last_source
            cost=read_json(str(KIT/'cost-source.json'))
            if dec(source['liability_reserve_usd'])>dec(cost['buy_regulatory_reserve_usd']):raise ValueError('STATIC_CAT_BOUND_INFEASIBLE')
            snapshot=dict(endpoint=env['ALPACA_BASE_URL'],account=raw['account'],positions=raw['positions'],open_orders=raw['open_orders'],
                asset=raw['asset'],quote=raw['quote']['quote'],observed_ms=source['observed_ms'],
                gates=dict(earnings=source['gates'][session['ticker']]['earnings'],reentry=session['ticker'] not in source['blocked_symbols'],
                    concentration=source['gates'][session['ticker']]['concentration'],protection=source['gates'][session['ticker']]['protection']))
            snapshot_path=KIT/'fresh-live-snapshot.json';readiness.write_new(snapshot_path,canonical(snapshot))
            source_path=KIT/'fresh-publisher-source.json';readiness.write_new(source_path,canonical(source))
            rows=[closure.pin(snapshot_path),closure.pin(source_path),closure.pin(KIT/'fresh-authority-capture.json')]
            readiness.write_new(preparation_path,canonical(dict(snapshot=snapshot,source_files=rows,source_manifest_sha256=digest(rows))))
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError) as exc:
            # Full PAPER PASS may still be preserved, but no invented fresh source.
            readiness.write_new(KIT/'fresh-preparation-blocker.json',canonical(readiness.blocked(str(exc))))
    result=closure.close_once(manifest,terminal_capture=terminal_path,live_preparation=preparation_path,now_ms=time.time_ns()//1000000)
    blocker=KIT/'fresh-preparation-blocker.json'
    if blocker.exists() and result['status']!='READY_FOR_LIVE_GO':
        result={**result,'fresh_preparation_blocker':read_json(str(blocker))['reason']}
    print(json.dumps(result));signal.alarm(0)
    return 0 if result['status']=='READY_FOR_LIVE_GO' else 2


if __name__=='__main__':
    signal.alarm(170)
    try:
        if len(sys.argv)<2 or sys.argv[2:] not in ([],['--verify-only']):raise ValueError('EXPLICIT_OPERATION_REQUIRED')
        raise SystemExit(main(sys.argv[1],verify_only=sys.argv[2:]==['--verify-only']))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps(dict(status='BLOCKED_DATA',reason=str(exc),orders_allowed=False,live_orders_allowed=False)));raise SystemExit(2)
