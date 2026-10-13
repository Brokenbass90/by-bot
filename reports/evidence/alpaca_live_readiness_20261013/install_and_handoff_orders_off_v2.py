"""Execute the exact owner-approved inert install and one-line cron retirement.

No broker write, HALT clear, unit registration/activation or monetary permit.
Pending PAPER finality remains explicit. Original PASS-only installer preserved.
"""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from shlex import quote

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_v1 import canonical,digest
from research_lab.alpaca_live_readiness_v1 import verify_package,write_new

REMOTE=r'''
import base64,fcntl,hashlib,json,os,signal,sqlite3,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from dotenv import dotenv_values
signal.alarm(100)
payload=json.load(sys.stdin)
sha=lambda b:hashlib.sha256(b).hexdigest()
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def need(ok,reason):
 if not ok:raise ValueError(reason)
def cli(args):
 r=subprocess.run(args,capture_output=True,timeout=8)
 need(r.returncode==0,'CONTROL_READ_OR_WRITE_FAILED')
 return r.stdout
root=Path('/root/by-bot');base=Path('/opt/bybot-research/alpaca-dynamic-live-20261013')
package=payload['package'];approval=payload['approval'];execution=payload['execution'];proposal=payload['proposal']
need(approval['receipt_sha256']==sha(canonical({k:v for k,v in approval.items() if k!='receipt_sha256'})),'OWNER_AUTHORIZATION_PIN')
need(execution['receipt_sha256']==sha(canonical({k:v for k,v in execution.items() if k!='receipt_sha256'})),'ACTUAL_EXECUTION_PIN')
need(approval['execution_receipt_sha256']==execution['receipt_sha256'],'EXECUTION_SOURCE_PIN')
need(proposal['proposal_sha256']==sha(canonical({k:v for k,v in proposal.items() if k!='proposal_sha256'})),'PROPOSAL_PIN')
need(not base.exists() and not any(p.is_symlink() for p in (base,*base.parents)),'NEW_APP_SCOPE_REQUIRED')
for name in [*package['units'],*package['unapproved_activation_templates']]:
 need(not any((Path(p)/name).exists() for p in ['/etc/systemd/system','/run/systemd/system','/lib/systemd/system']),'DYNAMIC_UNIT_ALREADY_REGISTERED')
lock=Path(proposal['original_shared_lock'])
need(lock==Path('/root/by-bot/runtime/locks/alpaca_bridge_0d0c322aef55c952.lock')
 and lock.is_file() and not lock.is_symlink(),'ORIGINAL_ACCOUNT_LOCK_REQUIRED')
fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
oldbind=json.loads((root/'runtime/alpaca_intended_live/binding.json').read_bytes())
need(oldbind['account_lock_path']==str(lock),'OLD_LOCK_PIN')
halt_path=lock.with_suffix('.paper-kill')/'.paper-entry-halt.json'
halt_raw=halt_path.read_bytes();halt=json.loads(halt_raw)
need(halt['halted'] is True,'LIVE_HALT_REQUIRED')
profile=root/'configs/alpaca_live_v38.env'
need(sha(profile.read_bytes())==payload['authority']['profiles']['configs/alpaca_live_v38.env']['sha256'],'ORIGINAL_PROFILE_PIN')
env=dotenv_values(profile,interpolate=False)
need(env['ALPACA_BASE_URL']=='https://api.alpaca.markets' and env.get('ALPACA_SEND_ORDERS')=='0','EXPLICIT_LIVE_PROFILE_OFF')
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):raise ValueError('REDIRECT_REFUSED')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def broker():
 out={}
 for name,path in [('account','/v2/account'),('positions','/v2/positions'),('open_orders','/v2/orders?status=open&limit=100&nested=true')]:
  req=urllib.request.Request(env['ALPACA_BASE_URL']+path,method='GET',headers={
   'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
  with opener.open(req,timeout=7) as r:raw=r.read(1000001)
  need(len(raw)<1000000,'BROKER_PAGE_BOUNDS');out[name]=dict(payload=json.loads(raw),sha256=sha(raw),receive_ms=time.time_ns()//1000000)
 need(out['account']['payload']['id']==oldbind['account_id']==halt['account_id'],'ACTUAL_ACCOUNT_PIN')
 need(out['positions']['payload']==[] and out['open_orders']['payload']==[],'LIVE_FLAT_NO_ORDERS_REQUIRED')
 return out
def process_check():
 for p in Path('/proc').iterdir():
  if not p.name.isdigit() or int(p.name)==os.getpid():continue
  try:args=(p/'cmdline').read_bytes().decode().split('\0')
  except (FileNotFoundError,PermissionError,ProcessLookupError,UnicodeError):continue
  need(not ('--send-orders' in args or '--apply' in args) or not any('alpaca' in a.lower() for a in args),'ALPACA_WRITER_IN_FLIGHT')
def service_state():
 return {name:dict(line.split('=',1) for line in cli(['systemctl','show',name,'-p','MainPID','-p','NRestarts','-p','ActiveState']).decode().splitlines() if '=' in line)
  for name in ('bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service')}
for name,row in payload['authority']['writers'].items():need(sha((root/name).read_bytes())==row['sha256'],'OLD_WRITER_SOURCE_DRIFT')
for name,row in payload['authority']['profiles'].items():need(sha((root/name).read_bytes())==row['sha256'],'OLD_PROFILE_DRIFT')
process_check();before_broker=broker();before_services=service_state()
before=cli(['crontab','-l']);spool=Path('/var/spool/cron/crontabs/root')
need(sha(before)==proposal['before_sha256'] and sha(spool.read_bytes())==proposal['expected_root_spool_sha256'],'EXACT_CRON_PINS_REQUIRED')
with tempfile.TemporaryDirectory(prefix='alpaca-orders-off-v2-',dir='/opt/bybot-research') as temp:
 stage=Path(temp);app=stage/'app';app.mkdir(mode=0o700)
 for name,row in package['files'].items():
  p=Path(name);need(not p.is_absolute() and '..' not in p.parts and not name.endswith('.env'),'PACKAGE_PATH')
  raw=base64.b64decode(row['content_b64'],validate=True);need(sha(raw)==row['sha256'],'PACKAGE_BYTES')
  target=app/p;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.write_bytes(raw)
 sys.path.insert(0,str(app))
 helper=base64.b64decode(payload['helper_b64'],validate=True);need(sha(helper)==payload['helper_sha256'],'CONTROL_HELPER_PIN')
 scope={'__name__':'approved_orders_off_control'};exec(compile(helper,'orders_off_control','exec'),scope)
 edited=scope['retired_crontab'](before,before_pin=proposal['before_sha256'])
 need(sha(edited)==proposal['after_sha256'],'EXACT_AFTER_CRON_PIN')
 deployment=scope['install_orders_off'](package,approval,execution,now_ms=time.time_ns()//1000000)
 from research_lab.alpaca_live_readiness_v1 import write_new
 rows=[]
 for name,row in payload['sources'].items():
  need(name in {'live_source_book.sqlite','actual_source_basis.json','execution_pending.json','owner_authorization.json','latest_closed_lifecycle.json','original_authority_inventory.json'},'CUSTODY_SOURCE_NAME')
  raw=base64.b64decode(row['content_b64'],validate=True);need(sha(raw)==row['sha256'],'CUSTODY_SOURCE_BYTES')
  p=base/'sources'/name;write_new(p,raw);rows.append(dict(path=str(p),sha256=sha(raw)))
 book=base/'sources/live_source_book.sqlite'
 with sqlite3.connect(book.as_uri()+'?mode=ro',uri=True) as db:
  meta=dict(db.execute('SELECT key,value FROM meta'))
  need(meta['policy']==package['policy_sha256'] and meta['runtime_kind']=='LIVE_DYNAMIC_SEPARATE','SEPARATE_LIVE_BOOK_REQUIRED')
  need(db.execute('SELECT COUNT(*) FROM intents').fetchone()[0]==0,'NO_PAPER_OR_LIVE_INTENT_ADOPTION')
 write_new(base/'control/orders_off_helper_v2.py',helper)
 write_new(base/'control/crontab_before.txt',before);write_new(base/'control/crontab_after.txt',edited)
 write_new(base/'control/root_spool_before.txt',spool.read_bytes())
 process_check()
 need(cli(['crontab','-l'])==before and sha(spool.read_bytes())==proposal['expected_root_spool_sha256'],'CRON_DRIFT_BEFORE_APPLY')
 change=subprocess.run(['crontab','-'],input=edited,capture_output=True,timeout=8)
 need(change.returncode==0,'EXACT_CRON_RETIREMENT_FAILED')
 post=cli(['crontab','-l']);need(post==edited,'POST_CRON_READBACK_FAILED')
 process_check();after_broker=broker();after_services=service_state()
 need(before_services==after_services,'PRODUCTION_PID_OR_RESTART_CHANGED')
 need(halt_path.read_bytes()==halt_raw,'LIVE_HALT_MUTATED')
 scope['physical_check'](deployment)
 for row in rows:need(sha(Path(row['path']).read_bytes())==row['sha256'],'CUSTODY_POSTCHECK_FAILED')
 custody=dict(schema='ALPACA_DYNAMIC_STATIC_CUSTODY_V2',status='STATIC_SOURCES_BOUND_FINALITY_PENDING',
  account_id=oldbind['account_id'],endpoint=env['ALPACA_BASE_URL'],original_shared_lock=str(lock),halt_path=str(halt_path),
  source_book=str(book),package_sha256=package['package_sha256'],source_files=rows,source_manifest_sha256=sha(canonical(rows)),
  paper_cost_finality='PENDING_NOT_PASS',money_go='ABSENT',first_intake='NOT_RESERVED',
  new_manager='DESIGNATED_DISABLED_NO_COMPETING_OLD_CRON',active_dynamic_managers=0,
  original_profiles_unchanged=True,orders_allowed=False,enabled=False)
 write_new(base/'session/static_custody_pending_v2.json',canonical(custody))
 receipt=dict(schema='ALPACA_ORDERS_OFF_INSTALL_HANDOFF_RECEIPT_V2',status='ORDERS_OFF_DEPLOYMENT_HANDOFF_VERIFIED_FINALITY_PENDING',
  observed_ms=time.time_ns()//1000000,owner_authorization_sha256=approval['receipt_sha256'],proposal_sha256=proposal['proposal_sha256'],
  deployment=deployment,custody=custody,cron_before_sha256=sha(before),cron_after_sha256=sha(post),
  root_spool_after_sha256=sha(spool.read_bytes()),cron_write_count=1,other_cron_lines_byte_preserved=True,
  original_lock_held=True,no_old_manager_inflight=True,broker_before=before_broker,broker_after=after_broker,
  service_state_before=before_services,service_state_after=after_services,halt_sha256=sha(halt_raw),
  original_profile_sha256=sha(profile.read_bytes()),broker_writes=0,service_activations=0,orders_allowed=False,
  money_go_received=False,full_paper_pass=False,
  rollback_bytes_verified=edited.replace(scope['PREFIX'].encode(),b'',1)==before,
  rollback='Exact archived crontab only after fresh flat/HALT/no Dynamic writer/fill under original lock. No rollback performed.',
  next_action='Bind actual final PAPER receipt without reinstall; prepare exact first-intent dossier; separate money GO then fresh opening gates.')
 write_new(base/'control/handoff_v2_receipt.json',canonical(receipt))
 print(json.dumps(receipt))
fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd);signal.alarm(0)
'''


def main(output):
    private=ROOT/'.private/alpaca_live_readiness_20261013'
    package=json.loads((private/'disabled_package_posted_fee_v3.json').read_bytes());verify_package(package)
    for name,row in package['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==row['sha256']
    approval=json.loads((ROOT/'reports/evidence/alpaca_live_readiness_20261013/orders_off_now_owner_authorization_v2.json').read_bytes())
    assert approval['authorization_status']=='DIRECT_OWNER_APPROVED','DIRECT_IMMEDIATE_OWNER_APPROVAL_REQUIRED'
    execution=json.loads((ROOT/'reports/evidence/alpaca_live_readiness_20261013/terminal_observation_receipt.json').read_bytes())
    proposal=json.loads((private/'manager_handoff_proposal.json').read_bytes())
    authority_path=private/'authority_before_orders_off_now_v2.json'
    authority=json.loads(authority_path.read_bytes())['response']
    helper=(ROOT/'research_lab/alpaca_orders_off_handoff_v2.py').read_bytes()
    paths={'live_source_book.sqlite':private/'live_source_book_prepared.sqlite',
        'actual_source_basis.json':private/'actual_source_basis.json',
        'execution_pending.json':ROOT/'reports/evidence/alpaca_live_readiness_20261013/terminal_observation_receipt.json',
        'owner_authorization.json':ROOT/'reports/evidence/alpaca_live_readiness_20261013/orders_off_now_owner_authorization_v2.json',
        'latest_closed_lifecycle.json':private/'finality_after_handoff_approval_oct13_1501.json',
        'original_authority_inventory.json':authority_path}
    sources={name:dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),content_b64=base64.b64encode(p.read_bytes()).decode()) for name,p in paths.items()}
    payload=dict(package=package,approval=approval,execution=execution,proposal=proposal,authority=authority,
        helper_b64=base64.b64encode(helper).decode(),helper_sha256=hashlib.sha256(helper).hexdigest(),sources=sources)
    assert output.parent==private and not output.exists()
    command='/root/by-bot/.venv/bin/python -B -c '+quote(REMOTE)
    r=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',command],
        input=canonical(payload),capture_output=True,timeout=120)
    if r.returncode:
        # Only narrow explicit assertion identifiers are reported; no raw HTTP
        # body, profile values, request headers or credentials are printed.
        import re
        reasons=re.findall(rb'(?:ValueError|AssertionError): ([A-Z_0-9:./-]+)',r.stderr)
        print(json.dumps(dict(status='BLOCKED_CONTROL_ACTION',exit=r.returncode,
            reason=reasons[-1].decode() if reasons else 'CONTROL_ACTION_FAILED_REQUIRES_READBACK')))
        write_new(output,canonical(dict(status='BLOCKED_CONTROL_ACTION',remote_return_code=r.returncode,
            raw_stderr_sha256=hashlib.sha256(r.stderr).hexdigest(),money_writes_authorized=False)))
        return 2
    receipt=json.loads(r.stdout)
    assert receipt['broker_writes']==receipt['service_activations']==0 and receipt['orders_allowed'] is False
    capture=dict(script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        query_sha256=hashlib.sha256(REMOTE.encode()).hexdigest(),response=receipt)
    write_new(output,canonical(capture))
    print(json.dumps(dict(status=receipt['status'],package_sha256=package['package_sha256'],
        capture_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),cron_write_count=1,
        broker_writes=0,service_activations=0,orders_allowed=False)))
    return 0


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).absolute()))
