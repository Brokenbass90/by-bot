from pathlib import Path
import json,hashlib,sys,datetime,time
from decimal import Decimal as D
r=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824');sys.path.insert(0,str(r))
from research_lab.polymarket_signal_cycle_v1 import verified_manifest
sha=lambda b:hashlib.sha256(b).hexdigest();rows=[];root=r/'.private/poly_signal_cycle_20261104/runtime-state/E2_20261104'
for p in sorted(root.rglob('outcome.json')):
 z=json.loads(p.read_bytes());f=p.parent;mb,m=verified_manifest(f);assert z['parent_manifest_sha256']==sha(mb)
 d=json.loads((f/'capture/sample-0/measurement.json').read_bytes());sel=next(x['measurement'] for x in d['outcomes'] if x['supplied_signal'])
 polls=[json.loads(x.read_bytes()) for x in (f/'polls').glob('*.json')]
 cap=next(x['capture'] for x in polls if x['capture']['raw_sha256']==z['official_capture_sha256']);assert sha(cap['raw_text'].encode())==cap['raw_sha256']
 data=json.loads(cap['raw_text'])['data'];assert len(data)==1;res=data[0];assert res['status']=='resolved' and res['condition_id']==m['condition_id'];pay=list(map(D,res['payouts']));assert sum(x>0 for x in pay)==1 and all(x>=0 for x in pay)
 resolved=int(datetime.datetime.fromisoformat(res['resolved_at'].replace('Z','+00:00')).timestamp()*1000);assert m['anchored_after_fsync_ms']<resolved==z['official_resolution_ms']<=cap['received_ms']==z['outcome_received_ms']<=z['joined_ms']
 winner=m['tokens'][next(i for i,x in enumerate(pay) if x>0)];won=winner==sel['token_id'];assert won==z['won']
 calc=(D(sel['model_shares']) if won else D(0))-D(sel['model_gross'])-D(sel['estimated_fee']);assert abs(calc-D(z['model_net']))<D('1e-20')
 assert z['real_fill'] is False and z['actual_fees'] is None and z['actual_net_pnl'] is None
 s=json.loads((f/'source-signal.json').read_bytes());rows.append(dict(signal_observation_id=z['signal_observation_id'],market_id=s['market_id'],question=s['question'],manifest_sha256=sha(mb),source_sha256=s['source_sha256'],official_capture_sha256=cap['raw_sha256'],measurement_anchored_ms=m['anchored_after_fsync_ms'],official_resolution_ms=resolved,outcome_received_ms=z['outcome_received_ms'],joined_ms=z['joined_ms'],model_net=z['model_net'],actual_net=None,won=won,model_only=True,before_sports_final_proven=False))
print(json.dumps(dict(schema='POLY_FIRST_REAL_FULL_CYCLES_VERIFIED_V1',observed_ms=time.time_ns()//1000000,rows=rows,measurement_count=len(list(root.rglob('measurement-manifest.json'))),blocked_count=len(list(root.rglob('blocked.json'))),same_completed_match=True,independent_opportunities_qualified=0,real_fills=0,money_authority=False),sort_keys=True,indent=2))
