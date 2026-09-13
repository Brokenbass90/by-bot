"""Authenticated Bybit account identity is mandatory for opt-in ATT1 dispatch."""
import sqlite3

import pytest

from bot import att1_coordinator_adapter as a


H1 = 3_600_000
T = 500_000 * H1
RECEIVED_MS = T + 10_000
CONFIG = {
    'name': 'operator-alias-must-not-be-ledger-identity',
    'key': 'selected-api-key',
    'base': 'https://api.bybit.com',
}


def _envelope(*, key='selected-api-key', user_id='123456789', time_ms=RECEIVED_MS):
    return {
        'retCode': 0,
        'time': str(time_ms),
        'result': {
            'apiKey': key,
            'userID': user_id,
            'parentUid': 'never-used-parent-uid',
            'note': 'never-used-name',
        },
    }


def _identity(config=CONFIG, **changes):
    envelope = _envelope(**changes)
    return a.validate_old_att1_broker_identity(
        config, envelope, received_ms=RECEIVED_MS,
    )


def _reserve(path, identity, *, config=CONFIG, now_ms=RECEIVED_MS + 1):
    return a.reserve_old_att1_dispatch(
        path,
        config,
        symbol='ETHUSDT',
        side='Sell',
        consumed_h1_rows=[[T - H1, '1', '1', '1', '1', '1']],
        now_ms=now_ms,
        enabled=True,
        broker_identity=identity,
    )


def test_query_api_identity_uses_only_endpoint_and_authenticated_user_id():
    identity = _identity()
    rotated_config = {**CONFIG, 'key': 'rotated-api-key'}
    rotated = _identity(rotated_config, key='rotated-api-key')

    assert identity.account.startswith('uid:')
    assert identity.account == rotated.account
    assert identity.credential_binding_sha256 != rotated.credential_binding_sha256
    exposed = repr(identity) + repr(vars(identity))
    for forbidden in ('selected-api-key', CONFIG['name'], 'never-used-parent-uid', 'never-used-name'):
        assert forbidden not in exposed


@pytest.mark.parametrize('config,envelope,received_ms', [
    (CONFIG, _envelope(time_ms=RECEIVED_MS - 60_001), RECEIVED_MS),
    (CONFIG, _envelope(time_ms=RECEIVED_MS + 1), RECEIVED_MS),
    (CONFIG, {**_envelope(), 'retCode': '0'}, RECEIVED_MS),
    (CONFIG, {**_envelope(), 'retCode': False}, RECEIVED_MS),
    (CONFIG, {**_envelope(), 'retCode': 1}, RECEIVED_MS),
    (CONFIG, _envelope(key='other-key'), RECEIVED_MS),
    (CONFIG, _envelope(user_id='0'), RECEIVED_MS),
    (CONFIG, {**_envelope(), 'result': {'apiKey': CONFIG['key'], 'userID': True}}, RECEIVED_MS),
    ({**CONFIG, 'base': 'http://api.bybit.com'}, _envelope(), RECEIVED_MS),
    ({**CONFIG, 'base': 'https://api-testnet.bybit.com'}, _envelope(), RECEIVED_MS),
])
def test_query_api_identity_rejects_stale_wrong_or_malformed_evidence(config, envelope, received_ms):
    with pytest.raises(a.AdapterViolation):
        a.validate_old_att1_broker_identity(config, envelope, received_ms=received_ms)


def test_disabled_dispatch_returns_before_identity_or_sqlite_io(tmp_path):
    path = tmp_path / 'trades.db'
    assert a.reserve_old_att1_dispatch(
        path, CONFIG, symbol='ETHUSDT', side='Sell',
        consumed_h1_rows=[[T - H1, '1', '1', '1', '1', '1']],
        now_ms=RECEIVED_MS + 1, enabled=False,
    ) is None
    assert not path.exists()


def test_enabled_dispatch_requires_fresh_config_bound_identity(tmp_path):
    path = tmp_path / 'trades.db'
    with pytest.raises(a.AdapterViolation, match='identity'):
        _reserve(path, None)
    assert not path.exists()

    identity = _identity()
    with pytest.raises(a.AdapterViolation, match='stale'):
        _reserve(path, identity, now_ms=RECEIVED_MS + a.ATT1_BROKER_IDENTITY_MAX_AGE_MS + 1)
    assert not path.exists()


def test_rotated_credential_keeps_the_authenticated_uid_reservation_slot(tmp_path):
    path = tmp_path / 'trades.db'
    original = _identity()
    reservation = _reserve(path, original)
    rotated_config = {**CONFIG, 'key': 'rotated-api-key'}
    rotated = _identity(rotated_config, key='rotated-api-key')

    with pytest.raises(a.AdapterViolation, match='cooldown|occupied'):
        _reserve(path, rotated, config=rotated_config, now_ms=RECEIVED_MS + 2)
    assert reservation['account'] == rotated.account
    with sqlite3.connect(path) as con:
        assert con.execute('SELECT account FROM att1_route').fetchone()[0] == rotated.account


def test_read_and_ack_lookup_deny_identity_or_account_mismatch(tmp_path):
    path = tmp_path / 'trades.db'
    identity = _identity()
    reservation = _reserve(path, identity)
    other_config = {**CONFIG, 'key': 'other-api-key'}
    other_identity = _identity(other_config, key='other-api-key', user_id='987654321')

    with pytest.raises(a.AdapterViolation):
        a.read_unresolved_old_att1_dispatches(
            path, CONFIG, broker_identity=other_identity, now_ms=RECEIVED_MS + 2,
        )
    with pytest.raises(a.AdapterViolation):
        a.validate_old_att1_ack_lookup(
            CONFIG, reservation,
            {'symbol': 'ETHUSDT', 'side': 'Sell',
             'orderLinkId': reservation['order_link_id'], 'orderId': 'ack-1'},
            broker_identity=other_identity, now_ms=RECEIVED_MS + 2,
        )


def test_legacy_cfg_ledger_blocks_fresh_uid_route_creation(tmp_path):
    path = tmp_path / 'trades.db'
    with sqlite3.connect(path) as con:
        a.initialize_att1_route(
            con, a.att1_account_config_fingerprint(CONFIG), now_ms=RECEIVED_MS,
        )

    with pytest.raises(a.AdapterViolation, match='legacy'):
        _reserve(path, _identity())
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM att1_route WHERE account LIKE 'uid:%'").fetchone()[0] == 0
