"""Frozen source replay only. No judge, return evaluation or broker interface."""
import hashlib,json,os,sys,time,socket
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--research-root',required=True,type=Path)
parser.add_argument('--fixtures',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
research=args.research_root.resolve();output=args.output.absolute()
assert not output.resolve().is_relative_to(research),'RESEARCH_OUTPUT_REFUSED'
assert not output.exists(),'EXCLUSIVE_OUTPUT_REQUIRED'
expected={'strategies/pump_fade_v4r.py':'cea7a2cc9151d22ddaf620428dc6b7734f6aa4051819145821a76cda2381792a',
          'strategies/signals.py':'5f9408f203f303853360dd79e31fe0893b6db95329abbd758401a89f3258755c'}
assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in expected.items()),'FROZEN_SOURCE_DRIFT'

assert not any(k.startswith('PF_') for k in os.environ),'AMBIENT_PF_CONFIG_REFUSED'
def denied(*args,**kwargs):raise AssertionError('PARITY_NETWORK_FORBIDDEN')
class NoNetwork(socket.socket):connect=denied;connect_ex=denied;sendto=denied
socket.socket=NoNetwork;socket.create_connection=denied
from strategies.pump_fade_v4r import PumpFadeV4RStrategy
source=Path(sys.modules[PumpFadeV4RStrategy.__module__].__file__).resolve();assert source==root/'strategies/pump_fade_v4r.py'
fixtures_raw=args.fixtures.read_bytes();assert hashlib.sha256(fixtures_raw).hexdigest()=='f6badf311e888fab05a3d4131559f98152f8589d49b35c7b034e306617726ca4','FIXTURE_DRIFT'
fx=json.loads(fixtures_raw)['fixtures']
rows=[];inputs={};started=time.monotonic();H=3600000
for f in fx:
 if f['status']!='OK':
  rows.append(dict(symbol=f.get('sym'),status='SOURCE_UNAVAILABLE_EXPECTED',reference_status=f['status']));continue
 sym=f['sym'];ts=f['signal_bar_open_ms'];p=research/'research_lab/data/oos_bybit_h1_20261020'/(sym+'.json')
 raw=p.read_bytes();inputs[str(p.relative_to(research))]=hashlib.sha256(raw).hexdigest();all_bars=json.loads(raw)
 b=[r for r in all_bars if r[0]>=ts-1000*H];idx=next(i for i,r in enumerate(b) if r[0]==ts);prefix=b[:idx+1]
 assert hashlib.sha256(json.dumps(prefix).encode()).hexdigest()==f['bary_sha256'],('BARS_HASH',sym,ts)
 assert len(prefix)==f['barov_v_okne']
 assert all(len(r)==6 and r[0]<=ts for r in prefix)
 strategy=PumpFadeV4RStrategy();signal=None
 for i in range(200,idx+1):
  got=strategy.maybe_signal(sym,*b[i])
  if i==idx:signal=got
 assert signal is not None,('MISSING_SIGNAL',sym,ts)
 observed=dict(entry=signal.entry,sl=signal.sl,tps=list(signal.tps),tp_fracs=list(signal.tp_fracs))
 assert observed==f['signal'] and signal.side==f['side'] and signal.reason==f['reason'],('SIGNAL_CONFLICT',sym,ts)
 # Only next-open execution geometry is checked; never evaluate R or outcomes.
 entry=b[idx+1][1];stop=entry+(signal.sl-entry)*4.0;plan=f['ispolnenie_V1']
 assert entry==plan['vhod'] and stop==plan['stop_x4']
 assert [signal.tps[0],signal.tps[1],signal.tp_fracs[0],round(1-signal.tp_fracs[0],6),168]==[plan['tp1'],plan['tp2'],plan['dolya_tp1'],plan['ostatok_na_tp2'],plan['uderzhanie_barov']]
 rows.append(dict(symbol=sym,signal_bar_open_ms=ts,status='FROZEN_SOURCE_SIGNAL_AND_PLAN_MATCH',bars_sha256=f['bary_sha256'],bar_count=len(prefix),signal_sha256=hashlib.sha256(json.dumps(observed,sort_keys=True).encode()).hexdigest()))

# Confirm no research input changed while read. No research file is written.
assert all(hashlib.sha256((research/n).read_bytes()).hexdigest()==h for n,h in inputs.items())
matched=sum(r['status']=='FROZEN_SOURCE_SIGNAL_AND_PLAN_MATCH' for r in rows)
assert matched==65 and len(rows)==66
out=dict(schema='PUMP4_FROZEN_PRODUCER_REPLAY_V1',status='FROZEN_SOURCE_REPLAY_PASS',contract_commit='b1387354e5b64de205e7f933b0537a2f6f37c123',published_origin='98cc87afd590b360cbb2f065b147ac913f85ea31',fixture_sha256=hashlib.sha256(fixtures_raw).hexdigest(),matched=matched,unavailable=1,elapsed_seconds=round(time.monotonic()-started,3),rows=rows,input_files=inputs,research_inputs_unchanged=True,outcomes_recomputed=False,funding_in_research_model=False,execution_adapter_parity='NOT_RUN',continuous_state_restart_parity='NOT_RUN',broker_requests=0,broker_writes=0,money_authority=False,orders_allowed=False,network_denied=True)
assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in expected.items()),'FROZEN_SOURCE_DRIFT_AFTER'
with output.open('x') as f:f.write(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in {'rows','input_files'}}))
