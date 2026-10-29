from copy import deepcopy
from pathlib import Path
import pytest
from research_lab.kity_weekly_rehearsal_v1 import WeeklyRehearsal, DAY, make_profile, routing_check


def profile():
    return make_profile('2026-10-22',[{'symbol':f'L{i}USDT','side':1,'qty':'1','entry_reference_price':'100'} for i in range(5)] +
                        [{'symbol':f'S{i}USDT','side':-1,'qty':'1','entry_reference_price':'100'} for i in range(5)],
                        {'signal':'a'*64,'entry':'b'*64,'c2':'c'*64},funding_intervals={f'{side}{i}USDT':480 for side in ('L','S') for i in range(5)})


def event(p,kind,symbol,ms,**kw):
    return dict(event_id=kind+'-'+symbol+'-'+str(ms)+'-'+str(kw.get('exec_id',kw.get('settlement_id',''))),
                kind=kind,symbol=symbol,observed_ms=ms,**kw)


def enter(w,p):
    t=p['entry_reference_ms']
    for leg in p['legs']:
        s=leg['symbol'];w.append(event(p,'MODEL_ENTRY_FILL',s,t,exec_id='entry-'+s,qty='1',price='100',fee_usdt='0.06'))
        w.append(event(p,'PROTECTION',s,t,qty='1',stop_price='90' if leg['side']==1 else '110',
                       contract='CONTINGENCY_FIXTURE_ONLY',status='ACCEPTED'))


def close(w,p):
    t=p['exit_reference_ms']
    for leg in p['legs']:
        s=leg['symbol']
        w.append(event(p,'MODEL_EXIT_FILL',s,t+1,exec_id='exit-'+s,qty='1',price='100',fee_usdt='0.06'))
        w.append(event(p,'PROTECTION',s,t+1,qty='0',status='CANCELLED',contract='CONTINGENCY_FIXTURE_ONLY'))
    w.append(event(p,'MODEL_COST_FINALITY','ALL',t+2,fees_complete=True,funding_complete=True))


def test_complete_week_restart_and_duplicate(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);enter(w,p)
    assert w.state()['protected_full'] is True
    for k in range(1,22):
        t=p['entry_reference_ms']+k*8*3600000
        for leg in p['legs']:
            s=leg['symbol'];w.append(event(p,'MODEL_FUNDING',s,t,settlement_id=str(t),qty='1',mark='100',rate='0.001',
                         cash_usdt='-0.1' if leg['side']==1 else '0.1'))
    before=w.state();w=WeeklyRehearsal(tmp_path/'weekly',p);assert w.state()==before
    close(w,p);r=w.state()
    assert r['terminal_complete'] and r['model_capital_released']
    assert r['net_usdt']=='-1.20' and r['funding_cash_usdt']=='0.0'
    assert r['actual_broker_writes']==0 and r['real_cost_finality_proven'] is False
    assert r['exit_early_by_strategy'] is False
    n=len(w.events.read());w.append(event(p,'MODEL_COST_FINALITY','ALL',p['exit_reference_ms']+2,fees_complete=True,funding_complete=True))
    assert len(w.events.read())==n


def test_early_exit_no_invented_weekly_stop_rule(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);enter(w,p)
    with pytest.raises(ValueError,match='EARLY_STRATEGY_EXIT'):
        w.append(event(p,'MODEL_EXIT_FILL','L0USDT',p['entry_reference_ms']+DAY,exec_id='early',qty='1',price='99',fee_usdt='0.06'))
    assert w.state()['held']['L0USDT']=='1'


def test_lost_ack_and_partial_fill_never_resend_or_complete_missing_basket(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);t=p['entry_reference_ms']
    w.append(event(p,'UNKNOWN_ENTRY_ACK','L0USDT',t))
    with pytest.raises(ValueError,match='ACK_RECONCILIATION_REQUIRED'):
        w.append(event(p,'MODEL_ENTRY_FILL','L0USDT',t,exec_id='e1',qty='0.4',price='100',fee_usdt='0.024'))
    w=WeeklyRehearsal(tmp_path/'weekly',p)
    w.append(event(p,'ACK_RECONCILED','L0USDT',t+1))
    fill=event(p,'MODEL_ENTRY_FILL','L0USDT',t+2,exec_id='e1',qty='0.4',price='100',fee_usdt='0.024')
    w.append(fill);w.append(dict(fill,event_id='new-delivery',observed_ms=t+3))
    assert w.state()['held']['L0USDT']=='0.4'
    w.append(event(p,'MODEL_ENTRY_REJECT','L1USDT',t+4))
    w.append(event(p,'MODEL_EMERGENCY_EXIT_FILL','L0USDT',t+5,exec_id='x1',qty='0.4',price='99',fee_usdt='0.024'))
    r=w.state();assert r['failed_basket'] and not r['terminal_complete'] and not r['model_capital_released']
    assert all(__import__('decimal').Decimal(v)==0 for v in r['held'].values())


def test_pending_costs_not_zero_and_r5_persists(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);t=p['entry_reference_ms']
    w.append(event(p,'OPERATIONAL_FAIL','ALL',t));w.append(event(p,'OPERATIONAL_FAIL','ALL',t+1))
    w=WeeklyRehearsal(tmp_path/'weekly',p);assert w.state()['r5_entry_halt']
    with pytest.raises(ValueError,match='R5_ENTRY_HALT'):
        w.append(event(p,'MODEL_ENTRY_FILL','L0USDT',t+2,exec_id='e1',qty='1',price='100',fee_usdt=None))
    assert w.state()['net_usdt'] is None


def test_partial_journal_cannot_be_repaired(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);enter(w,p)
    with w.events.path.open('ab') as f:f.write(b'{')
    raw=w.events.path.read_bytes()
    with pytest.raises(ValueError):WeeklyRehearsal(tmp_path/'weekly',p).state()
    assert w.events.path.read_bytes()==raw


def test_current_live_scope_cannot_route_kity():
    r=routing_check({'schema':'PUMP4_ACCOUNT_OWNER_SCOPE_V1','mode':'OWNER_TINY_LIVE',
                     'policy':{'max_entries':1,'max_positions':1}},profile())
    assert not r['admitted'] and not r['orders_allowed'] and r['live_scope_change_required']


def test_native_stop_contingency_is_separate_from_weekly_strategy(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);enter(w,p);t=p['entry_reference_ms']+DAY
    with pytest.raises(ValueError,match='STOP_TRIGGER_OR_COVERAGE'):
        w.append(event(p,'MODEL_NATIVE_STOP_FILL','L0USDT',t,exec_id='bad-stop',qty='1',price='95',fee_usdt='0.06'))
    w.append(event(p,'MODEL_NATIVE_STOP_FILL','L0USDT',t,exec_id='native-stop',qty='1',price='89',fee_usdt='0.06'))
    r=w.state();assert r['off_protocol_contingency'] and not r['terminal_complete']
    assert r['held']['L0USDT']=='0' and r['held']['L1USDT']=='1'


def test_missing_funding_cannot_be_zero_finality(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);enter(w,p)
    with pytest.raises(ValueError,match='FUNDING_COVERAGE_INCOMPLETE'):close(w,p)
    r=w.state();assert r['net_usdt'] is None and not r['model_capital_released']


def test_duplicate_funding_after_finality_does_not_revoke_model_finality(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);enter(w,p)
    for k in range(1,22):
        t=p['entry_reference_ms']+k*8*3600000
        for leg in p['legs']:
            w.append(event(p,'MODEL_FUNDING',leg['symbol'],t,settlement_id=str(t),qty='1',mark='100',rate='0.001',
                           cash_usdt='-0.1' if leg['side']==1 else '0.1'))
    close(w,p);before=w.state();settle=p['entry_reference_ms']+8*3600000
    w.append(event(p,'MODEL_FUNDING','L0USDT',p['exit_reference_ms']+DAY,settlement_id=str(settle),qty='1',mark='100',rate='0.001',cash_usdt='-0.1'))
    assert w.state()==before


def test_funding_off_calendar_is_rejected(tmp_path):
    p=profile();w=WeeklyRehearsal(tmp_path/'weekly',p);enter(w,p);t=p['entry_reference_ms']+1
    with pytest.raises(ValueError,match='FUNDING_CALENDAR'):
        w.append(event(p,'MODEL_FUNDING','L0USDT',t,settlement_id=str(t),qty='1',mark='100',rate='.001',cash_usdt='-.1'))
