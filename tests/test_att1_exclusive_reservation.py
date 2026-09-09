"""Durable preparation ledger only; no production dispatch or broker sends."""
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from bot import att1_coordinator_adapter as a

H1 = 3_600_000
T = 500_000 * H1
ACCOUNT = 'fixture-account'


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
