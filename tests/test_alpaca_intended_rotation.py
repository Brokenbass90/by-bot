import copy
import json
from datetime import datetime, timezone

import pytest
from scripts import equities_alpaca_paper_bridge as bridge

NOW = datetime(2026, 10, 1, 13, 31, tzinfo=timezone.utc)


def record(symbol):
    return {'entry_order_id': 'entry-'+symbol, 'accepted_order_id': 'stop-'+symbol,
            'account_id': 'fixture', 'strategy_id': bridge._INTENDED_PAPER_STRATEGY_ID,
            'entry_price': 100., 'qty': .4, 'hwm': 110., 'accepted_stop_floor': 106.,
            'lifecycle_first_seen_at_utc': '2026-09-01T13:30:00Z'}


class Broker:
    def __init__(self):
        self.positions = {s: {'symbol': s, 'qty': '.4', 'avg_entry_price': '100', 'side': 'long'} for s in ['OLD', 'KEEP', 'FOREIGN']}
        self.orders = {}
        for s in self.positions:
            self.orders['entry-'+s] = {'id': 'entry-'+s, 'symbol': s, 'side': 'buy', 'type': 'market', 'status': 'filled', 'filled_qty': '.4', 'filled_avg_price': '100'}
            self.orders['stop-'+s] = {'id': 'stop-'+s, 'symbol': s, 'side': 'sell', 'type': 'stop', 'status': 'new', 'qty': '.4', 'filled_qty': '0', 'stop_price': '106', 'time_in_force': 'day'}
        self.sent = []; self.cancelled = []; self.crash_after_post = False; self.pending = False
    def get_account(self): return {'id': 'fixture'}
    def get_clock(self): return {'is_open': True, 'timestamp': NOW.isoformat()}
    def list_positions(self): return list(copy.deepcopy(self.positions).values())
    def list_orders(self, **kw): return [copy.deepcopy(o) for o in self.orders.values() if kw.get('status') == 'all' or o['status'] in {'new', 'partially_filled', 'pending_cancel'}]
    def get_order(self, order_id): return copy.deepcopy(self.orders[order_id])
    def get_order_by_client_id(self, client_id):
        return next((copy.deepcopy(o) for o in self.orders.values() if o.get('client_order_id') == client_id), None)
    def cancel_order(self, order_id):
        self.cancelled.append(order_id); self.orders[order_id]['status'] = 'canceled'
        return self.get_order(order_id)
    def submit_market_sell_qty(self, symbol, qty, *, client_order_id):
        self.sent.append((symbol, qty, client_order_id))
        row = {'id': 'exit-'+symbol, 'client_order_id': client_order_id, 'symbol': symbol, 'side': 'sell', 'type': 'market', 'qty': str(qty), 'status': 'new' if self.pending else 'filled', 'filled_qty': '0' if self.pending else str(qty), 'filled_avg_price': None if self.pending else '111', 'filled_at': None if self.pending else NOW.isoformat()}
        self.orders[row['id']] = row
        if not self.pending: self.positions.pop(symbol)
        if self.crash_after_post: raise OSError('response lost after broker accepted')
        return copy.deepcopy(row)


def run(tmp_path, monkeypatch, broker, *, live=False, selected=('KEEP',)):
    monkeypatch.setenv('ALPACA_INTENDED_PAPER', '0' if live else '1')
    monkeypatch.setenv('ALPACA_INTENDED_LIVE', '1' if live else '0')
    if live:
        b={'schema_version':1,'endpoint':'https://api.alpaca.markets','strategy_id':bridge._INTENDED_PAPER_STRATEGY_ID,'account_id':'fixture','capital_usd':487.42,'enabled':True,'max_positions':4,'gross_exposure':.7,'maximum_weight':.6}
        path=tmp_path/'binding.json';path.write_text(json.dumps(b))
        for key, val in {'ALPACA_INTENDED_LIVE_BINDING_PATH':str(path),'ALPACA_INTENDED_LIVE_ACK':'INTENDED_LIVE_CANARY','ALPACA_LIVE_ACCOUNT_ROLE':'monthly_v38','ALPACA_LIVE_CONFIRM':'MONTHLY_V38_LIVE','ALPACA_LIVE_MAX_CAPITAL_USD':'487.42'}.items():monkeypatch.setenv(key,val)
    ledger=tmp_path/'floor.json'
    if not ledger.exists(): ledger.write_text(json.dumps({s:record(s) for s in ['OLD','KEEP']}))
    return bridge._rotate_intended_monthly(client=broker, base_url='https://api.alpaca.markets' if live else bridge._PAPER_API_URL,
        account_id='fixture', capital=487.42, state_path=ledger, reentry_path=tmp_path/'blocks.json',
        selected_symbols=set(selected), entry_session='2026-10-01', now=NOW)


@pytest.mark.parametrize('live', [False, True])
def test_month_turn_closes_only_stale_owned_and_preserves_retained_floor(tmp_path, monkeypatch, live):
    broker=Broker(); foreign=copy.deepcopy(broker.positions['FOREIGN'])
    assert run(tmp_path,monkeypatch,broker,live=live)['status']=='COMPLETE'
    assert [s[0] for s in broker.sent]==['OLD']
    assert broker.cancelled==['stop-OLD']
    assert broker.positions['FOREIGN']==foreign
    assert json.loads((tmp_path/'floor.json').read_text())=={'KEEP':record('KEEP')}
    blocks=json.loads((tmp_path/'blocks.json').read_text())
    assert blocks['symbols']=={}  # Monthly rotation does not invent a stop re-entry block.
    assert len(blocks['rotation_exits'])==1
    assert run(tmp_path,monkeypatch,broker,live=live)['status']=='COMPLETE'
    assert len(broker.sent)==1


def test_response_lost_after_sell_is_reconciled_without_duplicate(tmp_path, monkeypatch):
    broker=Broker();broker.crash_after_post=True
    with pytest.raises(OSError): run(tmp_path,monkeypatch,broker)
    row=json.loads((tmp_path/'floor.json').read_text())['OLD']
    assert row['rotation_intent']['client_order_id']==broker.sent[0][2]
    broker.crash_after_post=False
    assert run(tmp_path,monkeypatch,broker)['status']=='COMPLETE'
    assert len(broker.sent)==1


def test_pending_sell_blocks_new_entry_phase_and_is_never_resent(tmp_path, monkeypatch):
    broker=Broker();broker.pending=True
    assert run(tmp_path,monkeypatch,broker)['status']=='PENDING'
    assert run(tmp_path,monkeypatch,broker)['status']=='PENDING'
    assert len(broker.sent)==1 and 'OLD' in json.loads((tmp_path/'floor.json').read_text())


def test_position_mismatch_cannot_cancel_or_close(tmp_path, monkeypatch):
    broker=Broker();broker.positions['OLD']['qty']='.5'
    with pytest.raises(bridge.IntendedPaperProtectionError, match='position'):
        run(tmp_path,monkeypatch,broker)
    assert not broker.sent and not broker.cancelled


def test_unknown_order_prevents_stop_cancel(tmp_path, monkeypatch):
    broker=Broker();broker.orders['unknown']={'id':'unknown','symbol':'OLD','side':'sell','type':'limit','status':'new','qty':'.4'}
    with pytest.raises(bridge.IntendedPaperProtectionError, match='order'):
        run(tmp_path,monkeypatch,broker)
    assert not broker.sent and not broker.cancelled


def test_pending_cancel_never_submits_over_reserved_quantity(tmp_path, monkeypatch):
    broker=Broker()
    def cancel(order_id): broker.cancelled.append(order_id);broker.orders[order_id]['status']='pending_cancel'
    broker.cancel_order=cancel
    assert run(tmp_path,monkeypatch,broker)['status']=='PENDING'
    assert not broker.sent


def test_rotation_receipts_survive_stop_block_updates(tmp_path):
    path=tmp_path/'blocks.json';path.write_text(json.dumps({'symbols':{},'rotation_exits':{'cycle':{'order_id':'exit'}}}))
    bridge._save_reentry_block_state(path, {'X':{'blocked_until':'2026-10-22T00:00:00Z'}})
    assert json.loads(path.read_text())['rotation_exits']=={'cycle':{'order_id':'exit'}}


def test_receipt_written_before_floor_retirement_recovers_without_duplicate(tmp_path, monkeypatch):
    broker = Broker()
    ledger = tmp_path / 'floor.json'
    original_write = bridge._atomic_write_json
    failed = False

    def fail_only_floor_retirement(path, payload):
        nonlocal failed
        if path == ledger and not failed and 'OLD' not in payload:
            failed = True
            raise OSError('crash after rotation receipt')
        return original_write(path, payload)

    monkeypatch.setattr(bridge, '_atomic_write_json', fail_only_floor_retirement)
    with pytest.raises(OSError, match='crash after rotation receipt'):
        run(tmp_path, monkeypatch, broker)
    assert len(broker.sent) == 1
    assert 'rotation_exits' in json.loads((tmp_path / 'blocks.json').read_text())
    assert 'OLD' in json.loads(ledger.read_text())
    monkeypatch.setattr(bridge, '_atomic_write_json', original_write)
    assert run(tmp_path, monkeypatch, broker)['status'] == 'COMPLETE'
    assert len(broker.sent) == 1
    assert json.loads(ledger.read_text()) == {'KEEP': record('KEEP')}


def test_durable_intent_survives_pre_submit_crash_and_restart(tmp_path, monkeypatch):
    broker = Broker()
    original_get_order = broker.get_order

    def fail_before_stop_cancel(order_id):
        if order_id == 'stop-OLD':
            raise OSError('broker lookup interrupted before submit')
        return original_get_order(order_id)

    broker.get_order = fail_before_stop_cancel
    with pytest.raises(OSError, match='before submit'):
        run(tmp_path, monkeypatch, broker)
    floor = json.loads((tmp_path / 'floor.json').read_text())
    assert floor['OLD']['rotation_intent']['client_order_id'].startswith('alp-rotate-')
    assert floor['KEEP'] == record('KEEP')
    assert not broker.sent and not broker.cancelled
    broker.get_order = original_get_order
    assert run(tmp_path, monkeypatch, broker)['status'] == 'COMPLETE'
    assert len(broker.sent) == 1
    assert json.loads((tmp_path / 'floor.json').read_text()) == {'KEEP': record('KEEP')}


@pytest.mark.parametrize('is_open,timestamp', [(False, NOW), (True, datetime(2026, 9, 30, 19, 59, tzinfo=timezone.utc))])
def test_market_or_session_not_ready_never_submits(tmp_path, monkeypatch, is_open, timestamp):
    broker = Broker()
    broker.get_clock = lambda: {'is_open': is_open, 'timestamp': timestamp.isoformat()}
    before = {'OLD': record('OLD'), 'KEEP': record('KEEP')}
    assert run(tmp_path, monkeypatch, broker) == {'status': 'PENDING', 'reason': 'awaiting_entry_session'}
    assert not broker.sent and not broker.cancelled
    assert json.loads((tmp_path / 'floor.json').read_text()) == before


def test_lookup_error_is_not_interpreted_as_absent_order(tmp_path, monkeypatch):
    broker = Broker()
    broker.get_order_by_client_id = lambda _client_id: (_ for _ in ()).throw(OSError('broker auth unavailable'))
    with pytest.raises(OSError, match='auth unavailable'):
        run(tmp_path, monkeypatch, broker)
    assert not broker.sent and not broker.cancelled
    assert json.loads((tmp_path / 'floor.json').read_text()) == {'OLD': record('OLD'), 'KEEP': record('KEEP')}


def test_malicious_returned_market_order_halts_without_retiring_floor(tmp_path, monkeypatch):
    broker = Broker()
    original_submit = broker.submit_market_sell_qty

    def malicious_submit(symbol, qty, *, client_order_id):
        order = original_submit(symbol, qty, client_order_id=client_order_id)
        order['client_order_id'] = 'attacker-controlled-id'
        return order

    broker.submit_market_sell_qty = malicious_submit
    with pytest.raises(bridge.IntendedPaperProtectionError, match='rotation_exit_identity_mismatch:OLD'):
        run(tmp_path, monkeypatch, broker)
    floor = json.loads((tmp_path / 'floor.json').read_text())
    assert floor['KEEP'] == record('KEEP')
    assert floor['OLD']['hwm'] == record('OLD')['hwm']
    assert floor['OLD']['accepted_stop_floor'] == record('OLD')['accepted_stop_floor']


@pytest.mark.parametrize('fill_on_cancel', [False, True])
def test_stop_fill_before_or_during_cancel_never_submits_market_sell(tmp_path, monkeypatch, fill_on_cancel):
    broker = Broker()
    stop = broker.orders['stop-OLD']

    def fill_stop():
        stop.update({'status': 'filled', 'filled_qty': '.4', 'filled_avg_price': '106', 'filled_at': NOW.isoformat()})
        broker.positions.pop('OLD', None)

    if fill_on_cancel:
        def cancel(order_id):
            broker.cancelled.append(order_id)
            fill_stop()
        broker.cancel_order = cancel
    else:
        fill_stop()
    result = run(tmp_path, monkeypatch, broker)
    assert not broker.sent
    assert json.loads((tmp_path / 'floor.json').read_text()).get('KEEP') == record('KEEP')
    if fill_on_cancel:
        assert result == {'status': 'PENDING', 'reason': 'stop_fill_requires_reconciliation', 'symbol': 'OLD'}
    else:
        assert result['status'] == 'COMPLETE'
        assert 'OLD' not in json.loads((tmp_path / 'floor.json').read_text())
