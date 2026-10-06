"""Causal data boundary for first Dynamic V1 source capture; no outcomes."""
import csv
import importlib
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
POLICY=json.loads((ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_text())
DAY=next(r for r in POLICY['calendar_sessions'] if r['session']=='2026-10-06')

@pytest.fixture
def api():
    try:return importlib.import_module('scripts.run_alpaca_dynamic_capture')
    except ImportError:return None

def cache(path, *, omit=None, duplicate=None, future=False):
    for symbol in POLICY['universe']:
        stamps=list(range(DAY['open_ms']//1000,DAY['close_ms']//1000,3600))
        if omit==symbol:stamps.pop()
        if duplicate==symbol:stamps.append(stamps[-1])
        if future:stamps.append(DAY['close_ms']//1000)
        with (path/f'{symbol}_M5.csv').open('w') as f:
            w=csv.writer(f);w.writerow(['ts','o','h','l','c','v'])
            for ts in stamps:w.writerow([ts,100,102,99,101,1000])

def test_closed_session_full_hour_coverage_and_source_hashes(api,tmp_path):
    assert api is not None,'closed-data collector missing'
    cache(tmp_path)
    r=api.validate_hourly(POLICY,tmp_path,'2026-10-06',DAY['close_ms']+1000)
    assert len(r['file_sha256'])==59 and len(r['history'])==59
    assert r['history']['SPY'][-1]['session']=='2026-10-06'

@pytest.mark.parametrize('kind',['missing_hour','duplicate','future','not_closed'])
def test_partial_duplicate_future_or_current_bars_never_become_closed_source(api,tmp_path,kind):
    assert api is not None
    cache(tmp_path,omit='NET' if kind=='missing_hour' else None,duplicate='SPY' if kind=='duplicate' else None,future=kind=='future')
    with pytest.raises(ValueError):api.validate_hourly(POLICY,tmp_path,'2026-10-06',DAY['close_ms']-1 if kind=='not_closed' else DAY['close_ms']+1000)

def test_concentration_is_against_actual_survivors_not_just_ranked_picks(api):
    assert api is not None
    # Existing two tech holdings disallow another tech name without rescaling them.
    assert api.concentration_check('NVDA',['MSFT','META'],{})['safe'] is False


def test_missing_correlation_overlap_is_unknown_not_safe(api):
    from backtest.alpaca_exact_parity_contract import DailyBar
    from datetime import date
    h={s:[DailyBar(date(2026,10,5),100,102,99,101),DailyBar(date(2026,10,6),101,103,100,102)] for s in ['XOM','META']}
    assert api.concentration_check('XOM',['META'],h)['safe'] is False


@pytest.mark.parametrize('bad',['stale_clock','future_clock','future_earnings'])
def test_first_window_rejects_stale_clock_or_noncausal_earnings(api,tmp_path,monkeypatch,bad):
    hourly=tmp_path/'hourly';hourly.mkdir();cache(hourly)
    data=api.validate_hourly(POLICY,hourly,'2026-10-06',DAY['close_ms']+1000)
    from research_lab.alpaca_dynamic_v1 import digest
    now=POLICY['first_window_ms']+1000
    data.update(policy_sha256=digest(POLICY),received_ms=DAY['close_ms']+2000,
                earnings={s:{'dates':['2026-11-10'],'received_ms':DAY['close_ms']+1500} for s in POLICY['universe']})
    if bad=='future_earnings':data['earnings']['NET']['received_ms']=now+1000
    (tmp_path/'closed_source.json').write_text(json.dumps(data))
    from datetime import datetime,timezone
    clock_ms=now-301000 if bad=='stale_clock' else now+301000
    truth={'positions':[],'open_orders':[], 'clock':{'is_open':True,'timestamp':datetime.fromtimestamp(clock_ms/1000,timezone.utc).isoformat()}}
    monkeypatch.setattr(api.time,'time_ns',lambda:now*1000000)
    monkeypatch.setattr(api,'live_read_only',lambda *a:truth)
    with pytest.raises(ValueError):api.first_window(POLICY,tmp_path,'unused','unused')
    assert not (tmp_path/'first_window_receipt.json').exists()


def test_capture_alarm_is_not_swallowed_as_unknown_earnings(api,tmp_path,monkeypatch):
    from types import SimpleNamespace
    import sys
    monkeypatch.setattr(api.time,'time_ns',lambda:(DAY['close_ms']+1000)*1000000)
    monkeypatch.setattr(api.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    monkeypatch.setattr(api,'validate_hourly',lambda *a:{'history':{'SPY':[{}]*200},'file_sha256':{}})
    def timeout(*a,**k):raise TimeoutError('capture alarm')
    monkeypatch.setitem(sys.modules,'yfinance',SimpleNamespace(Ticker=lambda *a:SimpleNamespace(get_earnings_dates=timeout)))
    with pytest.raises(TimeoutError):api.capture(POLICY,tmp_path)
    assert not (tmp_path/'closed_source.json').exists()
