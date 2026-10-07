"""Captured Oct7 failure regression; all broker operations are offline doubles."""
import copy
import json
import sys

import pytest

from scripts import equities_alpaca_paper_bridge as bridge
from scripts import alpaca_adaptive_paper as driver


def record(symbol):
    return {'entry_order_id': 'entry-'+symbol, 'accepted_order_id': 'expired-'+symbol,
            'accepted_order_tif': 'day', 'account_id': 'fixture',
            'strategy_id': bridge._INTENDED_PAPER_STRATEGY_ID,
            'entry_price': 100., 'qty': .4, 'entry_fill_qty': .4,
            'hwm': 110., 'accepted_stop_floor': 106.,
            'lifecycle_first_seen_at_utc': '2026-10-01T13:30:00Z'}


class Broker:
    def __init__(self, failed, below_floor=False, storage_failure=False):
        self.failed = failed
        self.storage_failure = storage_failure
        self.positions = [{'symbol': s, 'qty': '.4', 'avg_entry_price': '100',
                           'current_price': '105' if below_floor and s in failed else '109',
                           'side': 'long'} for s in ['CRWD', 'META']]
        self.orders = {}
        self.attempts = []

    def get_account(self):
        return {'id': 'fixture', 'status': 'ACTIVE', 'cash': '262.22', 'equity': '496.12'}

    def get_clock(self):
        return {'is_open': True, 'timestamp': '2026-10-07T13:30:16Z'}

    def list_positions(self):
        return copy.deepcopy(self.positions)

    def list_orders(self, **kwargs):
        return copy.deepcopy(list(self.orders.values()))

    def get_order(self, order_id):
        return copy.deepcopy(self.orders[order_id])

    def submit_stop_sell(self, symbol, *, qty, stop_price, time_in_force):
        self.attempts.append(symbol)
        assert qty == .4 and stop_price == 106 and time_in_force == 'day'
        if symbol in self.failed:
            if self.storage_failure:
                raise OSError('fixture fatal storage uncertainty')
            raise RuntimeError('POST /v2/orders failed: 422 stop price above current price')
        order = {'id': 'new-'+symbol, 'symbol': symbol, 'side': 'sell', 'type': 'stop',
                 'status': 'new', 'qty': '.4', 'filled_qty': '0', 'stop_price': '106',
                 'time_in_force': 'day'}
        self.orders[order['id']] = order
        return copy.deepcopy(order)


def run(tmp_path, monkeypatch, broker):
    picks = tmp_path/'picks.csv'
    picks.write_text('month,ticker,entry_day,score,atr20_pct,momentum20_pct,momentum60_pct,pullback60_pct,entry_price,stop_price,weight\n'
                     '2026-10,CRWD,2026-10-01,1,2,3,4,-1,100,95,.3\n'
                     '2026-10,META,2026-10-01,1,2,3,4,-1,100,95,.3\n')
    ledger = tmp_path/'floor.json'
    ledger.write_text(json.dumps({s: record(s) for s in ['CRWD', 'META']}))
    for key, value in {
        'ALPACA_INTENDED_PAPER': '1', 'ALPACA_INTENDED_LIVE': '0',
        'ALPACA_BASE_URL': bridge._PAPER_API_URL, 'ALPACA_API_KEY_ID': 'fixture',
        'ALPACA_API_SECRET_KEY': 'fixture', 'ALPACA_SEND_ORDERS': '1',
        'ALPACA_ALLOW_NEW_ENTRIES': '0', 'ALPACA_INTENDED_MONTHLY': '1',
        'ALPACA_INTENDED_ENTRY_SESSION': '2026-10-01',
        'ALPACA_PROTECTIVE_EXIT_HWM_PATH': str(ledger),
        'ALPACA_MONTHLY_REENTRY_PATH': str(tmp_path/'blocks.json'),
        'ALPACA_BRIDGE_LOCK_PATH': str(tmp_path/'account.lock'),
        'ALPACA_CAPITAL_OVERRIDE_USD': '487.42', 'ALPACA_EARNINGS_FILTER': '0',
        'TG_TOKEN': '', 'TG_CHAT_ID': '',
    }.items(): monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, 'argv', ['bridge', '--picks-csv', str(picks)])
    monkeypatch.setattr(bridge, 'AlpacaClient', lambda *args: broker)
    monkeypatch.setattr(bridge, '_paper_kill_state_dir', lambda *args: tmp_path)
    monkeypatch.setattr(bridge, '_reentry_block_state_path', lambda *args: tmp_path/'blocks.json')
    monkeypatch.setattr(bridge, '_rotate_intended_monthly', lambda **kwargs: pytest.fail('rotation reached after failed protection'))
    rc = bridge._main_unlocked()
    return rc, ledger


@pytest.mark.parametrize('failed', [{'CRWD'}, {'META'}, {'CRWD', 'META'}])
@pytest.mark.parametrize('below_floor', [False, True])
def test_failed_rearm_halts_entries_after_protecting_other_owned_name(tmp_path, monkeypatch, failed, below_floor):
    # Aborting the retained-name loop after the first rejection leaves a healthy
    # name unprotected and expands the real emergency exit scope.
    broker = Broker(failed, below_floor)
    rc, ledger = run(tmp_path, monkeypatch, broker)
    assert rc == 9
    assert json.loads((tmp_path/'.paper-entry-halt.json').read_text())['halted'] is True
    saved = json.loads(ledger.read_text())
    for symbol in ['CRWD', 'META']:
        if symbol in failed:
            assert saved[symbol] == record(symbol)
        else:
            assert saved[symbol]['accepted_order_id'] == 'new-'+symbol
            assert saved[symbol]['accepted_stop_floor'] == 106
            assert saved[symbol]['hwm'] == 110
    assert len(broker.attempts) == len(set(broker.attempts))
    emergency_calls = []
    def emergency(command, **kwargs):
        from subprocess import CompletedProcess
        proof = json.loads((tmp_path/'emergency_owned_proof.json').read_text())
        emergency_calls.append([p['symbol'] for p in proof['positions']])
        return CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(driver.subprocess, 'run', emergency)
    result = driver._intended_emergency_exits(broker, {'ALPACA_PROTECTIVE_EXIT_HWM_PATH': str(ledger)}, tmp_path, 'fixture')
    assert result['scope'] == [s for s in ['CRWD', 'META'] if s in failed]
    assert emergency_calls == [[s for s in ['CRWD', 'META'] if s in failed]]


def test_unexpected_storage_uncertainty_still_aborts_before_other_mutations(tmp_path, monkeypatch):
    broker = Broker({'CRWD'}, storage_failure=True)
    rc, ledger = run(tmp_path, monkeypatch, broker)
    assert rc == 9 and not broker.orders
    assert broker.attempts == ['CRWD']
    assert json.loads(ledger.read_text()) == {s: record(s) for s in ['CRWD', 'META']}


def test_uncertain_stop_readback_is_not_retried_or_assumed_unprotected(tmp_path, monkeypatch):
    broker = Broker({'CRWD'})
    original_get = broker.get_order
    first_read = True
    def read(order_id):
        nonlocal first_read
        if order_id == 'new-META' and first_read:
            first_read = False
            raise RuntimeError('fixture stop readback temporarily unavailable')
        return original_get(order_id)
    broker.get_order = read
    rc, ledger = run(tmp_path, monkeypatch, broker)
    assert rc == 9
    assert broker.attempts == ['CRWD', 'META']
    assert json.loads(ledger.read_text()) == {s: record(s) for s in ['CRWD', 'META']}
    from subprocess import CompletedProcess
    monkeypatch.setattr(driver.subprocess, 'run', lambda command, **kwargs: CompletedProcess(command, 0, '', ''))
    result = driver._intended_emergency_exits(broker, {'ALPACA_PROTECTIVE_EXIT_HWM_PATH': str(ledger)}, tmp_path, 'fixture')
    # Fresh real emergency verification sees the broker-accepted META stop even
    # though the first readback could not persist it. No second dispatch occurs.
    assert result['scope'] == ['CRWD']
    assert broker.attempts == ['CRWD', 'META']
