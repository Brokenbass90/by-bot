import copy,hashlib,json
import pytest
from research_lab.pump4_bybit_sources_v1 import universe,public_get,closed_h1,flat_account
from research_lab.pump4_execution_plan_v1 import HOUR_MS as H

NOW=2000*H

def capture(path,params,result,*,at=NOW,private=False):
    body=dict(retCode=0,result=result,time=at)
    raw=json.dumps(body)
    return dict(endpoint=path,params=params,method='GET',signed=private,request_ms=at,receive_ms=at+1,
        http_status=200,body=body,raw=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        **({'account_fingerprint':'a'*64} if private else {}))

def klines():
    rows=[[str(i*H),'10','12','8','11','100','1000'] for i in range(999,2001)]
    params=dict(category='linear',symbol='ZROUSDT',interval='60',start=999*H,end=2001*H-1,limit=1000)
    first=capture('/v5/market/kline',params,dict(category='linear',symbol='ZROUSDT',list=list(reversed(rows[2:]))))
    second=capture('/v5/market/kline',dict(params,end=1001*H-1),dict(category='linear',symbol='ZROUSDT',list=list(reversed(rows[:2]))))
    return [first,second]

def test_frozen_universe_no_silent_replacement():
    s=universe();assert len(s)==137 and 'HFTUSDT' in s and 'BTCUSDT_B21' not in s
    assert hashlib.sha256(('\n'.join(s)+'\n').encode()).hexdigest()=='935880315e2450e03e1df0beb43a8598a9e5440d86036a5469e436f76f6bd71a'

def test_closed_h1_seed_and_actual_next_open_are_separate():
    rows=closed_h1(klines(),'ZROUSDT',next_open_ms=NOW,observed_ms=NOW+2)
    assert len(rows['seed'])==1000 and rows['signal_bar'][0]==NOW-H
    assert rows['next_open']==10 and rows['next_open_ms']==NOW
    assert rows['prospective_decisions_credited']==0 and rows['orders_allowed'] is False

@pytest.mark.parametrize('fault',['hash','wrong_symbol','gap','insufficient','changed_duplicate','open_clock','invalid_ohlc','outside_request'])
def test_candle_source_conflicts_fail_closed(fault):
    c=klines()
    if fault=='hash':c[0]['raw_sha256']='0'*64
    else:
        b=c[0]['body'];p=c[0]['params']
        if fault=='wrong_symbol':b['result']['symbol']='BTCUSDT'
        elif fault=='gap':b['result']['list'].pop(3)
        elif fault=='insufficient':c.pop()
        elif fault=='changed_duplicate':c[1]['body']['result']['list'].append([str(1001*H),'9','12','8','11','100','1000'])
        elif fault=='open_clock':b['time']=NOW-H
        elif fault=='invalid_ohlc':b['result']['list'][3][3]='999'
        else:p['end']=NOW-H-1
        for x in c:
            x['raw']=json.dumps(x['body']);x['raw_sha256']=hashlib.sha256(x['raw'].encode()).hexdigest()
    with pytest.raises(ValueError):closed_h1(c,'ZROUSDT',next_open_ms=NOW,observed_ms=NOW+2)

@pytest.mark.parametrize('path,params',[
    ('/v5/order/create',{}),('/v5/market/kline',dict(category='linear',symbol='BTCUSDT_B21',interval='60',start=1,end=2,limit=1)),
    ('/v5/market/kline',dict(category='linear',symbol='ZROUSDT',interval='5',start=1,end=2,limit=1))])
def test_public_reader_rejects_scope_before_wire(path,params):
    with pytest.raises(ValueError):public_get(path,params,wire=lambda *a:pytest.fail('wire called'))

def test_public_reader_reuses_get_wire_and_preserves_raw_hash():
    def wire(method,url,headers,data,timeout):
        assert method=='GET' and data is None and url.startswith('https://api.bybit.com/v5/market/time')
        assert not any('KEY' in k.upper() or 'SIGN' in k.upper() for k in headers)
        return 200,json.dumps(dict(retCode=0,result=dict(timeSecond=str(NOW//1000)),time=NOW)).encode()
    c=public_get('/v5/market/time',{},wire=wire,clock=lambda:NOW+1)
    assert c['signed'] is False and c['raw_sha256']==hashlib.sha256(c['raw'].encode()).hexdigest()

def group(path,params,rows):
    return dict(complete=True,pages=[capture(path,params,dict(list=rows,nextPageCursor=''),private=True)])

def account():
    return dict(schema='PUMP4_ACCOUNT_GET_CAPTURE_V1',account_fingerprint='a'*64,started_ms=NOW,completed_ms=NOW+1,
        captures=dict(
            positions=group('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),[]),
            orders=group('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),[]),
            fees=capture('/v5/account/fee-rate',dict(category='linear'),dict(list=[dict(symbol='ZROUSDT',takerFeeRate='.00055',makerFeeRate='.0002')]),private=True),
            wallet=capture('/v5/account/wallet-balance',dict(accountType='UNIFIED'),dict(list=[dict(accountType='UNIFIED',totalAvailableBalance='100',totalEquity='100',coin=[dict(coin='USDT',borrowAmount='0',spotBorrow='0')])]),private=True),
            account=capture('/v5/account/info',{},dict(marginMode='REGULAR_MARGIN'),private=True)))

def test_actual_flat_account_view_keeps_identity_cost_unknown_and_no_authority():
    r=flat_account(account(),expected_fingerprint='a'*64,now_ms=NOW+2)
    assert r['positions_flat'] and r['open_orders_empty'] and r['available_balance']=='100'
    assert r['fees']['ZROUSDT']['takerFeeRate']=='.00055'
    assert r['cost_finality']=='UNKNOWN_NOT_INFERRED_FROM_EMPTY_ACCOUNT'
    assert r['orders_allowed'] is False

def test_account_metadata_has_no_server_time_and_updated_time_is_not_freshness():
    x=account();cap=x['captures']['account'];cap['body'].pop('time')
    cap['body']['result']['updatedTime']='1000'
    cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
    r=flat_account(x,expected_fingerprint='a'*64,now_ms=NOW+2)
    assert r['account_metadata_clock_basis']=='AUTHENTICATED_REQUEST_RECEIVE_BRACKET_ONLY'
    assert r['source_ms']==NOW

def test_wallet_without_server_clock_stays_blocked():
    x=account();cap=x['captures']['wallet'];cap['body'].pop('time')
    cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
    with pytest.raises((ValueError,KeyError)):flat_account(x,expected_fingerprint='a'*64,now_ms=NOW+2)

def test_other_coin_borrow_is_not_hidden_by_zero_usdt_borrow():
    x=account();cap=x['captures']['wallet']
    cap['body']['result']['list'][0]['coin'].append(dict(coin='BTC',borrowAmount='1',spotBorrow='0'))
    cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
    with pytest.raises(ValueError,match='BORROWED_FUNDS'):flat_account(x,expected_fingerprint='a'*64,now_ms=NOW+2)

@pytest.mark.parametrize('field',['positions','orders','fees','wallet','account'])
def test_each_authenticated_capture_is_bound_to_selected_reader(field):
    x=account();v=x['captures'][field]
    v.get('pages',[v])[0]['account_fingerprint']='b'*64
    with pytest.raises(ValueError,match='CAPTURE_ACCOUNT_IDENTITY'):
        flat_account(x,expected_fingerprint='a'*64,now_ms=NOW+2)

@pytest.mark.parametrize('fault',['identity','unsigned','stale','body_hash','cursor','borrow','duplicate','future','foreign_position'])
def test_account_admission_never_trusts_false_complete_or_unbound_sources(fault):
    x=account()
    if fault=='identity':x['account_fingerprint']='b'*64
    elif fault=='unsigned':x['captures']['wallet']['signed']=False
    elif fault=='stale':x['started_ms']-=5001
    elif fault=='cursor':x['captures']['positions']['pages'][0]['body']['result']['nextPageCursor']='MORE'
    elif fault=='borrow':x['captures']['wallet']['body']['result']['list'][0]['coin'][0]['spotBorrow']='1'
    elif fault=='duplicate':x['captures']['positions']['pages'].append(copy.deepcopy(x['captures']['positions']['pages'][0]))
    elif fault=='future':x['completed_ms']=NOW+100
    elif fault=='foreign_position':x['captures']['positions']['pages'][0]['body']['result']['list']=[dict(symbol='BTCUSDT',positionIdx=0,size='1',side='Buy')]
    else:x['captures']['fees']['raw_sha256']='0'*64
    if fault not in ('body_hash',):
        for v in x['captures'].values():
            for c in v.get('pages',[v]):c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()
    with pytest.raises(ValueError):flat_account(x,expected_fingerprint='a'*64,now_ms=NOW+2)
