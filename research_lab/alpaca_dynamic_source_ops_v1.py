"""Pinned original Dynamic59 DATA-ONLY source. No strategy/entry book or broker client."""
import fcntl,json,os,time,uuid
from pathlib import Path
from research_lab import alpaca_monthly_source_ops_v1 as ops
SCHEMA='ALPACA_DYNAMIC59_CLOSED_SOURCE_V1'
CAPTURE_SCHEMA='ALPACA_DYNAMIC59_HOURLY_CAPTURE_V1'
POLICY_PIN='fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d'


def required_symbols():
    p=json.loads((ops.ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_bytes())
    if ops.digest(p)!=POLICY_PIN:raise ValueError('DYNAMIC_POLICY_PIN')
    names=tuple(sorted(p['universe']))
    if len(names)!=59 or set(names)!=set(ops.required_symbols())|{'QQQ'}:raise ValueError('DYNAMIC_UNIVERSE_PIN')
    return names


def capture_full(directory,*,clock=lambda:time.time_ns()//1000000):
    return ops._capture_full(directory,symbols=required_symbols(),capture_schema=CAPTURE_SCHEMA,clock=clock)


def compile_source(directory,capture,calendar,*,now_ms):
    return ops._compile_source(directory,capture,calendar,now_ms=now_ms,symbols=required_symbols(),
                               capture_schema=CAPTURE_SCHEMA,output_schema=SCHEMA)


def seal_source(root,bundle):
    if (bundle.get('schema')!=SCHEMA or bundle.get('status')!='DATA_READY'
        or bundle.get('orders_allowed') is not False or bundle.get('money_authority') is not False
        or set(bundle.get('history',{}))!=set(required_symbols())
        or bundle.get('source_id')!=ops.digest({k:v for k,v in bundle.items() if k!='source_id'})):
        raise ValueError('DYNAMIC_SOURCE_CONFLICT')
    root=ops.safe_path(root);marker=root/'dynamic59-source-only.json';expected={'schema':SCHEMA,'money_authority':False}
    if root.exists() and any(root.iterdir()) and not marker.exists():raise ValueError('FOREIGN_RUNTIME_ROOT')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(root/'.writer.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    def put(path,raw):
        tmp=root/('.'+uuid.uuid4().hex+'.incomplete');out=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        try:
            with os.fdopen(out,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            os.link(tmp,path)
            d=os.open(root,os.O_RDONLY)
            try:os.fsync(d)
            finally:os.close(d)
        finally:tmp.unlink(missing_ok=True)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if marker.exists():
            if json.loads(ops.safe_path(marker).read_bytes())!=expected:raise ValueError('FOREIGN_RUNTIME_ROOT')
        else:put(marker,json.dumps(expected,sort_keys=True).encode())
        path=ops.safe_path(root/(bundle['signal_session']+'.json'))
        if path.exists():
            if json.loads(path.read_bytes())!=bundle:raise ValueError('SESSION_SOURCE_CONFLICT')
            return {'status':'DYNAMIC59_SOURCE_SEALED','source_id':bundle['source_id'],'already_sealed':True,'orders_allowed':False,'money_authority':False}
        put(path,(json.dumps(bundle,sort_keys=True,allow_nan=False)+'\n').encode())
        return {'status':'DYNAMIC59_SOURCE_SEALED','source_id':bundle['source_id'],'already_sealed':False,'orders_allowed':False,'money_authority':False}
    finally:os.close(fd)
