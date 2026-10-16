"""Future-entry parity only; these tests cannot start the installed NET manager."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from research_lab import alpaca_strategy_parity_v1 as parity


def ms(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()*1000)


@pytest.fixture
def calendar():
    return [dict(session=day, open_ms=ms(day+'T13:30:00'), close_ms=ms(day+'T20:00:00'))
            for day in ('2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03')]


def test_fill_anchor_uses_raw_atr_and_reference_downward_grid():
    # Recorded NET inputs: old implementation rounded an ask-based distance to
    # 33.54 and rounded the stop upward. The baseline requires 277.67 here.
    assert parity.initial_stop(311.222, 16.771206665045003) == 277.67


def test_nonpositive_atr_stop_uses_exact_reference_five_percent_fallback():
    assert parity.initial_stop(10, 6) == 9.5
    assert parity.initial_stop(.9, .01) == .88


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1, 0])
def test_bad_atr_never_becomes_a_reference_stop(value):
    with pytest.raises(ValueError):
        parity.initial_stop(100, value)


def test_intraday_observation_cannot_ratchet_or_consume_daily_close(calendar):
    state=parity.initial_state('NET', 100, 2, '2026-10-30')
    before=deepcopy(state)
    r=parity.daily_transition(state, dict(session='2026-10-30', open=100,
        high=500, low=97, close=104), calendar, ms('2026-10-30T19:59:59'))
    assert r['status']=='NOT_DUE'
    assert r['state']==before and state==before


def test_high_is_not_hwm_and_new_close_stop_cannot_fire_same_bar(calendar):
    state=parity.initial_state('NET', 100, 2, '2026-10-30')
    r=parity.daily_transition(state, dict(session='2026-10-30', open=100,
        high=500, low=97, close=104), calendar, ms('2026-10-30T20:00:00'))
    assert r['status']=='DAILY_CLOSE_OBSERVED'
    assert r['state']['hwm']==104
    # Preserve the frozen runner's binary-float expression then ROUND_DOWN;
    # 100*(1+.5/100) is 100.49999999999999 in that implementation.
    assert r['state']['active_stop']==100.49
    assert r['stop_effective_session']=='2026-11-02'
    # Low 97 is below the NEW stop but above the old 96 stop.
    assert r.get('exit_reason') is None
    next_r=parity.daily_transition(r['state'], dict(session='2026-11-02',
        open=99, high=102, low=98, close=101), calendar, ms('2026-11-02T20:00:00'))
    assert next_r['exit_reason']=='protective_stop_gap_open'
    assert next_r['exit_reference']==99


def test_gap_exit_precedes_low_and_ratchet(calendar):
    state=parity.initial_state('NET', 100, 2, '2026-10-30')
    r=parity.daily_transition(state, dict(session='2026-10-30', open=95,
        high=200, low=90, close=150), calendar, ms('2026-10-30T20:00:00'))
    assert r['exit_reason']=='entry_gap_below_signal_stop'
    assert r['exit_reference']==95
    assert r['state']['hwm']==100 and r['state']['active_stop']==96


def test_restart_duplicate_daily_bar_is_idempotent_and_conflict_blocks(calendar):
    state=parity.initial_state('NET', 100, 2, '2026-10-30')
    bar=dict(session='2026-10-30',open=100,high=105,low=97,close=104)
    r=parity.daily_transition(state,bar,calendar,ms('2026-10-30T20:00:00'))
    assert parity.daily_transition(r['state'],bar,calendar,ms('2026-10-30T20:01:00'))['status']=='ALREADY_OBSERVED'
    with pytest.raises(ValueError,match='DAILY_BAR_CONFLICT'):
        parity.daily_transition(r['state'],{**bar,'close':103},calendar,ms('2026-10-30T20:01:00'))


def test_stop_never_loosens_when_market_ceiling_drops_below_old_stop(calendar):
    state=parity.initial_state('NET',100,2,'2026-10-29')
    state.update(hwm=110,active_stop=105,last_observed_session='2026-10-29')
    r=parity.daily_transition(state,dict(session='2026-10-30',open=106,
        high=107,low=105.01,close=105.02),calendar,ms('2026-10-30T20:00:00'))
    assert r['state']['active_stop']==105


def test_off_cycle_or_missed_entry_cannot_select_or_substitute(calendar,monkeypatch):
    def forbidden(*a,**k):
        raise AssertionError('must refuse before selector/source consumption')
    monkeypatch.setattr(parity,'prepare_intended_report',forbidden)
    for signal,intended,actual in [('2026-10-29','2026-10-30','2026-10-30'),
                                    ('2026-10-30','2026-11-02','2026-11-03')]:
        r=parity.entry_gate({},calendar,signal_session=signal,
            intended_entry_session=intended,entry_session=actual,symbol='NET',
            history_available_ms=0,quote={},now_ms=ms(actual+'T13:30:00'))
        assert r['status']=='NO_SEND'
        assert r['reason']=='STALE_SIGNAL_RESELECT_FAIL'
        assert r['orders_allowed'] is False


def test_weekend_month_end_valid_quote_provenance_and_fill_receipt(calendar,monkeypatch):
    monkeypatch.setattr(parity,'prepare_intended_report',lambda *a,**k:dict(
        gate_ok=True,picks=[dict(symbol='NET',atr20=2,signal_close=100,weight=.6)],
        selector_source_hashes={'fixture':'fixture'}))
    quote=dict(ask=101,quote_ts=ms('2026-11-02T13:30:00'),
        received_ms=ms('2026-11-02T13:30:00'),source='IEX')
    r=parity.entry_gate({},calendar,signal_session='2026-10-30',
        intended_entry_session='2026-11-02',entry_session='2026-11-02',symbol='NET',
        history_available_ms=ms('2026-10-30T20:00:00'),quote=quote,
        now_ms=ms('2026-11-02T13:30:01'))
    assert r['status']=='ENTRY_PARITY_CANDIDATE'
    assert r['atr20_session']=='2026-10-30' and r['quote_source']=='IEX'
    fill=dict(id='owned-id',symbol='NET',side='buy',type='limit',status='filled',
        filled_qty='.3',filled_avg_price='101.123',filled_at='2026-11-02T13:30:02Z')
    bound=parity.fill_receipt(r,fill)
    assert bound['stop_price']==97.12
    assert bound['actual_fill']==101.123 and bound['orders_allowed'] is False
    assert bound['signal_at']==ms('2026-10-30T20:00:00')
    with pytest.raises(ValueError,match='FILL_SYMBOL_CONFLICT'):
        parity.fill_receipt(r,{**fill,'symbol':'AMD'})
    with pytest.raises(ValueError,match='FILL_TIMESTAMP_TIMEZONE_UNKNOWN'):
        parity.fill_receipt(r,{**fill,'filled_at':'2026-11-02T13:30:02'})
    with pytest.raises(ValueError,match='ENTRY_GATE_HASH_CONFLICT'):
        parity.fill_receipt({**r,'atr20':1},fill)


@pytest.mark.parametrize('change', [dict(source=''),dict(quote_ts=None),
    dict(quote_ts=ms('2026-11-02T13:30:03')),dict(quote_ts=ms('2026-11-02T13:20:00'))])
def test_unknown_future_stale_quote_blocks(calendar,monkeypatch,change):
    monkeypatch.setattr(parity,'prepare_intended_report',lambda *a,**k:dict(
        gate_ok=True,picks=[dict(symbol='NET',atr20=2,signal_close=100,weight=.6)],
        selector_source_hashes={}))
    q=dict(ask=101,quote_ts=ms('2026-11-02T13:30:00'),
        received_ms=ms('2026-11-02T13:30:00'),source='IEX');q.update(change)
    r=parity.entry_gate({},calendar,signal_session='2026-10-30',intended_entry_session='2026-11-02',
        entry_session='2026-11-02',symbol='NET',history_available_ms=ms('2026-10-30T20:00:00'),
        quote=q,now_ms=ms('2026-11-02T13:30:01'))
    assert r['status']=='BLOCKED_DATA' and r['orders_allowed'] is False
