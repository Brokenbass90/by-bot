#!/usr/bin/env python3
"""HUMAN ONLY monetary activation of one pre-pinned batch policy.

Agents may inspect the packet, but must never use --owner-execute. Default is
offline. Does not create a policy, widen bounds, repeat GO or submit an order.
The existing single account writer owns dispatch, protection and finality.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(ok,reason):
    if not ok:raise ValueError(reason)
def read(p):return json.loads(Path(p).read_bytes())
def session(p,at):
    need(type(at) is int and p['created_ms']<=at<p['valid_until_ms'],'OWNER_POLICY_EXPIRED_OR_NOT_STARTED')
def config_delta(old,new,expiry):
    expected=dict(old,money_go=True,policy_valid_until_ms=expiry,unit_template_sha256=new['unit_template_sha256'])
    need(old['money_go'] is False and new==expected,'UNAPPROVED_CONFIG_DELTA')
def rollback_safe(root):
    root=Path(root)
    return not ((root/'go-may-have-been-queued.json').exists() or (root/'selected-batch.json').exists()
                or any((root/'wire').glob('send-*.json')))


def approved_bounds(base):
    from research_lab.kity_execution_micro_runtime_v1 import _owner_bounds
    bounds=_owner_bounds(base['bounds'])
    need(base['dispatch_window_ms']==60000 and bounds['schema'] in (
        'kity_execution_micro_owner_bounds_v3','kity_execution_micro_owner_bounds_v4'), 'POLICY_BOUNDS_CONFLICT')


def queue_command(new,manifest):
    """Personal-execution path only; module imports resolve from pinned app."""
    return subprocess.check_output([sys.executable,'-B','-m','research_lab.kity_batch_service_v1',
        '--config',manifest['new_config'],'--config-sha256',sha(Path(manifest['new_config']).read_bytes()),
        '--owner-go-batch',manifest['policy_id']],cwd=new['app_root'],
        text=True,stderr=subprocess.PIPE,timeout=20)


def load(path,pin):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'MANIFEST_PIN')
    m=json.loads(raw);need(m['schema']=='KITY_BATCH_OWNER_PACKET_V1','OWNER_PACKET_SCOPE')
    for p,want in m['files'].items():need(sha(Path(p).read_bytes())==want,'OWNER_PACKET_SOURCE_DRIFT')
    old,new=read(m['old_config']),read(m['new_config'])
    sys.path.insert(0,new['app_root'])
    from research_lab.kity_batch_ws_v1 import validate_batch_policy
    policy=read(m['policy_path']);validate_batch_policy(policy)
    need(policy['batch_policy_id']==m['policy_id'],'EXACT_NEW_POLICY_REQUIRED')
    base=policy['base_policy'];session(base,time.time_ns()//1000000)
    config_delta(old,new,base['valid_until_ms'])
    need(base['physical_config_sha256']==sha(Path(m['new_config']).read_bytes()),'POLICY_CONFIG_CONFLICT')
    approved_bounds(base)
    need(sha(Path(m['unit_path']).read_bytes())==m['old_unit_sha256'],'CURRENT_UNIT_DRIFT_OR_ALREADY_ACTIVATED')
    root=Path(new['runtime_root']);need(rollback_safe(root),'POLICY_HISTORY_NOT_EMPTY')
    for p in (root/'commands').glob('*.json'):
        need((root/'results'/p.name).is_file() and read(p).get('kind')=='PREPARE_BATCH','PENDING_OR_MONETARY_CONTROL')
    h=read(Path(new['custody_runtime_root'])/'heartbeat.json')
    need(h['mode']=='ORDERS_OFF' and h['phase']=='NO_ACTIVE_PLAN' and h.get('error') is None
         and h['private_authenticated'] is True and h['private_subscribed'] is True
         and 0<=time.time_ns()//1000000-h['at_ms']<10000,'OWNER_NOT_HEALTHY_IDLE')
    return m,old,new,policy


def owner_execute(m,old,new,policy):
    """Never called by an agent. The personal shell command calls this once."""
    from research_lab.kity_micro_physical_owner_v1 import AccountLease,load_bound_credentials,publish,rows
    from research_lab.kity_micro_transport_v1 import BybitReadTransport,wire_get
    from research_lab.kity_micro_bounded_owner_v2 import read_predecessor
    root=Path(new['runtime_root']);unit=Path(m['unit_path']);lease=None;changed=False
    claim=root/'personal-owner-launch-20261017.json'
    publish(claim,dict(policy_id=m['policy_id'],at_ms=time.time_ns()//1000000,status='PERSONAL_OWNER_LAUNCH_ONCE'))
    key,secret=load_bound_credentials(new)
    reader=BybitReadTransport(key,secret,wire=lambda a,b,c,d,e:wire_get(a,b,c,d,2))
    def run(*a):return subprocess.check_output(a,text=True,stderr=subprocess.PIPE,timeout=20)
    def flat():
        ps=rows(reader,'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'))
        orders=rows(reader,'/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))
        from decimal import Decimal
        need(not any(Decimal(p['size']) for p in ps) and not orders,'ACCOUNT_NOT_FLAT_NO_ACTIVATION')
    def install(raw):
        tmp=unit.with_name('.kity-batch-personal-20261017.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,unit);fd=os.open(unit.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    try:
        session(policy['base_policy'],time.time_ns()//1000000);read_predecessor(new);flat()
        run('systemctl','stop',new['unit'])
        lease=AccountLease(Path(new['custody_runtime_root'])/'account.lock')
        need(lease.inode==new['account_lock_inode'],'ORIGINAL_ACCOUNT_LOCK_CHANGED');flat()
        need(sha(unit.read_bytes())==m['old_unit_sha256'],'UNIT_RACE')
        install(Path(m['prepared_unit']).read_bytes());changed=True
        run('systemctl','daemon-reload');lease.close();lease=None;run('systemctl','start',new['unit'])
        ready=False
        for _ in range(60):
            h=read(Path(new['custody_runtime_root'])/'heartbeat.json')
            pid=run('systemctl','show',new['unit'],'--value','-p','MainPID').strip()
            if (h.get('pid')==int(pid) and h.get('money_config_enabled') is True
                and h.get('error') is None and h.get('mode')=='ORDERS_OFF'
                and h.get('private_authenticated') is True and h.get('private_subscribed') is True):
                ready=True;break
            time.sleep(.2)
        need(ready,'OWNER_ACTIVATION_NOT_READY');flat();session(policy['base_policy'],time.time_ns()//1000000)
        # Durable uncertainty barrier BEFORE the one possible command queue call.
        publish(root/'go-may-have-been-queued.json',dict(policy_id=m['policy_id'],at_ms=time.time_ns()//1000000))
        output=queue_command(new,m)
        queued=json.loads(output);need(queued['status']=='COMMAND_QUEUED','QUEUE_RESULT_UNKNOWN_NO_RETRY')
        publish(root/'personal-owner-queued-20261017.json',dict(queued,policy_id=m['policy_id']))
        return queued
    except Exception as exc:
        if lease:lease.close();lease=None
        rollback=False
        if changed and rollback_safe(root):
            try:
                flat();run('systemctl','stop',new['unit'])
                lease=AccountLease(Path(new['custody_runtime_root'])/'account.lock')
                flat();install(Path(m['previous_unit']).read_bytes());run('systemctl','daemon-reload')
                lease.close();lease=None;run('systemctl','start',old['unit']);rollback=True
            except Exception:pass
        publish(root/'personal-owner-failure-20261017.json',dict(status='OWNER_LAUNCH_FAILED_NO_BLIND_RETRY',
            reason_type=type(exc).__name__,rolled_back_orders_off=rollback,
            possible_go_or_send=not rollback_safe(root)))
        raise
    finally:
        if lease:lease.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest');p.add_argument('--manifest-sha256')
    p.add_argument('--owner-execute',action='store_true',help='HUMAN ONLY, monetary authority')
    a=p.parse_args(argv)
    if not a.manifest:
        need(not a.owner_execute,'EXACT_OWNER_PACKET_REQUIRED')
        print(json.dumps(dict(status='OWNER_PACKET_OFFLINE_NO_AUTHORITY',broker_writes=0)));return 0
    m,old,new,policy=load(a.manifest,a.manifest_sha256)
    if not a.owner_execute:
        print(json.dumps(dict(status='OWNER_PACKET_INSPECTION_PASS',policy_id=m['policy_id'],
            valid_until_ms=policy['base_policy']['valid_until_ms'],broker_requests=0,broker_writes=0)));return 0
    print(json.dumps(owner_execute(m,old,new,policy)));return 0


if __name__=='__main__':raise SystemExit(main())
