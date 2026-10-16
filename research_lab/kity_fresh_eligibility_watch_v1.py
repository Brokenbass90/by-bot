"""Exact-policy GET-only eligibility observer. No financial authority.

Writes only its own source/attempt/health/terminal files. Never instantiates an
owner, sender, permit, actual journal or control command. READY is a dated
observation; real personal GO must use a separate fresh capture in the writer.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

from bot.kity_m3_orders_off import digest
from research_lab.kity_micro_physical_owner_v1 import publish

STATUSES={'KITY_FRESH_COMPATIBLE_READY','POLICY_EXPIRED_UNUSED',
          'POLICY_OWNER_ACTION_PRESENT','KITY_FRESH_WATCH_BLOCKED'}

class AlreadyRunning(ValueError):pass


def atomic(path,value):
    path=Path(path);temp=path.with_name('.'+path.name+'.'+str(time.time_ns()))
    publish(temp,value)
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


class Watch:
    def __init__(self,root,*,policy_id,expires_ms,clock,guard,capture,spec_sha256=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if any(p.is_symlink() for p in (self.root,*self.root.absolute().parents)):
            raise ValueError('WATCH_ROOT_SYMLINK')
        self.policy_id=policy_id;self.expires_ms=expires_ms;self.clock=clock
        self.guard=guard;self.capture=capture;self.spec_sha256=spec_sha256;self.terminal=None
        self.lock=os.open(self.root/'observer.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lock);self.lock=None;raise AlreadyRunning('WATCH_ALREADY_RUNNING')
        try:
            p=self.root/'terminal.json'
            if p.exists():
                r=json.loads(p.read_bytes());body={k:v for k,v in r.items() if k!='terminal_id'}
                if (r.get('schema')!='KITY_EXACT_POLICY_WATCH_TERMINAL_V1' or r.get('terminal_id')!=digest(body)
                        or r.get('policy_id')!=policy_id or r.get('expires_ms')!=expires_ms
                        or r.get('spec_sha256')!=spec_sha256 or r.get('status') not in STATUSES):
                    raise ValueError('WATCH_TERMINAL_IDENTITY_CONFLICT')
                self.terminal=r
        except Exception:self.close();raise

    def close(self):
        if self.lock is not None:os.close(self.lock);self.lock=None

    def stop(self,status,**fields):
        if self.terminal:return self.terminal
        if status not in STATUSES:raise ValueError('WATCH_STATUS')
        r=dict(schema='KITY_EXACT_POLICY_WATCH_TERMINAL_V1',policy_id=self.policy_id,
            expires_ms=self.expires_ms,spec_sha256=self.spec_sha256,status=status,
            observed_ms=self.clock(),broker_writes=0,owner_authority=False,policy_consumed_by_watcher=False,**fields)
        r['terminal_id']=digest(r);publish(self.root/'terminal.json',r);self.terminal=r
        atomic(self.root/'heartbeat.json',r);return r

    def check(self):
        # Check consumption before expiry: a policy used by a personal command
        # is never reported EXPIRED_UNUSED merely because observation was late.
        try:status=self.guard()
        except Exception as exc:return self.stop('KITY_FRESH_WATCH_BLOCKED',reason=type(exc).__name__+':'+str(exc)[:240])
        if status:return self.stop(status)
        if self.clock()>=self.expires_ms:return self.stop('POLICY_EXPIRED_UNUSED')

    def step(self):
        if self.terminal:return self.terminal
        stopped=self.check()
        if stopped:return stopped
        attempt=self.root/'attempts'/(str(self.clock())+'-'+str(time.time_ns()))
        attempt.mkdir(parents=True,exist_ok=False,mode=0o700)
        atomic(self.root/'heartbeat.json',dict(status='OBSERVING',policy_id=self.policy_id,observed_ms=self.clock(),broker_writes=0))
        try:r=self.capture(attempt)
        except Exception as exc:r=dict(compatible=False,reason=type(exc).__name__+':'+str(exc)[:240])
        if type(r.get('compatible')) is not bool:raise ValueError('WATCH_CAPTURE_CONTRACT')
        r=dict(r,observed_ms=self.clock(),policy_id=self.policy_id,broker_writes=0)
        publish(attempt/'result.json',r)
        stopped=self.check()
        if stopped:return stopped
        if r['compatible']:
            return self.stop('KITY_FRESH_COMPATIBLE_READY',**{k:v for k,v in r.items() if k not in ('compatible','policy_id','broker_writes','observed_ms')})
        pending=dict(r,status='PENDING');atomic(self.root/'heartbeat.json',pending);return pending


class PinnedSource:
    """Immutable writer custody is read, never acquired or changed."""
    def __init__(self,spec):
        self.spec=spec;self.core=Path(spec['core_config']);self.pin=spec['core_config_sha256']
        self.c=self.read(self.core,self.pin);self.runtime=Path(self.c['runtime_root'])
        self.custody=Path(self.c['custody_runtime_root'])
        self.policy_path=self.runtime/'policies'/(spec['policy_id']+'.json')
        self.policy=self.read(self.policy_path,spec['policy_sha256'])
        from research_lab.kity_micro_post_go_pricing_v1 import validate_policy
        validate_policy(self.policy)
        if (self.policy['policy_id']!=spec['policy_id'] or self.policy['physical_config_sha256']!=self.pin
                or self.policy['valid_until_ms']!=spec['expires_ms']):raise ValueError('WATCH_POLICY_SCOPE')
        output=Path(spec['output_root']).absolute()
        if output==self.custody or self.custody in output.parents or output in self.custody.parents:
            raise ValueError('WATCH_OUTPUT_MUST_BE_OUTSIDE_WRITER_RUNTIME')

    @staticmethod
    def read(path,pin):
        path=Path(path)
        if any(p.is_symlink() for p in (path,*path.absolute().parents)):raise ValueError('WATCH_SOURCE_SYMLINK')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('WATCH_PIN_DRIFT:'+str(path))
        return json.loads(raw)

    def unclaimed(self):
        if (self.runtime/'selected-v2.json').exists():return 'POLICY_OWNER_ACTION_PRESENT'
        store=self.runtime/'experiments-v2'/self.policy['policy_id']
        if any(store.glob('*')):return 'POLICY_OWNER_ACTION_PRESENT'
        for p in (self.runtime/'commands').glob('*.json'):
            cmd=json.loads(p.read_bytes())
            if cmd.get('kind')=='GO_POST_GO':return 'POLICY_OWNER_ACTION_PRESENT'

    def guard(self):
        used=self.unclaimed()
        if used:return used
        self.read(self.core,self.pin);self.read(self.policy_path,self.spec['policy_sha256'])
        for rel,pin in self.c['source_files'].items():
            p=Path(self.c['app_root'])/rel
            if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=pin:raise ValueError('WATCH_CORE_SOURCE_DRIFT:'+rel)
        for group in ('guard_source_files','prior_no_send_files','predecessor_files'):
            for name,pin in self.c[group].items():
                p=Path(name)
                if any(q.is_symlink() for q in (p,*p.absolute().parents)) or hashlib.sha256(p.read_bytes()).hexdigest()!=pin:
                    raise ValueError('WATCH_ORIGINAL_SOURCE_DRIFT:'+name)
        if self.c.get('credential_source'):
            if hashlib.sha256(Path(self.c['credential_source']).read_bytes()).hexdigest()!=self.c['credential_source_sha256']:
                raise ValueError('WATCH_CREDENTIAL_SOURCE_DRIFT')
        unit=Path('/etc/systemd/system')/self.c['unit']
        if hashlib.sha256(unit.read_bytes()).hexdigest()!=self.spec['core_unit_sha256']:raise ValueError('WATCH_UNIT_DRIFT')
        if (self.custody/'account.lock').stat().st_ino!=self.c['account_lock_inode']:raise ValueError('WATCH_ORIGINAL_LOCK_DRIFT')
        for path,pin in self.c['wire_baseline_files'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=pin:raise ValueError('WATCH_WIRE_SOURCE_DRIFT')
        if any(str(p) not in self.c['wire_baseline_files'] for p in (self.custody/'wire').glob('send-*.json')):
            # Recheck the personal command after the wire scan to avoid
            # classifying a concurrent owner action as a static conflict.
            used=self.unclaimed()
            if used:return used
            raise ValueError('WATCH_UNEXPECTED_FINANCIAL_HISTORY')
        health=read_only_health(self.spec)
        if health.get('status')!='HEALTHY':raise ValueError('WATCH_OWNER_NOT_HEALTHY')


def read_only_health(spec):
    """Call the existing pinned read-only observer, never its locking CLI."""
    import types
    path=Path(spec['health_script']);raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['health_script_sha256']:raise ValueError('HEALTH_SOURCE_DRIFT')
    health_spec=PinnedSource.read(spec['health_spec'],spec['health_spec_sha256'])
    module=types.ModuleType('kity_pinned_read_only_health');module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module.observe(health_spec)


class ReadonlyCapture:
    def __init__(self,source,output_root):
        from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials,EvidenceReader
        from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError
        from research_lab.kity_micro_low_latency_v1 import ReusableGetWire
        key,secret=load_bound_credentials(source.c);self.source=source;wire=ReusableGetWire()
        class GuardedReader(EvidenceReader):
            def get(self,path,params):
                if source.unclaimed() or time.time_ns()//1000000>=source.spec['expires_ms']:
                    raise SourceError('WATCH_POLICY_NO_LONGER_OBSERVABLE')
                return super().get(path,params)
        self.reader=GuardedReader(BybitReadTransport(key,secret,wire=wire),Path(output_root)/'raw')
        self.reader.all_symbol_fee_snapshot=True

    def __call__(self,store):
        from research_lab.kity_micro_physical_owner_v1 import batch_get,capture_account,rows,validate_fresh_entry,now_ms
        from research_lab.kity_micro_bounded_owner_v2 import account_instrument_available
        from research_lab.kity_micro_pricing_intent_v2 import load_source
        from research_lab.kity_micro_post_go_pricing_v1 import compile_after_go,verify_compilation
        from research_lab.kity_execution_micro_runtime_v1 import BASKET,initial
        from research_lab.kity_micro_low_latency_v1 import ParallelPreflightGets
        c=self.source.c;reader=self.reader;began=now_ms()
        permissions=batch_get(reader,[(s,'/v5/account/instruments-info',dict(category='linear',symbol=s)) for s,_ in BASKET])
        for s,cap in permissions.items():account_instrument_available(cap,s)
        cap=capture_account(reader);cap['response'].update(physical_config_sha256=self.source.pin,account_instruments=permissions)
        path=store/'capture.json';pin=publish(path,cap)
        bounds=json.loads((Path(c['app_root'])/c['bounds_file']).read_bytes())
        d,caps=load_source(path,pin,bounds,self.source.pin)
        result=dict(compatible=False,gross=d['current_basket_gross_usdt'],source_sha256=pin,
            source_completed_ms=d['observed_end_ms'],account_instrument_checks=10,checks=0)
        if d['plan']['blocked_reasons']:return dict(result,reason='|'.join(d['plan']['blocked_reasons']))
        # Pure no-claim rehearsal of the same compiler. The virtual clock here
        # is not a monetary GO; no result is installed into the account owner.
        out=compile_after_go(self.source.policy,d,caps,go_ms=began,now_ms=now_ms());verify_compilation(out)
        class EmptyJournal:
            plan=out['plan']
            def snapshot(self):return initial(self.plan)
        checks=[]
        for leg in out['plan']['legs']:
            symbol=leg['symbol'];view=ParallelPreflightGets(reader,symbol,True)
            account_instrument_available(view.get('/v5/account/instruments-info',dict(category='linear',symbol=symbol)),symbol)
            validate_fresh_entry(view,EmptyJournal(),leg['request'],now_ms)
            checks.append(dict(symbol=symbol,status='EXISTING_FRESH_PREFLIGHT_PASS'))
        if rows(reader,'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200')) or rows(reader,'/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50')):
            return dict(result,reason='ACCOUNT_NOT_FLAT_OR_OPEN_ORDERS')
        return dict(result,compatible=True,gross=out['current_basket_gross_usdt'],checks=10,per_symbol=checks,reason=None)


def notify_once(root,event,sender):
    root=Path(root);done=root/'notification-receipt.json';claim=root/'notification-claim.json'
    if json.loads((root/'terminal.json').read_bytes())!=event:raise ValueError('NOTIFY_REQUIRES_DURABLE_TERMINAL')
    if done.exists():
        result=json.loads(done.read_bytes())
        if result.get('terminal_id')!=event['terminal_id']:raise ValueError('NOTIFICATION_IDENTITY_CONFLICT')
        return result
    if claim.exists():return dict(status='NOTIFICATION_UNKNOWN_DO_NOT_RETRY',terminal_id=event['terminal_id'])
    publish(claim,dict(terminal_id=event['terminal_id'],status='DELIVERY_MAY_HAVE_RUN_NO_BLIND_RETRY'))
    try:
        delivery=sender(event)
        result=dict(delivery,status='NOTIFICATION_DELIVERED' if delivery.get('delivered') is True else 'NOTIFICATION_UNKNOWN_DO_NOT_RETRY')
    except Exception as exc:result=dict(status='NOTIFICATION_UNKNOWN_DO_NOT_RETRY',error_type=type(exc).__name__)
    result.update(terminal_id=event['terminal_id'],broker_writes=0);publish(done,result);return result


def telegram_sender(spec,event):
    import importlib.util
    import datetime as dt
    envpath=Path(spec['telegram_env']);raw=envpath.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['telegram_env_sha256']:raise ValueError('TG_CONFIG_DRIFT')
    env=dict(line.split('=',1) for line in raw.decode().splitlines() if '=' in line)
    if set(env)!={'TG_TOKEN','TG_CHAT_ID'}:raise ValueError('TG_ONLY_CONFIG_REQUIRED')
    helper=Path(spec['telegram_helper'])
    if hashlib.sha256(helper.read_bytes()).hexdigest()!=spec['telegram_helper_sha256']:raise ValueError('TG_HELPER_DRIFT')
    os.environ.update(env);os.environ['ALPACA_REPORT_LOCAL_ENV']='/nonexistent-report-only-env'
    imp=importlib.util.spec_from_file_location('kity_watch_owner_notify',helper)
    module=importlib.util.module_from_spec(imp);imp.loader.exec_module(module)
    source=dt.datetime.fromtimestamp(event.get('source_completed_ms',event['observed_ms'])/1000,dt.timezone.utc).isoformat()
    caption=(event['status']+'\nKITY policy '+event['policy_id'][:12]+'…\n'
        +'Снимок: '+source+'\n'
        +('Gross '+str(event['gross'])+' USDT ≤215; проверки 10/10.\n' if event['status']=='KITY_FRESH_COMPATIBLE_READY' else str(event.get('reason',''))+'\n')
        +'Watcher остановлен. Ордеров не отправлял; policy не использовал.\n'
        +'Это уведомление, не денежное разрешение. Срок policy:16.10 21:00UTC /17.10 00:00Кипра.')
    captured={};original=module.urllib.request.urlopen
    def request(req,*args,**kwargs):
        if not (req.full_url.startswith('https://api.telegram.org/bot') and req.full_url.endswith('/sendMessage') and req.get_method()=='POST'):
            raise ValueError('NOTIFICATION_TELEGRAM_ONLY')
        response=original(req,*args,**kwargs);captured.update(status=response.status,raw=response.read(200001));return response
    module.urllib.request.urlopen=request
    ok=module._tg_send(caption);body=captured.get('raw',b'')
    publish(Path(spec['output_root'])/'notification-response.json',dict(http_status=captured.get('status'),raw=body.decode(errors='replace')))
    try:result=json.loads(body)
    except ValueError:result={}
    return dict(delivered=ok and result.get('ok') is True,http_status=captured.get('status'),
        response_sha256=hashlib.sha256(body).hexdigest(),message_id=result.get('result',{}).get('message_id'))


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--spec-sha256',required=True)
    a=ap.parse_args(argv);spec=PinnedSource.read(a.spec,a.spec_sha256)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=spec['watcher_source_sha256']:raise ValueError('WATCHER_CODE_DRIFT')
    if spec['interval_seconds']!=120:raise ValueError('WATCH_INTERVAL_SCOPE')
    source=PinnedSource(spec);root=Path(spec['output_root'])
    clock=lambda:time.time_ns()//1000000
    # Capture constructor only creates a signed GET reader, never a sender.
    capture=ReadonlyCapture(source,root)
    w=Watch(root,policy_id=spec['policy_id'],expires_ms=spec['expires_ms'],clock=clock,
        guard=source.guard,capture=capture,spec_sha256=a.spec_sha256)
    try:
        while True:
            r=w.step();print(json.dumps({k:r.get(k) for k in ('status','policy_id','observed_ms','reason','gross','checks')}),flush=True)
            if r['status']!='PENDING':
                if r['status']!='POLICY_OWNER_ACTION_PRESENT':notify_once(root,r,lambda event:telegram_sender(spec,event))
                return 0
            time.sleep(max(0,min(spec['interval_seconds'],(spec['expires_ms']-clock())/1000)))
    finally:w.close()

if __name__=='__main__':main()
