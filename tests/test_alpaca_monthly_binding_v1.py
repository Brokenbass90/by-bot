"""Durable monthly/daily binding, without broker writes or legacy state adoption."""
import copy
from datetime import date,datetime,timezone

import pytest

from research_lab import alpaca_monthly_binding_v1 as binding
from research_lab.alpaca_dynamic_v1 import digest


def ms(s):return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)


@pytest.fixture
def calendar():
    days=('2026-10-29','2026-10-30','2026-11-02','2026-11-03','2026-11-04')
    return [dict(session=s,open_ms=ms(s+'T14:30:00'),close_ms=ms(s+'T21:00:00')) for s in days]


@pytest.fixture
def sealed(tmp_path,calendar,monkeypatch):
    monkeypatch.setattr(binding,'prepare_intended_report',lambda *a,**kw:dict(
        picks=[dict(symbol='KEEP',atr20=2.,signal_close=100.,weight=.6)],
        gate_ok=True,reason='ok',selector_source_hashes={}))
    book=binding.MonthlyBook(tmp_path/'book.sqlite',binding.CONTRACT)
    selection=book.seal_selection({},calendar,signal_session='2026-10-30',
        entry_session='2026-11-02',source_available_ms=ms('2026-10-30T21:01:00'),
        source_sha256='a'*64,now_ms=ms('2026-10-30T21:02:00'))
    return book,selection


def fill(selection,symbol='KEEP',price='100',qty='.4'):
    return dict(id='entry-'+symbol,client_order_id=binding.entry_cid(selection,symbol),
        symbol=symbol,side='buy',type='limit',qty=qty,limit_price='110',status='filled',
        filled_qty=qty,filled_avg_price=price,time_in_force='day',
        filled_at='2026-11-02T14:30:02.234131481Z')


def stop(symbol='KEEP',price='96',qty='.4',id='stop-KEEP'):
    return dict(id=id,symbol=symbol,side='sell',type='stop',status='new',qty=qty,
                filled_qty='0',stop_price=price,time_in_force='day')


def source(calendar,day='2026-11-02',close=104.,**extra):
    raw=dict(symbol='KEEP',session=day,open=100.,high=105.,low=97.,close=close)
    end=next(c['close_ms'] for c in calendar if c['session']==day)
    return dict(schema='ALPACA_COMPLETED_SESSION_SOURCE_V1',calendar=calendar,
        source='RECORDED_REGULAR_SESSION_OHLC',raw=[raw],raw_sha256=digest([raw]),
        available_ms=end+1000,completed_ms=end+2000,**extra)


def test_owner_contract_is_monthly_daily_and_disabled():
    contract=getattr(binding,'CONTRACT',{})
    assert contract.get('selection')=='MONTH_END_NEXT_OPEN'
    assert contract.get('ratchet')=='DAILY_CLOSE_NEXT_SESSION'
    assert contract.get('enabled') is False
    assert contract.get('orders_allowed') is False


def test_selection_is_durable_and_missed_cycle_never_reselects(sealed,calendar):
    b,s=sealed
    same=b.seal_selection({},calendar,signal_session='2026-10-30',entry_session='2026-11-02',
        source_available_ms=ms('2026-10-30T21:01:00'),source_sha256='a'*64,now_ms=ms('2026-10-30T21:03:00'))
    assert s==same
    r=b.monthly_actions(s['selection_id'],now_ms=ms('2026-11-03T14:30:00'))
    assert r['status']=='NO_SEND' and r['reason']=='STALE_SIGNAL_RESELECT_FAIL'
    assert b.rows('events')


def test_existing_cycle_cannot_be_overwritten_with_revised_source(sealed,calendar):
    b,s=sealed
    with pytest.raises(ValueError,match='MONTHLY_SOURCE_CONFLICT'):
        b.seal_selection({},calendar,signal_session='2026-10-30',entry_session='2026-11-02',
            source_available_ms=ms('2026-10-30T21:01:00'),source_sha256='b'*64,now_ms=ms('2026-10-30T21:03:00'))


def test_native_binding_rejects_foreign_or_undercovered_stop(sealed):
    b,s=sealed
    with pytest.raises(ValueError,match='ENTRY_OWNER_CONFLICT'):
        b.bind_fill(s['selection_id'],{**fill(s),'client_order_id':'foreign'},stop())
    with pytest.raises(ValueError,match='STOP_COVER_CONFLICT'):
        b.bind_fill(s['selection_id'],fill(s),stop(qty='.3'))
    assert not b.rows('positions')


def test_raw_atr_fill_stop_and_timestamp_precision_survive_restart(sealed,tmp_path):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    old=b.rows('positions')[0]
    reopened=binding.MonthlyBook(tmp_path/'book.sqlite',binding.CONTRACT)
    current=fill(s);current['filled_at']='2026-11-02T14:30:02.234131Z';current['source']='access_key'
    reopened.bind_fill(s['selection_id'],current,stop())
    assert reopened.rows('positions')[0]==old
    with pytest.raises(ValueError):reopened.bind_fill(s['selection_id'],{**current,'filled_avg_price':'101'},stop())


def test_closed_source_retains_native_floor_and_defers_raise_until_next_session(sealed,calendar,tmp_path):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    raw=source(calendar);r=b.observe_close(raw,now_ms=raw['completed_ms'])
    assert r['status']=='DAILY_SOURCE_BOUND'
    p=b.rows('positions')[0]
    assert p['native_floor']==96 and p['daily_state']['hwm']==104
    assert p['daily_state']['active_stop']==100.49
    assert not b.stop_actions(now_ms=ms('2026-11-02T22:00:00'))['actions']
    reloaded=binding.MonthlyBook(tmp_path/'book.sqlite',binding.CONTRACT)
    actions=reloaded.stop_actions(now_ms=ms('2026-11-03T14:30:00'))['actions']
    assert len(actions)==1 and actions[0]['stop_price']==100.49
    assert reloaded.observe_close(raw,now_ms=raw['completed_ms']+1000)['status']=='DAILY_ALREADY_BOUND'
    reloaded.confirm_stop(actions[0]['action_id'],{**stop(price='100.49',id='replacement'),'replaces':'stop-KEEP'},
        observed_ms=ms('2026-11-03T14:30:01'))
    assert not reloaded.stop_actions(now_ms=ms('2026-11-03T14:31:00'))['actions']
    assert reloaded.rows('positions')[0]['native_floor']==100.49


@pytest.mark.parametrize('mutation', ['early','raw_hash','future','missing','bool'])
def test_invalid_source_cannot_become_daily_close_or_move_state(sealed,calendar,mutation):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop());before=b.rows('positions')
    raw=source(calendar);now=raw['completed_ms']
    if mutation=='early':raw['available_ms']=raw['completed_ms']=ms('2026-11-02T20:59:59')
    if mutation=='raw_hash':raw['raw_sha256']='f'*64
    if mutation=='future':raw['completed_ms']=now+1000
    if mutation=='missing':raw['raw']=[];raw['raw_sha256']=digest([])
    if mutation=='bool':raw['raw'][0]['close']=True;raw['raw_sha256']=digest(raw['raw'])
    with pytest.raises(ValueError):b.observe_close(raw,now_ms=now)
    assert b.rows('positions')==before


def test_missing_day_blocks_and_atomic_multi_symbol_failure_rolls_back(sealed,calendar):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop());before=b.rows('positions')
    late=source(calendar,day='2026-11-03')
    with pytest.raises(ValueError,match='MISSING_DAILY_OBSERVATION'):
        b.observe_close(late,now_ms=late['completed_ms'])
    assert b.rows('positions')==before


def test_zero_risk_authority_even_when_prepared_in_open_window(sealed):
    b,s=sealed
    r=b.monthly_actions(s['selection_id'],now_ms=ms('2026-11-02T14:30:00'))
    assert r['status']=='MONTHLY_PLAN_ORDERS_OFF'
    assert r['orders_allowed'] is False and r['money_authority'] is False
    assert r['new_symbols']==['KEEP'] and r['retain']==[] and r['rotate']==[]


def test_same_closed_bar_with_new_retrieval_time_cannot_duplicate_stop_intention(sealed,calendar):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    raw=source(calendar);b.observe_close(raw,now_ms=raw['completed_ms'])
    again={**raw,'completed_ms':raw['completed_ms']+1000}
    b.observe_close(again,now_ms=again['completed_ms'])
    assert len(b.rows('stops'))==1


def test_daily_calendar_cannot_omit_a_held_session(sealed,calendar):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    raw=source(calendar,day='2026-11-03')
    raw['calendar']=[r for r in calendar if r['session']!='2026-11-02']
    with pytest.raises(ValueError,match='DAILY_CALENDAR_SOURCE_CONFLICT'):
        b.observe_close(raw,now_ms=raw['completed_ms'])


def test_stop_above_fill_or_wrong_tif_never_binds(sealed):
    b,s=sealed
    for candidate in [stop(price='97'),stop(price='101'),{**stop(),'time_in_force':'ioc'}]:
        with pytest.raises(ValueError):b.bind_fill(s['selection_id'],fill(s),candidate)
    assert not b.rows('positions')


def test_retained_name_not_rebought_or_hwm_reset_in_next_month(sealed,calendar,monkeypatch):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    raw=source(calendar);b.observe_close(raw,now_ms=raw['completed_ms'])
    before=b.rows('positions')
    next_cal=calendar+[dict(session=d,open_ms=ms(d+'T14:30:00'),close_ms=ms(d+'T21:00:00'))
        for d in ('2026-11-30','2026-12-01','2026-12-02')]
    next_selection=b.seal_selection({},next_cal,signal_session='2026-11-30',entry_session='2026-12-01',
        source_available_ms=ms('2026-11-30T21:01:00'),source_sha256='b'*64,now_ms=ms('2026-11-30T21:02:00'))
    r=b.monthly_actions(next_selection['selection_id'],now_ms=ms('2026-12-01T14:30:00'))
    assert r['retain']==['KEEP'] and r['new_symbols']==[] and r['rotate']==[]
    assert b.rows('positions')==before


def test_rotation_must_finish_before_new_buys_and_does_not_create_stop_cooldown(sealed,calendar,monkeypatch):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    monkeypatch.setattr(binding,'prepare_intended_report',lambda *a,**kw:dict(picks=[dict(
        symbol='NEW',atr20=2.,signal_close=100.,weight=.6)],gate_ok=True,reason='ok'))
    next_cal=calendar+[dict(session=d,open_ms=ms(d+'T14:30:00'),close_ms=ms(d+'T21:00:00'))
        for d in ('2026-11-30','2026-12-01','2026-12-02')]
    n=b.seal_selection({},next_cal,signal_session='2026-11-30',entry_session='2026-12-01',
        source_available_ms=ms('2026-11-30T21:01:00'),source_sha256='b'*64,now_ms=ms('2026-11-30T21:02:00'))
    r=b.monthly_actions(n['selection_id'],now_ms=ms('2026-12-01T14:30:00'))
    assert r['rotate']==['KEEP'] and r['new_symbols']==[]
    intent=r['rotation_intentions'][0]
    exit_order=dict(id='exit-owned',client_order_id=intent['client_order_id'],symbol='KEEP',
        side='sell',type='market',status='filled',qty='.4',filled_qty='.4',
        filled_avg_price='102',filled_at='2026-12-01T14:30:01Z')
    b.record_exit('KEEP',[exit_order],reason='monthly_rotation_next_open',
        observed_ms=ms('2026-12-01T14:30:02'),remaining_qty='0',open_order_ids=[])
    r=b.monthly_actions(n['selection_id'],now_ms=ms('2026-12-01T14:30:02'))
    assert r['new_symbols']==['NEW'] and r['cooldown_symbols']==[]


def test_only_owned_full_terminal_exit_creates_twenty_one_day_stop_block(sealed):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    exit_order=dict(id='stop-KEEP',symbol='KEEP',side='sell',type='stop',status='filled',
        qty='.4',filled_qty='.4',filled_avg_price='96',filled_at='2026-11-02T14:31:00Z')
    with pytest.raises(ValueError):
        b.record_exit('KEEP',[{**exit_order,'id':'foreign'}],reason='protective_stop_intraday',
            observed_ms=ms('2026-11-02T14:31:01'),remaining_qty='0',open_order_ids=[])
    with pytest.raises(ValueError):
        b.record_exit('KEEP',[exit_order],reason='protective_stop_intraday',
            observed_ms=ms('2026-11-02T14:31:01'),remaining_qty='.1',open_order_ids=[])
    b.record_exit('KEEP',[exit_order],reason='protective_stop_intraday',
        observed_ms=ms('2026-11-02T14:31:01'),remaining_qty='0',open_order_ids=[])
    r=b.monthly_actions(s['selection_id'],now_ms=ms('2026-11-02T14:31:02'))
    assert not r['new_symbols'] and r['cooldown_symbols']==['KEEP']


def test_foreign_stop_or_early_ack_never_consumes_pending_raise(sealed,calendar):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop());raw=source(calendar)
    b.observe_close(raw,now_ms=raw['completed_ms'])
    a=b.rows('stops')[0]
    with pytest.raises(ValueError,match='STOP_CONFIRMATION_OWNER_OR_TIME'):
        b.confirm_stop(a['action_id'],stop(price='100.49',id='foreign'),observed_ms=ms('2026-11-03T14:30:01'))
    with pytest.raises(ValueError,match='STOP_CONFIRMATION_OWNER_OR_TIME'):
        b.confirm_stop(a['action_id'],{**stop(price='100.49',id='new'),'replaces':'stop-KEEP'},
            observed_ms=ms('2026-11-02T22:00:00'))
    assert b.rows('positions')[0]['native_floor']==96
    assert b.rows('stops')[0]['confirmed'] is False


def test_twenty_one_calendar_days_expire_at_session_date_not_fill_clock(sealed,calendar):
    b,s=sealed;b.bind_fill(s['selection_id'],fill(s),stop())
    exit_order=dict(id='stop-KEEP',symbol='KEEP',side='sell',type='stop',status='filled',
        qty='.4',filled_qty='.4',filled_avg_price='96',filled_at='2026-11-10T20:00:00Z')
    b.record_exit('KEEP',[exit_order],reason='protective_stop_intraday',
        observed_ms=ms('2026-11-10T20:00:01'),remaining_qty='0',open_order_ids=[])
    next_cal=calendar+[dict(session=d,open_ms=ms(d+'T14:30:00'),close_ms=ms(d+'T21:00:00'))
        for d in ('2026-11-30','2026-12-01','2026-12-02')]
    n=b.seal_selection({},next_cal,signal_session='2026-11-30',entry_session='2026-12-01',
        source_available_ms=ms('2026-11-30T21:01:00'),source_sha256='b'*64,now_ms=ms('2026-11-30T21:02:00'))
    r=b.monthly_actions(n['selection_id'],now_ms=ms('2026-12-01T14:30:00'))
    assert r['new_symbols']==['KEEP'] and not r['cooldown_symbols']
