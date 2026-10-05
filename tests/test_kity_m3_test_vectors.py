"""Frozen signal-only vectors, adapted to synthetic public wires; no returns/judge.

The vectors contain eight-decimal features and expected baskets, not raw PIT OI
or candles. This proves selector/reconstruction compatibility at that precision;
it does not establish historical raw provenance or prospective eligibility.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/kity_m3_test_vectors_28e4b48.json'
RAW=FIXTURE.read_bytes()
VECTORS=json.loads(RAW)['nedeli']
SPEC=importlib.util.spec_from_file_location('kity_vector_fixture',ROOT/'tests/test_kity_m3_orders_off.py')
F=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(F)


def vector_bundle(vector):
    # Independent input is the supplied feature map. Expected long/short names
    # never participate in building inputs. Transport/census/OI are synthetic.
    t=int(datetime.fromisoformat(vector['d']).replace(tzinfo=timezone.utc).timestamp()*1000)
    now=t+600000;cutoff=t-300000
    features=vector['priznaki'];symbols=sorted(features)
    symbols += [f'ZZFIX{i}USDT' for i in range(50-len(symbols))]
    candidates=[];oi={};klines={}
    for i,s in enumerate(symbols):
        eligible=s in features;count=60 if eligible else 30
        candidates.append(dict(symbol=s,baseAsset=s[:-4],quoteAsset='USDT',marginAsset='USDT',contractType='PERPETUAL',status='TRADING',onboardDate=t-(100 if eligible else 30)*F.DAY,deliveryDate=t+1000*F.DAY))
        oi[s]=F.cap('BINANCE','/futures/data/openInterestHist',[{'timestamp':cutoff,'sumOpenInterestValue':str(1000-i)}],{'symbol':s,'period':'5m','endTime':cutoff},rx=now-10)
        taker=str(Decimal(str(features[s]))*Decimal('100000000')) if eligible else '0'
        bars=[]
        for j in range(count):
            ts=t-(count-j)*F.DAY
            bars.append([ts,'100','110','90','100','1',ts+F.DAY-1,'100000000','1','1',taker,'0'])
        klines[s]=F.cap('BINANCE','/fapi/v1/klines',bars,{'symbol':s,'interval':'1d','endTime':t-1},rx=now-10)
    return {'day':vector['d'],'research_ref':F.REF,'census':F.cap('BINANCE','/fapi/v1/exchangeInfo',{'symbols':candidates},rx=cutoff-1),'oi':oi,'klines':klines},now


@pytest.mark.parametrize('vector',VECTORS,ids=[v['d'] for v in VECTORS])
def test_all_frozen_vectors_reconstruct_without_fixed_ten_leg_refusal(vector):
    b,now=vector_bundle(vector);r=F.api('reconstruct_signal')(b,now)
    assert r['signal_valid'] is True
    frozen=r['frozen_signal']
    assert frozen['feature_count']==vector['monet_s_priznakom']
    assert frozen['decile_count']==vector['k']
    assert [x['symbol'] for x in frozen['long']]==vector['long']
    assert [x['symbol'] for x in frozen['short']]==vector['short']
    assert r['status']=='BLOCKED_DATA'
    assert 'BLOCKED_BASKET_CONTRACT' not in r['reasons']
    assert r['prospective_eligible'] is False
    assert r['orders_allowed'] is False and r['money_ready'] is False
