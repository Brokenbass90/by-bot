"""84 frozen geometries through existing API adapter/lifecycle/send barriers.

All captures, clocks, keys and exchange acknowledgements here are FICTIONAL.
Source sizing is recorded separately; blocked financial sizing is never turned
into an admission. Geometry-only cases use the minimum protocol test quantity.
"""
import copy,json,collections,hashlib
from pathlib import Path
from decimal import Decimal as D,ROUND_CEILING
from research_lab.pump4_account_adapter_v1 import owned_observation,checked_order_ack
from research_lab.pump4_account_owner_v1 import source_sizing
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
from research_lab.pump4_native_stop_v1 import native_mapping
from research_lab.kity_micro_physical_owner_v1 import SignedPostOnce
from scripts.rehearse_pump4_bybit_v1 import MemoryBybit
from test_pump4_bybit_sources_v1 import account,capture,group,H

KEY='NONFINANCIAL_PUMP4_NATIVE_84_FIXTURE';SECRET='NONFINANCIAL_PUMP4_NATIVE_84_SECRET';FP=hashlib.sha256(KEY.encode()).hexdigest()

def inputs(exchange,case,now,price):
    p=case['plan'];sym=p['symbol'];start=p['entry_bar_open_ms'];state=exchange.state
    x=account();x.update(account_fingerprint=FP,started_ms=now-2,completed_ms=now-1,history_start_ms=start,history_end_ms=now)
    orders=[];fills=[]
    for row in state['orders'].values():
        req=row['request'];orders.append(dict(row,**{k:req[k] for k in ('symbol','side','qty','positionIdx','reduceOnly')},updatedTime=str(now-1)))
    for i,row in enumerate(state['executions']):
        req=next(v['request'] for v in state['orders'].values() if v['orderId']==row['orderId'])
        fills.append(dict(row,symbol=sym,side=req['side'],execType='Trade',execTime=str(start+1+i),feeCurrency='USDT'))
    held=D(state['held']);positions=[];open_orders=[]
    if held:
        positions=[dict(symbol=sym,size=str(held),positionIdx=0,side='Sell',stopLoss=state['stop']['triggerPrice'])]
        open_orders=[dict(state['stop'],reduceOnly=True,closeOnTrigger=True,triggerBy='LastPrice',orderLinkId='',updatedTime=str(now-1),cumExecQty='0')]
    x['captures']['positions']=group('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),positions)
    x['captures']['symbol_position']=capture('/v5/position/list',dict(category='linear',symbol=sym),dict(category='linear',list=positions or [dict(symbol=sym,size='0',positionIdx=0,side='')],nextPageCursor=''),private=True)
    x['captures']['orders']=group('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),open_orders)
    x['captures']['fees']['body']['result']['list']=[case['fee']]
    ticker=dict(case['ticker'],symbol=sym,lastPrice=str(price),bid1Price=str(price),ask1Price=str(price),nextFundingTime=str(now+case['instrument']['fundingInterval']*60000))
    quote=capture('/v5/market/tickers',dict(category='linear'),dict(category='linear',list=[ticker]));x['captures']['quote']=quote
    x['history_windows']=[dict(start_ms=start,end_ms=now,groups=dict(
        history=group('/v5/order/history',dict(category='linear',startTime=str(start),endTime=str(now),limit='50'),orders),
        executions=group('/v5/execution/list',dict(category='linear',startTime=str(start),endTime=str(now),limit='100'),fills),
        transactions=group('/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',startTime=str(start),endTime=str(now),limit='50'),[])))]
    public=dict(instruments=dict(complete=True,pages=[capture('/v5/market/instruments-info',dict(category='linear',limit=1000),dict(category='linear',list=[case['instrument']],nextPageCursor=''))]),quote=quote)
    for value in [*x['captures'].values(),*[g for w in x['history_windows'] for g in w['groups'].values()],public['instruments']]:
        for cap in value.get('pages',[value]):
            cap.update(request_ms=now-2,receive_ms=now-1);cap['body']['time']=now-2
            if cap['signed']:cap['account_fingerprint']=FP
            cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
    return x,public,ticker

def run(root,source):
    root=Path(root);data=json.loads(Path(source).read_bytes());policy=data['policy'];rows=[]
    for index,case in enumerate(data['cases']):
        folder=root/str(index);folder.mkdir();p=case['plan'];original=json.dumps(p,sort_keys=True);now=p['entry_bar_open_ms']+20
        exchange=MemoryBybit(folder/'exchange.json','entry_reply_loss' if index%2 else 'normal');exchange.state['fixture_entry_price']=str(p['entry']);exchange.save()
        bundle,public,ticker=inputs(exchange,case,now,p['entry']);mapping=native_mapping(p,case['instrument'],ticker)
        try:
            sizing=source_sizing(p,bundle,public,policy,fingerprint=FP,now_ms=now);sizing_status='FIXTURE_SOURCE_SIZING_PASS';q=D(sizing['quantity'])
        except (ValueError,KeyError,ArithmeticError) as exc:
            sizing_status=str(exc);lots=case['instrument']['lotSizeFilter'];unit=5*D(lots['qtyStep'])
            q=(max(D(lots['minOrderQty'])/D('.4'),D(lots['minNotionalValue'])/D(str(p['entry'])))/unit).to_integral_value(rounding=ROUND_CEILING)*unit
        lots=case['instrument']['lotSizeFilter'];flow=Pump4Lifecycle(folder/'flow',p,qty=str(q),qty_step=lots['qtyStep'],min_qty=lots['minOrderQty'],min_notional=lots['minNotionalValue'],tick_size=case['instrument']['priceFilter']['tickSize'],native_stop_mapping=mapping)
        roles=[];quantities=[]
        for price in (p['entry'],p['targets'][0],p['targets'][1]):
            flow=Pump4Lifecycle.resume(folder/'flow');bundle,public,_=inputs(exchange,case,now,price)
            known=[e['verified_native_stop_id'] for e in flow.observations.read() if e['verified_native_stop_id']]
            observation=owned_observation(bundle,p,flow.requests(),first_send_ms=p['entry_bar_open_ms'],expected_fingerprint=FP,now_ms=now,known_native_ids=known)
            result=flow.advance(observation,now_ms=now);req=result['request'];assert req is not None
            roles.append(result['role']);quantities.append(D(req['qty']))
            # Crash after reservation, before any acknowledgement: never reserve a second CID.
            resumed=Pump4Lifecycle.resume(folder/'flow');assert resumed.advance(observation,now_ms=now)['status']=='RECONCILE_ONLY'
            exchange.state['fixture_exit_price']=str(price);exchange.save();sender=SignedPostOnce(KEY,SECRET,folder/'send-barriers',wire=exchange.wire)
            try:checked_order_ack(sender.post('/v5/order/create',req),req)
            except TimeoutError:pass # Memory accepted; independent reload supplies proof.
            calls=exchange.state['calls']
            try:sender.post('/v5/order/create',req)
            except ValueError:pass
            else:raise AssertionError('SEND_BARRIER_DID_NOT_BLOCK')
            assert exchange.state['calls']==calls
            exchange=MemoryBybit(exchange.path,exchange.scenario);now+=1000
        flow=Pump4Lifecycle.resume(folder/'flow');bundle,public,_=inputs(exchange,case,now,p['targets'][1]);known=[e['verified_native_stop_id'] for e in flow.observations.read() if e['verified_native_stop_id']]
        observation=owned_observation(bundle,p,flow.requests(),first_send_ms=p['entry_bar_open_ms'],expected_fingerprint=FP,now_ms=now,known_native_ids=known)
        assert flow.advance(observation,now_ms=now)['status']=='FLAT_COSTS_PENDING'
        assert roles==['ENTRY','TP1','TP2'] and quantities[1]==quantities[0]*D('.4') and quantities[2]==quantities[0]*D('.6')
        assert len(set(exchange.state['submitted_links']))==3 and D(exchange.state['held'])==0
        rows.append(dict(symbol=p['symbol'],signal_bar_open_ms=p['signal_bar_open_ms'],sizing_status=sizing_status,protocol_status='MEMORY_PROTOCOL_PASS',quantity_is_protocol_only_if_sizing_blocked=sizing_status!='FIXTURE_SOURCE_SIZING_PASS',entry_qty=str(quantities[0]),tp1_qty=str(quantities[1]),tp2_qty=str(quantities[2]),native_stop=mapping['native_stop'],reference_stop=p['stop'],unchanged_reference=original==json.dumps(flow.config['plan'],sort_keys=True),unique_fixture_wire_requests=3,final_costs_proven=False))
    return dict(schema='PUMP4_NATIVE_84_MEMORY_PROTOCOL_V1',cases=len(rows),protocol_pass=len(rows),sizing_statuses=dict(collections.Counter(r['sizing_status'] for r in rows)),rows=rows,
        actual_market_captures=False,fictional_capture_clocks_and_acknowledgements=True,financial_admission_pass_claimed=False,real_broker_requests=0,real_broker_writes=0,orders_allowed=False,money_authority=False)
