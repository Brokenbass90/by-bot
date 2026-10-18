"""Independent NET DAY telemetry: authenticated GET only, separate state/lock.

No account lock, manager call, permission file, order or protection mutation.
Telegram is the only POST route, after a durable journal and delivery claim.
"""
import contextlib
from datetime import date,datetime,timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import ssl
import time
from urllib import request,error
import uuid
from zoneinfo import ZoneInfo

from research_lab.alpaca_day_protection_v1 import evaluate,summarize,_digest as digest
from research_lab.kity_oct15_deadline_v1 import publish_once,stable_bytes

LIVE='https://api.alpaca.markets'


def publish(path,value):
    publish_once(Path(path),(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())


def atomic(path,value):
    path=Path(path);tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    publish(tmp,value);os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


class AlreadyRunning(ValueError):pass


class Monitor:
    def __init__(self,root,*,clock):
        self.root=Path(root).absolute();self.clock=clock
        if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise ValueError('OBSERVER_ROOT_SYMLINK')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        for name in ('journal','captures','notifications','sessions'):(self.root/name).mkdir(exist_ok=True,mode=0o700)
        self.fd=os.open(self.root/'observer.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:os.close(self.fd);self.fd=None;raise AlreadyRunning('OBSERVER_ALREADY_RUNNING')

    def __enter__(self):return self
    def __exit__(self,*args):
        if self.fd is not None:os.close(self.fd);self.fd=None

    def notify(self,event,sender):
        key=digest(event);claim=self.root/'notifications'/(key+'.claim.json')
        receipt=self.root/'notifications'/(key+'.receipt.json')
        if receipt.exists():return dict(status='ALREADY_RECORDED',delivery=json.loads(stable_bytes(receipt)))
        if claim.exists():return dict(status='DELIVERY_UNKNOWN_NO_RETRY')
        publish(claim,event)  # durable before any network request
        try:
            delivery=sender(event)
            out=dict(status='DELIVERED' if delivery.get('delivered') is True else 'DELIVERY_UNKNOWN_NO_RETRY',**delivery)
        except Exception as exc:out=dict(status='DELIVERY_UNKNOWN_NO_RETRY',error_type=type(exc).__name__)
        publish(receipt,out);return out

    def delivery_test(self,sender):
        # A notification transport check, never a fake broker/protection event.
        return self.notify(dict(kind='DELIVERY_TEST',incident_id='installation-transport-test',
            meaning='NOT_A_PROTECTION_CONFIRMATION'),sender)

    def service_failure(self,sender):
        now=self.clock();day=datetime.fromtimestamp(now/1000,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        event=dict(kind='CRITICAL',incident_id=digest(dict(kind='MONITOR_UNIT_FAILED',session=day)),session=day,
            first_evidence_id=digest(dict(service_failed_at_ms=now)),
            issues=[dict(code='DAY_MONITOR_SERVICE_FAILED',severity='CRITICAL')])
        saved=self.root/'service-failure-event.json'
        if saved.exists():
            previous=json.loads(stable_bytes(saved))
            if previous['session']==day:event=previous
        atomic(saved,event)  # separate from potentially corrupt observation state
        return self.notify(event,sender)

    def once(self,capture,sender):
        run=uuid.uuid4().hex;now=self.clock()
        try:
            source=capture();now=self.clock()
            publish(self.root/'captures'/(run+'.json'),source)
            observation=evaluate(source,now_ms=now)
        except Exception as exc:
            day=datetime.fromtimestamp(now/1000,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            observation=dict(schema='ALPACA_DAY_PROTECTION_OBSERVATION_V1',status='DAY_PROTECTION_UNKNOWN',
                observed_ms=now,session=day,session_open_ms=None,regular_session=False,
                coverage=[],issues=[dict(code='DAY_CAPTURE_FAILED',severity='CRITICAL')],
                source_error_type=type(exc).__name__,actual_unprotected_minutes=None,
                orders_allowed=False,money_authority=False,broker_writes=0)
            observation['evidence_id']=digest(observation)
        observed_day=observation['session'] or datetime.fromtimestamp(now/1000,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        journal=self.root/'journal'/(observed_day+'-'+str(now)+'-'+run+'.json');publish(journal,observation)
        state_path=self.root/'state.json'
        state=json.loads(stable_bytes(state_path)) if state_path.exists() else dict(generation=0,active=False)
        issue_key=digest(observation['issues']);event=None
        if observation['issues']:
            if not state['active'] or state.get('issue_key')!=issue_key or state.get('session')!=observed_day:
                state['generation']+=1
                state.update(incident_id=digest(dict(session=observed_day,generation=state['generation'])),
                    issue_key=issue_key,session=observed_day,first_evidence_id=observation['evidence_id'])
            state['active']=True
            event=dict(kind='CRITICAL',incident_id=state['incident_id'],session=state['session'],
                first_evidence_id=state['first_evidence_id'],issues=observation['issues'])
        elif state['active'] and observation['status'] in {'DAY_PROTECTION_CONFIRMED','DAY_NO_OWNED_EXPOSURE_OBSERVED'}:
            state['active']=False
            event=dict(kind='RECOVERED',incident_id=state['incident_id'],session=observation['session'],
                evidence_id=observation['evidence_id'],status=observation['status'])
        state['last_evidence_id']=observation['evidence_id'];atomic(state_path,state)
        atomic(self.root/'latest.json',dict(observation=observation,journal=journal.name,broker_writes=0))
        notification=self.notify(event,sender) if event else dict(status='QUIET')
        if observation['regular_session']:
            rows=[json.loads(p.read_bytes()) for p in (self.root/'journal').glob(observed_day+'-*.json')]
            summary=summarize(rows,session=observation['session'])
            atomic(self.root/'sessions'/(observation['session']+'.json'),summary)
        return dict(observation=observation,notification=notification,broker_writes=0)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('BROKER_REDIRECT_REFUSED')


class GetReader:
    """No method/payload parameter and no broker-write method exists."""
    def __init__(self,key,secret,*,open_request=None):
        self.headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
        self.opener=request.build_opener(NoRedirect(),request.HTTPSHandler(context=ssl.create_default_context()))
        self.open_request=open_request or self._open

    def _open(self,req):
        with self.opener.open(req,timeout=8) as response:raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('BROKER_RESPONSE_TOO_LARGE')
        return raw

    def get(self,path):
        allowed=path in {'/v2/account','/v2/clock','/v2/positions','/v2/orders?status=open&limit=500'}
        allowed=allowed or bool(re.fullmatch(r'/v2/orders/[A-Za-z0-9_-]{1,128}',path))
        cal=re.fullmatch(r'/v2/calendar\?start=(\d{4}-\d{2}-\d{2})&end=(\d{4}-\d{2}-\d{2})',path)
        if cal:allowed=date.fromisoformat(cal[1])==date.fromisoformat(cal[2])
        if not allowed:raise ValueError('GET_ROUTE_REFUSED')
        req=request.Request(LIVE+path,headers=self.headers,method='GET')
        return json.loads(self.open_request(req))


def pin_files(files):
    for name,pin in files.items():
        if hashlib.sha256(stable_bytes(Path(name))).hexdigest()!=pin:raise ValueError('READ_ONLY_SOURCE_PIN_DRIFT')


def collect(config):
    from dotenv import dotenv_values
    pin_files(config['read_only_pins'])
    binding=json.loads(stable_bytes(Path(config['binding_path'])))
    if Path(binding['lock_path']).stat().st_ino!=config['account_lock_inode']:
        raise ValueError('ORIGINAL_ACCOUNT_LOCK_INODE_CHANGED')
    profile=dotenv_values(config['live_profile'],interpolate=False)
    if profile.get('ALPACA_BASE_URL')!=LIVE:raise ValueError('EXACT_LIVE_GET_PROFILE_REQUIRED')
    reader=GetReader(profile['ALPACA_API_KEY_ID'],profile['ALPACA_API_SECRET_KEY'])
    ledger=Path(binding['ledger_path']);before=stable_bytes(ledger);native=json.loads(before)
    expected={s:native.get(s,config['initial_expected'][s]) for s in config['symbols']}
    start=time.time_ns()//1000000;clock=reader.get('/v2/clock')
    day=datetime.fromisoformat(clock['timestamp'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    calendar=reader.get('/v2/calendar?start='+day+'&end='+day)
    account=reader.get('/v2/account')
    if account['id']!=binding['account_id']:raise ValueError('ACCOUNT_IDENTITY_CONFLICT')
    positions=reader.get('/v2/positions');orders=reader.get('/v2/orders?status=open&limit=500')
    if not isinstance(orders,list) or len(orders)>=500:raise ValueError('ORDERS_SOURCE_INCOMPLETE')
    if any(s not in native and any(p['symbol']==s for p in positions) for s in expected):
        raise ValueError('POSITION_WITHOUT_CURRENT_OWNERSHIP')
    stops=[reader.get('/v2/orders/'+r['accepted_order_id']) for r in expected.values()]
    clock=reader.get('/v2/clock');end=time.time_ns()//1000000
    unchanged=stable_bytes(ledger)==before;pin_files(config['read_only_pins'])
    return dict(schema='ALPACA_DAY_PROTECTION_SOURCE_V1',started_ms=start,completed_ms=end,
        clock=clock,calendar=calendar,positions=positions,open_orders=orders,stop_readbacks=stops,
        expected=expected,orders_complete=True,account_identity_verified=True,ledger_unchanged=unchanged,
        source_pins_verified=len(config['read_only_pins']),broker_writes=0)


def telegram(config,event):
    """Reuse the existing photo/text-report helper; Telegram-only HTTP wrapper."""
    raw=stable_bytes(Path(config['telegram_env']))
    if hashlib.sha256(raw).hexdigest()!=config['telegram_env_sha256']:raise ValueError('TELEGRAM_SOURCE_DRIFT')
    env=dict(line.split('=',1) for line in raw.decode().splitlines() if '=' in line)
    if set(env)!={'TG_TOKEN','TG_CHAT_ID'}:raise ValueError('TELEGRAM_ONLY_ENV_REQUIRED')
    helper=Path(config['telegram_helper']);pin_files({str(helper):config['telegram_helper_sha256']})
    os.environ.update(env);os.environ['ALPACA_REPORT_LOCAL_ENV']='/nonexistent-report-only-env'
    loader=importlib.util.spec_from_file_location('day_report_helper',helper)
    module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
    if event['kind']=='DELIVERY_TEST':
        text=(config['scope_label']+': безопасная проверка доставки.\nORDERS_OFF, реальных ордеров нет.\nNET, SHOP, manager, риск и финансовые разрешения не изменены.'
            if config.get('scope_label') else 'Alpaca DAY monitor: проверка доставки.\nЭто НЕ тревога и НЕ подтверждение стопа.\nНаблюдатель только GET; NET, manager, V3 и HALT не изменены.')
    elif event['kind']=='RECOVERED':
        text='Alpaca NET: readback восстановлен.\n'+event['status']+'\nEvidence '+event['evidence_id']
    else:
        codes=', '.join(r['code'] for r in event['issues'])
        text='Alpaca NET CRITICAL\n'+codes+'\nСессия '+event['session']+'\nПодтверждение защиты отсутствует или источник UNKNOWN.\nНаблюдатель ордеров не отправляет. Evidence '+event['first_evidence_id']
    if config.get('scope_label') and event['kind']!='DELIVERY_TEST':
        text=config['scope_label']+' '+event['kind']+'\n'+(', '.join(r['code'] for r in event.get('issues',[])))+'\nEvidence '+str(event.get('first_evidence_id',event.get('evidence_id','UNKNOWN')))+'\nРеальные ордера из этого наблюдателя не отправляются.'
    captured={};original=module.urllib.request.urlopen
    def send(req,*args,**kwargs):
        if req.full_url!='https://api.telegram.org/bot'+env['TG_TOKEN']+'/sendMessage' or req.get_method()!='POST':
            raise ValueError('TELEGRAM_ONLY_ROUTE')
        response=original(req,*args,**kwargs);captured.update(http_status=response.status,raw=response.read(200001));return response
    module.urllib.request.urlopen=send
    try:
        with contextlib.redirect_stderr(io.StringIO()):ok=module._tg_send(text)
    finally:module.urllib.request.urlopen=original
    body=captured.get('raw',b'')
    publish(Path(config['output_root'])/'notifications'/(digest(event)+'.response.json'),
        dict(http_status=captured.get('http_status'),raw_response=body.decode(errors='replace')))
    result=json.loads(body) if body else {}
    return dict(delivered=ok and result.get('ok') is True,http_status=captured.get('http_status'),
        response_sha256=hashlib.sha256(body).hexdigest(),message_id=result.get('result',{}).get('message_id'))
