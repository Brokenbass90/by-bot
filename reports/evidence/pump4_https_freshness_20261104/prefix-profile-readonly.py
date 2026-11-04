from pathlib import Path
import os,json,sys,hashlib,time,datetime as dt,concurrent.futures
candidate=Path('/opt/bybot-research/pump4-current-hour-repair-20261101/candidate-05f89618d8550664');raw=(candidate/'verification-source-hashes.json').read_bytes();assert hashlib.sha256(raw).hexdigest()=='05f89618d8550664cf2d914f000ef9f7b101d32176032adb78a6d7bbbdb03dfd'
for name,pin in json.loads(raw).items():
 p=Path(name);assert not p.is_absolute() and '..' not in p.parts;assert hashlib.sha256((candidate/'app'/p).read_bytes()).hexdigest()==pin
sys.path.insert(0,str(candidate/'app'))
from research_lab.att1_lifecycle_journal import LifecycleJournal
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_bybit_sources_v1 import public_get,closed_h1
source=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-7d8ae05dab162ec5/app/.private/pump4-supervisor-v1/intake/SIRENUSDT.jsonl')
fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as f:
 a=os.fstat(f.fileno());assert a.st_size<8*2**20;allraw=f.read();b=os.fstat(f.fileno())
assert (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns)
complete=allraw[:allraw.rfind(b'\n')+1];tail=len(allraw)-len(complete)
H=3600000;entry=int(dt.datetime(2026,11,3,3,tzinfo=dt.timezone.utc).timestamp()*1000)
lines=complete.splitlines(keepends=True);cut=next(i+1 for i,line in enumerate(lines) if json.loads(line)['event'].get('bar',[None])[0]==entry-H)
prefix=b''.join(lines[:cut]);mem=os.memfd_create('readonly-siren-prefix',flags=os.MFD_CLOEXEC);os.write(mem,prefix)
journal=LifecycleJournal('/NOT_A_SOURCE_JOURNAL');t=time.perf_counter_ns();events,_,tip,_=journal._load(mem);validate_ms=(time.perf_counter_ns()-t)/1e6
obj=Pump4Intake.__new__(Pump4Intake);obj.symbol='SIRENUSDT'
first=entry-1001*H;qs=[dict(category='linear',symbol='SIRENUSDT',interval='60',start=first,end=entry+H-1,limit=1000),dict(category='linear',symbol='SIRENUSDT',interval='60',start=first,end=entry-999*H-1,limit=1000)]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:caps=list(pool.map(lambda q:public_get('/v5/market/kline',q),qs))
get_done=time.time_ns()//1000000;packet=closed_h1(caps,'SIRENUSDT',next_open_ms=entry,observed_ms=get_done)
profiles=[]
for i in range(3):
 t=time.perf_counter_ns();state=obj._replay(tuple(events));ended=time.time_ns()//1000000
 matches=[d for d in state['decisions'] if d['bar_open_ms']==entry-H];assert len(matches)==1
 profiles.append(dict(pass_index=i+1,replay_ms=(time.perf_counter_ns()-t)/1e6,actual_end_ms=ended,source_age_ms=ended-packet['source_ms'],available_age_ms=ended-packet['available_ms'],signal_present=matches[0]['signal'] is not None,decision_id=matches[0]['decision_id']))
os.close(mem)
assert source.stat().st_size>=a.st_size
print(json.dumps(dict(schema='PUMP4_READONLY_SIREN_REPLAY_PROFILE_V1',observed_ms=time.time_ns()//1000000,prefix_rows=len(events),prefix_sha256=hashlib.sha256(prefix).hexdigest(),prefix_tip=tip,complete_source_sha256=hashlib.sha256(complete).hexdigest(),ignored_partial_tail_bytes=tail,source_flock=False,source_modified=False,initial_chain_validation_ms=validate_ms,actual_get_done_ms=get_done,actual_initial_source_age_ms=get_done-packet['source_ms'],actual_initial_available_age_ms=get_done-packet['available_ms'],captures=caps,replays=profiles,diagnostic_replays_only=True,historical_failed_HTTP_capture_recovered=False,no_admission=True,no_owner_constructed=True,no_judge_or_PnL=True)))
