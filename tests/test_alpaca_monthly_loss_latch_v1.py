"""The Monthly BUY latch survives recovery; it never revokes owned custody."""
import json
import os
from pathlib import Path

import pytest
from research_lab import alpaca_monthly_native_binding_v1 as mod
from test_alpaca_monthly_native_binding_v1 import setup,ticket
from test_alpaca_monthly_account_transport_v1 import connect_wire
from test_alpaca_monthly_standing_v1 import standing,resign


def test_loss_latch_survives_restart_and_new_scope_even_after_marks_recover(setup,monkeypatch):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    scope['max_cumulative_net_loss_usd']='8';resign(n,scope)
    with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):
        n._latch_standing_loss(scope,mod.dec('-8'),[],now_ms=now)
    path=n.runtime/'standing-loss-stop.json';original=path.read_bytes()
    assert json.loads(original)['account_id']==n.account
    assert json.loads(original)['book']==str(n.book.path)
    # A normal grant renewal, including a different revocation path, is not a reset.
    scope['revocation_path']=str(Path(scope['revocation_path']).with_name('renewed.json'))
    scope['valid_until_ms']+=1000;resign(n,scope)
    restarted=mod.MonthlyNativeBinding(b,client=client,base_url=n.base_url,account_id=n.account,
        capital=n.capital,runtime=n.runtime,lock_path=n.lock_path,entry_halt_path=n.halt,
        live_scope_path=n.live_scope_path,live_scope_sha256=n.live_scope_sha256,owner_go_path=n.owner_go_path)
    with pytest.raises(ValueError,match='LOSS_LATCHED'):
        restarted._latch_standing_loss(scope,mod.dec('100'),[],now_ms=now+1000)
    with pytest.raises(ValueError,match='LOSS_LATCHED'):restarted.enter(ticket(setup),now_ms=now,apply=True)
    assert path.read_bytes()==original and writes==[]


def test_latched_owner_keeps_native_protection_and_replay(setup,monkeypatch):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    saved=ticket(setup);n.enter(saved,now_ms=now,apply=True)
    with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):
        n._latch_standing_loss(scope,mod.dec('-20'),[],now_ms=now)
    assert n.maintain(now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert n.enter(saved,now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert len(writes)==2


@pytest.mark.parametrize('kind',['directory','dangling_symlink','corrupt'])
def test_unknown_latch_leaf_blocks_new_buy_without_repair(setup,monkeypatch,kind):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);standing(n,now)
    p=n.runtime/'standing-loss-stop.json';p.parent.mkdir(parents=True,exist_ok=True)
    if kind=='directory':p.mkdir()
    elif kind=='dangling_symlink':p.symlink_to(p.parent/'missing')
    else:p.write_bytes(b'{partial')
    with pytest.raises(ValueError,match='LOSS_LATCHED'):n.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[] and os.path.lexists(p)


def test_failed_durable_write_cannot_admit_new_risk(setup,monkeypatch):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    from research_lab import kity_oct15_deadline_v1 as storage
    publish=storage.publish_once
    def disk_full(path,raw):
        if Path(path).name=='standing-loss-stop.json':raise OSError('fixture_disk_full')
        return publish(path,raw)
    monkeypatch.setattr(storage,'publish_once',disk_full)
    with pytest.raises(OSError,match='fixture_disk_full'):
        n._latch_standing_loss(scope,mod.dec('-20'),[],now_ms=now)
    assert writes==[]
    with pytest.raises(ValueError,match='LOSS_LATCHED'):
        n._latch_standing_loss(scope,mod.dec('100'),[],now_ms=now+1000)
    restarted=mod.MonthlyNativeBinding(b,client=client,base_url=n.base_url,account_id=n.account,
        capital=n.capital,runtime=n.runtime,lock_path=n.lock_path,entry_halt_path=n.halt,
        live_scope_path=n.live_scope_path,live_scope_sha256=n.live_scope_sha256,owner_go_path=n.owner_go_path)
    with pytest.raises(ValueError,match='LOSS_LATCHED'):restarted.enter(ticket(setup),now_ms=now,apply=True)
    assert (n.runtime/'standing-loss-observation.json').is_file() and writes==[]


def test_observer_prearms_before_reading_marks_even_without_new_signal(setup,monkeypatch):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    saved=ticket(setup);n.enter(saved,now_ms=now,apply=True)
    account=client.get_account;positions=client.list_positions
    calls=[]
    def marked():
        calls.append(True)
        rows=positions()
        if len(calls)>1:
            assert (n.runtime/'standing-loss-observation.json').is_file()
            rows[0]['current_price']='200'
        return rows
    monkeypatch.setattr(client,'list_positions',marked)
    with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):n.observe_standing_loss(now_ms=now)
    assert (n.runtime/'standing-loss-stop.json').is_file() and len(writes)==2
    monkeypatch.setattr(client,'list_positions',positions)
    assert n.maintain(now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'


def test_known_recovery_gap_does_not_create_a_permanent_loss_marker(setup,monkeypatch):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    monkeypatch.setattr(client,'list_positions',lambda:[dict(symbol='NET',side='long',qty='1',
        avg_entry_price='100',current_price='100')])
    with pytest.raises(ValueError,match='FOREIGN_OR_UNRECONCILED_POSITION'):n.observe_standing_loss(now_ms=now)
    assert not (n.runtime/'standing-loss-observation.json').exists()
    assert not (n.runtime/'standing-loss-stop.json').exists() and writes==[]


def test_safe_observation_clears_only_its_own_checkpoint(setup,monkeypatch):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    n.observe_standing_loss(now_ms=now)
    assert not (n.runtime/'standing-loss-observation.json').exists()
    n._standing_entry_state(scope,now)
    assert writes==[]


@pytest.mark.parametrize('cash,accepted',[('208',True),('207.99',False)])
def test_owner_budget_keeps_frozen_weight_and_reserve_without_borrowing(setup,monkeypatch,cash,accepted):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    n.capital=400.;n.liability=mod.dec('40')
    scope.update(capital_usd=str(mod.dec(n.capital)),liability_reserve_usd='40',
        max_entry_notional_usd='168',max_cumulative_net_loss_usd='8')
    resign(n,scope)
    saved=ticket(setup)
    assert mod.dec(saved['notional'])==mod.dec('168')  # 400 * .70 * existing .60
    account=io.get_account
    io.get_account=lambda:dict(account(),cash=cash,non_marginable_buying_power=cash)
    if accepted:assert n._admit_new_entry(saved,now)['account']['cash']==cash
    else:
        with pytest.raises(ValueError,match='FRESH_CASH_GROSS_OR_POSITION_CAP'):n._admit_new_entry(saved,now)
    assert writes==[]
