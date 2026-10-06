#!/usr/bin/env python3
"""One closed-data capture and first-window ranking. Public data + broker GETs.

No order methods, judge/outcomes, monthly-cache overwrite or LIVE configuration
changes. Native unattended mode has a fixed first-window deadline, no retries.
"""
import argparse
import csv
from datetime import date, datetime, timezone
import fcntl
import hashlib
from io import StringIO
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research_lab.alpaca_dynamic_v1 import DynamicBook, build_ranking, canonical, digest, positive, dec, policy_check, source_check
from research_lab.alpaca_dynamic_paper import earnings_check


def validate_hourly(policy, cache, session, captured_ms):
    policy_check(policy)
    row = next(r for r in policy['calendar_sessions'] if r['session'] == session)
    if captured_ms < row['close_ms']:
        raise ValueError('SESSION_NOT_CLOSED')
    cache = Path(cache)
    wanted = {s+'_M5.csv' for s in policy['universe']}
    if {p.name for p in cache.glob('*.csv')} != wanted:
        raise ValueError('INCOMPLETE_UNIVERSE')
    expected = set(range(row['open_ms']//1000, row['close_ms']//1000, 3600))
    history, pins = {}, {}
    for symbol in policy['universe']:
        path = cache/(symbol+'_M5.csv')
        if path.is_symlink() or path.stat().st_size > 8_000_000:
            raise ValueError('SOURCE_PATH_OR_SIZE')
        raw = path.read_bytes(); pins[path.name] = hashlib.sha256(raw).hexdigest()
        rows, last, actual = {}, None, set()
        for item in csv.DictReader(StringIO(raw.decode())):
            ts = int(item['ts'])
            if (last is not None and ts <= last) or ts >= row['close_ms']//1000:
                raise ValueError('UNORDERED_DUPLICATE_OR_FUTURE_BAR:'+symbol)
            last = ts
            o,h,l,c = (positive(item[k]) for k in ('o','h','l','c'))
            if not l <= min(o,c) <= max(o,c) <= h or dec(item['v']) < 0:
                raise ValueError('INVALID_OHLCV:'+symbol)
            day = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
            if day == session: actual.add(ts)
            if day not in rows:
                rows[day] = {'session':day,'open':str(o),'high':str(h),'low':str(l),'close':str(c)}
            else:
                rows[day].update(high=str(max(dec(rows[day]['high']),h)),low=str(min(dec(rows[day]['low']),l)),close=str(c))
        if actual != expected:
            raise ValueError('CLOSED_HOUR_COVERAGE:'+symbol)
        history[symbol] = list(rows.values())
    return {'history':history,'file_sha256':pins,'closed_session':session,'captured_ms':captured_ms}


def concentration_check(symbol, survivors, history):
    from scripts.alpaca_adaptive_paper import _frozen_clusters
    from strategies.alpaca_dynamic_v4_event import SECTOR_MAP
    from backtest.alpaca_honest_portfolio import _correlation
    if sum(SECTOR_MAP.get(s,'unknown')==SECTOR_MAP.get(symbol,'unknown') for s in survivors)>=2:
        return {'safe':False,'reason':'SECTOR_CAP'}
    if any(symbol in group and any(s in group for s in survivors) for group in _frozen_clusters()):
        return {'safe':False,'reason':'CLUSTER_CAP'}
    if not history.get(symbol) or any(not history.get(s) for s in survivors):
        return {'safe':False,'reason':'CONCENTRATION_SOURCE_UNKNOWN'}
    for held in survivors:
        corr = _correlation(history[symbol],history[held],60)
        if corr is None or not math.isfinite(corr):
            return {'safe':False,'reason':'CORRELATION_SOURCE_UNKNOWN','held':held}
        if corr>=.75:
            return {'safe':False,'reason':'CORRELATION_CAP','held':held,'correlation':corr}
    return {'safe':True,'reason':'FROZEN_CONCENTRATION_GATES'}


def exclusive(path, payload):
    raw = canonical(payload)
    with Path(path).open('xb') as f:
        f.write(raw);f.flush()
        import os
        os.fsync(f.fileno())
    Path(path).chmod(0o400)
    return hashlib.sha256(raw).hexdigest()


def capture(policy, runtime):
    prior = next(r for r in policy['calendar_sessions'] if r['session']=='2026-10-06')
    now = time.time_ns()//1_000_000
    if not prior['close_ms'] <= now < policy['first_window_ms']:
        raise ValueError('CLOSED_CAPTURE_WINDOW')
    import shutil
    if shutil.disk_usage(runtime).free<1_000_000_000:raise ValueError('SOURCE_DISK_BOUND')
    cache=runtime/'hourly';cache.mkdir()
    with (runtime/'fetch.log').open('xb') as log:
        p=subprocess.run([sys.executable,str(ROOT/'scripts/fetch_equities_yfinance.py'),
            '--tickers',','.join(policy['universe']),'--period','730d','--interval','60m','--out-dir',str(cache)],
            stdout=log,stderr=log,timeout=600)
    if p.returncode:raise ValueError('PUBLIC_DOWNLOAD_FAILED')
    data=validate_hourly(policy,cache,prior['session'],time.time_ns()//1_000_000)
    if len(data['history']['SPY'])<200:raise ValueError('SPY200_SOURCE_SHORT')
    import yfinance as yf
    earnings={}
    for symbol in policy['universe']:
        try:
            frame=yf.Ticker(symbol).get_earnings_dates(limit=12)
            dates=sorted({x.date().isoformat() for x in frame.index}) if frame is not None else []
            earnings[symbol]={'provider':'Yahoo via existing yfinance','dates':dates,'received_ms':time.time_ns()//1_000_000}
        except TimeoutError:
            raise  # a capture deadline must not be swallowed as one unknown date
        except Exception:
            earnings[symbol]={'provider':'Yahoo via existing yfinance','dates':[],'status':'UNKNOWN','received_ms':time.time_ns()//1_000_000}
    now=time.time_ns()//1_000_000
    if now>=policy['first_window_ms']:raise ValueError('CAPTURE_MISSED_DEADLINE')
    data.update(schema='ALPACA_DYNAMIC_CLOSED_SOURCE_V1',policy_sha256=digest(policy),
                earnings=earnings,received_ms=now,order_authority=False,broker_writes=0)
    for path in cache.glob('*.csv'):path.chmod(0o400)
    exclusive(runtime/'closed_source.json',data)
    return data


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('SOURCE_REDIRECT_REFUSED')


def live_read_only(policy, live_env, live_profile):
    """Exact established LIVE profile; authenticated GETs only, no client writer."""
    from dotenv import dotenv_values
    base=Path(live_env).absolute();lines=Path(live_profile).read_text().splitlines()
    if not lines or lines[0]!='source '+str(base):raise ValueError('LIVE_PROFILE_SOURCE_CONFLICT')
    env=dict(dotenv_values(base));env.update(dotenv_values(stream=StringIO('\n'.join(lines[1:]))))
    host='https://api.alpaca.markets'
    if env.get('ALPACA_BASE_URL','').rstrip('/')!=host:raise ValueError('READ_ONLY_LIVE_HOST_CONFLICT')
    opener=request.build_opener(request.ProxyHandler({}),NoRedirect())
    fields={'account':'/v2/account','clock':'/v2/clock','positions':'/v2/positions','open_orders':'/v2/orders?status=open&limit=100&nested=true'}
    raw={}
    for name,path in fields.items():
        req=request.Request(host+path,method='GET',headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
        with opener.open(req,timeout=7) as response:body=response.read(1_000_001)
        if len(body)>1_000_000:raise ValueError('BROKER_SOURCE_TOO_LARGE')
        raw[name]=json.loads(body)
    raw['observed_ms']=time.time_ns()//1_000_000
    if raw['account']['id']!=policy['account_id'] or len(raw['open_orders'])>=100:raise ValueError('BROKER_IDENTITY_OR_TRUNCATED_ORDERS')
    return raw


def first_window(policy,runtime,live_env,live_profile):
    data=json.loads((runtime/'closed_source.json').read_text())
    source_check(policy,policy['calendar_sessions'])
    now=time.time_ns()//1_000_000
    if (data['policy_sha256']!=digest(policy) or not data['captured_ms']<=data['received_ms']<=now
        or any(not data['captured_ms']<=e['received_ms']<=data['received_ms'] for e in data['earnings'].values())):
        raise ValueError('CAPTURE_POLICY_OR_RECEIVE_TIME_CONFLICT')
    checked=validate_hourly(policy,runtime/'hourly',data['closed_session'],data['captured_ms'])
    if checked['file_sha256']!=data['file_sha256'] or checked['history']!=data['history']:raise ValueError('CAPTURE_SOURCE_CHANGED')
    from scripts.run_alpaca_dynamic_v1_orders_off import load_history
    history=load_history(data['history'])
    truth=live_read_only(policy,live_env,live_profile)
    now=time.time_ns()//1_000_000
    if not policy['first_window_ms']<=now<policy['first_window_ms']+300000:raise ValueError('FIRST_WINDOW_MISSED')
    clock_ms=int(datetime.fromisoformat(truth['clock']['timestamp'].replace('Z','+00:00')).timestamp()*1000)
    if (truth['clock'].get('is_open') is not True or clock_ms>now+1000
        or now-clock_ms>policy['max_snapshot_age_ms']
        or not policy['first_window_ms']<=clock_ms<policy['first_window_ms']+300000):
        raise ValueError('MARKET_CLOCK_STALE_FUTURE_OR_CLOSED')
    slots={s['symbol']:s for s in policy['inherited_slots']}
    survivors=[p['symbol'] for p in truth['positions']]
    if len(survivors)!=len(set(survivors)) or any(p['symbol'] not in slots or positive(p['qty'])!=positive(slots[p['symbol']]['qty']) for p in truth['positions']):
        raise ValueError('UNOWNED_OR_CHANGED_SURVIVOR')
    if any(o.get('side')=='buy' for o in truth['open_orders']):raise ValueError('EXISTING_PENDING_ENTRY')
    # This initial source/ranking capture cannot prove cash/finality or create a
    # vacancy/intent. All inherited names remain excluded from initial ranking.
    gates={s:{'earnings':earnings_check(data['earnings'][s]['dates'],'2026-10-07'),
              'concentration':concentration_check(s,survivors,history)} for s in policy['universe'] if s!='SPY'}
    blocked=set(slots)|{s for s,g in gates.items() if not all(v['safe'] for v in g.values())}
    ranking=build_ranking(policy,policy['calendar_sessions'],history,blocked,digest(data['history']),data['captured_ms'],now)
    book=DynamicBook(runtime/'selection/replacement.sqlite',policy)
    now=time.time_ns()//1_000_000
    if not policy['first_window_ms']<=now<policy['first_window_ms']+300000:raise ValueError('FIRST_WINDOW_MISSED_AT_SEAL')
    book.seal_ranking(ranking,policy['calendar_sessions'],now)
    receipt={'schema':'ALPACA_DYNAMIC_FIRST_SOURCE_RECEIPT_V1','status':'ORDERS_OFF_RANKING_CAPTURED',
        'policy_sha256':digest(policy),'closed_source_sha256':digest(data),'captured_ms':now,
        'broker_truth':truth,'ranking':ranking,'gates':gates,'broker_writes':0,'money_authority':False,
        'paper_executed':False,'cash_finality_verified':False,'actual_fee_verified':False,
        'next_gate':'Exact current quote/sizing/cash-liability inputs → isolated PAPER lifecycle; separate LIVE GO'}
    exclusive(runtime/'first_window_receipt.json',receipt)
    return receipt


def wait_until(target_ms, deadline_ms):
    while time.time_ns()//1_000_000<target_ms:
        if time.time_ns()//1_000_000>=deadline_ms:raise ValueError('FIXED_DEADLINE_PASSED')
        time.sleep(min(30,max(.01,(target_ms-time.time_ns()//1_000_000)/1000)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',type=Path,default=ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json')
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--live-env',type=Path,required=True)
    parser.add_argument('--live-profile',type=Path,required=True)
    parser.add_argument('--unattended-first-window',action='store_true')
    args=parser.parse_args()
    policy=json.loads(args.policy.read_text());policy_check(policy);source_check(policy,policy['calendar_sessions'])
    if digest(policy)!='fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d':raise ValueError('SEALED_POLICY_CONFLICT')
    args.runtime.mkdir(parents=True,exist_ok=True)
    with (args.runtime/'writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if any((args.runtime/name).exists() for name in ['schedule.json','hourly','fetch.log','closed_source.json','terminal.json','first_window_receipt.json']):
            raise ValueError('EXISTING_ATTEMPT_NOT_RESTARTED')
        deadline=policy['first_window_ms']+300000
        exclusive(args.runtime/'schedule.json',{'capture_after_ms':1791317700000,'window_ms':policy['first_window_ms'],
            'deadline_ms':deadline,'policy_sha256':digest(policy),'broker_writes_allowed':False,'automatic_retry':False})
        try:
            if args.unattended_first_window:wait_until(1791317700000,deadline)  # Oct6 20:15 UTC
            signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('CAPTURE_900S_BOUND')))
            signal.alarm(900)
            capture(policy,args.runtime)
            signal.alarm(0)
            if args.unattended_first_window:wait_until(policy['first_window_ms'],deadline)
            receipt=first_window(policy,args.runtime,args.live_env,args.live_profile)
            terminal={'status':receipt['status'],'first_receipt_sha256':digest(receipt)}
        except Exception as exc:
            signal.alarm(0)
            terminal={'status':'BLOCKED_DATA','reason':type(exc).__name__+':'+str(exc)}
        terminal.update(observed_ms=time.time_ns()//1_000_000,broker_writes=0,money_authority=False,completed_48h_evidence=False)
        exclusive(args.runtime/'terminal.json',terminal)
        print(json.dumps(terminal))
        return 2 if terminal['status']=='BLOCKED_DATA' else 0


if __name__=='__main__':raise SystemExit(main())
