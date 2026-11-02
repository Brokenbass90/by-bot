"""Fixed public Polymarket DATA capture. No credentials, orders or strategy judge."""
import ast,base64,datetime as dt,fcntl,gzip,hashlib,io,json,os,re,shutil,socket,time,types,urllib.parse,urllib.request,uuid
from pathlib import Path

EPOCH='poly-ws-data-20261102'
URLS=dict(sports='wss://sports-api.polymarket.com/ws',clob='wss://ws-subscriptions-clob.polymarket.com/ws/market')
BUDGETS=dict(sports=128*2**20,clob=512*2**20,catalog=128*2**20)


class DataStop(BaseException):pass

def need(ok,why):
    if not ok:raise ValueError('POLY_DATA_'+why)
def clock():return time.time_ns()//1000000
def encoded(x):return (json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def sync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def mkdirs_durable(path):
    path=Path(path)
    if path.exists():need(path.is_dir() and not path.is_symlink(),'DIRECTORY_CUSTODY');return
    mkdirs_durable(path.parent)
    try:path.mkdir(mode=0o700)
    except FileExistsError:need(path.is_dir() and not path.is_symlink(),'DIRECTORY_CUSTODY')
    sync_dir(path);sync_dir(path.parent)
def sync_ancestors(path):
    path=Path(path).absolute()
    for folder in (path,*path.parents):sync_dir(folder)

def once(path,raw):
    path=Path(path);mkdirs_durable(path.parent)
    temp=path.with_name('.publish-'+uuid.uuid4().hex)
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.link(temp,path,follow_symlinks=False)
        fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
    finally:temp.unlink()
def replace(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex)
    once(tmp,encoded(value));os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def read(path,limit=8*2**20):
    p=Path(path);need(not p.is_symlink() and p.stat().st_size<=limit,'READ_BOUND')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        a=os.fstat(f.fileno());raw=f.read(limit+1);b=os.fstat(f.fileno())
    fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    need(len(raw)<=limit and fields(a)==fields(b)==fields(p.stat()),'READ_CHANGED');return raw


class SegmentStore:
    def __init__(self,root,role,*,epoch=EPOCH,clock=clock,min_free=2*2**30,max_total=None):
        need(role in BUDGETS and epoch==EPOCH,'STORE_SCOPE')
        self.root=Path(root).resolve();self.folder=self.root/role;self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.role,self.epoch,self.clock,self.min_free=role,epoch,clock,min_free
        self.max_total=max_total if max_total is not None else BUDGETS[role]
        self.fd=os.open(self.folder/'data.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:os.close(self.fd);raise
        self.file=None;self.session=uuid.uuid4().hex;self.index=0;self.rows=0;self.start=None;self.last=None;self.size=0;self.opened=self.clock();self.completed=0;self.status_clock=None;self.status_state=None;self.retention_mtime=None;self.terminal_state=None
        self.used=sum(p.stat().st_size for p in self.folder.rglob('*') if p.is_file())
        try:self._budget(0)
        except BaseException:os.close(self.fd);raise
    def _budget(self,extra):
        marker=self.folder/'retention-generation.json';stamp=marker.stat().st_mtime_ns if marker.exists() else None
        if stamp!=self.retention_mtime:
            self.used=sum(p.stat().st_size for p in self.folder.rglob('*') if p.is_file());self.retention_mtime=stamp
        if shutil.disk_usage(self.root).free<self.min_free or self.used+extra>self.max_total:
            raise DataStop('DATA_DISK_BUDGET_STOP')
    def status(self,state,**extra):
        if state.startswith('STOPPED'):self.terminal_state=state
        state=self.terminal_state or state
        self.status_clock=self.clock();self.status_state=state
        warning=['BACKLOG_75_PERCENT'] if self.used>=.75*self.max_total else []
        if shutil.disk_usage(self.root).free<3*2**30:warning.append('FREE_DISK_BELOW_3_GIB')
        replace(self.folder/'status.json',dict(schema='POLY_WS_DATA_STATUS_V1',role=self.role,epoch=self.epoch,pid=os.getpid(),session=self.session,observed_ms=self.clock(),state=state,warnings=warning,used_bytes=self.used,max_bytes=self.max_total,completed_segments=self.completed,unsealed_rows=self.rows,last_received_ms=self.last,venue_sequence_coverage='UNKNOWN',orders_allowed=False,**extra))
    def append(self,kind,payload,*,received_ms=None,monotonic_ns=None):
        now=self.clock();recv=now if received_ms is None else received_ms
        need(type(recv) is int and recv>0 and recv<=now,'RECEIVE_CLOCK')
        mono=time.monotonic_ns() if monotonic_ns is None else monotonic_ns
        need(type(mono) is int and mono>=0,'MONOTONIC_CLOCK')
        row=dict(schema='POLY_WS_RAW_V1',epoch=self.epoch,role=self.role,session=self.session,seq=self.rows,kind=kind,received_ms=recv,monotonic_ns=mono,payload=payload)
        raw=encoded(row);need(len(raw)<=8*2**20,'FRAME_BOUND')
        if self.file is not None and (self.size+len(raw)>2*2**20 or now-self.opened>=60000):self.seal();row['seq']=0;raw=encoded(row)
        # Cached role accounting; never scan archives for every market frame.
        self._budget(len(raw)+8192)
        if self.file is None:
            self.path=self.folder/(str(now)+'-'+self.session+'-'+str(self.index)+'.partial');self.index+=1
            self.file=self.path.open('xb',buffering=0);self.rows=0;self.size=0;self.start=recv;self.opened=now
        self.file.write(raw);self.rows+=1;self.size+=len(raw);self.used+=len(raw);self.last=recv
    def seal(self):
        if self.file is None:return None
        self.file.flush();os.fsync(self.file.fileno());self.file.close();self.file=None
        raw=read(self.path);compressed=gzip.compress(raw,compresslevel=3,mtime=0)
        self._budget(len(compressed)+8192)
        target=self.folder/'sealed'/(self.path.stem+'.jsonl.gz');once(target,compressed)
        seal=dict(schema='POLY_WS_SEGMENT_DELIVERY_V1',epoch=self.epoch,role=self.role,session=self.session,
            file=str(target.relative_to(self.root)),sha256=sha(compressed),bytes=len(compressed),raw_sha256=sha(raw),raw_bytes=len(raw),rows=self.rows,first_received_ms=self.start,last_received_ms=self.last,closed_ms=self.clock(),venue_sequence_coverage='UNKNOWN',orders_allowed=False)
        once(target.with_suffix(target.suffix+'.delivery.json'),encoded(seal))
        # Only this successfully compressed/sealed temporary file is removed. Crash partials are never repaired/deleted.
        self.path.unlink();self.rows=0;self.size=0;self.completed+=1
        self.used=sum(p.stat().st_size for p in self.folder.rglob('*') if p.is_file());self.status('RUNNING')
        return seal
    def checkpoint(self,state='RUNNING'):
        if self.file is not None and self.clock()-self.opened>=60000:self.seal()
        if self.status_clock is None or self.clock()-self.status_clock>=5000 or self.status_state!=state:self.status(state)
    def close(self,*,seal=True):
        try:
            if seal:self.seal()
            elif self.file:self.file.close();self.file=None
        finally:os.close(self.fd)


class FrozenSelection:
    def __init__(self,root,pins):
        root=Path(root);expected={'poly_monitor_minuty.py','poly_clob_ws_sbor.py','poly_sports_ws_sbor.py'}
        need(set(pins)==expected,'PROTOTYPE_SET');self.trees={}
        for name,pin in pins.items():
            raw=read(root/name);need(sha(raw)==pin,'PROTOTYPE_PIN');self.trees[name]=ast.parse(raw)
        nodes=[n for n in self.trees['poly_monitor_minuty.py'].body if isinstance(n,ast.FunctionDef) and n.name in ('iso','spisok') or isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in ('KRIPTO',) for x in n.targets) or isinstance(n,ast.Assign) and any(isinstance(x,ast.Tuple) and any(isinstance(y,ast.Name) and y.id=='MAKS_RYNKOV' for y in x.elts) for x in n.targets)]
        self.code=compile(ast.Module(body=nodes,type_ignores=[]),'frozen-monitor-selection','exec')
        self.token_code=compile(ast.Module(body=[n for n in self.trees['poly_clob_ws_sbor.py'].body if isinstance(n,ast.FunctionDef) and n.name=='tekushchie'],type_ignores=[]),'frozen-clob-membership','exec')
    def markets(self,now,fetch):
        ns=dict(dt=dt,re=re,urllib=urllib,P=types.SimpleNamespace(GAMMA='https://gamma-api.polymarket.com',get_json=fetch,js=lambda x:json.loads(x) if isinstance(x,str) else x))
        exec(self.code,ns);return ns['spisok'](dt.datetime.fromtimestamp(now/1000,dt.timezone.utc))
    def tokens(self,snapshot,now):
        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls,tz=None):return dt.datetime.fromtimestamp(now/1000,tz or dt.timezone.utc)
        rows=snapshot['markets'];need(isinstance(rows,list) and len(rows)<=150,'CATALOGUE_SIZE')
        text=''.join(json.dumps(dict(m,sob='dobavlen'))+'\n' for m in rows)
        ns=dict(dt=types.SimpleNamespace(datetime=FixedDateTime,timedelta=dt.timedelta,timezone=dt.timezone),json=json,RY=types.SimpleNamespace(open=lambda:io.StringIO(text)))
        exec(self.token_code,ns);active=ns['tekushchie']();tokens=[]
        for m in rows:
            if m['token'] in active:
                need(isinstance(m['tokens'],list) and len(m['tokens'])==2 and m['tokens'][0]==m['token'],'BOTH_OUTCOMES')
                tokens.extend(m['tokens'])
        need(all(isinstance(t,str) and re.fullmatch('[0-9]{1,100}',t) for t in tokens),'TOKEN_ID')
        return sorted(set(tokens))


def validate_get(url):
    u=urllib.parse.urlsplit(url);q=urllib.parse.parse_qs(u.query)
    need(u.scheme=='https' and u.netloc=='gamma-api.polymarket.com' and u.path=='/events' and not u.fragment
         and set(q)=={'active','closed','limit','offset','order','ascending'} and all(len(v)==1 for v in q.values())
         and q['active']==['true'] and q['closed']==['false'] and q['limit']==['100'] and q['order']==['volume']
         and q['ascending']==['false'] and q['offset'][0] in [str(x) for x in range(0,1000,100)],'PUBLIC_GET_SCOPE')
    return url


def validate_send(role,payload):
    if role=='sports':need(payload=='pong','SPORTS_SEND_SCOPE');return payload
    need(role=='clob','WS_ROLE')
    if payload=='PING':return payload
    x=json.loads(payload)
    need(isinstance(x,dict) and set(x)<={'type','assets_ids','operation','custom_feature_enabled'}
         and x.get('custom_feature_enabled') is True and isinstance(x.get('assets_ids'),list)
         and 0<len(x['assets_ids'])<=300 and all(isinstance(v,str) and re.fullmatch('[0-9]{1,100}',v) for v in x['assets_ids'])
         and ((x.get('type')=='market' and 'operation' not in x) or (x.get('operation') in ('subscribe','unsubscribe') and 'type' not in x)),'CLOB_SEND_SCOPE')
    return payload


def load_catalogue(root,now):
    raw=read(Path(root)/'catalog/current.json');x=json.loads(raw)
    need(type(x['generated_ms']) is int and 0<=now-x['generated_ms']<=2400000,'CATALOGUE_STALE_OR_FUTURE')
    return x,sha(raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise ValueError('POLY_DATA_REDIRECT_FORBIDDEN')


def update_catalogue(root,selection):
    s=SegmentStore(root,'catalog');meta={};failed=[];start=clock()
    def fetch(url):
        validate_get(url);request=clock()
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'TradingOS-DATA_ONLY/1'})
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=12) as response:
                need(response.status==200,'GAMMA_STATUS');raw=response.read(4*2**20+1)
            need(len(raw)<=4*2**20,'GAMMA_BODY_BOUND');receive=clock();body=json.loads(raw);need(isinstance(body,list),'GAMMA_SCHEMA')
            s.append('GET_RESPONSE',dict(url=url,request_ms=request,receive_ms=receive,raw=raw.decode()),received_ms=receive)
            for event in body:
                for m in event.get('markets') or []:
                    toks=m.get('clobTokenIds');toks=json.loads(toks) if isinstance(toks,str) else toks
                    if isinstance(toks,list) and len(toks)==2:meta[str(m.get('id'))]=[str(t) for t in toks]
            return body
        except Exception:failed.append(True);raise
    try:
        rows=selection.markets(start,fetch);need(not failed,'CATALOGUE_PARTIAL_SOURCE')
        need(len({str(m['id']) for m in rows})==len(rows),'CATALOGUE_DUPLICATE_ID')
        for m in rows:m['tokens']=meta[str(m['id'])]
        value=dict(schema='POLY_WS_CATALOG_V1',epoch=EPOCH,selection_started_ms=start,generated_ms=clock(),markets=rows,selection='UNCHANGED_PINNED_SPISOK_150',coverage='LIMITED_TOP1000_EVENTS_NOT_EXHAUSTIVE',orders_allowed=False)
        s.append('CATALOGUE',value);s.seal();replace(Path(root)/'catalog/current.json',value);s.status('CATALOGUE_CAPTURED');return value
    except Exception:
        s.status('STOPPED_CATALOGUE_SOURCE_ERROR');raise
    finally:s.close()


def run_worker(root,role,selection,*,connect=None):
    need(role in URLS,'ROLE')
    if connect is None:
        from websockets.sync.client import connect
    s=SegmentStore(root,role);s.append('PROCESS_START',dict(connection_gap_before_session='UNKNOWN',pid=os.getpid()))
    try:
        while True:
            connection=uuid.uuid4().hex
            try:
                tokens=[];catalog_sha=None
                if role=='clob':
                    cat,catalog_sha=load_catalogue(root,clock());tokens=selection.tokens(cat,clock())
                    if not tokens:s.checkpoint('WAIT_NO_ACTIVE_MARKETS');time.sleep(5);continue
                s.append('CONNECT_ATTEMPT',dict(connection=connection,url=URLS[role],catalogue_sha256=catalog_sha,tokens=tokens))
                with connect(URLS[role],open_timeout=15,close_timeout=5,ping_interval=None,max_size=4*2**20) as ws:
                    s.append('CONNECTED',dict(connection=connection))
                    if role=='clob':
                        msg=json.dumps(dict(assets_ids=tokens,type='market',custom_feature_enabled=True));ws.send(validate_send(role,msg));s.append('SEND',msg)
                    ping=refresh=last=time.monotonic()
                    while True:
                        now=time.monotonic()
                        if role=='clob' and now-ping>=10:ws.send(validate_send(role,'PING'));s.append('SEND','PING');ping=now
                        if role=='clob' and now-refresh>=300:
                            cat,new_sha=load_catalogue(root,clock());new=selection.tokens(cat,clock())
                            for op,ids in [('subscribe',sorted(set(new)-set(tokens))),('unsubscribe',sorted(set(tokens)-set(new)))]:
                                if ids:
                                    msg=json.dumps(dict(assets_ids=ids,operation=op,custom_feature_enabled=True));ws.send(validate_send(role,msg));s.append('SEND',msg)
                            tokens=new;catalog_sha=new_sha;refresh=now
                        try:frame=ws.recv(timeout=5)
                        except TimeoutError:
                            s.checkpoint()
                            if now-last>60:raise TimeoutError('FEED_HEARTBEAT_STALE')
                            continue
                        received=clock();mono=time.monotonic_ns();last=time.monotonic()
                        payload=frame if isinstance(frame,str) else dict(binary_base64=base64.b64encode(frame).decode())
                        s.append('RECV',dict(connection=connection,frame=payload,catalogue_sha256=catalog_sha),received_ms=received,monotonic_ns=mono)
                        if role=='sports' and frame=='ping':ws.send(validate_send(role,'pong'));s.append('SEND','pong')
                        s.checkpoint()
            except Exception as exc:
                s.append('DISCONNECTED',dict(connection=connection,error_type=type(exc).__name__,missing_messages='UNKNOWN'))
                s.seal();s.status('RECONNECTING_GAP_UNKNOWN',error_type=type(exc).__name__);time.sleep(10)
    except DataStop:
        s.status('STOPPED_DISK_OR_BUDGET');raise
    finally:s.close()
