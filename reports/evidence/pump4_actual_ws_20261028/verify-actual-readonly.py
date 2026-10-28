"""Literal source custody plus unchanged frozen replay; GET-free and read-only."""
from pathlib import Path
import sys,json,hashlib,time,collections
B=Path('/opt/bybot-research/pump4-server-orders-off-20261023');A=B/'candidate-7d8ae05dab162ec5/app';D=A/'.private/pump4-supervisor-v1';sys.path.insert(0,str(A))
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_source_probe_v1 import Probe
from research_lab.alpaca_dynamic_v1 import canonical,digest
from research_lab.pump4_bybit_sources_v1 import universe,H
started=time.time_ns()//1000000;hours=list(range(1793178000000,1793199600000+H,H));by_symbol={};verified=0;raws=0;files={};receipts={};status=[];maxlag=0
for hour in hours:
 f=D/'ws-hours'/str(hour);raw=(f/'receipt.json').read_bytes();r=json.loads(raw);assert r['hour_pass'] and r['census']==137 and r['within60s']==r['expected_trading']==135 and not r['disconnected'];receipts[str(hour)]=hashlib.sha256(raw).hexdigest();assert [x['symbol'] for x in r['rows']]==list(universe())
 ack=json.loads((f/'subscription-ack.json').read_bytes());assert ack['preboundary'] and ack['received_ms']<hour
 for row in r['rows']:
  symbol=row['symbol']
  if row['status']=='UNAVAILABLE_INSTRUMENT':assert symbol in ('HFTUSDT','VELODROMEUSDT');continue
  assert row['status']=='CLOSED_H1_INTAKE_PASS' and 0<=row['publication_completed_ms']-hour<=60000 and row['broker_writes']==0 and row['mode']=='CURRENT_CLOSED_BAR';maxlag=max(maxlag,row['publication_completed_ms']-hour)
  published=f/'published'/(symbol+'.json');assert json.loads(published.read_bytes())==row
  batch=json.loads((f/'batches'/(symbol+'.json')).read_bytes());prefix=json.loads((f/'prefixes'/(symbol+'.json')).read_bytes());pins=batch['raw_captures'];p=Probe(hour,[symbol]);mono=None;anchor=None
  for pin in pins:
   path=Path(pin['path']);assert path.is_relative_to(f/'frames') and not path.is_symlink();cap=json.loads(path.read_bytes());assert digest(cap)==pin['sha256'] and hashlib.sha256(cap['raw'].encode()).hexdigest()==cap['raw_sha256'] and cap['connection']==1
   if anchor is None:anchor=(cap['received_ms'],cap['received_monotonic_ns'])
   assert mono is None or cap['received_monotonic_ns']>=mono;mono=cap['received_monotonic_ns'];assert abs((cap['received_ms']-anchor[0])-(mono-anchor[1])/1e6)<=1000
   p.add(cap['raw'],received_ms=cap['received_ms'],connection=1);raws+=1
  summary=p.summary()['symbols'][symbol];assert summary['timely_pair'] and summary['same_connection'] and not summary['conflict'] and p.opened[symbol]['server_ms']>=hour and p.opened[symbol]['received_ms']>=hour
  assert batch['bar']==[hour-H,*map(float,p.closed[symbol]['values'][:5])]
  assert batch['archive_id']==digest(dict(hour=hour,symbol=symbol,frames=pins))==row['decisions'][0]['archive_id']
  if symbol not in by_symbol:
   i=Pump4Intake(D/'intake'/(symbol+'.jsonl'),symbol);events=i.journal.read();snapshot=i._replay(events);by_symbol[symbol]=(events,{x['bar_open_ms']:x for x in snapshot['decisions']});files[symbol]=hashlib.sha256((D/'intake'/(symbol+'.jsonl')).read_bytes()).hexdigest()
  events,decisions=by_symbol[symbol];found=[n for n,e in enumerate(events[1:],1) if e['bar'][0]==hour-H];assert len(found)==1;n=found[0];assert events[n]['bar']==batch['bar'] and hashlib.sha256(canonical(events[:n])).hexdigest()==prefix['journal_prefix_sha256']
  obs=row['decisions'][0];assert obs['decision']==decisions[hour-H] and json.loads((D/'observations'/(obs['decision']['decision_id']+'.json')).read_bytes())==obs
  assert prefix['epoch']==json.loads((D/'epochs'/(symbol+'.json')).read_bytes());verified+=1
 status.append(dict(hour=hour,verified=135,receipt_sha256=receipts[str(hour)]))
print(json.dumps(dict(schema='PUMP4_ACTUAL_WS_FROZEN_REPLAY_CUSTODY_V1',status='PASS',started_ms=started,observed_ms=time.time_ns()//1000000,hours=7,census=137,available_symbols=135,explicit_unavailable=['HFTUSDT','VELODROMEUSDT'],verified_decisions=verified,frozen_replay_equal=True,hash_chain_read_only=True,raw_pins_verified=raws,journal_sha256=files,receipts=receipts,rows=status,max_publication_delay_ms=maxlag,broker_requests=0,broker_writes=0,production_state_writes=0,financial_admission_proven=False)))
