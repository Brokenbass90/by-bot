#!/usr/bin/env python3
"""Immutable DATA-only SSH delivery, never financial commands or old log writes."""
import argparse,datetime as dt,fcntl,gzip,hashlib,io,json,os,re,shlex,shutil,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.polymarket_ws_data_v1 import EPOCH,read,sha,once,encoded,need,clock,replace,mkdirs_durable,sync_ancestors

PATTERN=r'(sports|clob|catalog)/sealed/[0-9]+-[0-9a-f]{32}-[0-9]+\.jsonl\.gz'
REMOTE='/var/lib/bybot-polydata-20261102'


def checked_name(name):
    need(isinstance(name,str) and re.fullmatch(PATTERN,name) is not None,'EXPORT_FILE_ALLOWLIST');return name


def validate_segment(seal,raw):
    name=checked_name(seal['file'])
    need(seal['schema']=='POLY_WS_SEGMENT_DELIVERY_V1' and seal['epoch']==EPOCH
         and seal['role']==name.split('/')[0] and seal['orders_allowed'] is False
         and len(raw)==seal['bytes'] and sha(raw)==seal['sha256'] and len(raw)<=8*2**20
         and type(seal['raw_bytes']) is int and 0<seal['raw_bytes']<=8*2**20,'SEGMENT_HASH_OR_SCOPE')
    with gzip.GzipFile(fileobj=io.BytesIO(raw),mode='rb') as f:plain=f.read(8*2**20+1)
    need(len(plain)==seal['raw_bytes'] and sha(plain)==seal['raw_sha256'] and plain.endswith(b'\n'),'RAW_HASH_OR_SIZE')
    rows=plain.splitlines();need(len(rows)==seal['rows'] and rows,'SEGMENT_ROWS')
    for i,line in enumerate(rows):
        x=json.loads(line);need(x['schema']=='POLY_WS_RAW_V1' and x['epoch']==EPOCH and x['role']==seal['role']
            and x['session']==seal['session'] and x['seq']==i and type(x['received_ms']) is int
            and 0<x['received_ms']<=seal['closed_ms'] and type(x['monotonic_ns']) is int,'ROW_SCOPE')
    need(json.loads(rows[0])['received_ms']==seal['first_received_ms'] and json.loads(rows[-1])['received_ms']==seal['last_received_ms'],'SEGMENT_CLOCKS')
    return name


def import_segment(destination,seal,raw,*,observed_ms=None):
    name=validate_segment(seal,raw);now=clock() if observed_ms is None else observed_ms
    need(type(now) is int and now>=seal['closed_ms'],'IMPORT_CLOCK')
    root=Path(destination).absolute();need(not any(p.is_symlink() for p in (root,*root.parents)),'DESTINATION_CUSTODY')
    mkdirs_durable(root)
    fd=os.open(root/'import.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        file=root/name;need(not any(p.is_symlink() for p in (file,*file.parents)),'DESTINATION_CUSTODY')
        if file.exists():need(read(file)==raw,'IMMUTABLE_LOCAL_CONFLICT')
        else:once(file,raw)
        sealfile=file.with_suffix(file.suffix+'.delivery.json');payload=encoded(seal)
        if sealfile.exists():need(read(sealfile)==payload,'IMMUTABLE_LOCAL_SEAL_CONFLICT')
        else:once(sealfile,payload)
        receipt=root/'receipts'/(sha(payload)+'.json')
        if receipt.exists():
            old=json.loads(read(receipt));need(old['seal_sha256']==sha(payload) and old['file_sha256']==sha(raw),'RECEIPT_CONFLICT');return old
        result=dict(schema='POLY_WS_DATA_IMPORT_V1',epoch=EPOCH,file=name,file_sha256=sha(raw),seal_sha256=sha(payload),actual_import_ms=now,source_closed_ms=seal['closed_ms'],first_local_mtime_ns=file.stat().st_mtime_ns,source_first_received_ms=seal['first_received_ms'],source_last_received_ms=seal['last_received_ms'],orders_allowed=False)
        once(receipt,encoded(result));return result
    finally:os.close(fd)


def export_listing(root):
    root=Path(root).resolve();out=[]
    for role in ('sports','clob','catalog'):
        paths=sorted((root/role/'sealed').glob('*.jsonl.gz.delivery.json'));need(len(paths)<=10000,'EXPORT_LIST_BOUND')
        for path in paths:
            seal=json.loads(read(path,16384));name=checked_name(seal['file'])
            need(path==root/(name+'.delivery.json') and seal['epoch']==EPOCH,'EXPORT_SEAL_PATH')
            out.append(seal)
    return out


def export_file(root,name,pin):
    name=checked_name(name);root=Path(root).resolve();seal=json.loads(read(root/(name+'.delivery.json'),16384));raw=read(root/name)
    need(seal['file']==name and seal['sha256']==pin,'EXPORT_PIN');validate_segment(seal,raw);return raw



def make_archive_ack(destination,seal):
    root=Path(destination);raw=read(root/checked_name(seal['file']));validate_segment(seal,raw)
    need(read(root/(seal['file']+'.delivery.json'))==encoded(seal),'ARCHIVE_LOCAL_SEAL')
    receipt=json.loads(read(root/'receipts'/(sha(encoded(seal))+'.json')))
    need(receipt['file_sha256']==sha(raw) and receipt['seal_sha256']==sha(encoded(seal)),'ARCHIVE_LOCAL_RECEIPT')
    sync_ancestors((root/checked_name(seal['file'])).parent);sync_ancestors(root/'receipts')
    return dict(schema='POLY_WS_VERIFIED_MAC_ARCHIVE_ACK_V1',epoch=EPOCH,seal=json.loads(encoded(seal)),
        local_receipt=receipt,local_receipt_sha256=sha(encoded(receipt)),receiver_readback_sha256=sha(raw),
        client_sha256=sha(read(Path(__file__))),destination=str(root.absolute()))


def _prune_ack_history(root,now_ms):
    day=dt.datetime.fromtimestamp(now_ms/1000,dt.timezone.utc).date().isoformat()
    marker=root/'archive-maintenance.json'
    if marker.exists() and json.loads(read(marker))['day']==day:return
    cutoff=now_ms-7*86400000
    def finish(folder,path):
        task=json.loads(read(path));summary=task['summary'];target=folder/('history-'+summary['day']+'.json')
        if target.exists():need(read(target)==encoded(summary),'ARCHIVE_DAY_DIGEST_CONFLICT')
        else:once(target,encoded(summary))
        for name,h in task['ack_files'].items():
            need(re.fullmatch(r'[0-9]+-[0-9a-f]{32}-[0-9]+\.jsonl\.gz\.ack\.json',name) is not None,'ACK_RETIREMENT_NAME')
            old=folder/name
            if old.exists():need(sha(read(old))==h,'ARCHIVE_ACK_CHANGED');old.unlink()
        path.unlink()
        fd=os.open(folder,os.O_RDONLY);os.fsync(fd);os.close(fd)
    for role in ('sports','clob','catalog'):
        folder=root/role/'archived';groups={}
        for path in folder.glob('retiring-*.json'):finish(folder,path)
        for path in folder.glob('*.ack.json'):
            raw=read(path);x=json.loads(raw)
            if x['acknowledged_ms']<cutoff:
                d=dt.datetime.fromtimestamp(x['acknowledged_ms']/1000,dt.timezone.utc).date().isoformat();groups.setdefault(d,[]).append((path,raw))
        for d,items in groups.items():
            end=int(dt.datetime.combine(dt.date.fromisoformat(d)+dt.timedelta(days=1),dt.time(),dt.timezone.utc).timestamp()*1000)
            if end>=cutoff:continue
            summary=dict(schema='POLY_WS_ARCHIVE_DAY_DIGEST_V1',epoch=EPOCH,day=d,role=role,ack_count=len(items),ack_hashes_sha256=sha(encoded(sorted(sha(raw) for _,raw in items))))
            task=dict(summary=summary,ack_files={path.name:sha(raw) for path,raw in items});temp=folder/('retiring-'+d+'.json')
            once(temp,encoded(task));finish(folder,temp)
    replace(marker,dict(day=day,observed_ms=now_ms,full_ack_retention_days=7))


def archive_ack(root,acks,*,now_ms=None):
    root=Path(root).resolve();now=clock() if now_ms is None else now_ms
    need(isinstance(acks,list) and len(acks)<=128,'ARCHIVE_BATCH_BOUND')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(root/'archive.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);freed=count=0;roles=set()
        for ack in acks:
            need(ack['schema']=='POLY_WS_VERIFIED_MAC_ARCHIVE_ACK_V1' and ack['epoch']==EPOCH and ack['client_sha256']==sha(read(Path(__file__))),'ARCHIVE_CLIENT_VERSION')
            seal=ack['seal'];name=checked_name(seal['file']);receipt=ack['local_receipt']
            need(ack['receiver_readback_sha256']==seal['sha256'] and receipt['file_sha256']==seal['sha256']
                and receipt['seal_sha256']==sha(encoded(seal)) and ack['local_receipt_sha256']==sha(encoded(receipt))
                and seal['closed_ms']<=receipt['actual_import_ms']<=now,'ARCHIVE_RECEIPT_PROOF')
            role=name.split('/')[0];source=root/name;metadata=root/(name+'.delivery.json');tomb=root/role/'archived'/(Path(name).name+'.ack.json')
            proof=sha(encoded(ack))
            if tomb.exists():need(json.loads(read(tomb))['proof_sha256']==proof,'ARCHIVE_ACK_CONFLICT')
            else:
                raw=read(source);validate_segment(seal,raw);need(read(metadata)==encoded(seal),'ARCHIVE_SOURCE_SEAL')
                once(tomb,encoded(dict(schema='POLY_WS_CACHE_EVICTION_ACK_V1',epoch=EPOCH,acknowledged_ms=now,proof_sha256=proof,seal=seal,local_receipt=receipt)))
            removed=False
            if source.exists():
                raw=read(source);validate_segment(seal,raw);freed+=len(raw);source.unlink();removed=True
            if metadata.exists():need(read(metadata)==encoded(seal),'ARCHIVE_SOURCE_SEAL');freed+=metadata.stat().st_size;metadata.unlink();removed=True
            if removed:
                dfd=os.open(source.parent,os.O_RDONLY);os.fsync(dfd);os.close(dfd);count+=1;roles.add(role)
        for role in roles:replace(root/role/'retention-generation.json',dict(observed_ms=now,generation=uuid.uuid4().hex))
        _prune_ack_history(root,now)
        return dict(schema='POLY_WS_CACHE_EVICTION_RESULT_V1',evicted_files=count,freed_bytes=freed,observed_ms=now,financial_commands=0)
    finally:os.close(fd)


def data_health(root):
    from research_lab.polymarket_ws_data_v1 import BUDGETS
    root=Path(root).resolve();out={};warnings=[];now=clock();free=shutil.disk_usage(root).free
    for role,budget in BUDGETS.items():
        folder=root/role;used=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        seals=[]
        for p in (folder/'sealed').glob('*.delivery.json'):seals.append(json.loads(read(p,16384)))
        oldest=min((s['closed_ms'] for s in seals),default=None)
        status_path=folder/'status.json'
        if status_path.exists():
            status=json.loads(read(status_path));state=status.get('state','UNKNOWN')
            if state.startswith('STOPPED'):warnings.append(role.upper()+'_COLLECTOR_STOPPED')
            if state=='RECONNECTING_GAP_UNKNOWN':warnings.append(role.upper()+'_FEED_RECONNECTING')
            freshness=2400000 if role=='catalog' else 120000
            if now-status.get('observed_ms',0)>freshness:warnings.append(role.upper()+'_STATUS_STALE')
        else:warnings.append(role.upper()+'_STATUS_MISSING')
        if used>=.75*budget:warnings.append(role.upper()+'_BACKLOG_75_PERCENT')
        if oldest is not None and now-oldest>3600000:warnings.append(role.upper()+'_ARCHIVE_LAG_OVER_1H')
        out[role]=dict(used_bytes=used,max_bytes=budget,sealed_backlog=len(seals),oldest_unarchived_ms=oldest)
    if free<3*2**30:warnings.append('VPS_FREE_DISK_BELOW_3_GIB')
    return dict(schema='POLY_WS_DATA_HEALTH_V1',observed_ms=now,free_bytes=free,roles=out,warnings=warnings)


def remote(identity,package,pin,args,*,input_bytes=None):
    need(re.fullmatch(r'/opt/bybot-research/polymarket-ws-data-20261102/candidate-[0-9a-f]{16}',package) is not None and re.fullmatch('[0-9a-f]{64}',pin) is not None,'REMOTE_PACKAGE')
    code="""import pathlib,hashlib,json,subprocess,sys
r=pathlib.Path(sys.argv[1]);raw=(r/'verification-source-hashes.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==sys.argv[2]
for n,h in json.loads(raw).items():
 p=pathlib.PurePosixPath(n);assert not p.is_absolute() and '..' not in p.parts and hashlib.sha256((r/'app'/n).read_bytes()).hexdigest()==h
raise SystemExit(subprocess.call(['/usr/bin/python3','-B',str(r/'app/scripts/pull_polymarket_ws_data_v1.py'),*sys.argv[3:]]))
"""
    invocation=['systemd-run','--quiet','--pipe','--wait','--collect','--unit=poly-ws-data-transfer-'+uuid.uuid4().hex,
        '-p','Slice=poly-ws-data.slice','-p','CPUQuota=10%','-p','MemoryMax=96M','-p','TasksMax=16',
        '-p','DynamicUser=yes','-p','User=bybot-polydata','-p','StateDirectory=bybot-polydata-20261102',
        '-p','ProtectHome=yes','-p','ProtectSystem=strict','-p','NoNewPrivileges=yes',
        '-p','PrivateTmp=yes','-p','Nice=15','-p','IOSchedulingClass=idle','-p','RuntimeMaxSec=90',
        '-p','ReadWritePaths=/var/lib/bybot-polydata-20261102',
        '/usr/bin/python3','-B','-c',code,package,pin,*args]
    command=' '.join(shlex.quote(x) for x in invocation)
    r=subprocess.run(['ssh','-i',str(identity),'-o','BatchMode=yes','-o','ConnectTimeout=10','root@64.226.73.119',command],input=input_bytes,capture_output=True,timeout=120)
    need(r.returncode==0,'SSH_EXPORT_FAILED');need(len(r.stdout)<=16*2**20,'SSH_BODY_BOUND');return r.stdout



def claim_selector_locks(mac_root):
    """Hold existing two DATA locks; no chmod/content change or producer."""
    folder=Path(mac_root)/'research_lab/data/locks';fds=[]
    try:
        for role in ('sportsws','clobws'):
            path=folder/(role+'.lock');need(path.is_file() and not path.is_symlink() and path.stat().st_nlink==1,'MAC_DATA_LOCK_CUSTODY')
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW);fds.append(fd);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return fds
    except BaseException:
        for fd in fds:os.close(fd)
        raise



def notify_storage(warnings,status_path):
    """Local desktop warning only, deduplicated; no external messages or keys."""
    file=Path(status_path).with_name('last-storage-warning.json');classes=sorted(set(warnings))
    old=json.loads(read(file)) if file.exists() else None
    if old and old['warnings']==classes:return
    if classes:
        text='Trading OS DATA: требуется проверить доставку или свободное место. Подробности в DATA status.'
        subprocess.run(['osascript','-e','display notification '+json.dumps(text)+' with title "Trading OS DATA"'],capture_output=True,timeout=10)
    replace(file,dict(warnings=classes,observed_ms=clock()))


def run_mac_consumer(config_path,pin):
    raw=read(config_path);need(sha(raw)==pin,'MAC_CONFIG_PIN');c=json.loads(raw)
    need(c['schema']=='POLY_WS_MAC_CONSUMER_V1' and c['mac_root']=='/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28','MAC_CONSUMER_SCOPE')
    for name,h in c['source_files'].items():need(not Path(name).is_absolute() and '..' not in Path(name).parts and sha(read(ROOT/name))==h,'MAC_CONSUMER_SOURCE_DRIFT')
    fds=claim_selector_locks(c['mac_root']);status=Path(c['status_path'])
    try:
        result=dict(schema='POLY_WS_MAC_SELECTOR_STATUS_V1',pid=os.getpid(),roles=['sportsws','clobws'],observed_ms=clock(),locks_held=True,mode='MAC_CONSUMER_VPS_PRODUCER',orders_allowed=False)
        replace(status,result)
        while True:
            try:
                args=['--pull','--identity',c['identity'],'--destination',c['destination'],'--package-root',c['package_root'],'--package-sha256',c['package_sha256']]
                child=subprocess.run([sys.executable,'-B',str(Path(__file__)),*args],capture_output=True,text=True,timeout=240)
                result.update(last_pull_ms=clock(),last_pull_exit=child.returncode,last_pull=json.loads(child.stdout) if child.returncode==0 else None)
            except Exception as exc:result.update(last_pull_ms=clock(),last_pull_exit=-1,last_pull=None,error_type=type(exc).__name__)
            warnings=result.get('last_pull',{}).get('data_health',{}).get('warnings',[]) if result.get('last_pull_exit')==0 and result.get('last_pull') else ['DATA_DELIVERY_FAILED']
            result['warnings']=warnings;result['observed_ms']=clock();replace(status,result)
            try:notify_storage(warnings,status)
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
            time.sleep(300)
    finally:
        for fd in fds:os.close(fd)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--pull',action='store_true');p.add_argument('--destination',type=Path);p.add_argument('--identity',type=Path);p.add_argument('--package-root');p.add_argument('--package-sha256')
    p.add_argument('--hold-mac-selector',action='store_true');p.add_argument('--selector-config',type=Path);p.add_argument('--selector-config-sha256');p.add_argument('--archive-ack',action='store_true');p.add_argument('--data-health',action='store_true');p.add_argument('--export-list',action='store_true');p.add_argument('--export-file');p.add_argument('--export-sha256');a=p.parse_args(argv)
    need(sum(bool(x) for x in (a.pull,a.hold_mac_selector,a.export_list,a.export_file,a.archive_ack,a.data_health))<=1,'EXCLUSIVE_DATA_MODE')
    if a.hold_mac_selector:
        need(a.selector_config and a.selector_config_sha256 and not a.pull and not a.export_list and not a.export_file,'MAC_SELECTOR_MODE');run_mac_consumer(a.selector_config,a.selector_config_sha256);return 0
    if a.archive_ack:
        body=sys.stdin.buffer.read(1024*1024+1);need(len(body)<=1024*1024,'ACK_BODY_BOUND');acks=json.loads(body)
        need(all(x['destination']=='/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data/poly_ws_vps_v1' for x in acks),'CANONICAL_ARCHIVE_DESTINATION')
        print(json.dumps(archive_ack(REMOTE,acks)));return 0
    if a.data_health:print(json.dumps(data_health(REMOTE)));return 0
    if a.export_list or a.export_file:
        need(not a.pull and not(a.export_list and a.export_file),'EXPORT_MODE')
        if a.export_list:sys.stdout.buffer.write(encoded(export_listing(REMOTE)))
        else:sys.stdout.buffer.write(export_file(REMOTE,a.export_file,a.export_sha256))
        return 0
    if not a.pull:print(json.dumps(dict(status='DATA_ONLY_NO_REQUESTS')));return 0
    need(a.destination and a.identity and a.package_root and a.package_sha256,'PULL_SCOPE')
    seals=json.loads(remote(a.identity,a.package_root,a.package_sha256,['--export-list']));need(isinstance(seals,list) and len(seals)<=30000,'PULL_LIST_BOUND')
    new=existing=0;last=None;acks=[];evicted=freed=0
    a.destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    archive_used=sum(p.stat().st_size for p in a.destination.rglob('*') if p.is_file())
    for seal in seals:
        name=checked_name(seal['file']);local=a.destination/name
        # Recheck existing bytes/seals; conflicts are never overwritten.
        if not local.exists():
            need(shutil.disk_usage(a.destination).free>=10*2**30,'MAC_ARCHIVE_FREE_BELOW_10_GIB')
            need(archive_used+seal['bytes']+4096<=20*2**30,'MAC_ARCHIVE_20_GIB_CAP')
        raw=read(local) if local.exists() else remote(a.identity,a.package_root,a.package_sha256,['--export-file',name,'--export-sha256',seal['sha256']])
        before=local.exists();receipt=import_segment(a.destination,seal,raw);existing+=int(before);new+=int(not before);last=max(last or 0,receipt['source_last_received_ms'])
        if not before:archive_used+=len(raw)+4096
        acks.append(make_archive_ack(a.destination,seal))
        if len(acks)>=64:
            result=json.loads(remote(a.identity,a.package_root,a.package_sha256,['--archive-ack'],input_bytes=encoded(acks)));evicted+=result['evicted_files'];freed+=result['freed_bytes'];acks=[]
    if acks:
        result=json.loads(remote(a.identity,a.package_root,a.package_sha256,['--archive-ack'],input_bytes=encoded(acks)));evicted+=result['evicted_files'];freed+=result['freed_bytes']
    health=json.loads(remote(a.identity,a.package_root,a.package_sha256,['--data-health']))
    if archive_used>=15*2**30:health['warnings'].append('MAC_ARCHIVE_75_PERCENT')
    if shutil.disk_usage(a.destination).free<15*2**30:health['warnings'].append('MAC_FREE_BELOW_15_GIB')
    print(json.dumps(dict(status='DATA_ONLY_DELIVERED',new_segments=new,existing_segments_verified=existing,last_source_received_ms=last,actual_observed_ms=clock(),archived_source_segments=evicted,freed_source_bytes=freed,data_health=health,orders_allowed=False)));return 0

if __name__=='__main__':raise SystemExit(main())
