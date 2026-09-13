"""Bybit evidence -> existing ATT1 event contract. No transport or send API.

These pure mappers validate broker-shaped records, not their authenticity.
The owning process must durably bind account/order identities and collect
complete signed evidence before any live use. No ACK manufactures a fill or
protective stop. Synthetic fixtures exercise this boundary without credentials.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import sqlite3
from pathlib import Path
from research_lab.att1_ets2s_accounting import _decimal, AccountingViolation
from research_lab.att1_lifecycle_coordinator import digest

SEND_ENABLED = False
# Preparation ledger only. NEW_READY never authorizes transport or money.
# The monolith has an opt-in OLD reservation/ACK path; NEW remains unwired.
# Flat/finality flags and evidence hashes still require authenticated reconciliation.
ATT1_FAMILY = 'ATT1'
ATT1_H1_MS = 60 * 60 * 1000
ATT1_COOLDOWN_MS = 8 * 60 * 60 * 1000
ATT1_BROKER_IDENTITY_MAX_AGE_MS = 60 * 1000
ATT1_BYBIT_PRODUCTION_ENDPOINT = 'https://api.bybit.com'


class AdapterViolation(ValueError):
    """Unsupported, mismatched or incomplete broker evidence."""


@dataclass(frozen=True)
class ValidatedOldAtt1BrokerIdentity:
    """Fresh, redacted account binding derived from a trusted signed response.

    The caller's transport owns HTTPS, Bybit request signing, and preservation
    of the signed ``/v5/user/query-api`` response.  This pure validator only
    checks that supplied envelope and cannot itself prove authenticity.
    """
    account: str
    endpoint: str
    credential_binding_sha256: str
    observed_at_ms: int


def _require_account(account):
    return _text(account, 'account')


def _route_row(row):
    if row is None:
        raise AdapterViolation('ATT1 route missing')
    keys = ('account', 'family', 'owner', 'cutover_ms', 'latest_h1_ms',
            'drained_at_ms', 'broker_truth_sha256', 'paused_at_ms', 'updated_ms')
    if any(key not in row for key in keys) or row['family'] != ATT1_FAMILY:
        raise AdapterViolation('ATT1 route malformed')
    if row['owner'] not in {'OLD', 'OLD_PAUSED', 'NEW_READY'}:
        raise AdapterViolation('ATT1 route owner malformed')
    for key in ('cutover_ms', 'latest_h1_ms', 'drained_at_ms', 'paused_at_ms', 'updated_ms'):
        if row[key] is not None and (type(row[key]) is not int or row[key] < 0):
            raise AdapterViolation('ATT1 route timestamp malformed')
    if row['broker_truth_sha256'] is not None and (
        not isinstance(row['broker_truth_sha256'], str)
        or len(row['broker_truth_sha256']) != 64
        or any(c not in '0123456789abcdef' for c in row['broker_truth_sha256'])
    ):
        raise AdapterViolation('ATT1 broker truth hash malformed')
    if row['updated_ms'] is None:
        raise AdapterViolation('ATT1 route clock malformed')
    if row['latest_h1_ms'] is not None and row['latest_h1_ms'] % ATT1_H1_MS:
        raise AdapterViolation('ATT1 route H1 malformed')
    if row['owner'] != 'OLD' and row['paused_at_ms'] is None:
        raise AdapterViolation('ATT1 route pause malformed')
    if row['owner'] == 'NEW_READY' and (
        any(row[k] is None for k in ('cutover_ms', 'latest_h1_ms', 'drained_at_ms', 'broker_truth_sha256'))
        or row['cutover_ms'] % ATT1_H1_MS
        or row['cutover_ms'] <= row['drained_at_ms']
        or not row['paused_at_ms'] <= row['drained_at_ms'] <= row['updated_ms']
    ):
        raise AdapterViolation('ATT1 cutover malformed')
    return dict(row)


def _begin(con):
    if not isinstance(con, sqlite3.Connection):
        raise AdapterViolation('SQLite connection required')
    if con.in_transaction:
        raise AdapterViolation('caller transaction already active')
    con.execute('PRAGMA synchronous=FULL')
    con.execute('BEGIN IMMEDIATE')


def init_att1_route_tables(con):
    """Create the small durable ATT1 route/decision ledger in the existing DB."""
    _begin(con)
    schema = '''
        CREATE TABLE IF NOT EXISTS att1_route (
            account TEXT PRIMARY KEY,
            family TEXT NOT NULL,
            owner TEXT NOT NULL,
            cutover_ms INTEGER,
            latest_h1_ms INTEGER,
            drained_at_ms INTEGER,
            broker_truth_sha256 TEXT,
            paused_at_ms INTEGER,
            updated_ms INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS att1_decisions (
            account TEXT NOT NULL,
            family TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            h1_close_ms INTEGER NOT NULL,
            owner TEXT NOT NULL,
            order_link_id TEXT NOT NULL,
            reserved_at_ms INTEGER NOT NULL,
            broker_order_id TEXT,
            terminal_at_ms INTEGER,
            costs_complete INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (account, family, symbol, side, h1_close_ms)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS att1_one_occupied_reservation
            ON att1_decisions(account, family) WHERE terminal_at_ms IS NULL;
        CREATE TABLE IF NOT EXISTS att1_symbol_state (
            account TEXT NOT NULL,
            family TEXT NOT NULL,
            symbol TEXT NOT NULL,
            latest_h1_ms INTEGER NOT NULL,
            cooldown_until_ms INTEGER NOT NULL,
            PRIMARY KEY (account, family, symbol)
        );
    '''
    try:
        for statement in schema.split(';'):
            if statement.strip():
                con.execute(statement)
        con.commit()
    except Exception:
        con.rollback()
        raise


def initialize_att1_route(con, account, *, owner='OLD', now_ms):
    account = _require_account(account)
    if owner not in {'OLD'}:
        raise AdapterViolation('invalid initial ATT1 owner')
    if type(now_ms) is not int or now_ms <= 0:
        raise AdapterViolation('invalid route clock')
    init_att1_route_tables(con)
    _begin(con)
    try:
        row = con.execute('SELECT * FROM att1_route WHERE account=?', (account,)).fetchone()
        if row is None:
            con.execute('''INSERT INTO att1_route
                (account,family,owner,cutover_ms,latest_h1_ms,drained_at_ms,
                 broker_truth_sha256,paused_at_ms,updated_ms)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (account, ATT1_FAMILY, owner, None, None, None, None, None, now_ms))
        result = read_att1_route(con, account)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return result


def read_att1_route(con, account):
    account = _require_account(account)
    cursor = con.execute('SELECT * FROM att1_route WHERE account=?', (account,))
    row = cursor.fetchone()
    if row is None:
        raise AdapterViolation('ATT1 route missing')
    return _route_row(dict(zip([d[0] for d in cursor.description], row)))


def pause_att1_route(con, account, now_ms):
    account = _require_account(account)
    if type(now_ms) is not int or now_ms <= 0:
        raise AdapterViolation('invalid pause clock')
    _begin(con)
    try:
        route = read_att1_route(con, account)
        if route['owner'] == 'NEW_READY':
            raise AdapterViolation('cannot resume OLD after NEW_READY')
        if now_ms < route['updated_ms']:
            raise AdapterViolation('pause clock regressed')
        if route['owner'] == 'OLD':
            con.execute('UPDATE att1_route SET owner=?, paused_at_ms=?, updated_ms=? WHERE account=?',
                        ('OLD_PAUSED', now_ms, now_ms, account))
        result = read_att1_route(con, account)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return result


def prepare_att1_cutover(con, account, *, cutover_ms, last_old_h1_ms,
                         drained_at_ms, broker_truth_sha256, now_ms):
    account = _require_account(account)
    vals = (cutover_ms, last_old_h1_ms, drained_at_ms, now_ms)
    if any(type(v) is not int or v <= 0 for v in vals):
        raise AdapterViolation('invalid cutover clock')
    if (not isinstance(broker_truth_sha256, str) or len(broker_truth_sha256) != 64
            or any(c not in '0123456789abcdef' for c in broker_truth_sha256)):
        raise AdapterViolation('invalid broker truth hash')
    if cutover_ms % ATT1_H1_MS or last_old_h1_ms % ATT1_H1_MS:
        raise AdapterViolation('cutover and OLD watermark must be H1 closes')
    _begin(con)
    try:
        route = read_att1_route(con, account)
        if route['owner'] != 'OLD_PAUSED':
            raise AdapterViolation('ATT1 route is not paused')
        if con.execute('''SELECT 1 FROM att1_decisions
                          WHERE account=? AND family=? AND terminal_at_ms IS NULL LIMIT 1''',
                       (account, ATT1_FAMILY)).fetchone():
            raise AdapterViolation('ATT1 reservation still occupied')
        last_terminal = con.execute('''SELECT MAX(terminal_at_ms) FROM att1_decisions
                                       WHERE account=? AND family=?''', (account, ATT1_FAMILY)).fetchone()[0] or 0
        if (last_old_h1_ms < (route['latest_h1_ms'] or 0)
                or not max(route['paused_at_ms'], last_terminal) <= drained_at_ms <= now_ms
                or now_ms < route['updated_ms'] or last_old_h1_ms > drained_at_ms):
            raise AdapterViolation('cutover watermark/drain clock mismatch')
        if cutover_ms <= max(last_old_h1_ms, drained_at_ms, now_ms):
            raise AdapterViolation('cutover must follow OLD watermark and drain')
        con.execute('''UPDATE att1_route SET owner='NEW_READY', cutover_ms=?,
                       latest_h1_ms=?, drained_at_ms=?, broker_truth_sha256=?, updated_ms=?
                       WHERE account=?''',
                    (cutover_ms, last_old_h1_ms, drained_at_ms,
                     broker_truth_sha256, now_ms, account))
        result = read_att1_route(con, account)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return result


def _decision_key(value):
    if isinstance(value, Mapping):
        values = (value.get('account'), value.get('family'), value.get('symbol'),
                  value.get('side'), value.get('h1_close_ms'))
    else:
        values = tuple(value) if isinstance(value, (tuple, list)) else ()
    if len(values) != 5:
        raise AdapterViolation('invalid ATT1 decision key')
    account, family, symbol, side, h1 = values
    account = _require_account(account)
    symbol = _text(symbol, 'symbol').upper()
    side = _text(side, 'side').upper()
    # Frozen ATT1 is short-only. Aliases cannot create distinct decision keys.
    if family != ATT1_FAMILY or side not in {'SELL', 'SHORT'}:
        raise AdapterViolation('invalid ATT1 decision key')
    side = 'SELL'
    if type(h1) is not int or h1 <= 0 or h1 % ATT1_H1_MS:
        raise AdapterViolation('invalid H1 close')
    return account, ATT1_FAMILY, symbol, side, h1


def _stable_link_id(account, symbol, side, h1_close_ms):
    raw = json.dumps([account, ATT1_FAMILY, symbol, side, h1_close_ms], separators=(',', ':'), ensure_ascii=True).encode()
    return 'a1' + hashlib.sha256(raw).hexdigest()[:26]


def _selected_bybit_endpoint_and_key(account_config):
    if not isinstance(account_config, Mapping):
        raise AdapterViolation('selected account config required')
    endpoint = _text(account_config.get('base'), 'account config base').rstrip('/')
    if endpoint != ATT1_BYBIT_PRODUCTION_ENDPOINT:
        raise AdapterViolation('ATT1 account endpoint is not allowlisted')
    return endpoint, _text(account_config.get('key'), 'account config key')


def _positive_int(value, name):
    if isinstance(value, bool):
        raise AdapterViolation('invalid ' + name)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isascii() and value.isdecimal():
        parsed = int(value)
    else:
        raise AdapterViolation('invalid ' + name)
    if parsed <= 0:
        raise AdapterViolation('invalid ' + name)
    return parsed


def validate_old_att1_broker_identity(account_config, query_api_envelope, *, received_ms):
    """Redact and bind a fresh trusted signed ``/v5/user/query-api`` result.

    This function never sends or authenticates a request.  Its caller must use
    the existing trusted Bybit transport and pass the response immediately.
    """
    endpoint, configured_key = _selected_bybit_endpoint_and_key(account_config)
    if type(received_ms) is not int or received_ms <= 0:
        raise AdapterViolation('invalid identity received clock')
    if (not isinstance(query_api_envelope, Mapping)
            or type(query_api_envelope.get('retCode')) is not int
            or query_api_envelope.get('retCode') != 0):
        raise AdapterViolation('broker identity response rejected')
    response_ms = _positive_int(query_api_envelope.get('time'), 'identity response time')
    if response_ms > received_ms or received_ms - response_ms > ATT1_BROKER_IDENTITY_MAX_AGE_MS:
        raise AdapterViolation('broker identity response is stale')
    result = query_api_envelope.get('result')
    if not isinstance(result, Mapping) or result.get('apiKey') != configured_key:
        raise AdapterViolation('broker identity credential mismatch')
    user_id = _positive_int(result.get('userID'), 'broker userID')
    account_raw = json.dumps([endpoint, user_id], separators=(',', ':'), ensure_ascii=True).encode()
    return ValidatedOldAtt1BrokerIdentity(
        account='uid:' + hashlib.sha256(account_raw).hexdigest(),
        endpoint=endpoint,
        credential_binding_sha256=hashlib.sha256(configured_key.encode()).hexdigest(),
        observed_at_ms=received_ms,
    )


def _validated_old_att1_account(account_config, broker_identity, *, now_ms):
    endpoint, configured_key = _selected_bybit_endpoint_and_key(account_config)
    if not isinstance(broker_identity, ValidatedOldAtt1BrokerIdentity):
        raise AdapterViolation('validated broker identity required')
    if (type(broker_identity.observed_at_ms) is not int
            or broker_identity.observed_at_ms <= 0):
        raise AdapterViolation('broker identity clock malformed')
    if (broker_identity.endpoint != endpoint
            or broker_identity.credential_binding_sha256 != hashlib.sha256(configured_key.encode()).hexdigest()):
        raise AdapterViolation('broker identity credential mismatch')
    account = broker_identity.account
    if (not isinstance(account, str) or not account.startswith('uid:') or len(account) != 68
            or any(char not in '0123456789abcdef' for char in account[4:])):
        raise AdapterViolation('broker identity account malformed')
    if (type(now_ms) is not int or now_ms < broker_identity.observed_at_ms
            or now_ms - broker_identity.observed_at_ms > ATT1_BROKER_IDENTITY_MAX_AGE_MS):
        raise AdapterViolation('broker identity is stale')
    return account


def att1_account_config_fingerprint(account_config):
    """Legacy opaque ledger ID from the selected loaded Bybit config.

    Existing ``cfg:`` rows are intentionally not migrated: opt-in dispatch now
    requires ``ValidatedOldAtt1BrokerIdentity`` and uses a broker user ID.
    """
    if not isinstance(account_config, Mapping):
        raise AdapterViolation('selected account config required')
    name = _text(account_config.get('name'), 'account config name')
    key = _text(account_config.get('key'), 'account config key')
    base = _text(account_config.get('base'), 'account config base').rstrip('/')
    if not base.startswith(('https://', 'http://')):
        raise AdapterViolation('invalid account config base')
    raw = json.dumps([name, key, base], separators=(',', ':'), ensure_ascii=True).encode()
    return 'cfg:' + hashlib.sha256(raw).hexdigest()


def _consumed_h1_close_ms(rows):
    """Return the close of the exact final closed H1 row used by ATT1."""
    if not isinstance(rows, (list, tuple)) or not rows:
        raise AdapterViolation('consumed H1 rows required')
    starts = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or not row:
            raise AdapterViolation('malformed consumed H1 row')
        raw = row[0]
        if isinstance(raw, bool) or not isinstance(raw, (int, str)):
            raise AdapterViolation('invalid consumed H1 timestamp')
        try:
            start = int(raw)
        except (TypeError, ValueError) as exc:
            raise AdapterViolation('invalid consumed H1 timestamp') from exc
        if start <= 0:
            raise AdapterViolation('invalid consumed H1 timestamp')
        # The existing Bybit adapter accepts seconds or milliseconds.  Preserve
        # that exact normalisation here, then require a real H1 boundary.
        if start <= 10**11:
            start *= 1000
        if start % ATT1_H1_MS:
            raise AdapterViolation('consumed H1 timestamp is not an H1 boundary')
        starts.append(start)
    if any(left >= right for left, right in zip(starts, starts[1:])):
        raise AdapterViolation('consumed H1 rows are not strictly ordered')
    return starts[-1] + ATT1_H1_MS


def reserve_old_att1_dispatch(db_path, account_config, *, symbol, side,
                              consumed_h1_rows, now_ms, enabled,
                              broker_identity=None):
    """Default-off durable OLD dispatch reservation in the existing SQLite DB.

    With ``enabled=False`` this returns before opening SQLite, so a normal OLD
    process creates no route table or other ledger state.  With opt-in it
    reserves before a broker send.  No submit failure, exception, or timeout
    may release that reservation; authenticated recovery owns finalisation.
    """
    if enabled is False:
        return None
    if enabled is not True:
        raise AdapterViolation('ATT1 dispatch binding flag must be bool')
    account = _validated_old_att1_account(
        account_config, broker_identity, now_ms=now_ms,
    )
    h1_close_ms = _consumed_h1_close_ms(consumed_h1_rows)
    if type(now_ms) is not int or now_ms < h1_close_ms:
        raise AdapterViolation('dispatch clock precedes consumed H1 close')
    with sqlite3.connect(db_path) as con:
        init_att1_route_tables(con)
        if con.execute('SELECT 1 FROM att1_route WHERE account=?', (account,)).fetchone() is None:
            legacy = con.execute('''SELECT 1 FROM att1_route WHERE account LIKE 'cfg:%'
                                    UNION ALL
                                    SELECT 1 FROM att1_decisions WHERE account LIKE 'cfg:%'
                                    LIMIT 1''').fetchone()
            if legacy is not None:
                raise AdapterViolation('legacy cfg ATT1 ledger blocks UID route creation')
        initialize_att1_route(con, account, now_ms=now_ms)
        return reserve_att1_decision(
            con, account, owner='OLD', symbol=symbol, side=side,
            h1_close_ms=h1_close_ms, now_ms=now_ms,
        )


def bind_old_att1_dispatch_ack(db_path, decision_key, broker_order_id):
    """Persist an OLD broker ACK without treating it as fill/finality.

    Exact ACK re-delivery is idempotent.  A conflicting order identity is a
    fail-closed violation and the occupied reservation remains in place.
    """
    key = _decision_key(decision_key)
    with sqlite3.connect(db_path) as con:
        return bind_att1_order(con, key[0], key, broker_order_id)


def read_unresolved_old_att1_dispatches(db_path, account_config, *, broker_identity, now_ms):
    """Read pre-ACK OLD intents without creating or modifying the trade DB."""
    account = _validated_old_att1_account(
        account_config, broker_identity, now_ms=now_ms,
    )
    try:
        uri = Path(db_path).expanduser().resolve().as_uri() + '?mode=ro'
        con = sqlite3.connect(uri, uri=True)
    except (OSError, sqlite3.Error) as exc:
        raise AdapterViolation('ATT1 recovery ledger unavailable') from exc
    try:
        read_att1_route(con, account)  # validates the existing route; never initializes it.
        rows = con.execute('''SELECT account,family,symbol,side,h1_close_ms,
                                      order_link_id,owner,reserved_at_ms
                               FROM att1_decisions
                               WHERE account=? AND family=? AND owner='OLD'
                                 AND broker_order_id IS NULL AND terminal_at_ms IS NULL
                               ORDER BY reserved_at_ms,h1_close_ms''',
                           (account, ATT1_FAMILY)).fetchall()
    except sqlite3.Error as exc:
        raise AdapterViolation('ATT1 recovery ledger malformed') from exc
    finally:
        con.close()
    keys = ('account', 'family', 'symbol', 'side', 'h1_close_ms',
            'order_link_id', 'owner', 'reserved_at_ms')
    return [dict(zip(keys, row)) for row in rows]


def validate_old_att1_ack_lookup(account_config, decision_key, order, *, broker_identity, now_ms):
    """Accept an order-link lookup only for the configured account's exact OLD intent."""
    account = _validated_old_att1_account(
        account_config, broker_identity, now_ms=now_ms,
    )
    key = _decision_key(decision_key)
    if account != key[0]:
        raise AdapterViolation('lookup account does not own ATT1 decision')
    if not isinstance(decision_key, Mapping) or decision_key.get('owner') != 'OLD':
        raise AdapterViolation('lookup is not an OLD ATT1 decision')
    link_id = _text(decision_key.get('order_link_id'), 'order_link_id')
    if not isinstance(order, Mapping):
        raise AdapterViolation('broker order lookup malformed')
    if order.get('symbol') != key[2] or order.get('side') != 'Sell':
        raise AdapterViolation('foreign broker order lookup')
    if order.get('orderLinkId') != link_id:
        raise AdapterViolation('broker order link mismatch')
    if order.get('category') not in (None, 'linear'):
        raise AdapterViolation('broker order category mismatch')
    return _text(order.get('orderId'), 'broker_order_id')


def reserve_att1_decision(con, account, *, owner, symbol, side, h1_close_ms, now_ms):
    account, _, symbol, side, h1_close_ms = _decision_key(
        (account, ATT1_FAMILY, symbol, side, h1_close_ms))
    if owner not in {'OLD', 'NEW'} or type(now_ms) is not int or now_ms < h1_close_ms:
        raise AdapterViolation('invalid ATT1 reservation input')
    link_id = _stable_link_id(account, symbol, side, h1_close_ms)
    _begin(con)
    try:
        route = read_att1_route(con, account)
        if (owner == 'OLD' and route['owner'] != 'OLD') or (owner == 'NEW' and route['owner'] != 'NEW_READY'):
            raise AdapterViolation('ATT1 route owner mismatch')
        if now_ms < route['updated_ms']:
            raise AdapterViolation('reservation clock regressed')
        if owner == 'NEW' and h1_close_ms < route['cutover_ms']:
            raise AdapterViolation('NEW decision is before cutover')
        state = con.execute('''SELECT latest_h1_ms,cooldown_until_ms FROM att1_symbol_state
                               WHERE account=? AND family=? AND symbol=?''',
                            (account, ATT1_FAMILY, symbol)).fetchone()
        if state and (h1_close_ms <= int(state[0]) or h1_close_ms < int(state[1])):
            raise AdapterViolation('ATT1 symbol H1 cooldown/watermark blocks decision')
        con.execute('''INSERT INTO att1_decisions
            (account,family,symbol,side,h1_close_ms,owner,order_link_id,reserved_at_ms)
            VALUES (?,?,?,?,?,?,?,?)''',
            (account, ATT1_FAMILY, symbol, side, h1_close_ms, owner, link_id, now_ms))
        con.execute('''INSERT INTO att1_symbol_state
            (account,family,symbol,latest_h1_ms,cooldown_until_ms) VALUES (?,?,?,?,?)
            ON CONFLICT(account,family,symbol) DO UPDATE SET latest_h1_ms=excluded.latest_h1_ms,
            cooldown_until_ms=excluded.cooldown_until_ms''',
            (account, ATT1_FAMILY, symbol, h1_close_ms, h1_close_ms + ATT1_COOLDOWN_MS))
        con.execute('UPDATE att1_route SET latest_h1_ms=MAX(COALESCE(latest_h1_ms,0),?),updated_ms=? WHERE account=?',
                    (h1_close_ms, now_ms, account))
        con.commit()
    except sqlite3.IntegrityError as exc:
        con.rollback()
        raise AdapterViolation('ATT1 decision duplicate or account slot occupied') from exc
    except Exception:
        con.rollback()
        raise
    return {'account': account, 'family': ATT1_FAMILY, 'symbol': symbol,
            'side': side, 'h1_close_ms': h1_close_ms, 'order_link_id': link_id,
            'owner': owner, 'reserved_at_ms': now_ms}


def bind_att1_order(con, account, decision_key, broker_order_id):
    key = _decision_key(decision_key)
    if _require_account(account) != key[0]:
        raise AdapterViolation('decision account mismatch')
    broker_order_id = _text(broker_order_id, 'broker_order_id')
    where = 'account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?'
    _begin(con)
    try:
        row = con.execute(f'SELECT broker_order_id,terminal_at_ms FROM att1_decisions WHERE {where}', key).fetchone()
        if row is None:
            raise AdapterViolation('ATT1 decision missing')
        if row[0] is not None and row[0] != broker_order_id:
            raise AdapterViolation('conflicting broker order identity')
        if row[0] is None:
            if row[1] is not None:
                raise AdapterViolation('cannot bind new identity after finality')
            con.execute(f'UPDATE att1_decisions SET broker_order_id=? WHERE {where}', (broker_order_id, *key))
        con.commit()
    except Exception:
        con.rollback()
        raise
    return broker_order_id


def finalize_att1_reservation(con, account, decision_key, *, flat, order_final,
                              costs_complete, now_ms):
    key = _decision_key(decision_key)
    if _require_account(account) != key[0]:
        raise AdapterViolation('decision account mismatch')
    if type(flat) is not bool or type(order_final) is not bool or type(costs_complete) is not bool:
        raise AdapterViolation('finality flags must be bool')
    if not (flat and order_final and costs_complete):
        raise AdapterViolation('ATT1 reservation remains occupied until complete finality/costs')
    if type(now_ms) is not int or now_ms <= 0:
        raise AdapterViolation('invalid finality clock')
    where = 'account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?'
    _begin(con)
    try:
        row = con.execute(f'SELECT reserved_at_ms FROM att1_decisions WHERE {where}', key).fetchone()
        if row is None:
            raise AdapterViolation('ATT1 decision missing')
        if now_ms < row[0]:
            raise AdapterViolation('finality clock precedes reservation')
        con.execute(f'''UPDATE att1_decisions SET terminal_at_ms=?, costs_complete=1
                        WHERE {where} AND terminal_at_ms IS NULL''', (now_ms, *key))
        con.commit()
    except Exception:
        con.rollback()
        raise
    return True


def _text(value, name):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise AdapterViolation('missing/invalid ' + name)
    return value


def _number(value, name, **kw):
    try:
        return _decimal(value, name, **kw)
    except AccountingViolation as exc:
        raise AdapterViolation(str(exc)) from exc


def _event(row, kind, identity, exchange_text, received_ms, fields):
    if not isinstance(exchange_text, str) or not exchange_text.isascii() or not exchange_text.isdigit() or len(exchange_text)>16:
        raise AdapterViolation('invalid broker timestamp')
    ex = int(exchange_text)
    if type(received_ms) is not int or not 0 < ex <= received_ms:
        raise AdapterViolation('invalid receive clock')
    source = digest(row)
    return {'schema_id':'att1_lifecycle_event_v1','event_id':'bybit:'+kind+':'+identity+':'+str(received_ms),
            'kind':kind,'exchange_ms':ex,'received_ms':received_ms,'source_sha256':source,**fields}


def map_execution(row, *, symbol, expected_order_id, expected_order_link_id,
                  kind, received_ms, exit_order_id=None):
    """Map Trade only. Funding execFee has a different sign and is refused."""
    if not isinstance(row, Mapping) or kind not in {'ENTRY_FILL','EXIT_FILL'}:
        raise AdapterViolation('invalid execution input/kind')
    for name, expected in (('symbol',symbol),('orderId',expected_order_id),('orderLinkId',expected_order_link_id)):
        _text(expected,name)
        if row.get(name) != expected:
            raise AdapterViolation('foreign ' + name)
    if row.get('execType') != 'Trade' or row.get('side') != ('Sell' if kind=='ENTRY_FILL' else 'Buy'):
        raise AdapterViolation('unsupported execution type/side')
    if row.get('feeCurrency') != 'USDT' or row.get('extraFees') != '':
        raise AdapterViolation('unmapped fee currency/extraFees')
    if type(row.get('isMaker')) is not bool:
        raise AdapterViolation('invalid liquidity')
    qty = _number(row.get('execQty'),'execQty',positive=True)
    _number(row.get('execPrice'),'execPrice',positive=True)
    # Missing fee stays unknown, never zero-filled by the adapter.
    fee = row.get('execFee')
    if fee is not None: _number(fee,'execFee')
    closed = _number(row.get('closedSize'),'closedSize',nonnegative=True)
    if closed != (0 if kind=='ENTRY_FILL' else qty):
        raise AdapterViolation('execution exposure direction mismatch')
    fields = {'execution_id':_text(row.get('execId'),'execId'), 'qty':row['execQty'],
              'price':row['execPrice'],'fee_amount':fee,'fee_source_sha256':digest(row),
              'liquidity':'MAKER' if row['isMaker'] else 'TAKER'}
    if kind == 'EXIT_FILL': fields['exit_order_id'] = _text(exit_order_id,'exit_order_id')
    elif exit_order_id is not None: raise AdapterViolation('exit identity on entry')
    return _event(row,kind,fields['execution_id'],row.get('execTime'),received_ms,fields)


def map_funding(row, *, symbol, received_ms):
    """UTA linear-USDT SETTLEMENT funding is signed cash: receive +, pay -.

    Require the transaction cash equation and unambiguous short quantity. Never
    derive an effective mark/rate to make a proxy equal broker-rounded cash.
    """
    if not isinstance(row, Mapping): raise AdapterViolation('invalid funding input')
    for key,value in (('symbol',symbol),('category','linear'),('currency','USDT'),
                      ('type','SETTLEMENT'),('side','Sell')):
        if row.get(key) != value: raise AdapterViolation('funding ' + key)
    for name in ('extraFees','transSubType'):
        if row.get(name) != '': raise AdapterViolation('unmapped funding ' + name)
    bonus = row.get('bonusChange')
    if bonus != '' and _number(bonus,'bonusChange') != 0:
        raise AdapterViolation('unmapped funding bonus')
    qty = _number(row.get('qty'),'funding qty',positive=True)
    if _number(row.get('size'),'funding size') != -qty:
        raise AdapterViolation('ambiguous funding quantity')
    amount = _number(row.get('funding'),'funding')
    if (_number(row.get('cashFlow'),'cashFlow') != 0 or _number(row.get('fee'),'fee') != 0
            or _number(row.get('change'),'change') != amount):
        raise AdapterViolation('funding cash reconciliation mismatch')
    identity = _text(row.get('id'),'settlement id')
    event = _event(row,'FUNDING_CASH',identity,row.get('transactionTime'),received_ms,
                  {'settlement_id':identity,'qty_at_settlement':row['qty'],
                   'cash_amount':row['funding'],'currency':'USDT'})
    event['settlement_ms'] = event['exchange_ms']
    return event


def _broker_receipt(receipt):
    if not isinstance(receipt, Mapping) or receipt.get('plan',{}).get('profile_id') != 'BROKER_REPLAY_ATT1_V1':
        raise AdapterViolation('broker replay receipt required')
    return receipt['plan']


def map_order_final(row, *, receipt, expected_order_id, expected_order_link_id,
                    received_ms, entry):
    """Terminal order evidence only, after executions have been reconciled."""
    p = _broker_receipt(receipt)
    if not isinstance(row, Mapping) or type(entry) is not bool:
        raise AdapterViolation('invalid order input')
    for name,expected in (('symbol',p['symbol']),('orderId',expected_order_id),
                          ('orderLinkId',expected_order_link_id)):
        _text(expected,name)
        if row.get(name) != expected: raise AdapterViolation('foreign order ' + name)
    if (type(row.get('positionIdx')) is not int or row['positionIdx'] != 0
            or row.get('side') != ('Sell' if entry else 'Buy')
            or row.get('reduceOnly') is not (not entry)):
        raise AdapterViolation('order direction/mode mismatch')
    statuses = {'Filled':'FILLED','Cancelled':'CANCELLED','Rejected':'REJECTED',
                'PartiallyFilledCanceled':'CANCELLED'}
    status = statuses.get(row.get('orderStatus'))
    if status is None: raise AdapterViolation('order finality not confirmed')
    if entry:
        requested = _number(p['requested_qty'],'requested_qty',positive=True)
        filled = Fraction(receipt['accounting']['aggregate_entry_qty'])
    else:
        pending = receipt.get('pending_exit')
        if pending is None: raise AdapterViolation('no coordinator exit intent')
        requested = Fraction(pending['qty'])
        filled = requested - Fraction(pending['remaining_qty'])
    if _number(row.get('qty'),'order qty',positive=True) != requested:
        raise AdapterViolation('order quantity mismatch')
    if _number(row.get('cumExecQty'),'cumExecQty',nonnegative=True) != filled:
        raise AdapterViolation('unreconciled order executions')
    if (status=='FILLED' and filled != requested) or (status=='REJECTED' and filled != 0):
        raise AdapterViolation('inconsistent order finality')
    fields = {'status':status}
    if not entry: fields['exit_order_id'] = pending['exit_order_id']
    return _event(row,'ENTRY_FINAL' if entry else 'EXIT_FINAL',expected_order_id,
                  row.get('updatedTime'),received_ms,fields)


def map_protection(position, stop_order, *, receipt, received_ms):
    """Prove exact full-position stop from position AND live conditional order."""
    p = _broker_receipt(receipt)
    if not isinstance(position,Mapping) or not isinstance(stop_order,Mapping):
        raise AdapterViolation('missing protection evidence')
    held = Fraction(receipt['held_qty'])
    if held <= 0: raise AdapterViolation('no exposure to protect')
    for row in (position,stop_order):
        if row.get('symbol') != p['symbol'] or type(row.get('positionIdx')) is not int or row['positionIdx'] != 0:
            raise AdapterViolation('protection symbol/mode mismatch')
    if (position.get('side')!='Sell' or _number(position.get('size'),'position size',positive=True)!=held
            or _number(position.get('stopLoss'),'stopLoss',positive=True)!=Fraction(p['original_stop'])):
        raise AdapterViolation('position protection mismatch')
    if (stop_order.get('side')!='Buy' or stop_order.get('orderStatus')!='Untriggered'
            or stop_order.get('stopOrderType')!='StopLoss' or stop_order.get('reduceOnly') is not True
            or stop_order.get('closeOnTrigger') is not True
            or _number(stop_order.get('qty'),'stop qty',positive=True)!=held
            or _number(stop_order.get('triggerPrice'),'triggerPrice',positive=True)!=Fraction(p['original_stop'])):
        raise AdapterViolation('conditional stop not proven')
    identity = _text(stop_order.get('orderId'),'stop orderId')
    # Validate both clocks independently before taking their latest timestamp.
    events = [_event(row,'PROTECTION_ACK',identity,row.get('updatedTime'),received_ms,{})
              for row in (position,stop_order)]
    from research_lab.att1_lifecycle_profile import _decimal_text
    result = _event({'position':position,'stop_order':stop_order},'PROTECTION_ACK',identity,
                   str(max(e['exchange_ms'] for e in events)),received_ms,
                   {'qty':_decimal_text(held),'stop':p['original_stop']})
    return result
