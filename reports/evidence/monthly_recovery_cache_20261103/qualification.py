import json,xml.etree.ElementTree as E
EXPECTED={('tests.test_alpaca_monthly_standing_v1','test_any_revocation_marker_blocks_buy_without_disabling_maintenance[directory]')}
def need(v,e):
 if not v:raise ValueError(e)
def qualify(candidate,packet,read):
 b={n:read(candidate/n,h) for n,h in packet['qualification_proofs'].items()};a=json.loads(b['acceptance.json']);r=json.loads(b['one-resource-rerun.json'])
 for v in [a,r]:need(v['source_material_sha256']==packet['source_material_sha256'] and v['network_denied'] is True and v['checkout_fallback']==[] and v['real_broker_requests']==v['real_broker_writes']==0,'QUALIFICATION_SOURCE_OR_NETWORK')
 need(a['counts']==dict(tests=307,failures=1,errors=0,skipped=0) and a['status']=='FAIL','ORIGINAL_COUNTS')
 need(r['counts']==dict(tests=1,failures=0,errors=0,skipped=0) and r['status']=='PASS','RERUN_COUNTS')
 def cases(raw):
  rows=list(E.fromstring(raw).iter('testcase'));out={(v.get('classname'),v.get('name')):v for v in rows};need(len(out)==len(rows),'DUPLICATE_NODE');return out
 first=cases(b['exact-tests.xml']);last=cases(b['one-resource-rerun.xml']);need(len(first)==307 and set(last)==EXPECTED,'QUALIFICATION_NODES')
 need({k for k,v in first.items() if v.find('failure') is not None}==EXPECTED,'UNEXPECTED_FAILURE')
 need(all(v.find('error') is None and v.find('skipped') is None for v in first.values()),'ERROR_OR_SKIP')
 need(all(not any(c.tag in {'failure','error','skipped'} for c in v) for v in last.values()),'RERUN_FAILED')
 need('MONTHLY_MANAGER_CLOCK_CONFLICT' in next(iter(first[k].find('failure') for k in EXPECTED)).get('message',''),'FAILURE_CLASSIFICATION')
 return dict(status='EXACT_307_QUALIFIED_WITH_ONE_TIMING_RERUN',unique_tests=307,initial_pass=306,timing_rerun_pass=1,original_failure_retained=True,network_denied=True,real_broker_writes=0)
