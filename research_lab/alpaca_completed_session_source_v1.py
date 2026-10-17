"""Completed RTH source using the exact frozen hourly loader; no order API.

Daily management uses the baseline's existing Yahoo unadjusted/RTH hourly
capture and UTC-day aggregation, never an intraday broker mark or a substituted
IEX/SIP daily close. Broker calendar only supplies real session/DST boundaries.
"""
import csv
from datetime import date,datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from research_lab.alpaca_dynamic_v1 import digest,instant,positive
from research_lab.alpaca_strategy_parity_v1 import _calendar
from scripts.build_equities_monthly_live_cycle import _aggregate_daily

ROOT=Path(__file__).resolve().parents[1]
SOURCE_PINS={
 'scripts/fetch_equities_yfinance.py':'44444e2244441c4dca84301727c9d37f30ff6921fa42a7fd3fb9d4676ef5adbd',
 'scripts/build_equities_monthly_live_cycle.py':'36fa73e2f6868f87a512f9c9f7196df9365657ecb60d1304d6986288942d51c2',
 'forex/data.py':'5bc4781af898206783319cb200ff04c2d9d43f5ae522db9385d5dd017eeda341'}


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_pins():
    for name,expected in SOURCE_PINS.items():
        if sha(ROOT/name)!=expected:raise ValueError('FROZEN_HOURLY_LOADER_CONFLICT:'+name)


def normalize_calendar(raw):
    rows=[]
    for r in raw:
        day=date.fromisoformat(r['date'])
        def stamp(field):
            d=datetime.fromisoformat(day.isoformat()+'T'+r[field])
            if d.tzinfo is not None:raise ValueError('CALENDAR_LOCAL_TIME_REQUIRED')
            return int(d.replace(tzinfo=ZoneInfo('America/New_York')).timestamp()*1000)
        rows.append(dict(session=day.isoformat(),open_ms=stamp('open'),close_ms=stamp('close')))
    _calendar(rows)
    return rows


def from_cache(directory,symbols,calendar,manifest,*,now_ms):
    check_pins();_calendar(calendar);now=instant(now_ms)
    if (not 1<=len(symbols)<=4 or len(set(symbols))!=len(symbols)
        or any(not re.fullmatch('[A-Z0-9.]{1,16}',s) for s in symbols)):
        raise ValueError('DAILY_SYMBOL_SCOPE')
    if (manifest['schema']!='ALPACA_FROZEN_HOURLY_CACHE_CAPTURE_V1'
        or manifest['fetcher_sha256']!=SOURCE_PINS['scripts/fetch_equities_yfinance.py']
        or manifest['interval']!='1h' or manifest['prepost'] is not False
        or manifest['auto_adjust'] is not False
        or not instant(manifest['started_ms'])<=instant(manifest['completed_ms'])<=now):
        raise ValueError('FROZEN_CACHE_CAPTURE_CONTRACT')
    closed=[r for r in calendar if r['close_ms']<=now]
    if not closed:raise ValueError('NO_COMPLETED_SESSION')
    target=closed[-1]
    if manifest['started_ms']<target['close_ms']:raise ValueError('PARTIAL_DAILY_SOURCE')
    expected=list(range(target['open_ms']//1000,target['close_ms']//1000,3600))
    normalized=[];excluded=set();raw_files={}
    for symbol in symbols:
        name=symbol+'_M5.csv';p=Path(directory)/name
        if (p.is_symlink() or not p.is_file() or p.stat().st_size>4_000_000
            or name not in manifest['files'] or sha(p)!=manifest['files'][name]):
            raise ValueError('FROZEN_CACHE_FILE_CONFLICT:'+symbol)
        raw_files[name]=manifest['files'][name];times=[];previous=None
        with p.open() as f:
            for row in csv.DictReader(f):
                t=int(row['ts'])
                if previous is not None and t<=previous:raise ValueError('CACHE_BAR_TIME_CONFLICT')
                previous=t
                o,h,l,c=(float(positive(row[k])) for k in ('o','h','l','c'))
                if not l<=min(o,c)<=max(o,c)<=h:raise ValueError('CACHE_OHLC_INVALID')
                day=datetime.fromtimestamp(t,ZoneInfo('UTC')).date().isoformat()
                if day>target['session']:excluded.add(day)
                if day==target['session']:times.append(t)
        if times!=expected:raise ValueError('INCOMPLETE_REGULAR_SESSION:'+symbol)
        bar=next((b for b in _aggregate_daily(p) if b.day==target['session']),None)
        if bar is None:raise ValueError('COMPLETED_BAR_UNKNOWN:'+symbol)
        normalized.append(dict(symbol=symbol,session=bar.day,open=bar.o,high=bar.h,low=bar.l,close=bar.c))
    return dict(schema='ALPACA_COMPLETED_SESSION_SOURCE_V1',calendar=calendar,
        source='ALPACA_FROZEN_HOURLY_REGULAR_SESSION_V1',raw=normalized,raw_sha256=digest(normalized),
        available_ms=manifest['completed_ms'],completed_ms=manifest['completed_ms'],
        cache_capture=manifest,cache_files=raw_files,loader_sha256=SOURCE_PINS,
        excluded_later_sessions=sorted(excluded),broker_writes=0,orders_allowed=False,money_authority=False)


def capture_cache(directory,symbols):
    """One bounded public-data fetch into a NEW directory; no retries/overwrite.

    Invokes the existing frozen fetcher with its baseline options, preserving
    raw CSVs, stdout/stderr and exact actual invocation/completion timestamps.
    This is not an account reader, manager or prospective outcome evaluator.
    """
    check_pins()
    if not symbols or any(not re.fullmatch('[A-Z0-9.]{1,16}',s) for s in symbols):raise ValueError('DAILY_SYMBOL_SCOPE')
    directory=Path(directory).absolute();directory.mkdir(mode=0o700)
    started=time.time_ns()//1_000_000
    args=[sys.executable,str(ROOT/'scripts/fetch_equities_yfinance.py'),'--tickers',','.join(symbols),
          '--period','5d','--interval','1h','--out-dir',str(directory)]
    r=subprocess.run(args,capture_output=True,timeout=180)
    completed=time.time_ns()//1_000_000
    (directory/'fetch.stdout').write_bytes(r.stdout);(directory/'fetch.stderr').write_bytes(r.stderr)
    if r.returncode or any(not (directory/(s+'_M5.csv')).is_file() for s in symbols):
        raise ValueError('FROZEN_FETCH_FAILED_OR_INCOMPLETE')
    manifest=dict(schema='ALPACA_FROZEN_HOURLY_CACHE_CAPTURE_V1',
        fetcher_sha256=SOURCE_PINS['scripts/fetch_equities_yfinance.py'],interval='1h',prepost=False,auto_adjust=False,
        started_ms=started,completed_ms=completed,
        files={s+'_M5.csv':sha(directory/(s+'_M5.csv')) for s in symbols})
    with (directory/'capture.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
    return manifest
