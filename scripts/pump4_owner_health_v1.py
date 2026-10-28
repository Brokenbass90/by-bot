#!/usr/bin/env python3
"""Read-only selected OFF/LIVE health; GET only, no owner/lease/lifecycle constructors."""
import argparse,hashlib,importlib.util,json,os,re,subprocess,time,fcntl,sys
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
def live_evidence(bundle,*,fingerprint,now_ms,config=None,requests=(),known_native_ids=()):
 from decimal import Decimal as D
 from research_lab.pump4_bybit_sources_v1 import flat_account,account_view
 from research_lab.pump4_account_adapter_v1 import frozen_plan,owned_observation
 from research_lab.pump4_native_stop_v1 import verify_mapping
 view=account_view(bundle,expected_fingerprint=fingerprint,now_ms=now_ms)
 need(not view['borrowed_funds'] and view['margin_mode']=='REGULAR_MARGIN','LIVE_MARGIN_OR_BORROW')
 base=dict(source_ms=view['source_ms'],actual_protection_proven=False,financial_trading_proven=False,orders_allowed=False,broker_writes=0)
 if config is None:
  flat_account(bundle,expected_fingerprint=fingerprint,now_ms=now_ms)
  return dict(base,status='LIVE_FLAT_WAITING_SIGNAL')
 p=config['plan'];frozen_plan(p);need(bool(requests),'LIVE_ADMISSION_WITHOUT_REQUEST_RECONCILE')
 if 'native_stop_mapping' in config:verify_mapping(p,config['tick_size'],config['native_stop_mapping'])
 o=owned_observation(bundle,p,list(requests),first_send_ms=p['entry_bar_open_ms'],expected_fingerprint=fingerprint,now_ms=now_ms,known_native_ids=known_native_ids)
 need(not o['foreign_positions'] and not o['borrowed_funds'] and all(r['symbol']==p['symbol'] for r in view['orders']),'LIVE_FOREIGN_EXPOSURE')
 held=D(o['held_qty']);bycid={r['orderLinkId']:r for r in requests};orders={r['orderLinkId']:r for r in o['orders']};entry=D(0);exits=D(0);totals={cid:D(0) for cid in bycid}
 for fill in o['executions']:
  q=D(fill['execQty']);cid=fill['orderLinkId']
  if cid in bycid:
   need(cid in orders and fill['orderId']==orders[cid]['orderId'] and fill['side']==bycid[cid]['side'],'LIVE_FILL_OWNERSHIP')
   totals[cid]+=q
   if bycid[cid]['reduceOnly']:exits+=q
   else:entry+=q
  else:
   need(fill['orderId'] in set(known_native_ids)|({o['native_stop']['orderId']} if o['native_stop'] else set()) and fill['side']==('Buy' if p['side']=='short' else 'Sell'),'LIVE_NATIVE_FILL_OWNERSHIP');exits+=q
 for cid,req in bycid.items():
  need(totals[cid]<=D(req['qty']),'LIVE_FILL_OVER_REQUEST')
  if cid in orders:need(totals[cid]==D(orders[cid]['cumExecQty']),'LIVE_EXECUTION_TOTAL')
 need(D(0)<=exits<=entry<=D(config['qty']) and held==entry-exits,'LIVE_POSITION_RECONCILIATION')
 base.update(source_ms=o['source_ms'],held_qty=str(held),symbol=p['symbol'],financial_trading_proven=entry>0,source_capture_sha256=o['source_capture_sha256'])
 if not held:
  need(not view['orders'],'LIVE_FLAT_HAS_OPEN_ORDERS')
  need(all(cid in orders and orders[cid]['orderStatus'] in {'Filled','Cancelled','Rejected','Deactivated','PartiallyFilledCanceled'} for cid in bycid),'LIVE_UNRESOLVED_REQUEST_RECONCILE')
  return dict(base,status='LIVE_FLAT_COSTS_PENDING',cost_finality_proven=False)
 n=o['native_stop'];need(n is not None,'LIVE_NATIVE_PROTECTION_UNKNOWN')
 intended=D(config['native_stop_mapping']['native_stop'] if 'native_stop_mapping' in config else str(p['stop']));actual=D(n['triggerPrice']);short=p['side']=='short'
 stop_ok=(actual==intended if 'native_stop_mapping' in config else (actual<=intended if short else actual>=intended))
 need(n['orderStatus']=='Untriggered' and D(n['qty'])==held and stop_ok,'LIVE_NATIVE_PROTECTION_UNKNOWN')
 need(D(o['price'])<actual if short else actual<D(o['price']),'LIVE_NATIVE_TRIGGER_RECONCILE')
 return dict(base,status='LIVE_NATIVE_PROTECTED',actual_protection_proven=True,native_stop_id=n['orderId'],native_stop_price=str(actual))

def read_flow(root,scope_digest):
 from research_lab.att1_lifecycle_journal import LifecycleJournal
 from research_lab.pump4_account_adapter_v1 import frozen_plan
 root=Path(root);admission=read(root/'admitted-lifecycle.json');flow=Path(admission['flow_root']);need(flow==root/'flows'/admission['plan_sha256'],'LIVE_FLOW_PATH')
 c=read(flow/'execution-config.json');frozen_plan(c['plan']);pin=digest(c)
 need(admission==dict(scope_sha256=scope_digest,plan_sha256=c['plan']['plan_sha256'],flow_root=str(flow),execution_config_sha256=pin),'LIVE_ADMISSION_IDENTITY')
 need(c['domain']=='PUMP4_BYBIT_EXECUTION_ORDERS_OFF_V1' and c['orders_allowed'] is False and c['money_authority'] is False,'LIVE_FLOW_DOMAIN')
 events=LifecycleJournal(flow/'execution.jsonl').read();requests=[]
 for i,e in enumerate(events):
  need(e['domain']==c['domain'] and e['kind']=='RESERVED_ACTION' and e['config_sha256']==pin and e['event_id']=='pump4-action-'+pin[:20]+'-'+str(i),'LIVE_REQUEST_CHAIN')
  need(e['role'] in ('ENTRY','TP1','TP2','TIME_EXIT'),'LIVE_REQUEST_ROLE');requests.append(e['request'])
 known=[]
 for e in LifecycleJournal(flow/'observations.jsonl').read():
  need(e['domain']==c['domain'] and e['kind']=='OBSERVATION' and e['config_sha256']==pin and e['event_id']=='pump4-observation-'+digest(e['observation']),'LIVE_OBSERVATION_CHAIN')
  if e['verified_native_stop_id'] is not None:
   n=e['observation']['native_stop'];need(n and n['orderId']==e['verified_native_stop_id'],'LIVE_KNOWN_NATIVE_ID');known.append(n['orderId'])
 return c,requests,known,digest(dict(admission=admission,config=c,requests=events))

def collect_live(c,scope):
 from types import SimpleNamespace
 from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials
 from research_lab.pump4_runtime_sources_v1 import TrustedSources
 from research_lab.pump4_bybit_sources_v1 import universe
 original=read(c['original_owner']['path'],c['original_owner']['sha256']);need(all(c[k]==original[k] for k in ('credential_source','credential_source_sha256','account_fingerprint')),'LIVE_ORIGINAL_ACCOUNT')
 key,secret=load_bound_credentials(original);root=Path(scope['root']);admitted=root/'admitted-lifecycle.json';flow=read_flow(root,digest(scope)) if admitted.exists() else None
 output=CONFIG.parent/'health-readonly';need(not any(x.is_symlink() for x in (output,*output.parents)),'HEALTH_OUTPUT_PATH');output.mkdir(mode=0o700,exist_ok=True)
 observer=SimpleNamespace(key=key,secret=secret,root=output,scope=dict(account_fingerprint=c['account_fingerprint'],execution_policy=c.get('execution_policy')),clock=lambda:time.time_ns()//1000000)
 src=TrustedSources(dict(execution_policy=c.get('execution_policy')),observer)
 bundle,_=src.account(flow[0]['plan'],custody=True) if flow else src.flat(metadata_symbol=universe()[0])
 if flow:
  need(read_flow(root,digest(scope))[3]==flow[3],'LIVE_FLOW_CHANGED_DURING_GET')
 else:need(not admitted.exists(),'LIVE_ADMISSION_CHANGED_DURING_GET')
 return live_evidence(bundle,fingerprint=c['account_fingerprint'],now_ms=time.time_ns()//1000000,**(dict(config=flow[0],requests=flow[1],known_native_ids=flow[2]) if flow else {}))

def assess(v,now):
 out=dict(schema='BYBIT_ACCOUNT_HEALTH_V1',observed_ms=now,status='UNHEALTHY',owner='PUMP4',orders_allowed=False,restart_allowed=False,actual_protection_proven=False,financial_trading_proven=False)
 try:
  mode=v.get('mode','ORDERS_OFF');need(mode in ('ORDERS_OFF','OWNER_TINY_LIVE'),'UNKNOWN_MODE')
  need(v['unit']['ActiveState']=='active' and int(v['unit']['MainPID'])>0,'OWNER_NOT_RUNNING')
  need(v['old_inhibited'] and v['lock_held'],'CUSTODY_OR_AUTHORITY_CONFLICT')
  need((not v['go_present']) if mode=='ORDERS_OFF' else (v['go_present'] and v.get('go_verified') is True),'CUSTODY_OR_AUTHORITY_CONFLICT')
  h=v['receipt'];need(h['schema']=='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1' and h['mode']==mode and (h['broker_writes']==0 if mode=='ORDERS_OFF' else h['broker_writes'] is None),'RECEIPT_MODE')
  need(h['pid']==int(v['unit']['MainPID']) and h['scope_sha256']==v['scope_digest'] and h['runner_config_sha256']==v['config_sha256'],'RECEIPT_IDENTITY')
  need(type(h['observed_ms']) is int and 0<=now-h['observed_ms']<=90000,'RECEIPT_STALE_OR_FUTURE')
  need(not h['result']['status'].startswith('BLOCKED'),'SUPERVISOR_SOURCE_BLOCKED')
  if mode=='ORDERS_OFF':return dict(out,status='HEALTHY',reason='ORDERS_OFF_SUPERVISOR_ALIVE',pid=h['pid'],age_ms=now-h['observed_ms'])
  proof=v['live_evidence'];need(type(proof['source_ms']) is int and 0<=now-proof['source_ms']<=5000,'LIVE_ACCOUNT_SOURCE_STALE_OR_FUTURE')
  need(proof['status'] in ('LIVE_FLAT_WAITING_SIGNAL','LIVE_FLAT_COSTS_PENDING','LIVE_NATIVE_PROTECTED'),'LIVE_EVIDENCE_REQUIRED')
  need(proof['actual_protection_proven'] is (proof['status']=='LIVE_NATIVE_PROTECTED'),'LIVE_PROTECTION_PROOF')
  return dict(out,status='HEALTHY',reason=proof['status'],pid=h['pid'],age_ms=now-h['observed_ms'],actual_protection_proven=proof['actual_protection_proven'],financial_trading_proven=proof['financial_trading_proven'],source_age_ms=now-proof['source_ms'])
 except (KeyError,TypeError,ValueError) as e:return dict(out,reason=str(e))
def observe():
 u=state('pump4-execution-owner.service');need(u['FragmentPath']=='/etc/systemd/system/pump4-execution-owner.service' and not u['DropInPaths'],'UNIT_CUSTODY')
 text=Path(u['FragmentPath']).read_text();match=re.search(r'--config '+re.escape(str(CONFIG))+r' --config-sha256 ([0-9a-f]{64}) (--orders-off|--dispatch)(?:\s|$)',text);need(match is not None,'UNIT_MODE')
 pin=match[1];c=read(CONFIG,pin);scope=read(c['authority']['path'],c['authority']['sha256']);mode='OWNER_TINY_LIVE' if match[2]=='--dispatch' else 'ORDERS_OFF';need(c['mode']==scope['mode']==mode and scope['root']==c['custody_runtime_root'],'CONFIG_MODE')
 need(digest({k:v for k,v in c.items() if k not in ('authority','_config_path','_config_sha256')})==scope['runner_config_sha256'],'CONFIG_SCOPE')
 for n,h in c['source_files'].items():need(hashlib.sha256((Path(c['app_root'])/n).read_bytes()).hexdigest()==h,'SOURCE_DRIFT')
 for n,h in c['guard_source_files'].items():need(hashlib.sha256(Path(n).read_bytes()).hexdigest()==h,'GUARD_DRIFT')
 need(hashlib.sha256(subprocess.check_output(['crontab','-l'])).hexdigest()==c['original_cron_sha256'],'CRON_DRIFT')
 root=Path(scope['root']);paths=list((root/'supervisor/receipts').glob('*.json'));need(bool(paths) and len(paths)<200000,'RECEIPT_COVERAGE');last=max(paths,key=lambda p:p.stat().st_mtime_ns)
 old=True
 for name,h in c['inhibitors'].items():
  p=Path('/etc/systemd/system')/(name+'.d/90-kity-micro-inhibit.conf');s=state(name);old &= s['MainPID']=='0' and s['ActiveState'] in ('inactive','failed') and hashlib.sha256(p.read_bytes()).hexdigest()==h
 lock=Path(scope['account_lock_path']);need(lock.stat().st_ino==scope['account_lock_inode'] and lock.stat().st_nlink==1,'LOCK_IDENTITY')
 value=dict(unit=u,old_inhibited=old and Path(c['inhibit_marker']).is_file(),lock_held=held(lock,u['MainPID']),go_present=os.path.lexists(root/'owner-go.json'),receipt=read(last),scope_digest=digest(scope),config_sha256=pin,mode=mode)
 if mode=='OWNER_TINY_LIVE':
  go=root/'owner-go.json';need(go.stat().st_mode&0o777==0o600,'LIVE_GO_MODE');need(read(go)==dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=digest(scope),owner_go_text='GO PUMP4_TINY '+digest(scope)),'LIVE_EXACT_GO')
  sys.path.insert(0,c['app_root'])
  value.update(go_verified=True,live_evidence=collect_live(c,scope))
 return assess(value,time.time_ns()//1000000)
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
