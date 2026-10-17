import csv
import hashlib
from datetime import datetime,timezone
from pathlib import Path
import pytest
from research_lab import alpaca_completed_session_source_v1 as source


def ms(s):return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)


def test_real_calendar_dst_and_half_day_are_used_instead_of_fixed_utc_hours():
    rows=source.normalize_calendar([dict(date='2026-10-30',open='09:30',close='16:00'),
        dict(date='2026-11-02',open='09:30',close='16:00'),dict(date='2026-11-27',open='09:30',close='13:00')])
    assert rows[0]['open_ms']==ms('2026-10-30T13:30:00Z')
    assert rows[1]['open_ms']==ms('2026-11-02T14:30:00Z')
    assert rows[2]['close_ms']==ms('2026-11-27T18:00:00Z')


@pytest.fixture
def bundle(tmp_path):
    p=tmp_path/'NET_M5.csv'
    with p.open('w') as f:
        w=csv.writer(f);w.writerow(['ts','o','h','l','c','v'])
        for h in range(7):w.writerow([ms('2026-10-15T13:30:00Z')//1000+h*3600,100+h,102+h,99+h,101+h,1000])
        # Later current-session bar is retained raw, but must not enter Oct15.
        w.writerow([ms('2026-10-16T13:30:00Z')//1000,500,600,400,550,1000])
    calendar=source.normalize_calendar([dict(date=d,open='09:30',close='16:00')
        for d in ['2026-10-14','2026-10-15','2026-10-16','2026-10-19']])
    manifest=dict(schema='ALPACA_FROZEN_HOURLY_CACHE_CAPTURE_V1',
        fetcher_sha256=hashlib.sha256(Path('scripts/fetch_equities_yfinance.py').read_bytes()).hexdigest(),
        interval='1h',prepost=False,auto_adjust=False,
        started_ms=ms('2026-10-16T14:59:00Z'),completed_ms=ms('2026-10-16T15:00:00Z'),
        files={'NET_M5.csv':hashlib.sha256(p.read_bytes()).hexdigest()})
    return tmp_path,calendar,manifest


def test_exact_frozen_loader_and_completed_day_only(bundle):
    p,c,m=bundle
    build=getattr(source,'from_cache',lambda *a,**kw:None)
    r=build(p,['NET'],c,m,now_ms=ms('2026-10-16T15:00:01Z'))
    assert r and r['raw']==[dict(symbol='NET',session='2026-10-15',open=100.,high=108.,low=99.,close=107.)]
    assert r['source']=='ALPACA_FROZEN_HOURLY_REGULAR_SESSION_V1'
    assert r['excluded_later_sessions']==['2026-10-16']
    assert r['broker_writes']==0


@pytest.mark.parametrize('change',['hash','missing','early','future','adjustment','fetcher'])
def test_incomplete_or_unbound_cache_never_becomes_a_close(bundle,change):
    p,c,m=bundle;now=ms('2026-10-16T15:00:01Z')
    if change=='hash':m['files']['NET_M5.csv']='a'*64
    if change=='missing':m['files']={}
    if change=='early':m['started_ms']=m['completed_ms']=ms('2026-10-15T19:59:00Z')
    if change=='future':m['completed_ms']=now+1000
    if change=='adjustment':m['auto_adjust']=True
    if change=='fetcher':m['fetcher_sha256']='b'*64
    with pytest.raises(ValueError):source.from_cache(p,['NET'],c,m,now_ms=now)


def test_missing_hour_is_unknown_instead_of_synthetic_close(bundle):
    p,c,m=bundle;file=p/'NET_M5.csv';lines=file.read_text().splitlines();file.write_text('\n'.join(lines[:3]+lines[4:])+'\n')
    m['files']['NET_M5.csv']=hashlib.sha256(file.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='INCOMPLETE_REGULAR_SESSION'):
        source.from_cache(p,['NET'],c,m,now_ms=ms('2026-10-16T15:00:01Z'))
