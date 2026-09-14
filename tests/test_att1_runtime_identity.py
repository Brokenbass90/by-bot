"""Exercise production identity collection without importing live startup."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

T = 1_800_000_000_000


def helper_namespace():
    tree = ast.parse(Path('smart_pump_reversal_bot.py').read_text())
    node = next(n for n in tree.body if getattr(n, 'name', '') == '_att1_read_broker_identity')
    cfg = {'name': 'main', 'key': 'fixture-key', 'base': 'https://api.bybit.com'}
    ns = {'ATT1_COORDINATOR_BINDING_ENABLE': True, 'TRADE_ACCOUNT_NAME': 'main',
          '_find_account_cfg': lambda _: cfg, 'time': SimpleNamespace(time=lambda: T/1000)}
    calls = []
    def get(path, params, timeout):
        calls.append((path, params, timeout))
        return {'retCode': 0, 'time': T, 'result': {'apiKey': cfg['key'], 'userID': 12345}}
    ns['TRADE_CLIENT'] = SimpleNamespace(name='main', key='fixture-key', base=cfg['base'], get=get)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<production-identity>', 'exec'), ns)
    return ns, cfg, calls


def test_disabled_identity_has_no_client_or_network_dependency():
    ns, _, calls = helper_namespace()
    ns['ATT1_COORDINATOR_BINDING_ENABLE'] = False
    ns['TRADE_CLIENT'] = None
    assert ns['_att1_read_broker_identity']() is None
    assert calls == []


def test_identity_uses_selected_authenticated_transport():
    ns, _, calls = helper_namespace()
    identity = ns['_att1_read_broker_identity']()
    assert identity.account.startswith('uid:')
    assert calls == [('/v5/user/query-api', {}, 10)]
    assert identity.observed_at_ms == T


@pytest.mark.parametrize('field,value', [('key', 'other-key'), ('name', 'alias'), ('base', 'https://wrong.invalid')])
def test_client_config_mismatch_denies_before_network(field, value):
    ns, _, calls = helper_namespace()
    setattr(ns['TRADE_CLIENT'], field, value)
    with pytest.raises(ValueError):
        ns['_att1_read_broker_identity']()
    assert calls == []


def test_untrusted_endpoint_denied_even_if_config_and_client_agree():
    ns, cfg, calls = helper_namespace()
    cfg['base'] = ns['TRADE_CLIENT'].base = 'https://wrong.invalid'
    with pytest.raises(ValueError):
        ns['_att1_read_broker_identity']()
    assert calls == []


def snapshot_client(get):
    tree = ast.parse(Path('smart_pump_reversal_bot.py').read_text())
    cls = next(n for n in tree.body if getattr(n, 'name', '') == 'BybitClient')
    method = next(n for n in cls.body if getattr(n, 'name', '') == 'get_att1_open_snapshot_pages')
    ns = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<production-pages>', 'exec'), ns)
    return lambda: ns['get_att1_open_snapshot_pages'](SimpleNamespace(get=get))


def test_snapshot_transport_consumes_all_cursors_and_only_active_orders():
    calls = []
    def get(path, params, timeout):
        calls.append((path, dict(params), timeout))
        cursor = 'second' if 'cursor' not in params else ''
        return {'retCode': 0, 'time': T, 'result': {'category': 'linear', 'list': [], 'nextPageCursor': cursor}}
    result = snapshot_client(get)()
    assert list(result) == ['position_pages', 'order_pages']
    assert [len(x) for x in result.values()] == [2, 2]
    assert [x[0] for x in calls] == ['/v5/position/list']*2 + ['/v5/order/realtime']*2
    assert [x[1].get('cursor') for x in calls] == [None, 'second', None, 'second']
    assert all(x[1]['openOnly'] == 0 and 'orderFilter' not in x[1] for x in calls[2:])
    assert all(x[1]['settleCoin'] == 'USDT' for x in calls)


def test_snapshot_transport_rejects_cursor_cycle_without_infinite_requests():
    calls = []
    def get(path, params, timeout):
        calls.append(path)
        return {'retCode': 0, 'time': T, 'result': {'category': 'linear', 'list': [], 'nextPageCursor': 'loop'}}
    with pytest.raises(ValueError):
        snapshot_client(get)()
    assert len(calls) == 2


def wired_snapshot_namespace():
    ns, cfg, calls = helper_namespace()
    tree = ast.parse(Path('smart_pump_reversal_bot.py').read_text())
    names = {'_att1_read_broker_snapshot', '_att1_reserve_old_dispatch'}
    nodes = [n for n in tree.body if getattr(n, 'name', '') in names]
    import sqlite3
    ns.update(sqlite3=sqlite3, _diag_inc=lambda _: None, log_error=lambda _: None)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<production-reconciliation>', 'exec'), ns)
    page = {'retCode': 0, 'time': T, 'result': {'category': 'linear', 'list': [], 'nextPageCursor': ''}}
    ns['TRADE_CLIENT'].get_att1_open_snapshot_pages = lambda: {
        'position_pages': [page], 'order_pages': [page]}
    return ns, cfg, calls


def test_snapshot_disabled_has_no_network_or_client_dependency():
    ns, _, calls = wired_snapshot_namespace()
    ns.update(ATT1_COORDINATOR_BINDING_ENABLE=False, TRADE_CLIENT=None)
    assert ns['_att1_read_broker_snapshot']() == (None, None)
    assert ns['_att1_reserve_old_dispatch']('ETHUSDT', None, T) == (True, None)
    assert calls == []


def test_snapshot_signed_identity_is_checked_before_and_after_pages():
    ns, _, calls = wired_snapshot_namespace()
    proof, snapshot = ns['_att1_read_broker_snapshot']()
    assert snapshot['account'] == proof.account
    assert snapshot['flat_no_orders'] is True
    assert len(calls) == 2


@pytest.mark.parametrize('change', ['uid', 'client', 'key'])
def test_identity_or_transport_change_during_snapshot_fails_closed(change):
    ns, cfg, _ = wired_snapshot_namespace()
    client = ns['TRADE_CLIENT']
    original_pages = client.get_att1_open_snapshot_pages
    def pages():
        if change == 'uid':
            client.get = lambda *args, **kwargs: {'retCode': 0, 'time': T,
                'result': {'apiKey': cfg['key'], 'userID': 999}}
        elif change == 'key':
            cfg['key'] = client.key = 'replacement-key'
        else:
            ns['TRADE_CLIENT'] = SimpleNamespace(**vars(client))
        return original_pages()
    client.get_att1_open_snapshot_pages = pages
    with pytest.raises(ValueError):
        ns['_att1_read_broker_snapshot']()


def test_wired_flat_snapshot_reserves_once_and_never_clears_unknown(tmp_path):
    ns, _, _ = wired_snapshot_namespace()
    ns['TRADE_DB_PATH'] = str(tmp_path / 'trades.db')
    proof, snapshot = ns['_att1_read_broker_snapshot']()
    args = dict(broker_identity=proof, broker_snapshot=snapshot)
    bars = [[T - 3600000, '1', '1', '1', '1', '1']]
    accepted, reservation = ns['_att1_reserve_old_dispatch']('ETHUSDT', bars, T, **args)
    assert accepted and reservation['order_link_id']
    # Re-reading a flat broker cannot release a possibly submitted durable intent.
    proof, snapshot = ns['_att1_read_broker_snapshot']()
    assert ns['_att1_reserve_old_dispatch']('BTCUSDT', bars, T,
        broker_identity=proof, broker_snapshot=snapshot) == (False, None)


@pytest.mark.parametrize('patch', [None, {'account': 'uid:' + '0'*64},
    {'observed_ms': T-60001}, {'observed_ms': T+1}, {'flat_no_orders': False},
    {'position_count': 1}, {'order_count': 1}, {'source_sha256': 'invalid'}])
def test_wired_missing_stale_foreign_or_occupied_snapshot_never_opens_ledger(tmp_path, patch):
    ns, _, _ = wired_snapshot_namespace()
    path = tmp_path / 'must-not-exist.db'
    ns['TRADE_DB_PATH'] = str(path)
    proof, snapshot = ns['_att1_read_broker_snapshot']()
    snapshot = None if patch is None else {**snapshot, **patch}
    assert ns['_att1_reserve_old_dispatch']('ETHUSDT', [[T-3600000]], T,
        broker_identity=proof, broker_snapshot=snapshot) == (False, None)
    assert not path.exists()


def test_entry_awaits_reconciliation_off_event_loop_before_durable_reserve():
    tree = ast.parse(Path('smart_pump_reversal_bot.py').read_text())
    caller = next(n for n in tree.body if getattr(n, 'name', '') == 'try_att1_entry_async')
    collect = next(n for n in ast.walk(caller) if isinstance(n, ast.Await)
        and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute)
        and n.value.func.attr == 'to_thread'
        and getattr(n.value.args[0], 'id', '') == '_att1_read_broker_snapshot')
    reserve = next(n for n in ast.walk(caller) if isinstance(n, ast.Call)
        and getattr(n.func, 'id', '') == '_att1_reserve_old_dispatch')
    assert collect.lineno < reserve.lineno
    assert any(k.arg == 'broker_snapshot' for k in reserve.keywords)


def test_snapshot_collection_deadline_rejects_delayed_response(monkeypatch):
    import time
    now = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    calls = []
    def get(path, params, timeout):
        calls.append(path)
        now[0] += 51
        return {'retCode': 0, 'time': T, 'result': {'category': 'linear', 'list': [], 'nextPageCursor': ''}}
    with pytest.raises(ValueError, match='expired'):
        snapshot_client(get)()
    assert len(calls) == 1
