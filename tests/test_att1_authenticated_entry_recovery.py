"""Signed transport is tested separately; these are synthetic recovery fixtures."""
import sqlite3
from copy import deepcopy
import pytest
from bot import att1_coordinator_adapter as a
from research_lab.att1_lifecycle_session import LifecycleSession
from test_att1_new_broker_lifecycle_binding import _new_reservation, _session, _entry_fill, ACCOUNT, T

CFG={'base':'https://api.bybit.com','key':'fixture'}
IDENTITY=a.ValidatedOldAtt1BrokerIdentity(ACCOUNT,CFG['base'],a.hashlib.sha256(b'fixture').hexdigest(),T+80)

def page(rows):
    return [{'retCode':0,'time':T+80,'result':{'category':'linear','list':rows,'nextPageCursor':''}}]

def setup(tmp):
    db=tmp/'t.db'; key=_new_reservation(db); s=_session(tmp/'s.jsonl',key)
    order={'symbol':'BTCUSDT','orderId':'broker-entry','orderLinkId':key['order_link_id'],
           'side':'Sell','positionIdx':0,'reduceOnly':False,'qty':'0.05',
           'orderStatus':'Filled','cumExecQty':'0.05','createdTime':str(T+31),
           'updatedTime':str(T+52),'timeInForce':'IOC','orderType':'Market'}
    fill={**_entry_fill(),'orderId':order['orderId'],'orderLinkId':key['order_link_id']}
    return db,key,s,order,fill

def recover(db,key,s,orders,fills,**kw):
    return a.recover_new_att1_broker_entry(db,key,session=s,account_config=CFG,
        broker_identity=kw.pop('identity',IDENTITY),order_pages=page(orders),
        execution_pages=page(fills),received_ms=T+90,**kw)

def test_lost_response_binds_exact_order_and_recovers_fill_once_after_restart(tmp_path):
    db,key,s,o,f=setup(tmp_path)
    result=recover(db,key,s,[o],[f])
    assert result['dispatch']['status']=='EXISTING_ORDER_RECOVERED'
    assert result['orders_allowed'] is False
    assert s.receipt['held_qty']=='1/20'
    assert s.receipt['accounting']['known_fee_total']=='1/200'
    before=s.journal.path.read_bytes()
    resumed=LifecycleSession(s.journal.path,s.profile)
    recover(db,key,resumed,[o],[f])
    assert resumed.receipt==s.receipt and before==s.journal.path.read_bytes()
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT broker_order_id,terminal_at_ms FROM att1_decisions WHERE owner='NEW'").fetchone()==('broker-entry',None)

def test_absent_order_does_not_create_ack_or_release_or_retry_send(tmp_path):
    db,key,s,_,_=setup(tmp_path); before=s.journal.path.read_bytes()
    result=recover(db,key,s,[],[])
    assert result['dispatch']['status']=='SEND_DISABLED_UNRESOLVED'
    assert s.journal.path.read_bytes()==before

@pytest.mark.parametrize('field,value',[('orderLinkId','foreign'),('side','Buy'),('reduceOnly',True),('qty','0.06'),('timeInForce','GTC')])
def test_foreign_or_wrong_order_cannot_bind(tmp_path,field,value):
    db,key,s,o,f=setup(tmp_path); o[field]=value
    with pytest.raises(a.AdapterViolation):recover(db,key,s,[o],[f])
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT broker_order_id FROM att1_decisions WHERE owner='NEW'").fetchone()==(None,)

def test_missing_fill_is_rejected_before_any_journal_or_db_mutation(tmp_path):
    db,key,s,o,_=setup(tmp_path); before=s.journal.path.read_bytes()
    with pytest.raises(a.AdapterViolation,match='executions'):recover(db,key,s,[o],[])
    assert s.journal.path.read_bytes()==before
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT broker_order_id FROM att1_decisions WHERE owner='NEW'").fetchone()==(None,)

def test_wrong_account_rejected(tmp_path):
    db,key,s,o,f=setup(tmp_path)
    identity=a.ValidatedOldAtt1BrokerIdentity('uid:'+'b'*64,CFG['base'],IDENTITY.credential_binding_sha256,T+80)
    with pytest.raises(a.AdapterViolation,match='account'):recover(db,key,s,[o],[f],identity=identity)

def test_duplicate_execution_in_pages_fails_before_writes(tmp_path):
    db,key,s,o,f=setup(tmp_path)
    with pytest.raises(a.AdapterViolation,match='duplicate'):recover(db,key,s,[o],[f,f])

def test_fill_durable_before_crash_recovers_order_finality(tmp_path,monkeypatch):
    db,key,s,o,f=setup(tmp_path)
    apply=s.apply
    def crash_on_final(event):
        if event['kind']=='ENTRY_FINAL':raise RuntimeError('crash before finality')
        return apply(event)
    monkeypatch.setattr(s,'apply',crash_on_final)
    with pytest.raises(RuntimeError,match='crash before'):
        recover(db,key,s,[o],[f])
    restarted=LifecycleSession(s.journal.path,s.profile)
    recover(db,key,restarted,[o],[f])
    assert restarted.receipt['entry_status']=='FILLED'
    assert len([e for e in restarted.journal.read() if e['kind']=='ENTRY_FILL'])==1


def test_collector_connects_signed_identity_lookup_and_raw_receipts(tmp_path):
    db,key,s,o,f=setup(tmp_path)
    class Client:
        redacted_config=CFG
        last_received_ms=T+90
        calls=[]
        def identity(self):return IDENTITY
        def pages(self,path,params):
            self.calls.append((path,params))
            if path=='/v5/order/history':
                assert params['orderLinkId']==key['order_link_id']
                return page([o])
            if path=='/v5/execution/list':
                assert params['orderId']==o['orderId']
                return page([f])
            return page([])
    c=Client()
    result=a.collect_new_att1_entry_recovery(c,db,key,session=s,source_dir=tmp_path/'private')
    assert result['receipt']['held_qty']=='1/20'
    assert result['blocker']=='PROTECTION_AND_EXIT_FUNDING_BINDING_PENDING'
    assert (tmp_path/'private'/(a.digest(f)+'.json')).exists()
    assert all(path.startswith('/v5/') for path,_ in c.calls)
    assert result['authenticated_account']==ACCOUNT


def test_existing_bound_order_absence_is_unresolved_not_finality(tmp_path):
    db,key,s,o,f=setup(tmp_path); recover(db,key,s,[o],[f])
    before=s.journal.path.read_bytes(); result=recover(db,key,s,[],[])
    assert result['dispatch']['status']=='SEND_DISABLED_UNRESOLVED'
    assert s.journal.path.read_bytes()==before


def test_recovery_orders_protection_before_terminal_ack_without_changing_clocks(tmp_path):
    db,key,s,o,f=setup(tmp_path)
    position={'symbol':'BTCUSDT','side':'Sell','size':'0.05','positionIdx':0,'stopLoss':'110','updatedTime':str(T+45)}
    stop={'symbol':'BTCUSDT','side':'Buy','qty':'0.05','positionIdx':0,'orderId':'stop-id',
          'orderStatus':'Untriggered','stopOrderType':'StopLoss','reduceOnly':True,
          'closeOnTrigger':True,'triggerPrice':'110','updatedTime':str(T+46)}
    result=recover(db,key,s,[o],[f],protection=(position,stop))
    assert result['receipt']['protected_qty']=='1/20'
    assert result['receipt']['incidents']==[]
    before=s.journal.path.read_bytes()
    recover(db,key,s,[o],[f],protection=(position,stop))
    assert before==s.journal.path.read_bytes()


def test_invalid_new_status_with_fills_rejected(tmp_path):
    db,key,s,o,f=setup(tmp_path); o['orderStatus']='New'
    with pytest.raises(a.AdapterViolation,match='status'):recover(db,key,s,[o],[f])
