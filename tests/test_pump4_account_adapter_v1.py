import copy
import pytest
from decimal import Decimal
from test_pump4_bybit_sources_v1 import account,group,capture,NOW,H
from research_lab.pump4_account_adapter_v1 import owned_observation,time_windows,execution_feasibility
from research_lab.pump4_execution_plan_v1 import build_plan
from strategies.signals import TradeSignal

FIRST=NOW-H
FP='a'*64

def fixture():
    signal=TradeSignal(strategy='pump_fade',symbol='ZROUSDT',side='short',entry=100.,sl=101.,tp=97.9,tps=[97.9,95.8,93.],tp_fracs=[.4,.3,.3])
    plan=build_plan(signal,signal_bar_open_ms=FIRST-H,next_open_ms=FIRST,next_open=100.)
    req=dict(category='linear',symbol='ZROUSDT',side='Sell',orderType='Market',qty='10',positionIdx=0,reduceOnly=False,orderLinkId='p4-owned-entry',stopLoss='104.0',slTriggerBy='LastPrice',tpslMode='Full')
    order=dict(orderId='owned-entry',orderLinkId=req['orderLinkId'],symbol='ZROUSDT',side='Sell',qty='10',cumExecQty='10',orderStatus='Filled',reduceOnly=False,positionIdx=0,updatedTime=str(NOW-1))
    stop=dict(orderId='native-stop',orderLinkId='',symbol='ZROUSDT',side='Buy',qty='10',cumExecQty='0',orderStatus='Untriggered',reduceOnly=True,closeOnTrigger=True,positionIdx=0,stopOrderType='StopLoss',triggerPrice='104',triggerBy='LastPrice',updatedTime=str(NOW-1))
    fill=dict(execId='owned-fill',execType='Trade',execTime=str(FIRST+1),orderId='owned-entry',orderLinkId=req['orderLinkId'],symbol='ZROUSDT',side='Sell',execQty='10',execPrice='100',execFee='.55',feeCurrency='USDT')
    x=account();x['history_start_ms']=FIRST;x['history_end_ms']=NOW
    x['captures']['quote']=capture('/v5/market/tickers',dict(category='linear'),dict(category='linear',list=[dict(symbol='ZROUSDT',lastPrice='100')]))
    x['captures']['positions']=group('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),[dict(symbol='ZROUSDT',side='Sell',size='10',positionIdx=0,stopLoss='104')])
    x['captures']['orders']=group('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),[stop])
    x['history_windows']=[dict(start_ms=FIRST,end_ms=NOW,groups=dict(
        history=group('/v5/order/history',dict(category='linear',startTime=str(FIRST),endTime=str(NOW),limit='50'),[order]),
        executions=group('/v5/execution/list',dict(category='linear',startTime=str(FIRST),endTime=str(NOW),limit='100'),[fill]),
        transactions=group('/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',startTime=str(FIRST),endTime=str(NOW),limit='50'),[dict(id='funding-row',symbol='ZROUSDT',category='linear',currency='USDT',type='SETTLEMENT',transactionTime=str(NOW-1),funding='-.01')])))]
    return x,plan,[req]

def convert(x,p,requests):return owned_observation(x,p,requests,first_send_ms=FIRST,expected_fingerprint=FP,now_ms=NOW+2)

def test_real_api_shaped_sources_produce_owned_lifecycle_observation():
    x,p,requests=fixture();r=convert(x,p,requests)
    assert r['held_qty']=='10' and r['native_stop']['orderId']=='native-stop'
    assert Decimal(r['executions'][0]['execFee'])==Decimal('.55')
    assert Decimal(r['funding'][0]['amount'])==Decimal('-.01')
    assert r['orders'][0]['orderLinkId']==requests[0]['orderLinkId']
    assert r['costs_complete'] is False and r['orders_allowed'] is False
    assert r['source_provenance']=='BOUND_AUTHENTICATED_GET_CAPTURES_NOT_BROKER_SIGNATURE'

@pytest.mark.parametrize('fault',['missing_window','window_gap','foreign_same_symbol','hedge_mode','native_not_reduce','unknown_exec','fill_fee_missing','cursor_missing','conflicting_fill'])
def test_partial_unbound_or_unknown_owned_history_is_never_adopted(fault):
    x,p,r=fixture()
    if fault=='missing_window':x['history_windows']=[]
    elif fault=='window_gap':x['history_windows'][0]['start_ms']+=1
    elif fault=='foreign_same_symbol':x['captures']['orders']['pages'][0]['body']['result']['list'].append(dict(orderId='manual',orderLinkId='manual',symbol='ZROUSDT',positionIdx=0,qty='1',side='Buy',reduceOnly=False))
    elif fault=='hedge_mode':x['captures']['positions']['pages'][0]['body']['result']['list'][0]['positionIdx']=2
    elif fault=='native_not_reduce':x['captures']['orders']['pages'][0]['body']['result']['list'][0]['reduceOnly']=False
    elif fault=='unknown_exec':x['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list'][0]['execType']='BustTrade'
    elif fault=='fill_fee_missing':x['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list'][0].pop('execFee')
    elif fault=='cursor_missing':x['history_windows'][0]['groups']['transactions']['pages'][0]['body']['result'].pop('nextPageCursor')
    else:
        rows=x['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list'];rows.append(dict(rows[0],execQty='9'))
    # Seal source bytes after fixture mutation; exercise semantic source checks.
    reseal(x)
    with pytest.raises((ValueError,KeyError)):convert(x,p,r)

def reseal(x):
    import json,hashlib
    caps=list(x['captures'].values())+[g for w in x['history_windows'] for g in w['groups'].values()]
    for v in caps:
        for c in v.get('pages',[v]):c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()

def test_duplicate_identical_execution_has_one_identity_and_no_extra_quantity():
    x,p,requests=fixture();rows=x['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list'];rows.append(copy.deepcopy(rows[0]));reseal(x)
    r=convert(x,p,requests);assert len(r['executions'])==1 and r['source_duplicate_execution_rows']==1

def test_funding_sign_is_preserved_and_missing_activity_does_not_mean_final():
    x,p,requests=fixture();t=x['history_windows'][0]['groups']['transactions']['pages'][0]['body']['result'];t['list']=[];t['nextPageCursor']=None;reseal(x)
    r=convert(x,p,requests);assert r['funding']==[] and r['costs_complete'] is False

def test_seven_day_history_splits_without_a_boundary_gap():
    w=time_windows(1000,1000+7*24*H+1)
    assert w==[(1000,1000+7*24*H),(1000+7*24*H+1,1000+7*24*H+1)]
    with pytest.raises(ValueError):time_windows(2000,1000)

def sizing():
    x,p,requests=fixture()
    instrument=dict(symbol='ZROUSDT',status='Trading',quoteCoin='USDT',contractType='LinearPerpetual',lotSizeFilter=dict(qtyStep='.01',minOrderQty='.01',minNotionalValue='5',maxMktOrderQty='10000'),priceFilter=dict(tickSize='.01'),fundingInterval=240,upperFundingRate='.005',lowerFundingRate='-.005')
    ticker=dict(symbol='ZROUSDT',ask1Price='100',bid1Price='99.99',fundingRate='.00005',nextFundingTime=str(NOW+H))
    policy=dict(schema='PUMP4_TINY_PROPOSAL_ONLY_V1',risk_usdt='1',gross_usdt='30',allocation_usdt='50',reserve_usdt='20',slippage_bps='10',orders_allowed=False)
    return p,instrument,ticker,dict(symbol='ZROUSDT',takerFeeRate='.00055'),dict(available_balance='100',positions_flat=True,open_orders_empty=True,borrowed_funds=False,margin_mode='REGULAR_MARGIN'),policy

def test_tiny_feasibility_uses_risk_lots_fees_and_funding_without_authority():
    r=execution_feasibility(*sizing(),now_ms=NOW)
    assert r['status']=='FEASIBLE_PROPOSAL_ONLY' and r['orders_allowed'] is False
    assert r['native_stop']==r['reference_stop'] and r['funding_is_guaranteed_bound'] is False
    assert float(r['nominal_stop_risk_usdt'])<=1 and float(r['gross_usdt'])<=30

@pytest.mark.parametrize('fault',['stop_tick','minimum','cash','fee','foreign','zero_funding_interval'])
def test_real_admission_blocks_instead_of_changing_strategy_or_inventing_cost(fault):
    p,i,t,f,a,policy=sizing()
    if fault=='stop_tick':
        i['priceFilter']['tickSize']='200';t['lastPrice']='100'
    elif fault=='minimum':i['lotSizeFilter']['minOrderQty']='10'
    elif fault=='cash':a['available_balance']='1'
    elif fault=='fee':f.pop('takerFeeRate')
    elif fault=='foreign':a['positions_flat']=False
    else:i['fundingInterval']=0
    r=execution_feasibility(p,i,t,f,a,policy,now_ms=NOW)
    assert r['status']=='BLOCKED' and r['orders_allowed'] is False
    if fault=='stop_tick':assert r['blocker']=='PUMP4_NATIVE_STOP_INVALID_NATIVE_GEOMETRY' and r['rounding_candidates_not_selected']

def test_native_last_price_trigger_does_not_use_mark_price():
    x,p,r=fixture();x['captures']['quote']['body']['result']['list'][0]['lastPrice']='101'
    x['captures']['positions']['pages'][0]['body']['result']['list'][0]['markPrice']='99';reseal(x)
    assert convert(x,p,r)['price']=='101'

def test_api_adapter_drives_existing_lifecycle_and_restart_without_new_order(tmp_path):
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    from test_pump4_execution_lifecycle_v1 import observation
    x,p,requests=fixture()
    flow=Pump4Lifecycle(tmp_path,p,qty='10',qty_step='1',min_qty='1',min_notional='5',tick_size='.1')
    entry=flow.advance(observation(now=FIRST),now_ms=FIRST)['request']
    old=requests[0]['orderLinkId'];new=entry['orderLinkId']
    for v in [x['history_windows'][0]['groups']['history'],x['history_windows'][0]['groups']['executions']]:
        for row in v['pages'][0]['body']['result']['list']:
            if row.get('orderLinkId')==old:row['orderLinkId']=new
    reseal(x)
    o=convert(x,p,[entry])
    assert flow.advance(o,now_ms=NOW+2)['status']=='PROTECTED_WAIT'
    restored=Pump4Lifecycle.resume(tmp_path)
    assert restored.advance(o,now_ms=NOW+2)['request'] is None
    assert len(restored.requests())==1

@pytest.mark.parametrize('fault',['plan_hash','borrowed','margin','funding_time'])
def test_feasibility_diagnostic_rejects_unbound_plan_and_unknown_obligations(fault):
    p,i,t,f,a,policy=sizing()
    if fault=='plan_hash':p['hold_bars']=1
    elif fault=='borrowed':a['borrowed_funds']=True
    elif fault=='margin':a['margin_mode']='PORTFOLIO_MARGIN'
    else:t['nextFundingTime']=str(NOW-1)
    assert execution_feasibility(p,i,t,f,a,policy,now_ms=NOW)['status']=='BLOCKED'

def test_quote_movement_cannot_hide_larger_risk_to_unchanged_stop():
    p,i,t,f,a,policy=sizing();t.update(bid1Price='90',ask1Price='90.01')
    r=execution_feasibility(p,i,t,f,a,policy,now_ms=NOW)
    assert r['status']=='BLOCKED' and r['blocker']=='CAPACITY_BLOCKED'
    # A lower exchange minimum permits the reduced quantity; the old risk-based
    # quantity would still exceed R by more than 3x even on this instrument.
    i['lotSizeFilter']['minNotionalValue']='3'
    r=execution_feasibility(p,i,t,f,a,policy,now_ms=NOW)
    assert r['status']=='FEASIBLE_PROPOSAL_ONLY'
    implied=Decimal(r['quantity'])*(Decimal('104')-Decimal('90')*(1-Decimal('.001')))
    assert implied<=Decimal('1') and Decimal(r['nominal_stop_risk_usdt'])==implied
    assert r['loss_is_guaranteed_bound'] is False

def test_quote_on_wrong_side_of_static_stop_is_blocked():
    p,i,t,f,a,policy=sizing();t.update(bid1Price='105',ask1Price='105.01')
    r=execution_feasibility(p,i,t,f,a,policy,now_ms=NOW)
    assert r['status']=='BLOCKED' and r['blocker']=='STOP_WRONG_SIDE_OF_QUOTE'

@pytest.mark.parametrize('fault',['rate_limit','insufficient_balance','reduce_only','bool_code','wrong_cid','missing_order'])
def test_create_ack_is_not_a_fill_and_invalid_ack_stays_reconcile_only(fault):
    from research_lab.pump4_account_adapter_v1 import checked_order_ack
    req=dict(orderLinkId='p4-owned-entry')
    reply=dict(retCode=0,result=dict(orderId='owned-1',orderLinkId=req['orderLinkId']))
    if fault=='rate_limit':reply['retCode']=10006
    elif fault=='insufficient_balance':reply['retCode']=110007
    elif fault=='reduce_only':reply['retCode']=110017
    elif fault=='bool_code':reply['retCode']=False
    elif fault=='wrong_cid':reply['result']['orderLinkId']='other'
    else:reply['result'].pop('orderId')
    with pytest.raises(ValueError):checked_order_ack(reply,req)

def test_successful_create_reply_only_confirms_ack_identity():
    from research_lab.pump4_account_adapter_v1 import checked_order_ack
    req=dict(orderLinkId='p4-owned-entry')
    reply=dict(retCode=0,result=dict(orderId='owned-1',orderLinkId=req['orderLinkId']))
    r=checked_order_ack(reply,req)
    assert r['status']=='ACK_ONLY_RECONCILE_REQUIRED' and r['execution_confirmed'] is False

@pytest.mark.parametrize('code',[10006,110007,110017])
def test_api_error_preserves_real_send_once_barrier_across_sender_restart(tmp_path,code):
    import json
    from research_lab.kity_micro_physical_owner_v1 import SignedPostOnce
    from research_lab.kity_micro_transport_v1 import SourceError
    from research_lab.pump4_account_adapter_v1 import checked_order_ack
    calls=[]
    def wire(*args):
        calls.append(args);return 200,json.dumps(dict(retCode=code,result={})).encode()
    req=dict(category='linear',symbol='ZROUSDT',orderLinkId='p4-owned-entry')
    sender=SignedPostOnce('NONFINANCIAL_KEY','NONFINANCIAL_SECRET',tmp_path,wire=wire)
    with pytest.raises(ValueError):checked_order_ack(sender.post('/v5/order/create',req),req)
    sender=SignedPostOnce('NONFINANCIAL_KEY','NONFINANCIAL_SECRET',tmp_path,wire=wire)
    with pytest.raises(SourceError,match='SEND_ALREADY_RECORDED'):sender.post('/v5/order/create',req)
    assert len(calls)==1 and len(list(tmp_path.glob('send-*.json')))==1
