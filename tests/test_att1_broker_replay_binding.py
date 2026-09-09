"""Synthetic broker-shaped fixtures; never private account receipts."""
from copy import deepcopy
from fractions import Fraction

import pytest

from test_att1_lifecycle_coordinator import fixture, ev, T, SHA
from research_lab.att1_lifecycle_profile import (
    bind_broker_replay_profile, validate_profile, admit_signal, ProfileViolation,
)
from research_lab.att1_lifecycle_coordinator import replay_lifecycle, CoordinatorViolation
from research_lab.att1_lifecycle_session import LifecycleSession
from bot.att1_coordinator_adapter import map_execution, map_funding, map_order_final, map_protection, AdapterViolation


def bound():
    base, intent = fixture()
    profile = bind_broker_replay_profile(base, {
        'base_profile_sha256': base['profile_sha256'],
        'account_fingerprint_sha256': 'd' * 64,
        'broker_truth_sha256': 'e' * 64,
        'account_mode': 'UNIFIED_ONE_WAY_USDT', 'observed_ms': T + 20,
        'absolute_risk_cap': '0.55', 'old_budget_ceiling': '0.6',
        'max_notional': '50', 'daily_loss_cap': '1.1',
        'max_concurrent_positions': 1, 'send_enabled': False,
    })
    intent['book'] = 'ATT1_BROKER_REPLAY:' + 'd' * 64
    return base, profile, intent


def execution(t=40, **changes):
    row = {'symbol': 'BTCUSDT', 'orderId': 'broker-order-fixture',
           'orderLinkId': 'fixture-link', 'execId': 'fixture-fill',
           'execType': 'Trade', 'side': 'Sell', 'execQty': '0.05',
           'execPrice': '100', 'execFee': '0.005', 'feeCurrency': 'USDT',
           'isMaker': False, 'execTime': str(T + t), 'closedSize': '0',
           'extraFees': ''}
    row.update(changes)
    return row


def mapped(row, **kw):
    return map_execution(row, symbol='BTCUSDT', expected_order_id='broker-order-fixture',
                         expected_order_link_id='fixture-link', kind='ENTRY_FILL',
                         received_ms=T + 50, **kw)


def test_binding_preserves_frozen_strategy_and_caps_worst_entry_risk():
    base, profile, intent = bound()
    assert base['profile_sha256'] == '79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050'
    assert profile['strategy'] == base['strategy']
    assert profile['source_sha256'] == base['source_sha256']
    assert profile['profile_sha256'] != base['profile_sha256']
    validate_profile(base)
    result = replay_lifecycle(profile, intent, [])
    assert result['plan']['requested_qty'] == '0.05'
    assert Fraction(result['plan']['requested_qty']) * 11 <= Fraction('0.55')
    assert result['authority']['orders_allowed'] is False
    assert result['execution_evidence'] == 'BROKER_REPLAY_INPUTS_NOT_AUTHENTICATED'


@pytest.mark.parametrize('field,value', [('absolute_risk_cap','0.7'), ('max_notional','101'),
    ('daily_loss_cap','1.11'), ('max_concurrent_positions',2), ('send_enabled',True)])
def test_unsafe_binding_rejected(field, value):
    base, profile, _ = bound()
    binding = deepcopy(profile['broker_binding']); binding[field] = value
    with pytest.raises(ProfileViolation): bind_broker_replay_profile(base, binding)


def test_stale_or_foreign_book_binding_rejects_admission():
    _, profile, intent = bound()
    intent['book'] = 'foreign'
    assert not replay_lifecycle(profile, intent, [])['admission']['accepted']
    intent['book'] = 'ATT1_BROKER_REPLAY:' + 'd' * 64
    intent['submit_ms'] = T + 2030
    intent['signal']['signal_ready_ms'] = T + 2029
    assert replay_lifecycle(profile, intent, [])['admission']['code'] == 'BROKER_TRUTH_STALE'


@pytest.mark.parametrize('change', [{'orderId':'foreign'}, {'orderLinkId':'foreign'},
    {'symbol':'ETHUSDT'}, {'execType':'Funding'}, {'side':'Buy'}, {'feeCurrency':''},
    {'feeCurrency':'BTC'}, {'closedSize':'0.01'}, {'extraFees':'unmapped'}, {'isMaker':'false'}])
def test_execution_mapping_fails_closed(change):
    with pytest.raises(AdapterViolation): mapped(execution(**change))


def test_real_cash_rounding_delayed_funding_and_restart(tmp_path):
    _, profile, intent = bound()
    s = LifecycleSession(tmp_path/'broker-replay.jsonl', profile, intent=intent)
    s.apply(ev('ENTRY_ACK',31))
    s.apply(mapped(execution()))
    s.apply(ev('PROTECTION_ACK',51,qty='0.05',stop='110'))
    s.apply(ev('ENTRY_FINAL',52,status='FILLED'))
    s.apply(ev('PRICE',20000,bid='111',ask='112'))
    oid = s.receipt['pending_exit']['exit_order_id']
    s.apply(ev('EXIT_ACK',20002,exit_order_id=oid))
    out = execution(20003, side='Buy', execId='fixture-exit', execPrice='112',
                    execFee='0.0056', closedSize='0.05')
    s.apply(map_execution(out, symbol='BTCUSDT', expected_order_id='broker-order-fixture',
                         expected_order_link_id='fixture-link', kind='EXIT_FILL',
                         received_ms=T+20004, exit_order_id=oid))
    s.apply(ev('EXIT_FINAL',20005,exit_order_id=oid,status='FILLED'))
    row = {'id':'funding-fixture', 'symbol':'BTCUSDT','category':'linear',
           'currency':'USDT','type':'SETTLEMENT','side':'Sell','qty':'0.05','size':'-0.05',
           'funding':'0.00049999','cashFlow':'0','fee':'0','change':'0.00049999',
           'bonusChange':'','extraFees':'','transSubType':'','transactionTime':str(T+10000)}
    funding = map_funding(row,symbol='BTCUSDT',received_ms=T+80000)
    s.apply(funding)
    s.apply(ev('FUNDING_COVERAGE',80001,start_ms=T,end_ms=T+25005,
               settlement_ms=[T+10000],complete=True))
    before = s.receipt
    assert before['accounting']['settled_funding'] == str(Fraction('0.00049999'))
    assert before['final_net_r'] == str((Fraction('-0.6')-Fraction('0.0106')+Fraction('0.00049999'))/Fraction('0.5'))
    assert before['actual_account_costs_verified'] is False
    assert LifecycleSession(s.journal.path,profile).receipt == before
    redelivery = deepcopy(funding); redelivery['event_id'] += ':redelivery'; redelivery['received_ms'] += 10
    s.apply(redelivery)
    assert s.receipt['final_net_r'] == before['final_net_r']
    redelivery['event_id'] += ':conflict'; redelivery['cash_amount'] = '0.001'
    with pytest.raises(CoordinatorViolation): s.apply(redelivery)


def test_synthetic_profile_cannot_accept_broker_cash_event():
    base, _, _ = bound()
    _, intent = fixture()
    with pytest.raises(CoordinatorViolation, match='broker'):
        replay_lifecycle(base,intent,[ev('FUNDING_CASH',10000,settlement_id='x',
            settlement_ms=T+10000,qty_at_settlement='0',cash_amount='0',currency='USDT')])


def test_order_ack_or_cancel_request_is_not_finality_and_missing_fill_blocks():
    _, profile, intent = bound()
    receipt = replay_lifecycle(profile,intent,[])
    row = {'symbol':'BTCUSDT','side':'Sell','positionIdx':0,'reduceOnly':False,
           'orderId':'fixture-order','orderLinkId':'fixture-link','qty':'0.05',
           'cumExecQty':'0.05','orderStatus':'Filled','updatedTime':str(T+100)}
    args = dict(receipt=receipt,expected_order_id='fixture-order',
                expected_order_link_id='fixture-link',received_ms=T+101,entry=True)
    with pytest.raises(AdapterViolation,match='unreconciled'): map_order_final(row,**args)
    for status in ('New','PartiallyFilled','PendingCancel','unknown'):
        row['orderStatus']=status
        with pytest.raises(AdapterViolation): map_order_final(row,**args)
    row.update(orderStatus='Cancelled',cumExecQty='0')
    event = map_order_final(row,**args)
    assert event['kind']=='ENTRY_FINAL' and event['status']=='CANCELLED'
    assert replay_lifecycle(profile,intent,[event])['terminal_nonfill']


def test_protection_requires_broker_position_and_actual_conditional_stop():
    _, profile, intent = bound()
    receipt = replay_lifecycle(profile,intent,[mapped(execution())])
    position={'symbol':'BTCUSDT','side':'Sell','size':'0.05','positionIdx':0,
              'stopLoss':'110','updatedTime':str(T+51)}
    stop={'symbol':'BTCUSDT','side':'Buy','qty':'0.05','positionIdx':0,
          'orderId':'actual-stop','orderStatus':'Untriggered','stopOrderType':'StopLoss',
          'reduceOnly':True,'closeOnTrigger':True,'triggerPrice':'110','updatedTime':str(T+52)}
    assert map_protection(position,stop,receipt=receipt,received_ms=T+53)['kind']=='PROTECTION_ACK'
    for change in ({'qty':'0.04'},{'triggerPrice':'109'},{'orderStatus':'New'},
                   {'reduceOnly':False},{'positionIdx':2}):
        with pytest.raises(AdapterViolation):
            map_protection(position,{**stop,**change},receipt=receipt,received_ms=T+53)
    with pytest.raises(AdapterViolation):
        map_protection(position,{'retCode':0},receipt=receipt,received_ms=T+53)
