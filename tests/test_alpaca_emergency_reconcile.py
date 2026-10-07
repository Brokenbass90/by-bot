"""Catch fabricated stop exits, premature retirement, and restart loss of provenance."""
import copy
import json
from pathlib import Path
import pytest
from scripts import alpaca_emergency_reconcile as recovery

NOW = 1791384900000  # 2026-10-07 14:55 UTC

def fixture(tmp_path):
    state={'CRWD': {'account_id':'acct','strategy_id':'frozen','entry_order_id':'buy',
        'accepted_order_id':'old-stop','qty':'.4','entry_price':'265',
        'hwm':285,'accepted_stop_floor':275.45,'lifecycle_first_seen_at_utc':'2026-10-01T14:10:00Z'}}
    blocks={'symbols':{'AMD':{'blocked_until':'2026-10-26T13:30:31Z'}},'entry_intents':{'old':{'status':'complete'}}}
    proof={'account_id':'acct','reason':'unprotected_after_reconcile','positions':[
        {'symbol':'CRWD','entry_order_id':'buy','qty':'.4','avg_entry_price':'265'}]}
    kill={'status':'confirmed_flat','reason':'unprotected_after_reconcile',
        'scope_symbols':['CRWD'],'remaining_symbols':[],
        'order_results':[{'symbol':'CRWD','close_order_id':'exit'}]}
    orders=[{'id':'buy','symbol':'CRWD','side':'buy','type':'market','status':'filled',
        'filled_qty':'.4','filled_avg_price':'265','filled_at':'2026-10-01T14:10:00Z'},
        {'id':'old-stop','symbol':'CRWD','side':'sell','type':'stop','status':'expired','filled_qty':'0'},
        {'id':'exit','symbol':'CRWD','side':'sell','type':'market','status':'filled','qty':'.4',
        'filled_qty':'.4','filled_avg_price':'275.43','filled_at':'2026-10-07T13:30:21Z'}]
    evidence={'observed_ms':NOW,'account':{'id':'acct','cash':'496.12','accrued_fees':'0','pending_reg_taf_fees':'.02'},
        'positions':[],'open_orders':[],'orders':orders,'activities':[
        {'id':'fill','activity_type':'FILL','order_id':'exit','symbol':'CRWD','side':'sell',
        'qty':'.4','price':'275.43','transaction_time':'2026-10-07T13:30:21Z'}]}
    for name,value in [('floor',state),('reentry',blocks),('halt',{'halted':True,'account_id':'acct'})]:
        (tmp_path/f'{name}.json').write_text(json.dumps(value))
    return dict(state_path=tmp_path/'floor.json',reentry_path=tmp_path/'reentry.json',
        halt_path=tmp_path/'halt.json',archive=tmp_path/'incident',account_id='acct',
        proof=proof,kill_receipt=kill,evidence=evidence,now_ms=NOW)

def test_market_emergency_is_archived_before_retirement_and_replay_is_exact(tmp_path):
    args=fixture(tmp_path);halt=(tmp_path/'halt.json').read_bytes()
    receipt=recovery.reconcile(**args,apply=True)
    assert json.loads((tmp_path/'floor.json').read_text())=={}
    r=json.loads((tmp_path/'reentry.json').read_text())
    assert r['symbols']=={'AMD':{'blocked_until':'2026-10-26T13:30:31Z'}}
    assert r['entry_intents']=={'old':{'status':'complete'}}
    exit=r['emergency_exits']['exit']
    assert exit['reason']=='confirmed_emergency_market_exit'
    assert exit['retired_lifecycle']['accepted_order_id']=='old-stop'
    assert receipt['gross_before_fees']=='4.172'
    assert receipt['fee_finality']=='PENDING'
    assert (tmp_path/'halt.json').read_bytes()==halt
    before={p.name:p.read_bytes() for p in (tmp_path/'incident').iterdir()}
    assert recovery.reconcile(**args,apply=True)==receipt
    assert {p.name:p.read_bytes() for p in (tmp_path/'incident').iterdir()}==before

@pytest.mark.parametrize('case',['partial','stop_fill','not_flat','active','wrong_entry','wrong_account',
    'no_fill','stale','halt_off','nonfinite','future_exit'])
def test_unproven_exit_never_retires_or_writes(tmp_path,case):
    a=fixture(tmp_path);e=a['evidence'];o=e['orders']
    if case=='partial':o[2]['filled_qty']='.2'
    if case=='stop_fill':o[1]['filled_qty']='.4';o[1]['status']='filled'
    if case=='not_flat':e['positions']=[{'symbol':'CRWD','qty':'.4'}]
    if case=='active':e['open_orders']=[{'id':'pending','symbol':'CRWD'}]
    if case=='wrong_entry':o[0]['filled_qty']='.5'
    if case=='wrong_account':e['account']['id']='other'
    if case=='no_fill':e['activities']=[]
    if case=='stale':e['observed_ms']=NOW-60001
    if case=='halt_off':(tmp_path/'halt.json').write_text('{"halted":false,"account_id":"acct"}')
    if case=='nonfinite':o[2]['filled_avg_price']='NaN'
    if case=='future_exit':o[2]['filled_at']='2026-10-08T13:30:21Z'
    before=[(tmp_path/n).read_bytes() for n in ['floor.json','reentry.json','halt.json']]
    with pytest.raises(ValueError):recovery.reconcile(**a,apply=True)
    assert before==[(tmp_path/n).read_bytes() for n in ['floor.json','reentry.json','halt.json']]
    assert not a['archive'].exists()

def test_crash_after_archive_before_floor_recovers_and_keeps_other_state(tmp_path,monkeypatch):
    args=fixture(tmp_path);original=recovery._write
    def fail(path,value):
        if path==args['state_path']:raise OSError('disk write')
        return original(path,value)
    monkeypatch.setattr(recovery,'_write',fail)
    with pytest.raises(OSError):recovery.reconcile(**args,apply=True)
    assert json.loads(args['state_path'].read_text())['CRWD']['accepted_stop_floor']==275.45
    assert json.loads(args['reentry_path'].read_text())['emergency_exits']['exit']['exit_order']['type']=='market'
    monkeypatch.setattr(recovery,'_write',original)
    recovery.reconcile(**args,apply=True)
    assert json.loads(args['state_path'].read_text())=={}

def test_dry_run_has_no_state_or_archive_effect(tmp_path):
    a=fixture(tmp_path)
    result=recovery.reconcile(**a,apply=False)
    assert result['broker_writes']==0 and not a['archive'].exists()
    assert 'CRWD' in json.loads(a['state_path'].read_text())

def test_changed_archived_lineage_cannot_be_retired(tmp_path):
    a=fixture(tmp_path);recovery.reconcile(**a,apply=True)
    corrupt=copy.deepcopy(json.loads((a['archive']/'source.json').read_text()))
    corrupt['state_before']['CRWD']['qty']='.3'
    (a['archive']/'source.json').write_text(json.dumps(corrupt))
    with pytest.raises(ValueError):recovery.reconcile(**a,apply=True)

def test_archive_parent_sync_failure_prevents_ledger_retirement(tmp_path,monkeypatch):
    """A lost directory entry must not leave durable retirement without proof."""
    import os
    a=fixture(tmp_path);real_fsync=os.fsync;parent_inode=tmp_path.stat().st_ino
    def fail_parent(fd):
        if os.fstat(fd).st_ino==parent_inode:raise OSError('parent directory fsync failed')
        return real_fsync(fd)
    monkeypatch.setattr(os,'fsync',fail_parent)
    before=a['state_path'].read_bytes(),a['reentry_path'].read_bytes()
    with pytest.raises(OSError):recovery.reconcile(**a,apply=True)
    assert before==(a['state_path'].read_bytes(),a['reentry_path'].read_bytes())
