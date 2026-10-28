"""Trusted GET-only provider for the already selected PUMP financial owner.

No credential discovery, account lease, authority creation or broker mutation.
Fresh account evidence is collected in parallel, never refreshed by relabelling.
The existing DATA journal is read without repair; real closed-H1 GETs must replay
its exact decision before selected_tick can admit any new entry.
"""
from concurrent.futures import ThreadPoolExecutor
import copy,hashlib,os,stat,time,base64,gzip,io,json
from pathlib import Path
from research_lab.alpaca_dynamic_v1 import digest,canonical
from research_lab.kity_micro_transport_v1 import BybitReadTransport,wire_get
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_oct15_deadline_v1 import stable_bytes,decode
from research_lab.pump4_account_owner_v1 import safe
from research_lab.pump4_account_adapter_v1 import frozen_plan,time_windows
from research_lab.pump4_bybit_sources_v1 import public_get,checked,account_view,universe,UNIVERSE_SHA,H
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_selected_runner_v1 import causal_plan


def need(ok,why):
    if not ok:raise ValueError('PUMP4_RUNTIME_SOURCE_'+why)


def publish_capture(path,value):
    raw=canonical(value)
    publish(path,dict(schema='PUMP4_LOSSLESS_GET_ARCHIVE_V1',codec='gzip-base64',uncompressed_bytes=len(raw),uncompressed_sha256=hashlib.sha256(raw).hexdigest(),payload=base64.b64encode(gzip.compress(raw,compresslevel=3,mtime=0)).decode()))

def load_capture(path,*,max_bytes=20000000):
    need(type(max_bytes) is int and 0<max_bytes<=20000000,'ARCHIVE_CONFIG_BOUND')
    path=safe(path);limit=2*max_bytes+4096
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=observation_identity(os.fstat(fd));need(before[2]<=limit,'ARCHIVE_INPUT_BOUND')
        with os.fdopen(os.dup(fd),'rb') as f:encoded=f.read(limit+1)
        need(len(encoded)==before[2] and len(encoded)<=limit and before==observation_identity(os.fstat(fd))==observation_identity(path.lstat()),'ARCHIVE_CHANGED_OR_OVERSIZED')
    finally:os.close(fd)
    value=decode(encoded)
    if value.get('schema')!='PUMP4_LOSSLESS_GET_ARCHIVE_V1':
        need(len(encoded)<=max_bytes,'ARCHIVE_LEGACY_BOUND');return value
    need(value['codec']=='gzip-base64' and type(value['uncompressed_bytes']) is int and 0<value['uncompressed_bytes']<=max_bytes,'ARCHIVE_DECODE_BOUND')
    try:
        compressed=base64.b64decode(value['payload'],validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed),mode='rb') as f:raw=f.read(max_bytes+1)
    except (ValueError,OSError,EOFError) as e:raise ValueError('PUMP4_RUNTIME_SOURCE_ARCHIVE_DECODE') from e
    need(len(raw)==value['uncompressed_bytes'] and len(raw)<=max_bytes and hashlib.sha256(raw).hexdigest()==value['uncompressed_sha256'],'ARCHIVE_HASH_OR_SIZE')
    return decode(raw)


def observation_identity(st):
    need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.getuid(),'OBSERVATION_CUSTODY')
    return tuple(getattr(st,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_gid','st_mode','st_nlink'))


def observation_bytes(path):
    # Identity comes from the SAME open file as the bytes, including a final
    # path comparison. Replacement during the read cannot prime the cache.
    fd=os.open(safe(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=observation_identity(os.fstat(fd));need(before[2]<=5000000,'OBSERVATION_BOUND')
        raw=bytearray()
        while True:
            chunk=os.read(fd,min(1048576,5000001-len(raw)))
            if not chunk:break
            raw.extend(chunk);need(len(raw)<=5000000,'OBSERVATION_BOUND')
        need(before==observation_identity(os.fstat(fd))==observation_identity(path.lstat())
            and len(raw)==before[2],'OBSERVATION_CHANGED')
        return bytes(raw),before
    finally:os.close(fd)


class TrustedSources:
    def __init__(self,config,owner,*,wire=None,clock=None):
        self.config=copy.deepcopy(config);self.config_sha=digest(config)
        self.owner=owner;self.clock=clock or owner.clock
        self._wire=wire or wire_get
        self.reader=BybitReadTransport(owner.key,owner.secret,wire=self.get_wire,
            clock=self.clock,symbols=universe())
        need(self.reader.account_fingerprint==owner.scope['account_fingerprint'],'ACCOUNT_BINDING')
        need(config.get('execution_policy')==owner.scope.get('execution_policy'),'EXECUTION_POLICY_BINDING')
        self._candidate_consumed=set()
        self._negative_observations={};self._negative_clock=None

    def get_wire(self,method,url,headers,data,timeout):
        need(method=='GET' and data is None,'GET_ONLY')
        return self._wire(method,url,headers,None,min(timeout,3))

    def _read(self,spec):
        name,path,params,paged=spec
        cap=self.reader.pages(path,params) if paged else self.reader.get(path,params)
        if paged:need(cap.get('complete') is True,'INCOMPLETE_'+name.upper())
        for row in cap.get('pages',[cap]):
            self.reader.result(row)
            if row['signed']:row['account_fingerprint']=self.reader.account_fingerprint
        return name,cap

    def _instruments(self):
        pages=[];cursor='';seen=set()
        for _ in range(8):
            cap=public_get('/v5/market/instruments-info',dict(category='linear',limit=1000,
                **({'cursor':cursor} if cursor else {})),wire=self.get_wire,clock=self.clock)
            result=checked(cap,'/v5/market/instruments-info',now_ms=self.clock(),private=False)
            pages.append(cap);cursor=result.get('nextPageCursor','')
            need(isinstance(cursor,str) and cursor not in seen,'INSTRUMENT_CURSOR')
            if not cursor:return dict(complete=True,pages=pages)
            seen.add(cursor)
        raise ValueError('PUMP4_RUNTIME_SOURCE_INSTRUMENT_PAGE_BOUND')

    def account(self,plan,*,custody):
        need(type(custody) is bool and digest(self.config)==self.config_sha,'CONFIG_OR_MODE')
        frozen_plan(plan);symbol=plan['symbol'];need(symbol in universe(),'SYMBOL')
        return self._capture(symbol,plan['entry_bar_open_ms'],custody=custody)

    def flat(self,*,metadata_symbol=None):
        """Recent account-only handoff evidence, never a relabelled signal plan."""
        from research_lab.pump4_bybit_sources_v1 import flat_account
        bundle,public=self._capture(None,self.clock()-H,custody=True,metadata_symbol=metadata_symbol)
        flat_account(bundle,expected_fingerprint=self.reader.account_fingerprint,now_ms=self.clock())
        return bundle,public

    def _capture(self,symbol,begin,*,custody,metadata_symbol=None):
        need(digest(self.config)==self.config_sha,'CONFIG_OR_MODE')
        selected=symbol if symbol is not None else metadata_symbol
        need(selected is None or selected in universe(),'METADATA_SYMBOL_SCOPE')
        params=dict(category='linear',**({'symbol':selected} if selected else {}))
        start=self.clock();windows=time_windows(begin,start)
        specs=[('account','/v5/account/info',{},False),
            ('wallet','/v5/account/wallet-balance',dict(accountType='UNIFIED'),False),
            ('fees','/v5/account/fee-rate',params,False),
            ('positions','/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),True),
            ('orders','/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),True),
            ('quote','/v5/market/tickers',params,False)]
        if not custody:specs.append(('symbol_position','/v5/position/list',dict(category='linear',symbol=symbol),False))
        for index,(lo,hi) in enumerate(windows):
            for key,path,limit,extra in [('history','/v5/order/history','50',{}),
                ('executions','/v5/execution/list','100',{}),
                ('transactions','/v5/account/transaction-log','50',dict(accountType='UNIFIED',currency='USDT'))]:
                specs.append((str(index)+':'+key,path,dict(category='linear',startTime=str(lo),endTime=str(hi),limit=limit,**extra),True))
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures=[pool.submit(self._read,spec) for spec in specs]
            instruments=pool.submit(self._instruments) if not custody else None
            caps=dict(f.result() for f in futures)
            metadata=instruments.result() if instruments is not None else None
        groups=[dict(start_ms=lo,end_ms=hi,groups={k:caps.pop(str(i)+':'+k) for k in ('history','executions','transactions')}) for i,(lo,hi) in enumerate(windows)]
        end=self.clock()
        bundle=dict(schema='PUMP4_ACCOUNT_GET_CAPTURE_V1',started_ms=start,completed_ms=end,
            account_fingerprint=self.reader.account_fingerprint,captures=caps,
            history_start_ms=begin,history_end_ms=start,history_windows=groups)
        # Do not silently cache stale/partial evidence or use empty pages as fees finality.
        account_view(bundle,expected_fingerprint=self.reader.account_fingerprint,now_ms=end)
        public=dict(quote=caps['quote'])
        if metadata is not None:public['instruments']=metadata
        if not custody and self.config.get('execution_policy') is not None:
            public['entry_interval']=public_get('/v5/market/kline',dict(category='linear',symbol=symbol,interval='60',start=begin,end=begin+H-1,limit=1),wire=self.get_wire,clock=self.clock)
            end=self.clock();bundle['completed_ms']=end
            account_view(bundle,expected_fingerprint=self.reader.account_fingerprint,now_ms=end)
        stored=dict(bundle=bundle,public=public,custody=custody,broker_writes=0)
        target=safe(self.owner.root/'source-captures'/(str(end)+'-'+digest(stored)+'.json'))
        if target.exists():need(load_capture(target)==stored,'IMMUTABLE_SOURCE_CONFLICT')
        else:publish_capture(target,stored)
        return bundle,public

    def _data(self):
        need(digest(self.config)==self.config_sha,'CONFIG_CHANGED')
        data=self.config.get('data_source')
        need(isinstance(data,dict) and set(data)=={'root','binding'},'DATA_BINDING_REQUIRED')
        need(Path(data['root']).is_absolute(),'DATA_BINDING_ROOT')
        root=safe(data['root']);pin=data['binding'];path=safe(pin['path'])
        need(path==root/'data-binding.json','DATA_BINDING_PATH')
        raw=stable_bytes(path);need(hashlib.sha256(raw).hexdigest()==pin['sha256'],'DATA_BINDING_PIN')
        bound=decode(raw)
        need(bound['schema']=='PUMP4_DATA_SUPERVISOR_V1' and bound['universe_sha256']==UNIVERSE_SHA
            and bound['orders_allowed'] is False and bound['money_authority'] is False,'DATA_BINDING_SCOPE')
        files=bound['source_files'];app=root.parent.parent
        need({'research_lab/pump4_closed_bar_intake_v1.py','research_lab/pump4_supervisor_v1.py',
            'strategies/pump_fade_v4r.py','strategies/signals.py'}.issubset(files),'DATA_SOURCE_CLOSURE')
        for name,pin in files.items():
            src=safe(app/name);need(src.is_relative_to(app) and hashlib.sha256(stable_bytes(src)).hexdigest()==pin,'DATA_SOURCE_DRIFT')
        return root

    def candidate(self):
        root=self._data();now=self.clock();epoch=self.config['epoch_started_ms'];delay=self.config['entry_max_delay_ms']
        need(type(epoch) is int and type(delay) is int and 0<delay<=60000,'EPOCH_OR_DELAY')
        directory=safe(root/'observations')
        files=list(directory.glob('*.json'));need(len(files)<=20000,'OBSERVATION_BOUND')
        if self._negative_clock is not None and now<self._negative_clock:self._negative_observations.clear()
        self._negative_clock=now
        present=set(files);self._negative_observations={p:v for p,v in self._negative_observations.items() if p in present}
        eligible=[]
        for path in files:
            identity=observation_identity(path.lstat());cached=self._negative_observations.get(path)
            if cached is not None and cached[0]==identity and (cached[1] is None or now>cached[1]):continue
            raw,identity=observation_bytes(path);row=decode(raw);d=row['decision']
            need(row['orders_allowed'] is False and row['money_authority'] is False,'OBSERVATION_AUTHORITY')
            entry=d['bar_open_ms']+H
            if (row['mode']!='CURRENT_CLOSED_BAR' or d['signal'] is None
                or d['decision_id'] in self._candidate_consumed or not epoch<=d['first_observed_ms']<=now
                or not epoch<=entry or not 0<=now-entry<=delay):
                # A cache hit may ONLY suppress a fully validated negative.
                # Current/future/consumed positive signals are never admitted
                # or permanently hidden using metadata instead of source reads.
                if d.get('signal',False) is None or now>entry+delay:
                    self._negative_observations[path]=(identity,None if d.get('signal',False) is None else entry+delay)
                continue
            need(d['symbol'] in universe() and path.name==d['decision_id']+'.json','OBSERVATION_IDENTITY')
            eligible.append(d)
        if not eligible:return None
        decision=min(eligible,key=lambda d:(d['first_observed_ms'],d['symbol'],d['decision_id']))
        symbol=decision['symbol'];entry=decision['bar_open_ms']+H
        path=safe(root/'intake'/(symbol+'.jsonl'));need(path.is_file(),'EXISTING_JOURNAL_REQUIRED')
        intake=Pump4Intake(path,symbol)
        # A fresh network read can verify an old decision; it cannot make its
        # first-observed time, bootstrap status or entry window new.
        first=entry-1001*H
        requests=[dict(category='linear',symbol=symbol,interval='60',start=first,end=entry+H-1,limit=1000),
            dict(category='linear',symbol=symbol,interval='60',start=first,end=entry-999*H-1,limit=1000)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            captures=list(pool.map(lambda q:public_get('/v5/market/kline',q,wire=self.get_wire,clock=self.clock),requests))
        causal_plan(intake,decision['decision_id'],captures,epoch_started_ms=epoch,max_delay_ms=delay,now_ms=self.clock())
        self._candidate_consumed.add(decision['decision_id'])
        return dict(intake=intake,decision_id=decision['decision_id'],captures=captures)

    def alert(self,event):
        """Only the existing, explicitly pinned Telegram-only sender."""
        from datetime import datetime,timezone
        from research_lab.pump4_selected_runner_v1 import pinned
        from research_lab.alpaca_day_monitor_v1 import telegram
        need(digest(self.config)==self.config_sha and self.config.get('notifications') is not None,'NOTIFICATION_BINDING')
        config=pinned(self.config['notifications'])
        need(config.get('scope_label')=='Trading OS PUMP4'
            and safe(config['output_root']).is_relative_to(self.owner.root),'NOTIFICATION_SCOPE')
        stamp=datetime.fromtimestamp(self.clock()/1000,timezone.utc).date().isoformat()
        message=dict(kind='PUMP4_EXECUTION',session=stamp,first_evidence_id=event['terminal_id'],
            issues=[dict(code=event['status'])],mode=self.config.get('mode'),
            actual_protection_proven=False,broker_writes=0)
        return telegram(config,message)
