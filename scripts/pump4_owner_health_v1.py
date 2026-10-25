#!/usr/bin/env python3
"""Read-only selected ORDERS_OFF supervisor monitor; no broker/owner constructors."""
import argparse,hashlib,importlib.util,json,os,re,subprocess,time,fcntl
from pathlib import Path
CONFIG=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-30677ce61f137272/owner-review-health-v3/runner.json')

def need(v,msg):
 if not v:raise ValueError(msg)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(p,pin=None):
 p=Path(p);need(p.is_absolute() and not any(x.is_symlink() for x in (p,*p.parents)),'PATH');st=p.stat();need(p.is_file() and st.st_nlink==1 and st.st_uid==os.geteuid() and st.st_size<2000000,'CUSTODY');raw=p.read_bytes()
 if pin:need(hashlib.sha256(raw).hexdigest()==pin,'PIN')
 return json.loads(raw)
def state(unit):return dict(r.split('=',1) for r in subprocess.check_output(['systemctl','show',unit,'--property=MainPID,ActiveState,FragmentPath,DropInPaths'],text=True,timeout=3).splitlines() if '=' in r)
def held(lock,pid):
 st=lock.stat();key=f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}'
 return any(len(v)==8 and v[1:4]==['FLOCK','ADVISORY','WRITE'] and v[4]==str(pid) and v[5:]==[key,'0','EOF'] for v in (r.split() for r in Path('/proc/locks').read_text().splitlines()))
def assess(v,now):
 out=dict(schema='BYBIT_ACCOUNT_HEALTH_V1',observed_ms=now,status='UNHEALTHY',owner='PUMP4',orders_allowed=False,restart_allowed=False)
 try:
  need(v['unit']['ActiveState']=='active' and int(v['unit']['MainPID'])>0,'OWNER_NOT_RUNNING')
  need(v['old_inhibited'] and v['lock_held'] and not v['go_present'],'CUSTODY_OR_AUTHORITY_CONFLICT')
  h=v['receipt'];need(h['schema']=='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1' and h['mode']=='ORDERS_OFF' and h['broker_writes']==0,'RECEIPT_MODE')
  need(h['pid']==int(v['unit']['MainPID']) and h['scope_sha256']==v['scope_digest'] and h['runner_config_sha256']==v['config_sha256'],'RECEIPT_IDENTITY')
  need(type(h['observed_ms']) is int and 0<=now-h['observed_ms']<=90000,'RECEIPT_STALE_OR_FUTURE')
  need(not h['result']['status'].startswith('BLOCKED'),'SUPERVISOR_SOURCE_BLOCKED')
  return dict(out,status='HEALTHY',reason='ORDERS_OFF_SUPERVISOR_ALIVE',pid=h['pid'],age_ms=now-h['observed_ms'],financial_trading_proven=False)
 except (KeyError,TypeError,ValueError) as e:return dict(out,reason=str(e))
def observe():
 u=state('pump4-execution-owner.service');need(u['FragmentPath']=='/etc/systemd/system/pump4-execution-owner.service' and not u['DropInPaths'],'UNIT_CUSTODY')
 text=Path(u['FragmentPath']).read_text();match=re.search(r'--config '+re.escape(str(CONFIG))+r' --config-sha256 ([0-9a-f]{64}) --orders-off',text);need(match is not None,'UNIT_MODE')
 pin=match[1];c=read(CONFIG,pin);scope=read(c['authority']['path'],c['authority']['sha256']);need(c['mode']==scope['mode']=='ORDERS_OFF' and scope['root']==c['custody_runtime_root'],'CONFIG_MODE')
 need(digest({k:v for k,v in c.items() if k not in ('authority','_config_path','_config_sha256')})==scope['runner_config_sha256'],'CONFIG_SCOPE')
 for n,h in c['source_files'].items():need(hashlib.sha256((Path(c['app_root'])/n).read_bytes()).hexdigest()==h,'SOURCE_DRIFT')
 for n,h in c['guard_source_files'].items():need(hashlib.sha256(Path(n).read_bytes()).hexdigest()==h,'GUARD_DRIFT')
 need(hashlib.sha256(subprocess.check_output(['crontab','-l'])).hexdigest()==c['original_cron_sha256'],'CRON_DRIFT')
 root=Path(scope['root']);paths=list((root/'supervisor/receipts').glob('*.json'));need(bool(paths) and len(paths)<200000,'RECEIPT_COVERAGE');last=max(paths,key=lambda p:p.stat().st_mtime_ns)
 old=True
 for name,h in c['inhibitors'].items():
  p=Path('/etc/systemd/system')/(name+'.d/90-kity-micro-inhibit.conf');s=state(name);old &= s['MainPID']=='0' and s['ActiveState'] in ('inactive','failed') and hashlib.sha256(p.read_bytes()).hexdigest()==h
 lock=Path(scope['account_lock_path']);need(lock.stat().st_ino==scope['account_lock_inode'] and lock.stat().st_nlink==1,'LOCK_IDENTITY')
 return assess(dict(unit=u,old_inhibited=old and Path(c['inhibit_marker']).is_file(),lock_held=held(lock,u['MainPID']),go_present=os.path.lexists(root/'owner-go.json'),receipt=read(last),scope_digest=digest(scope),config_sha256=pin),time.time_ns()//1000000)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--spec-sha256',required=True);ap.add_argument('--no-notify',action='store_true');a=ap.parse_args();spec=read(a.spec,a.spec_sha256)
 fd=os.open(spec['observer_lock'],os.O_RDONLY|os.O_NOFOLLOW)
 try:
  try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return 0
  legacy=CONFIG.parent/'health-legacy-immutable.py';need(hashlib.sha256(legacy.read_bytes()).hexdigest()=='4c1674865daf0e2da2014642d2d474f8e206c2c885f14f0cc40bc16b65654ed8','NOTIFY_HELPER_PIN');sp=importlib.util.spec_from_file_location('legacy',legacy);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
  try:result=observe()
  except Exception as e:result=dict(schema='BYBIT_ACCOUNT_HEALTH_V1',status='UNHEALTHY',observed_ms=time.time_ns()//1000000,owner='PUMP4',reason='OBSERVER_'+str(e),orders_allowed=False,restart_allowed=False)
  # Existing channel and persistent state; unchanged failures do not repeat.
  marker=CONFIG.parent/'observer-state.json';prior=read(marker) if marker.exists() else {}
  if not a.no_notify and result['status']!='HEALTHY' and (prior.get('status'),prior.get('reason'))!=(result['status'],result['reason']):
   try:result['notification']=m.notify(spec,result)
   except Exception:result['notification']='UNKNOWN_NO_RETRY'
  if not a.no_notify:m.save_state(marker,{k:result[k] for k in ('status','reason','observed_ms')})
  print(json.dumps(result));return 0 if result['status']=='HEALTHY' else 2
 finally:os.close(fd)
if __name__=='__main__':raise SystemExit(main())
