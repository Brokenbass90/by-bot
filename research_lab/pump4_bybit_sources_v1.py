"""PUMP4 frozen137 public source + existing authenticated GET capture checks.

No secret loader, POST, controller, authority file or broker mutation. Response
hashes are integrity evidence, not a broker signature; trust comes from the
known HTTPS/SSH reader. Old captures may be replayed at their original cutoff,
but that does not turn them into a fresh entry or prospective decision.
"""
from decimal import Decimal as D
import hashlib,json,re,time,urllib.parse
from pathlib import Path
from research_lab.kity_micro_transport_v1 import wire_get,BASE
from research_lab.pump4_execution_plan_v1 import HOUR_MS as H

UNIVERSE_SHA='935880315e2450e03e1df0beb43a8598a9e5440d86036a5469e436f76f6bd71a'
ROOT=Path(__file__).resolve().parents[1]


def need(ok,why):
    if not ok:raise ValueError('PUMP4_SOURCE_'+why)


def number(v,*,zero=False):
    need(type(v) in (str,int,float),'NUMBER')
    n=D(str(v));need(n.is_finite() and (n>=0 if zero else n>0),'NUMBER');return n


def universe():
    x=json.loads((ROOT/'configs/preregistered/pump4_v1_universe_20261020.json').read_bytes())
    s=x['symbols']
    need(x['schema']=='PUMP4_V1_FROZEN_UNIVERSE_V1' and x['orders_allowed'] is False
        and s==sorted(set(s)) and len(s)==137 and all(re.fullmatch('[A-Z0-9]{1,24}USDT',v) for v in s)
        and hashlib.sha256(('\n'.join(s)+'\n').encode()).hexdigest()==x['universe_sha256']==UNIVERSE_SHA,'UNIVERSE_IDENTITY')
    return tuple(s)


def public_get(path,params,*,wire=wire_get,clock=None):
    allowed={'/v5/market/time':set(),'/v5/market/kline':{'category','symbol','interval','start','end','limit'},
        '/v5/market/instruments-info':{'category','limit','cursor'},'/v5/market/tickers':{'category'}}
    need(path in allowed and isinstance(params,dict) and set(params)<=allowed[path],'PUBLIC_SCOPE')
    need(all(type(v) in (str,int) for v in params.values()),'PUBLIC_PARAMS')
    if path!='/v5/market/time':need(params.get('category')=='linear','CATEGORY')
    if path=='/v5/market/kline':
        need(set(params)==allowed[path] and params['symbol'] in universe() and params['interval']=='60'
            and all(type(params[k]) is int for k in ('start','end','limit'))
            and 0<params['start']<=params['end'] and 1<=params['limit']<=1000,'H1_SCOPE')
    if path=='/v5/market/instruments-info':need(params.get('limit')==1000,'INSTRUMENT_PAGE_SIZE')
    clock=clock or (lambda:time.time_ns()//1000000);started=clock()
    status,raw=wire('GET',BASE+path+('?' + urllib.parse.urlencode(sorted(params.items())) if params else ''),
        {'User-Agent':'PUMP4-ORDERS-OFF-source/1'},None,12)
    need(len(raw)<=5_000_000,'BODY_BOUND')
    return dict(endpoint=path,params=dict(params),method='GET',signed=False,request_ms=started,receive_ms=clock(),
        http_status=status,raw=raw.decode(),raw_sha256=hashlib.sha256(raw).hexdigest(),body=json.loads(raw))


def checked(cap,path,*,now_ms,private,fingerprint=None):
    need(cap.get('method')=='GET' and cap.get('endpoint')==path and cap.get('signed') is private
        and cap.get('http_status')==200 and not cap.get('error_type'),'CAPTURE_SCOPE')
    need(hashlib.sha256(cap['raw'].encode()).hexdigest()==cap['raw_sha256']
        and json.loads(cap['raw'])==cap['body'],'RAW_BODY_IDENTITY')
    if private:need(fingerprint is not None and cap.get('account_fingerprint')==fingerprint,'CAPTURE_ACCOUNT_IDENTITY')
    b=cap['body'];need(type(b.get('retCode')) is int and b['retCode']==0 and isinstance(b.get('result'),dict),'API_RESULT')
    start,end=cap['request_ms'],cap['receive_ms']
    need(all(type(t) is int for t in (start,end,now_ms)) and 0<start<=end<=now_ms,'SOURCE_CLOCK')
    # This metadata endpoint has no response-level server time in the documented
    # actual API. updatedTime is a configuration-change time, never freshness.
    if private and path=='/v5/account/info' and 'time' not in b:
        updated=int(b['result']['updatedTime'])
        need(0<updated<=now_ms+5000 and now_ms-start<=5000,'ACCOUNT_METADATA_CLOCK')
    else:
        source=b['time'];need(type(source) is int and start-5000<=source<=end+5000,'SOURCE_CLOCK')
        if private:need(now_ms-start<=5000 and now_ms-source<=5000,'STALE_PRIVATE_CAPTURE')
    return b['result']


def closed_h1(captures,symbol,*,next_open_ms,observed_ms):
    need(symbol in universe() and type(next_open_ms) is int and next_open_ms%H==0,'H1_IDENTITY')
    bars={};identities=[];latest_source=0
    for cap in captures:
        result=checked(cap,'/v5/market/kline',now_ms=observed_ms,private=False);p=cap['params']
        need(p.get('category')=='linear' and p.get('symbol')==symbol and p.get('interval')=='60'
            and result.get('category')=='linear' and result.get('symbol')==symbol,'H1_SOURCE_IDENTITY')
        need(cap['body']['time']>=next_open_ms,'H1_NOT_CLOSED')
        latest_source=max(latest_source,cap['body']['time']);previous=None
        for raw in result['list']:
            need(isinstance(raw,list) and len(raw)==7,'H1_ROW_SCHEMA')
            stamp=int(raw[0]);o,h,l,c,v,turnover=map(D,raw[1:])
            need(stamp%H==0 and p['start']<=stamp<=p['end'] and (previous is None or stamp<previous),'H1_ORDER_OR_SCOPE')
            need(all(n.is_finite() for n in (o,h,l,c,v,turnover)) and 0<l<=min(o,c)<=max(o,c)<=h
                and v>=0 and turnover>=0,'H1_OHLC_VOLUME')
            row=[stamp,*map(float,(o,h,l,c,v))]
            need(stamp not in bars or bars[stamp]==row,'H1_CHANGED_OVERLAP');bars[stamp]=row;previous=stamp
        identities.append(dict(raw_sha256=cap['raw_sha256'],request_ms=cap['request_ms'],receive_ms=cap['receive_ms'],source_ms=cap['body']['time']))
    required=list(range(next_open_ms-1001*H,next_open_ms,H))
    need(all(t in bars for t in required) and next_open_ms in bars,'H1_GAP_OR_INSUFFICIENT')
    need(all(next_open_ms-1001*H<=t<=next_open_ms for t in bars),'H1_WINDOW_EXTRA')
    return dict(schema='PUMP4_CLOSED_H1_SOURCE_V1',symbol=symbol,seed=[bars[t] for t in required[:-1]],
        signal_bar=bars[required[-1]],next_open_ms=next_open_ms,next_open=bars[next_open_ms][1],
        source_ms=latest_source,available_ms=max(c['receive_ms'] for c in captures),observed_ms=observed_ms,
        source_captures=identities,universe_sha256=UNIVERSE_SHA,
        source_kind='ACTUAL_HTTPS_CAPTURE_NOT_PROSPECTIVE_EXECUTION_AUTHORITY',
        prospective_decisions_credited=0,orders_allowed=False,money_authority=False)


def paged(group,path,params,*,now_ms,fingerprint):
    need(group.get('complete') is True and isinstance(group.get('pages'),list) and 1<=len(group['pages'])<=10,'COMPLETE_PAGES_REQUIRED')
    cursor='';seen=set();rows=[]
    for i,cap in enumerate(group['pages']):
        expected=dict(params,**({'cursor':cursor} if cursor else {}))
        need(cap['params']==expected,'PAGE_QUERY_IDENTITY')
        result=checked(cap,path,now_ms=now_ms,private=True,fingerprint=fingerprint)
        need(isinstance(result.get('list'),list),'PAGE_LIST')
        rows.extend(result['list']);cursor=result.get('nextPageCursor')
        if cursor is None and path=='/v5/account/transaction-log' and result['list']==[]:cursor=''
        need(isinstance(cursor,str) and cursor not in seen,'CURSOR_LOOP_OR_SCHEMA')
        if cursor:seen.add(cursor)
        need(bool(cursor)==(i<len(group['pages'])-1),'PAGE_COMPLETENESS')
    return rows


def account_view(bundle,*,expected_fingerprint,now_ms):
    need(re.fullmatch('[a-f0-9]{64}',expected_fingerprint) is not None
        and bundle['schema']=='PUMP4_ACCOUNT_GET_CAPTURE_V1'
        and bundle['account_fingerprint']==expected_fingerprint,'ACCOUNT_IDENTITY')
    need(type(bundle['started_ms']) is int and type(bundle['completed_ms']) is int
        and 0<=now_ms-bundle['started_ms']<=5000 and bundle['started_ms']<=bundle['completed_ms']<=now_ms,'ACCOUNT_WINDOW')
    caps=bundle['captures']
    positions=paged(caps['positions'],'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),now_ms=now_ms,fingerprint=expected_fingerprint)
    orders=paged(caps['orders'],'/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),now_ms=now_ms,fingerprint=expected_fingerprint)
    for k,path,params in [('fees','/v5/account/fee-rate',dict(category='linear')),
        ('wallet','/v5/account/wallet-balance',dict(accountType='UNIFIED')),('account','/v5/account/info',{})]:
        need(caps[k]['params']==params,'ACCOUNT_CAPTURE_QUERY')
    rates=checked(caps['fees'],'/v5/account/fee-rate',now_ms=now_ms,private=True,fingerprint=expected_fingerprint)['list'];fees={}
    for r in rates:
        need(r['symbol'] not in fees,'DUPLICATE_FEE_SYMBOL');number(r['takerFeeRate'],zero=True)
        maker=D(r['makerFeeRate']);need(maker.is_finite(),'FEE_NUMBER');fees[r['symbol']]=r
    wallet=checked(caps['wallet'],'/v5/account/wallet-balance',now_ms=now_ms,private=True,fingerprint=expected_fingerprint)['list']
    need(len(wallet)==1 and wallet[0]['accountType']=='UNIFIED','WALLET_IDENTITY');w=wallet[0]
    usdt=[r for r in w['coin'] if r['coin']=='USDT'];need(len(usdt)==1,'USDT_BALANCE_REQUIRED')
    borrowed=any(number(r['borrowAmount'],zero=True)>0 or number(r['spotBorrow'],zero=True)>0 for r in w['coin'])
    account=checked(caps['account'],'/v5/account/info',now_ms=now_ms,private=True,fingerprint=expected_fingerprint)
    return dict(schema='PUMP4_ACCOUNT_GET_VIEW_V1',account_fingerprint=expected_fingerprint,
        available_balance=str(number(w['totalAvailableBalance'],zero=True)),equity=str(number(w['totalEquity'],zero=True)),
        positions_flat=not any(number(p['size'],zero=True)>0 for p in positions),open_orders_empty=not orders,
        positions=positions,orders=orders,borrowed_funds=borrowed,margin_mode=account['marginMode'],fees=fees,
        source_ms=min(c['body']['time'] for v in caps.values() for c in v.get('pages',[v]) if 'time' in c['body']),observed_ms=now_ms,
        account_metadata_clock_basis='SERVER_RESPONSE_TIME' if 'time' in caps['account']['body'] else 'AUTHENTICATED_REQUEST_RECEIVE_BRACKET_ONLY',
        cost_finality='UNKNOWN_NOT_INFERRED_FROM_EMPTY_ACCOUNT',orders_allowed=False,money_authority=False)


def flat_account(bundle,*,expected_fingerprint,now_ms):
    view=account_view(bundle,expected_fingerprint=expected_fingerprint,now_ms=now_ms)
    need(view['positions_flat'] and view['open_orders_empty'],'ACCOUNT_NOT_FLAT_OR_FOREIGN_ORDER')
    need(not view['borrowed_funds'],'BORROWED_FUNDS')
    need(view['margin_mode']=='REGULAR_MARGIN','UNSUPPORTED_MARGIN_MODE')
    return dict(view,schema='PUMP4_ACCOUNT_FLAT_VIEW_V1')
