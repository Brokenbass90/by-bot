"""Historical warmup is causal input, never prospective freshness evidence."""
import copy
import datetime as dt
import json
import math

import pytest

from research_lab.ibit_btc_data_only_v1 import Adapter, rule_values
from test_ibit_btc_data_only_v1 import fixture, now_for, ts


def history():
    end=dt.date(2026,10,16);days=[]
    while len(days)<81:
        if end.weekday()<5: days.append(end.isoformat())
        end-=dt.timedelta(days=1)
    days.reverse();receipt='2026-10-17T14:00:00+00:00'
    sources={'calendar':{'received_at':receipt,'raw':[]},
             'alpaca_sip':{'received_at':receipt,'feed':'sip','timeframe':'1Day',
                           'raw':{'bars':{'IBIT':[]},'next_page_token':None}},
             'binance':{'received_at':receipt,'symbol':'BTCUSDT','interval':'1h','raw':[]}}
    expected=[]
    for i,day in enumerate(days):
        price=50*(1+.003*math.sin(i));btc=100000+i*5
        src=fixture(day,price=price,btc=btc)
        for name in sources:
            if name=='alpaca_sip':sources[name]['raw']['bars']['IBIT']+=src[name]['raw']['bars']['IBIT']
            else:sources[name]['raw']+=src[name]['raw']
        expected.append({'session':day,'ibit_close':price,'btc_ref_binance':btc,'freshness':'HISTORICAL_WARMUP'})
    return sources,expected


def test_history_then_first_forward_has_exact_frozen_z_and_no_fake_sessions(tmp_path):
    sources,expected=history();a=Adapter(tmp_path)
    seed=a.seed_history(sources,dt.datetime.fromisoformat('2026-10-17T14:01:00+00:00'))
    assert seed['status']=='HISTORICAL_WARMUP_ONLY' and seed['prospective_sessions']==0
    assert seed['sessions']==81 and not seed['orders_enabled']
    assert a.decisions()==[] and a.qa_records()==[]
    src=fixture('2026-10-19',price=50.6,btc=100500)
    r=Adapter(tmp_path).import_session('2026-10-19',src,now_for(src))
    want=rule_values(expected+[r])
    assert r['z']==want['z'] and r['sobytie']==want['sobytie'] and r['znak']==want['znak']
    assert r['warmup_sha']==seed['seed_sha'] and r['history_sessions']==82
    assert len(a.decisions())==1 and len(a.qa_records())==1
    assert r['freshness']=='FRESH' and r['orders_enabled'] is False


def test_seed_replay_is_immutable_and_cannot_start_after_forward(tmp_path):
    src,_=history();a=Adapter(tmp_path);now=dt.datetime.fromisoformat('2026-10-17T14:01:00+00:00')
    first=a.seed_history(src,now)
    assert Adapter(tmp_path).seed_history(src,now)==first
    changed=copy.deepcopy(src);changed['alpaca_sip']['raw']['bars']['IBIT'][0]['c']+=.1
    with pytest.raises(ValueError,match='immutable'):a.seed_history(changed,now)
    root=tmp_path/'other';forward=fixture();b=Adapter(root)
    b.import_session('2026-10-16',forward,now_for(forward))
    with pytest.raises(ValueError,match='before prospective'):b.seed_history(src,now)


@pytest.mark.parametrize('bad',['missing','duplicate','future_receipt','early_receipt','iex','partial_page','wrong_interval','not_enough'])
def test_bad_seed_fails_before_any_forward_evidence(tmp_path,bad):
    src,_=history();now=dt.datetime.fromisoformat('2026-10-17T14:01:00+00:00')
    if bad=='missing':src['alpaca_sip']['raw']['bars']['IBIT'].pop(10)
    if bad=='duplicate':src['binance']['raw'].append(src['binance']['raw'][0])
    if bad=='future_receipt':src['alpaca_sip']['received_at']='2026-10-18T00:00:00+00:00'
    if bad=='early_receipt':src['binance']['received_at']='2026-01-01T00:00:00+00:00'
    if bad=='iex':src['alpaca_sip']['feed']='iex'
    if bad=='partial_page':src['alpaca_sip']['raw']['next_page_token']='more'
    if bad=='wrong_interval':src['binance']['interval']='1d'
    if bad=='not_enough':src['calendar']['raw']=src['calendar']['raw'][-20:]
    a=Adapter(tmp_path)
    with pytest.raises(ValueError):a.seed_history(src,now)
    assert not (tmp_path/'warmup.json').exists() and a.decisions()==[]


def test_seed_cannot_overlap_forward_or_be_tampered(tmp_path):
    src,_=history();a=Adapter(tmp_path);now=dt.datetime.fromisoformat('2026-10-17T14:01:00+00:00')
    a.seed_history(src,now)
    f=fixture('2026-10-16')
    with pytest.raises(ValueError,match='warmup overlap'):a.import_session('2026-10-16',f,now)
    p=tmp_path/'warmup.json';r=json.loads(p.read_bytes());r['rows'][0]['ibit_close']+=1;p.write_text(json.dumps(r))
    f=fixture('2026-10-19')
    with pytest.raises(ValueError,match='warmup hash'):a.import_session('2026-10-19',f,now_for(f))


def test_missing_history_after_forward_blocks_restart_and_all_new_decisions(tmp_path):
    src,_=history();a=Adapter(tmp_path);now=dt.datetime.fromisoformat('2026-10-17T14:01:00+00:00')
    a.seed_history(src,now);f=fixture('2026-10-19')
    a.import_session('2026-10-19',f,now_for(f));(tmp_path/'warmup.json').unlink()
    with pytest.raises(ValueError,match='warmup identity'):Adapter(tmp_path).decisions()
    f=fixture('2026-10-20')
    with pytest.raises(ValueError,match='warmup identity'):a.import_session('2026-10-20',f,now_for(f))


def test_saved_seed_cli_does_not_claim_freshness_or_write_decision(tmp_path,capsys):
    from scripts.run_ibit_btc_data_only_v1 import main
    sources,_=history();p=tmp_path/'sources.json';p.write_text(json.dumps(sources));root=tmp_path/'store'
    assert main(['seed','--sources',str(p),'--store',str(root),'--now','2026-10-17T14:01:00+00:00'])==0
    out=json.loads(capsys.readouterr().out)
    assert out['sessions']==81 and out['prospective_sessions']==0 and out['orders_enabled'] is False
    assert 'freshness' not in out and Adapter(root).decisions()==[]


def test_history_received_after_decision_cannot_leak_backwards(tmp_path):
    sources,_=history()
    for source in sources.values():source['received_at']='2026-10-20T20:20:00+00:00'
    a=Adapter(tmp_path);a.seed_history(sources,'2026-10-20T20:21:00+00:00')
    f=fixture('2026-10-19')
    with pytest.raises(ValueError,match='not available at decision'):
        a.import_session('2026-10-19',f,now_for(f))
