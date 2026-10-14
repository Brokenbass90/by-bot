import copy
from datetime import datetime,timezone
from tests.test_alpaca_dynamic_live_runtime_v1 import setup,case,run,NOW

# Break caught: a normal broker fill after CLI start is rejected as future.
def test_actual_fill_after_call_start_is_checked_at_receive_time(setup,monkeypatch):
    module,broker,*_=setup
    elapsed=[1000.0];monkeypatch.setattr(module.time,'monotonic',lambda:elapsed[0])
    original=broker._request
    def delayed(method,path,payload=None):
        elapsed[0]+=.2
        row=original(method,path,payload)
        if payload and payload['side']=='buy':
            row['filled_at']=datetime.fromtimestamp((NOW+3200)/1000,timezone.utc).isoformat()
            broker.orders[row['id']]['filled_at']=row['filled_at']
        return row
    monkeypatch.setattr(broker,'_request',delayed)
    result=run(setup,apply=True)
    assert result['status']=='LIVE_PROTECTED',result
    assert result['filled_qty']=='.5' or result['filled_qty']=='0.5'
    assert len([p for p in broker.writes if p.get('side')=='buy'])==1
    assert len([p for p in broker.writes if p.get('type')=='stop'])==1

# Break caught: time spent receiving owned-state GETs is mistaken for broker clock drift.
def test_maintenance_clock_uses_current_observation_after_gets(setup,monkeypatch):
    assert run(setup,apply=True)['status']=='LIVE_PROTECTED'
    module,broker,*_=setup;elapsed=[1000.0]
    monkeypatch.setattr(module.time,'monotonic',lambda:elapsed[0])
    original=broker.list_orders;base=NOW+60000
    def delayed(*args,**kwargs):
        elapsed[0]+=3;broker.clock_ms=base+int((elapsed[0]-1000)*1000)
        return original(*args,**kwargs)
    monkeypatch.setattr(broker,'list_orders',delayed)
    result=run(setup,now=base,apply=True,maintenance=True)
    assert result['status']=='LIVE_PROTECTED',result

def test_preflight_http_elapsed_is_not_broker_clock_drift(setup,monkeypatch):
    module,broker,*_=setup;elapsed=[1000.0]
    monkeypatch.setattr(module.time,'monotonic',lambda:elapsed[0]);original=broker.get_account
    def delayed_account():elapsed[0]+=3;return original()
    def clock():return dict(is_open=True,timestamp=datetime.fromtimestamp((NOW+3000+int((elapsed[0]-1000)*1000))/1000,timezone.utc).isoformat())
    monkeypatch.setattr(broker,'get_account',delayed_account);monkeypatch.setattr(broker,'get_clock',clock)
    result=run(setup,apply=True)
    assert result['status']=='LIVE_PROTECTED',result
