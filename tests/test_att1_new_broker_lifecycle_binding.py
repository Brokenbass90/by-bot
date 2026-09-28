"""Offline-only NEW reservation to journal reconciliation boundary."""
from copy import deepcopy
import sqlite3

import pytest

from bot import att1_coordinator_adapter as a
from research_lab.att1_lifecycle_profile import bind_broker_replay_profile
from research_lab.att1_lifecycle_session import LifecycleSession
from test_att1_lifecycle_coordinator import fixture, ev, coverage, T


H1 = 3_600_000
ACCOUNT = 'uid:' + 'a' * 64


def _new_reservation(path):
    with sqlite3.connect(path) as con:
        a.initialize_att1_route(con, ACCOUNT, now_ms=T - 2 * H1)
        old = a.reserve_att1_decision(
            con, ACCOUNT, owner='OLD', symbol='ETHUSDT', side='Sell',
            h1_close_ms=T - H1, now_ms=T - H1 + 1,
        )
        a.finalize_att1_reservation(
            con, ACCOUNT, old, flat=True, order_final=True, costs_complete=True,
            now_ms=T - H1 + 2,
        )
        a.pause_att1_route(con, ACCOUNT, T - H1 + 3)
        a.prepare_att1_cutover(
            con, ACCOUNT, cutover_ms=T, last_old_h1_ms=T - H1,
            drained_at_ms=T - H1 + 4, broker_truth_sha256='b' * 64,
            now_ms=T - H1 + 5,
        )
        return a.reserve_att1_decision(
            con, ACCOUNT, owner='NEW', symbol='BTCUSDT', side='Sell',
            h1_close_ms=T, now_ms=T + 1,
        )


def _session(path, reservation, *, symbol='BTCUSDT', account=ACCOUNT):
    base, intent = fixture()
    intent['signal']['symbol'] = symbol
    intent['instrument']['symbol'] = symbol
    fingerprint = a.att1_broker_account_fingerprint(account)
    profile = bind_broker_replay_profile(base, {
        'base_profile_sha256': base['profile_sha256'],
        'account_fingerprint_sha256': fingerprint,
        'broker_truth_sha256': 'c' * 64,
        'account_mode': 'UNIFIED_ONE_WAY_USDT', 'observed_ms': T + 20,
        'absolute_risk_cap': '0.55', 'old_budget_ceiling': '0.6',
        'max_notional': '50', 'daily_loss_cap': '1.1',
        'max_concurrent_positions': 1, 'send_enabled': False,
    })
    intent['book'] = 'ATT1_BROKER_REPLAY:' + fingerprint
    return LifecycleSession(path, profile, intent=intent)


def _entry_fill(*, fee='0.005'):
    return {
        'symbol': 'BTCUSDT', 'orderId': 'new-order', 'orderLinkId': 'new-link',
        'execId': 'new-entry-fill', 'execType': 'Trade', 'side': 'Sell',
        'execQty': '0.05', 'execPrice': '100', 'execFee': fee,
        'feeCurrency': 'USDT', 'isMaker': False, 'execTime': str(T + 40),
        'closedSize': '0', 'extraFees': '',
    }


def _entry_event(*, received_ms=T + 50, fee='0.005'):
    return a.map_execution(
        _entry_fill(fee=fee), symbol='BTCUSDT', expected_order_id='new-order',
        expected_order_link_id='new-link', kind='ENTRY_FILL', received_ms=received_ms,
    )


def _reconcile(path, reservation, session, events, *, now_ms=T + 100):
    return a.reconcile_new_att1_lifecycle_receipts(
        path, reservation, session=session, broker_order_id='new-order',
        events=events, now_ms=now_ms,
    )


def _new_decision_row(path):
    with sqlite3.connect(path) as con:
        return con.execute(
            "SELECT broker_order_id,terminal_at_ms,costs_complete FROM att1_decisions WHERE owner='NEW'"
        ).fetchone()


def test_later_received_duplicate_reuses_durable_broker_event(tmp_path):
    """Changing only receipt time must not create a second economic fill."""
    ledger = tmp_path / 'trades.db'
    reservation = _new_reservation(ledger)
    session = _session(tmp_path / 'new.jsonl', reservation)
    first = _entry_event(received_ms=T + 50)

    _reconcile(ledger, reservation, session, [ev('ENTRY_ACK', 31), first])
    before = session.journal.path.read_bytes()
    later = _entry_event(received_ms=T + 90)
    assert later['event_id'] == first['event_id']
    assert later['received_ms'] == T + 90

    out = _reconcile(ledger, reservation, session, [later], now_ms=T + 101)
    assert session.journal.path.read_bytes() == before
    assert out['held_qty'] == '1/20'


def test_wrong_session_binding_is_rejected_before_order_identity_write(tmp_path):
    """A NEW slot cannot be bound to a journal for another ATT1 decision."""
    ledger = tmp_path / 'trades.db'
    reservation = _new_reservation(ledger)
    wrong = _session(tmp_path / 'wrong.jsonl', reservation, symbol='ETHUSDT')

    with pytest.raises(a.AdapterViolation, match='session'):
        _reconcile(ledger, reservation, wrong, [ev('ENTRY_ACK', 31)])

    assert _new_decision_row(ledger) == (None, None, 0)


def test_conflicting_same_broker_fill_retains_new_reservation(tmp_path):
    """A changed fee under one broker execution identity is evidence conflict."""
    ledger = tmp_path / 'trades.db'
    reservation = _new_reservation(ledger)
    session = _session(tmp_path / 'new.jsonl', reservation)
    _reconcile(ledger, reservation, session, [ev('ENTRY_ACK', 31), _entry_event()])

    with pytest.raises(Exception, match='conflict'):
        _reconcile(ledger, reservation, session, [_entry_event(received_ms=T + 90, fee='0.006')])

    assert _new_decision_row(ledger)[1] is None


def test_partial_or_nonterminal_receipt_cannot_release_new_reservation(tmp_path):
    """An ACK/fill without terminal, cost-complete lifecycle stays occupied."""
    ledger = tmp_path / 'trades.db'
    reservation = _new_reservation(ledger)
    session = _session(tmp_path / 'new.jsonl', reservation)

    out = _reconcile(ledger, reservation, session, [ev('ENTRY_ACK', 31), _entry_event()])
    assert out['lifecycle_terminal'] is False
    assert _new_decision_row(ledger)[1] is None


def test_crash_after_durable_terminal_journal_retries_only_final_release(tmp_path, monkeypatch):
    """A post-journal crash leaves the slot occupied until the same evidence retries."""
    ledger = tmp_path / 'trades.db'
    reservation = _new_reservation(ledger)
    session = _session(tmp_path / 'new.jsonl', reservation)
    events = [ev('ENTRY_ACK', 31), _entry_event()]
    _reconcile(ledger, reservation, session, events)
    _reconcile(ledger, reservation, session, [
        ev('PROTECTION_ACK', 51, qty='0.05', stop='110'),
        ev('ENTRY_FINAL', 52, status='FILLED'),
        ev('PRICE', 200, bid='111', ask='112'),
    ], now_ms=T+201)
    exit_id = session.receipt['pending_exit']['exit_order_id']
    terminal_events = [ev('EXIT_ACK', 202, exit_order_id=exit_id), a.map_execution(
        {**_entry_fill(), 'side': 'Buy', 'execId': 'new-exit-fill', 'execPrice': '112',
         'execFee': '0.0056', 'execTime': str(T + 203), 'closedSize': '0.05'},
        symbol='BTCUSDT', expected_order_id='new-order', expected_order_link_id='new-link',
        kind='EXIT_FILL', exit_order_id=exit_id, received_ms=T + 204,
    ), ev('EXIT_FINAL', 205, exit_order_id=exit_id, status='FILLED'), coverage(300)]

    flat = _reconcile(ledger, reservation, session, terminal_events[:-1], now_ms=T+206)
    assert flat['held_qty'] == '0'
    assert flat['lifecycle_terminal'] is False
    assert _new_decision_row(ledger)[1] is None  # Funding finality is still missing.

    original = a.finalize_att1_reservation
    def crash(*args, **kwargs):
        raise RuntimeError('crash after journal before release')
    monkeypatch.setattr(a, 'finalize_att1_reservation', crash)
    with pytest.raises(RuntimeError, match='after journal'):
        _reconcile(ledger, reservation, session, terminal_events, now_ms=T+301)
    assert session.receipt['lifecycle_terminal'] is True
    assert _new_decision_row(ledger)[1] is None
    monkeypatch.setattr(a, 'finalize_att1_reservation', original)

    restarted = LifecycleSession(session.journal.path, session.profile)
    assert restarted.receipt == session.receipt
    _reconcile(ledger, reservation, restarted, terminal_events, now_ms=T + 301)
    assert _new_decision_row(ledger)[1:] == (T + 301, 1)


def test_same_batch_redelivery_is_idempotent(tmp_path):
    ledger=tmp_path/'trades.db';reservation=_new_reservation(ledger)
    session=_session(tmp_path/'new.jsonl',reservation)
    first=_entry_event();later=_entry_event(received_ms=T+90)
    _reconcile(ledger,reservation,session,[ev('ENTRY_ACK',31),first,later])
    assert len([e for e in session.journal.read() if e['kind']=='ENTRY_FILL'])==1


@pytest.mark.parametrize('bad_receive',[None,True,T+39,T+101])
def test_invalid_duplicate_receive_clock_rejected(tmp_path,bad_receive):
    ledger=tmp_path/'trades.db';reservation=_new_reservation(ledger)
    session=_session(tmp_path/'new.jsonl',reservation)
    _reconcile(ledger,reservation,session,[ev('ENTRY_ACK',31),_entry_event()])
    duplicate=_entry_event();duplicate['received_ms']=bad_receive
    with pytest.raises(a.AdapterViolation,match='clock'):
        _reconcile(ledger,reservation,session,[duplicate])


def test_wrong_account_binding_preserves_unbound_reservation(tmp_path):
    ledger=tmp_path/'trades.db';reservation=_new_reservation(ledger)
    session=_session(tmp_path/'new.jsonl',reservation,account='uid:'+'d'*64)
    with pytest.raises(a.AdapterViolation,match='account'):
        _reconcile(ledger,reservation,session,[])
    assert _new_decision_row(ledger)==(None,None,0)
