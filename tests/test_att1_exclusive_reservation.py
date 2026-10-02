"""Durable preparation ledger only; no production dispatch or broker sends."""
import sqlite3
import subprocess
import sys
import ast
from copy import deepcopy
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

import pytest

from bot import att1_coordinator_adapter as a


def canary_reservation_api():
    assert hasattr(a, 'reserve_new_att1_preparation'), 'cash-aware reservation missing'
    return a.reserve_new_att1_preparation


def canary_budget(*, now):
    from test_att1_canary_budget import inputs, api
    from test_att1_lifecycle_coordinator import fixture
    from research_lab.att1_lifecycle_profile import bind_broker_replay_profile
    b, old, cash = inputs()
    b['account_fingerprint_sha256'] = old['account_fingerprint_sha256'] = cash['account_fingerprint_sha256'] = a.att1_broker_account_fingerprint(ACCOUNT)
    b['observed_ms'] = old['observed_ms'] = now - 20
    cash['observed_ms'] = cash['coverage_end_ms'] = now
    cash['coverage_start_ms'] = now // 86400000 * 86400000
    base, intent = fixture()
    profile = bind_broker_replay_profile(base, b)
    intent['signal']['bar_close_ms'] = now // H1 * H1
    intent['signal']['source_available_ms'] = now - 30
    intent['signal']['signal_ready_ms'] = now - 20
    intent['instrument']['observed_ms'] = now - 20
    intent['submit_ms'] = now
    intent['book'] = 'ATT1_BROKER_REPLAY:' + b['account_fingerprint_sha256']
    v = api().validate_canary_budget_inputs(b, old, cash, now_ms=now)
    from test_att1_canary_preparation import handoff_inputs
    v = api().bind_canary_handoff(v, **handoff_inputs(now))
    assert hasattr(api(), 'bind_canary_command_budget'), 'admitted command binding missing'
    link = a._stable_link_id(ACCOUNT, 'BTCUSDT', 'SELL', intent['signal']['bar_close_ms'])
    return api().bind_canary_command_budget(v, profile, intent, order_link_id=link)


def new_cash_reserve(con, *, now, budget=None, **changes):
    args = dict(symbol='BTCUSDT', side='Sell', h1_close_ms=now // H1 * H1,
                now_ms=now, validated_budget=budget or canary_budget(now=now),
                proposed_risk_usdt='0.44', proposed_cost_reserve_usdt='0.0176')
    args.update(changes)
    return canary_reservation_api()(con, ACCOUNT, **args)


def ready_for_canary(con):
    a.pause_att1_route(con, ACCOUNT, T + 10)
    a.prepare_att1_cutover(con, ACCOUNT, cutover_ms=T + H1, last_old_h1_ms=T,
                          drained_at_ms=T + 20, broker_truth_sha256='a'*64, now_ms=T + 21)


def test_budget_and_slot_checked_in_one_transaction(ledger):
    canary_reservation_api()
    con, _ = ledger
    ready_for_canary(con)
    row = new_cash_reserve(con, now=T+H1+40)
    assert row['orders_allowed'] is False
    assert con.execute('SELECT risk_reserve_usdt,cost_reserve_usdt FROM att1_decisions').fetchone() == ('0.44', '0.0176')
    assert con.execute('PRAGMA synchronous').fetchone()[0] == 2
    with pytest.raises(a.AdapterViolation):
        new_cash_reserve(con, now=T+H1+40)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0] == 1


def test_missing_reserve_migration_blocks_new(ledger):
    canary_reservation_api()
    con, _ = ledger
    ready_for_canary(con)
    # A legacy unresolved row must never be priced as zero exposure.
    a.reserve_att1_decision(con, ACCOUNT, owner='NEW', symbol='ETHUSDT', side='Sell', h1_close_ms=T+H1, now_ms=T+H1+1)
    with pytest.raises(a.AdapterViolation):
        new_cash_reserve(con, now=T+H1+40)
    assert con.execute('SELECT terminal_at_ms FROM att1_decisions').fetchone()[0] is None


@pytest.mark.parametrize('field,value', [('proposed_risk_usdt','0.4'), ('proposed_cost_reserve_usdt','0'), ('symbol','ETHUSDT')])
def test_reserve_matches_admitted_command_and_binding(ledger, field, value):
    canary_reservation_api()
    con, _ = ledger
    ready_for_canary(con)
    with pytest.raises(a.AdapterViolation, match='command|reserve'):
        new_cash_reserve(con, now=T+H1+40, **{field:value})
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0] == 0


def test_bound_finality_cannot_bypass_spend_transfer(ledger):
    canary_reservation_api()
    con, _ = ledger
    ready_for_canary(con)
    row = new_cash_reserve(con, now=T+H1+40)
    key=(ACCOUNT,'ATT1','BTCUSDT','Sell',T+H1)
    with pytest.raises(a.AdapterViolation, match='budget|cash'):
        a.finalize_att1_reservation(con,ACCOUNT,key,flat=True,order_final=True,costs_complete=True,now_ms=T+H1+100)
    assert con.execute('SELECT terminal_at_ms FROM att1_decisions').fetchone()[0] is None


def test_release_crash_then_stale_cash_retry_blocks(ledger,tmp_path):
    canary_reservation_api()
    from test_att1_canary_budget import cash_event, api
    con,path=ledger
    ready_for_canary(con)
    budget=canary_budget(now=T+H1+40)
    new_cash_reserve(con,now=T+H1+40,budget=budget)
    key=(ACCOUNT,'ATT1','BTCUSDT','Sell',T+H1)
    base=deepcopy(budget)
    base.pop('command_binding')
    cash=base['cash_evidence'];cash['observed_ms']=cash['coverage_end_ms']=T+H1+100
    cash['events']=[cash_event(account_fingerprint_sha256=a.att1_broker_account_fingerprint(ACCOUNT), owner='NEW',economic_ms=T+H1+90,received_ms=T+H1+100,command_sha256=budget['command_binding']['command_sha256'])]
    session=_toy_cash_terminal(tmp_path,budget)
    cash['events'][0]['lifecycle_sources']=[{'event_id':e['event_id'],'source_sha256':e['source_sha256']} for e in session.journal.read() if e['kind'] in {'ENTRY_FILL','EXIT_FILL','FUNDING_CASH'}]
    terminal=api().validate_canary_budget_inputs(base['binding'],base['old_budget_evidence'],cash,now_ms=T+H1+100)
    a.finalize_att1_reservation(con,ACCOUNT,key,flat=True,order_final=True,costs_complete=True,now_ms=T+H1+100,validated_budget=terminal,lifecycle_session=session)
    con.close()
    with sqlite3.connect(path) as restored:
        assert restored.execute('SELECT spent_debits_usdt FROM att1_route').fetchone()[0]=='0.3'
        assert restored.execute('SELECT terminal_at_ms FROM att1_decisions').fetchone()[0]==T+H1+100
        with pytest.raises(a.AdapterViolation, match='frontier|coverage|clock'):
            new_cash_reserve(restored,now=T+2*H1+40)
    # Restore the fixture-owned connection so its finalizer remains safe.
    # sqlite.Connection.close is idempotent; the original fixture may close twice.


def test_two_connections_cannot_spend_same_budget(ledger):
    canary_reservation_api()
    con,path=ledger
    ready_for_canary(con)
    budget=canary_budget(now=T+H1+40)
    barrier=Barrier(2)
    def attempt():
        with sqlite3.connect(path,timeout=10) as other:
            barrier.wait()
            try:
                return new_cash_reserve(other,now=T+H1+40,budget=budget)['orders_allowed']
            except a.AdapterViolation:
                return 'BLOCKED'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:attempt(),range(2)))
    assert results.count(False)==1 and results.count('BLOCKED')==1
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==1


def test_restart_and_route_switch_do_not_refill(ledger):
    canary_reservation_api()
    con,path=ledger
    ready_for_canary(con)
    new_cash_reserve(con,now=T+H1+40)
    with sqlite3.connect(path) as reopened:
        with pytest.raises(a.AdapterViolation):
            a.pause_att1_route(reopened,ACCOUNT,T+H1+50)
        with pytest.raises(a.AdapterViolation):
            new_cash_reserve(reopened,now=T+H1+40)
        assert reopened.execute('SELECT terminal_at_ms FROM att1_decisions').fetchone()[0] is None


def test_unknown_order_and_late_old_fill_keep_handoff_draining(ledger):
    canary_reservation_api()
    con,_=ledger
    key=reserve(con)
    a.pause_att1_route(con,ACCOUNT,T+5)
    a.bind_att1_order(con,ACCOUNT,key,'late-old-fill')
    with pytest.raises(a.AdapterViolation,match='occupied'):
        cutover(con)
    assert a.read_att1_route(con,ACCOUNT)['owner']=='OLD_PAUSED'


def test_pre_c_signal_and_old_cooldown_are_preserved(ledger):
    canary_reservation_api()
    con,_=ledger
    key=reserve(con,symbol='BTCUSDT')
    finish(con,key)
    ready_for_canary(con)
    with pytest.raises(a.AdapterViolation,match='cooldown'):
        new_cash_reserve(con,now=T+H1+40)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==1


@pytest.mark.parametrize('defect',[None,'zero_cash','missing_source','wrong_source','past_day_completion'])
def test_budget_finality_threads_through_existing_lifecycle_reconciliation(ledger,tmp_path,defect):
    canary_reservation_api()
    from test_att1_canary_budget import api,cash_event
    from research_lab.att1_lifecycle_session import LifecycleSession
    con,path=ledger;ready_for_canary(con);now=T+H1+40
    budget=canary_budget(now=now);row=new_cash_reserve(con,now=now,budget=budget)
    attach=budget['command_binding'];s=LifecycleSession(tmp_path/'cash-aware.jsonl',attach['profile'],intent=attach['intent'])
    def event(kind,offset,**fields):
        return {'schema_id':'att1_lifecycle_event_v1','event_id':kind+str(offset),'kind':kind,
                'exchange_ms':now+offset,'received_ms':now+offset+1,'source_sha256':'a'*64,**fields}
    events=[event('ENTRY_ACK',1),event('ENTRY_FILL',2,execution_id='entry-cash',qty='0.04',price='100',fee_amount='0.004',fee_source_sha256='a'*64,liquidity='TAKER'),
            event('PROTECTION_ACK',3,qty='0.04',stop='110'),event('ENTRY_FINAL',4,status='FILLED'),event('PRICE',10,bid='111',ask='112')]
    for e in events:s.apply(e)
    xid=s.receipt['pending_exit']['exit_order_id']
    terminal_events=[event('EXIT_ACK',11,exit_order_id=xid),event('EXIT_FILL',12,exit_order_id=xid,execution_id='exit-cash',qty='0.04',price='112',fee_amount='0.00448',fee_source_sha256='a'*64,liquidity='TAKER'),
        event('EXIT_FINAL',13,exit_order_id=xid,status='FILLED'),event('FUNDING_COVERAGE',20,start_ms=now,end_ms=now+20,settlement_ms=[],complete=True)]
    cash=deepcopy(budget['cash_evidence']);cash['observed_ms']=cash['coverage_end_ms']=now+30
    cash['events']=[cash_event(account_fingerprint_sha256=a.att1_broker_account_fingerprint(ACCOUNT),owner='NEW',economic_ms=now+12,received_ms=now+30,
                              gross_realized_usdt='-0.48',execution_fee_usdt='0.00848',command_sha256=attach['command_sha256'],
                              lifecycle_sources=[{'event_id':e['event_id'],'source_sha256':e['source_sha256']} for e in [*events,*terminal_events] if e['kind'] in {'ENTRY_FILL','EXIT_FILL','FUNDING_CASH'}])]
    if defect=='zero_cash':cash['events'][0].update(gross_realized_usdt='0',execution_fee_usdt='0')
    if defect=='missing_source':cash['events'][0]['lifecycle_sources']=[]
    if defect=='wrong_source':cash['events'][0]['lifecycle_sources'][0]['source_sha256']='f'*64
    final_now=now+30
    binding,old=budget['binding'],budget['old_budget_evidence']
    if defect=='past_day_completion':
        final_now=now+86400000+30
        fresh=canary_budget(now=final_now);binding,old=fresh['binding'],fresh['old_budget_evidence']
        cash['prior_command_events']=cash['events'];cash['events']=[]
        cash['prior_day_coverage_sha256']=budget['cash_coverage_sha256']
        cash['coverage_start_ms']=final_now//86400000*86400000
        cash['observed_ms']=cash['coverage_end_ms']=final_now
    v=api().validate_canary_budget_inputs(binding,old,cash,now_ms=final_now)
    if defect in {'zero_cash','missing_source','wrong_source'}:
        with pytest.raises(a.AdapterViolation,match='terminal|lifecycle'):
            a.reconcile_new_att1_lifecycle_receipts(path,row,session=s,broker_order_id='entry-fixture',events=terminal_events,now_ms=now+30,validated_budget=v)
        assert con.execute('SELECT terminal_at_ms FROM att1_decisions').fetchone()[0] is None
        assert con.execute('SELECT spent_debits_usdt FROM att1_route').fetchone()[0]=='0'
        return
    result=a.reconcile_new_att1_lifecycle_receipts(path,row,session=s,broker_order_id='entry-fixture',events=terminal_events,now_ms=final_now,validated_budget=v)
    assert result['lifecycle_terminal'] is True
    assert con.execute('SELECT spent_debits_usdt FROM att1_route').fetchone()[0]==('0' if defect=='past_day_completion' else '0.48848')
    assert con.execute('SELECT terminal_at_ms FROM att1_decisions').fetchone()[0]==final_now

H1 = 3_600_000
T = 500_000 * H1
ACCOUNT = 'fixture-account'
ACCOUNT_CONFIG = {
    'name': 'main',
    'key': 'fixture-api-key',
    'base': 'https://api.bybit.com',
}


def old_broker_identity(config=ACCOUNT_CONFIG, *, received_ms=T):
    return a.validate_old_att1_broker_identity(
        config,
        {'retCode': 0, 'time': received_ms,
         'result': {'apiKey': config['key'], 'userID': '123456789'}},
        received_ms=received_ms,
    )


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / 'trades.db'
    con = sqlite3.connect(path)
    a.initialize_att1_route(con, ACCOUNT, now_ms=T)
    yield con, path
    con.close()


def reserve(con, **overrides):
    args = dict(owner='OLD', symbol='ETHUSDT', side='Sell', h1_close_ms=T, now_ms=T + 1)
    args.update(overrides)
    return a.reserve_att1_decision(con, ACCOUNT, **args)


def finish(con, key, **overrides):
    args = dict(flat=True, order_final=True, costs_complete=True, now_ms=T + 10)
    args.update(overrides)
    return a.finalize_att1_reservation(con, ACCOUNT, key, **args)


def cutover(con, **overrides):
    args = dict(cutover_ms=T + H1, last_old_h1_ms=T,
                drained_at_ms=T + 20, broker_truth_sha256='a' * 64, now_ms=T + 21)
    args.update(overrides)
    return a.prepare_att1_cutover(con, ACCOUNT, **args)


def test_initialization_preserves_existing_route_and_full_sync(ledger):
    con, _ = ledger
    assert a.read_att1_route(con, ACCOUNT)['owner'] == 'OLD'
    a.pause_att1_route(con, ACCOUNT, T + 10)
    a.initialize_att1_route(con, ACCOUNT, now_ms=T + 11)
    assert a.read_att1_route(con, ACCOUNT)['owner'] == 'OLD_PAUSED'
    assert con.execute('PRAGMA synchronous').fetchone()[0] == 2
    assert a.SEND_ENABLED is False


def test_missing_or_corrupt_route_denies_reservation(ledger):
    con, _ = ledger
    con.execute('DELETE FROM att1_route')
    con.commit()
    with pytest.raises(a.AdapterViolation, match='missing'):
        reserve(con)
    a.initialize_att1_route(con, ACCOUNT, now_ms=T)
    con.execute("UPDATE att1_route SET owner='INVALID'")
    con.commit()
    with pytest.raises(a.AdapterViolation, match='malformed'):
        reserve(con)


def test_does_not_commit_caller_transaction(ledger):
    con, _ = ledger
    con.execute('CREATE TABLE unrelated (n INTEGER)')
    con.execute('INSERT INTO unrelated VALUES (1)')
    with pytest.raises(a.AdapterViolation, match='transaction'):
        a.initialize_att1_route(con, ACCOUNT, now_ms=T + 1)
    assert con.in_transaction
    con.rollback()
    assert con.execute('SELECT * FROM unrelated').fetchall() == []


def test_unknown_send_survives_reopen_and_never_ttl_releases(ledger):
    con, path = ledger
    key = reserve(con)
    con.close()  # Simulated crash after committed intent, before possible ACK.
    with sqlite3.connect(path) as restored:
        assert restored.execute('SELECT order_link_id FROM att1_decisions').fetchone()[0] == key['order_link_id']
        with pytest.raises(a.AdapterViolation, match='occupied'):
            reserve(restored, symbol='BTCUSDT', h1_close_ms=T + 100 * H1, now_ms=T + 100 * H1 + 1)
        a.pause_att1_route(restored, ACCOUNT, T + 100 * H1 + 2)
        with pytest.raises(a.AdapterViolation, match='occupied'):
            cutover(restored, cutover_ms=T + 101 * H1, drained_at_ms=T + 100 * H1 + 3, now_ms=T + 100 * H1 + 4)
        # A late ACK must remain bindable after pause; pause is not order finality.
        assert a.bind_att1_order(restored, ACCOUNT, key, 'late-order') == 'late-order'


@pytest.mark.parametrize('flag', ['flat', 'order_final', 'costs_complete'])
def test_incomplete_finality_retains_slot(ledger, flag):
    con, _ = ledger
    key = reserve(con)
    with pytest.raises(a.AdapterViolation, match='remains occupied'):
        finish(con, key, **{flag: False})
    with pytest.raises(a.AdapterViolation, match='occupied'):
        reserve(con, symbol='BTCUSDT')


def test_terminal_decision_and_cooldown_survive_old_new_handoff(ledger):
    con, path = ledger
    key = reserve(con)
    a.bind_att1_order(con, ACCOUNT, key, 'order-1')
    finish(con, key)
    a.pause_att1_route(con, ACCOUNT, T + 11)
    route = cutover(con)
    assert route['owner'] == 'NEW_READY'  # Inert preparation, no send authorization.
    con.close()
    with sqlite3.connect(path) as restored:
        with pytest.raises(a.AdapterViolation, match='owner'):
            reserve(restored, h1_close_ms=T + 8 * H1, now_ms=T + 8 * H1 + 1)
        with pytest.raises(a.AdapterViolation, match='cutover'):
            reserve(restored, owner='NEW', now_ms=T + H1)
        with pytest.raises(a.AdapterViolation, match='cooldown'):
            reserve(restored, owner='NEW', h1_close_ms=T + H1, now_ms=T + H1 + 1)
        new = reserve(restored, owner='NEW', h1_close_ms=T + 8 * H1, now_ms=T + 8 * H1 + 1)
        assert new['order_link_id'] != key['order_link_id']
        assert restored.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0] == 2


def test_side_aliases_share_one_economic_decision_identity(ledger):
    con, _ = ledger
    key = reserve(con, side='Short')
    assert key['side'] == 'SELL'
    a.bind_att1_order(con, ACCOUNT, {**key, 'side': 'Sell'}, 'order-1')
    assert con.execute('SELECT broker_order_id FROM att1_decisions').fetchone()[0] == 'order-1'


@pytest.mark.parametrize('change', [dict(h1_close_ms=T + 1), dict(h1_close_ms=T + H1), dict(now_ms=True), dict(side='Buy')])
def test_invalid_or_future_decision_is_not_reserved(ledger, change):
    con, _ = ledger
    with pytest.raises(a.AdapterViolation):
        reserve(con, **change)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0] == 0


@pytest.mark.parametrize('change', [dict(cutover_ms=T + H1 + 1), dict(last_old_h1_ms=T - H1),
    dict(drained_at_ms=T + 100), dict(drained_at_ms=T + 1), dict(broker_truth_sha256='z' * 64)])
def test_cutover_rejects_unproven_watermark_clock_or_hash(ledger, change):
    con, _ = ledger
    key = reserve(con)
    finish(con, key)
    a.pause_att1_route(con, ACCOUNT, T + 11)
    with pytest.raises(a.AdapterViolation):
        cutover(con, **change)
    assert a.read_att1_route(con, ACCOUNT)['owner'] == 'OLD_PAUSED'


def test_conflicting_binding_and_cross_account_writes_are_rejected(ledger):
    con, _ = ledger
    key = reserve(con)
    a.bind_att1_order(con, ACCOUNT, key, 'order-1')
    assert a.bind_att1_order(con, ACCOUNT, key, 'order-1') == 'order-1'
    with pytest.raises(a.AdapterViolation, match='conflicting'):
        a.bind_att1_order(con, ACCOUNT, key, 'order-2')
    for identity in (key, tuple(key[k] for k in ('account', 'family', 'symbol', 'side', 'h1_close_ms'))):
        with pytest.raises(a.AdapterViolation, match='account'):
            a.bind_att1_order(con, 'other-account', identity, 'order-1')
        with pytest.raises(a.AdapterViolation, match='account'):
            a.finalize_att1_reservation(con, 'other-account', identity, flat=True, order_final=True, costs_complete=True, now_ms=T + 10)


def test_terminal_timestamp_cannot_precede_reservation_or_be_rewritten(ledger):
    con, _ = ledger
    key = reserve(con)
    with pytest.raises(a.AdapterViolation, match='clock'):
        finish(con, key, now_ms=T)
    finish(con, key)
    finish(con, key, now_ms=T + 99)
    assert con.execute('SELECT terminal_at_ms FROM att1_decisions').fetchone()[0] == T + 10


def test_finalized_unbound_intent_cannot_acquire_a_late_order(ledger):
    con, _ = ledger
    key = reserve(con)
    finish(con, key)
    with pytest.raises(a.AdapterViolation, match='after finality'):
        a.bind_att1_order(con, ACCOUNT, key, 'unexpected-late-order')


def test_pause_is_idempotent_and_has_no_old_resume(ledger):
    con, _ = ledger
    a.pause_att1_route(con, ACCOUNT, T + 10)
    a.pause_att1_route(con, ACCOUNT, T + 11)
    assert a.read_att1_route(con, ACCOUNT)['paused_at_ms'] == T + 10
    cutover(con)
    with pytest.raises(a.AdapterViolation, match='cannot resume'):
        a.pause_att1_route(con, ACCOUNT, T + 22)
    a.initialize_att1_route(con, ACCOUNT, now_ms=T + 23)
    assert a.read_att1_route(con, ACCOUNT)['owner'] == 'NEW_READY'


def test_competing_database_connections_cannot_own_two_symbols(ledger):
    con, path = ledger
    gate = Barrier(2)
    def attempt(symbol):
        with sqlite3.connect(path, timeout=5) as worker:
            gate.wait(timeout=5)
            try:
                reserve(worker, symbol=symbol)
                return 'reserved'
            except a.AdapterViolation:
                return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ['ETHUSDT', 'BTCUSDT'])) == ['denied', 'reserved']
    assert con.execute('SELECT COUNT(*) FROM att1_decisions WHERE terminal_at_ms IS NULL').fetchone()[0] == 1


def test_abrupt_process_exit_retains_committed_pre_send_reservation(ledger):
    _, path = ledger
    code = 'import sys; sys.path[:] = ' + repr(sys.path) + '\n' + '''
import importlib.util, os, sqlite3
spec = importlib.util.spec_from_file_location('routing_crash_fixture', sys.argv[2])
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)
con = sqlite3.connect(sys.argv[1])
t = 500_000 * 3_600_000
a.reserve_att1_decision(con, 'fixture-account', owner='OLD', symbol='ETHUSDT',
                        side='Sell', h1_close_ms=t, now_ms=t + 1)
os._exit(73)  # No close/cleanup; process dies before any ACK binding.
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), a.__file__],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 73, result.stderr
    with sqlite3.connect(path) as restored:
        with pytest.raises(a.AdapterViolation, match='occupied'):
            reserve(restored, symbol='BTCUSDT')
        assert restored.execute('SELECT broker_order_id,terminal_at_ms FROM att1_decisions').fetchone() == (None, None)


def test_route_checks_are_inside_the_sqlite_write_transaction(ledger):
    con, _ = ledger
    checks = []
    con.set_trace_callback(lambda sql: checks.append(con.in_transaction) if sql.lstrip().upper().startswith('SELECT') else None)
    key = reserve(con)
    a.bind_att1_order(con, ACCOUNT, key, 'order-1')
    finish(con, key)
    a.pause_att1_route(con, ACCOUNT, T + 11)
    cutover(con)
    assert checks and all(checks)


def test_default_off_old_dispatch_does_not_create_or_mutate_ledger(tmp_path):
    """A disabled production binding must not touch the existing trade DB."""
    path = tmp_path / 'trades.db'
    reservation = a.reserve_old_att1_dispatch(
        path,
        ACCOUNT_CONFIG,
        symbol='ETHUSDT',
        side='Sell',
        consumed_h1_rows=[[T - H1, '1', '1', '1', '1', '1']],
        now_ms=T + 1,
        enabled=False,
    )
    assert reservation is None
    assert not path.exists()


def test_monolith_att1_binding_gate_is_default_off_and_precedes_submit():
    """A future edit cannot accidentally put a ledger send gate behind send."""
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'smart_pump_reversal_bot.py').read_text())
    gate = next(
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'ATT1_COORDINATOR_BINDING_ENABLE'
                for target in node.targets)
    )
    assert isinstance(gate, ast.Call)
    assert isinstance(gate.func, ast.Name) and gate.func.id == '_env_bool'
    assert isinstance(gate.args[1], ast.Constant) and gate.args[1].value is False
    caller = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'try_att1_entry_async'
    )
    reserve_line = min(
        node.lineno for node in ast.walk(caller)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == '_att1_reserve_old_dispatch'
    )
    submit_line = min(
        node.lineno for node in ast.walk(caller)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == '_submit_entry_order_guarded'
    )
    assert reserve_line < submit_line


def test_monolith_keeps_adapter_lazy_and_starts_lookup_without_finalizing():
    """Default OLD import stays free of research binding; recovery is ACK-only."""
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'smart_pump_reversal_bot.py').read_text())
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == 'bot'
        and any(alias.name == 'att1_coordinator_adapter' for alias in node.names)
        for node in tree.body
    )
    helpers = {
        node.name: node for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    reserve = helpers['_att1_reserve_old_dispatch']
    recovery = helpers['_att1_recover_unknown_old_dispatches']
    reserve_import = min(
        node.lineno for node in ast.walk(reserve)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == 'att1_coordinator_adapter' for alias in node.names)
    )
    disabled_return = min(
        node.lineno for node in reserve.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == 'ATT1_COORDINATOR_BINDING_ENABLE'
    )
    assert disabled_return < reserve_import
    names = [
        node.func.attr for node in ast.walk(recovery)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert 'get_order_by_link_id' in names
    assert 'bind_old_att1_dispatch_ack' in names
    assert 'finalize_att1_reservation' not in names
    submit_calls = [
        node for node in ast.walk(helpers['_submit_entry_order_guarded'])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'place_market'
    ]
    assert any(not any(keyword.arg == 'order_link_id' for keyword in node.keywords)
               for node in submit_calls)
    assert any(any(keyword.arg == 'order_link_id' for keyword in node.keywords)
               for node in submit_calls)


def test_old_dispatch_uses_selected_account_config_and_frozen_closed_h1(tmp_path):
    """A changed credential or consumed bar must change/refuse the durable intent."""
    path = tmp_path / 'trades.db'
    reservation = a.reserve_old_att1_dispatch(
        path,
        ACCOUNT_CONFIG,
        symbol='ETHUSDT',
        side='Sell',
        consumed_h1_rows=[[T - 2 * H1, '1', '1', '1', '1', '1'],
                          [T - H1, '1', '1', '1', '1', '1']],
        now_ms=T + 1,
        enabled=True,
        broker_identity=old_broker_identity(),
    )
    assert reservation['account'] == old_broker_identity().account
    assert reservation['h1_close_ms'] == T
    with sqlite3.connect(path) as con:
        assert a.read_att1_route(con, reservation['account'])['owner'] == 'OLD'
        assert con.execute('SELECT order_link_id, broker_order_id FROM att1_decisions').fetchone() == (
            reservation['order_link_id'], None,
        )


def test_old_dispatch_crash_before_ack_and_duplicate_late_ack_keep_one_slot(tmp_path):
    """No process exit, late ACK, or ACK re-delivery may free or fork an ATT1 intent."""
    path = tmp_path / 'trades.db'
    code = 'import sys; sys.path[:] = ' + repr(sys.path) + '\n' + '''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location('routing_crash_fixture', sys.argv[2])
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)
t = 500_000 * 3_600_000
a.reserve_old_att1_dispatch(sys.argv[1], {'name':'main','key':'fixture-api-key','base':'https://api.bybit.com'},
                            symbol='ETHUSDT', side='Sell',
                            consumed_h1_rows=[[t-3_600_000, '1', '1', '1', '1', '1']],
                            now_ms=t+1, enabled=True,
                            broker_identity=a.validate_old_att1_broker_identity(
                                {'name':'main','key':'fixture-api-key','base':'https://api.bybit.com'},
                                {'retCode':0, 'time':t,
                                 'result':{'apiKey':'fixture-api-key','userID':'123456789'}},
                                received_ms=t))
os._exit(73)
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), a.__file__],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 73, result.stderr
    with pytest.raises(a.AdapterViolation, match='occupied'):
        a.reserve_old_att1_dispatch(
            path, ACCOUNT_CONFIG, symbol='BTCUSDT', side='Sell',
            consumed_h1_rows=[[T, '1', '1', '1', '1', '1']],
            now_ms=T + H1 + 1, enabled=True,
            broker_identity=old_broker_identity(received_ms=T + H1),
        )
    with sqlite3.connect(path) as con:
        key = dict(zip(('account', 'family', 'symbol', 'side', 'h1_close_ms'), con.execute(
            'SELECT account, family, symbol, side, h1_close_ms FROM att1_decisions'
        ).fetchone()))
    assert a.bind_old_att1_dispatch_ack(path, key, 'late-order') == 'late-order'
    assert a.bind_old_att1_dispatch_ack(path, key, 'late-order') == 'late-order'
    with sqlite3.connect(path) as con:
        assert con.execute('SELECT broker_order_id, terminal_at_ms FROM att1_decisions').fetchone() == ('late-order', None)


def test_unknown_old_dispatch_lookup_is_read_only_and_refuses_foreign_ack(tmp_path):
    """A restart probe may bind only the exact reserved symbol/side/link ACK."""
    path = tmp_path / 'trades.db'
    reservation = a.reserve_old_att1_dispatch(
        path, ACCOUNT_CONFIG, symbol='ETHUSDT', side='Sell',
        consumed_h1_rows=[[T - H1, '1', '1', '1', '1', '1']],
        now_ms=T + 1, enabled=True, broker_identity=old_broker_identity(),
    )
    pending = a.read_unresolved_old_att1_dispatches(
        path, ACCOUNT_CONFIG, broker_identity=old_broker_identity(), now_ms=T + 1,
    )
    assert pending == [reservation]
    assert a.validate_old_att1_ack_lookup(
        ACCOUNT_CONFIG, reservation,
        {'symbol': 'ETHUSDT', 'side': 'Sell', 'orderLinkId': reservation['order_link_id'], 'orderId': 'ack-1'},
        broker_identity=old_broker_identity(), now_ms=T + 1,
    ) == 'ack-1'
    for bad in (
        {'symbol': 'BTCUSDT', 'side': 'Sell', 'orderLinkId': reservation['order_link_id'], 'orderId': 'ack-1'},
        {'symbol': 'ETHUSDT', 'side': 'Buy', 'orderLinkId': reservation['order_link_id'], 'orderId': 'ack-1'},
        {'symbol': 'ETHUSDT', 'side': 'Sell', 'orderLinkId': 'foreign', 'orderId': 'ack-1'},
    ):
        with pytest.raises(a.AdapterViolation):
            a.validate_old_att1_ack_lookup(
                ACCOUNT_CONFIG, reservation, bad,
                broker_identity=old_broker_identity(), now_ms=T + 1,
            )
    with sqlite3.connect(path) as con:
        assert con.execute('SELECT broker_order_id, terminal_at_ms FROM att1_decisions').fetchone() == (None, None)
    assert a.bind_old_att1_dispatch_ack(path, reservation, 'ack-1') == 'ack-1'
    assert a.read_unresolved_old_att1_dispatches(
        path, ACCOUNT_CONFIG, broker_identity=old_broker_identity(), now_ms=T + 1,
    ) == []
    with sqlite3.connect(path) as con:
        assert con.execute('SELECT broker_order_id, terminal_at_ms FROM att1_decisions').fetchone() == ('ack-1', None)


def _isolated_bybit_client():
    """Compile the production client class with only its non-I/O dependencies."""
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'smart_pump_reversal_bot.py').read_text())
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == 'BybitClient')
    namespace = {
        'DRY_RUN': False,
        'Tuple': Tuple,
        'Optional': Optional,
        'strict_round_qty': lambda _symbol, qty: qty,
        'fmt_qty': lambda _symbol, qty: str(qty),
        'fmt_amt': lambda _symbol, qty: str(qty),
        'ORDER_LINK_ID_ENABLED': True,
        'POS_IS_ONEWAY': True,
        '_make_order_link_id': lambda *_args: 'legacy-generated-link',
        '_log_order_link': lambda *_args: None,
        'MIN_NOTIONAL_USD': 5.0,
        'S': lambda *_args: None,
        '_HTTP': None,
        'log_error': lambda *_args: None,
        'tg_trade': lambda *_args: None,
        'time': __import__('time'),
        'hmac': __import__('hmac'),
        'hashlib': __import__('hashlib'),
        'json': __import__('json'),
        'urlencode': __import__('urllib.parse', fromlist=['urlencode']).urlencode,
        'AUTH_LAST_ERROR': {},
        'auth_disabled': lambda *_args: False,
        'is_timestamp_error': lambda *_args: False,
        'is_bybit_auth_error': lambda *_args: False,
        'mark_auth_fail': lambda *_args, **_kwargs: None,
        'tg_trade_throttled': lambda *_args, **_kwargs: None,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<isolated-bybit-client>', 'exec'), namespace)
    return namespace['BybitClient']


def test_market_transport_uses_reserved_link_and_keeps_legacy_payload_when_omitted():
    """Changing the optional transport link must not mutate the default OLD body."""
    client_type = _isolated_bybit_client()
    client = object.__new__(client_type)
    client.name = 'main'
    bodies = []
    client.post = lambda _path, body: bodies.append(dict(body)) or {'result': {'orderId': 'oid-1'}}

    stable = 'a1' + 'b' * 26
    client.place_market('ETHUSDT', 'Sell', 0.1, allow_quote_fallback=False, order_link_id=stable)
    assert bodies[-1]['orderLinkId'] == stable
    client.place_market('ETHUSDT', 'Sell', 0.1, allow_quote_fallback=False, order_link_id=stable)
    assert bodies[-1]['orderLinkId'] == stable

    client.place_market('ETHUSDT', 'Sell', 0.1, allow_quote_fallback=False)
    assert bodies[-1] == {
        'category': 'linear', 'symbol': 'ETHUSDT', 'side': 'Sell',
        'orderType': 'Market', 'qty': '0.1', 'timeInForce': 'IOC',
        'marketUnit': 'baseCoin', 'orderLinkId': 'legacy-generated-link',
    }

    gets = []
    client.get = lambda path, params, timeout: gets.append((path, dict(params), timeout)) or {
        'result': {'list': [{'symbol': 'ETHUSDT', 'side': 'Sell', 'orderLinkId': stable, 'orderId': 'oid-1'}]}
    }
    assert client.get_order_by_link_id('ETHUSDT', stable)['orderId'] == 'oid-1'
    assert gets == [('/v5/order/realtime', {
        'category': 'linear', 'symbol': 'ETHUSDT', 'orderLinkId': stable, 'limit': 1,
    }, 10)]


def test_cash_aware_direct_reserve_requires_complete_handoff(ledger):
    from bot.att1_canary_preparation import validate_canary_budget_inputs,bind_canary_command_budget
    con,_=ledger;ready_for_canary(con);now=T+H1+40;v=canary_budget(now=now);cmd=v['command_binding']
    bare=validate_canary_budget_inputs(v['binding'],v['old_budget_evidence'],v['cash_evidence'],now_ms=now)
    bare=bind_canary_command_budget(bare,cmd['profile'],cmd['intent'],order_link_id=cmd['command']['orderLinkId'])
    with pytest.raises(a.AdapterViolation,match='handoff'):
        new_cash_reserve(con,now=now,budget=bare)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==0


def _toy_cash_terminal(tmp_path,budget):
    from research_lab.att1_lifecycle_session import LifecycleSession
    attach=budget['command_binding'];now=budget['now_ms']
    s=LifecycleSession(tmp_path/'toy-finality.jsonl',attach['profile'],intent=attach['intent'])
    def e(kind,offset,**fields):
        return {'schema_id':'att1_lifecycle_event_v1','event_id':kind+str(offset),'kind':kind,'exchange_ms':now+offset,'received_ms':now+offset+1,'source_sha256':'a'*64,**fields}
    for event in [e('ENTRY_ACK',1),e('ENTRY_FILL',2,execution_id='entry-toy',qty='0.04',price='100',fee_amount='0.04',fee_source_sha256='a'*64,liquidity='TAKER'),e('PROTECTION_ACK',3,qty='0.04',stop='110'),e('ENTRY_FINAL',4,status='FILLED'),e('PRICE',10,bid='111',ask='112')]:s.apply(event)
    xid=s.receipt['pending_exit']['exit_order_id']
    for event in [e('EXIT_ACK',11,exit_order_id=xid),e('EXIT_FILL',50,exit_order_id=xid,execution_id='exit-toy',qty='0.04',price='105',fee_amount='0.06',fee_source_sha256='a'*64,liquidity='TAKER'),e('EXIT_FINAL',51,exit_order_id=xid,status='FILLED'),e('FUNDING_COVERAGE',55,start_ms=now,end_ms=now+55,settlement_ms=[],complete=True)]:s.apply(event)
    return s
