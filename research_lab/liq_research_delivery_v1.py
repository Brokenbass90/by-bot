"""Immutable DATA-ONLY delivery of the existing V2.1 epoch. No research judge.

Normalized bytes are never filtered/deduplicated. A last-published receipt seals
all sidecars; repeat delivery preserves bytes. Collector locks/files are read only.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl,hashlib,json,math,os,re,shutil,time,uuid
from pathlib import Path
from scripts.export_bybit_liquidation_v2_1 import export,encoded,sha

EPOCH='0688909d05884004b991bec76c6e4847'
MANIFEST='46895caaef1e1689cd4224a544bb3e3287f41ef8a8a4ad702fd403cdcc2a4ddd'
SYMBOLS=tuple('BTCUSDT ETHUSDT SOLUSDT ZECUSDT NEARUSDT XRPUSDT HYPEUSDT STRKUSDT BTWUSDT ENAUSDT SUIUSDT WLDUSDT OPUSDT QNTUSDT ADAUSDT DOGEUSDT PUMPFUNUSDT 1000PEPEUSDT UNIUSDT TRUTHUSDT INJUSDT TIAUSDT BATUSDT ONDOUSDT OGNUSDT'.split())
SCHEMA='LIQ_RESEARCH_IMMUTABLE_DELIVERY_V1'


def safe(path):
    p=Path(path).absolute()
    if any(q.is_symlink() for q in (p,*p.parents)):raise ValueError('SYMLINK_PATH')
    return p


def load(path):return json.loads(safe(path).read_bytes())
def hashed(path):
    h=hashlib.sha256()
    with safe(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def check_self(x,key):
    if x.get(key)!=sha(encoded({k:v for k,v in x.items() if k!=key})):raise ValueError('SELF_HASH_CONFLICT')


def publish(path,raw):
    path=safe(path)
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('IMMUTABLE_FILE_CONFLICT')
        return
    tmp=path.parent/('.'+path.name+'.'+uuid.uuid4().hex+'.incomplete')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        try:os.link(tmp,path)
        except FileExistsError:
            if path.read_bytes()!=raw:raise ValueError('IMMUTABLE_FILE_CONFLICT')
        d=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:tmp.unlink(missing_ok=True)


def copy_stream(source,target,pin):
    source=safe(source);target=safe(target)
    if target.exists():
        if hashed(target)!=pin:raise ValueError('IMMUTABLE_FILE_CONFLICT')
        return
    tmp=target.parent/('.'+target.name+'.'+uuid.uuid4().hex+'.incomplete')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    try:
        h=hashlib.sha256()
        with os.fdopen(fd,'wb') as out,source.open('rb') as stream:
            for part in iter(lambda:stream.read(1048576),b''):out.write(part);h.update(part)
            out.flush();os.fsync(out.fileno())
        if h.hexdigest()!=pin:raise ValueError('COPY_SOURCE_CHANGED')
        try:os.link(tmp,target)
        except FileExistsError:
            if hashed(target)!=pin:raise ValueError('IMMUTABLE_FILE_CONFLICT')
        d=os.open(target.parent,os.O_RDONLY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:tmp.unlink(missing_ok=True)


@contextmanager
def locked(root):
    root=safe(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(root/'.delivery.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
    finally:os.close(fd)


def names(day):
    if not re.fullmatch(r'\d{8}',day):raise ValueError('UTC_DAY_REQUIRED')
    datetime.strptime(day,'%Y%m%d')
    stem='normalized-'+day
    return [stem+s for s in ('.jsonl','.receipt.json','.heartbeat.json','.qa.json')],stem+'.delivery.json'


def identity(x):
    if (x.get('epoch_id')!=EPOCH or x.get('source_manifest_sha256')!=MANIFEST
        or tuple(x.get('symbols',()))!=SYMBOLS):raise ValueError('SOURCE_EPOCH_OR_UNIVERSE_CONFLICT')


def verify_snapshot(directory,day):
    directory=safe(directory);files,last=names(day);seal=load(directory/last)
    check_self(seal,'delivery_sha256');identity(seal)
    if (seal.get('schema')!=SCHEMA or seal.get('day_utc')!=day or set(seal.get('files',{}))!=set(files)
        or seal.get('orders_allowed') is not False or seal.get('source_gate_pass') is not False):raise ValueError('DELIVERY_CONTRACT')
    for name,pin in seal['files'].items():
        if hashed(directory/name)!=pin:raise ValueError('SNAPSHOT_FILE_HASH_CONFLICT')
    receipt=load(directory/files[1]);check_self(receipt,'receipt_sha256');identity(receipt)
    heartbeat=load(directory/files[2]);check_self(heartbeat,'heartbeat_sha256');identity(heartbeat)
    if receipt['normalized_sha256']!=seal['files'][files[0]] or receipt['event_count']!=seal['event_count']:
        raise ValueError('NORMALIZED_RECEIPT_CONFLICT')
    return seal


def qa_prefixes(root,receipt):
    controls=[];latency=Counter();flags=Counter();counts=Counter();first=last=None;events=0
    for name,pin in receipt['source_prefixes'].items():
        if not re.fullmatch(r'runs/[0-9a-z-]+/frames.jsonl',name):raise ValueError('RAW_PREFIX_PATH')
        remaining=pin['bytes'];h=hashlib.sha256();previous='0'*64
        with safe(root/name).open('rb') as f:
            while remaining:
                line=f.readline(min(remaining,16*1024**2)+1)
                if not line.endswith(b'\n') or len(line)>remaining:raise ValueError('RAW_PREFIX_PARTIAL')
                remaining-=len(line);h.update(line);r=json.loads(line)
                check_self(r,'record_sha256')
                if r['prev_sha256']!=previous or r['source_manifest_sha256']!=MANIFEST:raise ValueError('RAW_CHAIN_CONFLICT')
                previous=r['record_sha256']
                if r['kind']!='FRAME' or r.get('qa_flags'):
                    controls.append({k:v for k,v in r.items() if k not in ('raw_text','raw_base64','normalized_events')})
                for z in r.get('normalized_events',[]):
                    if z['source_manifest_sha256']!=MANIFEST or z['symbol'] not in SYMBOLS:raise ValueError('EVENT_SOURCE_CONFLICT')
                    available=z['t_available_ms'];stamp=z['ts_ms']
                    if type(available) is not int or type(stamp) is not int:raise ValueError('EVENT_CLOCK_SCHEMA')
                    latency[available-stamp]+=1;flags.update(z.get('qa_flags',[]));counts[z['symbol']]+=1;events+=1
                    first=available if first is None else min(first,available);last=available if last is None else max(last,available)
        if h.hexdigest()!=pin['sha256'] or previous!=pin['tip']:raise ValueError('RAW_PREFIX_HASH_CONFLICT')
    if events!=receipt['event_count']:raise ValueError('EVENT_COUNT_CONFLICT')
    def percentile(fraction):
        threshold=math.ceil(events*fraction);n=0
        for value,count in sorted(latency.items()):
            n+=count
            if n>=threshold:return value
        return None
    return {'schema':'LIQ_SOURCE_QA_SIDECAR_V1','epoch_id':EPOCH,'source_manifest_sha256':MANIFEST,
      'normalized_events':events,'symbol_event_counts':dict(counts),'first_available_ms':first,'last_available_ms':last,
      'latency_ms':{'p50':percentile(.5),'p90':percentile(.9),'max':max(latency) if latency else None,
                    'negative_count':sum(n for x,n in latency.items() if x<0)},
      'event_qa_flags':dict(flags),'controls':controls,
      'gap_records':sum(r['kind'] in ('OBSERVATION_GAP','PROCESS_RESTART_GAP') for r in controls),
      'coverage':'UNKNOWN_NO_SEQUENCE_OR_BACKFILL','gap_hours':'UNKNOWN_NEVER_ZERO_FILL',
      'prospective_decisions':0,'base_events':'NOT_COMPUTED','source_gate_pass':False,'orders_allowed':False}


def seal_daily(root,day,*,now_ms=None):
    root=safe(root);now=time.time_ns()//1000000 if now_ms is None else now_ms
    files,last=names(day)
    if datetime.fromtimestamp(now/1000,timezone.utc).strftime('%Y%m%d')!=day:raise ValueError('NO_BACKDATED_EXPORT')
    manifest=load(root/'source-manifest.json');check_self(manifest,'manifest_sha256')
    identity({**manifest,'source_manifest_sha256':manifest['manifest_sha256']})
    directory=safe(root/'exports')
    with locked(directory):
        if (directory/last).exists():return {**verify_snapshot(directory,day),'already_sealed':True}
        # A cumulative normalized export is bounded above by its raw journal.
        # Preserve the collector's own free-space reserve; never delete evidence.
        raw_bytes=sum(p.stat().st_size for p in root.glob('runs/*/frames.jsonl'))
        reserve=manifest['min_free_bytes']
        if type(reserve) is not int or reserve<0 or shutil.disk_usage(root).free<reserve+raw_bytes+8*1024**2:
            raise ValueError('EXPORT_DISK_BUDGET_BLOCKED')
        target=directory/files[0];receipt_path=directory/files[1]
        if target.exists()!=receipt_path.exists():raise ValueError('PARTIAL_EXPORT_REQUIRES_READ_ONLY_RECONCILIATION')
        receipt=load(receipt_path) if target.exists() else export(root,target)
        check_self(receipt,'receipt_sha256');identity(receipt)
        if hashed(target)!=receipt['normalized_sha256']:raise ValueError('NORMALIZED_HASH_CONFLICT')
        heartbeat_path=directory/files[2]
        heartbeat=load(heartbeat_path) if heartbeat_path.exists() else load(root/'heartbeat.json')
        check_self(heartbeat,'heartbeat_sha256');identity(heartbeat)
        publish(heartbeat_path,encoded(heartbeat)+b'\n')
        qa_path=directory/files[3]
        if not qa_path.exists():publish(qa_path,encoded(qa_prefixes(root,receipt))+b'\n')
        qa=load(qa_path)
        if qa['normalized_events']!=receipt['event_count'] or qa['source_manifest_sha256']!=MANIFEST:raise ValueError('QA_CONFLICT')
        result={'schema':SCHEMA,'day_utc':day,'epoch_id':EPOCH,'source_manifest_sha256':MANIFEST,'symbols':list(SYMBOLS),
          'seal_started_ms':now,'sealed_ms':time.time_ns()//1000000 if now_ms is None else now,
          'exported_ms':receipt['exported_ms'],'event_count':receipt['event_count'],
          'files':{n:hashed(directory/n) for n in files},'coverage':'UNKNOWN_NO_SEQUENCE_OR_BACKFILL',
          'heartbeat_is_point_sample':True,'source_gate_pass':False,'prospective_decisions':0,'orders_allowed':False}
        result['delivery_sha256']=sha(encoded(result));publish(directory/last,encoded(result)+b'\n')
        return {**verify_snapshot(directory,day),'already_sealed':False}


def import_snapshot(exports,destination,day):
    exports=safe(exports);destination=safe(destination);seal=verify_snapshot(exports,day)
    files,last=names(day)
    with locked(destination):
        if (destination/last).exists():
            if verify_snapshot(destination,day)!=seal:raise ValueError('DELIVERY_IDENTITY_CONFLICT')
            return {**seal,'already_imported':True}
        # Validate every existing partial file before making any new one.
        for name in [*files,last]:
            p=safe(destination/name)
            if p.exists() and hashed(p)!=hashed(exports/name):raise ValueError('IMMUTABLE_FILE_CONFLICT')
        for name in [*files,last]:copy_stream(exports/name,destination/name,hashed(exports/name))
        verify_snapshot(destination,day)
        return {**seal,'already_imported':False}
