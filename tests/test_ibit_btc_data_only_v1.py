"""Synthetic saved-source and real-filesystem acceptance tests; no market outcomes."""
import datetime as dt
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from research_lab.ibit_btc_data_only_v1 import Adapter, canonical, frozen_events, rule_values, RULE_SHA

NY = ZoneInfo('America/New_York')
UTC = dt.timezone.utc

def ts(day, hour, minute=0):
    return dt.datetime.combine(dt.date.fromisoformat(day), dt.time(hour, minute), NY).astimezone(UTC)

def fixture(day='2026-10-16', close=16, delay=20, price=50.0, btc=100000):
    end = ts(day, 16)
    receipt = (max(ts(day, close) + dt.timedelta(minutes=delay), end)).isoformat()
    start_ms = int((end-dt.timedelta(hours=1)).timestamp()*1000)
    def wrap(raw): return {'received_at': receipt, 'raw': raw}
    return {
        'calendar': wrap([{'date':day, 'open':'09:30', 'close':f'{close:02}:00'}]),
        'alpaca_sip': dict(feed='sip',timeframe='1Day', **wrap({'bars':{'IBIT':[{'t':ts(day,0).isoformat(),'c':price}]}})),
        'binance':dict(symbol='BTCUSDT',interval='1h',**wrap([[start_ms,'1','1','1',str(btc),'1',start_ms+3599999]])),
        'bybit':dict(interval='60', **wrap({'retCode':0,'result':{'category':'linear','symbol':'BTCUSDT','list':[[str(start_ms),'1','1','1',str(btc),'1','1']]}}))
    }

def now_for(src, hours=0):
    return dt.datetime.fromisoformat(src['binance']['received_at'])+dt.timedelta(hours=hours)

def test_source_sha_rows_qa_and_revision_restart(tmp_path):
    src=fixture(); a=Adapter(tmp_path)
    r=a.import_session('2026-10-16',src,now_for(src))
    assert r['freshness']=='FRESH' and r['feed']=='SIP'
    assert r['bar_t_raw'] != r['session_close_ts']
    assert r['data_eligible'] and r['execution']=='NO_SEND' and not r['orders_enabled']
    assert len(RULE_SHA)==64 and r['rule_sha']==RULE_SHA
    assert r['row_sha']==hashlib.sha256(canonical({k:v for k,v in r.items() if k!='row_sha'})).hexdigest()
    for name,value in src.items():
        h=hashlib.sha256(canonical(value['raw'])).hexdigest()
        assert r['source_sha'][name]==h
        assert json.loads((tmp_path/'raw'/name/(h+'.json')).read_text())==value['raw']
    src['alpaca_sip']['raw']['bars']['IBIT'][0]['c']=51
    assert Adapter(tmp_path).import_session('2026-10-16',src,now_for(src))==r
    assert len(a.decisions())==1
    assert a.qa_records()[0]['status']=='PENDING_SVERKA'
    qa=a.reconcile('2026-10-16',{'date':'2026-10-16','rows':[['IBIT',1,1,1,50]]},now_for(src))
    assert qa['status']=='SVERKA_PASS' and qa['row_sha']==r['row_sha']
    assert a.reconcile('2026-10-16',{'date':'2026-10-16','rows':[['IBIT',1,1,1,50]]},now_for(src))==qa
    assert a.reconcile('2026-10-16',{'date':'2026-10-16','rows':[['IBIT',1,1,1,51]]},now_for(src))['status']=='DEFECT'
    assert a.decisions()==[r]

@pytest.mark.parametrize('day,utc_hour',[('2026-03-06',21),('2026-03-09',20),('2026-11-27',21)])
def test_dst_halfday_fixed_reference(tmp_path,day,utc_hour):
    half=day=='2026-11-27'; src=fixture(day,13 if half else 16)
    r=Adapter(tmp_path).import_session(day,src,now_for(src))
    assert dt.datetime.fromisoformat(r['btc_ref_end_ts']).hour==utc_hour
    assert r['sokrashchennyy']==half
    if half:
        assert r['freshness']=='LATE' and not r['data_eligible']
        assert dt.datetime.fromisoformat(r['session_close_ts']).hour==18

@pytest.mark.parametrize('delay,fresh',[(30,'FRESH'),(31,'LATE'),(360,'LATE'),(361,'MISSING')])
def test_freshness_thresholds(tmp_path,delay,fresh):
    src=fixture(delay=delay)
    r=Adapter(tmp_path).import_session('2026-10-16',src,now_for(src))
    assert r['freshness']==fresh
    if fresh=='MISSING': assert r['premiya'] is None


def test_notready_then_missing_no_interpolation(tmp_path):
    src=fixture(); src.pop('bybit'); a=Adapter(tmp_path)
    assert a.import_session('2026-10-16',src,now_for(src))['status']=='NOT_READY'
    assert a.decisions()==[]
    r=a.import_session('2026-10-16',src,now_for(src,7))
    assert r['freshness']=='MISSING' and r['z'] is None and not r['data_eligible']

@pytest.mark.parametrize('mutation', ['future','iex','extra_bar','wrong_btc','unclosed','bad_number','duplicate_calendar','traversal'])
def test_reject_malformed_or_noncausal(tmp_path,mutation):
    src=fixture(); day='2026-10-16'
    if mutation=='future': src['alpaca_sip']['received_at']=(now_for(src)+dt.timedelta(hours=1)).isoformat()
    elif mutation=='iex': src['alpaca_sip']['feed']='iex'
    elif mutation=='wrong_date': src['alpaca_sip']['raw']['bars']['IBIT'][0]['t']=ts('2026-10-15',0).isoformat()
    elif mutation=='extra_bar': src['alpaca_sip']['raw']['bars']['IBIT']*=2
    elif mutation=='wrong_btc': src['bybit']['raw']['result']['symbol']='ETHUSDT'
    elif mutation=='unclosed': src['binance']['raw'][0][0]+=3600000
    elif mutation=='bad_number': src['alpaca_sip']['raw']['bars']['IBIT'][0]['c']=float('nan')
    elif mutation=='duplicate_calendar': src['calendar']['raw']*=2
    else: day='../bad'
    with pytest.raises(ValueError): Adapter(tmp_path).import_session(day,src,now_for(src))
    assert Adapter(tmp_path).decisions()==[]


def test_early_receipt_is_notready_and_cross_discrepancy_closed(tmp_path):
    src=fixture(); src['alpaca_sip']['received_at']=(ts('2026-10-16',16)-dt.timedelta(seconds=1)).isoformat()
    assert Adapter(tmp_path).import_session('2026-10-16',src,now_for(src))['status']=='NOT_READY'
    src=fixture(); src['bybit']['raw']['result']['list'][0][4]='100201'
    r=Adapter(tmp_path).import_session('2026-10-16',src,now_for(src))
    assert r['btc_discrepancy']>0.002 and not r['data_eligible']


def test_concurrent_restart_tail_and_hash_tamper(tmp_path):
    src=fixture();
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows=list(pool.map(lambda _:Adapter(tmp_path).import_session('2026-10-16',src,now_for(src)),range(12)))
    assert all(r==rows[0] for r in rows)
    assert len(Adapter(tmp_path).decisions())==1
    with (tmp_path/'decisions.jsonl').open('ab') as f: f.write(b'{"partial":')
    assert Adapter(tmp_path).import_session('2026-10-16',src,now_for(src))==rows[0]
    assert (tmp_path/'decisions.jsonl').read_bytes().endswith(b'\n')
    p=tmp_path/'decisions.jsonl'; p.write_text(p.read_text().replace('"FRESH"','"LATE"'))
    with pytest.raises(ValueError,match='hash'): Adapter(tmp_path).decisions()


def test_missing_qa_after_crash_is_recovered(tmp_path):
    src=fixture(); a=Adapter(tmp_path); a.import_session('2026-10-16',src,now_for(src))
    (tmp_path/'qa.jsonl').unlink()
    a.import_session('2026-10-16',src,now_for(src))
    assert a.qa_records()[0]['status']=='PENDING_SVERKA'


def test_frozen_formula_event_parity_synthetic_only():
    rows=[]
    for i in range(125):
        day=(dt.date(2025,1,1)+dt.timedelta(days=i)).isoformat()
        rows.append({'session':day,'ibit_close':50*(1+0.001*np.sin(i))+ (1 if i==100 else 0),'btc_ref_binance':100000})
    events=frozen_events(rows)
    assert events
    for i,r in enumerate(rows):
        val=rule_values(rows[:i+1]); ev=next((e for e in events if e['den']==r['session']),None)
        assert val['sobytie']==bool(ev)
        if ev:
            assert val['znak']==ev['znak'] and round(val['z'],2)==ev['z']
        if i<20: assert val['premiya'] is None
        if i<60: assert val['z'] is None
    # Future rows cannot alter the historical value.
    assert rule_values(rows[:101])['z']==pytest.approx(next(e['z'] for e in events if e['den']==rows[100]['session']),abs=.005)


def test_cli_offline_import_and_default_no_network(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    script=Path(__file__).resolve().parents[1]/'scripts/run_ibit_btc_data_only_v1.py'
    no_args=subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
    assert no_args.returncode==0 and 'NO_NETWORK' in no_args.stdout
    source=tmp_path/'saved.json'; source.write_bytes(canonical(fixture()))
    result=subprocess.run([sys.executable,str(script),'import','--session','2026-10-16',
                           '--sources',str(source),'--store',str(tmp_path/'store'),
                           '--now',now_for(fixture()).isoformat()],capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    assert json.loads(result.stdout)['freshness']=='FRESH'


def test_saved_provenance_and_source_tamper(tmp_path):
    src=fixture(); src['binance']['symbol']='ETHUSDT'
    with pytest.raises(ValueError): Adapter(tmp_path).import_session('2026-10-16',src,now_for(src))
    src=fixture(); a=Adapter(tmp_path); r=a.import_session('2026-10-16',src,now_for(src))
    path=tmp_path/'raw/alpaca_sip'/f"{r['source_sha']['alpaca_sip']}.json"
    path.write_text('{}')
    with pytest.raises(ValueError,match='source'): a.decisions()


def test_first_receipt_retained_when_missing_source_retried(tmp_path):
    src=fixture(); partial={k:v for k,v in src.items() if k!='bybit'}; a=Adapter(tmp_path)
    assert a.import_session('2026-10-16',partial,now_for(src))['status']=='NOT_READY'
    later=now_for(src,2)
    for value in src.values(): value['received_at']=later.isoformat()
    r=a.import_session('2026-10-16',src,later)
    assert r['received_at']==fixture()['alpaca_sip']['received_at']
    assert r['freshness']=='FRESH'


def test_exact_btc_threshold_not_flagged(tmp_path):
    src=fixture(); src['bybit']['raw']['result']['list'][0][4]='100200'
    r=Adapter(tmp_path).import_session('2026-10-16',src,now_for(src))
    assert not r['btc_discrepancy_flag'] and r['data_eligible']


@pytest.mark.parametrize('kind',['wrong_date','alpaca_sip','binance','bybit'])
def test_absent_or_prior_session_response_is_notready(tmp_path,kind):
    src=fixture()
    if kind=='wrong_date': src['alpaca_sip']['raw']['bars']['IBIT'][0]['t']=ts('2026-10-15',0).isoformat()
    elif kind=='alpaca_sip': src[kind]['raw']['bars']['IBIT']=[]
    elif kind=='binance': src[kind]['raw']=[]
    else: src[kind]['raw']['result']['list']=[]
    a=Adapter(tmp_path)
    assert a.import_session('2026-10-16',src,now_for(src))['status']=='NOT_READY'
    assert a.import_session('2026-10-16',src,now_for(src,7))['freshness']=='MISSING'


def test_foreign_nonempty_store_rejected_without_changes(tmp_path):
    foreign=tmp_path/'foreign'; foreign.mkdir(); original=foreign/'unrelated.txt'; original.write_bytes(b'keep')
    with pytest.raises(ValueError): Adapter(foreign)
    assert original.read_bytes()==b'keep' and list(foreign.iterdir())==[original]


@pytest.mark.parametrize('kind',['root_ancestor','lock_symlink','lock_hardlink','journal_symlink','journal_hardlink','raw_dir_symlink','receipt_dir_symlink'])
def test_unsafe_runtime_paths_never_mutate_outside_bytes(tmp_path,kind):
    store=tmp_path/'store'; outside=tmp_path/'outside'; outside.mkdir()
    evidence=outside/'evidence'; evidence.write_bytes(b'{"unfinished":')
    original=evidence.read_bytes(); src=fixture()
    if kind=='root_ancestor':
        (tmp_path/'alias').symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError): Adapter(tmp_path/'alias/store')
        assert not (outside/'store').exists()
    else:
        a=Adapter(store)
        if kind.startswith('lock_'):
            target=store/'.adapter.lock'
        elif kind.startswith('journal_'):
            target=store/'decisions.jsonl'
        else:
            target=store/('raw' if kind=='raw_dir_symlink' else 'first_receipts')
        if 'hardlink' in kind:
            import os
            os.link(evidence,target)
        elif 'dir_symlink' in kind:
            target.symlink_to(outside, target_is_directory=True)
        else:
            target.symlink_to(evidence)
        with pytest.raises(ValueError): a.import_session('2026-10-16',src,now_for(src))
    assert evidence.read_bytes()==original
    assert list(outside.iterdir())==[evidence]


def test_millisecond_timestamp_fields_exact_integers(tmp_path):
    src=fixture(); src['alpaca_sip']['received_at']='2026-10-16T20:20:00.123456+00:00'
    now=dt.datetime.fromisoformat('2026-10-16T20:21:00.987654+00:00')
    row=Adapter(tmp_path).import_session('2026-10-16',src,now)
    def exact(value):
        delta=dt.datetime.fromisoformat(value)-dt.datetime(1970,1,1,tzinfo=UTC)
        return delta.days*86400000+delta.seconds*1000+delta.microseconds//1000
    for field in ('received_at','session_close_ts','decided_at'):
        assert type(row[field+'_ms']) is int
        assert row[field+'_ms']==exact(row[field])
    assert all(type(value) is int for value in row['source_received_at_ms'].values())
    assert row['source_received_at_ms']=={k:exact(v) for k,v in row['source_received_at'].items()}


def test_cli_rejects_saved_input_inside_store_without_mutation(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    store=tmp_path/'store'; Adapter(store)
    source=store/'saved.json'; source.write_bytes(canonical(fixture())); original=source.read_bytes()
    script=Path(__file__).resolve().parents[1]/'scripts/run_ibit_btc_data_only_v1.py'
    result=subprocess.run([sys.executable,str(script),'import','--session','2026-10-16',
                           '--sources',str(source),'--store',str(store),
                           '--now',now_for(fixture()).isoformat()],capture_output=True,text=True)
    assert result.returncode==2
    assert source.read_bytes()==original and not (store/'decisions.jsonl').exists()
