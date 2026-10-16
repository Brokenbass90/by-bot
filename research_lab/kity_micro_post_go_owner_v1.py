"""One price-free policy on the original physical account writer.

Agents may prepare/rehearse orders-OFF. Only the human personally invokes
--owner-go-policy. Never import an old intent approval as policy authority.
"""
import argparse
import json
import os
from pathlib import Path
import time

from research_lab import kity_micro_bounded_owner_v2 as bo
from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
from research_lab.kity_micro_physical_owner_v1 import (
    AccountLease, PhysicalOwner, EvidenceReader, SignedPostOnce,
    load_bound_credentials, platform_verifier, publish, sha, now_ms,
)
from research_lab.kity_micro_post_go_pricing_v1 import (
    make_policy, validate_policy, consume_policy_once, verify_compilation,
    dispatch_window, GO_PREFIX,
)
from research_lab.kity_micro_supervisor_v1 import recover_without_reentry, sd_notify
from research_lab.kity_micro_transport_v1 import BybitReadTransport, SourceError, wire_get

CLOSEOUT_SCOPES={
    'ONE_CLOSEOUT_MICRO_2026_10_16':'post-go-closeout-20261016',
    'ONE_CLOSEOUT2_MICRO_2026_10_16':'post-go-closeout2-20261016',
}

def check_history(root, custody, config):
    for name,pin in config.get('prior_no_send_files', {}).items():
        p=Path(name)
        if p.is_symlink() or not p.is_file() or sha(p.read_bytes())!=pin:
            raise SourceError('PRIOR_NO_SEND_SOURCE_DRIFT')
    if (root/'selected-v2.json').exists():
        return
    if (any(str(p) not in config['wire_baseline_files'] for p in (custody/'wire').glob('send-*.json'))
            or any(p.is_file() for p in (root/'experiments-v2').glob('**/*'))):
        raise SourceError('MISSING_SELECTED_STATE_WITH_HISTORY')


class PostGoOwner(bo.BoundedOwner):
    def __init__(self,*args,dossier,wire_root,**kwargs):
        PhysicalOwner.__init__(self,*args,**kwargs)
        self.dossier=dossier; self.policy=dossier['post_go_policy']
        self.intent=dossier['pricing_intent']; self.wire_root=Path(wire_root)
        verify_compilation(dossier)
        self.verify_claim()
        transport=self.post
        def final_transport(path,request):
            if path=='/v5/order/create' and request.get('reduceOnly') is False:
                try:self.entry_fence()
                except SourceError:
                    self.mark_no_wire(request)
                    raise
            return transport(path,request)
        self.post=final_transport

    def verify_claim(self):
        c=json.loads((self.store/'policy-claim.json').read_bytes())
        if (c.get('policy_id')!=self.policy['policy_id']
                or c.get('owner_go_text')!=GO_PREFIX+self.policy['policy_id']
                or c.get('go_ms')!=self.dossier['post_go_go_ms']):
            raise SourceError('LITERAL_POLICY_CLAIM_CONFLICT')

    def accept_intent_go(self,text):
        raise SourceError('EXACT_POLICY_GO_REQUIRED_NOT_DERIVED_INTENT_GO')

    def accept_policy_go(self,text):
        if text!=GO_PREFIX+self.policy['policy_id']:
            raise SourceError('EXACT_POLICY_GO_REQUIRED')
        self.assert_exclusive(self.journal.plan); self.verify_claim(); self.entry_fence()
        if self.journal.snapshot()['entries']:
            raise SourceError('GO_ALREADY_CONSUMED')
        publish(self.store/'owner-go.json',dict(schema='KITY_POST_GO_POLICY_AUTH_V1',
            owner_go_text=text, policy_id=self.policy['policy_id'],
            plan_id=self.journal.plan['plan_id'], go_ms=self.dossier['post_go_go_ms'],
            at_ms=self.clock()))
        self._authorized=True

    def recover_go(self):
        self.verify_claim(); go=json.loads((self.store/'owner-go.json').read_bytes())
        if (go.get('schema')!='KITY_POST_GO_POLICY_AUTH_V1'
                or go.get('plan_id')!=self.journal.plan['plan_id']
                or go.get('policy_id')!=self.policy['policy_id']
                or go.get('go_ms')!=self.dossier['post_go_go_ms']
                or go.get('owner_go_text')!=GO_PREFIX+self.policy['policy_id']):
            raise SourceError('POLICY_GO_RECOVERY_CONFLICT')
        self.assert_exclusive(self.journal.plan)
        self._authorized=True  # constructor immediately persists no-reentry unwind

    def entry_fence(self):
        dispatch_window(self.policy,self.dossier['post_go_go_ms'],self.clock())
        if (self.store/'rollback-request.json').exists() or (self.lease.path.parent/'rollback-request.json').exists():
            raise SourceError('ROLLBACK_INHIBITS_ENTRY')

    def validate_preflight(self,plan,request,role):
        if role!='ENTRY' or not getattr(self,'parallel_entry_preflight',False):
            return super().validate_preflight(plan,request,role)
        from research_lab.kity_micro_low_latency_v1 import ParallelPreflightGets
        self.entry_fence(); original=self.reader
        self.reader=ParallelPreflightGets(original,request['symbol'],
            getattr(self,'require_account_instruments',False))
        try:return super().validate_preflight(plan,request,role)
        finally:self.reader=original


def validate_control(x):
    allowed={'PREPARE_POST_GO':{'kind'}, 'REHEARSE_POST_GO':{'kind','policy_id'},
        'GO_POST_GO':{'kind','policy_id','exact_go','issued_ms'}, 'KILL':{'kind','plan_id'}}
    if not isinstance(x,dict) or x.get('kind') not in allowed or set(x)!=allowed[x['kind']]:
        raise SourceError('POST_GO_CONTROL_SCOPE')
    if x['kind']!='PREPARE_POST_GO':
        key='plan_id' if x['kind']=='KILL' else 'policy_id'
        if not isinstance(x[key],str) or not bo.SHA.fullmatch(x[key]):
            raise SourceError('POST_GO_CONTROL_ID')
    if x['kind']=='GO_POST_GO':
        if x['exact_go']!=GO_PREFIX+x['policy_id']:
            raise SourceError('EXACT_POLICY_GO_REQUIRED')
        if type(x['issued_ms']) is not int or x['issued_ms']<=0:
            raise SourceError('POST_GO_CONTROL_CLOCK')
    return x


def entry_window(config):
    """The owner's single 70s amendment belongs only to the new namespace."""
    closeout=config.get('operation_scope') in CLOSEOUT_SCOPES
    window=config.get('entry_dispatch_window_ms',60000)
    if (type(window) is not int or window!=(70000 if closeout else 60000)
            or closeout and config.get('critical_path_profile')!='ACCOUNT_READBACK_V2'):
        raise SourceError('ENTRY_WINDOW_SCOPE_CONFLICT')
    return window


class PostGoSupervisor(bo.BoundedSupervisor):
    def cycle(self):
        profile=self.config.get('critical_path_profile')
        if profile not in ('POOL_PARALLEL_V1','ACCOUNT_READBACK_V2'):return super().cycle()
        from research_lab.kity_micro_low_latency_v1 import cycle_with_sources
        if profile=='ACCOUNT_READBACK_V2':
            from research_lab.kity_micro_account_readbacks_v2 import AccountCycleSources
            return cycle_with_sources(self,super().cycle,view_type=AccountCycleSources)
        return cycle_with_sources(self,super().cycle)

    def __init__(self,config):
        self.config=config; self.root=Path(config['runtime_root'])
        entry_window(config)
        self.custody_root=Path(config['custody_runtime_root'])
        allowed={'ONE_POST_GO_MICRO_2026_10_16':'post-go-20261016',
            'ONE_LATENCY_MICRO_2026_10_16':'post-go-fast-20261016',
            **CLOSEOUT_SCOPES}
        if (self.root.parent!=self.custody_root
                or self.root.name!=allowed.get(config.get('operation_scope'))
                or not (self.custody_root/'account.lock').is_file()
                or not config.get('prior_no_send_files')):
            raise SourceError('POST_GO_RUNTIME_CUSTODY_SCOPE')
        if any(p.is_symlink() for p in (self.root,*self.root.parents,self.custody_root)):
            raise SourceError('RUNTIME_CUSTODY_SYMLINK')
        check_history(self.root,self.custody_root,config)
        self.lease=AccountLease(self.custody_root/'account.lock')
        if self.lease.inode!=config['account_lock_inode']:
            raise SourceError('ORIGINAL_LOCK_INODE_CONFLICT')
        self.previous=bo.read_predecessor(config)
        key,secret=load_bound_credentials(config); self.check=platform_verifier(config)
        profile=config.get('critical_path_profile')
        if profile not in (None,'POOL_PARALLEL_V1','ACCOUNT_READBACK_V2'):raise SourceError('CRITICAL_PATH_PROFILE_UNKNOWN')
        if profile in ('POOL_PARALLEL_V1','ACCOUNT_READBACK_V2'):
            from research_lab.kity_micro_low_latency_v1 import ReusableGetWire
            wire=ReusableGetWire()
        else:wire=lambda m,u,h,d,t:wire_get(m,u,h,d,2)
        self.reader=EvidenceReader(BybitReadTransport(key,secret,wire=wire),self.custody_root/'raw')
        self.reader.all_symbol_fee_snapshot=profile in ('POOL_PARALLEL_V1','ACCOUNT_READBACK_V2')
        self.writer=SignedPostOnce(key,secret,self.custody_root/'wire')
        self.journal=None; self.owner=None; self.spec=None; self.experiment_root=None
        selection=self.root/'selected-v2.json'
        if selection.exists():
            selected=json.loads(selection.read_bytes())
            self.experiment_root=bo.selected_store(self.root,selected)
            active=self.experiment_root/'active-plan.json'
            if active.exists():
                self.bind(json.loads(active.read_bytes()))
                if (self.experiment_root/'owner-go.json').exists():self.owner.recover_go()
                self.owner.recover_no_wire(); self.recover_saved_terms_rejections()
                recover_without_reentry(self.journal,now_ms())
            elif not (self.experiment_root/'no-send.json').exists():
                publish(self.experiment_root/'no-send.json',dict(status='CONTROL_INTERRUPTED_NOT_RETRIED',
                    policy_id=selected['intent_id'],observed_ms=now_ms(),broker_writes=0))

    def before_selection(self):
        if (self.root/'rollback-request.json').exists():raise SourceError('CONTROL_CLOSED_FOR_ROLLBACK')
        if (self.root/'selected-v2.json').exists():raise SourceError('ONE_POST_GO_EXPERIMENT_ALREADY_SELECTED')
        check_history(self.root,self.custody_root,self.config)
        bo.read_predecessor(self.config); self.check()

    def bind(self,dossier,*,create=False):
        policy=dossier['post_go_policy']; validate_policy(policy)
        store=self.experiment_root
        if (store!=bo.selected_store(self.root,{'intent_id':policy['policy_id']})
                or policy['physical_config_sha256']!=self.config['_config_sha256']
                or policy['predecessor_plan_id']!=self.config['predecessor_plan_id']
                or policy['dispatch_window_ms']!=entry_window(self.config)):
            raise SourceError('POST_GO_SELECTED_BINDING_CONFLICT')
        if not create and not (store/'lifecycle.sqlite').is_file():raise SourceError('RECOVERY_JOURNAL_MISSING')
        self.spec={i['symbol']:i for i in dossier['instruments']}; self.dossier=dossier
        self.journal=bo.JournalV2(store/'lifecycle.sqlite',dossier['plan'])
        self.owner=PostGoOwner(self.journal,self.reader,self.lease,store,platform_check=self.check,
            post=self.writer.post,dossier=dossier,wire_root=self.custody_root/'wire')
        self.owner.require_account_instruments=self.config.get('require_account_instruments') is True
        self.owner.parallel_entry_preflight=self.config.get('critical_path_profile') in ('POOL_PARALLEL_V1','ACCOUNT_READBACK_V2')
        bridge=MicroAccountBridge
        if self.config.get('critical_path_profile')=='POOL_PARALLEL_V1':
            from research_lab.kity_micro_low_latency_v1 import ParallelReadBridge
            bridge=ParallelReadBridge
        elif self.config.get('critical_path_profile')=='ACCOUNT_READBACK_V2':
            from research_lab.kity_micro_account_readbacks_v2 import AccountReadBridge
            bridge=AccountReadBridge
        self.bridge=bridge(self.journal,self.reader,owner=self.owner)

    def control(self,x):
        validate_control(x); kind=x['kind']
        if kind=='KILL':
            if not self.journal or self.journal.plan['plan_id']!=x['plan_id']:
                raise SourceError('ACTIVE_PLAN_REQUIRED')
            self.unwind('OWNER_KILL'); return dict(status='OWNED_UNWIND_REQUESTED')
        self.before_selection()
        if kind=='PREPARE_POST_GO':
            if (self.config.get('operation_scope') in CLOSEOUT_SCOPES
                    and any((self.root/'policies').glob('*.json'))):
                raise SourceError('ONE_CLOSEOUT_POLICY_ALREADY_PREPARED')
            bounds=json.loads((Path(self.config['app_root'])/self.config['bounds_file']).read_bytes())
            p=make_policy(created_ms=now_ms(),valid_until_ms=self.config['policy_valid_until_ms'],
                physical_config_sha256=self.config['_config_sha256'],
                predecessor_plan_id=self.config['predecessor_plan_id'],bounds=bounds,
                dispatch_window_ms=entry_window(self.config))
            publish(self.root/'policies'/(p['policy_id']+'.json'),p)
            return dict(status='POST_GO_POLICY_PREPARED_ORDERS_OFF',policy=p,
                owner_go_text=GO_PREFIX+p['policy_id'],broker_writes=0)
        p=json.loads((self.root/'policies'/(x['policy_id']+'.json')).read_bytes()); validate_policy(p)
        if (p['policy_id']!=x['policy_id'] or p['physical_config_sha256']!=self.config['_config_sha256']
                or p['dispatch_window_ms']!=entry_window(self.config)):
            raise SourceError('EXACT_PREPARED_POLICY_REQUIRED')
        if kind=='REHEARSE_POST_GO':
            # Pre-GO source validation only: no claim, selection, journal or
            # owner authority. Real order transport is not instantiated here.
            go_ms=now_ms(); fresh,caps=self.fresh(self.root/'rehearsals')
            from research_lab.kity_micro_post_go_pricing_v1 import compile_after_go
            out=compile_after_go(p,fresh,caps,go_ms=go_ms,now_ms=now_ms())
            verify_compilation(out)
            return dict(status='POST_GO_SAVED_SOURCE_REHEARSAL_PASS',policy_id=p['policy_id'],
                gross=out['current_basket_gross_usdt'],plan_id=out['plan']['plan_id'],
                broker_writes=0,actual_journal_created=False,owner_authority=False)
        dispatch_window(p,x['issued_ms'],now_ms())
        publish(self.root/'selected-v2.json',dict(intent_id=p['policy_id'],
            owner_go_text=x['exact_go'],at_ms=now_ms(),issued_ms=x['issued_ms']))
        self.experiment_root=bo.selected_store(self.root,{'intent_id':p['policy_id']})
        out=consume_policy_once(self.experiment_root,p,x['exact_go'],x['issued_ms'],
            lambda:self.fresh(self.experiment_root),clock=now_ms)
        publish(self.experiment_root/'active-plan.json',out); self.bind(out,create=True)
        self.owner.accept_policy_go(x['exact_go'])
        return dict(status='POST_GO_POLICY_BOUND_ONE_EXPERIMENT',policy_id=p['policy_id'],
            plan_id=out['plan']['plan_id'],gross=out['current_basket_gross_usdt'],
            entry_dispatch_deadline_ms=x['issued_ms']+p['dispatch_window_ms'])


def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--config'); ap.add_argument('--config-sha256')
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--serve',action='store_true'); mode.add_argument('--command')
    mode.add_argument('--owner-go-policy',help='HUMAN ONLY: personally authorize one real monetary experiment')
    a=ap.parse_args(argv)
    if not (a.serve or a.command or a.owner_go_policy):
        print(json.dumps(dict(status='OWNER_PREPARATION_ONLY_NO_NETWORK',broker_writes=0))); return 0
    if not a.config or not a.config_sha256:raise SourceError('CONFIG_REQUIRED')
    raw=Path(a.config).read_bytes()
    if sha(raw)!=a.config_sha256:raise SourceError('CONFIG_PIN_CONFLICT')
    c=json.loads(raw); c.update(_config_path=a.config,_config_sha256=a.config_sha256)
    root=Path(c['runtime_root'])
    if a.command or a.owner_go_policy:
        if a.owner_go_policy:
            x=dict(kind='GO_POST_GO',policy_id=a.owner_go_policy,
                exact_go=GO_PREFIX+a.owner_go_policy,issued_ms=now_ms())
        else:
            x=json.loads(a.command)
            if x.get('kind') not in ('PREPARE_POST_GO','REHEARSE_POST_GO'):
                raise SourceError('MONETARY_CONTROL_REQUIRES_PERSONAL_OWNER_COMMAND')
        validate_control(x); identifier=str(time.time_ns())
        publish(root/'commands'/(identifier+'.json'),x)
        print(json.dumps(dict(status='COMMAND_QUEUED',command_id=identifier))); return 0
    s=PostGoSupervisor(c); s.check(); s.heartbeat(); sd_notify('READY=1')
    while True:
        sd_notify('WATCHDOG=1')
        for path in sorted((root/'commands').glob('*.json')):
            done=root/'results'/path.name
            if done.exists():continue
            claim=root/'claims'/path.name
            if claim.exists():
                publish(done,dict(status='CONTROL_INTERRUPTED_NOT_RETRIED',orders_allowed=False)); continue
            publish(claim,dict(command_sha256=sha(path.read_bytes()),at_ms=now_ms()))
            try:result=s.control(json.loads(path.read_bytes()))
            except Exception as exc:result=dict(status='CONTROL_BLOCKED',reason=str(exc)[:2000],orders_allowed=False)
            publish(done,result)
        before=s.journal.snapshot() if s.journal else None
        try:
            if not s.journal:s.check()
            error=s.cycle()
        except Exception as exc:
            error=type(exc).__name__+':'+str(exc)[:1024]; s.unwind('SUPERVISOR_FAILURE:'+type(exc).__name__)
        s.heartbeat(error); sd_notify('WATCHDOG=1')
        after=s.journal.snapshot() if s.journal else None
        delay=1
        if c.get('critical_path_profile') in ('POOL_PARALLEL_V1','ACCOUNT_READBACK_V2'):
            from research_lab.kity_micro_low_latency_v1 import cycle_delay
            delay=cycle_delay(before,after)
        time.sleep(delay if after and after['phase']!='TERMINAL' else 3)


if __name__=='__main__':main()
