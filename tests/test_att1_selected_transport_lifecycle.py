"""Synthetic HTTPS responses through the real signed reader and recovery owner.

Temporary SQLite/journal only. This is not selected-account execution evidence.
"""
from urllib.parse import urlparse, parse_qs

from bot import att1_coordinator_adapter as a
from scripts.live_bybit_evidence_20260706 import StrictAtt1ReadClient
from research_lab.att1_lifecycle_session import LifecycleSession
import test_att1_new_broker_lifecycle_binding as fixtures
from test_att1_authenticated_transport import _Response
from test_att1_authenticated_finality import NOW, T, cash, funding, terminal


def test_real_signed_reader_reconciles_native_protection_stop_costs_and_restart(tmp_path, monkeypatch):
    phase = {'closed':False}
    rows = {}
    class HTTPS:
        def open(self, request, timeout):
            assert request.get_method()=='GET' and timeout==10
            url=request.full_url;parts=urlparse(url);params=parse_qs(parts.query)
            if parts.path=='/v5/user/query-api':
                result={'apiKey':'fixture','userID':731}
            elif parts.path=='/v5/position/list':
                result={'category':'linear','list':[] if phase['closed'] else [rows['position']],'nextPageCursor':''}
            elif parts.path=='/v5/order/realtime':
                result={'category':'linear','list':[] if phase['closed'] else [rows['stop']],'nextPageCursor':''}
            elif parts.path=='/v5/order/history':
                stop=params.get('orderId')==['native-stop']
                assert stop or params.get('orderLinkId')==[rows['entry']['orderLinkId']]
                result={'category':'linear','list':[rows['closed_stop'] if stop and phase['closed'] else
                                                  rows['stop'] if stop else rows['entry']],'nextPageCursor':''}
            elif parts.path=='/v5/execution/list':
                stop=params.get('orderId')==['native-stop']
                assert stop or params.get('orderId')==['broker-entry']
                result={'category':'linear','list':[rows['exit_fill']] if stop and phase['closed'] else
                                                  [] if stop else [rows['entry_fill']],'nextPageCursor':''}
            elif parts.path=='/v5/account/transaction-log':
                assert params.get('type')==['SETTLEMENT']
                result={'list':[cash()],'nextPageCursor':''}
            elif parts.path=='/v5/market/funding/history':result=funding()[0]['result']
            else:raise AssertionError('unexpected HTTP path '+parts.path)
            return _Response({'retCode':0,'time':(NOW if phase['closed'] else T+90)-1,'result':result},url)
    client=StrictAtt1ReadClient({'key':'fixture','secret':'synthetic-secret','base':'https://api.bybit.com'},
                               opener=HTTPS(),clock_ms=lambda:NOW if phase['closed'] else T+90)
    account=client.identity().account
    monkeypatch.setattr(fixtures,'ACCOUNT',account)
    db=tmp_path/'route.db';key=fixtures._new_reservation(db)
    session=fixtures._session(tmp_path/'session.jsonl',key,account=account)
    rows['entry']={'symbol':'BTCUSDT','orderId':'broker-entry','orderLinkId':key['order_link_id'],
        'side':'Sell','positionIdx':0,'reduceOnly':False,'qty':'0.05','cumExecQty':'0.05',
        'orderStatus':'Filled','createdTime':str(T+31),'updatedTime':str(T+52),'timeInForce':'IOC','orderType':'Market'}
    rows['entry_fill']={**fixtures._entry_fill(),'orderId':'broker-entry','orderLinkId':key['order_link_id']}
    rows['position']={'symbol':'BTCUSDT','side':'Sell','size':'0.05','positionIdx':0,'stopLoss':'110','updatedTime':str(T+45)}
    rows['stop']={'symbol':'BTCUSDT','side':'Buy','qty':'0.05','positionIdx':0,'orderId':'native-stop',
        'orderLinkId':'','cumExecQty':'0','orderStatus':'Untriggered','stopOrderType':'StopLoss','reduceOnly':True,
        'closeOnTrigger':True,'triggerPrice':'110','createdTime':str(T+41),'updatedTime':str(T+46)}
    rows['closed_stop']={**rows['stop'],'orderStatus':'Filled','cumExecQty':'0.05',
                         'updatedTime':str(T+20005),'orderType':'Market','timeInForce':'IOC'}
    rows['exit_fill']={**rows['entry_fill'],'orderId':'native-stop','orderLinkId':'','side':'Buy',
        'closedSize':'0.05','execId':'native-fill','execTime':str(T+20003),'execPrice':'112','execFee':'0.0056'}
    source_dir=tmp_path/'sources'
    first=a.reconcile_new_att1_authenticated(client,db,key,session=session,source_dir=source_dir)
    assert first['blocker']=='EXPOSURE_STILL_OPEN_ORDERS_OFF' and terminal(db) is None
    assert session.receipt['held_qty']=='1/20'
    assert any(e['kind']=='PROTECTION_ACK' for e in session.journal.read())
    phase['closed']=True
    final=a.reconcile_new_att1_authenticated(client,db,key,
        session=LifecycleSession(session.journal.path,session.profile),source_dir=source_dir)
    assert final['receipt']['lifecycle_terminal'] and final['receipt']['final_net_r']=='-6101/5000'
    assert final['orders_allowed'] is False and terminal(db)==NOW
    before=session.journal.path.read_bytes()
    again=a.reconcile_new_att1_authenticated(client,db,key,
        session=LifecycleSession(session.journal.path,session.profile),source_dir=source_dir)
    assert again['receipt']==final['receipt'] and before==session.journal.path.read_bytes()
