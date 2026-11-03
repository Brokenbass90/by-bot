"""Bounded file-only measurement of one genuine archived full book, not a V2 signal."""
import json,gzip,hashlib,sys,socket,os,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R));from scripts.pull_polymarket_ws_data_v1 import validate_segment,encoded,sha
from research_lab import polymarket_v2_orders_off_v1 as measure
A=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data/poly_ws_vps_v1');D=R/'.private/poly_v2_execution_20261103/real-archive-probe';D.mkdir(mode=0o700,exist_ok=True)
proof=[]
def rows(sp):
 seal=json.loads(sp.read_bytes());raw=(A/seal['file']).read_bytes();validate_segment(seal,raw)
 receipt_path=A/'receipts'/(sha(encoded(seal))+'.json');rec=json.loads(receipt_path.read_bytes());assert rec['file_sha256']==seal['sha256'] and rec['seal_sha256']==sha(encoded(seal))
 return seal,[json.loads(l) for l in gzip.decompress(raw).splitlines()],{'file':seal['file'],'seal_sha256':sha(encoded(seal)),'compressed_sha256':sha(raw),'import_receipt_sha256':hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
first_clob=sorted((A/'clob/sealed').glob('*.delivery.json'))[0];first_time=json.loads(first_clob.read_bytes())['first_received_ms']
cat=None
prior=[sp for sp in (A/'catalog/sealed').glob('*.delivery.json') if json.loads(sp.read_bytes())['last_received_ms']<=first_time]
for sp in sorted(prior,reverse=True)[:120]:
 seal,rr,pr=rows(sp)
 for row in reversed(rr):
  if row['kind']=='CATALOGUE':cat=(row,pr);break
 if cat:break
assert cat,'NO_CATALOGUE_IN_BOUNDED_WINDOW'
markets=cat[0]['payload']['markets'];bytoken={tok:m for m in markets for tok in m['tokens']};found=None
for sp in sorted((A/'clob/sealed').glob('*.delivery.json'))[:4]:
 seal,rr,pr=rows(sp)
 for row in reversed(rr):
  if row['kind']!='RECV':continue
  frame=row['payload'].get('frame');value=json.loads(frame) if frame and frame not in ('PONG','pong','ping') else None
  for event in value if isinstance(value,list) else [value]:
   if isinstance(event,dict) and event.get('event_type')=='book' and event.get('asset_id') in bytoken:
    found=(row,event,pr);break
  if found:break
 if found:break
assert found,'NO_FULL_BOOK_IN_BOUNDED_WINDOW'
row,event,pr=found;m=bytoken[event['asset_id']];stamp=max(row['received_ms'],cat[0]['received_ms']);booksha=measure.sha(row);metasha=measure.sha(cat[0])
signal={'market_id':str(m['id']),'token_id':event['asset_id'],'policy_sha256':'7ba7af0cd23fd1f9792b7593844ab9a9c85ec0e23b94c1b03e342ea0fb07221f','received_ms':row['received_ms'],'model_price':None,'kind':'ARCHIVED_BOOK_MEASUREMENT_NOT_A_TRADE_SIGNAL'}
book={'asset_id':event['asset_id'],'bids':event.get('bids',[]),'asks':event.get('asks',[]),'received_ms':row['received_ms'],'time_origin':'VPS_WS_RECEIVED','continuity':'VERIFIED','source_sha256':booksha}
market={'market_id':str(m['id']),'tokens':m['tokens'],'received_ms':cat[0]['received_ms'],'source_sha256':metasha} # slim catalogue does not prove accepting_orders or fees
for n,v in [('signal',signal),('book',book),('market',market),('raw-book-row',row),('raw-catalogue-row',cat[0])]:
 with (D/(n+'.json')).open('x') as f:json.dump(v,f,sort_keys=True)
(D/'source-proof.json').write_text(json.dumps({'book':pr,'catalogue':cat[1],'full_snapshot_only':True,'venue_sequence_coverage':'UNKNOWN','historical_replay':True,'actual_observed_ms':time.time_ns()//1000000},indent=2))
def denied(*a,**kw):raise AssertionError('NETWORK_DENIED_IN_FILE_ONLY_REPLAY')
socket.socket=denied;socket.create_connection=denied
measure.main(['--signal',str(D/'signal.json'),'--book',str(D/'book.json'),'--market',str(D/'market.json'),'--destination',str(D/'measurement.json'),'--replay-decision-ms',str(stamp)])
x=json.loads((D/'measurement.json').read_bytes());assert x['status']=='UNKNOWN' and x['model_gross'] is None and 'ACCEPTING_STATUS_UNKNOWN' in x['issues'] and 'FEE_SCHEDULE_UNKNOWN' in x['issues']
print(json.dumps({'status':x['status'],'issues':x['issues'],'best_ask':x['best_ask'],'depth_to_limit':x['depth_to_limit'],'book_age_ms':x['book_age_ms'],'source_received_ms':row['received_ms'],'decision_ms':stamp,'market_id':m['id'],'quote_currency':x['quote_currency'],'historical_replay':True,'real_signal':False,'network_denied':True,'real_fill':False,'receipt_sha256':hashlib.sha256((D/'measurement.json').read_bytes()).hexdigest(),'source_proof_sha256':hashlib.sha256((D/'source-proof.json').read_bytes()).hexdigest()}))
