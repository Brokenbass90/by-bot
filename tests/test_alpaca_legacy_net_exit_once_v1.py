import copy
import pytest
from scripts import alpaca_legacy_net_exit_once_v1 as exit_once


def plan():
    return dict(session='2026-11-02',open_ms=1793629800000,end_ms=1793630100000,
        entry_order_id='705a1b5b-1d45-4ba1-97cf-9c646033d78d',symbol='NET',
        initial_quantity='0.325167779',intake_sha256='a'*64)


def test_default_has_no_clock_source_broker_or_mutation(capsys,monkeypatch):
    monkeypatch.setattr(exit_once,'load',lambda *a:pytest.fail('loaded'))
    assert exit_once.main([])==0
    assert 'OFFLINE_NO_AUTHORITY' in capsys.readouterr().out


@pytest.mark.parametrize('delta',[-1,0,299999,300000])
def test_exact_window_no_date_or_dst_transfer(delta):
    p=plan()
    if 0<=delta<300000:exit_once.window(p,p['open_ms']+delta)
    else:
        with pytest.raises(ValueError):exit_once.window(p,p['open_ms']+delta)


def test_future_calendar_has_correct_new_york_and_cyprus_dst():
    p=plan()
    assert exit_once.calendar_open([dict(date='2026-11-02',open='09:30')])==p['open_ms']
    with pytest.raises(ValueError):exit_once.calendar_open([dict(date='2026-11-02',open='08:30')])


def test_original_entry_only_no_adoption_of_new_monthly_net():
    p=plan();item=dict(entry=dict(id=p['entry_order_id']),intake=dict(intake_sha256='a'*64,plan=dict(symbol='NET',qty='0.325167779')))
    exit_once.owned_identity(p,item)
    for key in ['entry','intake']:
        bad=copy.deepcopy(item)
        if key=='entry':bad[key]['id']='new-monthly-entry'
        else:bad[key]['plan']['qty']='1'
        with pytest.raises(ValueError):exit_once.owned_identity(p,bad)
