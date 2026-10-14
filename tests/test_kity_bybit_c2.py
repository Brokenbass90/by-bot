"""Independent frozen C2 arithmetic/source checks; no shadow import or outcomes."""
import copy
import gzip
import hashlib
import importlib
import json
from datetime import datetime,timezone

import pytest


def api():return importlib.import_module('research_lab.kity_bybit_c2')
def rawpin(path):return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def ms(s):return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)


def fixture(tmp_path,n):
    day='2026-10-15';start=ms(day+'T00:00:00Z');files={}
    symbols=[f'S{i:02d}USDT' for i in range(50)]
    snapshot=dict(vremya='2026-10-14T23:55:00+00:00',oi_usd={s:50-i for i,s in enumerate(symbols)},
        instrumenty={s:dict(step=.1,min_qty=.1,min_notional=5) for s in symbols})
    p=tmp_path/'snapshot.json';p.write_text(json.dumps(snapshot));snap=rawpin(p)
    candles={};archives={}
    for i,s in enumerate(symbols):
        rows=[[str(start-k*86400000),'1','1','1','1','1','1'] for k in range(1,76 if i<n else 60)]
        response=json.dumps(dict(retCode=0,result=dict(list=rows)))
        capture=dict(venue='BYBIT',endpoint='/v5/market/kline',params=dict(category='linear',symbol=s,interval='D',end=start-1,limit=75),
            request_ms=start+600000,receive_ms=start+601000,raw=response,sha256=hashlib.sha256(response.encode()).hexdigest())
        p=tmp_path/(s+'-candles.json');p.write_text(json.dumps(capture));candles[s]=rawpin(p)
        text=f'timestamp,symbol,side,size,price,foreignNotional\n{start/1000-20},{s},Buy,1,1,{i+1}\n{start/1000-10},{s},Sell,1,1,{51-i}\n'
        p=tmp_path/(s+'.csv.gz');p.write_bytes(gzip.compress(text.encode(),mtime=0));archives[s]=rawpin(p)
    bundle=dict(schema='KITY_BYBIT_C2_INPUT_V1',day=day,research_ref='cb47f0eb57e7a64ea5fcb948d7ae12d617c2abe1',
        snapshot=snap,candles=candles,archives=archives)
    return bundle,start+7200000,symbols


@pytest.mark.parametrize('n',[30,39,40,49,50])
def test_frozen_n_floor_10_from_raw_archives(tmp_path,n):
    b,now,symbols=fixture(tmp_path,n);r=api().reconstruct(b,now_ms=now)
    assert r['status']=='C2_RECONSTRUCTED_ORDERS_OFF',r
    assert len(r['vse_priznaki'])==n
    assert r['short']==symbols[:n//10] and r['long']==symbols[n-n//10:n]
    assert r['vse_priznaki'][symbols[0]]==pytest.approx(1/52)
    assert set(r['arhiv_sha256'])==set(r['vse_priznaki'])
    assert r['orders_allowed'] is False and r['money_ready'] is False


def test_under_30_is_blocked_without_padding(tmp_path):
    b,now,s=fixture(tmp_path,29)
    assert api().reconstruct(b,now_ms=now)['reason']=='FROZEN_MINIMUM_30_NOT_MET'


@pytest.mark.parametrize('fault,reason',[
    ('missing_archive','ARCHIVE_REQUIRED'),('missing_candles','CANDLES_REQUIRED'),
    ('wrong_pin','SOURCE_PIN_CONFLICT'),('snapshot_early','FROZEN_SNAPSHOT_WINDOW'),
    ('snapshot_future','FROZEN_SNAPSHOT_WINDOW'),('wrong_end','CANDLE_REQUEST_IDENTITY'),
    ('wrong_raw_pin','CANDLE_RAW_PIN_CONFLICT'),('early_candles','CANDLE_CAPTURE_NOT_CLOSED_SOURCE'),('wrong_day','TRADE_DAY_CONFLICT'),
    ('unknown_side','TRADE_SIDE_UNKNOWN'),('nonfinite','TRADE_VALUE_INVALID'),
    ('missing_yesterday','FROZEN_MINIMUM_30_NOT_MET')])
def test_source_defects_do_not_silently_remove_mature_name(tmp_path,fault,reason):
    b,now,s=fixture(tmp_path,30)
    if fault=='missing_archive':del b['archives'][s[0]]
    elif fault=='missing_candles':del b['candles'][s[0]]
    elif fault=='wrong_pin':b['snapshot']['sha256']='0'*64
    elif fault.startswith('snapshot_'):
        from pathlib import Path
        p=Path(b['snapshot']['path']);d=json.loads(p.read_text())
        d['vremya']='2026-10-14T23:49:59+00:00' if fault=='snapshot_early' else '2026-10-15T00:00:00+00:00'
        p.write_text(json.dumps(d));b['snapshot']=rawpin(p)
    elif fault in {'wrong_end','wrong_raw_pin','missing_yesterday','early_candles'}:
        from pathlib import Path
        p=Path(b['candles'][s[0]]['path']);d=json.loads(p.read_text())
        if fault=='wrong_end':d['params']['end']-=1
        elif fault=='wrong_raw_pin':d['sha256']='0'*64
        elif fault=='early_candles':d['request_ms']=d['receive_ms']=ms('2026-10-15T00:00:00Z')-1
        else:
            rows=json.loads(d['raw']);rows['result']['list']=rows['result']['list'][1:]
            d['raw']=json.dumps(rows);d['sha256']=hashlib.sha256(d['raw'].encode()).hexdigest()
        p.write_text(json.dumps(d));b['candles'][s[0]]=rawpin(p)
    else:
        from pathlib import Path
        p=Path(b['archives'][s[0]]['path']);text=gzip.decompress(p.read_bytes()).decode()
        if fault=='wrong_day':text=text.replace(str(ms('2026-10-15T00:00:00Z')/1000-20),'1')
        elif fault=='unknown_side':text=text.replace(',Buy,',',Other,')
        else:text=text.replace(',1\n',',NaN\n',1)
        p.write_bytes(gzip.compress(text.encode(),mtime=0));b['archives'][s[0]]=rawpin(p)
    assert api().reconstruct(b,now_ms=now)['reason']==reason


def test_foreign_notional_missing_uses_size_times_price(tmp_path):
    b,now,s=fixture(tmp_path,30)
    from pathlib import Path
    p=Path(b['archives'][s[0]]['path']);text=gzip.decompress(p.read_bytes()).decode()
    text=text.replace('size,price,foreignNotional','size,price').replace(',1,1,1\n',',2,3\n').replace(',1,1,51\n',',1,6\n')
    p.write_bytes(gzip.compress(text.encode(),mtime=0));b['archives'][s[0]]=rawpin(p)
    assert api().reconstruct(b,now_ms=now)['vse_priznaki'][s[0]]==.5


def external(r):
    shadow=dict(d=r['d'],vse_priznaki={s:round(v,6) for s,v in r['vse_priznaki'].items()},
        long=[dict(s=s) for s in r['long']],short=[dict(s=s) for s in r['short']])
    flow={s:dict(sha256=v) for s,v in r['arhiv_sha256'].items()}
    return shadow,flow


def test_compare_requires_all_exact_hashes_even_when_basket_matches(tmp_path):
    b,now,s=fixture(tmp_path,30);r=api().reconstruct(b,now_ms=now);shadow,flow=external(r)
    assert api().compare(r,shadow,flow)['status']=='C2_PASS_MATCH_ONLY'
    missing=copy.deepcopy(r);missing['arhiv_sha256']={'FAKE':'0'*64}
    assert api().compare(missing,shadow,flow)['status']=='C2_FAIL'
    del flow[s[0]]
    assert api().compare(r,shadow,flow)['status']=='C2_FAIL'


def test_nan_or_threshold_equality_is_not_parity(tmp_path):
    b,now,s=fixture(tmp_path,30);r=api().reconstruct(b,now_ms=now);shadow,flow=external(r)
    shadow['vse_priznaki'][s[0]]=float('nan')
    assert api().compare(r,shadow,flow)['status']=='C2_FAIL'
    shadow,flow=external(r);shadow['vse_priznaki'][s[25]]=.500001
    assert api().compare(r,shadow,flow)['status']=='C2_FAIL'
    shadow,flow=external(r);shadow['long'][0]['s']=s[0]
    assert api().compare(r,shadow,flow)['status']=='C2_FAIL'


def test_modified_but_rehashed_receipt_still_requires_raw_replay(tmp_path):
    b,now,s=fixture(tmp_path,30);r=api().reconstruct(b,now_ms=now);shadow,flow=external(r)
    r['vse_priznaki'][s[0]]=.9
    r['receipt_sha256']=api().digest({k:v for k,v in r.items() if k!='receipt_sha256'})
    assert api().compare(r,shadow,flow)['problems']==['INDEPENDENT_RAW_REPLAY_CONFLICT']


def test_cli_publishes_only_new_output_outside_shadow_and_never_overwrites(tmp_path,monkeypatch):
    from scripts.kity_bybit_c2 import main
    root=tmp_path/'owned';b,now,s=fixture(tmp_path,30)
    bundle=tmp_path/'bundle.json';bundle.write_text(json.dumps(b))
    monkeypatch.setattr('scripts.kity_bybit_c2.OUTPUT_ROOT',root)
    monkeypatch.setattr('scripts.kity_bybit_c2.clock_ms',lambda:now)
    out=root/'independent.json'
    assert main(['reconstruct','--bundle',str(bundle),'--output',str(out)])==0
    saved=out.read_bytes()
    assert main(['reconstruct','--bundle',str(bundle),'--output',str(out)])==2
    assert out.read_bytes()==saved
    assert main(['reconstruct','--bundle',str(bundle),'--output',str(tmp_path/'shadow'/'signal.json')])==2
    assert not (tmp_path/'shadow').exists()
