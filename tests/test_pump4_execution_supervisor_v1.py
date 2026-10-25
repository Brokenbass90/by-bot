"""Synthetic physical/profile verifier only; real temporary flock and memory wire."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import threading
from decimal import Decimal as D

import pytest
from test_pump4_selected_runner_v1 import fixture
from test_pump4_supervisor_v1 import fixture_candidate
from test_pump4_account_owner_v1 import inputs, reseal
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_micro_physical_owner_v1 import AccountLease
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle


def module():
    try:return importlib.import_module('research_lab.pump4_execution_supervisor_v1')
    except ImportError:pytest.fail('Long-lived selected execution supervisor missing')


def setup(tmp_path, monkeypatch, *, dispatch=False, go=True, overrides=None):
    runner,s,path,pin,config,scope,called=fixture(tmp_path,monkeypatch,dispatch=dispatch,go=False)
    config.update(mode=scope['mode']);config.update(overrides or {})
    scope['runner_config_sha256']=runner.config_sha(config)
    scope_path=Path(config['authority']['path']);scope_path.write_text(json.dumps(scope))
    config['authority']['sha256']=hashlib.sha256(scope_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(config));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    if go and dispatch:
        root=Path(scope['root']);root.mkdir()
        p=root/'owner-go.json';p.write_text(json.dumps(dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=digest(scope),owner_go_text='GO PUMP4_TINY '+digest(scope))));p.chmod(0o600)
    monkeypatch.setattr(runner,'wire_post',s[1].wire)
    return runner,s,path,pin,config,scope,called


def provider(s, candidate, *, prices=None, failures=()):
    o,e,t,_,_,lease=s
    class Sources:
        count=0
        candidate_calls=0
        def __init__(self, config, owner):self.owner=owner
        def candidate(self):
            self.candidate_calls+=1
            if self.candidate_calls>1:raise RuntimeError('new signal source unavailable')
            return candidate
        def account(self,plan,*,custody):
            self.owner.lease.assert_held()
            with pytest.raises(BlockingIOError):AccountLease(lease.path)
            self.count+=1
            if self.count in failures:raise TimeoutError('GET failed')
            price=(prices or ['100'])[min(self.count-1,len(prices or ['100'])-1)]
            x,p=inputs(e,now=t[0],price=price)
            cap=p['instruments']['pages'][0];cap['body']['result']['list'][0]['priceFilter']['tickSize']='.000000000000000001';reseal(cap)
            for group in (x['captures']['positions'],x['captures']['symbol_position']):
                for cap in group.get('pages',[group]):
                    for row in cap['body']['result']['list']:
                        if 'stopLoss' in row:row['stopLoss']=str(plan['stop'])
                    reseal(cap)
            return x,p
    return Sources


def test_default_cli_has_no_state_provider_credentials_or_lease(tmp_path,capsys):
    module()
    from scripts import run_pump4_execution_supervisor_v1 as cli
    assert cli.main(['--config',str(tmp_path/'missing'),'--once'])==0
    assert json.loads(capsys.readouterr().out)['status']=='ORDERS_OFF_NO_REQUESTS'
    assert list(tmp_path.iterdir())==[]


def test_missing_go_fails_before_provider_credentials_or_lease(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,dispatch=True,go=False)
    def forbidden(*a):pytest.fail('source factory must not run')
    with pytest.raises(ValueError,match='EXACT_OWNER_GO'):
        m.run(path,pin,dispatch=True,once=True,source_factory=forbidden)
    assert called==[]
    AccountLease(s[-1].path).close()
    assert not Path(scope['root']).exists()


@pytest.mark.parametrize('change',[dict(mode='OWNER_TINY_LIVE'),dict(epoch_started_ms=True),dict(entry_max_delay_ms=60001)])
def test_invalid_bound_config_fails_before_selection(tmp_path,monkeypatch,change):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,overrides=change)
    with pytest.raises(ValueError):m.run(path,pin,orders_off=True,once=True,source_factory=lambda *a:pytest.fail('provider'))
    assert not called


def test_once_off_actual_causal_candidate_zero_wire_immutable_receipt(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch)
    candidate=fixture_candidate(tmp_path);sources=provider(s,candidate)
    results=m.run(path,pin,orders_off=True,once=True,source_factory=sources,clock=lambda:s[2][0])
    assert results[0]['result']['status']=='ACTION_RESERVED_ORDERS_OFF'
    assert results[0]['broker_writes']==0 and s[1].state['calls']==0
    files=list((Path(scope['root'])/'supervisor/receipts').glob('*.json'))
    assert len(files)==1 and json.loads(files[0].read_bytes())==results[0]
    before=files[0].read_bytes()
    again=m.run(path,pin,orders_off=True,once=True,source_factory=sources,clock=lambda:s[2][0])
    assert again[0]['result']['status']=='RECONCILE_ONLY' and files[0].read_bytes()==before


def test_one_original_lease_full_40_60_and_no_final_cost_claim(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,dispatch=True)
    candidate=fixture_candidate(tmp_path)
    plan=r.causal_plan(**candidate,epoch_started_ms=c['epoch_started_ms'],max_delay_ms=c['entry_max_delay_ms'],now_ms=s[2][0])
    sources=provider(s,candidate,prices=['100',str(plan['targets'][0]-.01),str(plan['targets'][1]-.01),str(plan['targets'][1]-.01)])
    instances=[]
    def factory(config,owner):
        item=sources(config,owner);instances.append(item);return item
    def advance(receipt):s[2][0]+=1000
    class FastStop(threading.Event):
        def wait(self,timeout=None):return self.is_set()
    out=m.run(path,pin,dispatch=True,max_ticks=4,source_factory=factory,clock=lambda:s[2][0],stop=FastStop(),on_receipt=advance)
    assert len(instances)==1 and instances[0].candidate_calls==1
    assert [row['result'].get('role') for row in out[:3]]==['ENTRY','TP1','TP2']
    assert out[-1]['result']['status']=='FLAT_COSTS_PENDING'
    root=Path(scope['root']);identity=json.loads((root/'admitted-lifecycle.json').read_bytes())
    reqs=Pump4Lifecycle.resume(identity['flow_root']).requests()
    assert D(reqs[1]['qty'])==D(reqs[0]['qty'])*D('.4') and D(reqs[2]['qty'])==D(reqs[0]['qty'])*D('.6')
    assert s[1].state['calls']==3
    AccountLease(s[-1].path).close()


def test_lost_entry_reply_restart_source_failure_still_services_custody(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,dispatch=True)
    s[1].scenario='entry_reply_loss';candidate=fixture_candidate(tmp_path)
    sources=provider(s,candidate)
    first=m.run(path,pin,dispatch=True,once=True,source_factory=sources,clock=lambda:s[2][0])
    assert first[0]['result']['status']=='WIRE_UNKNOWN_RECONCILE_ONLY'
    class Restart(sources):
        def candidate(self):pytest.fail('custody must precede failed candidate source')
    second=m.run(path,pin,dispatch=True,once=True,source_factory=Restart,clock=lambda:s[2][0])
    assert second[0]['result']['status']=='PROTECTED_WAIT' and s[1].state['calls']==1


def test_loop_source_errors_keep_same_lease_and_clean_stop(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch)
    stop=threading.Event();owners=[];alerts=[]
    class Sources:
        def __init__(self,config,owner):self.owner=owner;owners.append(owner)
        def candidate(self):
            self.owner.lease.assert_held()
            with pytest.raises(BlockingIOError):AccountLease(s[-1].path)
            raise RuntimeError('GET failed')
        def account(self,*a,**k):pytest.fail('no candidate')
    class FastStop(threading.Event):
        def wait(self,timeout=None):return self.is_set()
    out=m.run(path,pin,orders_off=True,max_ticks=3,source_factory=Sources,clock=lambda:s[2][0],stop=FastStop(),alert=lambda event:(alerts.append(event) or dict(delivered=True)))
    assert len(owners)==1 and all(x['result']['status']=='BLOCKED_OBSERVATION' for x in out)
    assert len(alerts)==1
    AccountLease(s[-1].path).close()


def test_candidate_attempt_durable_even_failed_account_read(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch)
    candidate=fixture_candidate(tmp_path);calls=[]
    class Sources:
        def __init__(self,*a):pass
        def candidate(self):return candidate
        def account(self,*a,**k):calls.append(1);raise TimeoutError('GET')
    first=m.run(path,pin,orders_off=True,once=True,source_factory=Sources,clock=lambda:s[2][0])
    second=m.run(path,pin,orders_off=True,once=True,source_factory=Sources,clock=lambda:s[2][0])
    assert len(calls)==1 and second[0]['result']['status']=='BLOCKED_NEW_INPUTS'
    assert not (Path(scope['root'])/'admitted-lifecycle.json').exists()


def test_config_entry_delay_not_overridden_after_slow_get(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,overrides=dict(entry_max_delay_ms=10))
    candidate=fixture_candidate(tmp_path);sources=provider(s,candidate)
    class Slow(sources):
        def account(self,*a,**k):
            value=super().account(*a,**k);s[2][0]+=11;return value
    out=m.run(path,pin,orders_off=True,once=True,source_factory=Slow,clock=lambda:s[2][0])
    assert out[0]['result']['status']=='BLOCKED_NEW_INPUTS' and 'ENTRY_WINDOW' in out[0]['result']['reason']
    assert s[1].state['calls']==0
    with pytest.raises(TypeError):m.run(path,pin,orders_off=True,once=True,epoch_started_ms=1)


def test_cli_sigterm_closes_original_lease(tmp_path,monkeypatch,capsys):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch)
    from scripts import run_pump4_execution_supervisor_v1 as cli
    class Sources:
        def __init__(self,*a):pass
        def candidate(self):os.kill(os.getpid(),signal.SIGTERM);return None
        def account(self,*a,**kw):pytest.fail('no account needed')
    monkeypatch.setattr(m,'trusted_sources',Sources)
    previous=signal.getsignal(signal.SIGTERM)
    assert cli.main(['--orders-off','--config',str(path),'--config-sha256',pin])==0
    assert signal.getsignal(signal.SIGTERM)==previous
    AccountLease(s[-1].path).close()


def test_failed_physical_verifier_never_constructs_sources_or_claims_owner(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch)
    def conflict():raise ValueError('ORIGINAL_OWNER_STILL_RUNNING')
    monkeypatch.setattr(r,'platform_verifier',lambda config:conflict)
    with pytest.raises(ValueError,match='ORIGINAL_OWNER'):
        m.run(path,pin,orders_off=True,once=True,source_factory=lambda *a:pytest.fail('no provider'))
    assert called==[] and not Path(scope['root']).exists()
    AccountLease(s[-1].path).close()


def test_custody_get_failure_recovers_under_same_lease_without_entry_retry(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,dispatch=True)
    candidate=fixture_candidate(tmp_path);sources=provider(s,candidate,failures=(2,))
    objects=[]
    def factory(config,owner):
        obj=sources(config,owner);objects.append(obj);return obj
    class FastStop(threading.Event):
        def wait(self,timeout=None):return self.is_set()
    out=m.run(path,pin,dispatch=True,max_ticks=3,source_factory=factory,clock=lambda:s[2][0],stop=FastStop())
    assert [row['result']['status'] for row in out]==['ACK_RECONCILE_REQUIRED','BLOCKED_OBSERVATION','PROTECTED_WAIT']
    assert out[1]['broker_writes'] is None and out[1]['result']['finality_proven'] is False
    assert len(objects)==1 and objects[0].candidate_calls==1 and s[1].state['calls']==1
    AccountLease(s[-1].path).close()


def test_provider_cannot_mutate_authorized_clocks(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,overrides=dict(entry_max_delay_ms=1))
    candidate=fixture_candidate(tmp_path);sources=provider(s,candidate)
    class Mutating(sources):
        def __init__(self,config,owner):
            super().__init__(config,owner);config.update(entry_max_delay_ms=60000,epoch_started_ms=1)
    out=m.run(path,pin,orders_off=True,once=True,source_factory=Mutating,clock=lambda:s[2][0])
    assert out[0]['result']['status']=='BLOCKED_NEW_INPUTS' and 'ENTRY_WINDOW' in out[0]['result']['reason']
    assert s[1].state['calls']==0


def test_cli_unclassified_failure_never_claims_zero_dispatch_writes(tmp_path,monkeypatch,capsys):
    module()
    from scripts import run_pump4_execution_supervisor_v1 as cli
    def uncertain(*args,**kwargs):raise OSError('receipt clock failed after a tick')
    monkeypatch.setattr(cli,'run',uncertain)
    assert cli.main(['--dispatch','--config',str(tmp_path/'config'),'--config-sha256','0'*64,'--once'])==2
    assert json.loads(capsys.readouterr().out)['broker_writes'] is None


def test_bound_source_alert_selected_after_owner_and_failure_preserves_custody(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,dispatch=True,
        overrides=dict(notifications=dict(path='fixture-only',sha256='1'*64)))
    candidate=fixture_candidate(tmp_path);sources=provider(s,candidate)
    owners=[];binding=[];attempts=[]
    class Sources(sources):
        def __init__(self,config,owner):
            super().__init__(config,owner);owners.append(owner)
        @property
        def alert(self):
            assert called[0]=='physical' and 'credentials' in called
            self.owner.lease.assert_held()
            with pytest.raises(BlockingIOError):AccountLease(s[-1].path)
            binding.append(self.owner)
            def send(event):
                self.owner.lease.assert_held();attempts.append(event)
                raise TimeoutError('notification response lost')
            return send
    class FastStop(threading.Event):
        def wait(self,timeout=None):return self.is_set()
    out=m.run(path,pin,dispatch=True,max_ticks=3,source_factory=Sources,clock=lambda:s[2][0],stop=FastStop())
    assert binding==owners and len(owners)==1
    assert [row['result']['status'] for row in out]==['ACK_RECONCILE_REQUIRED','PROTECTED_WAIT','PROTECTED_WAIT']
    assert len(attempts)==2 and s[1].state['calls']==1
    notifications=list((Path(scope['root'])/'supervisor/alerts').glob('*/notification-receipt.json'))
    assert len(notifications)==2
    assert all(json.loads(p.read_bytes())['status']=='NOTIFICATION_UNKNOWN_DO_NOT_RETRY' for p in notifications)
    AccountLease(s[-1].path).close()


@pytest.mark.parametrize('explicit',[False,True])
def test_no_notification_pin_or_explicit_override_never_accesses_source_alert(tmp_path,monkeypatch,explicit):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,
        overrides=dict(notifications=dict(path='fixture-only',sha256='1'*64)) if explicit else {})
    events=[]
    class Sources:
        def __init__(self,*args):pass
        def candidate(self):return None
        @property
        def alert(self):pytest.fail('Source callback must remain unselected')
        def account(self,*args,**kwargs):pytest.fail('No account needed')
    callback=(lambda event:(events.append(event) or dict(delivered=True))) if explicit else None
    m.run(path,pin,orders_off=True,once=True,source_factory=Sources,clock=lambda:s[2][0],alert=callback)
    assert len(events)==int(explicit)


def test_notification_pin_does_not_bypass_physical_owner_validation(tmp_path,monkeypatch):
    m=module();r,s,path,pin,c,scope,called=setup(tmp_path,monkeypatch,
        overrides=dict(notifications=dict(path='fixture-only',sha256='1'*64)))
    def conflict():raise ValueError('ORIGINAL_OWNER_ACTIVE')
    monkeypatch.setattr(r,'platform_verifier',lambda config:conflict)
    with pytest.raises(ValueError,match='ORIGINAL_OWNER_ACTIVE'):
        m.run(path,pin,orders_off=True,once=True,source_factory=lambda *a:pytest.fail('No source or alert loading before owner'))
    assert called==[] and not Path(scope['root']).exists()
