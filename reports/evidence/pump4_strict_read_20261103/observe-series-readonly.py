"""GET-only fixed six-H1 acceptance. No repair, broker calls or financial imports."""
import pathlib,hashlib,json,subprocess,time
P=pathlib.Path('/opt/bybot-research/pump4-data-throughput-20261103/strict-read-6f65581e0f6615de')
ROOT=pathlib.Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-7d8ae05dab162ec5/app/.private/pump4-supervisor-v1')
H=3600000;FIRST=1793736000000
sha=lambda b:hashlib.sha256(b).hexdigest()
def need(x,s):
 if not x:raise ValueError(s)
def show(n):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',n,'-p','MainPID','-p','ActiveState','-p','NRestarts','-p','DropInPaths'],text=True).splitlines() if '=' in x)
def collect():
 raw=(P/'patch-manifest.json').read_bytes();need(sha(raw)=='746f35af071b7383f387afc9ca9ec1766a185cf74d2a10de1ec0e9145c016ba8','MANIFEST_DRIFT');m=json.loads(raw)
 for n,h in m['files'].items():need(sha((P/n).read_bytes())==h,'OVERLAY_FILE_DRIFT')
 need(sha((P/'quiet-handoff.py').read_bytes())=='5be1055772b51f94562540be6fe57bb4b632974cfbfb74b4a2e686f6dea26e7b','HELPER_DRIFT')
 now=time.time_ns()//1000000;out=dict(observed_ms=now,status='PENDING_HANDOFF',hours=[],files={},broker_requests=0,broker_writes=0,financial_changes=False)
 for n in ['strict-v1-handoff-result.json','strict-v1-handoff-failed.json','strict-v1-actual-h1-after.json','strict-v1-actual-h1-unconfirmed.json']:
  p=P/n
  if p.exists():b=p.read_bytes();out['files'][n]=dict(sha256=sha(b),value=json.loads(b))
 units=['pump4-data-supervisor.service','pump4-execution-owner.service','alpaca-monthly-owned.service'];out['units']={n:dict(sha256=sha((pathlib.Path('/etc/systemd/system')/n).read_bytes()),state=show(n)) for n in units};out['account_lock_inode']=pathlib.Path('/opt/bybot-research/kity-micro-owner-20261015/runtime/account.lock').stat().st_ino
 owner=out['units'][units[1]];need(owner['sha256']=='991211ed5db0c9dd163193141179eefe9a266298d9bdde1491dc0904793fb843' and owner['state']['MainPID']=='3669955' and owner['state']['NRestarts']=='0' and owner['state']['ActiveState']=='active' and not owner['state']['DropInPaths'] and out['account_lock_inode']==818853,'FINANCIAL_OWNER_DRIFT')
 need(out['units'][units[2]]['sha256']=='f167c6ccf922902d5bee874ca4946bfb6d5c8bf227df31f2144f595e2ad0a81c','MONTHLY_UNIT_DRIFT')
 if any(n in out['files'] for n in ['strict-v1-handoff-failed.json','strict-v1-actual-h1-unconfirmed.json']):out['status']='HANDOFF_OR_ACTUAL_H1_FAILURE';return out
 if 'strict-v1-handoff-result.json' not in out['files']:return out
 data=out['units'][units[0]];handoff=out['files']['strict-v1-handoff-result.json']['value'];need(data['sha256']=='9c7ff89367ba1a69c419fc5ffc8260f078e998a2886bbc6373148bc06f7bbcbe' and data['state']['MainPID']==str(handoff['new_data_pid']) and data['state']['NRestarts']=='0' and data['state']['ActiveState']=='active' and not data['state']['DropInPaths'],'SELECTED_DATA_DRIFT')
 if now>=FIRST+125000:
  if 'strict-v1-actual-h1-after.json' not in out['files']:
   out['status']='NATIVE_ACTUAL_PROOF_MISSING' if now>=FIRST+600000 else 'NATIVE_ACTUAL_PROOF_PENDING';return out
  actual=out['files']['strict-v1-actual-h1-after.json']['value'];need(actual['actual_data_pid']==handoff['new_data_pid'] and actual['actual_data_unit_sha256']==data['sha256'] and actual['actual_hour']['hour_open_ms']==FIRST,'ACTUAL_NATIVE_PROOF_DRIFT')
 for hour in range(FIRST,FIRST+6*H,H):
  if now<hour+125000:break
  p=ROOT/'ws-hours'/str(hour)/'receipt.json'
  if not p.exists():out['status']='SERIES_MISSING_RECEIPT';out['missing_hour_ms']=hour;return out
  b=p.read_bytes();v=json.loads(b);rows=[r for r in v['rows'] if r.get('status')=='CLOSED_H1_INTAKE_PASS'];last=max((r['publication_completed_ms']-hour for r in rows),default=None)
  if hour==FIRST:need(sha(b)==actual['actual_hour']['receipt_sha256'],'ACTUAL_SOURCE_RECEIPT_DRIFT')
  r=dict(hour_open_ms=hour,receipt_sha256=sha(b),complete=v['complete_pairs'],expected=v['expected_trading'],within60=v['within60s'],hour_pass=v['hour_pass'],disconnected=v['disconnected'],last_publication_offset_ms=last,raw_signals=sum(bool(r['decisions'][0]['decision']['signal']) for r in rows));out['hours'].append(r)
  if not(r['complete']==r['expected']==r['within60']==len(rows)==134 and r['hour_pass'] is True and not r['disconnected'] and last is not None and 0<=last<=60000):out['status']='SERIES_SOURCE_BLOCKED';return out
 out['status']='SERIES_SIX_H1_PASS' if len(out['hours'])==6 else 'FIRST_H1_PASS_SERIES_PENDING' if out['hours'] else 'HANDOFF_CONFIRMED_ACTUAL_H1_PENDING';return out
if __name__=='__main__':
 try:print(json.dumps(collect(),sort_keys=True))
 except Exception as e:print(json.dumps(dict(observed_ms=time.time_ns()//1000000,status='UNKNOWN',reason=type(e).__name__+':'+str(e),broker_requests=0,financial_changes=False)))
