#!/usr/bin/env python3
"""Separate, resumable SIP research snapshot of the frozen candidate pool.

The legacy bar encoding is preserved; the manifest explicitly names Alpaca SIP,
not Massive. Never replaces the accepted archive, universe, or Factory queue.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.materialize_alpaca_pit_daily import _atomic_json, _canonical_sha, _load_env, AUTHORITY


def bind_raw_cache(raw, identity):
    """Never reuse a saved response for a different date/feed/universe request."""
    path=raw/'request_identity.json'
    if path.exists():
        if json.loads(path.read_text())!=identity:raise ValueError('raw_cache_identity_changed')
    else:
        if any(raw.iterdir()):raise ValueError('unbound_existing_raw_cache')
        _atomic_json(path,identity)
        path.chmod(0o600)


def normalize(rows, start, end):
    result=[]
    for row in rows:
        stamp=dt.datetime.fromisoformat(row['t'].replace('Z','+00:00'))
        if stamp.tzinfo is None or not start <= stamp.date() <= end:
            raise ValueError('bar_outside_requested_interval')
        values={k:float(row[k]) for k in ('o','h','l','c','v','vw')}
        no_trades = values['v'] == 0 and values['vw'] == 0 and row['n'] == 0
        if (not all(math.isfinite(v) for v in values.values()) or min(values[k] for k in ('o','h','l','c'))<=0
            or (values['vw']<=0 and not no_trades)
            or values['v']<0 or values['l']>min(values['o'],values['c']) or values['h']<max(values['o'],values['c'])
            or type(row['n']) is not int or row['n']<0):
            raise ValueError('bar_invalid')
        result.append({**values,'n':row['n'],'t':int(stamp.timestamp()*1000)})
    times=[r['t'] for r in result]
    if times!=sorted(set(times)):
        raise ValueError('timestamps_not_unique_ascending')
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--raw',type=Path,required=True);ap.add_argument('--env',type=Path,required=True)
    ap.add_argument('--start',default='2016-01-01');ap.add_argument('--end',required=True)
    ap.add_argument('--allow-readonly-network',action='store_true')
    args=ap.parse_args()
    if not args.allow_readonly_network:raise ValueError('explicit_readonly_network_required')
    source=args.source.resolve();out=args.out.resolve();raw=args.raw.resolve()
    if source==out or source in out.parents:raise ValueError('source_archive_is_immutable')
    start,end=dt.date.fromisoformat(args.start),dt.date.fromisoformat(args.end)
    if start>=end or end>=dt.datetime.now(dt.timezone.utc).date():raise ValueError('only_completed_dates_allowed')
    if shutil.disk_usage(ROOT).free<50*1024**3:raise ValueError('disk_guard_50gb')
    membership=json.loads((source/'membership_intervals.json').read_text())
    symbols=[r['symbol'] for r in membership['intervals']]
    if len(symbols)!=len(set(symbols)) or not symbols:raise ValueError('invalid_source_membership')
    env=_load_env(args.env)
    headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY'],'Accept':'application/json'}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**kw):raise ValueError('data_redirect_denied')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    out.mkdir(parents=True,exist_ok=True);raw.mkdir(parents=True,exist_ok=True,mode=0o700);(out/'bars').mkdir(exist_ok=True)
    identity={'source_membership_sha256':hashlib.sha256((source/'membership_intervals.json').read_bytes()).hexdigest(),
        'start':args.start,'end':args.end,'provider':'Alpaca SIP','feed':'sip','adjustment':'split','asof':'-',
        'universe_symbols':symbols,'legacy_bar_schema':'massive_adjusted_daily_symbol_v1'}
    bind_raw_cache(raw,identity)
    manifest_path=out/'deep_history_manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        if manifest['request']!=identity:raise ValueError('resume_identity_changed')
    else:
        manifest={'request':identity,'authority':AUTHORITY,'promotion_authorized':False,'factory_hypothesis_run':False,
            'accepted_archive_replaced':False,'full_market_pit':False,'source_provider_changed':True,
            'schema_name_is_legacy_encoding_not_provider_claim':True,'files':{},'errors':{},'state':'RUNNING',
            'caveats':['Original candidate pool selected partly by current liquidity; historical selection bias remains.',
                'Split-adjusted history is not a vintage corporate-action dataset.',
                'No ticker rename stitching (asof=-); no fabricated pre-listing bars.',
                'Factory queue and blind hypothesis remain untouched pending data acceptance.']}
    # Freeze the original acceptance/membership artifacts byte-for-byte. Their
    # observed spans describe the original snapshot; refreshed spans live in the
    # new manifest. The consumer uses only symbols/delisting and bar existence.
    for name in ('membership_intervals.json','universe.json','ticker_reference.json'):
        dest=out/name
        if dest.exists() and dest.read_bytes()!=(source/name).read_bytes():raise ValueError('frozen_metadata_changed')
        if not dest.exists():shutil.copy2(source/name,dest)
    for index,symbol in enumerate(symbols):
        target=out/'bars'/f'{symbol}.json'
        if symbol in manifest['files']:
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=manifest['files'][symbol]['sha256']:
                raise ValueError('resume_file_changed:'+symbol)
            continue
        if shutil.disk_usage(out).free<50*1024**3:raise ValueError('disk_guard_50gb')
        try:
            rows=[];token='';page=0;tokens=set();page_receipts=[]
            while True:
                params={'timeframe':'1Day','start':args.start+'T00:00:00Z','end':args.end+'T23:59:59Z',
                    'feed':'sip','adjustment':'split','asof':'-','limit':10000,'sort':'asc'}
                if token:params['page_token']=token
                url='https://data.alpaca.markets/v2/stocks/'+urllib.parse.quote(symbol,safe='')+'/bars?'+urllib.parse.urlencode(params)
                page_path=raw/f'{symbol}.{page}.json'
                if page_path.exists():body=page_path.read_bytes()
                else:
                    for attempt in range(3):
                        try:
                            with opener.open(urllib.request.Request(url,headers=headers,method='GET'),timeout=25) as response:body=response.read(8*1024*1024+1)
                            break
                        except urllib.error.HTTPError as exc:
                            if exc.code not in (429,500,502,503,504) or attempt==2:raise
                            time.sleep(2**(attempt+1))
                    if len(body)>8*1024*1024:raise ValueError('response_size_limit')
                    page_path.write_bytes(body);page_path.chmod(0o600);time.sleep(.40)
                payload=json.loads(body)
                if payload.get('symbol')!=symbol or not isinstance(payload.get('bars'),(list,type(None))):raise ValueError('provider_symbol_or_bars_mismatch')
                rows.extend(payload.get('bars') or []);page_receipts.append({'file':page_path.name,'sha256':hashlib.sha256(body).hexdigest()})
                token=payload.get('next_page_token')
                if not token:break
                if token in tokens or page>=9:raise ValueError('pagination_loop_or_budget')
                tokens.add(token);page+=1
            records=normalize(rows,start,end)
            doc={'schema_id':'massive_adjusted_daily_symbol_v1','authority':AUTHORITY,'symbol':symbol,
                'start':args.start,'end':args.end,'adjusted':True,'records':records,'payload_sha256':_canonical_sha(records),
                'first_bar_ms':records[0]['t'] if records else None,'last_bar_ms':records[-1]['t'] if records else None}
            _atomic_json(target,doc)
            manifest['files'][symbol]={'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bars':len(records),
                'zero_trade_rows':sum(r['v']==0 and r['n']==0 for r in records),
                'first_bar_ms':doc['first_bar_ms'],'last_bar_ms':doc['last_bar_ms'],'raw_pages':page_receipts}
            manifest['errors'].pop(symbol,None)
        except Exception as exc:
            # Do not print credentials, URLs with tokens, or raw HTTP bodies.
            manifest['errors'][symbol]={'type':type(exc).__name__,'http':getattr(exc,'code',None)}
            if isinstance(exc,ValueError):manifest['errors'][symbol]['validation_reason']=str(exc)
            if isinstance(exc,urllib.error.HTTPError) and exc.code in (401,403):
                manifest['state']='BLOCKED_PROVIDER';_atomic_json(manifest_path,manifest);raise RuntimeError('data_provider_access_blocked') from None
        manifest['updated_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        _atomic_json(manifest_path,manifest)
        if (index+1)%50==0:print(json.dumps({'completed':len(manifest['files']),'requested':len(symbols),'errors':len(manifest['errors'])}),flush=True)
    manifest['state']='FETCH_COMPLETE' if not manifest['errors'] else 'FETCH_INCOMPLETE'
    _atomic_json(manifest_path,manifest)
    print(json.dumps({'state':manifest['state'],'completed':len(manifest['files']),'requested':len(symbols),'errors':len(manifest['errors'])}),flush=True)
    return 0 if not manifest['errors'] else 2

if __name__=='__main__':raise SystemExit(main())
