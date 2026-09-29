"""Synthetic broker evidence. Never counted as prospective trades."""
import sqlite3
from copy import deepcopy
import pytest
from bot import att1_coordinator_adapter as a
from research_lab.att1_lifecycle_session import LifecycleSession
from research_lab.att1_lifecycle_coordinator import CoordinatorViolation
from test_att1_authenticated_entry_recovery import setup, recover, page, CFG, ACCOUNT
from test_att1_lifecycle_coordinator import ev, T

NOW=T+90000
IDENTITY=a.ValidatedOldAtt1BrokerIdentity(ACCOUNT,CFG['base'],a.hashlib.sha256(b'fixture').hexdigest(),NOW-10)

def closed(tmp):
    db,key,s,o,f=setup(tmp)
    recover(db,key,s,[o],[f])
    s.apply(ev('PROTECTION_ACK',100,qty='0.05',stop='110'))
    s.apply(ev('PRICE',20000,bid='111',ask='112'))
    xid=s.receipt['pending_exit']['exit_order_id']
    link=a.att1_exit_order_link_id(key,xid)
    row={**f,'orderId':'exit-order','orderLinkId':link,'execId':'exit-fill',
        'side':'Buy','execQty':'0.05','execPrice':'112','closedSize':'0.05',
        'execFee':'0.0056','execTime':str(T+20003)}
    order={'symbol':'BTCUSDT','orderId':'exit-order','orderLinkId':link,'side':'Buy',
        'positionIdx':0,'reduceOnly':True,'qty':'0.05','cumExecQty':'0.05',
        'orderStatus':'Filled','createdTime':str(T+20002),'updatedTime':str(T+20005),
        'timeInForce':'IOC','orderType':'Market'}
    identity=a.ValidatedOldAtt1BrokerIdentity(ACCOUNT,CFG['base'],IDENTITY.credential_binding_sha256,T+20006)
    args=dict(session=s,account_config=CFG,broker_identity=identity,
        order_pages=[{**page([order])[0],'time':T+20006}],
        execution_pages=[{**page([row])[0],'time':T+20006}],received_ms=T+20007)
    a.recover_new_att1_broker_exit(db,key,**args)
    assert terminal(db) is None
    before=s.journal.path.read_bytes()
    args['session']=LifecycleSession(s.journal.path,s.profile)
    a.recover_new_att1_broker_exit(db,key,**args)
    assert before==s.journal.path.read_bytes()
    return db,key,s

def cash():
    return {'id':'funding','symbol':'BTCUSDT','category':'linear','currency':'USDT',
        'type':'SETTLEMENT','side':'Sell','qty':'0.05','size':'-0.05','funding':'0.0005',
        'cashFlow':'0','fee':'0','change':'0.0005','extraFees':'','transSubType':'',
        'bonusChange':'','transactionTime':str(T+10000)}

def pages(rows,category=True):
    p=page(rows)[0];p['time']=NOW-1
    if not category:
        p['result'].pop('category')
        if not rows:p['result']['nextPageCursor']=None
    return [p]

def funding():
    return [{'retCode':0,'time':NOW-1,'result':{'category':'linear','list':[
        {'symbol':'BTCUSDT','fundingRateTimestamp':str(T+10000),'fundingRate':'0.0001'}]}}]

def finish(db,key,s,cash_rows,orders=None):
    return a.reconcile_new_att1_broker_finality(db,key,session=s,account_config=CFG,
        broker_identity=IDENTITY,transaction_pages=pages(cash_rows,False),
        funding_pages=funding(),coverage_start_ms=T-5000,coverage_end_ms=T+25003,
        position_pages=pages([]),order_pages=pages(orders or []),received_ms=NOW)

def terminal(db):
    with sqlite3.connect(db) as c:return c.execute("SELECT terminal_at_ms FROM att1_decisions WHERE owner='NEW'").fetchone()[0]

def test_delayed_cash_keeps_reservation_then_finality_is_restart_idempotent(tmp_path):
    db,key,s=closed(tmp_path)
    pending=finish(db,key,s,[])
    assert pending['final_net_r'] is None and terminal(db) is None
    result=finish(db,key,s,[cash()])
    assert result['lifecycle_terminal'] is True and terminal(db)==NOW
    before=s.journal.path.read_bytes()
    reopened=LifecycleSession(s.journal.path,s.profile)
    assert finish(db,key,reopened,[cash()])==result
    assert before==s.journal.path.read_bytes()


def test_cash_complete_but_active_order_retains_slot(tmp_path):
    db,key,s=closed(tmp_path)
    order={'orderId':'unknown','symbol':'BTCUSDT','side':'Buy','qty':'0.01','cumExecQty':'0','orderStatus':'New'}
    with pytest.raises(a.AdapterViolation,match='flat'):
        finish(db,key,s,[cash()],[order])
    assert terminal(db) is None


def test_funding_mismatch_never_releases(tmp_path):
    db,key,s=closed(tmp_path)
    with pytest.raises(CoordinatorViolation,match="historical held qty"):finish(db,key,s,[{**cash(),'qty':'0.04','size':'-0.04'}])
    assert terminal(db) is None


def test_signed_caller_path_collects_cash_schedule_and_fresh_flat_before_release(tmp_path):
    db,key,s=closed(tmp_path)
    class Client:
        redacted_config=CFG
        last_received_ms=NOW
        calls=[]
        def identity(self):return IDENTITY
        def pages(self,path,params):
            self.calls.append((path,params))
            if path=='/v5/order/history':
                return pages([{'symbol':'BTCUSDT','orderId':'broker-entry','orderLinkId':key['order_link_id'],
                    'side':'Sell','positionIdx':0,'reduceOnly':False,'qty':'0.05','cumExecQty':'0.05',
                    'orderStatus':'Filled','createdTime':str(T+31),'updatedTime':str(T+52),
                    'timeInForce':'IOC','orderType':'Market'}])
            if path=='/v5/execution/list':
                from test_att1_new_broker_lifecycle_binding import _entry_fill
                return pages([{**_entry_fill(),'orderId':'broker-entry','orderLinkId':key['order_link_id']}])
            if path=='/v5/account/transaction-log':
                assert params['type']=='SETTLEMENT' and params['startTime']==T+40-5000
                return pages([cash()],False)
            return pages([])
        def get(self,path,params):
            assert path=='/v5/market/funding/history'
            self.calls.append((path,params))
            return funding()[0]
    c=Client()
    result=a.reconcile_new_att1_authenticated(c,db,key,session=s,source_dir=tmp_path/'private')
    assert result['blocker'] is None and result['receipt']['lifecycle_terminal']
    assert result['orders_allowed'] is False and terminal(db)==NOW
    assert len([p for p,_ in c.calls if p=='/v5/order/realtime'])==2
    before=s.journal.path.read_bytes()
    again=a.reconcile_new_att1_authenticated(c,db,key,
        session=LifecycleSession(s.journal.path,s.profile),source_dir=tmp_path/'private')
    assert again['receipt']==result['receipt'] and before==s.journal.path.read_bytes()


def test_native_stop_without_coordinator_exit_is_not_silently_adopted(tmp_path):
    db,key,s,o,f=setup(tmp_path);recover(db,key,s,[o],[f])
    s.apply(ev('PROTECTION_ACK',100,qty='0.05',stop='110'))
    native={'symbol':'BTCUSDT','orderId':'native-stop','orderLinkId':'','side':'Buy',
        'positionIdx':0,'reduceOnly':True,'qty':'0.05','cumExecQty':'0.05','orderStatus':'Filled',
        'createdTime':str(T+100),'updatedTime':str(T+20005),'timeInForce':'IOC','orderType':'Market'}
    with pytest.raises(a.AdapterViolation,match='foreign exit link'):
        a.recover_new_att1_broker_exit(db,key,session=s,account_config=CFG,broker_identity=IDENTITY,
            order_pages=pages([native]),execution_pages=pages([]),received_ms=NOW)
    assert terminal(db) is None and s.receipt['held_qty']=='1/20'
