"""Reproduce stale evidence at its use point. All clients/identities are fixtures."""
import copy
from datetime import datetime,timezone
from pathlib import Path
from decimal import Decimal
import pytest
from research_lab import alpaca_monthly_native_binding_v1 as native_mod
from research_lab import alpaca_monthly_cost_source_v1 as costs
from research_lab.alpaca_fee_to_live_closure_v1 import collect_account_cost_source
from research_lab.alpaca_dynamic_v1 import canonical
from test_alpaca_monthly_native_binding_v1 import setup
from test_alpaca_monthly_cost_source_v1 import case
from test_alpaca_monthly_pending_fees_v1 import pending_inputs,producer_fixture


def prepared(case,tmp_path,monkeypatch):
    c=pending_inputs(case);n,paths,source=producer_fixture(c,tmp_path)
    n.pending_fee_sources=costs.produce_cost_sources(n,**paths,now_ms=c['observed'],allow_pending=True)
    elapsed=[0.];monkeypatch.setattr(native_mod.time,'monotonic',lambda:elapsed[0])
    n.client.get_account=lambda:copy.deepcopy(source['account_after'])
    return c,n,paths,source,elapsed


def refresh_source(c,n,paths,source,elapsed,tmp_path):
    # New immutable source; old source/estimate bytes and clocks are preserved.
    stamp=c['observed']+int(elapsed[0]*1000)
    account=source['account_after']
    def get(route,query):
        return dict(http_status=200,started_ms=stamp-100,received_ms=stamp-100,
            raw=__import__('json').dumps(account if route=='/v2/account' else c['fills']+c['fees']))
    until=datetime.fromtimestamp((stamp-1000)/1000,timezone.utc).isoformat()
    fresh=collect_account_cost_source(get,account_id='fixture',after='2026-10-01T00:00:00Z',until=until,now_ms=stamp)
    path=tmp_path/('fresh-'+str(stamp)+'.json');path.write_bytes(canonical(fresh))
    n.pending_fee_sources=costs.produce_cost_sources(n,**dict(paths,source_path=str(path)),now_ms=stamp,allow_pending=True)


def test_stale_actual_pending_proof_refreshes_at_use_without_retiming_old_source(case,tmp_path,monkeypatch):
    c,n,paths,source,elapsed=prepared(case,tmp_path,monkeypatch);elapsed[0]=6.;calls=[]
    original=Path(paths['source_path']).read_bytes()
    with pytest.raises(ValueError,match='MONTHLY_PENDING_FEE_STALE_SOURCE'):
        n._accounting_for_admission(account=source['account_after'],now_ms=c['observed']+6000)
    def refresh():
        calls.append('capture');elapsed[0]+=3.
        refresh_source(c,n,paths,source,elapsed,tmp_path)
        # Existing finality callback re-enters the classifier after capture.
        n._require_admission_accounting(now_ms=c['observed']+int(elapsed[0]*1000))
    with n.admission_cost_refresh(refresh):
        lower,proof=n._accounting_for_admission(account=source['account_after'],now_ms=c['observed']+6000)
    assert calls==['capture'] and lower==Decimal('1.98')
    assert proof['source_observed_ms']==c['observed']+9000
    assert Path(paths['source_path']).read_bytes()==original
    assert getattr(n,'_admission_cost_refresher',None) is None


def test_refresh_is_bounded_and_does_not_recurse_on_still_stale_evidence(case,tmp_path,monkeypatch):
    c,n,paths,source,elapsed=prepared(case,tmp_path,monkeypatch);elapsed[0]=6.;calls=[]
    def refresh():
        calls.append(1);n._require_admission_accounting(now_ms=c['observed']+6000)
    with n.admission_cost_refresh(refresh):
        with pytest.raises(ValueError,match='MONTHLY_PENDING_FEE_STALE_SOURCE'):
            n._accounting_for_admission(account=source['account_after'],now_ms=c['observed']+6000)
    assert calls==[1] and not getattr(n,'_admission_refreshing',False)
    assert getattr(n,'_admission_cost_refresher',None) is None


def test_fresh_proof_and_cash_conflicts_do_not_trigger_refresh(case,tmp_path,monkeypatch):
    c,n,paths,source,elapsed=prepared(case,tmp_path,monkeypatch)
    def forbidden():pytest.fail('Only an exact stale-source result may refresh')
    with n.admission_cost_refresh(forbidden):
        assert n._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])[0]==Decimal('1.98')
        bad=dict(source['account_after'],cash='999')
        with pytest.raises(ValueError,match='CASH_OR_LIABILITY_CHANGED'):
            n._accounting_for_admission(account=bad,now_ms=c['observed'])


@pytest.mark.parametrize('field,value', [
    ('cash','1'),('equity','1'),('non_marginable_buying_power','1'),
    ('accrued_fees','9'),('pending_reg_taf_fees','9'),
    ('trading_blocked',True),('account_blocked',True),('currency','EUR'),
])
def test_refresh_rejects_changed_admission_account(case,tmp_path,monkeypatch,field,value):
    c,n,paths,source,elapsed=prepared(case,tmp_path,monkeypatch);elapsed[0]=6.
    original=copy.deepcopy(source['account_after'])
    def refresh():
        refresh_source(c,n,paths,source,elapsed,tmp_path)
        n.client.get_account=lambda:dict(original,**{field:value})
    with n.admission_cost_refresh(refresh):
        with pytest.raises(ValueError,match='MONTHLY_ADMISSION_ACCOUNT_CHANGED_DURING_REFRESH'):
            n._accounting_for_admission(account=original,now_ms=c['observed']+6000)
    assert not getattr(n,'_admission_refreshing',False)
    assert getattr(n,'_admission_cost_refresher',None) is None


@pytest.mark.parametrize('account_change',[None,'cash','trading_blocked'])
def test_full_opening_reproduces_old_failure_then_refreshes_without_duplicate_buy(setup,case,tmp_path,monkeypatch,account_change):
    import json,hashlib
    from contextlib import nullcontext
    from test_alpaca_monthly_cycle_custody_v1 import wired
    from test_alpaca_monthly_account_transport_v1 import connect_wire
    from test_alpaca_monthly_standing_v1 import standing,resign
    from test_alpaca_monthly_legacy_cost_transition_v1 import legacy_case
    from scripts import run_alpaca_dynamic_v1_orders_off as history_cli
    m,n,s,io,now=wired(setup,tmp_path);now+=2000
    connect_wire((m.book,s,n,io,now),monkeypatch);scope=standing(n,now)
    elapsed=[0.];monkeypatch.setattr(native_mod.time,'monotonic',lambda:elapsed[0])
    n.pending_fee_admission=True;n.liability=Decimal('.04')
    account=dict(id='fixture',currency='USD',cash='487.42',equity='487.42',
        non_marginable_buying_power='487.42',accrued_fees='.02',pending_reg_taf_fees='0',
        trading_blocked=False,account_blocked=False)
    io.get_account=lambda:copy.deepcopy(account)
    io.get_clock=lambda:dict(is_open=True,timestamp=datetime.fromtimestamp((now+elapsed[0]*1000)/1000,timezone.utc).isoformat())
    _,seal=legacy_case(case);seal['exits'][0]['filled_at']='2026-11-02T14:30:00Z';seal['sealed_ms']=now-1000
    seal_path=tmp_path/'refresh-legacy.json';seal_path.write_bytes(canonical(seal));pin=dict(path=str(seal_path),sha256=__import__('hashlib').sha256(seal_path.read_bytes()).hexdigest())
    paths={}
    for key,value in dict(protocol=case['protocol'],calendar=s['calendar'],assets=[dict(id='NET',symbol='NET',asset_class='us_equity',exchange='NASDAQ')]).items():
        path=tmp_path/(key+'-opening.json');path.write_bytes(canonical(value));paths[key+'_path']=str(path)
    rows={k:dict(path=paths[k+'_path'],sha256=hashlib.sha256(Path(paths[k+'_path']).read_bytes()).hexdigest()) for k in ['protocol','calendar','assets']}
    scope.update(liability_reserve_usd='0.04',pending_fee_admission=native_mod.PENDING_FEE_POLICY,
        pending_fee_protocol_sha256=rows['protocol']['sha256'],legacy_cost_transition=pin,
        legacy_pending_cost_inputs=dict(after='2026-11-02T00:00:00Z',**rows));resign(n,scope)
    fill=dict(id='legacy-f1',activity_type='FILL',order_id='legacy-sell',symbol='NET',side='sell',qty='1',price='5',transaction_time='2026-11-02T14:30:00Z');captures=[]
    def capture(exits):
        stamp=now+int(elapsed[0]*1000);captures.append(stamp)
        def get(route,query):return dict(http_status=200,started_ms=stamp,received_ms=stamp,raw=json.dumps(account if route=='/v2/account' else [fill]))
        src=collect_account_cost_source(get,account_id='fixture',after='2026-11-02T00:00:00Z',until=datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat(),now_ms=stamp)
        path=tmp_path/('opening-capture-'+str(stamp)+'.json');path.write_bytes(canonical(src))
        result=costs.produce_cost_sources(n,**dict(paths,source_path=str(path)),legacy_transition=pin,now_ms=stamp,allow_pending=True)
        if account_change and getattr(n,'_admission_refreshing',False):
            account[account_change]='1' if account_change=='cash' else True
        return result
    authority=n._entry_authority
    def slow(ticket,observed,**kwargs):
        # Delay source/authority work before its final handoff witness, not
        # after the witness (which correctly has its own five-second TTL).
        elapsed[0]+=6.
        return authority(ticket,observed+6000,**kwargs)
    monkeypatch.setattr(n,'_entry_authority',slow)
    monkeypatch.setattr(m,'source',lambda *a,**kw:dict(status='EXISTING_FIXTURE_SELECTION'))
    monkeypatch.setattr(history_cli,'load_history',lambda _: {})
    quotes={'NET':dict(ask=311.,quote_ts=now,received_ms=now,source='fixture')}
    args=dict(apply=True,source_loader=lambda:dict(history='fixture-only'),quotes=quotes,cost_sources=capture)
    hook=n.admission_cost_refresh
    monkeypatch.setattr(n,'admission_cost_refresh',lambda _:nullcontext())
    old=m.tick(n,now_ms=now,**args)
    assert old['entry_status']=='BLOCKED' and old['issues'][0]['reason']=='MONTHLY_PENDING_FEE_STALE_SOURCE'
    assert io.sent==[] and not n.reentry.exists() and len(list((m.root/'tickets').glob('*.json')))==1
    monkeypatch.setattr(n,'admission_cost_refresh',hook)
    new=m.tick(n,now_ms=now+int(elapsed[0]*1000),**args)
    if account_change:
        assert new['entry_status']=='BLOCKED'
        assert new['issues'][0]['reason'] in {'MONTHLY_ADMISSION_ACCOUNT_CHANGED_DURING_REFRESH','MONTHLY_PENDING_FEE_CASH_OR_LIABILITY_CHANGED'}
        assert io.sent==[] and not n.reentry.exists() and not m.book.rows('positions')
        return
    assert new['issues']==[] and new['entry_status']=='OPENING_PROCESSED'
    assert len(io.sent)==2 and len(m.book.rows('positions'))==1
    assert getattr(n,'_admission_cost_refresher',None) is None
    saved=json.loads(next((m.root/'tickets').glob('*.json')).read_bytes())
    assert n.enter(saved,now_ms=now+int(elapsed[0]*1000),apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert len(io.sent)==2 and len(captures)>=4


def test_refresh_reuses_verified_held_account_descriptor_without_releasing_writer(tmp_path):
    import os,fcntl
    from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock
    from research_lab.alpaca_monthly_native_binding_v1 import MonthlyNativeBinding
    path=tmp_path/'account.lock';n=object.__new__(MonthlyNativeBinding);n.lock_path=path
    with account_lock(dict(lock_path=str(path))) as fd:
        assert type(fd) is int
        with n._cost_capture_lock(fd):
            with n.cost_snapshot_guard():
                assert os.fstat(fd).st_ino==path.stat().st_ino
                other=os.open(path,os.O_RDWR)
                try:
                    with pytest.raises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
                finally:os.close(other)
            other=os.open(path,os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:os.close(other)
