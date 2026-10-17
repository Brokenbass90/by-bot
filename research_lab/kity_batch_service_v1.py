"""Bind batch/WS to ONE original account lease. Default: ORDERS_OFF.

The deployment uses the existing owner unit, inhibitors and health heartbeat.
No automatic policy, GO, entry, replay or strategy authority. Human money
command additionally requires a separately activated pinned money config.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time

from research_lab import kity_batch_ws_v1 as batch
from research_lab import kity_micro_bounded_owner_v2 as bo
from research_lab.kity_micro_physical_owner_v1 import (
    AccountLease,EvidenceReader,load_bound_credentials,platform_verifier,publish,sha,now_ms,rows,
)
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError
from research_lab.kity_micro_low_latency_v1 import ReusableGetWire,cycle_with_sources
from research_lab.kity_micro_post_go_pricing_v1 import make_policy,dispatch_window
from research_lab.kity_micro_supervisor_v1 import sd_notify


def validate_config(c):
    root,custody=Path(c['runtime_root']),Path(c['custody_runtime_root'])
    if (c.get('operation_scope')!='KITY_BATCH_WS_V1' or c.get('default_orders_off') is not True
            or type(c.get('money_go')) is not bool or c.get('entry_dispatch_window_ms')!=60000
            or type(c.get('entry_dispatch_window_ms')) is not int or root.parent!=custody
            or not re.fullmatch(r'batch-ws-[0-9]{8}(?:-v[1-9][0-9]*)?',root.name)
            or any(p.is_symlink() for p in (root,*root.absolute().parents))):
        raise SourceError('BATCH_CONFIG_SCOPE_OR_AUTHORITY')


def validate_control(x):
    allowed={'PREPARE_BATCH':{'kind'},'GO_BATCH':{'kind','batch_policy_id','exact_go','issued_ms'},
             'KILL_BATCH':{'kind','plan_id'}}
    if not isinstance(x,dict) or x.get('kind') not in allowed or set(x)!=allowed[x['kind']]:
        raise SourceError('BATCH_CONTROL_SCOPE')
    if x['kind']=='GO_BATCH':
        if (not isinstance(x['batch_policy_id'],str) or not re.fullmatch(r'[0-9a-f]{64}',x['batch_policy_id'])
                or x['exact_go']!=batch.GO_PREFIX+x['batch_policy_id']
                or type(x['issued_ms']) is not int or x['issued_ms']<=0):
            raise SourceError('NEW_EXACT_BATCH_GO_REQUIRED')
    if x['kind']=='KILL_BATCH' and not re.fullmatch(r'[0-9a-f]{64}',x.get('plan_id','')):
        raise SourceError('BATCH_OWNED_PLAN_REQUIRED')
    return x


class BatchSupervisor:
    fresh=bo.BoundedSupervisor.fresh

    def __init__(self,c):
        validate_config(c)
        self.config=c;self.root=Path(c['runtime_root']);self.custody_root=Path(c['custody_runtime_root'])
        self.lease=AccountLease(self.custody_root/'account.lock')
        if self.lease.inode!=c['account_lock_inode']:raise SourceError('ORIGINAL_ACCOUNT_LOCK_CHANGED')
        self.check=platform_verifier(c);self.check();bo.read_predecessor(c)
        key,secret=load_bound_credentials(c)
        self.reader=EvidenceReader(BybitReadTransport(key,secret,wire=ReusableGetWire()),self.root/'raw')
        self.reader.all_symbol_fee_snapshot=True
        self.writer=batch.BatchSignedPostOnce(key,secret,self.root/'wire')
        self.inbox=batch.PrivateInbox(self.root/'private-inbox')
        self.feed=batch.PrivateFeed(batch.PrivateSession(key,secret),self.inbox)
        self.journal=self.owner=self.runtime=None;self.experiment_root=None;self.last_ping_ms=0
        self.unselected_history()
        selection=self.root/'selected-batch.json'
        if selection.exists():
            selected=json.loads(selection.read_bytes());store=self.store(selected['batch_policy_id'])
            active=store/'active-batch.json'
            if active.exists():
                self.bind(json.loads(active.read_bytes()),create=False)
                if (store/'batch-owner-go.json').exists():
                    self.owner.recover_go()  # durable no-reentry unwind BEFORE socket/network
                elif self.journal.snapshot()['entries'] or any((self.root/'wire').glob('send-*.json')):
                    raise SourceError('BATCH_RECOVERY_GO_MISSING_WITH_SEND_HISTORY')
                else:
                    self.runtime.supervisor.unwind('INTERRUPTED_BEFORE_OWNER_AUTH_NO_RETRY')
                    self.runtime.supervisor.bridge.reconcile_positions()
                    self.journal.append(dict(kind='FINALITY_NO_SEND',at_ms=now_ms(),source_sha256=self.journal.plan['plan_id'],
                        event_id='interrupted-before-owner-auth'))
            elif not (store/'batch-no-send.json').exists():
                if (store/'lifecycle.sqlite').exists():raise SourceError('BATCH_ACTIVE_SOURCE_MISSING')
                publish(store/'batch-no-send.json',dict(status='CONTROL_INTERRUPTED_NOT_RETRIED',at_ms=now_ms()))
        try:self.open_stream()
        except Exception:self.stream_error='PRIVATE_STREAM_UNAVAILABLE_ORDERS_OFF'

    def store(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[0-9a-f]{64}',identifier):
            raise SourceError('BATCH_STORE_IDENTITY')
        return self.root/'experiments'/identifier

    def unselected_history(self):
        if (self.root/'selected-batch.json').exists():return
        if any((self.root/'wire').glob('send-*.json')) or any((self.root/'experiments').glob('**/*')):
            raise SourceError('MISSING_BATCH_SELECTION_WITH_HISTORY')

    def open_stream(self):
        self.feed.open();self.last_ping_ms=now_ms();self.stream_error=None

    def ping_stream(self):
        if self.feed.socket is None:raise SourceError('BATCH_PRIVATE_STREAM_OFFLINE')
        self.feed.send(dict(op='ping'));end=time.monotonic()+3
        while time.monotonic()<end:
            m=self.feed.receive(max(.01,end-time.monotonic()))
            if m.get('op')=='pong' or m.get('ret_msg')=='pong' or (m.get('op')=='ping' and m.get('success') is True):
                self.last_ping_ms=now_ms();return
        raise SourceError('BATCH_PONG_DEADLINE')

    def bind(self,active,*,create):
        p=active['batch_policy'];batch.validate_batch_policy(p)
        d=active['dossier'];base=p['base_policy']
        if (base['physical_config_sha256']!=self.config['_config_sha256']
                or base['predecessor_plan_id']!=self.config['predecessor_plan_id']
                or base['dispatch_window_ms']!=60000):
            raise SourceError('BATCH_PRODUCTION_CUSTODY_CONFLICT')
        store=self.store(p['batch_policy_id']);self.experiment_root=store
        if not create and not (store/'lifecycle.sqlite').is_file():raise SourceError('BATCH_RECOVERY_JOURNAL_MISSING')
        self.journal=batch.BatchJournal(store/'lifecycle.sqlite',d['plan'])
        self.owner=batch.BatchPhysicalOwner(self.journal,self.reader,self.lease,store,
            platform_check=self.check,post=self.writer.post,dossier=d,batch_policy=p,inbox=self.inbox)
        self.runtime=batch.BatchRuntime(self.journal,self.reader,self.owner,self.feed,{i['symbol']:i for i in d['instruments']})
        from research_lab.kity_micro_account_readbacks_v2 import AccountReadBridge,AccountCycleSources
        supervisor=self.runtime.supervisor
        supervisor.bridge=AccountReadBridge(self.journal,self.reader,owner=self.owner)
        original=supervisor.cycle
        supervisor.cycle=lambda:cycle_with_sources(supervisor,original,view_type=AccountCycleSources)

    def control(self,x):
        validate_control(x)
        if x['kind']=='KILL_BATCH':
            if not self.journal or x['plan_id']!=self.journal.plan['plan_id']:raise SourceError('BATCH_OWNED_PLAN_REQUIRED')
            self.unwind('OWNER_KILL');return dict(status='OWNED_UNWIND_REQUESTED')
        # Even a literal personal GO cannot spend a disabled deployment.
        if self.config.get('money_go') is not True:
            if x['kind']!='PREPARE_BATCH':raise SourceError('BATCH_ORDERS_OFF_NO_MONEY_AUTHORITY')
            self.check()
            d,_=self.fresh(self.root/'readiness')
            return dict(status='KITY_BATCH_WS_BOUND_ORDERS_OFF',private_authenticated=self.inbox._auth,
                private_subscribed=self.inbox._sub,gross=d['current_basket_gross_usdt'],
                fresh_only=d['plan']['blocked_reasons'],source_clock=d['common_clock_at_capture']['status'],
                monetary_transport_authorized=False,policy_created=False,actual_intents_created=0,broker_writes=0)
        if (self.root/'selected-batch.json').exists():raise SourceError('ONE_BATCH_EXPERIMENT_ALREADY_SELECTED')
        if (self.root/'rollback-request.json').exists() or (self.custody_root/'rollback-request.json').exists():
            raise SourceError('ROLLBACK_INHIBITS_BATCH')
        self.unselected_history();self.check();bo.read_predecessor(self.config)
        if x['kind']=='PREPARE_BATCH':
            if any((self.root/'policies').glob('*.json')):raise SourceError('ONE_BATCH_POLICY_ALREADY_PREPARED')
            bounds=json.loads((Path(self.config['app_root'])/self.config['bounds_file']).read_bytes())
            p=batch.make_batch_policy(make_policy(created_ms=now_ms(),valid_until_ms=self.config['policy_valid_until_ms'],
                physical_config_sha256=self.config['_config_sha256'],predecessor_plan_id=self.config['predecessor_plan_id'],
                bounds=bounds,dispatch_window_ms=60000))
            publish(self.root/'policies'/(p['batch_policy_id']+'.json'),p)
            return dict(status='BATCH_POLICY_PREPARED',batch_policy=p,broker_writes=0)
        p=json.loads((self.root/'policies'/(x['batch_policy_id']+'.json')).read_bytes());batch.validate_batch_policy(p)
        if p['batch_policy_id']!=x['batch_policy_id'] or p['base_policy']['physical_config_sha256']!=self.config['_config_sha256']:
            raise SourceError('BATCH_PREPARED_POLICY_PIN_CONFLICT')
        dispatch_window(p['base_policy'],x['issued_ms'],now_ms())
        ps=rows(self.reader,'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'))
        orders=rows(self.reader,'/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))
        if any(bo.rt.numeric(v['size'],zero=True)>0 for v in ps) or orders:raise SourceError('BATCH_GO_ACCOUNT_NOT_FLAT')
        publish(self.root/'selected-batch.json',x)
        store=self.store(p['batch_policy_id'])
        d=batch.consume_batch_policy_once(store,p,x['exact_go'],x['issued_ms'],lambda:self.fresh(store),clock=now_ms)
        active=dict(batch_policy=p,dossier=d);publish(store/'active-batch.json',active)
        self.bind(active,create=True)
        self.ping_stream();self.runtime.reconcile_before_go()
        self.owner.accept_batch_go(x['exact_go'])
        return self.runtime.dispatch_once()

    def unwind(self,reason):
        if self.runtime:self.runtime.supervisor.unwind(reason)

    def cycle(self):
        try:
            if self.feed.socket is not None and now_ms()-self.last_ping_ms>=15000:self.ping_stream()
        except Exception:
            self.feed.close()
        if self.runtime:return self.runtime.tick()
        if self.feed.socket is None:return ['PRIVATE_STREAM_OFFLINE_ORDERS_OFF']
        try:self.feed.poll(.1);return []
        except Exception:
            self.feed.close();return ['PRIVATE_STREAM_DISCONNECTED_ORDERS_OFF']

    def heartbeat(self,error=None):
        state=self.journal.snapshot() if self.journal else None
        active=bool(self.owner and self.owner._authorized and not bo.terminal_orders_off(state))
        if isinstance(error,dict):error=error.get('errors')
        publish(self.custody_root/'heartbeat.json',dict(schema='kity_micro_owner_heartbeat_v1',pid=os.getpid(),
            at_ms=now_ms(),mode='EXACT_GO_SCOPED_MANAGEMENT' if active else 'ORDERS_OFF',
            account_lock_inode=self.lease.inode,active_plan_id=state['plan_id'] if state else None,
            phase=state['phase'] if state else 'NO_ACTIVE_PLAN',state=state,error=error or None,
            trading_post_attempts=len(list((self.custody_root/'wire').glob('send-*.json')))+len(list((self.root/'wire').glob('send-*.json'))),
            execution_contract=batch.MODE,private_connected=self.inbox._connected,
            private_authenticated=self.inbox._auth,private_subscribed=self.inbox._sub,
            private_last_receive_ms=self.inbox.last_receive_ms,money_config_enabled=self.config['money_go']),exclusive=False)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--config-sha256')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--serve',action='store_true')
    mode.add_argument('--command');mode.add_argument('--owner-go-batch',help='HUMAN ONLY: one exact new batch policy')
    a=p.parse_args(argv)
    if not (a.serve or a.command or a.owner_go_batch):
        print(json.dumps(dict(status='KITY_BATCH_PREPARATION_ONLY_NO_NETWORK',broker_writes=0)));return 0
    raw=Path(a.config).read_bytes()
    if sha(raw)!=a.config_sha256:raise SourceError('BATCH_CONFIG_PIN_CONFLICT')
    c=json.loads(raw);c.update(_config_path=a.config,_config_sha256=a.config_sha256)
    if a.command or a.owner_go_batch:
        if a.command:
            x=json.loads(a.command)
            if x.get('kind')!='PREPARE_BATCH':raise SourceError('MONETARY_CONTROL_REQUIRES_PERSONAL_OWNER_COMMAND')
        else:x=dict(kind='GO_BATCH',batch_policy_id=a.owner_go_batch,exact_go=batch.GO_PREFIX+a.owner_go_batch,issued_ms=now_ms())
        validate_control(x);identifier=str(time.time_ns())
        publish(Path(c['runtime_root'])/'commands'/(identifier+'.json'),x)
        print(json.dumps(dict(status='COMMAND_QUEUED',command_id=identifier)));return 0
    s=BatchSupervisor(c);s.heartbeat();sd_notify('READY=1')
    while True:
        sd_notify('WATCHDOG=1')
        for path in sorted((s.root/'commands').glob('*.json')):
            done=s.root/'results'/path.name
            if done.exists():continue
            claim=s.root/'claims'/path.name
            if claim.exists():publish(done,dict(status='CONTROL_INTERRUPTED_NOT_RETRIED'));continue
            publish(claim,dict(command_sha256=sha(path.read_bytes()),at_ms=now_ms()))
            try:result=s.control(json.loads(path.read_bytes()))
            except Exception as exc:result=dict(status='CONTROL_BLOCKED',reason=str(exc)[:1000],orders_allowed=False)
            publish(done,result)
        try:
            if not s.journal:s.check()
            error=s.cycle()
        except Exception as exc:
            s.unwind('BATCH_SUPERVISOR_FAILURE');error=type(exc).__name__
        s.heartbeat(error);sd_notify('WATCHDOG=1');time.sleep(1 if s.journal else 3)


if __name__=='__main__':main()
