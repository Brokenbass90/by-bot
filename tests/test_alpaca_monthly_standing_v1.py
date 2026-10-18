"""Standing grant acceptance; fixture grants/HTTP only, never money authority."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from research_lab import alpaca_monthly_native_binding_v1 as mod
from research_lab.alpaca_dynamic_v1 import canonical,digest
from test_alpaca_monthly_native_binding_v1 import setup,ticket
from test_alpaca_monthly_account_transport_v1 import connect_wire


def standing(adapter,now,*,limit=4):
    p=Path(adapter.live_scope_path);scope=json.loads(p.read_bytes())
    scope.pop('symbol');scope.pop('selection_id')
    scope.update(schema='ALPACA_MONTHLY_STANDING_OWNER_SCOPE_V1',
        max_new_entries_per_session=limit,valid_from_ms=now-3600000,
        valid_until_ms=now+90*86400000,revocation_path=str(p.parent/'standing-revoked.json'),
        max_cumulative_net_loss_usd='20',
        universe_sha256=digest(list(mod.monthly_universe())),
        selection_policy='EXISTING_SEALED_FROZEN_MONTHLY_ONLY',
        source_files=[dict(path=str(mod.ROOT/n),sha256=h) for n,h in mod.standing_source_pins().items()])
    resign(adapter,scope);return scope


def resign(adapter,scope):
    Path(adapter.live_scope_path).write_bytes(canonical(scope))
    adapter.live_scope_sha256=hashlib.sha256(Path(adapter.live_scope_path).read_bytes()).hexdigest()
    Path(adapter.owner_go_path).write_bytes(canonical(dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',
        scope_sha256=adapter.live_scope_sha256,
        owner_go_text='GO ALPACA_MONTHLY_STANDING '+adapter.live_scope_sha256)))


def test_standing_grant_enters_through_existing_native_wire(setup,monkeypatch):
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch)
    standing(a,now)
    saved=ticket(setup)
    assert a.enter(saved,now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert len(writes)==2 and len(b.rows('positions'))==1
    assert a.enter(saved,now_ms=now+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert len(writes)==2


@pytest.mark.parametrize('defect',['expired','future','revoked','wrong_go','universe','closure','bad_limit','bad_loss'])
def test_standing_invalid_grants_never_send(setup,monkeypatch,defect):
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(a,now)
    if defect=='expired':scope['valid_until_ms']=now
    elif defect=='future':scope['valid_from_ms']=now+3600000
    elif defect=='revoked':Path(scope['revocation_path']).write_text('{}')
    elif defect=='universe':scope['universe_sha256']='f'*64
    elif defect=='closure':scope['source_files']=[r for r in scope['source_files'] if not r['path'].endswith('alpaca_monthly_cycle_v1.py')]
    elif defect=='bad_limit':scope['max_new_entries_per_session']=True
    elif defect=='bad_loss':scope['max_cumulative_net_loss_usd']='NaN'
    resign(a,scope)
    if defect=='wrong_go':Path(a.owner_go_path).write_text('{}')
    with pytest.raises(ValueError):a.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[]


@pytest.mark.parametrize('block',['expired','revoked'])
def test_standing_expiry_or_revocation_keeps_owned_maintenance(setup,monkeypatch,block):
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(a,now)
    a.enter(ticket(setup),now_ms=now,apply=True)
    if block=='expired':scope['valid_until_ms']=now+1000;resign(a,scope)
    else:Path(scope['revocation_path']).write_text('{}')
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-11-02T14:31:00Z')
    assert a.maintain(now_ms=now+60000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert len(writes)==2


def test_session_attempt_ceiling_survives_failed_reservation_and_new_grant(setup,monkeypatch):
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(a,now,limit=1)
    a.reentry.parent.mkdir();a.reentry.write_text(json.dumps(dict(entry_intents={'old':dict(
        entry_session=s['entry_session'],status='reserved')})))
    scope['valid_until_ms']+=1000;resign(a,scope)
    with pytest.raises(ValueError,match='SESSION_ENTRY'):a.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[]


def test_standing_final_validator_sees_revocation_after_reservation(setup,monkeypatch):
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(a,now)
    original=client.get_clock
    def clock():
        if a.reentry.exists():Path(scope['revocation_path']).write_text('{}')
        return original()
    client.get_clock=clock
    with pytest.raises(ValueError,match='STANDING_REVOKED'):a.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[] and len(json.loads(a.reentry.read_text())['entry_intents'])==1


@pytest.mark.parametrize('cutoff',['expiry','window'])
def test_slow_final_authority_check_cannot_cross_entry_cutoff(setup,monkeypatch,cutoff):
    from datetime import datetime,timezone
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch)
    scope=standing(a,now);elapsed=[0.]
    monkeypatch.setattr(mod.time,'monotonic',lambda:elapsed[0])
    if cutoff=='expiry':scope['valid_until_ms']=now+1000
    else:now+=299000
    resign(a,scope);saved=ticket(setup)
    io.get_clock=lambda:dict(is_open=True,timestamp=datetime.fromtimestamp(
        (now+int(elapsed[0]*1000))/1000,timezone.utc).isoformat())
    original=a._entry_authority
    def delayed(*args,**kw):
        result=original(*args,**kw)
        if kw.get('reserved'):elapsed[0]+=2.
        return result
    a._entry_authority=delayed
    with pytest.raises(ValueError,match='STANDING_NOT_CURRENT|FINAL_DISPATCH'):
        a.enter(saved,now_ms=now,apply=True)
    assert writes==[] and a.reentry.exists()


@pytest.mark.parametrize('marker',['directory','dangling_symlink'])
def test_any_revocation_marker_blocks_buy_without_disabling_maintenance(setup,monkeypatch,marker):
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(a,now)
    a.enter(ticket(setup),now_ms=now,apply=True)
    p=Path(scope['revocation_path'])
    if marker=='directory':p.mkdir()
    else:p.symlink_to(p.parent/'missing-marker-target')
    assert a.maintain(now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    with pytest.raises(ValueError,match='STANDING_REVOKED'):a._standing_entry_state(scope,now)
    assert len(writes)==2


def test_dispatcher_recovers_rotation_crash_before_maintenance(setup,tmp_path,monkeypatch):
    from test_alpaca_monthly_cycle_custody_v1 import wired
    from test_alpaca_monthly_native_binding_v1 import ms,bookmod
    m,n,s,io,now=wired(setup,tmp_path);n.enter(ticket(setup),now_ms=now,apply=True)
    monkeypatch.setattr(bookmod,'prepare_intended_report',lambda *a,**k:dict(
        picks=[dict(symbol='NEW',atr20=2.,signal_close=100.,weight=.6)],gate_ok=True,reason='ok'))
    calendar=s['calendar']+[dict(session=d,open_ms=ms(d+'T14:30:00'),close_ms=ms(d+'T21:00:00'))
        for d in ('2026-11-30','2026-12-01')]
    selection=n.book.seal_selection({},calendar,signal_session='2026-11-30',entry_session='2026-12-01',
        source_available_ms=ms('2026-11-30T21:00:01'),source_sha256='b'*64,now_ms=ms('2026-11-30T21:00:02'))
    now=ms('2026-12-01T14:30:01');io.get_clock=lambda:dict(is_open=True,timestamp='2026-12-01T14:30:01Z')
    io.cancel_order=lambda oid:io.orders[oid].update(status='canceled')
    def sell(symbol,qty,*,client_order_id):
        io.sent.append('sell');io.positions=[]
        order=dict(id='exit',client_order_id=client_order_id,symbol=symbol,side='sell',type='market',
            status='filled',qty=str(qty),filled_qty=str(qty),filled_avg_price='320',filled_at='2026-12-01T14:30:01Z')
        io.orders['exit']=order;return copy.deepcopy(order)
    io.submit_market_sell_qty=sell;record=n.book.record_exit
    n.book.record_exit=lambda *a,**k:(_ for _ in ()).throw(OSError('rotation book commit lost'))
    with pytest.raises(OSError):n.rotate(selection['selection_id'],now_ms=now,apply=True)
    n.book.record_exit=record;maintain=n.maintain
    def protected(**kw):
        assert not m.book.rows('positions'), 'rotation receipt must retire book before maintenance'
        return maintain(**kw)
    n.maintain=protected
    out=m.tick(n,now_ms=now,apply=True)
    assert not any(i['phase'] in {'RECOVERY','MAINTENANCE'} for i in out['issues'])
    assert not m.book.rows('positions') and len(m.book.rows('exits'))==1
    assert io.sent==['buy','stop','sell']


def test_multisymbol_opening_refreshes_elapsed_time_between_real_native_entries(setup,tmp_path,monkeypatch):
    from test_alpaca_monthly_native_binding_v1 import bookmod,ms
    from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager
    from scripts.rehearse_alpaca_monthly_cycle_v1 import MemoryBroker,standing_mode
    picks=[dict(symbol=symbol,atr20=2.,signal_close=100.,weight=.25) for symbol in ('NET','AMD','AAPL','MSFT')]
    report=lambda *a,**k:dict(picks=picks,gate_ok=True,reason='ok')
    monkeypatch.setattr(bookmod,'prepare_intended_report',report)
    monkeypatch.setattr(mod.baseline,'prepare_intended_report',report)
    b,s,a,io,now=setup
    m=MonthlyManager(tmp_path/'four-cycle',account_id='fixture',capital='487.42',
        account_lock_path=a.lock_path,entry_halt_path=a.halt)
    (m.root/'book').mkdir();bookmod.MonthlyBook(m.root/'book/monthly-orders-off.sqlite',bookmod.CONTRACT)
    later=m.book.seal_selection({},s['calendar'],signal_session='2026-10-30',entry_session='2026-11-02',
        source_available_ms=ms('2026-10-30T21:01:00'),source_sha256='b'*64,now_ms=ms('2026-10-30T21:02:00'))
    elapsed=[0.];monkeypatch.setattr(mod.time,'monotonic',lambda:elapsed[0])
    broker=MemoryBroker(tmp_path/'broker.json',s['calendar'],standing=True);broker.set_clock(now)
    get_account=broker.get_account
    # Fixed fixture equity isolates elapsed-time admission from fee/MTM sizing.
    broker.get_account=lambda:{**get_account(),'id':'fixture','equity':'487.42'}
    # This is an explicit fixture selector, testing native dispatch timing only.
    with standing_mode(tmp_path,m,now) as authority:
        n=m.native(broker,base_url=broker.base_url,**authority)
        scope=json.loads(Path(n.live_scope_path).read_bytes());scope['max_new_entries_per_session']=4;resign(n,scope)
        original=n.enter
        def delayed(*args,**kw):
            out=original(*args,**kw);elapsed[0]+=6.;return out
        n.enter=delayed
        quotes={p['symbol']:dict(ask=100.,quote_ts=now,received_ms=now,source='FIXTURE') for p in picks}
        out=m.opening(n,{},later['selection_id'],quotes=quotes,now_ms=now,apply=True)
    assert len([r for r in out['results'] if r['status']=='MONTHLY_NATIVE_PROTECTED'])==4
    assert len(broker.state['positions'])==4
    assert len([w for w in broker.state['writes'] if w['payload'].get('side')=='buy'])==4


def test_legacy_exact_scope_cannot_use_standing_go(setup,monkeypatch):
    b,s,a,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch)
    Path(a.owner_go_path).write_bytes(canonical(dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',
        scope_sha256=a.live_scope_sha256,owner_go_text='GO ALPACA_MONTHLY_STANDING '+a.live_scope_sha256)))
    with pytest.raises(ValueError,match='OWNER_GO'):a.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[]


def test_dispatcher_recovers_previous_selection_before_maintenance(setup,tmp_path):
    from test_alpaca_monthly_cycle_custody_v1 import wired
    from research_lab.alpaca_monthly_cycle_v1 import publish
    m,n,s,io,now=wired(setup,tmp_path);saved=ticket(setup)
    publish(m.root/'tickets'/(saved['client_order_id']+'.json'),saved)
    io.lose_once=True
    with pytest.raises(OSError):n.enter(saved,now_ms=now,apply=True)
    assert not m.book.rows('positions') and io.sent==['buy']
    from test_alpaca_monthly_native_binding_v1 import ms
    later=[dict(session=d,open_ms=ms(d+'T14:30:00'),close_ms=ms(d+'T21:00:00'))
           for d in ('2026-11-30','2026-12-01')]
    m.book.seal_selection({},later,signal_session='2026-11-30',entry_session='2026-12-01',
        source_available_ms=ms('2026-11-30T21:01:00'),source_sha256='b'*64,
        now_ms=ms('2026-11-30T21:02:00'))
    now=ms('2026-12-01T14:30:00')
    io.get_clock=lambda:dict(is_open=True,timestamp='2026-12-01T14:30:00Z')
    old=n.maintain
    def protect(**kw):
        assert m.book.rows('positions'), 'old accepted buy must bind before maintenance'
        io.positions[0]['current_price']='311.222'
        io.orders['stop']['submitted_at']='2026-12-01T14:30:00Z'
        return old(**kw)
    n.maintain=protect
    out=m.tick(n,now_ms=now+1000,apply=True)
    assert out['recovered'] and len(m.book.rows('positions'))==1
    assert io.sent==['buy','stop']
    m.tick(n,now_ms=now+2000,apply=True)
    assert io.sent==['buy','stop']


def test_dispatcher_source_failure_still_maintains_owned_protection(setup,tmp_path):
    from test_alpaca_monthly_cycle_custody_v1 import wired
    m,n,s,io,now=wired(setup,tmp_path);n.enter(ticket(setup),now_ms=now,apply=True)
    io.positions[0]['current_price']='311.222'
    io.orders['stop']['submitted_at']='2026-11-02T14:30:00Z'
    def missing():raise ValueError('SOURCE_OFFLINE_FIXTURE')
    out=m.tick(n,now_ms=now,source_loader=missing,apply=True)
    assert out['maintenance']['status']=='MONTHLY_NATIVE_PROTECTED'
    assert out['entry_status']=='BLOCKED' and io.sent==['buy','stop']


def test_dispatcher_never_submits_a_saved_ticket_without_reservation(setup,tmp_path):
    from test_alpaca_monthly_cycle_custody_v1 import wired
    from research_lab.alpaca_monthly_cycle_v1 import publish
    m,n,s,io,now=wired(setup,tmp_path);saved=ticket(setup)
    publish(m.root/'tickets'/(saved['client_order_id']+'.json'),saved)
    out=m.tick(n,now_ms=now,apply=True)
    assert out['recovered']==[] and not io.sent and not n.reentry.exists()


def test_lifecycle_notifications_reuse_monitor_and_do_not_repeat(setup,tmp_path):
    from research_lab.alpaca_monthly_notifications_v1 import cycle_delivery
    b,s,n,io,now=setup;n.enter(ticket(setup),now_ms=now,apply=True)
    events=[];config=dict(output_root=str(tmp_path/'alerts'))
    send=lambda event:events.append(event) or dict(delivered=True)
    cycle_delivery(config,n,now_ms=now,sender=send)
    cycle_delivery(config,n,now_ms=now+1000,sender=send)
    assert [e['kind'] for e in events]==['MONTHLY_ENTRY']
    assert events[0]['entry_order_id']=='entry'
    assert events[0]['financial_source']=='EXISTING_OWNED_MONTHLY_BOOK'


@pytest.mark.parametrize('realized,mark,blocked',[('0','80',True),('40','80',True),
    ('40.01','80',False),('-20','100',True),('0','100',False)])
def test_standing_loss_trigger_uses_final_net_and_current_owned_marks(realized,mark,blocked):
    scope=dict(max_cumulative_net_loss_usd='20')
    positions=[dict(qty='3',avg_entry_price='100',current_price=mark)]
    if blocked:
        with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):
            mod.MonthlyNativeBinding._check_standing_loss(scope,mod.dec(realized),positions)
    else:mod.MonthlyNativeBinding._check_standing_loss(scope,mod.dec(realized),positions)
