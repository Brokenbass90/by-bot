"""Monthly source → existing native dispatch → durable book, with fake I/O only."""
import copy
import json
from datetime import datetime,timezone

import pytest
from research_lab import alpaca_monthly_binding_v1 as bookmod
from research_lab import alpaca_monthly_native_binding_v1 as binding
from test_alpaca_monthly_native_adapter_v1 import Broker


def ms(s):return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('ALPACA_INTENDED_PAPER','1');monkeypatch.setenv('ALPACA_INTENDED_LIVE','0')
    pick=dict(symbol='NET',atr20=16.771206665045003,signal_close=360.9299926758,weight=.6)
    report=lambda *a,**k:dict(picks=[pick],gate_ok=True,reason='ok')
    monkeypatch.setattr(bookmod,'prepare_intended_report',report)
    monkeypatch.setattr(binding.baseline,'prepare_intended_report',report)
    calendar=[dict(session=d,open_ms=ms(d+'T14:30:00'),close_ms=ms(d+'T21:00:00'))
              for d in ('2026-10-30','2026-11-02','2026-11-03')]
    book=bookmod.MonthlyBook(tmp_path/'monthly.sqlite',bookmod.CONTRACT)
    s=book.seal_selection({},calendar,signal_session='2026-10-30',entry_session='2026-11-02',
        source_available_ms=ms('2026-10-30T21:01:00'),source_sha256='a'*64,now_ms=ms('2026-10-30T21:02:00'))
    io=Broker(); now=ms('2026-11-02T14:30:00')
    io.get_account=lambda:dict(id='fixture',cash='487.42',non_marginable_buying_power='487.42',
        equity='487.42',trading_blocked=False,account_blocked=False)
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-02T14:30:00Z')
    io.get_asset=lambda symbol:dict(symbol=symbol,status='active',tradable=True,fractionable=True)
    io.latest_quote=lambda symbol:dict(ap='311',t='2026-11-02T14:30:00Z')
    adapter=binding.MonthlyNativeBinding(book,client=io,base_url=binding.native._PAPER_API_URL,
        account_id='fixture',capital=487.42,runtime=tmp_path/'native',lock_path=tmp_path/'shared.lock',
        entry_halt_path=tmp_path/'original-entry-halt.json')
    return book,s,adapter,io,now


def ticket(setup):
    b,s,a,io,now=setup
    return a.prepare_entry({},s['selection_id'],'NET',quote=dict(ask=311.,quote_ts=now,
        received_ms=now,source='recorded-iex'),now_ms=now,cash=487.42,open_equity=487.42)


def test_default_off_prepares_without_transport_or_adopting_current_net(setup):
    b,s,a,io,now=setup;t=ticket(setup)
    assert t['status']=='MONTHLY_NATIVE_ENTRY_PREPARED_ORDERS_OFF'
    assert a.enter(t,now_ms=now)['orders_allowed'] is False
    assert not io.sent and not b.rows('positions')


def test_actual_native_entry_path_binds_atr_quote_stop_and_no_duplicate_on_restart(setup):
    b,s,a,io,now=setup;t=ticket(setup);io.lose_once=True
    with pytest.raises(OSError):a.enter(t,now_ms=now,apply=True)
    assert a.enter(t,now_ms=now+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert io.sent==['buy','stop'] and b.rows('positions')[0]['native_floor']==277.67
    stored=json.loads(a.reentry.read_text())['entry_intents'][t['client_order_id']]
    assert stored['baseline_entry_gate']['quote_source']=='recorded-iex'
    assert a.enter(t,now_ms=now+2000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert io.sent==['buy','stop']


def test_missed_session_and_halt_block_before_dispatch(setup):
    b,s,a,io,now=setup;t=ticket(setup)
    with pytest.raises(ValueError,match='STALE_SIGNAL'):
        a.enter(t,now_ms=now+300000,apply=True)
    a.halt.parent.mkdir(parents=True,exist_ok=True);a.halt.write_text('{}')
    with pytest.raises(ValueError,match='ENTRY_HALT'):
        a.enter(t,now_ms=now,apply=True)
    assert not io.sent


def test_foreign_native_ledger_is_never_migrated(setup):
    b,s,a,io,now=setup;t=ticket(setup)
    a.ledger.parent.mkdir(parents=True,exist_ok=True)
    a.ledger.write_text(json.dumps({'NET':dict(entry_order_id='current-off-protocol-NET')}))
    before=a.ledger.read_bytes()
    with pytest.raises(ValueError,match='MONTHLY_NATIVE_OWNER_CONFLICT'):
        a.enter(t,now_ms=now,apply=True)
    assert not io.sent and a.ledger.read_bytes()==before


def test_modified_ticket_or_raw_atr_cannot_send(setup):
    b,s,a,io,now=setup;t=ticket(setup)
    with pytest.raises(ValueError,match='TICKET_HASH'):
        a.enter({**t,'notional':200.},now_ms=now,apply=True)
    assert not io.sent


def test_daily_raise_and_expired_day_rearm_do_not_use_intraday_high(setup):
    b,s,a,io,now=setup;t=ticket(setup);a.enter(t,now_ms=now,apply=True)
    end=ms('2026-11-02T21:00:00');raw=[dict(symbol='NET',session='2026-11-02',
        open=311.222,high=380.,low=300.,close=325.)]
    b.observe_close(dict(schema='ALPACA_COMPLETED_SESSION_SOURCE_V1',source='RECORDED_REGULAR_SESSION_OHLC',
        raw=raw,raw_sha256=bookmod.digest(raw),calendar=s['calendar'],available_ms=end,completed_ms=end),now_ms=end)
    assert b.rows('positions')[0]['daily_state']['hwm']==325.
    io.orders['stop']['status']='expired'
    io.positions[0]['current_price']='326'
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-03T14:30:00Z')
    out=a.maintain(now_ms=ms('2026-11-03T14:30:00'),apply=True)
    assert out['status']=='MONTHLY_NATIVE_PROTECTED'
    assert io.sent==['buy','stop','stop']
    assert b.rows('positions')[0]['native_floor']==313.62
    assert json.loads(a.ledger.read_text())['NET']['hwm']==325.
    assert a.maintain(now_ms=ms('2026-11-03T14:30:00'),apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert io.sent==['buy','stop','stop']


def test_unknown_stop_send_is_never_repeated(setup):
    b,s,a,io,now=setup;t=ticket(setup);a.enter(t,now_ms=now,apply=True)
    io.orders['stop']['status']='expired';io.positions[0]['current_price']='320'
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-03T14:30:00Z')
    sends=[]
    def lost(*args,**kwargs):sends.append(kwargs);raise TimeoutError('unknown stop send')
    io.submit_stop_sell=lost
    with pytest.raises(TimeoutError):a.maintain(now_ms=ms('2026-11-03T14:30:00'),apply=True)
    with pytest.raises(ValueError,match='UNCERTAIN_STOP_NO_RESEND'):
        a.maintain(now_ms=ms('2026-11-03T14:30:00'),apply=True)
    assert len(sends)==1


def test_initial_stop_response_loss_recovers_pending_native_record(setup):
    b,s,a,io,now=setup;t=ticket(setup);submit=io.submit_stop_sell
    def lost(*args,**kwargs):submit(*args,**kwargs);raise TimeoutError('accepted stop response lost')
    io.submit_stop_sell=lost
    with pytest.raises(TimeoutError):a.enter(t,now_ms=now,apply=True)
    io.submit_stop_sell=submit
    assert a.enter(t,now_ms=now+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert io.sent==['buy','stop'] and len(b.rows('positions'))==1


def test_maintenance_cannot_apply_without_existing_native_approval(setup,monkeypatch):
    b,s,a,io,now=setup;t=ticket(setup);a.enter(t,now_ms=now,apply=True)
    monkeypatch.setenv('ALPACA_INTENDED_PAPER','0')
    with pytest.raises(binding.native.IntendedPaperProtectionError):
        a.maintain(now_ms=now,apply=True)
    assert io.sent==['buy','stop']


def test_rotation_retirement_crash_recovers_book_before_new_admission(setup,monkeypatch):
    b,s,a,io,now=setup;a.enter(ticket(setup),now_ms=now,apply=True)
    monkeypatch.setattr(bookmod,'prepare_intended_report',lambda *args,**kw:dict(
        picks=[dict(symbol='NEW',atr20=2.,signal_close=100.,weight=.6)],gate_ok=True,reason='ok'))
    calendar=s['calendar']+[dict(session=d,open_ms=ms(d+'T14:30:00'),close_ms=ms(d+'T21:00:00'))
        for d in ('2026-11-30','2026-12-01','2026-12-02')]
    selection=b.seal_selection({},calendar,signal_session='2026-11-30',entry_session='2026-12-01',
        source_available_ms=ms('2026-11-30T21:00:01'),source_sha256='b'*64,now_ms=ms('2026-11-30T21:00:02'))
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-12-01T14:30:01Z')
    def cancel(id):io.orders[id]['status']='canceled'
    io.cancel_order=cancel
    def sell(symbol,qty,*,client_order_id):
        io.sent.append('sell');io.positions=[]
        o=dict(id='exit',client_order_id=client_order_id,symbol=symbol,side='sell',type='market',
            status='filled',qty=str(qty),filled_qty=str(qty),filled_avg_price='320',filled_at='2026-12-01T14:30:01Z')
        io.orders['exit']=o;return copy.deepcopy(o)
    io.submit_market_sell_qty=sell
    original=b.record_exit
    def crash(*args,**kw):raise OSError('crash after native rotation retired')
    monkeypatch.setattr(b,'record_exit',crash)
    with pytest.raises(OSError):a.rotate(selection['selection_id'],now_ms=ms('2026-12-01T14:30:02'),apply=True)
    monkeypatch.setattr(b,'record_exit',original)
    assert a.rotate(selection['selection_id'],now_ms=ms('2026-12-01T14:30:03'),apply=True)['new_symbols']==['NEW']
    assert io.sent==['buy','stop','sell'] and not b.rows('positions')


def test_native_stop_exit_and_partial_remaining_are_owned_readback_only(setup):
    b,s,a,io,now=setup;a.enter(ticket(setup),now_ms=now,apply=True)
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-02T14:31:00Z')
    io.orders['stop'].update(status='partially_filled',filled_qty='.1',filled_avg_price='277',
        filled_at='2026-11-02T14:30:59Z')
    io.positions[0]['qty']='.2'
    out=a.maintain(now_ms=now+60000,apply=True)
    assert out['status']=='MONTHLY_PARTIAL_STOP_PROTECTED' and out['remaining_qty']=='0.2'
    io.orders['stop'].update(status='filled',filled_qty='.3');io.positions=[]
    assert a.maintain(now_ms=now+60000,apply=True)['status']=='MONTHLY_EXIT_PENDING_ACCOUNTING'
    assert not b.rows('positions') and io.sent==['buy','stop']


def test_gap_below_floor_reuses_existing_durable_scoped_unwind(setup):
    b,s,a,io,now=setup;a.enter(ticket(setup),now_ms=now,apply=True)
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-03T14:30:00Z')
    io.orders['stop']['status']='expired';io.positions[0]['current_price']='270'
    def post(method,path,payload):
        assert method=='POST' and payload['type']=='market' and payload['side']=='sell'
        io.sent.append('sell');io.positions=[]
        out=dict(**payload,id='gap-exit',status='filled',filled_qty='.3',filled_avg_price='270',
            filled_at='2026-11-03T14:30:00Z');io.orders['gap-exit']=out;return out
    io._request=post
    out=a.maintain(now_ms=ms('2026-11-03T14:30:00'),apply=True)
    assert out['status']=='MONTHLY_EXIT_PENDING_ACCOUNTING' and a.halt.exists()
    assert io.sent==['buy','stop','sell'] and not b.rows('positions')


def test_unknown_initial_stop_is_not_resent_if_broker_lookup_temporarily_empty(setup):
    b,s,a,io,now=setup;t=ticket(setup);sends=[]
    def lost(*args,**kw):sends.append(kw);raise TimeoutError('unknown stop delivery')
    io.submit_stop_sell=lost
    with pytest.raises(TimeoutError):a.enter(t,now_ms=now,apply=True)
    with pytest.raises(binding.native.IntendedPaperProtectionError,match='uncertain_monthly_stop_no_resend'):
        a.enter(t,now_ms=now+1000,apply=True)
    assert len(sends)==1


def test_definitive_initial_stop_rejection_uses_existing_emergency_exit(setup):
    b,s,a,io,now=setup;t=ticket(setup)
    def reject(*args,**kw):raise binding.native.AlpacaAPIError(422,'stop rejected')
    io.submit_stop_sell=reject
    def post(method,path,payload):
        assert method=='POST' and payload['type']=='market' and payload['side']=='sell'
        io.sent.append('sell');io.positions=[]
        out=dict(**payload,id='emergency',status='filled',filled_qty='.3',filled_avg_price='310',
            filled_at='2026-11-02T14:30:02Z');io.orders['emergency']=out;return out
    io._request=post
    out=a.enter(t,now_ms=now+2000,apply=True)
    assert out['status']=='MONTHLY_EXIT_PENDING_ACCOUNTING' and a.halt.exists()
    assert io.sent==['buy','sell'] and not b.rows('positions')
    assert b.rows('exits')[0]['reason']=='emergency_protection_failure'


def test_exit_crash_between_native_and_monthly_commits_is_reconciled(setup,monkeypatch):
    b,s,a,io,now=setup;a.enter(ticket(setup),now_ms=now,apply=True)
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-02T14:31:00Z')
    io.orders['stop'].update(status='filled',filled_qty='.3',filled_avg_price='277',filled_at='2026-11-02T14:30:59Z')
    io.positions=[];record_exit=b.record_exit
    monkeypatch.setattr(b,'record_exit',lambda *args,**kw:(_ for _ in ()).throw(OSError('second journal failed')))
    with pytest.raises(OSError):a.maintain(now_ms=now+60000,apply=True)
    monkeypatch.setattr(b,'record_exit',record_exit)
    assert a.maintain(now_ms=now+60000,apply=True)['status']=='MONTHLY_EXIT_PENDING_ACCOUNTING'
    assert not b.rows('positions') and io.sent==['buy','stop']
