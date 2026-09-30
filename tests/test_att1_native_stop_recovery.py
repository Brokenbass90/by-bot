"""Native stop fixtures, not prospective or authenticated market evidence."""
import json
import pytest
from bot import att1_coordinator_adapter as a
from research_lab.att1_lifecycle_session import LifecycleSession
from research_lab.att1_lifecycle_coordinator import CoordinatorViolation
from test_att1_authenticated_entry_recovery import setup,recover,CFG,ACCOUNT,T
from test_att1_authenticated_finality import pages,finish,cash,terminal,IDENTITY,NOW


def armed(tmp):
    db,key,s,o,f=setup(tmp)
    position={'symbol':'BTCUSDT','side':'Sell','size':'0.05','positionIdx':0,'stopLoss':'110','updatedTime':str(T+45)}
    stop={'symbol':'BTCUSDT','side':'Buy','qty':'0.05','positionIdx':0,'orderId':'native-stop',
        'orderLinkId':'','orderStatus':'Untriggered','stopOrderType':'StopLoss','reduceOnly':True,
        'closeOnTrigger':True,'triggerPrice':'110','createdTime':str(T+41),'updatedTime':str(T+46)}
    recover(db,key,s,[o],[f],protection=(position,stop))
    root=tmp/'sources';root.mkdir(mode=0o700)
    src={'position':position,'stop_order':stop}
    (root/(a.digest(src)+'.json')).write_text(json.dumps(src))
    order={**stop,'orderStatus':'Filled','cumExecQty':'0.05','updatedTime':str(T+20005),'orderType':'Market','timeInForce':'IOC'}
    fill={**f,'orderId':'native-stop','orderLinkId':'','side':'Buy','closedSize':'0.05',
        'execId':'native-fill','execTime':str(T+20003),'execPrice':'112','execFee':'0.0056'}
    return db,key,s,root,order,fill


def native(db,key,s,root,o,f):
    return a.recover_new_att1_native_stop(db,key,session=s,account_config=CFG,
        broker_identity=IDENTITY,order_pages=pages([o]),execution_pages=pages([f]),
        source_dir=root,received_ms=NOW)


def test_native_stop_has_real_clocks_no_fake_price_and_costed_finality(tmp_path):
    db,key,s,root,o,f=armed(tmp_path)
    result=native(db,key,s,root,o,f)
    assert result['held_qty']=='0' and result['final_net_r'] is None
    assert terminal(db) is None
    events=s.journal.read()
    assert not any(e['kind']=='PRICE' for e in events)
    trigger=next(e for e in events if e['kind']=='BROKER_STOP_TRIGGER')
    assert trigger['exchange_ms']==int(f['execTime']) and trigger['received_ms']==NOW
    before=s.journal.path.read_bytes()
    restarted=LifecycleSession(s.journal.path,s.profile)
    assert native(db,key,restarted,root,o,f)==result
    assert before==s.journal.path.read_bytes()
    result=finish(db,key,restarted,[cash()])
    assert result['lifecycle_terminal'] and result['final_net_r']=='-6101/5000'
    assert terminal(db)==NOW


@pytest.mark.parametrize('change',[{'orderId':'foreign'},{'triggerPrice':'111'},{'closeOnTrigger':False},{'qty':'0.06'},{'createdTime':str(T+42)}])
def test_native_stop_rejects_foreign_or_changed_armed_order(tmp_path,change):
    db,key,s,root,o,f=armed(tmp_path);before=s.journal.path.read_bytes()
    with pytest.raises(a.AdapterViolation):native(db,key,s,root,{**o,**change},f)
    assert before==s.journal.path.read_bytes() and terminal(db) is None


def test_missing_original_protection_source_cannot_adopt_stop(tmp_path):
    db,key,s,root,o,f=armed(tmp_path)
    for p in root.iterdir():p.unlink()
    with pytest.raises(a.AdapterViolation,match='protection'):native(db,key,s,root,o,f)
    assert terminal(db) is None


def test_crash_after_native_fill_before_final_is_restart_safe(tmp_path,monkeypatch):
    db,key,s,root,o,f=armed(tmp_path);apply=s.apply
    def crash(e):
        if e['kind']=='EXIT_FINAL':raise RuntimeError('crash')
        return apply(e)
    monkeypatch.setattr(s,'apply',crash)
    with pytest.raises(RuntimeError,match='crash'):native(db,key,s,root,o,f)
    restarted=LifecycleSession(s.journal.path,s.profile)
    native(db,key,restarted,root,o,f)
    assert len([e for e in restarted.journal.read() if e['kind']=='EXIT_FILL'])==1
    assert terminal(db) is None


@pytest.mark.parametrize('crash_kind',[None,'BROKER_STOP_TRIGGER','EXIT_FILL','EXIT_FINAL','FUNDING_CASH','FUNDING_COVERAGE'])
def test_authenticated_path_finds_native_stop_then_cash_finality(tmp_path,monkeypatch,crash_kind):
    db,key,s,root,o,f=armed(tmp_path)
    from test_att1_new_broker_lifecycle_binding import _entry_fill
    from test_att1_authenticated_finality import funding
    class Client:
        redacted_config=CFG
        last_received_ms=NOW
        calls=[]
        def identity(self):return IDENTITY
        def pages(self,path,params):
            self.calls.append((path,params))
            if path=='/v5/order/history':
                if params.get('orderId')=='native-stop':return pages([o])
                assert params.get('orderLinkId')==key['order_link_id']
                return pages([{'symbol':'BTCUSDT','orderId':'broker-entry','orderLinkId':key['order_link_id'],
                    'side':'Sell','positionIdx':0,'reduceOnly':False,'qty':'0.05','cumExecQty':'0.05',
                    'orderStatus':'Filled','createdTime':str(T+31),'updatedTime':str(T+52),
                    'timeInForce':'IOC','orderType':'Market'}])
            if path=='/v5/execution/list':
                if params['orderId']=='native-stop':return pages([f])
                return pages([{**_entry_fill(),'orderId':'broker-entry','orderLinkId':key['order_link_id']}])
            if path=='/v5/account/transaction-log':return pages([cash()],False)
            return pages([])
        def get(self,path,params):return funding()[0]
    c=Client()
    if crash_kind:
        apply=s.apply
        def crash(e):
            if e['kind']==crash_kind:raise RuntimeError('crash before '+crash_kind)
            return apply(e)
        monkeypatch.setattr(s,'apply',crash)
        with pytest.raises(RuntimeError,match='crash before'):
            a.reconcile_new_att1_authenticated(c,db,key,session=s,source_dir=root)
        assert terminal(db) is None
        s=LifecycleSession(s.journal.path,s.profile)
    result=a.reconcile_new_att1_authenticated(c,db,key,session=s,source_dir=root)
    assert result['blocker'] is None and result['receipt']['lifecycle_terminal']
    assert result['receipt']['final_net_r']=='-6101/5000' and terminal(db)==NOW
    assert result['orders_allowed'] is False
    before=s.journal.path.read_bytes()
    result2=a.reconcile_new_att1_authenticated(c,db,key,session=LifecycleSession(s.journal.path,s.profile),source_dir=root)
    assert result2['receipt']==result['receipt'] and before==s.journal.path.read_bytes()


def test_conflicting_stop_fill_fee_after_restart_is_rejected(tmp_path):
    db,key,s,root,o,f=armed(tmp_path)
    native(db,key,s,root,o,f)
    before=s.journal.path.read_bytes()
    with pytest.raises(a.AdapterViolation,match='conflicting'):
        native(db,key,LifecycleSession(s.journal.path,s.profile),root,o,{**f,'execFee':'0.006'})
    assert before==s.journal.path.read_bytes() and terminal(db) is None


def test_native_partial_fill_keeps_slot_and_accumulates_without_duplicate(tmp_path):
    db,key,s,root,o,f=armed(tmp_path)
    partial={**f,'execQty':'0.02','closedSize':'0.02','execFee':'0.00224'}
    result=native(db,key,s,root,{**o,'orderStatus':'PartiallyFilled','cumExecQty':'0.02'},partial)
    assert result['held_qty']=='3/100' and terminal(db) is None
    rest={**f,'execId':'native-rest','execQty':'0.03','closedSize':'0.03',
          'execFee':'0.00336','execTime':str(T+20004)}
    result=a.recover_new_att1_native_stop(db,key,session=LifecycleSession(s.journal.path,s.profile),
        account_config=CFG,broker_identity=IDENTITY,order_pages=pages([o]),
        execution_pages=pages([partial,rest]),source_dir=root,received_ms=NOW)
    assert result['held_qty']=='0' and result['final_net_r'] is None and terminal(db) is None
    assert len([e for e in s.journal.read() if e['kind']=='EXIT_FILL'])==2
