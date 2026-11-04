"""Bounded public GET only: no account, signing, credential or trading imports."""
import concurrent.futures,hashlib,json,time,urllib.request,urllib.parse,subprocess
SYMBOLS=('AKEUSDT','ACEUSDT','BLESSUSDT','BTCUSDT')
ENDPOINTS=('/v5/market/instruments-info','/v5/market/tickers','/v5/market/funding/history','/v5/market/risk-limit','/v5/market/orderbook')
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):raise ValueError('NO_REDIRECT')
client=urllib.request.build_opener(NoRedirect)
def get(spec):
 path,symbol,sample=spec;assert path in ENDPOINTS and symbol in SYMBOLS
 params=dict(category='linear',symbol=symbol)
 if path.endswith('orderbook'):params['limit']='200'
 if path.endswith('history'):params['limit']='8'
 url='https://api.bybit.com'+path+'?'+urllib.parse.urlencode(params)
 started=time.time_ns()//1000000
 try:
  with client.open(urllib.request.Request(url,method='GET'),timeout=12) as response:raw=response.read(2**20+1);assert len(raw)<=2**20;status=response.status
  return dict(endpoint=path,symbol=symbol,sample=sample,request_ms=started,received_ms=time.time_ns()//1000000,status=status,raw=raw.decode(),raw_sha256=hashlib.sha256(raw).hexdigest())
 except Exception as e:return dict(endpoint=path,symbol=symbol,sample=sample,request_ms=started,received_ms=time.time_ns()//1000000,error=type(e).__name__+':'+str(e))
rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 rows+=list(pool.map(get,[(p,s,None) for s in SYMBOLS for p in ENDPOINTS[:-1]]))
 for i in range(10):
  rows+=list(pool.map(get,[('/v5/market/orderbook',s,i) for s in SYMBOLS]))
  if i<9:time.sleep(3)
state=subprocess.check_output(['systemctl','show','pump4-execution-owner.service','alpaca-monthly-owned.service','--property=Id,ActiveState,MainPID,NRestarts,Result','--no-pager'],text=True)
print(json.dumps(dict(schema='SHORT_HVOST_PUBLIC_EXECUTION_RECON_V1',observed_ms=time.time_ns()//1000000,symbols=SYMBOLS,rows=rows,native_state=state,private_account_requests=0,financial_mutations=0,orders=0)))
