"""One fixed Oct15 source deadline observation; no network, shadow import or PnL.

The observer cannot approve a producer version or create a snapshot. It requires
an independently reviewed publisher receipt and never rewrites a terminal result.
"""
import datetime as dt,fcntl,hashlib,json,math,os,uuid
from pathlib import Path

DAY='2026-10-15'
END=int(dt.datetime(2026,10,15,tzinfo=dt.timezone.utc).timestamp()*1000)
START=END-600000


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

def path(value):
    p=Path(value)
    if not p.is_absolute() or '..' in p.parts or any(x.is_symlink() for x in (p,*p.parents)):raise ValueError('PATH_CUSTODY')
    if p.exists() and (not p.is_file() or p.stat().st_nlink!=1 or p.stat().st_uid!=os.getuid()):raise ValueError('PATH_CUSTODY')
    return p


def stable_bytes(p):
    p=path(p)
    before=p.stat();raw=p.read_bytes();after=p.stat()
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_nlink)
    if identity(before)!=identity(after):raise ValueError('SOURCE_CHANGED_DURING_READ')
    return raw


def decode(raw):
    def pairs(rows):
        if len(dict(rows))!=len(rows):raise ValueError('MALFORMED_SOURCE')
        return dict(rows)
    return json.loads(raw,object_pairs_hook=pairs)


def read(p):return decode(stable_bytes(p))


def fsync_dir(p):
    fd=os.open(p,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def publish_once(p,raw):
    """Full fsynced temp -> atomic no-overwrite hard link -> unlink -> dir fsync.

    A crash before link leaves no final file. A crash after link can leave a
    complete two-link file: custody then BLOCKS; no silent repair is performed.
    """
    p=path(p);p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=p.with_name('.'+p.name+'.tmp-'+uuid.uuid4().hex)
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        view=memoryview(raw)
        while view:
            n=os.write(fd,view)
            if n<=0:raise OSError('INCOMPLETE_WRITE')
            view=view[n:]
        os.fsync(fd);os.close(fd);fd=None
        os.link(tmp,p,follow_symlinks=False)  # atomic EEXIST, never replaces p
        tmp.unlink();fsync_dir(p.parent)
    finally:
        if fd is not None:os.close(fd)
        if tmp.exists():tmp.unlink()


def inspect(cfg):
    if cfg.get('approval_scope')!='SOURCE_ONLY_NO_STRATEGY_CHANGE':raise ValueError('PRODUCER_APPROVAL_PENDING')
    producer=path(cfg['producer_path'])
    if sha(stable_bytes(producer))!=cfg['producer_sha256']:raise ValueError('PRODUCER_SOURCE_DRIFT')
    p=path(cfg['snapshot_path']);r=path(cfg['publisher_receipt_path'])
    if not p.exists():raise ValueError('SNAPSHOT_MISSING')
    # Parse first: malformed evidence is explicit, not repaired or zeroed.
    try:
        snapshot_raw=stable_bytes(p);s=decode(snapshot_raw)
    except (json.JSONDecodeError,UnicodeError):raise ValueError('MALFORMED_SOURCE') from None
    if not r.exists():raise ValueError('PUBLISHER_RECEIPT_MISSING')
    receipt_raw=stable_bytes(r);receipt=decode(receipt_raw)
    if receipt.get('day')!=DAY:raise ValueError('CAPTURE_DAY_CONFLICT')
    if receipt.get('status')!='CAPTURE_PASS':raise ValueError('PUBLISHER_NOT_PASS')
    if receipt.get('producer_sha256')!=cfg['producer_sha256']:raise ValueError('PRODUCER_SOURCE_DRIFT')
    completed=receipt.get('completed_ms')
    if type(completed) is not int or not START<=completed<END:raise ValueError('PUBLICATION_OUTSIDE_WINDOW')
    capture=receipt.get('capture_ms')
    if type(capture) is not int or not START<=capture<=completed:raise ValueError('CAPTURE_OUTSIDE_WINDOW')
    raw_hash=sha(snapshot_raw)
    if receipt.get('snapshot_sha256')!=raw_hash:raise ValueError('SNAPSHOT_PIN_CONFLICT')
    try:
        stamp=dt.datetime.fromisoformat(s['vremya'].replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError()
        ms=int(stamp.timestamp()*1000)
    except (KeyError,ValueError,TypeError):raise ValueError('SNAPSHOT_OUTSIDE_WINDOW') from None
    if not START<=ms<=completed<END:raise ValueError('SNAPSHOT_OUTSIDE_WINDOW')
    if not ms<=capture<ms+1000 or s.get('capture_ms')!=capture:raise ValueError('CAPTURE_OUTSIDE_WINDOW')
    raw_dir=Path(cfg['source_raw_dir'])
    expected=f'popytki/tickers_{capture}.raw'
    if (raw_dir!=p.parent/'popytki' or receipt.get('source_raw')!=expected):raise ValueError('RAW_SOURCE_PATH_CONFLICT')
    raw_path=path(str(raw_dir/f'tickers_{capture}.raw'))
    if not raw_path.exists():raise ValueError('TICKER_RAW_MISSING')
    source_hash=sha(stable_bytes(raw_path))
    if source_hash!=receipt.get('source_sha256') or source_hash!=s.get('sha256_tickers'):raise ValueError('RAW_SOURCE_PIN_CONFLICT')
    oi=s.get('oi_usd')
    if not isinstance(oi,dict) or not oi or s.get('oi_otsutstvuet'):raise ValueError('SNAPSHOT_OI_UNKNOWN')
    for value in oi.values():
        try:v=float(value)
        except (ValueError,TypeError):raise ValueError('SNAPSHOT_OI_UNKNOWN') from None
        if isinstance(value,bool) or not math.isfinite(v) or v<0:raise ValueError('SNAPSHOT_OI_UNKNOWN')
    return dict(snapshot_sha256=raw_hash,publisher_receipt_sha256=sha(receipt_raw),
        source_sha256=source_hash,source_raw=expected,capture_ms=capture,snapshot_ms=ms,completed_ms=completed)


def existing_receipt(out):
    r=read(out);body={k:v for k,v in r.items() if k!='receipt_sha256'}
    if (r.get('schema')!='KITY_OCT15_SOURCE_DEADLINE_RECEIPT_V1' or r.get('day')!=DAY
        or r.get('window_start_ms')!=START or r.get('window_end_ms')!=END
        or r.get('status') not in ('CAPTURE_OBSERVATION_PASS','CAPTURE_BLOCKED')
        or any(r.get(k) is not False for k in ('orders_allowed','money_ready','c1_pass','c2_pass','pnl_interpretation'))
        or r.get('receipt_sha256')!=sha(canonical(body))):raise ValueError('EXISTING_RECEIPT_CONFLICT')
    return r


def run_once(cfg,*,now_ms):
    if cfg['schema']!='KITY_OCT15_DEADLINE_OBSERVER_V1' or cfg['day']!=DAY:raise ValueError('FIXED_OCT15_ONLY')
    if type(now_ms) is not int:raise ValueError('CLOCK_REQUIRED')
    if now_ms<END:return dict(status='WATCH_PENDING',day=DAY,deadline_ms=END,orders_allowed=False)
    out=path(cfg['output_path']);out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(out.with_name('.observer.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if out.exists():return existing_receipt(out)
        r=dict(schema='KITY_OCT15_SOURCE_DEADLINE_RECEIPT_V1',day=DAY,window_start_ms=START,window_end_ms=END,
            observed_ms=now_ms,producer_sha256=cfg.get('producer_sha256'),
            orders_allowed=False,money_ready=False,c1_pass=False,c2_pass=False,pnl_interpretation=False)
        try:r.update(status='CAPTURE_OBSERVATION_PASS',**inspect(cfg))
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError) as e:r.update(status='CAPTURE_BLOCKED',reason=str(e) or type(e).__name__)
        r['receipt_sha256']=sha(canonical(r));publish_once(out,canonical(r));return r
    finally:os.close(fd)
