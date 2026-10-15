"""Concrete exclusive account owner. Installation is orders-OFF, never a GO.

One process holds the account flock and the only authenticated POST capability.
Raw observations and one-shot send barriers are durable before wire I/O. Reads
may be concurrent; journal/state mutations and every POST remain serial.
"""
import concurrent.futures as cf
from decimal import Decimal as D
import fcntl,hashlib,hmac,json,os,re,subprocess,time,urllib.request,urllib.error
from pathlib import Path

from bot.kity_m3_orders_off import digest,_levels,_vwap
from research_lab.kity_execution_micro_runtime_v1 import canonical,numeric,validate_plan,BASKET
from research_lab.kity_execution_micro_v1 import common_source_clock
from research_lab.kity_micro_transport_v1 import BASE,SYMBOLS,NoRedirect,BybitReadTransport,SourceError

now_ms=lambda:time.time_ns()//1000000
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def publish(path,value,*,exclusive=True):
    """Complete private JSON, fsync, atomic non-overwrite publication by default."""
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.is_symlink():raise SourceError('STATE_SYMLINK')
    raw=(canonical(value)+'\n').encode();tmp=path.parent/('.'+path.name+'.'+str(time.time_ns()))
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        if exclusive:os.link(tmp,path)
        else:os.replace(tmp,path)
        dfd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        if tmp.exists():tmp.unlink()
    return sha(raw)


class AccountLease:
    def __init__(self,path):
        self.path=Path(path)
        self.fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:os.close(self.fd);raise
        self.pid=os.getpid();self.inode=os.fstat(self.fd).st_ino
    def assert_held(self):
        if (os.getpid()!=self.pid or os.fstat(self.fd).st_ino!=self.inode
            or self.path.lstat().st_ino!=self.inode or self.path.is_symlink()):
            raise SourceError('ACCOUNT_LEASE_LOST')
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def close(self):os.close(self.fd)


def wire_post(method,url,headers,data,timeout):
    if method!='POST':raise SourceError('POST_METHOD_REQUIRED')
    req=urllib.request.Request(url,data=data,headers=headers,method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=timeout) as r:
            return r.status,r.read(2_000_001)
    except urllib.error.HTTPError as e:return e.code,e.read(2_000_001)


class SignedPostOnce:
    def __init__(self,key,secret,store,*,wire=wire_post,clock=now_ms):
        self._key,self._secret,self.store,self.wire,self.clock=key,secret,Path(store),wire,clock
        self.store.mkdir(mode=0o700,parents=True,exist_ok=True)
    def post(self,path,request):
        if path not in ('/v5/order/create','/v5/order/cancel'):raise SourceError('POST_PATH_SCOPE')
        raw=canonical(request).encode();pin=digest(dict(path=path,request=request));at=self.clock()
        try:publish(self.store/('send-'+pin+'.json'),dict(path=path,request=request,at_ms=at,status='INTENT_WIRE_MAY_HAVE_RUN'))
        except FileExistsError as exc:raise SourceError('SEND_ALREADY_RECORDED_RECONCILE_ONLY') from exc
        sig=hmac.new(self._secret.encode(),(str(at)+self._key+'10000').encode()+raw,hashlib.sha256).hexdigest()
        headers={'Content-Type':'application/json','User-Agent':'KITY-exclusive-micro-owner/1',
            'X-BAPI-API-KEY':self._key,'X-BAPI-TIMESTAMP':str(at),'X-BAPI-RECV-WINDOW':'10000','X-BAPI-SIGN':sig}
        try:
            status,body=self.wire('POST',BASE+path,headers,raw,3)
            if len(body)>2_000_000:raise SourceError('POST_RESPONSE_BOUND')
            if self._key.encode() in body or self._secret.encode() in body:raise SourceError('SECRET_ECHO_REJECTED')
            publish(self.store/('response-'+pin+'.json'),dict(http_status=status,raw=body.decode(),raw_sha256=sha(body),receive_ms=self.clock()))
            response=json.loads(body)
            if status!=200 or not isinstance(response,dict):raise SourceError('POST_ACK_UNKNOWN')
            return response
        except Exception:
            # No second call and no removal of the send barrier, even on timeout.
            raise


class EvidenceReader:
    """Record exact GET evidence; never retain authentication headers/secrets."""
    def __init__(self,reader,root):
        self.reader,self.root=reader,Path(root);self.count=0
        self.account_fingerprint=reader.account_fingerprint
    def get(self,path,params):
        cap=self.reader.get(path,params)
        publish(self.root/('get-'+str(time.time_ns())+'-'+digest(cap)[:12]+'.json'),cap)
        self.count+=1
        return cap
    pages=BybitReadTransport.pages
    result=staticmethod(BybitReadTransport.result)


def batch_get(reader,tasks):
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        jobs={pool.submit(reader.get,path,params):name for name,path,params in tasks}
        return {jobs[j]:j.result() for j in cf.as_completed(jobs)}


def rows(reader,path,params):
    group=reader.pages(path,params)
    if not group.get('complete'):raise SourceError('PAGINATION_UNKNOWN:'+path)
    return [r for p in group['pages'] for r in reader.result(p)['list']]


def capture_account(reader):
    """Same immutable source schema as intake; books last, no order requests."""
    start=now_ms();tasks=[('identity','/v5/user/query-api',{}),('account','/v5/account/info',{}),
        ('wallet','/v5/account/wallet-balance',dict(accountType='UNIFIED')),('server_clock','/v5/market/time',{})]
    for s in SYMBOLS:
        tasks.extend((('instrument:'+s,'/v5/market/instruments-info',dict(category='linear',symbol=s)),
                      ('ticker:'+s,'/v5/market/tickers',dict(category='linear',symbol=s)),
                      ('fee:'+s,'/v5/account/fee-rate',dict(category='linear',symbol=s)),
                      ('position:'+s,'/v5/position/list',dict(category='linear',symbol=s))))
    c=batch_get(reader,tasks)
    for name,path,params in (
        ('all_positions','/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200')),
        ('all_open_orders','/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50')),
        ('history_connectivity','/v5/order/history',dict(category='linear',symbol='LTCUSDT',limit='1')),
        ('execution_connectivity','/v5/execution/list',dict(category='linear',symbol='LTCUSDT',limit='1')),
        ('transaction_connectivity','/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',startTime=str(start-3600000),endTime=str(start),limit='50'))):
        c[name]=reader.pages(path,params)
    c.update(batch_get(reader,[('book:'+s,'/v5/market/orderbook',dict(category='linear',symbol=s,limit='50')) for s in SYMBOLS]))
    return dict(response=dict(schema='kity_execution_micro_get_capture_v2',started_ms=start,completed_ms=now_ms(),
        base=BASE,symbols=list(SYMBOLS),selected_credential_sha256=reader.account_fingerprint,
        captures=c,services={},broker_writes=0))


def load_bound_credentials(config):
    p=Path(config['credential_source']);raw=p.read_bytes()
    if sha(raw)!=config['credential_source_sha256']:raise SourceError('CREDENTIAL_SOURCE_DRIFT')
    env={}
    for line in raw.decode().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);env[k.strip()]=v.strip().strip('"').strip("'")
    if env.get('BYBIT_BASE')!=BASE:raise SourceError('ACCOUNT_BASE_CONFLICT')
    selected=[r for r in json.loads(env['BYBIT_ACCOUNTS_JSON']) if r.get('name')==env.get('TRADE_ACCOUNT_NAME')]
    if len(selected)!=1 or sha(selected[0]['key'].encode())!=config['account_fingerprint']:
        raise SourceError('ACCOUNT_FINGERPRINT_CONFLICT')
    return selected[0]['key'],selected[0]['secret']


def platform_verifier(config):
    """Verify physical process/unit/inhibitor/source state, not a receipt boolean."""
    def verify():
        root=Path(config['app_root'])
        if sha(Path(config['_config_path']).read_bytes())!=config['_config_sha256']:
            raise SourceError('PHYSICAL_CONFIG_DRIFT')
        for name,pin in config['source_files'].items():
            p=root/name
            if p.is_symlink() or sha(p.read_bytes())!=pin:raise SourceError('INSTALLED_SOURCE_DRIFT:'+name)
        for name,pin in config['guard_source_files'].items():
            if sha(Path(name).read_bytes())!=pin:raise SourceError('ORIGINAL_SOURCE_DRIFT:'+name)
        if sha(Path(config['credential_source']).read_bytes())!=config['credential_source_sha256']:
            raise SourceError('CREDENTIAL_SOURCE_DRIFT')
        if sha(subprocess.run(['crontab','-l'],capture_output=True,check=True,timeout=3).stdout)!=config['original_cron_sha256']:
            raise SourceError('ORIGINAL_CRON_DRIFT')
        for unit,pin in config['inhibitors'].items():
            p=Path('/etc/systemd/system')/(unit+'.d')/'90-kity-micro-inhibit.conf'
            if sha(p.read_bytes())!=pin:raise SourceError('OLD_OWNER_INHIBITOR_DRIFT')
            info=unit_state(unit)
            if info['MainPID']!='0' or info['ActiveState'] not in ('inactive','failed'):
                raise SourceError('COMPETING_PHYSICAL_OWNER:'+unit)
        if not Path(config['inhibit_marker']).is_file():raise SourceError('INHIBIT_MARKER_MISSING')
        state=unit_state(config['unit'])
        if state['MainPID']!=str(os.getpid()) or state['ActiveState']!='active':
            raise SourceError('PHYSICAL_OWNER_PID_CONFLICT')
        unit_raw=Path(state['FragmentPath']).read_text()
        normalized=re.sub(r'--config-sha256 [0-9a-f]{64}', '--config-sha256 <PIN>',unit_raw)
        if sha(normalized.encode())!=config['unit_template_sha256']:
            raise SourceError('OWNER_UNIT_SOURCE_DRIFT')
        # A same-key process outside this owner may be another local sender.
        for p in Path('/proc').iterdir():
            if not p.name.isdecimal() or int(p.name)==os.getpid():continue
            try:
                e=(p/'environ').read_bytes()
                if b'BYBIT_ACCOUNTS_JSON=' in e:
                    for part in e.split(b'\0'):
                        if part.startswith(b'BYBIT_ACCOUNTS_JSON='):
                            try:accts=json.loads(part.partition(b'=')[2])
                            except ValueError:raise SourceError('UNKNOWN_CREDENTIAL_PROCESS')
                            if any(sha(a.get('key','').encode())==config['account_fingerprint'] for a in accts):
                                raise SourceError('COMPETING_CREDENTIAL_PROCESS:'+p.name)
            except (FileNotFoundError,ProcessLookupError,PermissionError):continue
    return verify


def unit_state(unit):
    r=subprocess.run(['systemctl','show',unit,'--property=ActiveState,MainPID,FragmentPath,SubState,NRestarts'],
        capture_output=True,text=True,timeout=3,check=True)
    return dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)


class PhysicalOwner:
    def __init__(self,journal,reader,lease,store,*,platform_check,post,clock=now_ms):
        self.journal,self.reader,self.lease,self.store=journal,reader,lease,Path(store)
        self.platform_check,self.post,self.clock=platform_check,post,clock
        self._authorized=False;self._ticket=None
    def assert_exclusive(self,plan):
        validate_plan(plan);self.lease.assert_held();self.platform_check()
        if self.journal is not None and self.journal.plan['plan_id']!=plan['plan_id']:
            raise SourceError('PHYSICAL_PLAN_CONFLICT')
    def accept_go(self,text):
        p=self.journal.plan
        if text!='GO KITY_EXECUTION_MICRO_LIVE '+p['plan_id']:raise SourceError('EXACT_OWNER_GO_REQUIRED')
        self.assert_exclusive(p)
        if self.journal.snapshot()['entries']:raise SourceError('GO_ALREADY_CONSUMED')
        publish(self.store/'owner-go.json',dict(exact_go=text,plan_id=p['plan_id'],at_ms=self.clock()))
        self._authorized=True
    def recover_go(self):
        p=self.journal.plan;go=json.loads((self.store/'owner-go.json').read_bytes())
        if go.get('exact_go')!='GO KITY_EXECUTION_MICRO_LIVE '+p['plan_id']:raise SourceError('GO_PIN_CONFLICT')
        self._authorized=True  # caller must durably inhibit new entries on restart
    def validate_preflight(self,plan,request,role):
        self.assert_exclusive(plan)
        if role=='ENTRY':
            if (self.store/'rollback-request.json').exists():raise SourceError('ROLLBACK_INHIBITS_ENTRY')
            validate_fresh_entry(self.reader,self.journal,request,self.clock)
        else:
            # Exits need actual signed same-symbol size, never entry-price gates.
            ps=rows(self.reader,'/v5/position/list',dict(category='linear',symbol=request['symbol']))
            if len(ps)!=1 or type(ps[0].get('positionIdx')) is not int or ps[0]['positionIdx']!=0:
                raise SourceError('EXIT_POSITION_MODE_UNKNOWN')
            held=numeric(self.journal.snapshot()['held'][request['symbol']],zero=True)
            expected=next(l['side'] for l in plan['legs'] if l['symbol']==request['symbol'])
            if numeric(ps[0]['size'],zero=True)!=held or (held and ps[0]['side']!=expected):
                raise SourceError('EXIT_OWNERSHIP_QUANTITY_CONFLICT')
            if role=='EXIT' and (request.get('reduceOnly') is not True or numeric(request['qty'])>held):
                raise SourceError('EXIT_SCOPE_CONFLICT')
        self._ticket=(digest(request),role,self.clock())
    def post_once(self,path,request):
        if not self._authorized:raise SourceError('EXACT_OWNER_GO_REQUIRED_ORDERS_OFF')
        self.assert_exclusive(self.journal.plan)
        ticket=self._ticket;self._ticket=None
        if not ticket or ticket[0]!=digest(request) or self.clock()<ticket[2] or self.clock()-ticket[2]>2000:
            raise SourceError('FRESH_VALIDATION_TICKET_REQUIRED')
        s=self.journal.snapshot();role=ticket[1];symbol=request.get('symbol')
        if path=='/v5/order/create' and role=='ENTRY':
            if (self.store/'rollback-request.json').exists():raise SourceError('ROLLBACK_INHIBITS_ENTRY')
            leg=next(l for l in self.journal.plan['legs'] if l['symbol']==symbol)
            order=s['entries'].get(symbol)
            if request!=leg['request'] or not order or order['order_id'] is not None or order['terminal']:
                raise SourceError('DURABLE_EXACT_ENTRY_INTENT_REQUIRED')
        elif path=='/v5/order/create' and role=='EXIT':
            order=s['exits'].get(request.get('orderLinkId'))
            leg=next(l for l in self.journal.plan['legs'] if l['symbol']==symbol)
            expected=dict(category='linear',symbol=symbol,side='Sell' if leg['side']=='Buy' else 'Buy',
                qty=order['quantity'] if order else None,orderType='Market',positionIdx=0,reduceOnly=True,orderLinkId=request.get('orderLinkId'))
            if not order or order['order_id'] is not None or order['terminal'] or request!=expected:
                raise SourceError('DURABLE_OWNED_EXIT_INTENT_REQUIRED')
        elif path=='/v5/order/cancel' and role=='CANCEL_NATIVE_PROTECTION':
            matches=[v for v in s['exits'].values() if v.get('is_native_protection') and v['order_id']==request.get('orderId') and v['symbol']==symbol and v['cancel_sent']]
            if len(matches)!=1 or request!=dict(category='linear',symbol=symbol,orderId=matches[0]['order_id']):
                raise SourceError('DURABLE_OWNED_CANCEL_INTENT_REQUIRED')
        else:raise SourceError('POST_ROLE_OR_SCOPE_CONFLICT')
        return self.post(path,request)


def validate_fresh_entry(reader,journal,request,clock=now_ms):
    """Fresh execution gates for the exact immutable request; never reprice."""
    plan=journal.plan;s=journal.snapshot()
    if plan['blocked_reasons'] or s['entry_blocked'] or s['ownership_conflict']:raise SourceError('ENTRY_INHIBITED')
    sym=request['symbol'];leg=next(l for l in plan['legs'] if l['symbol']==sym)
    if request!=leg['request'] or 'stopLoss' not in request:raise SourceError('EXACT_NATIVE_GUARDED_REQUEST_REQUIRED')
    tasks=[('identity','/v5/user/query-api',{}),('account','/v5/account/info',{}),
        ('wallet','/v5/account/wallet-balance',dict(accountType='UNIFIED')),
        ('i','/v5/market/instruments-info',dict(category='linear',symbol=sym)),
        ('p','/v5/position/list',dict(category='linear',symbol=sym)),
        ('f','/v5/account/fee-rate',dict(category='linear',symbol=sym)),
        ('t','/v5/market/tickers',dict(category='linear',symbol=sym))]
    caps=batch_get(reader,tasks);r={k:reader.result(v) for k,v in caps.items()}
    if any(not (c['request_ms']<=c['receive_ms']<=clock()) for c in caps.values()):raise SourceError('FRESH_ACCOUNT_CLOCK_CONFLICT')
    perms=r['identity'].get('permissions',{}).get('ContractTrade',[])
    if type(r['identity'].get('readOnly')) is not int or r['identity']['readOnly']!=0 or not {'Order','Position'}<=set(perms):
        raise SourceError('ACCOUNT_TRADE_PERMISSION_UNKNOWN')
    if r['account'].get('marginMode')!='REGULAR_MARGIN' or r['account'].get('unifiedMarginStatus')!=5:
        raise SourceError('ACCOUNT_MODE_CONFLICT')
    def one(label):
        rs=r[label].get('list')
        if not isinstance(rs,list) or len(rs)!=1 or rs[0].get('symbol')!=sym:raise SourceError('AMBIGUOUS_SYMBOL_SOURCE')
        return rs[0]
    i,p,f,t=(one(k) for k in ('i','p','f','t'))
    if (i.get('contractType'),i.get('status'),i.get('quoteCoin'),i.get('settleCoin'),i.get('unifiedMarginTrade'))!=('LinearPerpetual','Trading','USDT','USDT',True):
        raise SourceError('INSTRUMENT_NOT_ELIGIBLE')
    if type(p.get('positionIdx')) is not int or p['positionIdx']!=0 or p.get('isReduceOnly') is not False or numeric(p['size'],zero=True)!=0:
        raise SourceError('ENTRY_SYMBOL_NOT_EXCLUSIVE_FLAT')
    q=numeric(request['qty']);price=numeric(request['price']);stop=numeric(request['stopLoss']);lot=i['lotSizeFilter'];tick=numeric(i['priceFilter']['tickSize'])
    if q<numeric(lot['minOrderQty']) or q>numeric(lot['maxOrderQty']) or q%numeric(lot['qtyStep']) or price%tick or stop%tick or q*price<numeric(lot['minNotionalValue']):
        raise SourceError('INSTRUMENT_SIZE_OR_TICK_CONFLICT')
    last=numeric(t['lastPrice'])
    if (stop>=last if request['side']=='Buy' else stop<=last):raise SourceError('NATIVE_STOP_ALREADY_CROSSED')
    fee=numeric(f['takerFeeRate'],zero=True)
    # Entire remaining basket is capital-backed; no configured leverage mutation.
    available=numeric(r['wallet']['list'][0]['totalAvailableBalance'],zero=True)
    remaining=sum((numeric(l['quantity'])*numeric(l['request']['price']) for l in plan['legs'] if l['symbol'] not in s['entries']),D(0))
    if available<remaining*(1+2*fee):raise SourceError('INSUFFICIENT_FULLY_FUNDED_AVAILABLE_BALANCE')
    books=batch_get(reader,[('book:'+x,'/v5/market/orderbook',dict(category='linear',symbol=x,limit='50')) for x in SYMBOLS])
    for x,cap in books.items():
        if reader.result(cap).get('s')!=x[5:]:raise SourceError('BOOK_IDENTITY_CONFLICT')
    timing=common_source_clock(list(books.values()),clock(),clock_captures=list(caps.values())+list(books.values()))
    if timing['status']!='OBSERVED_COMMON_2S_PASS':raise SourceError('COMMON_2S_BASKET_UNKNOWN')
    book=reader.result(books['book:'+sym]);levels=_levels(book['a'] if request['side']=='Buy' else book['b'],request['side']=='Sell')
    _,notional=_vwap(levels,q)
    # A moved book may reject this fixed IOC; it never authorizes repricing.
    if (levels[0][0]>price if request['side']=='Buy' else levels[0][0]<price):raise SourceError('EXACT_IOC_LIMIT_NOT_MARKETABLE')
    gross=sum((D(v['quantity'])*D(v['price']) for v in s['fills'].values() if v['kind']=='ENTRY_FILL'),D(0))
    pending=sum((numeric(l['quantity'])*numeric(l['request']['price']) for l in plan['legs'] if l['symbol'] not in s['entries'] and l['symbol']!=sym),D(0))
    if gross+notional+pending>D(plan['bounds']['max_gross_usdt']):raise SourceError('FRESH_GROSS_CAP_EXCEEDED')
    return dict(common_clock=timing,at_ms=clock(),source_sha256=digest(caps),book_sha256=digest(books))
