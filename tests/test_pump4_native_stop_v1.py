"""Native mapping is an OFF execution detail, never a new reference strategy."""
import copy,json
from decimal import Decimal as D
import pytest
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.pump4_execution_plan_v1 import build_plan
from strategies.signals import TradeSignal

def material(side='short',tick='.3'):
    sign=-1 if side=='short' else 1
    s=TradeSignal(strategy='pump_fade',symbol='ZROUSDT',side=side,entry=100.,sl=101. if side=='short' else 99.,tp=100+sign*4.2,tps=[100+sign*2.1,100+sign*4.2],tp_fracs=[.4,.6])
    p=build_plan(s,signal_bar_open_ms=3600000,next_open_ms=7200000,next_open=100.)
    i=dict(symbol='ZROUSDT',status='Trading',quoteCoin='USDT',contractType='LinearPerpetual',priceFilter=dict(tickSize=tick,minPrice='.01',maxPrice='10000'))
    t=dict(symbol='ZROUSDT',lastPrice='100',bid1Price='100',ask1Price='100')
    return p,i,t

@pytest.mark.parametrize('side,native',[('short','103.8'),('long','96.0')])
def test_non_widening_mapping_keeps_reference_identity(side,native):
    from research_lab.pump4_native_stop_v1 import native_mapping,verify_mapping
    p,i,t=material(side);raw=json.dumps(p,sort_keys=True);m=native_mapping(p,i,t)
    assert D(m['native_stop'])==D(native) and m['plan_sha256']==p['plan_sha256']
    assert m['reference_stop']==str(p['stop']) and json.dumps(p,sort_keys=True)==raw
    assert m['orders_allowed'] is False and m['money_authority'] is False
    assert verify_mapping(p,i['priceFilter']['tickSize'],m)==m

@pytest.mark.parametrize('fault',['symbol','tick','price','entry','mapping','plan'])
def test_invalid_or_tampered_mapping_rejected(fault):
    from research_lab.pump4_native_stop_v1 import native_mapping,verify_mapping
    p,i,t=material();m=native_mapping(p,i,t)
    if fault=='symbol':m['symbol']='AAVEUSDT'
    elif fault=='tick':i['priceFilter']['tickSize']='.4'
    elif fault=='price':t['lastPrice']='103.9'
    elif fault=='entry':i['priceFilter']['tickSize']='200'
    elif fault=='mapping':m['native_stop']='104.1'
    else:p['plan_sha256']='0'*64
    with pytest.raises(ValueError):
        if fault in ('price','entry'):native_mapping(p,i,t)
        else:verify_mapping(p,i['priceFilter']['tickSize'],m)

def test_mapping_lifecycle_restart_and_exact_native_readback(tmp_path):
    from research_lab.pump4_native_stop_v1 import native_mapping
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    from test_pump4_execution_lifecycle_v1 import observation,filled
    p,i,t=material();m=native_mapping(p,i,t);args=dict(qty='10',qty_step='1',min_qty='1',min_notional='5',tick_size='.3',native_stop_mapping=m)
    f=Pump4Lifecycle(tmp_path,p,**args);o=observation();a=f.advance(o,now_ms=7200000)
    assert D(a['request']['stopLoss'])==D('103.8') and f.config['plan']==p
    raw=(tmp_path/'execution-config.json').read_bytes();g=Pump4Lifecycle.resume(tmp_path)
    assert g.config==f.config and (tmp_path/'execution-config.json').read_bytes()==raw
    assert g.advance(o,now_ms=7200000)['status']=='RECONCILE_ONLY'
    row,fill=filled(a['request']);o=observation(held='10',orders=[row],fills=[fill],price='99');o['native_stop']['triggerPrice']='103.8'
    assert g.advance(o,now_ms=7200000)['status']=='PROTECTED_WAIT'
    o['native_stop']['triggerPrice']='103.5'
    assert g.advance(o,now_ms=7200000)['status']=='NATIVE_PROTECTION_UNKNOWN'

def test_legacy_exact_tick_config_has_no_mapping_field(tmp_path):
    from test_pump4_execution_lifecycle_v1 import setup
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    f=setup(tmp_path);before=(tmp_path/'execution-config.json').read_bytes();g=Pump4Lifecycle.resume(tmp_path)
    assert 'native_stop_mapping' not in g.config and g.config==f.config
    assert (tmp_path/'execution-config.json').read_bytes()==before

def owner_material(tmp_path,mode='ORDERS_OFF'):
    from test_pump4_account_owner_v1 import create,inputs,reseal
    s=create(tmp_path,mode=mode,authorize=False);o,e,t,_,_,_=s
    p,i,q=material(tick='.01');p['stop']=104.005;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
    # This is a reference-plan test fixture, not a new strategy decision.
    from test_pump4_bybit_sources_v1 import NOW
    p['entry_bar_open_ms']=NOW;p['signal_bar_open_ms']=NOW-3600000;p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
    x,public=inputs(e,now=t[0]);return s,p,x,public

def test_checked_mapping_never_increases_qty_and_persists(tmp_path):
    from research_lab.pump4_account_owner_v1 import source_sizing
    from test_pump4_account_owner_v1 import reseal
    s,p,x,public=owner_material(tmp_path);o,e,t,_,_,lease=s
    try:
        quantities=[]
        for tick in ('.01','.1','.3'):
            public['instruments']['pages'][0]['body']['result']['list'][0]['priceFilter']['tickSize']=tick;reseal(public['instruments']['pages'][0])
            size=source_sizing(p,x,public,o.scope['policy'],fingerprint=o.scope['account_fingerprint'],now_ms=t[0]);quantities.append(size['quantity'])
        assert len(set(quantities))==1
        f=o.prepare(p,x,public);assert f.config['plan']==p and 'native_stop_mapping' in f.config
        with pytest.raises(ValueError,match='NATIVE_MAPPING_ORDERS_OFF_ONLY'):o.cycle(f,x,public,apply=True)
        assert not f.requests() and e.state['calls']==0
        assert o.cycle(f,x,public,apply=False)['status']=='ACTION_RESERVED_ORDERS_OFF'
        assert e.state['calls']==0
    finally:lease.close()

def test_fresh_tick_drift_or_crossed_last_rejects_before_admission(tmp_path):
    from test_pump4_account_owner_v1 import reseal
    s,p,x,public=owner_material(tmp_path);o,e,t,_,_,lease=s
    try:
        f=o.prepare(p,x,public)
        public['instruments']['pages'][0]['body']['result']['list'][0]['priceFilter']['tickSize']='.03';reseal(public['instruments']['pages'][0])
        with pytest.raises(ValueError,match='NATIVE_MAPPING_SOURCE_CHANGED'):o.cycle(f,x,public,apply=False)
        assert not (o.root/'admitted-lifecycle.json').exists() and not f.requests()
        public['instruments']['pages'][0]['body']['result']['list'][0]['priceFilter']['tickSize']='.01';reseal(public['instruments']['pages'][0])
        public['quote']['body']['result']['list'][0]['lastPrice']='104.003';reseal(public['quote'])
        with pytest.raises(ValueError,match='INVALID_NATIVE_GEOMETRY'):o.cycle(f,x,public,apply=False)
        assert not (o.root/'admitted-lifecycle.json').exists() and e.state['calls']==0
    finally:lease.close()

def test_mapping_tamper_on_disk_cannot_resume(tmp_path):
    from research_lab.pump4_native_stop_v1 import native_mapping
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    p,i,t=material();f=Pump4Lifecycle(tmp_path,p,qty='10',qty_step='1',min_qty='1',min_notional='5',tick_size='.3',native_stop_mapping=native_mapping(p,i,t))
    c=f.config;c['native_stop_mapping']['native_stop']='104.1';(tmp_path/'execution-config.json').write_text(json.dumps(c))
    with pytest.raises(ValueError):Pump4Lifecycle.resume(tmp_path)

def test_native_mapper_is_in_selected_source_closure():
    from research_lab.pump4_selected_runner_v1 import source_pins
    assert 'research_lab/pump4_native_stop_v1.py' in source_pins()

def test_legacy_live_scope_cannot_prepare_new_mapped_flow(tmp_path):
    s,p,x,public=owner_material(tmp_path,mode='OWNER_TINY_LIVE');o,e,t,_,_,lease=s
    try:
        with pytest.raises(ValueError,match='NATIVE_MAPPING_ORDERS_OFF_ONLY'):o.prepare(p,x,public)
        assert not (o.flows/p['plan_sha256']).exists() and e.state['calls']==0
    finally:lease.close()

def mapped_flow(tmp_path):
    from research_lab.pump4_native_stop_v1 import native_mapping
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    p,i,t=material();return Pump4Lifecycle(tmp_path,p,qty='10',qty_step='1',min_qty='1',min_notional='5',tick_size='.3',native_stop_mapping=native_mapping(p,i,t))

def test_mapped_partial_entry_and_partial_tp_preserve_actual_40_60(tmp_path):
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    from test_pump4_execution_lifecycle_v1 import observation,filled
    f=mapped_flow(tmp_path);req=f.advance(observation(),now_ms=7200000)['request'];row,fill=filled(req,'5','PartiallyFilledCanceled');orders=[row];fills=[fill]
    def observe(held,price):
        o=observation(held=held,orders=orders,fills=fills,price=price);o['native_stop']['triggerPrice']='103.8';return o
    a=f.advance(observe('5','97.8'),now_ms=7200000)['request'];assert D(a['qty'])==2
    row,fill=filled(a,'1','PartiallyFilledCanceled');orders.append(row);fills.append(fill)
    g=Pump4Lifecycle.resume(tmp_path);a=g.advance(observe('4','97.8'),now_ms=7200000)['request'];assert D(a['qty'])==1
    row,fill=filled(a);orders.append(row);fills.append(fill)
    a=g.advance(observe('3','95.7'),now_ms=7200000)['request'];assert D(a['qty'])==3
    assert a['reduceOnly'] is True

def test_mapped_native_stop_race_is_owned_after_restart(tmp_path):
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    from test_pump4_execution_lifecycle_v1 import observation,filled
    f=mapped_flow(tmp_path);req=f.advance(observation(),now_ms=7200000)['request'];row,fill=filled(req)
    o=observation(held='10',orders=[row],fills=[fill],price='103.8');o['native_stop']['triggerPrice']='103.8'
    assert f.advance(o,now_ms=7200000)['status']=='NATIVE_STOP_TRIGGER_WAIT'
    stopfill=dict(execId='mapped-native-fill',orderId='native-1',orderLinkId='',symbol='ZROUSDT',side='Buy',execQty='10',execPrice='103.8',execFee='.6',feeCurrency='USDT')
    g=Pump4Lifecycle.resume(tmp_path);out=g.advance(observation(orders=[row],fills=[fill,stopfill]),now_ms=7200000)
    assert out['status']=='FLAT_COSTS_PENDING' and len(g.requests())==1
