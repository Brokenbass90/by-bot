from copy import deepcopy
import hashlib,json
import pytest
from research_lab.kity_weekly_bybit_adapter_v1 import observe,ack_only
from research_lab.kity_weekly_rehearsal_v1 import make_profile

NOW=1792800000000
FP='f'*64


def cap(endpoint,params,rows,*,cursor=''):
    body={'retCode':0,'retMsg':'OK','result':{'list':rows,'nextPageCursor':cursor},'time':NOW}
    raw=json.dumps(body)
    return dict(method='GET',endpoint=endpoint,params=params,signed=True,account_fingerprint=FP,
                http_status=200,request_ms=NOW-100,receive_ms=NOW,body=body,raw=raw,
                raw_sha256=hashlib.sha256(raw.encode()).hexdigest())


def fixture():
    legs=[dict(symbol=f'{side}{i}USDT',side=1 if side=='L' else -1,qty='1',entry_reference_price='100') for side in ('L','S') for i in range(5)]
    p=make_profile('2026-10-22',legs,dict(signal='a'*64,entry='b'*64,c2='c'*64),funding_intervals={x['symbol']:480 for x in legs})
    requests=[];orders=[];fills=[];positions=[]
    for i,l in enumerate(legs):
        side='Buy' if l['side']==1 else 'Sell';link='kw-entry-'+str(i);oid='order-'+str(i)
        r=dict(category='linear',symbol=l['symbol'],side=side,qty='1',orderType='Limit',price='100',timeInForce='GTC',reduceOnly=False,positionIdx=0,orderLinkId=link)
        requests.append(dict(role='ENTRY',request=r,order_id=oid,first_send_ms=NOW-1000))
        orders.append(dict(r,orderId=oid,orderStatus='Filled',cumExecQty='1',updatedTime=str(NOW)))
        fills.append(dict(orderId=oid,orderLinkId=link,symbol=l['symbol'],side=side,execType='Trade',execId='trade-'+str(i),
                          execQty='1',execPrice='100',execFee='.06',feeCurrency='USDT',execTime=str(NOW)))
        positions.append(dict(symbol=l['symbol'],positionIdx=0,side=side,size='1',stopLoss='90' if l['side']==1 else '110'))
    groups={}
    for name,path,params,rows in [
        ('positions','/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),positions),
        ('orders','/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),[]),
    ]:groups[name]=dict(complete=True,pages=[cap(path,params,rows)])
    history=[]
    for name,path,limit,extra,rows in [('history','/v5/order/history','50',{},orders),('executions','/v5/execution/list','100',{},fills),
         ('transactions','/v5/account/transaction-log','50',dict(accountType='UNIFIED',currency='USDT'),[])]:
        params=dict(category='linear',startTime=str(NOW-1000),endTime=str(NOW),limit=limit,**extra)
        history.append((name,dict(complete=True,pages=[cap(path,params,rows)])))
    b=dict(schema='KITY_WEEKLY_BYBIT_GET_V1',origin='SYNTHETIC_API_FORMAT_FIXTURE',account_fingerprint=FP,
           history_start_ms=NOW-1000,history_end_ms=NOW,captures=groups,
           history_windows=[dict(start_ms=NOW-1000,end_ms=NOW,groups=dict(history))])
    return p,requests,b


def reseal(b):
    for group in [*b['captures'].values(),*[g for w in b['history_windows'] for g in w['groups'].values()]]:
        for c in group['pages']:
            c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()


def call(p,r,b):return observe(p,r,b,expected_fingerprint=FP,now_ms=NOW,native_bindings=[])


def test_ten_leg_execution_facts_no_money_no_finality():
    p,r,b=fixture();v=call(p,r,b)
    assert len(v['executions'])==10 and len(v['positions'])==10
    assert v['orders_allowed'] is False and v['costs_complete'] is False
    assert v['entry_ready'] is False and v['protection_status']=='UNKNOWN_UNAPPROVED_STOP_POLICY'
    assert v['source_origin']=='SYNTHETIC_API_FORMAT_FIXTURE'


def test_ack_not_fill_and_error_never_retry():
    p,r,b=fixture();req=r[0]['request']
    v=ack_only({'retCode':0,'result':{'orderId':'o','orderLinkId':req['orderLinkId']}},req)
    assert not v['execution_confirmed']
    with pytest.raises(ValueError):ack_only({'retCode':10006,'result':{}},req)


@pytest.mark.parametrize('bad',['hash','cursor','account','foreign_position','foreign_fill','side','position_mode','overfill'])
def test_bad_material_identity_or_evidence_is_rejected(bad):
    p,r,b=fixture()
    if bad=='hash':b['captures']['positions']['pages'][0]['raw_sha256']='0'*64
    elif bad=='cursor':b['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['nextPageCursor']='missing'
    elif bad=='account':b['account_fingerprint']='a'*64
    elif bad=='foreign_position':b['captures']['positions']['pages'][0]['body']['result']['list'].append(dict(symbol='FOREIGNUSDT',positionIdx=0,side='Buy',size='1'))
    else:
        row=b['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list'][0]
        if bad=='foreign_fill':row['orderLinkId']='other'
        elif bad=='side':row['side']='Sell'
        elif bad=='position_mode':b['captures']['positions']['pages'][0]['body']['result']['list'][0]['positionIdx']=1
        else:row['execQty']='2'
    if bad!='hash':reseal(b)
    with pytest.raises((ValueError,KeyError)):call(p,r,b)


def test_signed_funding_and_duplicate_fill_preserved():
    p,r,b=fixture();g=b['history_windows'][0]['groups']
    g['executions']['pages'][0]['body']['result']['list'].append(deepcopy(g['executions']['pages'][0]['body']['result']['list'][0]))
    g['transactions']['pages'][0]['body']['result']['list']=[dict(id='fund-1',symbol='L0USDT',type='SETTLEMENT',category='linear',
        currency='USDT',transactionTime=str(NOW),funding='-.01',fee='0',cashFlow='0',change='-.01',qty='1',tradePrice='100',feeRate='.0001',side='Buy')]
    reseal(b);v=call(p,r,b)
    assert len(v['executions'])==10 and v['funding'][0]['cash_usdt']=='-0.01'


def test_unbound_native_stop_is_not_adopted():
    p,r,b=fixture();b['captures']['orders']['pages'][0]['body']['result']['list']=[dict(symbol='L0USDT',orderId='unowned-stop',orderLinkId='',
         side='Sell',qty='1',positionIdx=0,reduceOnly=True,closeOnTrigger=True,stopOrderType='StopLoss',orderStatus='Untriggered',triggerPrice='90',triggerBy='LastPrice',orderType='Market')]
    reseal(b)
    with pytest.raises(ValueError,match='UNBOUND_NATIVE'):call(p,r,b)


def native_rows(p,r):
    from research_lab.alpaca_dynamic_v1 import digest
    bindings=[];rows=[]
    for i,l in enumerate(p['legs']):
        oid='stop-'+str(i);price='90' if l['side']==1 else '110'
        bindings.append(dict(order_id=oid,symbol=l['symbol'],trigger_price=price,profile_sha256=digest(p),contract='CONTINGENCY_FIXTURE_ONLY'))
        rows.append(dict(orderId=oid,orderLinkId='',symbol=l['symbol'],side='Sell' if l['side']==1 else 'Buy',qty='1',
                         reduceOnly=True,closeOnTrigger=True,positionIdx=0,triggerBy='LastPrice',triggerPrice=price,
                         orderType='Market',stopOrderType='StopLoss',orderStatus='Untriggered',cumExecQty='0'))
    return bindings,rows


def test_full_native_coverage_is_technical_only_and_qty_drift_detected():
    p,r,b=fixture();bindings,rows=native_rows(p,r);b['captures']['orders']['pages'][0]['body']['result']['list']=rows;reseal(b)
    v=observe(p,r,b,expected_fingerprint=FP,now_ms=NOW,native_bindings=bindings)
    assert all(v['technical_native_coverage'].values()) and v['entry_ready'] is False
    rows[0]['qty']='.5';reseal(b)
    v=observe(p,r,b,expected_fingerprint=FP,now_ms=NOW,native_bindings=bindings)
    assert v['technical_native_coverage']['L0USDT'] is False


def test_cid_cannot_resolve_to_two_broker_orders_even_if_qty_small():
    p,r,b=fixture();r[0]['order_id']=None
    b['history_windows'][0]['groups']['history']['pages'][0]['body']['result']['list']=[]
    fills=b['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list']
    fills[0]['execQty']='.5';fills.append(dict(fills[0],execId='different',orderId='second-order'))
    reseal(b)
    with pytest.raises(ValueError,match='CID_MULTIPLE'):call(p,r,b)


def test_cli_raw_format_roundtrip_has_no_money_authority(tmp_path):
    import subprocess,sys
    from pathlib import Path
    p,_,_=fixture()
    signal={'instrumenty':{l['symbol']:{'step':'.1','min_qty':'.1','min_notional':'5'} for l in p['legs']}}
    raw=json.dumps(signal).encode();sp=tmp_path/'signal.json';sp.write_bytes(raw)
    p['source_pins']['signal']=hashlib.sha256(raw).hexdigest()
    raw=json.dumps(p).encode();pp=tmp_path/'profile.json';pp.write_bytes(raw)
    command=[sys.executable,'-B',str(Path(__file__).parents[1]/'scripts/rehearse_kity_bybit_orders_off_v1.py'),
             '--profile',str(pp),'--profile-sha256',hashlib.sha256(raw).hexdigest(),'--signal',str(sp),'--root',str(tmp_path/'run')]
    result=subprocess.run(command,capture_output=True,text=True,check=True)
    v=json.loads(result.stdout)
    assert v['status']=='ORDERS_OFF_API_FORMAT_REHEARSAL_PASS' and len(v['raw_snapshots'])==5
    assert v['broker_writes']==0 and not v['actual_exchange_acceptance_proven']
    assert not v['live_entry_ready'] and v['final']['terminal_complete']
    assert v['raw_snapshots'][-1]['technical_native_full'] is None
    assert subprocess.run(command,capture_output=True).returncode!=0


def test_late_observation_does_not_hide_early_execution():
    from research_lab.kity_weekly_rehearsal_v1 import WeeklyRehearsal
    import tempfile
    from pathlib import Path
    p,_,_=fixture();start=p['entry_reference_ms'];due=p['exit_reference_ms']
    with tempfile.TemporaryDirectory() as directory:
        w=WeeklyRehearsal(Path(directory).resolve()/'model',p)
        w.append(dict(event_id='e',kind='MODEL_ENTRY_FILL',symbol='L0USDT',observed_ms=start+1,source_execution_ms=start,
                      exec_id='e',qty='1',price='100',fee_usdt='.06'))
        with pytest.raises(ValueError,match='EARLY_STRATEGY_EXIT'):
            w.append(dict(event_id='x',kind='MODEL_EXIT_FILL',symbol='L0USDT',observed_ms=due+1000,source_execution_ms=due-1,
                          exec_id='x',qty='1',price='100',fee_usdt='.06'))


def test_signed_maker_rebate_remains_known_cost_in_model(tmp_path):
    from research_lab.kity_weekly_rehearsal_v1 import WeeklyRehearsal
    p,_,_=fixture();w=WeeklyRehearsal(tmp_path/'model',p)
    w.append(dict(event_id='rebate',kind='MODEL_ENTRY_FILL',symbol='L0USDT',observed_ms=p['entry_reference_ms'],
                  exec_id='e',qty='1',price='100',fee_usdt='-.001'))
    assert w.state()['fees_known_usdt']=='-0.001'


def test_two_unknown_ack_cids_cannot_share_broker_id():
    p,r,b=fixture()
    for item in r[:2]:item['order_id']=None
    orders=b['history_windows'][0]['groups']['history']['pages'][0]['body']['result']['list']
    fills=b['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list']
    positions=b['captures']['positions']['pages'][0]['body']['result']['list']
    for i in (0,1):
        orders[i]['orderId']=fills[i]['orderId']='shared-oid'
        orders[i]['cumExecQty']=fills[i]['execQty']=positions[i]['size']='.5';orders[i]['orderStatus']='PartiallyFilled'
    reseal(b)
    with pytest.raises(ValueError,match='BROKER_ID_MULTIPLE'):call(p,r,b)


@pytest.mark.parametrize('field,value',[('price','150'),('timeInForce','IOC'),('cumExecQty','0')])
def test_material_and_terminal_quantity_drift_rejected(field,value):
    p,r,b=fixture();r[0]['request']['price']='100';r[0]['request']['timeInForce']='GTC'
    row=b['history_windows'][0]['groups']['history']['pages'][0]['body']['result']['list'][0]
    row['price']='100';row['timeInForce']='GTC';row[field]=value;reseal(b)
    with pytest.raises(ValueError):call(p,r,b)
