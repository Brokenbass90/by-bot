import copy
import json
from types import SimpleNamespace

import pytest
from scripts import equities_alpaca_paper_bridge as b


class Exchange:
    def __init__(self):
        self.orders = {}; self.positions = []; self.buys = 0; self.stops = 0
        self.crash = ''
    def get_account(self): return {'id': 'fixture'}
    def get_order(self, key): return copy.deepcopy(self.orders[key])
    def get_order_by_client_id(self, key):
        return next((copy.deepcopy(o) for o in self.orders.values() if o['client_order_id'] == key), None)
    def list_positions(self): return copy.deepcopy(self.positions)
    def list_orders(self, **kw): return [copy.deepcopy(o) for o in self.orders.values() if o['status'] == 'new']
    def cancel_order(self, key): self.orders[key]['status'] = 'canceled'
    def submit_market_buy(self, symbol, notional, *, client_order_id):
        self.buys += 1
        row = dict(id='buy', client_order_id=client_order_id, symbol=symbol, side='buy', type='market', time_in_force='day',
                   notional=str(notional), status='filled', filled_qty='0.4', filled_avg_price='100', filled_at='2026-10-01T13:30:01Z')
        self.orders['buy'] = row
        self.positions = [dict(symbol=symbol, qty='.4', avg_entry_price='100', current_price='100', side='long')]
        if self.crash == 'buy': raise OSError('lost response')
        return copy.deepcopy(row)
    def submit_stop_sell(self, symbol, *, qty, stop_price, time_in_force, client_order_id):
        self.stops += 1
        row = dict(id='stop', client_order_id=client_order_id, symbol=symbol, side='sell', type='stop',
                   qty=str(qty), filled_qty='0', stop_price=str(stop_price), time_in_force=time_in_force, status='new')
        self.orders['stop'] = row
        if self.crash == 'stop': raise OSError('lost stop response')
        return copy.deepcopy(row)


def enter(tmp_path, monkeypatch, exchange):
    monkeypatch.setenv('ALPACA_INTENDED_PAPER', '1'); monkeypatch.setenv('ALPACA_INTENDED_LIVE', '0')
    return b._submit_intended_reserved_entry(client=exchange, base_url=b._PAPER_API_URL, account_id='fixture', capital=487.42,
        reentry_path=tmp_path/'blocks.json', state_path=tmp_path/'floor.json', state_dir=tmp_path/'halt',
        pick=SimpleNamespace(ticker='NEW', entry_day='2026-10-01', entry_price=100., stop_price=94.), notional=40., timeout_sec=0)


@pytest.mark.parametrize('crash', ['buy', 'stop'])
def test_lost_broker_response_recovers_exact_order_and_floor_without_resubmission(tmp_path, monkeypatch, crash):
    exchange = Exchange(); exchange.crash = crash
    with pytest.raises(OSError): enter(tmp_path, monkeypatch, exchange)
    raw = json.loads((tmp_path/'blocks.json').read_text())
    assert next(iter(raw['entry_intents'].values()))['status'] == 'reserved'
    exchange.crash = ''
    b._recover_intended_entry_intents(client=exchange, base_url=b._PAPER_API_URL, account_id='fixture', capital=487.42,
        reentry_path=tmp_path/'blocks.json', state_path=tmp_path/'floor.json', state_dir=tmp_path/'halt')
    state = json.loads((tmp_path/'floor.json').read_text())['NEW']
    assert state['entry_order_id'] == 'buy' and state['accepted_order_id'] == 'stop'
    assert state['accepted_stop_floor'] == 94 and state['hwm'] == 100
    assert exchange.buys == exchange.stops == 1


def test_reservation_is_durable_before_first_post_and_duplicate_cycle_cannot_reenter(tmp_path, monkeypatch):
    exchange = Exchange(); original = exchange.submit_market_buy
    def submit(*args, **kwargs):
        row = json.loads((tmp_path/'blocks.json').read_text())['entry_intents'][kwargs['client_order_id']]
        assert row['status'] == 'reserved' and row['notional'] == 40.
        return original(*args, **kwargs)
    exchange.submit_market_buy = submit
    enter(tmp_path, monkeypatch, exchange)
    with pytest.raises(b.IntendedPaperProtectionError, match='entry_cycle_already_consumed'):
        enter(tmp_path, monkeypatch, exchange)
    assert exchange.buys == 1


def test_fresh_position_mismatch_never_adopted(tmp_path, monkeypatch):
    exchange = Exchange(); exchange.crash = 'buy'
    with pytest.raises(OSError): enter(tmp_path, monkeypatch, exchange)
    exchange.positions[0]['qty'] = '9'
    with pytest.raises(b.IntendedPaperProtectionError, match='position_mismatch'):
        b._recover_intended_entry_intents(client=exchange, base_url=b._PAPER_API_URL, account_id='fixture', capital=487.42,
            reentry_path=tmp_path/'blocks.json', state_path=tmp_path/'floor.json', state_dir=tmp_path/'halt')
    assert exchange.stops == 0


def test_partial_buy_response_loss_cancels_remainder_and_protects_actual_qty(tmp_path, monkeypatch):
    exchange = Exchange(); exchange.crash = 'buy'
    with pytest.raises(OSError): enter(tmp_path, monkeypatch, exchange)
    exchange.orders['buy'].update(status='partially_filled', filled_qty='.2')
    exchange.positions[0]['qty'] = '.2'
    b._recover_intended_entry_intents(client=exchange, base_url=b._PAPER_API_URL, account_id='fixture', capital=487.42,
        reentry_path=tmp_path/'blocks.json', state_path=tmp_path/'floor.json', state_dir=tmp_path/'halt')
    assert exchange.orders['buy']['status'] == 'canceled'
    assert exchange.orders['stop']['qty'] == '0.2'
    assert exchange.buys == exchange.stops == 1
