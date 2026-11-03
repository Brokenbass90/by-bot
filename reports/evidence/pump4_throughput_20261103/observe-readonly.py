"""GET-only physical DATA repair observer, no subprocess mutations or broker."""
import hashlib,json,subprocess,time
from pathlib import Path
P=Path('/opt/bybot-research/pump4-data-throughput-20261103/patch-59f6639e8c700153');PIN='59f6639e8c70015391e756bb1d5a217904dc6b2c204f750d6e52e254522d4e15'
def sha(b):return hashlib.sha256(b).hexdigest()
b=(P/'patch-manifest.json').read_bytes();assert sha(b)==PIN,'PATCH_MANIFEST_DRIFT';manifest=json.loads(b)
for n,h in manifest['files'].items():assert sha((P/n).read_bytes())==h,'PATCH_SOURCE_DRIFT'
def state(u):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',u,'-p','MainPID','-p','NRestarts','-p','ActiveState','-p','SubState'],text=True).splitlines() if '=' in x)
out=dict(schema='PUMP4_WARM_PHYSICAL_OBSERVER_V1',observed_ms=time.time_ns()//1000000,patch_manifest_sha256=PIN,broker_requests=0,broker_writes=0,data=state('pump4-data-supervisor.service'),owner=state('pump4-execution-owner.service'),watcher=state('pump4-data-warm-handoff-v2-20261103.service'))
for n in ['v2-handoff-result.json','v2-handoff-failed.json','v2-actual-h1-after.json','v2-actual-h1-unconfirmed.json']:
 p=P/n
 if p.is_file():
  b=p.read_bytes();out[n]={'sha256':sha(b),'value':json.loads(b)}
f=out.get('v2-handoff-failed.json')
if f:out['status']='DATA_HANDOFF_FAILED'
elif 'v2-handoff-result.json' not in out:out['status']='PENDING_SAFE_BOUNDARY'
else:
 r=out['v2-handoff-result.json']['value'];assert out['data']['MainPID']==str(r['new_data_pid']),'DATA_PID_DRIFT';assert sha(Path('/etc/systemd/system/pump4-data-supervisor.service').read_bytes())=='0e227ab316240795ba73bc3ec81d513b12b579327d691ecaac84ad5b8efff8c1','DATA_UNIT_DRIFT'
 assert out['owner']['MainPID']=='3669955' and out['owner']['NRestarts']=='0' and out['owner']['ActiveState']=='active','FINANCIAL_OWNER_DRIFT'
 out['status']='DATA_PATCH_SELECTED_H1_PENDING'
 if 'v2-actual-h1-after.json' in out:
  a=out['v2-actual-h1-after.json']['value']['actual_hour'];out['status']='ACTUAL_NEW_H1_SOURCE_PASS' if a['hour_pass'] and a['complete']==a['expected']==a['within60']==134 else 'ACTUAL_NEW_H1_SOURCE_BLOCKED'
 elif 'v2-actual-h1-unconfirmed.json' in out:out['status']='ACTUAL_NEW_H1_UNKNOWN'
print(json.dumps(out,sort_keys=True))
