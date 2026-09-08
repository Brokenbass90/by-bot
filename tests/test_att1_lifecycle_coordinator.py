from copy import deepcopy
from pathlib import Path
from fractions import Fraction

import pytest

from research_lab.att1_lifecycle_profile import build_profile
from research_lab.att1_lifecycle_coordinator import CoordinatorViolation, replay_lifecycle

ROOT = Path(__file__).resolve().parents[1]
T = 1800 * 3600000
SHA = 'a' * 64


def fixture():
    profile = build_profile(ROOT)
    signal = {'schema_id':'att1_lifecycle_signal_v1','symbol':'BTCUSDT','side':'short','stream':'EXECUTION_FORWARD',
              'bar_close_ms':T,'source_available_ms':T+10,'signal_ready_ms':T+20,'entry':'100','sl':'110',
              'tps':['88','75'],'tp_fracs':['0.55','0.45'],'be_trigger_rr':'0','be_lock_rr':'0.02',
              'trailing_atr_mult':'0','trailing_atr_period':14,'trail_activate_rr':'1','time_stop_bars_5m':4032,
              'source_sha256':SHA,'data_sha256':'b'*64,'profile_sha256':profile['profile_sha256']}
    instrument = {'symbol':'BTCUSDT','tick_size':'0.01','qty_step':'0.01','min_order_qty':'0.01',
                  'min_notional':'1','max_market_qty':'10','observed_ms':T+10,'source_sha256':'c'*64}
    intent = {'signal':signal,'instrument':instrument,'book_state':{'active_decision_id':None,'last_admitted_bar_ms':None,'last_terminal_ms':None},'book':'ATT1_TEST','submit_ms':T+30}
    return profile, intent


def ev(kind, t, eid=None, **fields):
    return {'schema_id':'att1_lifecycle_event_v1','event_id':eid or f'{kind}:{t}', 'kind':kind,
            'exchange_ms':T+t,'received_ms':T+t+1,'source_sha256':SHA,**fields}


def fill(kind, t, qty, price, fee='0', **kw):
    return ev(kind,t,execution_id=f'ex:{t}',qty=qty,price=price,fee_amount=fee,fee_source_sha256=SHA,liquidity='TAKER',**kw)


def start():
    return [ev('ENTRY_ACK',31),fill('ENTRY_FILL',40,'0.1','100','0.01'),
            ev('PROTECTION_ACK',42,qty='0.1',stop='110'),ev('ENTRY_FINAL',44,status='FILLED')]


def replay(events, intent=None):
    profile, default = fixture()
    return replay_lifecycle(profile, intent or default, events)


def exit_events(events, t, qty, price, fee='0', status='FILLED'):
    oid = replay(events)['pending_exit']['exit_order_id']
    return [ev('EXIT_ACK',t,exit_order_id=oid),fill('EXIT_FILL',t+2,qty,price,fee,exit_order_id=oid),
            ev('EXIT_FINAL',t+4,exit_order_id=oid,status=status)]


def coverage(t, **kw):
    return ev('FUNDING_COVERAGE',t,start_ms=T,end_ms=T+t,settlement_ms=[],complete=True,**kw)


def test_full_literal_two_target_lifecycle_and_costed_net_r():
    events=start()
    opened=replay(events)
    assert opened['held_qty']=='1/10'
    assert opened['targets']==['88','75']
    assert opened['final_net_r'] is None
    events.append(ev('PRICE',100,bid='87.99',ask='88'))
    assert replay(events)['pending_exit']['reason']=='TP1'
    events+=exit_events(events,102,'0.05','88','0.0044')
    events.append(ev('PRICE',200,bid='74.99',ask='75'))
    assert replay(events)['pending_exit']['qty']=='1/20'
    events+=exit_events(events,202,'0.05','75','0.00375')
    assert replay(events)['lifecycle_terminal'] is False
    events.append(coverage(300))
    result=replay(events)
    assert result['accounting']['gross_realized']=='37/20'
    assert result['accounting']['known_fee_total']=='363/20000'
    assert result['final_net_r']=='36637/20000'
    assert result['lifecycle_terminal'] is True
    assert result['held_qty']=='0'
    assert all(v is False for v in result['authority'].values())
    assert replay(events)==result


def test_ack_no_fill_and_expired_nonfill_are_not_trades():
    events=[ev('ENTRY_ACK',31),ev('CLOCK',2031)]
    result=replay(events)
    assert result['held_qty']=='0' and result['intents']['cancel_entry'] is True
    assert result['final_net_r'] is None
    events.append(ev('ENTRY_FINAL',2033,status='EXPIRED'))
    result=replay(events)
    assert result['terminal_nonfill'] is True and result['lifecycle_terminal'] is False


def test_partial_entry_requires_resize_protection_and_finality_before_targets():
    events=[fill('ENTRY_FILL',40,'0.04','100'),ev('PROTECTION_ACK',42,qty='0.04',stop='110')]
    result=replay(events)
    assert result['targets']==[] and result['held_qty']=='1/25'
    events+=[fill('ENTRY_FILL',44,'0.06','100'),ev('PROTECTION_ACK',46,qty='0.1',stop='110'),ev('ENTRY_FINAL',48,status='FILLED')]
    assert replay(events)['protected_qty']=='1/10'
    assert replay(events)['targets']==['88','75']


def test_stop_gap_costs_exit_and_exit_ack_is_not_fill():
    events=start()+[ev('PRICE',100,bid='111.99',ask='112')]
    result=replay(events)
    assert result['pending_exit']['reason']=='SL'
    oid=result['pending_exit']['exit_order_id']
    events.append(ev('EXIT_ACK',102,exit_order_id=oid))
    assert replay(events)['held_qty']=='1/10'
    events+=[fill('EXIT_FILL',104,'0.1','112','0.0112',exit_order_id=oid),ev('EXIT_FINAL',106,exit_order_id=oid,status='FILLED'),coverage(200)]
    assert replay(events)['final_net_r']=='-3053/2500'


def test_exit_before_entry_final_keeps_pending_entry_visible():
    events=[fill('ENTRY_FILL',40,'0.04','100'),ev('PROTECTION_ACK',42,qty='0.04',stop='110'),ev('PRICE',50,bid='111.99',ask='112')]
    assert replay(events)['intents']['cancel_entry'] is True
    events+=exit_events(events,52,'0.04','112')
    assert replay(events)['pending_entry_qty']=='3/50'
    assert replay(events)['exposure_terminal'] is False
    events+=[fill('ENTRY_FILL',60,'0.02','100'),ev('PROTECTION_ACK',62,qty='0.02',stop='110'),ev('ENTRY_FINAL',64,status='CANCELLED')]
    assert replay(events)['held_qty']=='1/50'


def test_execution_redelivery_does_not_repeat_exposure_or_fees():
    events=start()
    alias=deepcopy(events[1]);alias['event_id']='delivery2';alias['received_ms']=T+100
    result=replay(events+[alias])
    assert result['held_qty']=='1/10' and result['accounting']['known_fee_total']=='1/100'
    alias['price']='99'
    with pytest.raises(CoordinatorViolation,match='execution'):
        replay(events+[alias])


def test_unprotected_observation_and_recovery_gap_block_clean_cohort():
    events=[fill('ENTRY_FILL',40,'0.1','100'),ev('PRICE',50,bid='99.99',ask='100')]
    result=replay(events)
    assert 'UNPROTECTED_MARKET' in result['incidents']
    assert result['pending_exit']['reason']=='INCIDENT'
    recovered=replay(start()+[ev('RECOVERY_GAP',100,reason='lost public stream')])
    assert 'RECOVERY_GAP' in recovered['incidents'] and recovered['held_qty']=='1/10'


def test_no_implicit_be_trailing_and_first_fill_time_deadline():
    events=start()+[ev('PRICE',100,bid='89.99',ask='90')]
    result=replay(events)
    assert result['pending_exit'] is None
    assert result['protection_stop']=='110'
    deadline=result['time_deadline_ms']
    assert deadline==T+40+336*3600000
    events.append(ev('CLOCK',deadline-T))
    assert replay(events)['pending_exit']['reason']=='TIME'
    with pytest.raises(CoordinatorViolation,match='stop'):
        replay(start()+[ev('PROTECTION_ACK',100,qty='0.1',stop='100')])


def test_invalid_event_is_rejected_without_retiming_or_foreign_fill():
    with pytest.raises(CoordinatorViolation): replay([ev('ENTRY_ACK',1)])
    with pytest.raises(CoordinatorViolation): replay(start()+[ev('PRICE',100,bid='100',ask='99')])
    with pytest.raises(CoordinatorViolation): replay(start()+[fill('EXIT_FILL',100,'0.1','90',exit_order_id='foreign')])
    with pytest.raises(CoordinatorViolation): replay(start()+[ev('PRICE',100,bid='90',ask='90',received_ms=T+5000)])
    bad=ev('ENTRY_ACK',31);bad['received_ms']=True
    with pytest.raises(CoordinatorViolation): replay([bad])


def test_missing_fee_and_funding_prevent_final_net_r():
    events=start();events[1]['fee_amount']=None
    events.append(ev('PRICE',100,bid='111',ask='112'))
    events+=exit_events(events,102,'0.1','112')
    events.append(coverage(200))
    result=replay(events)
    assert result['accounting']['costs_complete'] is False
    assert result['final_net_r'] is None and result['lifecycle_terminal'] is False


def test_partial_target_cancel_retries_only_unfilled_target_quantity():
    events=start()+[ev('PRICE',100,bid='87.99',ask='88')]
    events+=exit_events(events,102,'0.02','88',status='CANCELLED')
    events.append(ev('PRICE',110,bid='87.99',ask='88'))
    assert replay(events)['pending_exit']['qty']=='3/100'
    events+=exit_events(events,112,'0.03','88')
    events.append(ev('PRICE',200,bid='74.99',ask='75'))
    events+=exit_events(events,202,'0.05','75')
    events.append(coverage(300))
    assert replay(events)['final_net_r']=='46/25'


def test_flat_without_exit_finality_cannot_publish_final_net_r():
    events=start()+[ev('PRICE',100,bid='111',ask='112')]
    oid=replay(events)['pending_exit']['exit_order_id']
    events+=[fill('EXIT_FILL',104,'0.1','112',exit_order_id=oid),coverage(105)]
    result=replay(events)
    assert result['held_qty']=='0' and result['accounting']['closed_net_r'] is not None
    assert result['final_net_r'] is None and result['lifecycle_terminal'] is False
    events.append(ev('EXIT_FINAL',106,exit_order_id=oid,status='FILLED'))
    assert replay(events)['lifecycle_terminal'] is True


def test_delayed_settlement_after_exit_reconciles_without_reordering_price_events():
    events=start()+[ev('PRICE',20000,bid='111',ask='112')]
    events+=exit_events(events,20002,'0.1','112')
    events.append(ev('FUNDING',10000,received_ms=T+21000,settlement_id='f1',settlement_ms=T+10000,qty_at_settlement='0.1',mark_price='100',rate='0.001'))
    assert replay(events)['final_net_r'] is None
    events.append(ev('FUNDING_COVERAGE',22000,start_ms=T,end_ms=T+22000,settlement_ms=[T+10000],complete=True))
    result=replay(events)
    assert result['accounting']['settled_funding']=='1/100'
    assert result['final_net_r']=='-6/5'
    assert events[-2]['exchange_ms']==T+10000 and events[-2]['received_ms']==T+21000
    with pytest.raises(CoordinatorViolation,match='shrink'):
        replay(events+[coverage(23000)])


def test_late_entry_keeps_finalized_r0_and_incident_exposure():
    result=replay(start()+[fill('ENTRY_FILL',60,'0.01','100')])
    assert result['held_qty']=='11/100'
    assert result['accounting']['fixed_r0']=='1'
    assert 'INCIDENT_UNEXPECTED_ENTRY_FILL' in result['incidents']
    assert result['pending_exit']['reason']=='INCIDENT'
    assert result['final_net_r'] is None


def test_late_protection_ack_does_not_erase_unprotected_interval():
    result=replay([fill('ENTRY_FILL',40,'0.1','100'),ev('PROTECTION_ACK',3000,qty='0.1',stop='110')])
    assert result['protected_qty']=='1/10'
    assert 'PROTECTION_ACK_TIMEOUT' in result['incidents']
    assert result['pending_exit']['reason']=='INCIDENT'


def test_open_valuation_cannot_reuse_expired_funding_coverage():
    events=start()+[coverage(100),ev('PRICE',8*3600000,bid='99.99',ask='100')]
    result=replay(events)
    assert result['accounting']['funding_coverage_complete'] is False
    assert result['accounting']['costs_complete'] is False
    assert result['accounting']['net_equity_change'] is None
    assert 'FUNDING_COVERAGE_INCOMPLETE' in result['accounting']['issues']
