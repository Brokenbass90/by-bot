"""Offline reconstruction of the fixed51; no evaluator, returns, network or writes.

Run from recovery checkout: .venv/bin/python -B <this file>
Only frozen strategy modules are imported. Compressed inputs exclude outcomes.
"""
from pathlib import Path
import collections,dataclasses,gzip,hashlib,json,sys
P=Path(__file__).resolve().parent;ROOT=P.parents[2];sys.path.insert(0,str(ROOT))
from research_lab.pump4_execution_plan_v1 import frozen_sources
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.att1_lifecycle_journal import SCHEMA
from strategies.pump_fade_v4r import PumpFadeV4RStrategy

H=3600000;frozen_sources()
m=json.loads((P/'manifest.json').read_bytes());raw=(P/'signal-only-inputs.json.gz').read_bytes()
assert hashlib.sha256(raw).hexdigest()==m['input_blob_sha256']
raw=gzip.decompress(raw);assert hashlib.sha256(raw).hexdigest()==m['decoded_input_sha256']
d=json.loads(raw);journal=d['journal'];cases=[x for x in d['diagnostic']['resheniya'] if x['klass']=='NE_VOSPR'];assert len(cases)==51
key=lambda x:(x['sym'],x['ts'],x['side'])
assert hashlib.sha256(json.dumps(sorted(key(x) for x in cases),separators=(',',':')).encode()).hexdigest()==m['case_membership_sha256']
def run(sym,bars,target,skip):
    s=PumpFadeV4RStrategy()
    for b in bars:
        if b[0]>target:break
        if skip(b):continue
        previous=dict(s.skip_reason_stats());before=s._cooldown;v=s.maybe_signal(sym,*b)
        if b[0]==target:
            reasons={k:n-previous.get(k,0) for k,n in s.skip_reason_stats().items() if n>previous.get(k,0)}
            return (dataclasses.asdict(v) if v else None),before,s._cooldown,reasons
    return None,None,None,{}
counts={};saved=json.loads((P/'signal-reconciliation.json').read_bytes())
for dataset in ('fresh_public','archived_public'):
    covered=0;insufficient=0;expected={key(x):x for x in saved['datasets'][dataset.replace('_','-')]['cases']}
    for c in cases:
        sym,target,side=key(c);i=next(i for i,x in enumerate(journal) if key(x)==key(c));row=journal[i];bars=d[dataset][sym]
        start=min(x['ts'] for x in journal if x['sym']==sym)-1000*H;window=row['zapisano']//H*H-999*H
        if bars[0][0]>min(start,window) or bars[-1][0]<target:insufficient+=1;continue
        ref=[b for b in bars if start<=b[0]<=target][200:]
        win=[b for b in bars if window<=b[0]<row['zapisano']//H*H][200:];seen={x['ts'] for x in journal[:i] if x['sym']==sym};nachalo=d['state_current']['nachalo']
        a=run(sym,ref,target,lambda b:False);b=run(sym,win,target,lambda b:b[0]<nachalo);c0=run(sym,win,target,lambda b:b[0]<nachalo or b[0] in seen)
        assert a[0] is b[0] is None and a[3]==b[3]=={'COOLDOWN_ACTIVE':1}
        assert c0[0] is not None and c0[0]['side']==side
        assert a[0]==expected[key(c)]['schedules']['reference']['signal'] and c0[0]==expected[key(c)]['schedules']['shadow_seen']['signal']
        covered+=1
    counts[dataset]=dict(reconstructed_by_seen_omission=covered,insufficient_range=insufficient)
assert counts==dict(fresh_public=dict(reconstructed_by_seen_omission=51,insufficient_range=0),archived_public=dict(reconstructed_by_seen_omission=49,insufficient_range=2))
# Check the continuous call schedule against the actual frozen intake, in memory.
intake_checked=0
for sym in sorted({x['sym'] for x in cases}):
    targets=[x for x in cases if x['sym']==sym];start=min(x['ts'] for x in journal if x['sym']==sym)-1000*H;end=max(x['ts'] for x in targets)
    bars=[b for b in d['fresh_public'][sym] if start<=b[0]<=end];intake=Pump4Intake(P/'NEVER_CREATED'/sym,sym);ctx=intake._context();seed=bars[:1000]
    events=[dict(schema_id=SCHEMA,event_id='pump4:'+sym+':seed',**ctx,kind='HISTORICAL_SEED',bars=seed,available_ms=seed[-1][0]+H,observed_ms=seed[-1][0]+H)]
    events += [dict(schema_id=SCHEMA,event_id='pump4:'+sym+':'+str(b[0]),**ctx,kind='CLOSED_BAR',bar=b,available_ms=b[0]+H,observed_ms=b[0]+H) for b in bars[1000:]]
    decisions={x['bar_open_ms']:x for x in intake._replay(events)['decisions']}
    for c in targets:assert decisions[c['ts']]['signal'] is None;intake_checked+=1
assert intake_checked==51
print(json.dumps(dict(status='PASS',datasets=counts,canonical_intake_cases=intake_checked,producer_changed=False,PnL_evaluator_calls=0,financial_authority=False,historical_run_attested=False),sort_keys=True))
