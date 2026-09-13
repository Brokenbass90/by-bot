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
