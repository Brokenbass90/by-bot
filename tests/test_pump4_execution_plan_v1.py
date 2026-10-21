"""Frozen PUMP4 geometry only; no broker, evaluator or strategy mutation."""
import copy
import pytest
from strategies.signals import TradeSignal
from research_lab import pump4_execution_plan_v1 as plans

H=3600000

def signal(side='short'):
    return TradeSignal(strategy='pump_fade',symbol='AAAUSDT',side=side,entry=100.,
        sl=101. if side=='short' else 99.,tp=97.9 if side=='short' else 102.1,
        tps=[97.9,95.8,93.] if side=='short' else [102.1,104.2,107.],
        tp_fracs=[.4,.3,.3],trailing_atr_mult=1.4,time_stop_bars=48)

@pytest.mark.parametrize('side',['long','short'])
def test_frozen_plan_is_orders_off_and_ignores_unused_v1_fields(side):
    s=signal(side);before=copy.deepcopy(s)
    p=plans.build_plan(s,signal_bar_open_ms=H,next_open_ms=2*H,next_open=100.)
    assert p['entry']==100. and p['stop']==(104. if side=='short' else 96.)
    assert p['targets']==s.tps[:2] and p['fractions']==[.4,.6]
    assert p['hold_bars']==168 and p['stop_checked_first'] is True
    assert p['orders_allowed'] is p['money_authority'] is False
    assert p['funding_cost']=='UNKNOWN' and p['geometric_leverage']==25.
    assert p['model_fee_rate_per_side']==.0006 and s==before
    s.trailing_atr_mult=9.;s.time_stop_bars=4;s.tps[2]=70.;s.tp_fracs[1:]=[.1,.5]
    assert plans.build_plan(s,signal_bar_open_ms=H,next_open_ms=2*H,next_open=100.)==p

@pytest.mark.parametrize('fault',['timestamp','next_hour','bool','nan','side','fraction','stop','target','leverage','pf'])
def test_invalid_or_unfrozen_plan_fails_closed(fault,monkeypatch):
    s=signal();kw=dict(signal_bar_open_ms=H,next_open_ms=2*H,next_open=100.)
    if fault=='timestamp':kw['signal_bar_open_ms']=H+1
    elif fault=='next_hour':kw['next_open_ms']=3*H
    elif fault=='bool':kw['next_open']=True
    elif fault=='nan':kw['next_open']=float('nan')
    elif fault=='side':s.side='buy'
    elif fault=='fraction':s.tp_fracs[0]=.55
    elif fault=='stop':s.sl=99.
    elif fault=='target':s.tps[0]=101.
    elif fault=='leverage':s.sl=100.01
    else:monkeypatch.setenv('PF_V4_RR','3')
    with pytest.raises(ValueError):plans.build_plan(s,**kw)
