"""Synthetic venue, actual concrete owner/transport/journal/supervisor path."""
import json,time
from decimal import Decimal as D
from pathlib import Path
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SYMBOLS
from research_lab.kity_micro_physical_owner_v1 import AccountLease,PhysicalOwner,SignedPostOnce,EvidenceReader
from research_lab.kity_execution_micro_runtime_v1 import MicroJournal,prepare_micro_plan
from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
from research_lab.kity_micro_supervisor_v1 import Supervisor
from test_kity_micro_runtime_v1 import dossier
from test_kity_micro_integration_v3 import V3


def test_concrete_owner_all_ten_native_restart_deadline_and_actual_cash_path(tmp_path,monkeypatch,latency=None):
    import research_lab.kity_micro_supervisor_v1 as sup
    import urllib.parse
    clock=[1792050000000];funding_next=clock[0]+86400000;now=lambda:clock[0];orders={};execs=[];cash=[];positions={};calls=[]
    if latency is not None:latency.bind(clock)
    d=dossier()
    for l in d['profiles'][0]['legs']:
        l['draft_entry'].update(price='1.0001' if l['side']=='Buy' else '1',stopLoss='.9' if l['side']=='Buy' else '1.1',
            slTriggerBy='LastPrice',slOrderType='Market',tpslMode='Full')
    p=prepare_micro_plan(d,V3)
    spec={s:dict(next_funding_ms=str(funding_next),funding_interval_minutes=480,funding_upper='.01',funding_lower='-.01') for s in SYMBOLS}
    def wire(method,url,headers,data,timeout):
        path=urllib.parse.urlparse(url).path;params=dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query));rows=[]
        if latency is not None:latency.network(method,path)
        if method=='POST':
            req=json.loads(data);calls.append((path,req));sym=req['symbol'];identifier='id-'+str(len(calls))
            if path.endswith('/cancel'):
                orders[req['orderId']].update(orderStatus='Deactivated',qty='0');result=dict(orderId=req['orderId'])
            else:
                q=D(req['qty']);price=D('1.0001' if req['side']=='Buy' else '1');xid='exec-'+identifier
                order=dict(req,orderId=identifier,orderStatus='Filled',cumExecQty=str(q),createdTime=str(now()))
                orders[identifier]=order
                execs.append(dict(order,execType='Trade',execTime=str(now()),execId=xid,execQty=str(q),execPrice=str(price),execFee='.001'))
                prior=positions.get(sym)
                if req.get('reduceOnly'):
                    pnl=(price-prior['price'])*q*(1 if prior['side']=='Buy' else -1);positions.pop(sym)
                    for o in orders.values():
                        if o['symbol']==sym and o.get('stopOrderType')=='StopLoss':o.update(orderStatus='Deactivated',qty='0')
                else:
                    pnl=D(0);positions[sym]=dict(side=req['side'],qty=q,price=price)
                    orders['sl-'+identifier]=dict(symbol=sym,side='Sell' if req['side']=='Buy' else 'Buy',qty=str(q),
                       orderId='sl-'+identifier,orderLinkId='',orderType='Market',positionIdx=0,reduceOnly=True,
                       orderStatus='Untriggered',cumExecQty='0',stopOrderType='StopLoss',triggerPrice=req['stopLoss'],createdTime=str(now()))
                cash.append(dict(id='cash-'+identifier,type='TRADE',tradeId=xid,orderId=identifier,symbol=sym,
                    currency='USDT',category='linear',qty=str(q),fee='.001',change=str(pnl-D('.001'))))
                result=dict(orderId=identifier,orderLinkId=req['orderLinkId'])
        elif path=='/v5/user/query-api':result=dict(readOnly=0,permissions=dict(ContractTrade=['Order','Position']))
        elif path=='/v5/account/info':result=dict(marginMode='REGULAR_MARGIN',unifiedMarginStatus=5)
        elif path=='/v5/account/wallet-balance':result=dict(list=[dict(totalAvailableBalance='1000')])
        elif path=='/v5/market/instruments-info':result=dict(list=[dict(symbol=params['symbol'],contractType='LinearPerpetual',status='Trading',quoteCoin='USDT',settleCoin='USDT',unifiedMarginTrade=True,fundingInterval=480,lotSizeFilter=dict(minOrderQty='.001',maxOrderQty='10000',minNotionalValue='.1',qtyStep='.001'),priceFilter=dict(tickSize='.0001'))])
        elif path=='/v5/account/fee-rate':result=dict(list=[dict(symbol=s,takerFeeRate='.001') for s in ([params['symbol']] if 'symbol' in params else SYMBOLS)])
        elif path=='/v5/market/tickers':result=dict(list=[dict(symbol=params['symbol'],lastPrice='1',nextFundingTime=str(funding_next))])
        elif path=='/v5/market/orderbook':result=dict(s=params['symbol'],b=[['1','1000']],a=[['1.0001','1000']],cts=now())
        elif path=='/v5/position/list':
            symbols=[params['symbol']] if params.get('symbol') else positions
            result=dict(list=[dict(symbol=s,side=positions[s]['side'] if s in positions else '',size=str(positions[s]['qty']) if s in positions else '0',positionIdx=0,isReduceOnly=False) for s in symbols],nextPageCursor='')
        elif path in ('/v5/order/history','/v5/order/realtime','/v5/execution/list'):
            rows=execs if path.endswith('/execution/list') else list(orders.values())
            rows=[r for r in rows if (not params.get('symbol') or r['symbol']==params['symbol']) and (not params.get('orderId') or r['orderId']==params['orderId']) and (not params.get('orderLinkId') or r.get('orderLinkId')==params['orderLinkId'])]
            if path.endswith('/realtime'):rows=[r for r in rows if r['orderStatus'] in ('Untriggered','New')]
            result=dict(list=rows,nextPageCursor='')
        elif path=='/v5/account/transaction-log':result=dict(list=cash,nextPageCursor='')
        else:raise AssertionError(path)
        return 200,json.dumps(dict(retCode=0,result=result,time=now())).encode()
    getwire=latency.get_wire(wire) if latency is not None else wire
    reader=EvidenceReader(BybitReadTransport('test-key','test-secret',wire=getwire,clock=now),tmp_path/'raw')
    if latency is not None:reader.all_symbol_fee_snapshot=True
    j=MicroJournal(tmp_path/'j.sqlite',p);lease=AccountLease(tmp_path/'lock');writer=SignedPostOnce('test-key','test-secret',tmp_path/'wire',wire=wire,clock=now)
    owner=PhysicalOwner(j,reader,lease,tmp_path/'go',platform_check=latency.custody if latency is not None else lambda:None,post=writer.post,clock=now)
    owner.accept_go('GO KITY_EXECUTION_MICRO_LIVE '+p['plan_id'])
    s=Supervisor.__new__(Supervisor);s.journal=j;s.reader=reader;s.owner=owner;s.spec=spec
    s.bridge=MicroAccountBridge(j,reader,owner=owner,clock=now)
    monkeypatch.setattr(sup,'now_ms',now)
    # nextFundingTime is a fixed schedule, not sliding with our synthetic clock.
    for _ in range(23):
        before=j.snapshot()
        errors=s.cycle()
        assert not errors,errors
        if latency is not None:latency.between_cycles(before,j.snapshot())
    assert len([r for _,r in calls if r.get('reduceOnly') is False])==10
    assert len(positions)==10 and len(j.snapshot()['entries'])==10
    if latency is not None:latency.entry_complete(j.snapshot())
    clock[0]=j.snapshot()['deadline_ms']
    # Fixed next settlement remains beyond this 30min experiment.
    # Manual restart transfers no entry authority and does not reset deadline.
    sup.recover_without_reentry(j,now())
    for _ in range(30):
        s.cycle()
        if j.snapshot()['phase']=='TERMINAL':break
    assert j.snapshot()['phase']=='TERMINAL',j.snapshot()
    assert not positions
    assert len([r for _,r in calls if r.get('reduceOnly') is False])==10
    assert D(j.snapshot()['terminal_net_usdt'])==D('-.0210')
