"""Explicit-opt-in, GET-only IBIT/BTC source capture. No financial API clients.

Only caller-supplied credential profile is read; no environment/key discovery.
Fixed endpoints and request parameters, HTTPS certificate verification, no proxy
or redirects, bounded read. Every response's first received_at is stamped directly
following body read, then immutable/fsync captured before parsing or decisions.
A single process lock spans capture, cache selection and isolated adapter import.
Probe is capture-only: historical retrieval is never prospective or backdated.
Warmup/bootstrap is separate; 61 total valid sessions permit first z and 81 total
supply the full frozen 60-prior-premium window. No historical seed is fabricated.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import http.client
import json
import io
import os
import re
import ssl
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

from research_lab.ibit_btc_data_only_v1 import (
    Adapter, NY, UTC, canonical, checked_path, _day, _stamp, _millis, _open_file, _price,
)

MAX_BODY = 16*1024*1024
TIMEOUT_SECONDS = 15
MAX_SOURCE_CAPTURES = 96
MAX_STORE_FILES = 20000
MAX_STORE_BYTES = 512*1024*1024
MIN_FREE_BYTES = 64*1024*1024
_MARKER = b'{"owner":"IBIT_BTC_COLLECTOR_V1","schema":1}'


class SourceError(ValueError):
    """Only fixed machine-readable codes, never remote exception text."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Request:
    source: str
    session: str
    host: str
    path: str
    params: dict
    headers: dict = field(repr=False)
    method: str = 'GET'
    close_hour: int = 16


def _geometry(session):
    day = _day(session)
    start = dt.datetime.combine(day,dt.time(),NY)
    end = dt.datetime.combine(day+dt.timedelta(days=1),dt.time(),NY)
    ref_end = dt.datetime.combine(day,dt.time(16),NY).astimezone(UTC)
    ref_start_ms = _millis(ref_end-dt.timedelta(hours=1))
    return start,end,ref_end,ref_start_ms


def build_request(source, session, keys, close_hour=16):
    if type(close_hour) is not int or close_hour not in (13,16):
        raise SourceError('CALENDAR_GEOMETRY')
    start,end,ref_end,ref_start = _geometry(session)
    end=dt.datetime.combine(_day(session),dt.time(close_hour),NY)
    headers = {'Accept':'application/json','User-Agent':'ibit-btc-data-only-v1/1'}
    if source == 'calendar':
        host,path,params = 'api.alpaca.markets','/v2/calendar',{'start':session,'end':session}
    elif source == 'alpaca_sip':
        host,path,params = 'data.alpaca.markets','/v2/stocks/bars',dict(
            symbols='IBIT',timeframe='1Day',feed='sip',adjustment='raw',
            start=start.isoformat(),end=end.isoformat(),limit='2',sort='asc')
    elif source == 'binance':
        host,path,params = 'api.binance.com','/api/v3/klines',dict(
            symbol='BTCUSDT',interval='1h',startTime=str(ref_start),endTime=str(ref_start+3599999),limit='1')
    elif source == 'bybit':
        host,path,params = 'api.bybit.com','/v5/market/kline',dict(
            category='linear',symbol='BTCUSDT',interval='60',start=str(ref_start),end=str(ref_start+3599999),limit='1')
    elif source == 'massive':
        host,path,params = 'api.massive.com',f'/v2/aggs/grouped/locale/us/market/stocks/{session}',{'adjusted':'false'}
    else:
        raise SourceError('SOURCE_NOT_ALLOWED')
    if source in ('calendar','alpaca_sip'):
        if not keys.get('alpaca_key_id') or not keys.get('alpaca_secret_key'):
            raise SourceError('ALPACA_PROFILE_REQUIRED')
        headers.update({'APCA-API-KEY-ID':keys['alpaca_key_id'],'APCA-API-SECRET-KEY':keys['alpaca_secret_key']})
    if source == 'massive':
        if not keys.get('massive_api_key'):
            raise SourceError('MASSIVE_PROFILE_KEY_REQUIRED')
        headers['Authorization'] = 'Bearer '+keys['massive_api_key']
    return Request(source,session,host,path,params,headers,close_hour=close_hour)


def validate_request(request):
    # Reconstruct exact permitted geometry, not a host-only general-purpose GET.
    sentinel = {'alpaca_key_id':'x','alpaca_secret_key':'x','massive_api_key':'x'}
    expected = build_request(request.source,request.session,sentinel,request.close_hour)
    if request.method != 'GET' or (request.host,request.path,request.params) != (expected.host,expected.path,expected.params):
        raise SourceError('REQUEST_NOT_ALLOWED')
    permitted = set(expected.headers)
    if set(request.headers) != permitted:
        raise SourceError('HEADERS_NOT_ALLOWED')
    for key,value in request.headers.items():
        if not isinstance(value,str) or not value or '\r' in value or '\n' in value or len(value)>512:
            raise SourceError('INVALID_HEADER')
        if key in ('Accept','User-Agent') and value != expected.headers[key]:
            raise SourceError('HEADERS_NOT_ALLOWED')


class GetOnlyHTTP:
    """HTTPS only. http.client has no redirect/proxy/environment discovery."""
    def __init__(self, clock=None):
        self.clock = clock or (lambda:dt.datetime.now(UTC))

    def get(self, request):
        validate_request(request)
        conn = None
        try:
            deadline = time.monotonic()+TIMEOUT_SECONDS
            conn = http.client.HTTPSConnection(request.host,timeout=TIMEOUT_SECONDS,context=ssl.create_default_context())
            conn.request('GET',request.path+'?'+urlencode(sorted(request.params.items())),headers=request.headers)
            response = conn.getresponse()
            chunks=[]; total=0
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise SourceError('READ_TIMEOUT')
                if conn.sock is not None:
                    conn.sock.settimeout(remaining)
                chunk=response.read1(min(65536,MAX_BODY+1-total))
                if not chunk:
                    break
                chunks.append(chunk); total+=len(chunk)
                if total>MAX_BODY:
                    raise SourceError('BODY_LIMIT')
            received=_stamp(self.clock())  # first receipt immediately after bounded read
            return response.status,b''.join(chunks),received
        except SourceError:
            raise
        except Exception:
            raise SourceError('TRANSPORT_ERROR') from None
        finally:
            if conn is not None:
                conn.close()


def _load_json(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:
                raise SourceError('DUPLICATE_JSON_KEY')
            out[k]=v
        return out
    def bad(value):
        raise SourceError('NONFINITE_JSON')
    try:
        return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
    except SourceError:
        raise
    except (ValueError,UnicodeError):
        raise SourceError('INVALID_JSON') from None


def _profile(path, root):
    if path is None:
        raise SourceError('EXPLICIT_PROFILE_REQUIRED')
    path=checked_path(path,regular=True)
    if path==root or root in path.parents or path in root.parents:
        raise SourceError('PROFILE_STORE_OVERLAP')
    with _open_file(path,'rb') as f:
        os.fstat(f.fileno())  # regular/nlink checks are enforced by _open_file
        raw=f.read(8193)
    if len(raw)>8192:
        raise SourceError('PROFILE_LIMIT')
    if raw.lstrip().startswith(b'{'):
        keys=_load_json(raw)
        if not isinstance(keys,dict) or set(keys)-{'alpaca_key_id','alpaca_secret_key','massive_api_key'}:
            raise SourceError('PROFILE_SCHEMA')
    else:
        # Parse only the explicitly supplied file; never source shell or expand
        # variables, inspect environment, search profiles or discover credentials.
        from dotenv import dotenv_values
        try:
            supplied=dotenv_values(stream=io.StringIO(raw.decode('utf-8')),interpolate=False)
        except (ValueError,UnicodeError):
            raise SourceError('PROFILE_SCHEMA') from None
        if supplied.get('ALPACA_BASE_URL')!='https://api.alpaca.markets':
            raise SourceError('PROFILE_BASE_URL')
        keys={'alpaca_key_id':supplied.get('ALPACA_API_KEY_ID'),
              'alpaca_secret_key':supplied.get('ALPACA_API_SECRET_KEY')}
        if supplied.get('MASSIVE_API_KEY'):
            keys['massive_api_key']=supplied['MASSIVE_API_KEY']
    for key,value in keys.items():
        if not isinstance(value,str) or not value or len(value)>256 or '\n' in value or '\r' in value:
            raise SourceError('PROFILE_SCHEMA')
    if not keys.get('alpaca_key_id') or not keys.get('alpaca_secret_key'):
        raise SourceError('ALPACA_PROFILE_REQUIRED')
    return keys


class CaptureStore:
    def __init__(self,root):
        self.root=checked_path(root); self.root.mkdir(parents=True,exist_ok=True)
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            marker=self.root/'.ibit_btc_collector_v1.json'
            if marker.exists() or marker.is_symlink():
                with _open_file(marker,'rb') as f:
                    if f.read()!=_MARKER: raise SourceError('FOREIGN_STORE')
            else:
                if any(self.root.iterdir()): raise SourceError('FOREIGN_STORE')
                self.write(marker,_MARKER)
        finally:
            os.close(fd)

    @staticmethod
    def write(path,raw):
        Adapter._immutable(path,raw)
        fd=os.open(checked_path(path.parent),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)

    @contextmanager
    def locked(self):
        with _open_file(self.root/'.collector.lock','a+b') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(f,fcntl.LOCK_UN)

    def budget(self, source=None, session=None, extra_bytes=MAX_BODY):
        if shutil.disk_usage(self.root).free < MIN_FREE_BYTES+extra_bytes:
            raise SourceError('DISK_FREE_LIMIT')
        count=total=0
        for parent,dirs,files in os.walk(self.root,followlinks=False):
            for name in dirs:
                checked_path(Path(parent)/name)
            for name in files:
                path=checked_path(Path(parent)/name,regular=True)
                count+=1; total+=path.stat().st_size
                if count>MAX_STORE_FILES or total+extra_bytes>MAX_STORE_BYTES:
                    raise SourceError('STORE_LIMIT')
        if source is not None:
            directory=checked_path(self.root/'captures'/session/source)
            if directory.exists() and sum(1 for _ in directory.glob('*.json'))>=MAX_SOURCE_CAPTURES:
                raise SourceError('CAPTURE_COUNT_LIMIT')

    def capture(self,request,status,body,received):
        if not isinstance(body,bytes) or len(body)>MAX_BODY:
            raise SourceError('BODY_LIMIT')
        received=_stamp(received)
        self.budget(request.source,request.session,len(body)+8192)
        body_sha=hashlib.sha256(body).hexdigest()
        directory=checked_path(self.root/'captures'/request.session/request.source)
        self.write(directory/(body_sha+'.body'),body)
        try:
            provider_sha=hashlib.sha256(canonical(_load_json(body))).hexdigest()
        except (SourceError,ValueError,TypeError):
            provider_sha=None
        metadata={'provider_canonical_raw_sha':provider_sha,'source':request.source,'session':request.session,'body_sha':body_sha,
                  'received_at':received.isoformat(),'received_at_ms':_millis(received),
                  'http_status':status,'request_sha':hashlib.sha256(canonical({
                      'method':'GET','host':request.host,'path':request.path,'params':request.params})).hexdigest()}
        # Include receipt in identity: repeated identical bytes before/after close
        # remain distinct observations. Source cache selects first valid receipt.
        identity=hashlib.sha256(canonical(metadata)).hexdigest()
        self.write(directory/(identity+'.json'),canonical(metadata))
        return metadata

    def cached(self,source,session,now,closed,ref_end):
        directory=checked_path(self.root/'captures'/session/source)
        if not directory.exists(): return None
        found=[]
        paths=list(directory.glob('*.json'))
        if len(paths)>MAX_SOURCE_CAPTURES: raise SourceError('CAPTURE_COUNT_LIMIT')
        for path in paths:
            with _open_file(path,'rb') as f: body=f.read(MAX_BODY+1)
            metadata=_load_json(body)
            if path.stem!=hashlib.sha256(canonical(metadata)).hexdigest(): raise SourceError('CAPTURE_HASH_MISMATCH')
            if metadata['source']!=source or metadata['session']!=session: raise SourceError('CAPTURE_IDENTITY')
            body_sha=metadata['body_sha']
            if not isinstance(body_sha,str) or not re.fullmatch('[0-9a-f]{64}',body_sha): raise SourceError('CAPTURE_IDENTITY')
            with _open_file(directory/(body_sha+'.body'),'rb') as f: raw=f.read(MAX_BODY+1)
            if hashlib.sha256(raw).hexdigest()!=body_sha: raise SourceError('CAPTURE_HASH_MISMATCH')
            received=_stamp(metadata['received_at'])
            if received>now or metadata['received_at_ms']!=_millis(received): raise SourceError('CAPTURE_TIME')
            if metadata['http_status']!=200: continue
            try:
                value=_load_json(raw)
                if _ready(source,value,session,received,closed,ref_end): found.append((received,value,metadata))
            except (SourceError,ValueError,KeyError,TypeError,IndexError):
                continue
        if not found: return None
        received,value,metadata=min(found,key=lambda x:x[0])
        return _envelope(source,value,received,metadata)


def _envelope(source,raw,received,capture=None):
    out={'raw':raw,'received_at':received.isoformat()}
    if capture is not None: out['capture']=capture
    if source=='alpaca_sip': out.update(feed='sip',timeframe='1Day')
    if source=='binance': out.update(symbol='BTCUSDT',interval='1h')
    if source=='bybit': out.update(interval='60')
    return out


def _ready(source,raw,session,received,closed,ref_end):
    if source=='calendar':
        if not isinstance(raw,list) or len(raw)>1 or (raw and raw[0]['date']!=session): raise SourceError('CALENDAR_SCHEMA')
        return True
    if source=='alpaca_sip':
        bars=raw['bars'].get('IBIT',[])
        if raw.get('next_page_token') or len(bars)>1: raise SourceError('DAILY_PAGINATION')
        if not bars: return False
        bar=bars[0]; stamp=_stamp(bar['t']); _price(bar['c'])
        if stamp.astimezone(NY).date()!=_day(session): return False
        if stamp>closed: raise SourceError('AFTER_HOURS_BAR')
        return received>=closed
    start=_millis(ref_end-dt.timedelta(hours=1))
    if source=='binance':
        if len(raw)>1: raise SourceError('REFERENCE_SCHEMA')
        if not raw: return False
        _price(raw[0][4])
        if int(raw[0][0])!=start or int(raw[0][6])!=start+3599999: raise SourceError('REFERENCE_INTERVAL')
        return received>=ref_end
    if source=='bybit':
        result=raw['result']
        if raw['retCode']!=0 or result['category']!='linear' or result['symbol']!='BTCUSDT': raise SourceError('BYBIT_API_ERROR')
        bars=result['list']
        if len(bars)>1: raise SourceError('REFERENCE_SCHEMA')
        if not bars: return False
        _price(bars[0][4])
        if int(bars[0][0])!=start: raise SourceError('REFERENCE_INTERVAL')
        return received>=ref_end
    return False


class Collector:
    def __init__(self,root,credentials=None,enabled=False,http=None,clock=None):
        self.root=root; self.credentials=credentials; self.enabled=enabled
        self.clock=clock or (lambda:dt.datetime.now(UTC)); self.http=http or GetOnlyHTTP(self.clock)

    def _fetch(self,store,source,session,keys,close_hour=16):
        request=build_request(source,session,keys,close_hour); validate_request(request)
        store.budget(source,session)
        try:
            status,body,received=self.http.get(request)
        except SourceError:
            raise
        except Exception:
            raise SourceError('TRANSPORT_ERROR') from None
        # Capture raw body + receipt durably BEFORE parsing, status handling or import.
        metadata=store.capture(request,status,body,received)
        if status!=200:
            raise SourceError('HTTP_'+str(status) if type(status) is int and 100<=status<=599 else 'HTTP_INVALID')
        return _envelope(source,_load_json(body),_stamp(metadata['received_at']),metadata)

    def collect(self,session,massive_qa=False,qa_only=False,probe=False):
        if not self.enabled:
            return {'status':'NO_NETWORK','orders_enabled':False}
        day=_day(session); now=_stamp(self.clock()); today=now.astimezone(NY).date()
        if day>today or (not probe and not qa_only and day<today-dt.timedelta(days=1)):
            raise SourceError('SESSION_OUTSIDE_CAPTURE_WINDOW')
        if qa_only and (not massive_qa or probe): raise SourceError('INVALID_QA_MODE')
        root=checked_path(self.root)
        keys=_profile(self.credentials,root)
        store=CaptureStore(root)
        errors={}
        def error(source,exc):
            code=exc.code if isinstance(exc,SourceError) else 'SOURCE_SCHEMA'
            errors[source]={'code':code,'retryable':code not in ('HTTP_401','HTTP_403','PROFILE_SCHEMA')}
        with store.locked():
            store.budget()
            adapter=Adapter(root/'adapter')
            rows=adapter.decisions(); previous=next((r for r in rows if r['session']==session),None)
            decision=previous; sources={}; health={}; calendar=None; closed=None
            if qa_only and previous is None: raise SourceError('NO_DECISION_FOR_QA')
            _,_,ref_end,_=_geometry(session)
            if not qa_only and not previous:
                try:
                    calendar=store.cached('calendar',session,now,None,ref_end) or self._fetch(store,'calendar',session,keys)
                    _ready('calendar',calendar['raw'],session,_stamp(calendar['received_at']),None,ref_end)
                except (SourceError,ValueError,KeyError,TypeError,IndexError) as exc:
                    error('calendar',exc)
                    return {'status':'BLOCKED_CALENDAR','errors':errors,'orders_enabled':False}
                if not calendar['raw']:
                    return {'status':'NO_SESSION','errors':errors,'orders_enabled':False}
                cal=calendar['raw'][0]
                try:
                    opened=dt.time.fromisoformat(cal['open']); close_time=dt.time.fromisoformat(cal['close'])
                    if opened!=dt.time(9,30) or close_time not in (dt.time(13),dt.time(16)):
                        raise SourceError('CALENDAR_GEOMETRY')
                    closed=dt.datetime.combine(day,close_time,NY).astimezone(UTC)
                except (ValueError,KeyError,TypeError) as exc:
                    error('calendar',exc)
                    return {'status':'BLOCKED_CALENDAR','errors':errors,'orders_enabled':False}
                sources['calendar']=calendar
                health['calendar']='CAPTURED'
                for source in ('alpaca_sip','binance','bybit'):
                    due=closed+dt.timedelta(minutes=15) if source=='alpaca_sip' else ref_end
                    if now<due:
                        health[source]='NOT_DUE'
                        continue
                    try:
                        envelope=store.cached(source,session,now,closed,ref_end)
                        if envelope is None and (probe or now<=closed+dt.timedelta(hours=6)):
                            envelope=self._fetch(store,source,session,keys,close_time.hour)
                        if envelope is None:
                            health[source]='DEADLINE_EXPIRED'
                            continue
                        ready=_ready(source,envelope['raw'],session,_stamp(envelope['received_at']),closed,ref_end)
                        health[source]='CAPTURED' if ready else 'NOT_READY'
                        sources[source]=envelope
                    except (SourceError,ValueError,KeyError,TypeError,IndexError) as exc:
                        error(source,exc)
                if not probe:
                    decision=adapter.import_session(session,sources,_stamp(self.clock()))
            qa=None
            if massive_qa:
                if not keys.get('massive_api_key'):
                    error('massive',SourceError('MASSIVE_PROFILE_KEY_REQUIRED'))
                elif previous or (decision and decision.get('row_sha')) or probe:
                    try:
                        envelope=self._fetch(store,'massive',session,keys)
                        raw=envelope['raw']
                        matches=[r for r in raw.get('results',[]) if r.get('T')=='IBIT']
                        if len(matches)!=1: raise SourceError('MASSIVE_NOT_READY')
                        match=matches[0]; _price(match['c'])
                        normalized={'date':session,'rows':[['IBIT',match.get('o'),match.get('h'),match.get('l'),match['c']]]}
                        health['massive']='CAPTURED'
                        if not probe:
                            qa=adapter.reconcile(session,normalized,envelope['received_at'])
                            capture=envelope['capture']
                            link={'provider':'MASSIVE','session':session,
                                  'provider_canonical_raw_sha':capture['provider_canonical_raw_sha'],
                                  'body_sha':capture['body_sha'],'adapter_qa_sha':qa['qa_sha'],
                                  'row_sha':qa['row_sha'],'received_at':capture['received_at'],
                                  'received_at_ms':capture['received_at_ms']}
                            identity=hashlib.sha256(canonical(link)).hexdigest()
                            store.write(root/'qa_links'/(identity+'.json'),canonical(link))
                    except (SourceError,ValueError,KeyError,TypeError,IndexError) as exc:
                        error('massive',exc)
            historical=adapter.historical_seed_summary()
            valid_forward=sum(r.get('freshness')!='MISSING' and r.get('ibit_close') is not None and r.get('btc_ref_binance') is not None for r in adapter.decisions())
            valid=valid_forward+historical['sessions']
            result={'status':'CAPTURE_ONLY' if probe else (decision or {}).get('status','NO_DECISION'),
                    'orders_enabled':False,'errors':errors,'decision':None if probe else decision,'qa':qa,
                    'capture_kind':'HISTORICAL_RETRIEVAL_NOT_PROSPECTIVE' if day<today else 'CURRENT_SESSION_NETWORK_CAPTURE',
                    'warmup':{'status':'FULL_WINDOW' if valid>=81 else 'WARMUP_INCOMPLETE',
                              'valid_sessions':valid,'valid_forward_sessions':valid_forward,'historical_seed_sessions':historical['sessions'],
                              'historical_seed_sha':historical.get('seed_sha'),'minimum_total_sessions_for_z':61,'full_window_prior_sessions':80},
                    'source_health':{**health,**{source:'ERROR' for source in errors}}}
            if probe: result['source_health'].update({source:'ERROR' for source in errors})
            return result
