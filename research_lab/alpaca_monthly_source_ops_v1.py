"""Full frozen monthly universe and calendar-driven source operations, ORDERS_OFF.

Uses the existing frozen fetcher/aggregator and MonthlyBook. No order client,
native sender, account position adoption, risk policy or financial activation.
The isolated source book may create intentions only. Installed NET/V3 untouched.
"""
import csv
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

from research_lab.alpaca_completed_session_source_v1 import (
    SOURCE_PINS, check_pins, normalize_calendar, from_cache,
)
from research_lab.alpaca_strategy_parity_v1 import source_pins, _calendar
from research_lab.alpaca_dynamic_v1 import digest, instant
from research_lab.alpaca_monthly_binding_v1 import MonthlyBook, CONTRACT
from scripts.build_equities_monthly_live_cycle import _aggregate_daily
from scripts.run_alpaca_dynamic_v1_orders_off import load_history

ROOT=Path(__file__).resolve().parents[1]
CAPTURE_SCHEMA='ALPACA_MONTHLY_FULL_UNIVERSE_CAPTURE_V1'
SCHEMA='ALPACA_MONTHLY_FULL_UNIVERSE_SOURCE_V1'
MIN_SESSIONS=200


class SourceBlocked(ValueError):
    def __init__(self,issues):
        self.issues=issues if isinstance(issues,list) else [str(issues)]
        super().__init__(';'.join(self.issues[:8]))


def safe_path(path):
    p=Path(path).absolute()
    if any(q.is_symlink() for q in (p,*p.parents)):raise SourceBlocked('SYMLINK_PATH')
    return p


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def required_symbols():
    source_pins()
    c=json.loads((ROOT/'configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json').read_bytes())
    symbols=next(w['symbols'] for w in c['windows'] if w['id']=='live_universe_2024_2026_cached_intraday_proxy')
    if len(symbols)!=57 or len(set(symbols))!=57:raise SourceBlocked('FROZEN_UNIVERSE_CONFLICT')
    return tuple(sorted(set(symbols)|{'SPY'}))


def schedule(calendar,*,now_ms):
    _calendar(calendar);now=instant(now_ms)
    closed=[r for r in calendar if r['close_ms']<=now]
    current=closed[-1] if closed else None
    today=datetime.fromtimestamp(now/1000,ZoneInfo('America/New_York')).date().isoformat()
    nxt=next((r for r in calendar if current and r['open_ms']>current['close_ms']),None)
    future=[r['close_ms']+20*60000 for r in calendar if r['close_ms']+20*60000>now]
    return dict(signal_session=current['session'] if current else None,
      entry_session=nxt['session'] if nxt else None,entry_open_ms=nxt['open_ms'] if nxt else None,
      daily_due=bool(current and current['session']==today and now>=current['close_ms']+20*60000),
      monthly_selection_due=bool(current and nxt and current['session'][:7]!=nxt['session'][:7]
                                and current['session']==today and now>=current['close_ms']+20*60000),
      month_end=bool(current and nxt and current['session'][:7]!=nxt['session'][:7]),
      next_source_run_ms=min(future) if future else None,orders_allowed=False,money_authority=False)


def compile_source(directory,capture,calendar,*,now_ms):
    """Validate ALL names and closed calendar sessions before returning history."""
    check_pins();directory=safe_path(directory);now=instant(now_ms)
    try:
        plan=schedule(calendar,now_ms=now)
        closed=[r for r in calendar if r['close_ms']<=now]
        if len(closed)<MIN_SESSIONS or not plan['entry_session']:raise SourceBlocked('CALENDAR_WARMUP_OR_NEXT_SESSION_MISSING')
        target=closed[-1];window=closed[-MIN_SESSIONS:]
        if (capture['schema']!=CAPTURE_SCHEMA or capture['fetcher_sha256']!=SOURCE_PINS['scripts/fetch_equities_yfinance.py']
          or capture['interval']!='1h' or capture['period']!='2y' or capture['prepost'] is not False
          or capture['auto_adjust'] is not False or capture['returncode']!=0
          or not target['close_ms']<=instant(capture['started_ms'])<=instant(capture['completed_ms'])<=now):
            raise SourceBlocked('CAPTURE_IDENTITY_OR_TIME')
        names={s+'_M5.csv' for s in required_symbols()}
        if set(capture['files'])!=names:raise SourceBlocked('FULL_UNIVERSE_MANIFEST_COVERAGE')
        expected={r['session']:list(range(r['open_ms']//1000,r['close_ms']//1000,3600)) for r in window}
        history={};coverage={};issues=[];excluded=set()
        for symbol in required_symbols():
            p=safe_path(directory/(symbol+'_M5.csv'))
            try:
                if not p.is_file() or p.stat().st_size>8_000_000 or sha(p)!=capture['files'][p.name]:
                    raise SourceBlocked('RAW_FILE_MISSING_OR_HASH')
                times={d:[] for d in expected};previous=None
                with p.open() as f:
                    reader=csv.DictReader(f)
                    if reader.fieldnames!=['ts','o','h','l','c','v']:raise SourceBlocked('RAW_SCHEMA')
                    for row in reader:
                        t=int(row['ts']);values=[float(row[k]) for k in ('o','h','l','c','v')]
                        o,h,l,c,v=values
                        if (previous is not None and t<=previous) or not all(math.isfinite(x) for x in values):
                            raise SourceBlocked('RAW_TIME_OR_NONFINITE')
                        if min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:raise SourceBlocked('RAW_OHLCV')
                        previous=t
                        day=datetime.fromtimestamp(t,timezone.utc).date().isoformat()
                        if day>target['session']:excluded.add(day)
                        if day in times:times[day].append(t)
                        elif window[0]['session']<=day<=target['session']:raise SourceBlocked('BAR_WITHOUT_CALENDAR_SESSION')
                missing=[d for d in expected if times[d]!=expected[d]]
                if missing:raise SourceBlocked('INCOMPLETE_RTH:'+','.join(missing[:5]))
                bars=[b for b in _aggregate_daily(p) if b.day<=target['session']]
                if sha(p)!=capture['files'][p.name]:raise SourceBlocked('RAW_FILE_CHANGED_DURING_READ')
                history[symbol]=[dict(session=b.day,open=b.o,high=b.h,low=b.l,close=b.c) for b in bars]
                coverage[symbol]=dict(completed_sessions=len(bars),latest_session=bars[-1].day,
                                     fully_verified_sessions=MIN_SESSIONS)
            except (ValueError,KeyError,TypeError,OSError) as exc:
                issues.append(symbol+':'+str(exc)[:250])
        if issues:raise SourceBlocked(issues)
        out=dict(schema=SCHEMA,status='DATA_READY',history=history,calendar=calendar,
          signal_session=target['session'],entry_session=plan['entry_session'],month_end=plan['month_end'],
          source_available_ms=capture['completed_ms'],cache_capture=capture,coverage=coverage,
          cache_root=str(directory),calendar_sha256=digest(calendar),source_code_sha256=source_pins(),
          excluded_later_sessions=sorted(excluded),orders_allowed=False,money_authority=False,broker_writes=0)
        out['source_id']=digest(out)
        return out
    except SourceBlocked:raise
    except (ValueError,KeyError,TypeError,OSError) as exc:raise SourceBlocked(str(exc)) from exc


def capture_full(directory,*,clock=lambda:time.time_ns()//1000000):
    """One new immutable public fetch, no retry and no pre-existing directory."""
    check_pins();symbols=required_symbols();directory=safe_path(directory)
    directory.mkdir(mode=0o700)
    started=clock()
    args=[sys.executable,str(ROOT/'scripts/fetch_equities_yfinance.py'),'--tickers',','.join(symbols),
          '--period','2y','--interval','1h','--out-dir',str(directory)]
    try:
        result=subprocess.run(args,capture_output=True,timeout=600)
        rc=result.returncode;stdout=result.stdout;stderr=result.stderr
    except subprocess.TimeoutExpired as exc:
        rc=124;stdout=exc.stdout or b'';stderr=exc.stderr or b''
    (directory/'fetch.stdout').write_bytes(stdout);(directory/'fetch.stderr').write_bytes(stderr)
    capture=dict(schema=CAPTURE_SCHEMA,started_ms=started,completed_ms=clock(),
      fetcher_sha256=SOURCE_PINS['scripts/fetch_equities_yfinance.py'],interval='1h',period='2y',
      prepost=False,auto_adjust=False,returncode=rc,
      files={p.name:sha(p) for p in directory.glob('*_M5.csv') if p.is_file() and not p.is_symlink()})
    with (directory/'capture.json').open('x') as f:json.dump(capture,f,sort_keys=True,indent=2);f.write('\n')
    return capture


def bind_source(root,bundle,*,now_ms):
    """Own local book only; never binds real fills or invokes native maintenance."""
    root=safe_path(root)
    if bundle.get('source_id')!=digest({k:v for k,v in bundle.items() if k!='source_id'}):
        raise SourceBlocked('SOURCE_BUNDLE_HASH')
    if bundle.get('schema')!=SCHEMA or bundle.get('orders_allowed') is not False or bundle.get('money_authority') is not False:
        raise SourceBlocked('ORDERS_OFF_SOURCE_REQUIRED')
    rebuilt=compile_source(bundle['cache_root'],bundle['cache_capture'],bundle['calendar'],now_ms=now_ms)
    if rebuilt!=bundle:raise SourceBlocked('SOURCE_BUNDLE_DERIVATION')
    marker=safe_path(root/'source-ops-v1.json')
    if root.exists() and any(root.iterdir()) and not marker.is_file():raise SourceBlocked('FOREIGN_RUNTIME_ROOT')
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not marker.exists():
        with marker.open('x') as f:json.dump(dict(schema='ALPACA_SOURCE_OPS_V1',orders_allowed=False),f)
    if json.loads(marker.read_text())!={'schema':'ALPACA_SOURCE_OPS_V1','orders_allowed':False}:
        raise SourceBlocked('RUNTIME_IDENTITY_CONFLICT')
    lock=os.open(root/'writer.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipts=root/'receipts';receipts.mkdir(exist_ok=True,mode=0o700)
        path=safe_path(receipts/(bundle['signal_session']+'.json'))
        if path.exists():
            old=json.loads(path.read_bytes())
            if (old.get('receipt_sha256')!=digest({k:v for k,v in old.items() if k!='receipt_sha256'})
              or old['source_id']!=bundle['source_id']):raise SourceBlocked('SESSION_SOURCE_REVISION')
            return {**old,'already_bound':True}
        book=MonthlyBook(root/'monthly-orders-off.sqlite',CONTRACT)
        selection=None;daily=None
        if bundle['month_end']:
            selection=book.seal_selection(load_history(bundle['history']),bundle['calendar'],
                signal_session=bundle['signal_session'],entry_session=bundle['entry_session'],
                source_available_ms=bundle['source_available_ms'],source_sha256=bundle['source_id'],now_ms=now_ms)
        positions=book.rows('positions')
        if positions:
            symbols=sorted(p['symbol'] for p in positions)
            cap=dict(bundle['cache_capture']);cap['schema']='ALPACA_FROZEN_HOURLY_CACHE_CAPTURE_V1'
            daily=book.observe_close(from_cache(bundle['cache_root'],symbols,bundle['calendar'],cap,now_ms=now_ms),now_ms=now_ms)
        out=dict(schema='ALPACA_SOURCE_OPERATION_RECEIPT_V1',status='ORDERS_OFF_OPERATIONAL_PASS',
          source_id=bundle['source_id'],signal_session=bundle['signal_session'],
          selection_id=selection['selection_id'] if selection else None,
          daily_status=daily['status'] if daily else 'NO_OWNED_MONTHLY_POSITIONS',
          next_schedule=schedule(bundle['calendar'],now_ms=now_ms),already_bound=False,
          orders_allowed=False,money_authority=False,broker_writes=0)
        out['receipt_sha256']=digest(out)
        raw=(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        tmp=safe_path(receipts/('.'+bundle['signal_session']+'.tmp'))
        fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        fd=os.open(receipts,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return out
    finally:os.close(lock)
