import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from research_lab import alpaca_monthly_source_ops_v1 as ops


def ms(s):
    return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)


@pytest.fixture
def cache(tmp_path):
    days=[];day=date(2026,10,30)
    while len(days)<200:
        if day.weekday()<5:days.append(day.isoformat())
        day-=timedelta(days=1)
    days=list(reversed(days))
    raw=[dict(date=d,open='09:30',close='16:00') for d in days+['2026-11-02']]
    cal=ops.normalize_calendar(raw)
    files={}
    for sym in ops.required_symbols():
        p=tmp_path/(sym+'_M5.csv')
        with p.open('w') as f:
            w=csv.writer(f);w.writerow(['ts','o','h','l','c','v'])
            for r in cal[:-1]:
                for t in range(r['open_ms']//1000,r['close_ms']//1000,3600):
                    w.writerow([t,100,103,99,102,1000])
        files[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    cap=dict(schema=ops.CAPTURE_SCHEMA,files=files,started_ms=ms('2026-10-30T20:10:00Z'),
             completed_ms=ms('2026-10-30T20:11:00Z'),fetcher_sha256=ops.SOURCE_PINS['scripts/fetch_equities_yfinance.py'],
             interval='1h',period='2y',prepost=False,auto_adjust=False,returncode=0)
    return tmp_path,cal,cap


def test_full_57_plus_spy_produces_closed_source_with_no_money_authority(cache):
    p,c,m=cache;r=ops.compile_source(p,m,c,now_ms=ms('2026-10-30T20:12:00Z'))
    assert len(r['history'])==58 and len(r['history']['SPY'])==200
    assert r['status']=='DATA_READY' and not r['orders_allowed'] and not r['money_authority']
    assert r['signal_session']=='2026-10-30' and r['entry_session']=='2026-11-02'
    assert r['month_end'] is True


@pytest.mark.parametrize('defect',['missing_symbol','missing_hour','nonfinite','hash','future','partial','calendar_gap'])
def test_incomplete_source_fails_closed_with_symbol_evidence(cache,defect):
    p,c,m=cache
    if defect=='missing_symbol':(p/'AMD_M5.csv').unlink()
    if defect in ['missing_hour','nonfinite']:
        f=p/'AMD_M5.csv';lines=f.read_text().splitlines()
        if defect=='missing_hour':lines.pop(-1)
        else:lines[-1]=lines[-1].replace(',100,',',nan,',1)
        f.write_text('\n'.join(lines)+'\n');m['files'][f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
    if defect=='hash':m['files']['AMD_M5.csv']='a'*64
    if defect=='future':m['completed_ms']=ms('2026-10-30T20:13:00Z')
    if defect=='partial':m['started_ms']=ms('2026-10-30T19:59:00Z')
    if defect=='calendar_gap':c=[r for r in c if r['session']!='2026-10-29']
    with pytest.raises(ops.SourceBlocked):ops.compile_source(p,m,c,now_ms=ms('2026-10-30T20:12:00Z'))


def test_schedule_uses_new_york_dst_and_half_day_calendar():
    c=ops.normalize_calendar([dict(date='2026-10-30',open='09:30',close='16:00'),
      dict(date='2026-11-02',open='09:30',close='16:00'),dict(date='2026-11-27',open='09:30',close='13:00')])
    r=ops.schedule(c,now_ms=ms('2026-10-30T20:21:00Z'))
    assert r['entry_open_ms']==ms('2026-11-02T14:30:00Z')
    assert r['monthly_selection_due'] is True
    assert ops.schedule(c,now_ms=ms('2026-11-27T18:19:00Z'))['daily_due'] is False
    assert ops.schedule(c,now_ms=ms('2026-11-27T18:21:00Z'))['daily_due'] is True


def test_source_receipt_is_idempotent_and_revised_capture_cannot_replace_it(cache,tmp_path):
    p,c,m=cache;r=ops.compile_source(p,m,c,now_ms=ms('2026-10-30T20:12:00Z'))
    root=tmp_path/'ops';a=ops.bind_source(root,r,now_ms=ms('2026-10-30T20:12:00Z'))
    b=ops.bind_source(root,r,now_ms=ms('2026-10-30T20:13:00Z'))
    assert a['source_id']==b['source_id'] and b['already_bound'] is True
    assert a['selection_id']==b['selection_id']
    revised=json.loads(json.dumps(r));revised['source_available_ms']+=1
    with pytest.raises(ops.SourceBlocked):ops.bind_source(root,revised,now_ms=ms('2026-10-30T20:14:00Z'))
    assert not a['orders_allowed'] and not a['money_authority']


def test_source_cache_parent_symlink_is_rejected(cache,tmp_path):
    p,c,m=cache;alias=tmp_path/'alias';alias.symlink_to(p,target_is_directory=True)
    with pytest.raises(ops.SourceBlocked):ops.compile_source(alias,m,c,now_ms=ms('2026-10-30T20:12:00Z'))


def test_calendar_range_uses_only_fixed_get_without_weakening_day_observer(tmp_path,monkeypatch):
    from scripts.run_alpaca_monthly_source_ops_v1 import calendar_capture
    from research_lab.alpaca_day_monitor_v1 import GetReader
    p=tmp_path/'calendar.env';p.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\nALPACA_API_KEY_ID=fixture\nALPACA_API_SECRET_KEY=fixture\n')
    seen=[]
    def fake(self,request):
        seen.append(request);return b'[]'
    monkeypatch.setattr(GetReader,'_open',fake)
    r=calendar_capture(p,ms('2026-10-17T13:30:00Z'))
    assert r['method']=='GET' and len(seen)==1
    assert seen[0].get_method()=='GET' and seen[0].data is None
    assert seen[0].full_url.startswith('https://api.alpaca.markets/v2/calendar?start=')


def test_schedule_does_not_recapture_previous_session_before_today_closes():
    c=ops.normalize_calendar([dict(date='2026-10-16',open='09:30',close='16:00'),
                             dict(date='2026-10-19',open='09:30',close='16:00')])
    assert not ops.schedule(c,now_ms=ms('2026-10-19T17:20:00Z'))['daily_due']


def test_package_pin_rejects_modified_source_before_any_calendar_request(tmp_path):
    from scripts import run_alpaca_monthly_source_ops_v1 as cli
    p=tmp_path/'spec.json';p.write_text(json.dumps(dict(schema='ALPACA_SOURCE_OPS_PACKAGE_V1',
        orders_allowed=False,money_authority=False,files={'missing.py':'a'*64})))
    with pytest.raises(ops.SourceBlocked):cli.verify_package(p,ops.sha(p))


def test_cli_binds_to_separate_book_inside_capture_runtime(cache,tmp_path,monkeypatch,capsys):
    from scripts import run_alpaca_monthly_source_ops_v1 as cli
    from datetime import datetime
    p,c,m=cache
    (p/'capture.json').write_text(json.dumps(m))
    raw=[dict(date=r['session'],open='09:30',close='16:00') for r in c]
    cp=tmp_path/'calendar.json'
    cp.write_text(json.dumps(dict(schema='BROKER_CALENDAR_GET_CAPTURE_V1',method='GET',
      endpoint='/v2/calendar?start=2026-01-01&end=2026-11-02',started_ms=ms('2026-10-30T20:09:00Z'),
      completed_ms=ms('2026-10-30T20:09:01Z'),body=raw)))
    monkeypatch.setattr(cli.time,'time_ns',lambda:ms('2026-10-30T20:21:00Z')*1000000)
    runtime=tmp_path/'runtime';(runtime/'captures').mkdir(parents=True)
    assert cli.main(['--runtime',str(runtime),'--calendar-source',str(cp),
       '--calendar-source-sha256',ops.sha(cp),'--cache',str(p),'--bind-orders-off'])==0
    out=json.loads(capsys.readouterr().out)
    assert out['status']=='ORDERS_OFF_OPERATIONAL_PASS'
    assert (runtime/'book/monthly-orders-off.sqlite').exists() and not out['orders_allowed']
