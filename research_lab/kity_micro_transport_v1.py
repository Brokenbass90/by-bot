"""Real authenticated Bybit GET transport; deliberately no write method.

Consumed by the micro account reader/reconciler. Dispatch is delegated to the
single physical account owner, never to this credential-bearing reader.
"""
import hashlib
import hmac
import json
import re
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

BASE='https://api.bybit.com'
SYMBOLS=('BTWUSDT','XAUUSDT','LTCUSDT','VVVUSDT','BNBUSDT',
         'XAUTUSDT','XPLUSDT','XAGUSDT','GRASSUSDT','SPCXUSDT')
ALLOW={
 '/v5/user/query-api':set(), '/v5/account/info':set(),
 '/v5/account/wallet-balance':{'accountType'},
 '/v5/account/fee-rate':{'category','symbol'},
 '/v5/account/instruments-info':{'category','symbol','limit','cursor'},
 '/v5/account/transaction-log':{'accountType','category','currency','startTime','endTime','limit','cursor'},
 '/v5/position/list':{'category','symbol','settleCoin','limit','cursor'},
 '/v5/order/realtime':{'category','symbol','orderId','orderLinkId','settleCoin','openOnly','limit','cursor'},
 '/v5/order/history':{'category','symbol','orderId','orderLinkId','startTime','endTime','limit','cursor'},
 '/v5/execution/list':{'category','symbol','orderId','orderLinkId','startTime','endTime','limit','cursor'},
 '/v5/market/instruments-info':{'category','symbol'},
 '/v5/market/tickers':{'category','symbol'},
 '/v5/market/orderbook':{'category','symbol','limit'},
 '/v5/market/time':set(),
}


class SourceError(ValueError): pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise SourceError('REDIRECT_REJECTED')


def wire_get(method,url,headers,data,timeout):
    if method!='GET' or data is not None: raise SourceError('GET_ONLY_TRANSPORT')
    req=urllib.request.Request(url,headers=headers,method='GET')
    opener=urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req,timeout=timeout) as r:return r.status,r.read(2_000_001)
    except urllib.error.HTTPError as e:return e.code,e.read(2_000_001)


def existing_selected_credentials(env_path='/root/by-bot/.env',pid=1648585):
    """Read existing credentials only if they match the original live process."""
    env={}
    for line in Path(env_path).read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);env[k.strip()]=v.strip().strip('"').strip("'")
    active={}
    for part in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0'):
        k,sep,v=part.partition(b'=')
        if sep:active[k.decode()]=v.decode()
    for k in ('BYBIT_ACCOUNTS_JSON','TRADE_ACCOUNT_NAME','BYBIT_BASE'):
        if env.get(k)!=active.get(k):raise SourceError('SELECTED_ACCOUNT_SOURCE_CONFLICT')
    if env.get('BYBIT_BASE')!=BASE:raise SourceError('BASE_CONFLICT')
    selected=[r for r in json.loads(env['BYBIT_ACCOUNTS_JSON']) if r.get('name')==env['TRADE_ACCOUNT_NAME']]
    if len(selected)!=1 or not selected[0].get('key') or not selected[0].get('secret'):
        raise SourceError('SELECTED_ACCOUNT_AMBIGUOUS')
    return selected[0]['key'],selected[0]['secret']


class BybitReadTransport:
    def __init__(self,key,secret,*,wire=wire_get,clock=None,symbols=SYMBOLS):
        if not isinstance(key,str) or not key or not isinstance(secret,str) or not secret:
            raise SourceError('EXISTING_CREDENTIALS_REQUIRED')
        self._key,self._secret,self._wire=key,secret,wire
        self._clock=clock or (lambda:time.time_ns()//1_000_000)
        if (not isinstance(symbols,(tuple,list)) or not symbols
            or len(set(symbols))!=len(symbols)
            or any(not isinstance(s,str) or not re.fullmatch('[A-Z0-9]{1,24}USDT',s) for s in symbols)):
            raise SourceError('EXPLICIT_GET_SYMBOL_SCOPE_REQUIRED')
        self._symbols=frozenset(symbols)
        self.account_fingerprint=hashlib.sha256(key.encode()).hexdigest()

    def get(self,path,params):
        if (path not in ALLOW or not isinstance(params,dict) or not set(params)<=ALLOW[path]
            or any(type(v) not in (str,int) for v in params.values())
            or ('category' in params and params['category']!='linear')
            or ('symbol' in params and params['symbol'] not in self._symbols)
            or ('settleCoin' in params and params['settleCoin']!='USDT')
            or ('accountType' in params and params['accountType']!='UNIFIED')
            or ('currency' in params and params['currency']!='USDT')):
            raise SourceError('GET_SCOPE_CONFLICT')
        at=self._clock();private=not path.startswith('/v5/market/')
        query=urllib.parse.urlencode(sorted(params.items()))
        headers={'User-Agent':'KITY-micro-owned-reader/1'}
        if private:
            sig=hmac.new(self._secret.encode(),(str(at)+self._key+'10000'+query).encode(),hashlib.sha256).hexdigest()
            headers.update({'X-BAPI-API-KEY':self._key,'X-BAPI-TIMESTAMP':str(at),
                            'X-BAPI-RECV-WINDOW':'10000','X-BAPI-SIGN':sig})
        cap=dict(endpoint=path,params=dict(params),request_ms=at,method='GET',signed=private)
        try:
            status,raw=self._wire('GET',BASE+path+('?'+query if query else ''),headers,None,12)
        except Exception as exc:
            return dict(cap,receive_ms=self._clock(),error_type=type(exc).__name__)
        cap.update(receive_ms=self._clock(),http_status=status,raw_sha256=hashlib.sha256(raw).hexdigest())
        if len(raw)>2_000_000:return dict(cap,error_type='BODY_BOUND')
        try:body=json.loads(raw)
        except (ValueError,UnicodeError):return dict(cap,error_type='NON_JSON_RESPONSE')
        if not isinstance(body,dict):return dict(cap,error_type='INVALID_RESPONSE_SCHEMA')
        if path=='/v5/user/query-api' and isinstance(body.get('result'),dict):
            body['result'].pop('apiKey',None);body['result'].pop('ips',None)
            cap['redacted_fields']=['result.apiKey','result.ips']
        else:cap['raw']=raw.decode()
        if any(v in json.dumps(body,sort_keys=True) for v in (self._key,self._secret)):
            return dict(endpoint=path,params=dict(params),request_ms=at,receive_ms=self._clock(),
                        error_type='SECRET_ECHO_REJECTED')
        cap['body']=body
        return cap

    @staticmethod
    def result(cap):
        body=cap.get('body',{})
        if (cap.get('error_type') or cap.get('http_status')!=200 or not isinstance(body,dict)
            or type(body.get('retCode')) is not int or body['retCode']!=0 or not isinstance(body.get('result'),dict)):
            raise SourceError('API_OR_TRANSPORT_SOURCE_UNKNOWN')
        return body['result']

    def pages(self,path,params):
        pages=[];cursor='';seen=set()
        for _ in range(10):
            cap=self.get(path,dict(params,**({'cursor':cursor} if cursor else {})));pages.append(cap)
            try:result=self.result(cap)
            except SourceError:return dict(pages=pages,complete=False,reason='API_OR_TRANSPORT_SOURCE_UNKNOWN')
            if not isinstance(result.get('list'),list):
                return dict(pages=pages,complete=False,reason='INVALID_LIST_SCHEMA')
            cursor=result.get('nextPageCursor','')
            if path=='/v5/account/transaction-log' and cursor is None and result['list']==[]:
                return dict(pages=pages,complete=True,source_contract='EMPTY_TRANSACTION_NULL_CURSOR_V1')
            if not isinstance(cursor,str):return dict(pages=pages,complete=False,reason='INVALID_CURSOR')
            if not cursor:return dict(pages=pages,complete=True)
            if cursor in seen:return dict(pages=pages,complete=False,reason='CURSOR_LOOP')
            seen.add(cursor)
        return dict(pages=pages,complete=False,reason='PAGE_BOUND')
