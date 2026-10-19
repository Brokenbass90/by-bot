"""Immutable DATA_ONLY capture helpers for the explicit Polymarket/BIL requests.

Only fixed public-data GET routes; no wallet, order route or financial client.
The snapshots describe source availability, never strategy or LIVE acceptance.
"""
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from research_lab.kity_oct15_deadline_v1 import canonical,sha,stable_bytes,publish_once,path


def put(target,raw):
    target=Path(target).absolute()
    if target.exists():
        if stable_bytes(target)!=raw:raise ValueError('IMMUTABLE_FILE_CONFLICT')
    else:publish_once(target,raw)


def data_get(url,headers):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**kw):raise ValueError('DATA_REDIRECT_DENIED')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request(url,headers=headers,method='GET')
    try:
        with opener.open(request,timeout=25) as response:status=response.status;raw=response.read(16*1024*1024+1)
    except urllib.error.HTTPError as e:status=e.code;raw=e.read(1024*1024)
    if len(raw)>16*1024*1024:raise ValueError('DATA_RESPONSE_SIZE')
    return status,raw


class SourceHTTP(ValueError):
    def __init__(self,status):self.status=status;super().__init__('DATA_HTTP_'+str(status))


class Capture:
    def __init__(self,root,*,transport=data_get):
        self.root=Path(root).absolute();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.transport=transport;self.receipts={}

    def get(self,base,params,headers=None):
        parsed=urllib.parse.urlsplit(base)
        allowed=(parsed.scheme=='https' and not parsed.query and not parsed.fragment and not parsed.username and (
            parsed.netloc=='gamma-api.polymarket.com' and parsed.path=='/markets'
            or parsed.netloc=='clob.polymarket.com' and (parsed.path in {'/prices-history','/fee-rate','/tick-size','/spread'}
                or re.fullmatch(r'/markets/0x[0-9a-fA-F]{64}',parsed.path))
            or parsed.netloc=='data.alpaca.markets' and re.fullmatch(r'/v2/stocks/(BIL|SGOV)/bars',parsed.path)
            or parsed.netloc=='paper-api.alpaca.markets' and parsed.path=='/v2/calendar'))
        if not allowed:raise ValueError('DATA_GET_ROUTE_DENIED')
        if any(k.lower() in {'api_key','secret','authorization'} for k in params):raise ValueError('URL_SECRET_DENIED')
        url=base+'?'+urllib.parse.urlencode(sorted(params.items()))
        key=sha(url.encode());raw_path=self.root/(key+'.raw');receipt_path=self.root/(key+'.receipt.json')
        if receipt_path.exists():
            receipt=json.loads(stable_bytes(receipt_path));raw=stable_bytes(raw_path)
            if receipt['url']!=url or receipt['raw_sha256']!=sha(raw):raise ValueError('RAW_CAPTURE_HASH_CONFLICT')
        else:
            if raw_path.exists():raise ValueError('RAW_CAPTURE_WITHOUT_RECEIPT')
            started=time.time_ns()//1000000
            for attempt in range(3):
                status,raw=self.transport(url,headers or {'User-Agent':'TradingOS-DataOnly-Research/1.0'})
                if status not in {429,500,502,503,504} or attempt==2:break
                time.sleep(2**attempt)
            receipt=dict(schema='RESEARCH_SOURCE_GET_RECEIPT_V1',url=url,method='GET',http_status=status,
                started_ms=started,received_ms=time.time_ns()//1000000,raw_sha256=sha(raw))
            put(raw_path,raw);put(receipt_path,canonical(receipt)+b'\n')
        self.receipts[key]=receipt
        if receipt['http_status']!=200:raise SourceHTTP(receipt['http_status'])
        return json.loads(raw)


def price_profile(payload):
    rows=payload['history'];prior=None;gaps=[]
    if not isinstance(rows,list):raise ValueError('HISTORY_SCHEMA')
    for row in rows:
        stamp,price=row['t'],row['p']
        if (type(stamp) is not int or stamp<0 or type(price) not in (int,float)
            or not math.isfinite(price) or not 0<=price<=1):raise ValueError('PRICE_ROW_INVALID')
        if prior is not None:
            if stamp<=prior:raise ValueError('PRICE_TIME_ORDER_OR_DUPLICATE')
            gaps.append(stamp-prior)
        prior=stamp
    return dict(points=len(rows),first_ts=rows[0]['t'] if rows else None,last_ts=prior,
        max_gap_seconds=max(gaps,default=None),hourly_full_lifetime_proven=False)


def explicit_history(get,token,start,end):
    if type(start) is not int or type(end) is not int or not 0<=start<=end:
        raise ValueError('HISTORY_WINDOW')
    if (end-start)//1209600>200:raise ValueError('HISTORY_WINDOW_BUDGET')
    points={};cursor=start
    while cursor<end:
        stop=min(end,cursor+1209600)
        payload=get('https://clob.polymarket.com/prices-history',dict(market=token,
            startTs=max(0,cursor-1),endTs=stop+1,fidelity=60))
        price_profile(payload)
        for row in payload['history']:
            if not start<=row['t']<=end:continue
            if row['t'] in points and points[row['t']]!=row['p']:raise ValueError('HISTORY_OVERLAP_CONFLICT')
            points[row['t']]=row['p']
        cursor=stop
    return dict(history=[dict(t=t,p=p) for t,p in sorted(points.items())])


def array(value):
    out=json.loads(value) if isinstance(value,str) else value
    if not isinstance(out,list):raise ValueError('MARKET_ARRAY_SCHEMA')
    return out


def market_profile(market,histories):
    tokens=array(market.get('clobTokenIds',[]));outcomes=array(market.get('outcomes',[]))
    if len(tokens)!=len(outcomes) or len(set(tokens))!=len(tokens):raise ValueError('MARKET_TOKEN_IDENTITY')
    profiles={t:price_profile(histories[t]) for t in tokens if t in histories}
    return dict(id=str(market['id']),tokens=len(tokens),tokens_with_history=sum(p['points']>0 for p in profiles.values()),
        price_profiles=profiles,resolved_status=market.get('umaResolutionStatus') or 'UNKNOWN',
        authoritative_winner=None,closed_time=market.get('closedTime'),planned_end=market.get('endDate'),
        hourly_full_lifetime_proven=False,historical_spread_status='UNKNOWN',historical_fee_status='UNKNOWN',
        pit_metadata_vintage='UNKNOWN_RETROSPECTIVE_CURRENT_SNAPSHOT',event_group_completeness='UNKNOWN')


def alpaca_pages(get,symbol,adjustment,*,start,end,headers=None):
    if symbol not in {'BIL','SGOV'} or adjustment not in {'all','split'}:raise ValueError('ETF_REQUEST_SCOPE')
    token=None;seen=set();rows=[]
    for _ in range(20):
        params=dict(timeframe='1Day',start=start+'T00:00:00Z',end=end+'T23:59:59Z',
            feed='sip',adjustment=adjustment,asof='-',limit=10000,sort='asc')
        if token:params['page_token']=token
        payload=get('https://data.alpaca.markets/v2/stocks/'+symbol+'/bars',params,headers=headers)
        if payload.get('symbol')!=symbol or not isinstance(payload.get('bars'),list):raise ValueError('ALPACA_SYMBOL_OR_BARS')
        rows.extend(payload['bars']);token=payload.get('next_page_token')
        if not token:return rows
        if not isinstance(token,str) or token in seen:raise ValueError('ALPACA_PAGE_LOOP')
        seen.add(token)
    raise ValueError('ALPACA_PAGE_BUDGET')


def bars_qa(all_rows,split_rows,calendar):
    dates=lambda rows:[datetime.fromtimestamp(r['t']/1000,timezone.utc).date().isoformat() for r in rows]
    a,b=dates(all_rows),dates(split_rows)
    if not a or not b:raise ValueError('EMPTY_ETF_HISTORY')
    if a!=sorted(set(a)) or b!=sorted(set(b)):raise ValueError('ETF_SESSION_DUPLICATE_OR_ORDER')
    expected=set(calendar)
    if (set(a)|set(b))-expected:raise ValueError('ETF_BAR_OUTSIDE_CALENDAR')
    return dict(bars_all=len(a),bars_split=len(b),first_observation=a[0],last_observation=a[-1],
        adjustment_timestamps_match=[r['t'] for r in all_rows]==[r['t'] for r in split_rows],
        missing_sessions_after_first=sorted(d for d in calendar if d>=a[0] and (d not in a or d not in b)),
        pre_first_observation_sessions=sorted(d for d in calendar if d<a[0]),
        pre_listing_history_fabricated=False,historical_adjustment_vintage='NOT_PROVEN',
        adjustments='all and split are separate provider snapshots; no second transformation')


def seal(directory,receipt):
    root=Path(directory).absolute();files={}
    for f in sorted(root.rglob('*')):
        if f.is_file():files[str(f.relative_to(root))]=sha(stable_bytes(f))
    body=dict(receipt,files=files,orders_allowed=False,money_authority=False,broker_writes=0)
    put(root/'delivery.json',canonical(body)+b'\n');return body


def verify_delivery(directory):
    root=Path(directory).absolute();doc=json.loads(stable_bytes(root/'delivery.json'))
    inventory=set()
    for f in root.rglob('*'):
        if f.is_symlink():raise ValueError('DELIVERY_INVENTORY_SYMLINK')
        if f.is_file() and f!=root/'delivery.json':inventory.add(str(f.relative_to(root)))
    if inventory!=set(doc['files']):raise ValueError('DELIVERY_INVENTORY_CONFLICT')
    for n,h in doc['files'].items():
        rel=Path(n)
        if rel.is_absolute() or '..' in rel.parts or sha(stable_bytes(root/n))!=h:raise ValueError('DELIVERY_HASH_CONFLICT')
    if doc['orders_allowed'] is not False or doc['money_authority'] is not False:raise ValueError('DATA_ONLY_AUTHORITY')
    return doc


def deliver_snapshot(source,destination):
    source=Path(source).absolute();destination=Path(destination).absolute()
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('DELIVERY_PATH_SCOPE')
    doc=verify_delivery(source);already=(destination/'delivery.json').exists()
    if already:
        if verify_delivery(destination)!=doc:raise ValueError('DELIVERY_IDENTITY_CONFLICT')
    else:
        allowed=set(doc['files'])|{'delivery.json'}
        for f in destination.rglob('*'):
            if f.is_symlink() or (f.is_file() and str(f.relative_to(destination)) not in allowed):
                raise ValueError('DELIVERY_INVENTORY_CONFLICT')
        for n,h in doc['files'].items():
            f=destination/n
            if f.exists() and sha(stable_bytes(f))!=h:raise ValueError('DELIVERY_HASH_CONFLICT')
        for n in doc['files']:put(destination/n,stable_bytes(source/n))
        put(destination/'delivery.json',stable_bytes(source/'delivery.json'))
        verify_delivery(destination)
    return dict(already_imported=already,delivery_sha256=sha(stable_bytes(destination/'delivery.json')),
        first_local_seal_mtime_ns=(destination/'delivery.json').stat().st_mtime_ns,
        import_observed_ms=time.time_ns()//1000000,source_received_ms=doc['source_received_ms'] if 'source_received_ms' in doc else None,
        immutable_files=len(doc['files'])+1,orders_allowed=False,money_authority=False)
