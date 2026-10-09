"""Source-bound one-plan preparation on the staged app. No broker order writes."""
import base64,hashlib,json,os,subprocess,sys,time
from datetime import datetime
from decimal import Decimal,ROUND_DOWN,ROUND_HALF_UP
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
raw=Path(sys.argv[1]).read_bytes();a=json.loads(raw)['response']
sys.path.insert(0,str(ROOT))
from reports.evidence.alpaca_opening_20261009.source_gate import require_review
# A raw process scan/exclusion snapshot alone never supplies complete gate truth.
# No review means rejection before constructing a snapshot or making SSH writes.
review=json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv)>3 else None
review_binding=require_review(review,hashlib.sha256(raw).hexdigest(),time.time_ns()//1000000)
broker=a['reports/evidence/money_morning_20261008/alpaca_broker_read_only.py'];q=a['reports/evidence/money_morning_20261008/alpaca_quote_lineage_read_only.py'];w=a['opening_writer_sources']
live={k:json.loads(v['raw']) for k,v in broker['live'].items()};paper={k:json.loads(v['raw']) for k,v in broker['paper'].items()}
quote=json.loads(q['quote_sources']['iex']['raw'])['quote'];quote_ms=int(datetime.fromisoformat(quote['t'].replace('Z','+00:00')).timestamp()*1000)
now=broker['completed_ms'];start=1791552600000
assert start<=quote_ms<=now and 0<=now-quote_ms<=300000 and Decimal(str(quote['ap']))>0
assert live['account']['id']=='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6' and not live['positions'] and not live['open_orders']
assert paper['account']['id']=='4cdbfb77-d1e0-4789-86b2-341bc886efaf' and len(paper['positions'])==5 and not paper['open_orders']
assert not any(p['symbol']=='XOM' for p in paper['positions'])
assert live['account']['pending_reg_taf_fees']==live['account']['accrued_fees']=='0'
assert live['account']['cash']==live['account']['non_marginable_buying_power']=='496.12'
assert broker['live_runtime']['entry_halt']['halted'] and w['shared_lock_available'] and not w['matching_processes']
assert all(not x['mismatches'] for x in broker['source_manifests'].values())
assert broker['paper_runtime']['legacy_exclusions_sha256']=='8171cd5ef14f8374e75f6406476d254c816465ef96cab8a52ac335d2f2122e3f'
assert all(x['counts']=={'rankings':1,'slots':3,'intents':0,'exits':0} for x in broker['books'].values())
asset=live['asset_XOM'];assert asset['symbol']=='XOM' and asset['status']=='active' and asset['tradable'] and asset['fractionable']
policy=json.loads((ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_text());slot=sorted(policy['inherited_slots'],key=lambda s:s['entry_order_id'])[0]
ranking=json.loads(q['book_rows']['rankings'][0][-1]);pick=ranking['picks'][0];assert pick['symbol']=='XOM'
price=Decimal(str(quote['ap']));distance=Decimal(str(pick['signal_close']))-Decimal(str(pick['stop_price']));stop=(price-distance).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);distance=price-stop
ceiling=(min(Decimal(slot['notional_cap'])/price,Decimal(slot['risk_cap'])/distance)/Decimal('.000000001')).to_integral_value(rounding=ROUND_DOWN)*Decimal('.000000001')
sys.path.insert(0,str(ROOT));from reports.evidence.alpaca_b3_gate_closure_20261008.fee_reserve_input import prepare_entry_cost_input
cost=prepare_entry_cost_input(str(ceiling),'0',ROOT/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json')
exits=[]
for s in policy['inherited_slots']:
 rows=[o for o in live['order_source'] if o['symbol']==s['symbol'] and o['side']=='sell' and o['status']=='filled' and Decimal(o['filled_qty'])>0]
 assert sum(Decimal(o['filled_qty']) for o in rows)==Decimal(s['qty'])
 exits.append({'entry_order_id':s['entry_order_id'],'orders':[{k:o[k] for k in ['id','symbol','side','status','filled_qty','filled_avg_price']}|{'filled_ms':int(datetime.fromisoformat(o['filled_at'].replace('Z','+00:00')).timestamp()*1000)} for o in rows]})
closed=json.loads(w['closed_source']['raw'])
snapshot={'account_id':live['account']['id'],'observed_ms':broker['completed_ms'],'source_sha256':hashlib.sha256(raw).hexdigest(),'single_owner_verified':True,'cash_finality_verified':True,'cash_usd':'496.12','liability_reserve_usd':cost['liability_reserve_usd'],'fee_rate':cost['fee_rate'],'positions':[],'open_orders':[],'exits':exits,'blocked_symbols':['AMD','CRWD','META'],'quotes':{'XOM':{'ask':str(price),'received_ms':q['quote_sources']['iex']['receive_ms'],'qty_step':'.000000001','min_qty':'.000000001','min_notional':'1','tradable':True,'fractionable':True}},'gates':{'XOM':{'earnings':True,'concentration':True,'symbol':True,'protection':True}}}
bundle={'schema':'ALPACA_DYNAMIC_INPUT_BUNDLE_V1','captured_ms':max(q['completed_ms'],w['observed_ms'],broker['completed_ms']),'history_available_ms':closed['received_ms'],'history':closed['history'],'snapshot':snapshot}
payload={'bundle':bundle,'cost':cost,'source_archive_sha256':hashlib.sha256(raw).hexdigest(),'operator_review':review,'review_binding':review_binding,'expected_manifest_sha256':'4f6e5288790174b9a9fdfb031d4e7a229c8b852ed2eef96785003d30961f76d3'}
encoded=base64.b64encode(json.dumps(payload).encode()).decode()
remote=r'''
import base64,json,sys,time,hashlib,os,fcntl,subprocess
from pathlib import Path
from decimal import Decimal
data=json.loads(base64.b64decode(ENCODED));base=Path('/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007');app=base/'app';sys.path.insert(0,str(app))
assert hashlib.sha256((app/'source_manifest.json').read_bytes()).hexdigest()==data['expected_manifest_sha256']
assert all(hashlib.sha256((app/n).read_bytes()).hexdigest()==h for n,h in json.loads((app/'source_manifest.json').read_text()).items())
from research_lab.alpaca_dynamic_paper import earnings_check
from scripts.run_alpaca_dynamic_capture import concentration_check
from scripts.run_alpaca_dynamic_v1_orders_off import load_history,run
import yfinance as yf
frame=yf.Ticker('XOM').get_earnings_dates(limit=12);dates=sorted({str(x.date()) for x in frame.index});earnings={'provider':'existing Yahoo/yfinance','dates':dates,'received_ms':time.time_ns()//1000000}
assert earnings_check(dates,'2026-10-09')['safe'],'EARNINGS_CURRENT_SOURCE_BLOCKED'
assert concentration_check('XOM',[],load_history(data['bundle']['history']))['safe']
excl=Path('/root/by-bot/runtime/alpaca_intended_paper/legacy_exclusions.json');assert hashlib.sha256(excl.read_bytes()).hexdigest()=='8171cd5ef14f8374e75f6406476d254c816465ef96cab8a52ac335d2f2122e3f'
assert hashlib.sha256(Path('/root/by-bot/runtime/alpaca_intended_paper/legacy_preserve.sh').read_bytes()).hexdigest()=='f61591405dd9533d750568e099aeb6b9fd642638f42fa4198e37cf1008ee6d61'
now=time.time_ns()//1000000;assert 1791552600000<=now<1791552900000
directory=base/'runtime/opening_oct9';directory.mkdir(mode=0o700)
def save(name,value):
 p=directory/name
 with p.open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 return p
source_binding={'source_archive_sha256':data['source_archive_sha256'],'cost':data['cost'],'fresh_earnings':earnings,'operator_review':data['operator_review'],'review_binding':data['review_binding'],'raw_quote_timestamp_enforced':True,'legacy_exclusion_verified':True,'known_old_cash_finality_reverified':True,'not_new_strategy_or_live_go':True}
save('source_binding.json',source_binding)
binding_sha=hashlib.sha256(json.dumps(source_binding,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
bundle=data['bundle'];bundle['captured_ms']=now;bundle['snapshot']['source_sha256']=binding_sha
save('actual_input.json',bundle)
policy=json.loads((app/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_text())
with Path('/root/by-bot/runtime/locks/alpaca_bridge_5cec021eb9d04382.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 receipt=run(policy,base/'runtime/rehearsal',bundle,time.time_ns()//1000000)
 assert receipt['status']=='RESERVED_ORDERS_OFF',receipt
 assert Decimal(receipt['qty'])<=Decimal(data['cost']['entry_qty_ceiling']) and Decimal(receipt['funding_limit_usd'])<=Decimal('496.12')-Decimal(data['cost']['liability_reserve_usd'])
 save('plan.json',receipt)
print(json.dumps({'status':receipt['status'],'plan':receipt,'cost':data['cost'],'fresh_earnings':earnings,'plan_path':str(directory/'plan.json'),'broker_writes':0,'live_changed':False}))
'''.replace('ENCODED',repr(encoded))
process=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119','/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=65)
if process.returncode:sys.stderr.write(process.stderr.decode()[-3000:]);raise SystemExit(process.returncode)
result=json.loads(process.stdout);out=Path(sys.argv[2])
with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
