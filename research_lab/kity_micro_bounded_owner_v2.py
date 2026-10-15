"""Versioned bounded intent on the existing physical owner/lock/POST barriers.

V1's spent files are read-only. One additional, separately approved experiment
lives in experiments-v2/<intent_id>. No literal plan GO is fabricated from the
human intent GO. The existing bridge receives its internal exact-plan token
only after the physical owner validates that independent bounded permission.
"""
import argparse,copy,hashlib,json,re,sqlite3,time,tempfile
from pathlib import Path

from bot.kity_m3_orders_off import digest
from research_lab import kity_execution_micro_runtime_v1 as rt
from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
from research_lab.kity_micro_physical_owner_v1 import (
    PhysicalOwner,AccountLease,SignedPostOnce,EvidenceReader,platform_verifier,
    load_bound_credentials,publish,sha,now_ms,capture_account,
    rows,
)
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError,wire_get
from research_lab.kity_micro_supervisor_v1 import Supervisor,sd_notify,recover_without_reentry
from research_lab.kity_micro_pricing_intent_v2 import (
    make_intent,validate_intent,materialize,consume_once,load_source,_window,
)

SHA=re.compile(r'[0-9a-f]{64}\Z')


def read_state(path,plan,journal_class=rt.MicroJournal):
    """Replay an existing journal without DDL/BEGIN IMMEDIATE or a create path."""
    rt.validate_plan(plan)
    path=Path(path)
    if not path.is_file() or any(p.is_symlink() for p in (path,*path.absolute().parents)):
        raise SourceError('READONLY_JOURNAL_MISSING_OR_SYMLINK')
    j=journal_class.__new__(journal_class);j.plan=copy.deepcopy(plan);j._cache=None
    j.db=sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True,isolation_level=None)
    try:
        if j.db.execute('PRAGMA application_id').fetchone()[0]!=0x4B584D31:raise SourceError('JOURNAL_IDENTITY_CONFLICT')
        return j.snapshot()
    finally:j.db.close()


def read_predecessor(config):
    for name,pin in config['predecessor_files'].items():
        p=Path(name)
        if not p.is_file() or any(x.is_symlink() for x in (p,*p.absolute().parents)) or sha(p.read_bytes())!=pin:
            raise SourceError('PREDECESSOR_SOURCE_DRIFT')
    root=Path(config['runtime_root']);d=json.loads((root/'active-plan.json').read_bytes())
    rt.validate_plan(d['plan'])
    if d['plan']['plan_id']!=config['predecessor_plan_id']:raise SourceError('PREDECESSOR_PLAN_CONFLICT')
    s=read_state(root/'lifecycle.sqlite',d['plan'])
    if (s['phase']!='TERMINAL' or s.get('execution_verdict')!='NO_SEND_NOT_LIFECYCLE_PASS'
        or s['entries'] or s['exits'] or s['fills'] or s['first_send_ms'] is not None
        or s['broker_flat_proven'] is not True):raise SourceError('PREDECESSOR_NOT_EXACT_NO_SEND')
    return s


def selected_store(root,selection):
    identifier=selection.get('intent_id')
    if not isinstance(identifier,str) or not SHA.fullmatch(identifier):raise SourceError('SELECTED_INTENT_ID')
    p=Path(root)/'experiments-v2'/identifier
    if any(x.is_symlink() for x in (p,*p.absolute().parents)):raise SourceError('SELECTED_STORE_SYMLINK')
    return p


def bound_config_pin(config,dossier,store,*,create=False):
    """A new source kit may recover only the exact existing old-config journal.

    This does not transfer GO to a proposal: PREPARE/selection are disabled for
    recovery-only configs, and neither the intent nor dossier is rewritten.
    """
    recovery=config.get('recovery_binding')
    if recovery is None:return config['_config_sha256']
    if (create or recovery.get('mode')!='OWNED_RECOVERY_ONLY'
        or recovery.get('intent_id')!=dossier['pricing_intent']['intent_id']
        or not (store/'lifecycle.sqlite').is_file()
        or sha((store/'active-plan.json').read_bytes())!=recovery.get('active_plan_sha256')):
        raise SourceError('RECOVERY_ONLY_BINDING_CONFLICT')
    original=Path(recovery['original_config_path'])
    if (original.is_symlink() or not original.is_file()
        or sha(original.read_bytes())!=recovery.get('original_config_sha256')):
        raise SourceError('RECOVERY_ORIGINAL_CONFIG_DRIFT')
    old=json.loads(original.read_bytes())
    for key in ('runtime_root','account_lock_inode','account_fingerprint','credential_source',
                'credential_source_sha256','predecessor_files','predecessor_plan_id','inhibitors','inhibit_marker','unit'):
        if old.get(key)!=config.get(key):raise SourceError('RECOVERY_ORIGINAL_CUSTODY_CONFLICT:'+key)
    return recovery['original_config_sha256']


def apply_v2(plan,state,event):
    if event['kind']!='LOCAL_NOT_SENT':return rt.apply_event(plan,state,event)
    # Validate common event/time/phase/ownership through the unchanged reducer.
    s=rt.apply_event(plan,state,dict(event,kind='UNWIND',reason='LOCAL_NOT_SENT'))
    o=s['entries'].get(event.get('symbol'))
    if (not o or o['link']!=event.get('order_link_id') or o['order_id'] is not None
        or rt.numeric(o['filled'],zero=True)!=0 or o['terminal']
        or not SHA.fullmatch(event.get('no_wire_proof_sha256',''))):raise SourceError('LOCAL_NO_WIRE_PROOF_CONFLICT')
    o.update(terminal=True,terminal_quantity='0',local_not_sent=True)
    return s


class JournalV2(rt.MicroJournal):
    event_reducer=staticmethod(apply_v2)


def verify_materialization(dossier):
    i=dossier['pricing_intent'];validate_intent(i)
    p=dossier['plan'];rt.validate_plan(p)
    fresh,caps=load_source(dossier['materialization_capture_path'],p['captured_source_sha256'],
        p['bounds'],i['physical_config_sha256'])
    expected=materialize(i,fresh,caps,now_ms=p['pricing_intent']['materialized_ms'])
    if expected['plan']!=p:raise SourceError('DERIVED_PLAN_REPLAY_CONFLICT')


class BoundedOwner(PhysicalOwner):
    def __init__(self,*args,dossier,wire_root,**kwargs):
        super().__init__(*args,**kwargs)
        self.dossier=dossier;self.intent=dossier['pricing_intent'];self.wire_root=Path(wire_root)
        transport=self.post
        def final_transport(path,request):
            # Parent post_once performs its custody check after our outer
            # check. Recheck at the final call boundary, before the one-use
            # SignedPostOnce barrier/signature/wire path, with no slow GET/CAS
            # between this fence and that transport invocation.
            if path=='/v5/order/create' and request.get('reduceOnly') is False:
                try:self.entry_fence()
                except SourceError:
                    self.mark_no_wire(request)
                    raise
            return transport(path,request)
        self.post=final_transport
        verify_materialization(dossier)
        c=json.loads((self.store/'intent-claim.json').read_bytes())
        if (c['intent_id']!=self.intent['intent_id']
            or c['owner_go_text']!='GO KITY_EXECUTION_MICRO_INTENT_V2 '+self.intent['intent_id']):
            raise SourceError('LITERAL_INTENT_CLAIM_CONFLICT')
    def accept_go(self,text):raise SourceError('EXACT_INTENT_GO_REQUIRED_NOT_PLAN_GO')
    def accept_intent_go(self,text):
        if text!='GO KITY_EXECUTION_MICRO_INTENT_V2 '+self.intent['intent_id']:raise SourceError('EXACT_INTENT_GO_REQUIRED')
        self.assert_exclusive(self.journal.plan);_window(self.intent,self.clock())
        if self.journal.snapshot()['entries']:raise SourceError('GO_ALREADY_CONSUMED')
        publish(self.store/'owner-go.json',dict(schema='KITY_BOUND_INTENT_GO_V2',
            owner_go_text=text,intent_id=self.intent['intent_id'],plan_id=self.journal.plan['plan_id'],at_ms=self.clock()))
        self._authorized=True
    def recover_go(self):
        go=json.loads((self.store/'owner-go.json').read_bytes())
        if (go.get('schema')!='KITY_BOUND_INTENT_GO_V2' or go.get('plan_id')!=self.journal.plan['plan_id']
            or go.get('intent_id')!=self.intent['intent_id']
            or go.get('owner_go_text')!='GO KITY_EXECUTION_MICRO_INTENT_V2 '+self.intent['intent_id']):
            raise SourceError('INTENT_GO_RECOVERY_CONFLICT')
        self.assert_exclusive(self.journal.plan);self._authorized=True
    def entry_fence(self):
        _window(self.intent,self.clock())
        if (self.store/'rollback-request.json').exists() or (self.lease.path.parent/'rollback-request.json').exists():
            raise SourceError('ROLLBACK_INHIBITS_ENTRY')
    def validate_preflight(self,plan,request,role):
        if role=='ENTRY':self.entry_fence()
        super().validate_preflight(plan,request,role)
        if role=='ENTRY':self.entry_fence()
    def mark_no_wire(self,req):
        pin=digest(dict(path='/v5/order/create',request=req))
        if (self.wire_root/('send-'+pin+'.json')).exists():return False
        row=self.journal.snapshot()['entries'].get(req['symbol'])
        if not row or row['terminal'] or row['order_id'] is not None or rt.numeric(row['filled'],zero=True):return False
        proof=self.wire_root/('not-sent-'+pin+'.json')
        if not proof.exists():publish(proof,dict(status='LOCAL_NOT_SENT_NO_SEND_BARRIER',request_sha256=digest(req),at_ms=self.clock()))
        data=json.loads(proof.read_bytes())
        if data.get('status')!='LOCAL_NOT_SENT_NO_SEND_BARRIER' or data.get('request_sha256')!=digest(req):
            raise SourceError('NO_WIRE_PROOF_CONFLICT')
        self.journal.append(dict(kind='LOCAL_NOT_SENT',symbol=req['symbol'],order_link_id=req['orderLinkId'],
            event_id='local-not-sent-'+req['orderLinkId'],at_ms=data['at_ms'],
            source_sha256=sha(proof.read_bytes()),no_wire_proof_sha256=sha(proof.read_bytes())))
        return True
    def recover_no_wire(self):
        for leg in self.journal.plan['legs']:self.mark_no_wire(leg['request'])
    def post_once(self,path,request):
        if path=='/v5/order/create' and request.get('reduceOnly') is False:
            try:self.entry_fence()
            except SourceError:
                self.mark_no_wire(request)
                raise
        return super().post_once(path,request)


def validate_control(x):
    allowed={'PREPARE_BOUNDED':{'kind'},'REHEARSE_BOUNDED':{'kind','intent_id'},
        'GO_BOUNDED':{'kind','intent_id','exact_go'},'KILL':{'kind','plan_id'}}
    if not isinstance(x,dict) or x.get('kind') not in allowed or set(x)!=allowed[x['kind']]:raise SourceError('BOUNDED_CONTROL_SCOPE')
    if x['kind']!='PREPARE_BOUNDED':
        key='plan_id' if x['kind']=='KILL' else 'intent_id'
        if not isinstance(x[key],str) or not SHA.fullmatch(x[key]):raise SourceError('BOUNDED_CONTROL_ID')
    if x['kind']=='GO_BOUNDED' and x['exact_go']!='GO KITY_EXECUTION_MICRO_INTENT_V2 '+x['intent_id']:
        raise SourceError('EXACT_INTENT_GO_REQUIRED')
    return x


class BoundedSupervisor(Supervisor):
    def __init__(self,config):
        self.config=config;self.root=Path(config['runtime_root'])
        self.lease=AccountLease(self.root/'account.lock')
        if self.lease.inode!=config['account_lock_inode']:raise SourceError('ORIGINAL_LOCK_INODE_CONFLICT')
        self.previous=read_predecessor(config);key,secret=load_bound_credentials(config)
        self.check=platform_verifier(config)
        wire=lambda method,url,headers,data,timeout:wire_get(method,url,headers,data,2)
        self.reader=EvidenceReader(BybitReadTransport(key,secret,wire=wire),self.root/'raw')
        self.writer=SignedPostOnce(key,secret,self.root/'wire')
        self.journal=None;self.owner=None;self.spec=None;self.experiment_root=None
        selection=self.root/'selected-v2.json'
        if selection.exists():
            selected=json.loads(selection.read_bytes());self.experiment_root=selected_store(self.root,selected)
            if (self.experiment_root/'active-plan.json').exists():
                self.bind(json.loads((self.experiment_root/'active-plan.json').read_bytes()))
                if (self.experiment_root/'owner-go.json').exists():self.owner.recover_go()
                self.owner.recover_no_wire();self.recover_saved_terms_rejections()
                recover_without_reentry(self.journal,now_ms())
            elif not (self.experiment_root/'no-send.json').exists():
                publish(self.experiment_root/'no-send.json',dict(status='CONTROL_INTERRUPTED_NOT_RETRIED',
                    intent_id=selected['intent_id'],observed_ms=now_ms(),broker_writes=0))
    def bind(self,dossier,*,create=False):
        store=self.experiment_root
        if store is None:raise SourceError('SEPARATE_EXPERIMENT_STORE_REQUIRED')
        i=dossier['pricing_intent']
        if (store!=selected_store(self.root,i) or i['physical_config_sha256']!=bound_config_pin(self.config,dossier,store,create=create)
            or i['predecessor_plan_id']!=self.config['predecessor_plan_id']):raise SourceError('SELECTED_BINDING_CONFLICT')
        if not create and not (store/'lifecycle.sqlite').is_file():raise SourceError('RECOVERY_JOURNAL_MISSING')
        self.spec={i['symbol']:i for i in dossier['instruments']};self.dossier=dossier
        self.journal=JournalV2(store/'lifecycle.sqlite',dossier['plan'])
        self.owner=BoundedOwner(self.journal,self.reader,self.lease,store,platform_check=self.check,
            post=self.writer.post,dossier=dossier,wire_root=self.root/'wire')
        self.bridge=MicroAccountBridge(self.journal,self.reader,owner=self.owner)
    def recover_saved_terms_rejections(self):
        """Resolve a saved, definite POST refusal; empty GETs alone prove nothing."""
        state=self.journal.snapshot()
        for symbol,order in state['entries'].items():
            if order['terminal'] or order['order_id'] is not None or rt.numeric(order['filled'],zero=True):continue
            request=next(l['request'] for l in self.journal.plan['legs'] if l['symbol']==symbol)
            key=digest(dict(path='/v5/order/create',request=request))
            send=self.root/'wire'/('send-'+key+'.json');response=self.root/'wire'/('response-'+key+'.json')
            if not send.is_file() or not response.is_file():continue
            if send.is_symlink() or response.is_symlink():raise SourceError('REJECTION_WIRE_SYMLINK')
            sent=json.loads(send.read_bytes());cap=json.loads(response.read_bytes())
            if sent.get('path')!='/v5/order/create' or sent.get('request')!=request:
                raise SourceError('REJECTION_WIRE_REQUEST_CONFLICT')
            raw=cap.get('raw')
            if not isinstance(raw,str) or sha(raw.encode())!=cap.get('raw_sha256'):
                raise SourceError('REJECTION_RESPONSE_HASH')
            body=json.loads(raw)
            if (cap.get('http_status')!=200 or type(body.get('retCode')) is not int
                or body['retCode'] not in (110123,110125)):continue
            if not isinstance(body.get('result'),dict) or body['result'].get('orderId'):
                raise SourceError('REJECTION_ACK_CONFLICT')
            params=dict(category='linear',symbol=symbol,orderLinkId=order['link'])
            for path,limit in (('/v5/order/realtime','50'),('/v5/order/history','50'),('/v5/execution/list','100')):
                if rows(self.reader,path,dict(params,limit=limit)):raise SourceError('REJECTION_READBACK_CONFLICT')
            positions=rows(self.reader,'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'))
            if any(rt.numeric(p['size'],zero=True) for p in positions if p.get('symbol')==symbol):
                raise SourceError('REJECTION_READBACK_CONFLICT')
            self.journal.append(dict(kind='DISPATCH_REJECTED',symbol=symbol,order_link_id=order['link'],
                ret_code=body['retCode'],at_ms=now_ms(),source_sha256=sha(response.read_bytes()),
                event_id='saved-terms-rejection-'+order['link']))
    def fresh(self,store):
        cap=capture_account(self.reader);cap['response']['physical_config_sha256']=self.config['_config_sha256']
        p=store/'captures'/('capture-'+str(cap['response']['started_ms'])+'.json');pin=publish(p,cap)
        bounds=json.loads((Path(self.config['app_root'])/self.config['bounds_file']).read_bytes())
        return load_source(p,pin,bounds,self.config['_config_sha256'])
    def before_selection(self):
        if self.config.get('recovery_binding') is not None:raise SourceError('RECOVERY_ONLY_NO_NEW_SELECTION')
        if (self.root/'rollback-request.json').exists():raise SourceError('CONTROL_CLOSED_FOR_ROLLBACK')
        if (self.root/'selected-v2.json').exists():raise SourceError('ONE_BOUNDED_EXPERIMENT_ALREADY_SELECTED')
        read_predecessor(self.config);self.check()
    def control(self,x):
        validate_control(x);kind=x['kind']
        if kind=='KILL':return super().control(x)
        self.before_selection()
        if kind=='PREPARE_BOUNDED':
            d,_=self.fresh(self.root/'bounded-preparation')
            i=make_intent(d,at_ms=now_ms(),collar_bps='50',ttl_ms=600000,
                predecessor_plan_id=self.config['predecessor_plan_id'])
            publish(self.root/'bounded-intents'/(i['intent_id']+'.json'),i)
            return dict(status='BOUNDED_INTENT_PREPARED_ORDERS_OFF',intent_id=i['intent_id'],
                expires_ms=i['expires_ms'],bands=i['price_bands'],broker_writes=0,
                owner_go_text='GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'])
        i=json.loads((self.root/'bounded-intents'/(x['intent_id']+'.json')).read_bytes());validate_intent(i)
        if i['intent_id']!=x['intent_id'] or i['physical_config_sha256']!=self.config['_config_sha256']:
            raise SourceError('EXACT_PREPARED_INTENT_REQUIRED')
        _window(i,now_ms())
        if kind=='REHEARSE_BOUNDED':
            d,c=self.fresh(self.root/'bounded-rehearsals');out=materialize(i,d,c,now_ms=now_ms())
            verify_materialization(out);results=[]
            before=len(list((self.root/'wire').glob('send-*.json')))
            with tempfile.TemporaryDirectory(prefix='bounded-no-send-',dir=self.root) as tmp:
                j=JournalV2(Path(tmp)/'rehearsal.sqlite',out['plan'])
                o=PhysicalOwner(j,self.reader,self.lease,tmp,platform_check=self.check,post=self.writer.post)
                try:
                    for leg in out['plan']['legs']:
                        sd_notify('WATCHDOG=1');_window(i,now_ms())
                        try:o.validate_preflight(out['plan'],leg['request'],'ENTRY');status='FRESH_PREFLIGHT_PASS_POST_INHIBITED'
                        except SourceError as exc:status=str(exc)
                        try:o.post_once('/v5/order/create',leg['request'])
                        except SourceError as exc:
                            if 'EXACT_OWNER_GO' not in str(exc):raise
                        else:raise SourceError('BOUNDED_REHEARSAL_AUTHORITY_BYPASS')
                        results.append(dict(symbol=leg['symbol'],fresh_result=status))
                    if j.snapshot()['entries']:raise SourceError('REHEARSAL_CREATED_ENTRY_INTENT')
                finally:j.close()
            if len(list((self.root/'wire').glob('send-*.json')))!=before:raise SourceError('REHEARSAL_POST_BARRIER_CHANGED')
            fresh_only=[r for r in results if r['fresh_result']!='FRESH_PREFLIGHT_PASS_POST_INHIBITED']
            return dict(status='BOUNDED_GET_ONLY_REHEARSAL_PASS' if not fresh_only else 'BOUNDED_REHEARSAL_FRESH_ONLY',intent_id=i['intent_id'],
                plan_id=out['plan']['plan_id'],gross=out['current_basket_gross_usdt'],
                native_stop_payloads=10,legs=results,static_blockers=[],fresh_only=fresh_only,
                actual_journal_created=False,broker_writes=0)
        publish(self.root/'selected-v2.json',dict(intent_id=i['intent_id'],owner_go_text=x['exact_go'],at_ms=now_ms()))
        self.experiment_root=selected_store(self.root,{'intent_id':i['intent_id']})
        out=consume_once(self.experiment_root,i,x['exact_go'],lambda:self.fresh(self.experiment_root),clock=now_ms)
        publish(self.experiment_root/'active-plan.json',out);self.bind(out,create=True)
        self.owner.accept_intent_go(x['exact_go'])
        return dict(status='BOUNDED_GO_BOUND_ONE_EXPERIMENT',intent_id=i['intent_id'],plan_id=out['plan']['plan_id'])


def rollback_state(config):
    """No mutation. Resolve current selected state before any owner restoration."""
    from research_lab.kity_micro_handoff_v1 import rollback_safe
    root=Path(config['runtime_root']);selection=root/'selected-v2.json'
    if not selection.exists():return None
    store=selected_store(root,json.loads(selection.read_bytes()))
    active=store/'active-plan.json'
    if not active.exists():
        if (store/'materialized.json').exists() or any((root/'wire').glob('send-*.json')):
            raise SourceError('ROLLBACK_SELECTED_SOURCE_MISSING')
        return None # no materialized plan and no possible POST, still needs fresh flat GET
    d=json.loads(active.read_bytes());s=read_state(store/'lifecycle.sqlite',d['plan'],JournalV2)
    if s['phase']!='TERMINAL' or not rollback_safe(s):raise SourceError('ROLLBACK_SELECTED_RISK_OR_UNCERTAIN_SEND')
    return s


def rollback(config):
    """Explicit operator path only. Never invoked by a watchdog or source check."""
    from research_lab.kity_micro_handoff_v1 import verify_files,fresh_flat,run,OLD_UNITS
    from research_lab.kity_micro_physical_owner_v1 import unit_state
    root=Path(config['runtime_root']);verify_files(config);read_predecessor(config)
    if not (root/'rollback-request.json').exists():publish(root/'rollback-request.json',dict(at_ms=now_ms(),reason='BOUNDED_OWNER_RETURN_REQUESTED'))
    rollback_state(config)
    for p in (root/'commands').glob('*.json'):
        if not (root/'results'/p.name).exists():raise SourceError('ROLLBACK_UNPROCESSED_COMMAND')
    key,secret=load_bound_credentials(config);reader=BybitReadTransport(key,secret)
    first=fresh_flat(reader,'v2-rollback-before',root)
    run('systemctl','stop',config['unit']);run('systemctl','disable',config['unit'])
    if unit_state(config['unit'])['MainPID']!='0':raise SourceError('OWNER_STILL_RUNNING')
    lease=AccountLease(root/'account.lock')
    try:
        rollback_state(config);second=fresh_flat(reader,'v2-rollback-stopped',root)
        for u,pin in config['inhibitors'].items():
            p=Path('/etc/systemd/system')/(u+'.d')/'90-kity-micro-inhibit.conf'
            if sha(p.read_bytes())!=pin:raise SourceError('ROLLBACK_INHIBITOR_CAS_CONFLICT')
        for u in OLD_UNITS:(Path('/etc/systemd/system')/(u+'.d')/'90-kity-micro-inhibit.conf').unlink()
        Path(config['inhibit_marker']).unlink();run('systemctl','daemon-reload')
        for u in OLD_UNITS:run('systemctl','start',u)
        result=dict(status='V2_ROLLED_BACK_AFTER_CURRENT_SELECTED_FINALITY',at_ms=now_ms(),
            first_flat=first,stopped_flat=second,broker_writes=0)
        publish(root/('rollback-v2-'+str(result['at_ms'])+'.json'),result);return result
    finally:lease.close()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--config-sha256',required=True)
    mode=ap.add_mutually_exclusive_group();mode.add_argument('--command');mode.add_argument('--rollback',action='store_true')
    a=ap.parse_args();raw=Path(a.config).read_bytes()
    if sha(raw)!=a.config_sha256:raise SourceError('CONFIG_PIN_CONFLICT')
    c=json.loads(raw);c.update(_config_path=a.config,_config_sha256=a.config_sha256);root=Path(c['runtime_root'])
    if a.rollback:print(json.dumps(rollback(c)));return
    if a.command:
        x=validate_control(json.loads(a.command));identifier=str(time.time_ns());publish(root/'commands'/(identifier+'.json'),x)
        print(json.dumps(dict(status='COMMAND_QUEUED',command_id=identifier)));return
    s=BoundedSupervisor(c);s.check();s.heartbeat();sd_notify('READY=1')
    while True:
        sd_notify('WATCHDOG=1')
        for p in sorted((root/'commands').glob('*.json')):
            done=root/'results'/p.name
            if done.exists():continue
            claim=root/'claims'/p.name
            if claim.exists():publish(done,dict(status='CONTROL_INTERRUPTED_NOT_RETRIED',orders_allowed=False));continue
            publish(claim,dict(command_sha256=sha(p.read_bytes()),at_ms=now_ms()))
            try:result=s.control(json.loads(p.read_bytes()))
            except Exception as exc:result=dict(status='CONTROL_BLOCKED',reason=str(exc)[:2000],orders_allowed=False)
            publish(done,result)
        try:
            if not s.journal:s.check()
            error=s.cycle()
        except Exception as exc:
            error=type(exc).__name__+':'+str(exc)[:1024];s.unwind('SUPERVISOR_FAILURE:'+type(exc).__name__)
        s.heartbeat(error);sd_notify('WATCHDOG=1');time.sleep(1 if s.journal and s.journal.snapshot()['phase']!='TERMINAL' else 3)


if __name__=='__main__':main()
