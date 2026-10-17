"""Readback only: never claim a queued stop, stale capture or weekend is protected."""
import copy
from datetime import datetime

import pytest

from research_lab import alpaca_day_protection_v1 as audit


def ms(text):
    return int(datetime.fromisoformat(text).timestamp()*1000)


def source():
    now=ms('2026-10-19T13:31:00+00:00')
    stop=dict(id='owned-stop',symbol='NET',side='sell',type='stop',status='new',
        time_in_force='day',qty='.325167779',filled_qty='0',stop_price='277.69')
    return dict(schema='ALPACA_DAY_PROTECTION_SOURCE_V1',started_ms=now-1000,completed_ms=now,
        clock=dict(timestamp='2026-10-19T09:31:00-04:00',is_open=True),
        calendar=[dict(date='2026-10-19',open='09:30',close='16:00')],
        positions=[dict(symbol='NET',side='long',qty='.325167779',avg_entry_price='311.222')],
        expected={'NET':dict(accepted_order_id='owned-stop',accepted_stop_floor='277.69',
            qty='.325167779',entry_price='311.222')},
        open_orders=[stop],stop_readbacks=[copy.deepcopy(stop)],orders_complete=True,
        account_identity_verified=True,ledger_unchanged=True,source_pins_verified=56)


def test_actual_stop_readback_is_required_and_inputs_unchanged():
    s=source();before=copy.deepcopy(s)
    r=audit.evaluate(s,now_ms=s['completed_ms'])
    assert r['status']=='DAY_PROTECTION_CONFIRMED' and not r['issues']
    assert r['coverage'][0]['status']=='PROTECTED'
    assert s==before and r['orders_allowed'] is False and r['broker_writes']==0


def test_first_regular_tick_without_stop_is_critical_without_a_grace_period():
    s=source();s['open_orders']=[];s['stop_readbacks'][0]['status']='expired'
    r=audit.evaluate(s,now_ms=s['completed_ms'])
    assert r['status']=='DAY_PROTECTION_MISSING'
    assert r['issues']==[dict(code='DAY_STOP_MISSING',severity='CRITICAL',symbol='NET')]
    assert r['regular_session_elapsed_minutes']==1


@pytest.mark.parametrize('mutation',[
    ('qty','.325167778'),('side','buy'),('type','limit'),('stop_price','277.68'),
    ('status','pending_new'),('status','pending_replace'),('time_in_force','gtc'),('id','foreign'),
])
def test_material_stop_conflicts_never_become_protected(mutation):
    s=source();key,value=mutation;s['open_orders'][0][key]=value
    s['stop_readbacks'][0][key]=value
    r=audit.evaluate(s,now_ms=s['completed_ms'])
    assert r['status']=='DAY_PROTECTION_UNKNOWN' and r['issues']


def test_list_orders_does_not_substitute_for_actual_get_order_readback():
    s=source();s['stop_readbacks'][0]['status']='canceled'
    assert audit.evaluate(s,now_ms=s['completed_ms'])['status']=='DAY_PROTECTION_UNKNOWN'


@pytest.mark.parametrize('field',['orders_complete','account_identity_verified','ledger_unchanged'])
def test_incomplete_or_conflicting_capture_is_unknown(field):
    s=source();s[field]=False
    assert audit.evaluate(s,now_ms=s['completed_ms'])['status']=='DAY_PROTECTION_UNKNOWN'


@pytest.mark.parametrize('value',[True,'NaN','Infinity','-1',None])
def test_invalid_position_quantity_is_unknown(value):
    s=source();s['positions'][0]['qty']=value
    assert audit.evaluate(s,now_ms=s['completed_ms'])['status']=='DAY_PROTECTION_UNKNOWN'


def test_stale_and_future_evidence_never_become_pass():
    s=source()
    for now in (s['completed_ms']+5001,s['completed_ms']-1):
        assert audit.evaluate(s,now_ms=now)['status']=='DAY_PROTECTION_UNKNOWN'


def test_calendar_and_clock_must_agree():
    s=source();s['clock']['is_open']=False
    assert audit.evaluate(s,now_ms=s['completed_ms'])['status']=='DAY_PROTECTION_UNKNOWN'


def test_weekend_absence_is_closed_not_a_regular_session_outage():
    s=source();s['completed_ms']=ms('2026-10-17T06:28:39+00:00');s['started_ms']=s['completed_ms']-1000
    s['clock']=dict(timestamp='2026-10-17T02:28:39-04:00',is_open=False)
    s['calendar']=[];s['open_orders']=[];s['stop_readbacks'][0]['status']='expired'
    r=audit.evaluate(s,now_ms=s['completed_ms'])
    assert r['status']=='DAY_CLOSED_SESSION' and not r['issues']
    assert r['regular_session_elapsed_minutes']==0 and r['coverage'][0]['status']=='OUTSIDE_RTH'


def test_short_session_uses_calendar_close_not_a_fixed_utc_schedule():
    s=source();s['completed_ms']=ms('2026-11-27T18:01:00+00:00');s['started_ms']=s['completed_ms']-1000
    s['clock']=dict(timestamp='2026-11-27T13:01:00-05:00',is_open=False)
    s['calendar']=[dict(date='2026-11-27',open='09:30',close='13:00')]
    assert audit.evaluate(s,now_ms=s['completed_ms'])['status']=='DAY_CLOSED_SESSION'


def test_existing_whole_share_gtc_protection_is_not_rejected_as_a_day_gap():
    s=source();s['positions'][0]['qty']=s['expected']['NET']['qty']='1'
    for row in (s['open_orders'][0],s['stop_readbacks'][0]):
        row.update(qty='1',time_in_force='gtc')
    assert audit.evaluate(s,now_ms=s['completed_ms'])['status']=='DAY_PROTECTION_CONFIRMED'


def test_flat_with_no_owned_open_order_is_not_a_missing_stop():
    s=source();s['positions']=[];s['open_orders']=[]
    assert audit.evaluate(s,now_ms=s['completed_ms'])['status']=='DAY_NO_OWNED_EXPOSURE_OBSERVED'
    # This remains an observation, not exit accounting/finality proof.


def test_sampling_gaps_remain_unknown_in_the_duration_report():
    s=source();missing=copy.deepcopy(s);missing['open_orders']=[];missing['stop_readbacks'][0]['status']='expired'
    a=audit.evaluate(missing,now_ms=s['completed_ms'])
    s['completed_ms']+=300000;s['started_ms']+=300000
    s['clock']['timestamp']='2026-10-19T09:36:00-04:00'
    b=audit.evaluate(s,now_ms=s['completed_ms'])
    r=audit.summarize([a,b],session='2026-10-19')
    assert r['unprotected_observations']==1 and r['protected_observations']==1
    assert r['first_confirmed_protection_delay_minutes']==6
    assert r['maximum_observation_gap_minutes']==5
    assert r['actual_unprotected_minutes'] is None
    assert r['duration_status']=='UNKNOWN_BETWEEN_POINT_OBSERVATIONS'


def test_duplicate_observations_do_not_inflate_metrics():
    s=source();r=audit.evaluate(s,now_ms=s['completed_ms'])
    assert audit.summarize([r,r],session='2026-10-19')['observations']==1


def test_saved_replay_is_labeled_and_receipt_cannot_be_overwritten(tmp_path):
    import json
    from scripts.audit_alpaca_day_protection_v1 import main
    capture=tmp_path/'capture.json';output=tmp_path/'receipt.json'
    capture.write_text(json.dumps(source()))
    args=['--capture-json',str(capture),'--output',str(output),'--replay-recorded-time']
    assert main(args)==0
    old=output.read_bytes();receipt=json.loads(old)
    assert receipt['mode']=='OFFLINE_SAVED_SOURCE_REPLAY'
    assert receipt['replay_is_fresh_broker_observation'] is False
    assert receipt['observer_activated'] is False and receipt['notifications_sent']==0
    with pytest.raises(FileExistsError):main(args)
    assert output.read_bytes()==old
