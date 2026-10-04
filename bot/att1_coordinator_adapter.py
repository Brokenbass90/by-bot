"""Bybit evidence -> existing ATT1 event contract. No order-send API.

Pure mappers validate broker-shaped records, not their authenticity.
Explicit GET-only collectors below pin account truth and reuse the existing
journal/reservation; none runs a background service or submits an order.
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
    fresh = row.get('fresh_epoch_json')
    kind = row.get('handoff_kind')
    if kind not in (None, 'FRESH_EPOCH_V1') or (kind == 'FRESH_EPOCH_V1') != (fresh is not None):
        raise AdapterViolation('fresh route declaration missing/invalid')
    if fresh is not None:
        from bot.att1_canary_preparation import validate_canary_fresh_handoff
        try:
            epoch = json.loads(fresh)
            proof = validate_canary_fresh_handoff(**epoch['inputs'])
            if (set(epoch) != {'inputs','declaration_sha256','handoff_sha256'}
                    or proof['declaration_sha256'] != epoch['declaration_sha256']
                    or proof['handoff_sha256'] != epoch['handoff_sha256']
                    or row['owner'] != 'NEW_READY'
                    or row['updated_ms'] < epoch['inputs']['now_ms']
                    or row['cutover_ms'] != proof['minimum_cutover_ms']
                    or row['drained_at_ms'] != proof['drained_at_ms']
                    or row['broker_truth_sha256'] != epoch['inputs']['broker_snapshot']['source_sha256']):
                raise AdapterViolation('fresh route provenance malformed')
        except (ValueError, KeyError, TypeError) as exc:
            raise AdapterViolation('fresh route provenance malformed') from exc
    if row['owner'] == 'NEW_READY' and (
        any(row[k] is None for k in ('cutover_ms', 'drained_at_ms', 'broker_truth_sha256'))
        or (not fresh and row['latest_h1_ms'] is None)
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
        additions = {
            'att1_decisions': {'risk_reserve_usdt': 'TEXT', 'cost_reserve_usdt': 'TEXT',
                'budget_day_utc': 'TEXT', 'budget_evidence_sha256': 'TEXT',
                'execution_binding_sha256': 'TEXT', 'command_sha256': 'TEXT', 'preparation_json': 'TEXT',
                'terminal_evidence_sha256': 'TEXT'},
            'att1_route': {'budget_day_utc': 'TEXT', 'spent_debits_usdt': 'TEXT',
                'cash_coverage_sha256': 'TEXT', 'cash_finality_frontier_ms': 'INTEGER',
                'cash_event_fingerprints_json': 'TEXT', 'risk_cap_usdt': 'TEXT', 'notional_cap_usdt': 'TEXT',
                'fresh_epoch_json': 'TEXT', 'handoff_kind': 'TEXT'},
        }
        for table, fields in additions.items():
            present = {row[1] for row in con.execute(f'PRAGMA table_info({table})')}
            for name, kind in fields.items():
                if name not in present:
                    con.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
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


def prepare_att1_fresh_cutover(con, account, **inputs):
    """Persist the accepted cold declaration in the existing orders-OFF ledger.

    This does not retire OLD in the runtime, connect to a broker or enable NEW.
    Its caller must supply authenticated retirement/finality/bar provenance.
    """
    from bot.att1_canary_preparation import validate_canary_fresh_handoff
    account = _require_account(account)
    proof = validate_canary_fresh_handoff(**inputs)
    if proof['account'] != account:
        raise AdapterViolation('fresh cutover account mismatch')
    now, retired = inputs['now_ms'], inputs['declaration']['retired_at_ms']
    _begin(con)
    try:
        route = read_att1_route(con, account)
        if (route['owner'] != 'OLD_PAUSED' or route.get('fresh_epoch_json') is not None
                or not route['paused_at_ms'] <= retired <= proof['drained_at_ms']
                or now < route['updated_ms']
                or (route['latest_h1_ms'] or 0) > proof['fence_h1_ms']):
            raise AdapterViolation('fresh cutover retirement/route mismatch')
        if con.execute('''SELECT 1 FROM att1_decisions WHERE account=? AND family=?
                AND (terminal_at_ms IS NULL OR costs_complete!=1 OR terminal_at_ms>?) LIMIT 1''',
                (account, ATT1_FAMILY, proof['drained_at_ms'])).fetchone():
            raise AdapterViolation('fresh cutover has unresolved reservations/costs')
        epoch = {'inputs':inputs, 'declaration_sha256':proof['declaration_sha256'],
                 'handoff_sha256':proof['handoff_sha256']}
        con.execute('''UPDATE att1_route SET owner='NEW_READY',handoff_kind='FRESH_EPOCH_V1',cutover_ms=?,drained_at_ms=?,
                       broker_truth_sha256=?,updated_ms=?,fresh_epoch_json=? WHERE account=?''',
            (proof['minimum_cutover_ms'],proof['drained_at_ms'],
             inputs['broker_snapshot']['source_sha256'],now,
             json.dumps(epoch,sort_keys=True,separators=(',',':')),account))
        result = read_att1_route(con, account)
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise


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


def att1_broker_account_fingerprint(account):
    """Opaque UID binding for an offline BROKER_REPLAY lifecycle journal."""
    return digest({'schema_id': 'att1_broker_replay_account_binding_v1',
                   'family': ATT1_FAMILY, 'account': _require_account(account)})


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


def validate_att1_broker_snapshot(account_config, broker_identity, *,
                                  position_pages, order_pages, observed_ms):
    """Validate complete current USDT-linear truth from the trusted transport.

    These endpoints are not an atomic account snapshot or trade finality.
    A flat result cannot release a durable unresolved reservation. Raw pages
    have no account UID: the caller must pin the signed client/identity across
    collection. The digest is evidence identity, never money authority.
    """
    account = _validated_old_att1_account(account_config, broker_identity, now_ms=observed_ms)
    counts = []
    for kind, pages in (('positions', position_pages), ('orders', order_pages)):
        if not isinstance(pages, list) or not 1 <= len(pages) <= 16:
            raise AdapterViolation('incomplete/bounded broker pagination required')
        cursors, entities, count = set(), set(), 0
        for index, page in enumerate(pages):
            if (not isinstance(page, Mapping) or type(page.get('retCode')) is not int
                    or page['retCode'] != 0 or type(page.get('time')) is not int
                    or not 0 < page['time'] <= observed_ms
                    or observed_ms - page['time'] > ATT1_BROKER_IDENTITY_MAX_AGE_MS):
                raise AdapterViolation('invalid/stale broker snapshot envelope')
            result = page.get('result')
            if (not isinstance(result, Mapping) or result.get('category') != 'linear'
                    or not isinstance(result.get('list'), list)
                    or not isinstance(result.get('nextPageCursor'), str)):
                raise AdapterViolation('broker snapshot result malformed')
            cursor = result['nextPageCursor']
            if ((index == len(pages) - 1) != (cursor == '')
                    or (cursor and cursor in cursors)):
                raise AdapterViolation('incomplete/cyclic broker pagination')
            cursors.add(cursor)
            for row in result['list']:
                if not isinstance(row, Mapping):
                    raise AdapterViolation('broker snapshot row malformed')
                symbol = _text(row.get('symbol'), 'symbol')
                if not symbol.endswith('USDT'):
                    raise AdapterViolation('foreign settlement in broker snapshot')
                if kind == 'positions':
                    size = _number(row.get('size'), 'size', nonnegative=True)
                    idx, side = row.get('positionIdx'), row.get('side')
                    if (type(idx) is not int or idx not in (0, 1, 2)
                            or side not in ('', 'Buy', 'Sell') or (size > 0 and not side)):
                        raise AdapterViolation('broker position malformed')
                    key = (symbol, idx)
                    count += int(size > 0)
                else:
                    key = _text(row.get('orderId'), 'orderId')
                    qty = _number(row.get('qty'), 'qty', positive=True)
                    filled = _number(row.get('cumExecQty'), 'cumExecQty', nonnegative=True)
                    if (filled > qty or row.get('side') not in ('Buy', 'Sell')
                            or row.get('orderStatus') not in ('New', 'PartiallyFilled', 'Untriggered', 'Triggered')):
                        raise AdapterViolation('broker active order malformed')
                    count += 1
                if key in entities:
                    raise AdapterViolation('duplicate broker snapshot entity')
                entities.add(key)
        counts.append(count)
    return {'schema_id': 'att1_broker_snapshot_v1', 'account': account,
            'observed_ms': observed_ms, 'position_count': counts[0], 'order_count': counts[1],
            'flat_no_orders': counts == [0, 0],
            'source_sha256': digest({'position_pages': position_pages, 'order_pages': order_pages})}


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


def _reserve_att1_decision_tx(con, account, *, owner, symbol, side, h1_close_ms, now_ms,
                             budget_authorized=False):
    account, _, symbol, side, h1_close_ms = _decision_key(
        (account, ATT1_FAMILY, symbol, side, h1_close_ms))
    if owner not in {'OLD', 'NEW'} or type(now_ms) is not int or now_ms < h1_close_ms:
        raise AdapterViolation('invalid ATT1 reservation input')
    link_id = _stable_link_id(account, symbol, side, h1_close_ms)
    route = read_att1_route(con, account)
    if owner == 'NEW' and (route.get('risk_cap_usdt') is not None or route.get('fresh_epoch_json')) and not budget_authorized:
        raise AdapterViolation('NEW cash-aware budget reservation required')
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
    return {'account': account, 'family': ATT1_FAMILY, 'symbol': symbol,
            'side': side, 'h1_close_ms': h1_close_ms, 'order_link_id': link_id,
            'owner': owner, 'reserved_at_ms': now_ms}


def reserve_att1_decision(con, account, *, owner, symbol, side, h1_close_ms, now_ms):
    _begin(con)
    try:
        result = _reserve_att1_decision_tx(con, account, owner=owner, symbol=symbol,
            side=side, h1_close_ms=h1_close_ms, now_ms=now_ms)
        con.commit()
        return result
    except sqlite3.IntegrityError as exc:
        con.rollback()
        raise AdapterViolation('ATT1 decision duplicate or account slot occupied') from exc
    except Exception:
        con.rollback()
        raise


def _apply_canary_cash_tx(con, account, validated_budget, now_ms):
    from bot.att1_canary_preparation import _revalidate
    from research_lab.att1_lifecycle_profile import _decimal_text
    v = _revalidate(validated_budget)
    route = read_att1_route(con, account)
    if (v['binding']['account_fingerprint_sha256'] != att1_broker_account_fingerprint(account)
            or v['now_ms'] != now_ms or now_ms < route['updated_ms']):
        raise AdapterViolation('canary cash account/clock mismatch')
    old_day = route.get('budget_day_utc')
    old_r = route.get('risk_cap_usdt')
    old_n = route.get('notional_cap_usdt')
    if old_r is not None and (_number(old_r, 'fixed risk') != _number(v['binding']['absolute_risk_cap'], 'fixed risk')
            or _number(v['binding']['max_notional'], 'notional') > _number(old_n, 'fixed notional')):
        raise AdapterViolation('fixed canary cash caps changed')
    frontier = route.get('cash_finality_frontier_ms') or 0
    if v['cash_evidence']['observed_ms'] < frontier:
        raise AdapterViolation('cash finality frontier not covered')
    if old_day is not None and v['day_utc'] < old_day:
        raise AdapterViolation('cash day clock regressed')
    fingerprints = {row['source_id']: digest({k:x for k,x in row.items() if k!='received_ms'})
                    for row in v['cash_evidence']['events']}
    prior = json.loads(route.get('cash_event_fingerprints_json') or '{}')
    spent = _number(v['spent_usdt'], 'spent cash', nonnegative=True)
    if old_day == v['day_utc']:
        if any(fingerprints.get(k) != value for k, value in prior.items()):
            raise AdapterViolation('cash coverage omits/conflicts with prior source identities')
        if spent < _number(route.get('spent_debits_usdt') or '0', 'prior spent'):
            raise AdapterViolation('cash spent projection regressed')
    elif old_day is not None and frontier:
        if v['cash_evidence'].get('prior_day_coverage_sha256') != route['cash_coverage_sha256']:
            raise AdapterViolation('prior-day cash finality coverage required')
    con.execute('''UPDATE att1_route SET budget_day_utc=?,spent_debits_usdt=?,
        cash_coverage_sha256=?,cash_event_fingerprints_json=?,risk_cap_usdt=?,notional_cap_usdt=?
        WHERE account=?''', (v['day_utc'], _decimal_text(spent), v['cash_coverage_sha256'],
        json.dumps(fingerprints,sort_keys=True,separators=(',',':')),
        old_r or v['binding']['absolute_risk_cap'], old_n or v['binding']['max_notional'], account))
    return v


def reserve_new_att1_preparation(con, account, *, symbol, side, h1_close_ms, now_ms,
                                validated_budget, proposed_risk_usdt, proposed_cost_reserve_usdt):
    from bot.att1_canary_preparation import project_att1_daily_budget, preparation_implementation_hash
    from research_lab.att1_lifecycle_profile import _decimal_text
    account, _, symbol, side, h1_close_ms = _decision_key((account,ATT1_FAMILY,symbol,side,h1_close_ms))
    _begin(con)
    try:
        v = _apply_canary_cash_tx(con, account, validated_budget, now_ms)
        if not v.get('handoff_binding'):
            raise AdapterViolation('complete handoff required for cash-aware reservation')
        attachment = v.get('command_binding')
        if not isinstance(attachment, Mapping):
            raise AdapterViolation('admitted command reserve binding required')
        cmd = attachment['command']
        if (cmd['symbol'] != symbol or cmd['side'].upper() != side or cmd['h1_close_ms'] != h1_close_ms
                or cmd['orderLinkId'] != _stable_link_id(account,symbol,side,h1_close_ms)):
            raise AdapterViolation('command decision identity mismatch')
        risk = _number(proposed_risk_usdt, 'proposed reserve risk', positive=True)
        costs = _number(proposed_cost_reserve_usdt, 'proposed reserve costs', nonnegative=True)
        if (risk < _number(attachment['required_risk_usdt'], 'command risk')
                or costs < _number(attachment['required_cost_reserve_usdt'], 'command costs')):
            raise AdapterViolation('command reserves understated')
        rows = con.execute('''SELECT risk_reserve_usdt,cost_reserve_usdt FROM att1_decisions
                              WHERE account=? AND family=? AND terminal_at_ms IS NULL''',
                           (account,ATT1_FAMILY)).fetchall()
        occupied = [dict(zip(('risk_reserve_usdt','cost_reserve_usdt'), row)) for row in rows]
        budget = project_att1_daily_budget(v,occupied,proposed_risk_usdt=proposed_risk_usdt,
                                            proposed_cost_reserve_usdt=proposed_cost_reserve_usdt)
        if not budget['admitted']:
            raise AdapterViolation('canary budget blocked: '+budget['reason'])
        handoff = v.get('handoff_binding', {}).get('result')
        if handoff:
            route = read_att1_route(con,account)
            from bot.att1_canary_preparation import validate_fresh_route_handoff
            validate_fresh_route_handoff(route, handoff)
            if (handoff['account'] != account or route['owner'] != 'NEW_READY'
                    or route['cutover_ms'] < handoff['minimum_cutover_ms']):
                raise AdapterViolation('NEW route/drain cutover mismatch')
            for state in handoff['symbols']:
                con.execute('''INSERT INTO att1_symbol_state
                    (account,family,symbol,latest_h1_ms,cooldown_until_ms) VALUES (?,?,?,?,?)
                    ON CONFLICT(account,family,symbol) DO UPDATE SET
                    latest_h1_ms=MAX(latest_h1_ms,excluded.latest_h1_ms),
                    cooldown_until_ms=MAX(cooldown_until_ms,excluded.cooldown_until_ms)''',
                    (account,ATT1_FAMILY,state['symbol'],state['latest_h1_ms'],state['cooldown_until_ms']))
        result = _reserve_att1_decision_tx(con,account,owner='NEW',symbol=symbol,side=side,
            h1_close_ms=h1_close_ms,now_ms=now_ms,budget_authorized=True)
        key = (account,ATT1_FAMILY,symbol,side,h1_close_ms)
        con.execute('''UPDATE att1_decisions SET risk_reserve_usdt=?,cost_reserve_usdt=?,
            budget_day_utc=?,budget_evidence_sha256=?,execution_binding_sha256=?,command_sha256=?,preparation_json=?
            WHERE account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?''',
            (_decimal_text(risk),_decimal_text(costs),v['day_utc'],v['validation_sha256'],
             v['binding_sha256'],attachment['command_sha256'],
             json.dumps({**attachment,'implementation_sha256':preparation_implementation_hash(),
                         'handoff_sha256':handoff['handoff_sha256'] if handoff else None},
                         sort_keys=True,separators=(',',':')),*key))
        con.commit()
        result.update(orders_allowed=False,budget=budget,command_sha256=attachment['command_sha256'])
        return result
    except sqlite3.IntegrityError as exc:
        con.rollback()
        raise AdapterViolation('ATT1 decision duplicate or account slot occupied') from exc
    except Exception:
        con.rollback()
        raise


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
                              costs_complete, now_ms, validated_budget=None, lifecycle_session=None):
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
        row = con.execute(f'''SELECT reserved_at_ms,command_sha256,terminal_at_ms,
            execution_binding_sha256,preparation_json FROM att1_decisions WHERE {where}''', key).fetchone()
        if row is None:
            raise AdapterViolation('ATT1 decision missing')
        if now_ms < row[0]:
            raise AdapterViolation('finality clock precedes reservation')
        if row[1] is not None and row[2] is None:
            if validated_budget is None:
                raise AdapterViolation('budget-bound cash finality required')
            _validate_new_lifecycle_session(lifecycle_session,key)
            records = lifecycle_session.journal.read()
            receipt = lifecycle_session._replay(records)
            saved = json.loads(row[4] or '{}')
            if (receipt['lifecycle_terminal'] is not True
                    or receipt['accounting']['costs_complete'] is not True
                    or any(e.get('received_ms',0)>now_ms for e in records)
                    or saved.get('profile') != lifecycle_session.profile
                    or saved.get('intent') != records[0]['intent']
                    or digest(saved.get('command')) != row[1]
                    or digest(lifecycle_session.profile['broker_binding']) != row[3]):
                raise AdapterViolation('terminal lifecycle/preparation provenance mismatch')
            v = _apply_canary_cash_tx(con,key[0],validated_budget,now_ms)
            cash = [e for e in [*v['cash_evidence']['events'],*v['cash_evidence'].get('prior_command_events',[])] if e.get('command_sha256')==row[1] and e['owner']=='NEW']
            if not cash:
                raise AdapterViolation('terminal command cash coverage missing')
            expected_sources = {e['event_id']:e['source_sha256'] for e in records
                                if e['kind'] in {'ENTRY_FILL','EXIT_FILL','FUNDING_CASH'}}
            sources = {}
            for e in cash:
                for source in e.get('lifecycle_sources',[]):
                    sid = source['event_id']
                    if sid in sources:
                        raise AdapterViolation('terminal lifecycle source duplicated')
                    sources[sid] = source['source_sha256']
            totals = tuple(sum((_number(e[field],field) for e in cash),Fraction(0)) for field in
                           ('gross_realized_usdt','execution_fee_usdt','funding_cash_usdt'))
            economics = tuple(Fraction(receipt['accounting'][field]) for field in
                              ('gross_realized','known_fee_total','settled_funding'))
            if sources != expected_sources or totals != economics:
                raise AdapterViolation('terminal lifecycle cash totals/source identities mismatch')
            con.execute(f'UPDATE att1_decisions SET terminal_evidence_sha256=? WHERE {where}',
                        (digest({'receipt':receipt,'records':records,'cash':cash}),*key))
            con.execute('''UPDATE att1_route SET cash_finality_frontier_ms=?,updated_ms=? WHERE account=?''',
                        (now_ms,now_ms,key[0]))
        con.execute(f'''UPDATE att1_decisions SET terminal_at_ms=?, costs_complete=1
                        WHERE {where} AND terminal_at_ms IS NULL''', (now_ms, *key))
        con.commit()
    except Exception:
        con.rollback()
        raise
    return True


def _validate_new_lifecycle_session(session, key):
    """Prove a pre-existing offline journal belongs to one NEW reservation."""
    from research_lab.att1_lifecycle_session import LifecycleSession

    if not isinstance(session, LifecycleSession):
        raise AdapterViolation('ATT1 lifecycle session required')
    if session.profile.get('profile_id') != 'BROKER_REPLAY_ATT1_V1':
        raise AdapterViolation('ATT1 session is not broker replay')
    binding = session.profile.get('broker_binding')
    if (not isinstance(binding, Mapping)
            or binding.get('account_fingerprint_sha256') != att1_broker_account_fingerprint(key[0])):
        raise AdapterViolation('ATT1 session account binding mismatch')
    records = session.journal.read()
    if not records:
        raise AdapterViolation('ATT1 session journal missing')
    intent = records[0].get('intent')
    if not isinstance(intent, Mapping):
        raise AdapterViolation('ATT1 session intent missing')
    signal = intent.get('signal')
    if (not isinstance(signal, Mapping) or signal.get('symbol') != key[2]
            or signal.get('side') != 'short' or signal.get('bar_close_ms') != key[4]
            or intent.get('book') != 'ATT1_BROKER_REPLAY:' + binding['account_fingerprint_sha256']):
        raise AdapterViolation('ATT1 session reservation mismatch')
    session.refresh()
    plan = session.receipt.get('plan')
    if not isinstance(plan, Mapping) or plan.get('symbol') != key[2]:
        raise AdapterViolation('ATT1 session plan mismatch')


def reconcile_new_att1_lifecycle_receipts(db_path, decision_key, *, session,
                                          broker_order_id, events, now_ms, release_reservation=True,
                                          validated_budget=None):
    """Offline-only reconciliation from normalized receipts into a NEW journal.

    This function neither sends nor authenticates broker traffic.  Callers own
    transport and may supply only already-normalized mapper events.  A durable
    NEW reservation is released only from the recovered session's complete,
    incident-free lifecycle receipt; it never accepts caller finality flags.
    """
    key = _decision_key(decision_key)
    if not isinstance(events, (list, tuple)):
        raise AdapterViolation('ATT1 normalized events required')
    if type(now_ms) is not int or now_ms <= 0:
        raise AdapterViolation('invalid reconciliation clock')
    _validate_new_lifecycle_session(session, key)
    durable = {event['event_id']: event for event in session.journal.read()}
    if any(event.get('received_ms', 0) > now_ms for event in durable.values()):
        raise AdapterViolation('reconciliation clock precedes durable evidence')
    for event in events:
        if not isinstance(event, Mapping):
            raise AdapterViolation('ATT1 normalized event malformed')
        ex, rx = event.get('exchange_ms'), event.get('received_ms')
        if type(ex) is not int or type(rx) is not int or not 0 < ex <= rx <= now_ms:
            raise AdapterViolation('invalid normalized event clock')
        _text(event.get('event_id'), 'event_id')
    with sqlite3.connect(db_path) as con:
        route = read_att1_route(con, key[0])
        row = con.execute('''SELECT owner,symbol,side,h1_close_ms,reserved_at_ms
                             FROM att1_decisions
                             WHERE account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?''',
                          key).fetchone()
        if (route['owner'] != 'NEW_READY' or row is None or row[0] != 'NEW'
                or tuple(row[1:4]) != key[2:]):
            raise AdapterViolation('ATT1 NEW reservation binding mismatch')
        if now_ms < row[4]:
            raise AdapterViolation('reconciliation clock precedes reservation')
        bind_att1_order(con, key[0], key, broker_order_id)
    for event in events:
        previous = durable.get(event.get('event_id'))
        if previous is not None:
            # Broker re-poll timestamps are local observability metadata.  Keep
            # the first fsynced row, but reject any changed normalized evidence.
            prior_economic = {k: v for k, v in previous.items() if k != 'received_ms'}
            current_economic = {k: v for k, v in event.items() if k != 'received_ms'}
            if prior_economic != current_economic:
                raise AdapterViolation('conflicting normalized broker event')
            continue
        session.apply(event)
        durable[event['event_id']] = dict(event)
    receipt = session.refresh()
    finality = {
        'flat': receipt.get('held_qty') == '0',
        'order_final': receipt.get('exposure_terminal') is True,
        'costs_complete': receipt.get('accounting', {}).get('costs_complete') is True,
    }
    if type(release_reservation) is not bool:
        raise AdapterViolation('invalid reservation release mode')
    if release_reservation and receipt.get('lifecycle_terminal') is True and all(finality.values()):
        with sqlite3.connect(db_path) as con:
            finalize_att1_reservation(
                con, key[0], key, now_ms=now_ms, validated_budget=validated_budget,
                lifecycle_session=session, **finality,
            )
    return receipt


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
    # Receipt time is observability metadata, not broker identity.  Re-polls
    # of an unchanged record must retain the initial durable event; the journal
    # compares every other normalized field (including source hash) on reuse.
    return {'schema_id':'att1_lifecycle_event_v1','event_id':'bybit:'+kind+':'+identity+':'+str(ex),
            'kind':kind,'exchange_ms':ex,'received_ms':received_ms,'source_sha256':source,**fields}


def map_execution(row, *, symbol, expected_order_id, expected_order_link_id,
                  kind, received_ms, exit_order_id=None, native_stop=False):
    """Map Trade only. Funding execFee has a different sign and is refused."""
    if not isinstance(row, Mapping) or kind not in {'ENTRY_FILL','EXIT_FILL'}:
        raise AdapterViolation('invalid execution input/kind')
    if type(native_stop) is not bool or (native_stop and kind!='EXIT_FILL'):
        raise AdapterViolation('native stop fill mode')
    for name, expected in (('symbol',symbol),('orderId',expected_order_id),('orderLinkId',expected_order_link_id)):
        if not (native_stop and name=='orderLinkId' and expected==''):
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


def _complete_att1_rows(pages, *, received_ms, identity_field, category_on_rows=False):
    """Check bounded pages again at the journal boundary, before any mutation."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= 16:
        raise AdapterViolation('incomplete broker pagination')
    rows, cursors, identities = [], set(), set()
    for index, page in enumerate(pages):
        if (not isinstance(page, Mapping) or type(page.get('retCode')) is not int
                or page['retCode'] != 0 or type(page.get('time')) is not int
                or not 0 < page['time'] <= received_ms
                or received_ms - page['time'] > ATT1_BROKER_IDENTITY_MAX_AGE_MS):
            raise AdapterViolation('invalid/stale broker envelope')
        result = page.get('result')
        if (not isinstance(result, Mapping) or (not category_on_rows and result.get('category') != 'linear')
                or not isinstance(result.get('list'), list)):
            raise AdapterViolation('invalid broker rows')
        cursor = result.get('nextPageCursor')
        if category_on_rows and result['list']==[] and 'nextPageCursor' in result and cursor is None:
            cursor=''
        if (not isinstance(cursor, str) or ((index == len(pages)-1) != (cursor == ''))
                or (cursor and cursor in cursors)):
            raise AdapterViolation('incomplete/cyclic broker pagination')
        cursors.add(cursor)
        for row in result['list']:
            if not isinstance(row, Mapping):
                raise AdapterViolation('invalid broker row')
            if category_on_rows and row.get('category')!='linear':
                raise AdapterViolation('foreign transaction category')
            identity = _text(row.get(identity_field), identity_field)
            if identity in identities:
                raise AdapterViolation('duplicate broker entity')
            identities.add(identity)
            rows.append(row)
    return rows


def recover_new_att1_broker_entry(db_path, decision_key, *, session, account_config,
                                 broker_identity, order_pages, execution_pages, received_ms,
                                 protection=None):
    """Recover an already-existing NEW entry, including a lost submit response.

    Pure boundary: caller must collect these pages using the same signed client.
    No missing-order result authorizes a retry/send, and no ACK invents a fill.
    Preflight the entire batch before binding or appending, then reuse the
    existing fsynced journal and SQLite reservation. Broker funding finality and
    protection are deliberately not inferred from an entry fill or account flat.
    """
    from research_lab.att1_lifecycle_coordinator import replay_lifecycle

    key = _decision_key(decision_key)
    account = _validated_old_att1_account(account_config, broker_identity, now_ms=received_ms)
    if account != key[0]:
        raise AdapterViolation('NEW recovery account mismatch')
    _validate_new_lifecycle_session(session, key)
    with sqlite3.connect(db_path) as con:
        route = read_att1_route(con, account)
        row = con.execute('''SELECT owner,order_link_id,broker_order_id,reserved_at_ms
            FROM att1_decisions WHERE account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?''', key).fetchone()
    if (row is None or row[0] != 'NEW' or route['owner'] != 'NEW_READY'
            or row[1] != _stable_link_id(account, key[2], key[3], key[4])
            or received_ms < row[3]):
        raise AdapterViolation('NEW recovery reservation mismatch')
    orders = _complete_att1_rows(order_pages, received_ms=received_ms, identity_field='orderId')
    fills = _complete_att1_rows(execution_pages, received_ms=received_ms, identity_field='execId')
    dispatch = {'order_link_id': row[1], 'broker_order_id': row[2],
                'source_sha256': digest(order_pages), 'send_enabled': False}
    if not orders:
        if fills:
            raise AdapterViolation('executions without bound broker order')
        dispatch['status'] = 'SEND_DISABLED_UNRESOLVED'
        return {'orders_allowed': False, 'dispatch': dispatch, 'receipt': session.refresh()}
    if len(orders) != 1:
        raise AdapterViolation('ambiguous NEW broker order')
    order = orders[0]
    p = session.receipt['plan']
    for field, expected in (('symbol',key[2]), ('orderLinkId',row[1]), ('side','Sell'),
                            ('timeInForce','IOC'), ('orderType','Market')):
        if order.get(field) != expected:
            raise AdapterViolation('NEW order contract mismatch: '+field)
    if (order.get('reduceOnly') is not False or type(order.get('positionIdx')) is not int
            or order['positionIdx'] != 0
            or _number(order.get('qty'),'qty',positive=True) != Fraction(p['requested_qty'])):
        raise AdapterViolation('NEW order exposure mismatch')
    oid = _text(order.get('orderId'),'orderId')
    if row[2] is not None and row[2] != oid:
        raise AdapterViolation('conflicting broker order identity')
    created = _positive_int(order.get('createdTime'),'createdTime')
    if not p['submit_ms'] <= created <= received_ms:
        raise AdapterViolation('order predates durable intent')
    events = []
    records = session.journal.read()
    durable = {event['event_id']:event for event in records[1:]}
    if not any(e['kind']=='ENTRY_ACK' for e in durable.values()):
        # Only immutable order identity fields: a later terminal status must
        # not change an ACK's source hash on restart.
        ack_source = {k:order[k] for k in ('symbol','orderId','orderLinkId','createdTime')}
        events.append(_event(ack_source,'ENTRY_ACK',oid,str(created),received_ms,{}))
    for fill in fills:
        events.append(map_execution(fill, symbol=key[2], expected_order_id=oid,
            expected_order_link_id=row[1], kind='ENTRY_FILL', received_ms=received_ms))
    events.sort(key=lambda event:(event['exchange_ms'], event['kind']!='ENTRY_ACK',event['event_id']))
    def preview(batch):
        additions = []
        for event in batch:
            previous = durable.get(event['event_id'])
            if previous is not None:
                if ({k:v for k,v in previous.items() if k!='received_ms'} !=
                        {k:v for k,v in event.items() if k!='received_ms'}):
                    raise AdapterViolation('conflicting normalized broker event')
            else:
                additions.append(event)
        return replay_lifecycle(session.profile,records[0]['intent'],list(records[1:])+additions)
    interim = preview(events)
    if _number(order.get('cumExecQty'),'cumExecQty',nonnegative=True) != Fraction(interim['accounting']['aggregate_entry_qty']):
        raise AdapterViolation('unreconciled order executions')
    if order.get('orderStatus') in {'Filled','Cancelled','Rejected','PartiallyFilledCanceled'}:
        events.append(map_order_final(order,receipt=interim,expected_order_id=oid,
            expected_order_link_id=row[1],received_ms=received_ms,entry=True))
    elif order.get('orderStatus') not in {'New','PartiallyFilled'}:
        raise AdapterViolation('unsupported entry status')
    else:
        qty = Fraction(interim['accounting']['aggregate_entry_qty'])
        if ((order['orderStatus']=='New' and qty!=0) or
                (order['orderStatus']=='PartiallyFilled' and not 0<qty<Fraction(p['requested_qty']))):
            raise AdapterViolation('inconsistent active order status')
    if protection is not None:
        if not isinstance(protection,(tuple,list)) or len(protection)!=2:
            raise AdapterViolation('invalid protection evidence pair')
        events.append(map_protection(protection[0],protection[1],receipt=interim,received_ms=received_ms))
        events.sort(key=lambda event:(event['exchange_ms'],event['kind']!='ENTRY_ACK',event['event_id']))
    preview(events)
    receipt = reconcile_new_att1_lifecycle_receipts(db_path,key,session=session,
        broker_order_id=oid,events=events,now_ms=received_ms,release_reservation=False)
    dispatch.update(status='EXISTING_ORDER_RECOVERED',broker_order_id=oid)
    return {'orders_allowed':False,'dispatch':dispatch,'receipt':receipt}


def collect_att1_authenticated_snapshot(client):
    """GET-only account reconciliation. Does not open or mutate a trading DB."""
    identity = client.identity()
    positions = client.pages('/v5/position/list',
        {'category':'linear','settleCoin':'USDT','limit':200})
    orders = client.pages('/v5/order/realtime',
        {'category':'linear','settleCoin':'USDT','openOnly':0,'limit':50})
    snapshot = validate_att1_broker_snapshot(client.redacted_config,identity,
        position_pages=positions,order_pages=orders,observed_ms=client.last_received_ms)
    return {'identity':identity,'snapshot':snapshot,'position_pages':positions,'order_pages':orders,
            'orders_allowed':False}


def validate_att1_symbol_input_evidence(account_config, broker_identity, *, symbol,
        position_pages, instrument_page, fee_page, observed_ms, zero_template_rule=None):
    """Classify source-bound symbol inputs; never authorizes orders or removes symbols.

    Pure validation cannot prove HTTPS/signing. The selected GET-only collector
    below owns transport provenance. Flat account-wide absence is not mode proof.
    COMPLETE_ONEWAY_INPUTS is only this input subset, never canary readiness.
    """
    account = _validated_old_att1_account(account_config, broker_identity, now_ms=observed_ms)
    symbol = _text(symbol, 'symbol')
    if (not symbol.endswith('USDT') or not symbol.isascii()
            or not symbol.isalnum() or symbol != symbol.upper()):
        raise AdapterViolation('exact uppercase USDT symbol required')

    def rows(page, *, fee=False):
        if (not isinstance(page, Mapping) or type(page.get('retCode')) is not int
                or page['retCode'] != 0 or type(page.get('time')) is not int
                or not 0 < page['time'] <= observed_ms
                or observed_ms-page['time'] > ATT1_BROKER_IDENTITY_MAX_AGE_MS):
            raise AdapterViolation('invalid/stale symbol envelope')
        result = page.get('result')
        if (not isinstance(result, Mapping) or not isinstance(result.get('list'), list)
                or (fee and 'category' in result)
                or (not fee and result.get('category') != 'linear')):
            raise AdapterViolation('symbol result malformed')
        batch = result['list']
        if len(batch) > 2 or any(not isinstance(r, Mapping) or r.get('symbol') != symbol for r in batch):
            raise AdapterViolation('foreign/bounded symbol rows')
        return result, batch

    if not isinstance(position_pages, list) or not 1 <= len(position_pages) <= 16:
        raise AdapterViolation('complete bounded symbol position pages required')
    positions, cursors = [], set()
    for index, page in enumerate(position_pages):
        result, batch = rows(page)
        cursor = result.get('nextPageCursor')
        if (not isinstance(cursor, str) or (index==len(position_pages)-1)!=(cursor=='')
                or (cursor and cursor in cursors)):
            raise AdapterViolation('incomplete/cyclic symbol position page')
        cursors.add(cursor); positions.extend(batch)
    compatibility = None
    if zero_template_rule is not None:
        policy = 'FLAT_IDX0_HISTORICAL_PLUS_ZERO_TEMPLATE_V1'
        if (not isinstance(zero_template_rule, Mapping)
                or set(zero_template_rule) != {'policy_id','flat_broker_snapshot'}
                or zero_template_rule['policy_id'] != policy):
            raise AdapterViolation('invalid explicit zero-template rule')
        snapshot = zero_template_rule['flat_broker_snapshot']
        if (not isinstance(snapshot, Mapping) or snapshot.get('schema_id') != 'att1_broker_snapshot_v1'
                or snapshot.get('account') != account or snapshot.get('flat_no_orders') is not True
                or type(snapshot.get('position_count')) is not int or snapshot['position_count'] != 0
                or type(snapshot.get('order_count')) is not int or snapshot['order_count'] != 0
                or type(snapshot.get('observed_ms')) is not int
                or not 0 < snapshot['observed_ms'] <= observed_ms
                or observed_ms-snapshot['observed_ms'] > ATT1_BROKER_IDENTITY_MAX_AGE_MS):
            raise AdapterViolation('zero-template rule requires fresh same-account flat broker evidence')
        source_hash = snapshot.get('source_sha256')
        if (not isinstance(source_hash,str) or len(source_hash) != 64
                or any(c not in '0123456789abcdef' for c in source_hash)):
            raise AdapterViolation('invalid flat broker source hash')
        diagnostic = diagnose_att1_symbol_position_sources(position_pages, symbol=symbol, observed_ms=observed_ms)
        if (len(position_pages) != 2 or any(len(p['result']['list']) != 1 for p in position_pages)
                or diagnostic['position_indices'] != [0,0]
                or diagnostic['uninitialized_zero_template_rows'] != [1]):
            raise AdapterViolation('zero-template source pattern mismatch')
        normal = positions[0]
        created, updated = normal.get('createdTime'), normal.get('updatedTime')
        if (any(_number(r['size'],'size') != 0 or r['side'] != '' for r in positions)
                or normal.get('positionStatus') != 'Normal' or type(normal.get('seq')) is not int
                or normal['seq'] < 0 or not isinstance(created,str) or not created.isdigit()
                or not isinstance(updated,str) or not updated.isdigit()
                or not 0 < int(created) <= int(updated) <= observed_ms
                or any(normal.get(k) != '' and _number(normal.get(k),k) != 0
                       for k in ('stopLoss','takeProfit','trailingStop'))):
            raise AdapterViolation('zero-template historical row is not unprotected flat Normal')
        compatibility = {**diagnostic, 'policy_id':policy, 'flat_broker_source_sha256':snapshot['source_sha256']}
    indices = set()
    for position in positions:
        idx = position.get('positionIdx')
        size = _number(position.get('size'), 'size', nonnegative=True)
        side = position.get('side')
        if (type(idx) is not int or idx not in (0,1,2) or (idx in indices and compatibility is None)
                or side not in ('','Buy','Sell') or (size>0 and not side)
                or (idx==1 and side=='Sell') or (idx==2 and side=='Buy')):
            raise AdapterViolation('ambiguous symbol position mode')
        indices.add(idx)
    # Observed LINK pagination: hedge1/2 then a flat idx0 placeholder. Retain
    # every page and report CONFLICT; never let the terminal0 certify one-way.
    mode = ('CONFLICT' if 0 in indices and len(indices)>1 else
            'ONEWAY' if indices=={0} else 'HEDGE' if indices=={1,2} else 'UNKNOWN')
    status = 'COMPLETE_ONEWAY_INPUTS' if mode=='ONEWAY' else 'BLOCKED_MODE_'+mode
    instrument = fee = None
    if instrument_page is None:
        status = 'BLOCKED_INSTRUMENT_UNKNOWN'
    else:
        result, batch = rows(instrument_page)
        if result.get('nextPageCursor','') != '' or len(batch)>1:
            raise AdapterViolation('ambiguous instrument source')
        if not batch:
            status = 'BLOCKED_INSTRUMENT_UNKNOWN'
        else:
            instrument = batch[0]
            if (instrument.get('status')!='Trading' or instrument.get('contractType')!='LinearPerpetual'
                    or instrument.get('settleCoin')!='USDT' or instrument.get('quoteCoin')!='USDT'):
                status = 'BLOCKED_CONTRACT_INELIGIBLE'
            else:
                for group, names in [('priceFilter',('tickSize',)),
                        ('lotSizeFilter',('qtyStep','minOrderQty','minNotionalValue'))]:
                    fields = instrument.get(group)
                    if not isinstance(fields, Mapping):raise AdapterViolation('missing instrument filters')
                    for name in names:_number(fields.get(name), name, positive=True)
    if fee_page is not None:
        _, batch = rows(fee_page, fee=True)
        if len(batch)!=1:raise AdapterViolation('missing/ambiguous actual fee')
        fee = batch[0]
        _number(fee.get('takerFeeRate'), 'taker fee', nonnegative=True)
        _number(fee.get('makerFeeRate'), 'maker fee', nonnegative=True)
    elif status=='COMPLETE_ONEWAY_INPUTS':
        status = 'BLOCKED_FEE_UNKNOWN'
    complete = status=='COMPLETE_ONEWAY_INPUTS'
    out = {'schema_id':'att1_symbol_input_evidence_v1','account':account,'symbol':symbol,
        'observed_ms':observed_ms,'position_mode':mode,'input_status':status,
        'instrument_status':instrument.get('status') if instrument is not None else None,
        'taker_fee_rate':str(_number(fee['takerFeeRate'],'taker fee')) if complete else None,
        'orders_allowed':False,'money_ready':False,
        'source_sha256':digest({'position_pages':position_pages,'instrument_page':instrument_page,'fee_page':fee_page})}
    if compatibility is not None:
        out['compatibility_rule'] = compatibility
        out['source_sha256'] = digest({'position_pages':position_pages,'instrument_page':instrument_page,
                                      'fee_page':fee_page,'zero_template_rule':zero_template_rule})
    return out


def diagnose_att1_symbol_position_sources(position_pages, *, symbol, observed_ms):
    """Retain ambiguous complete sources without weakening the mode validator.

    A terminal zero template is not documented as disposable mode evidence.
    This diagnostic never selects a preferred row or establishes one-way mode.
    """
    symbol = _text(symbol, 'symbol')
    if (type(observed_ms) is not int or observed_ms <= 0 or not symbol.endswith('USDT')
            or not symbol.isascii() or not symbol.isalnum() or symbol != symbol.upper()
            or not isinstance(position_pages, list) or not 1 <= len(position_pages) <= 16):
        raise AdapterViolation('invalid position diagnostic inputs')
    indices, sources, templates, cursors = [], [], [], set()
    for page_index, page in enumerate(position_pages):
        if (not isinstance(page, Mapping) or type(page.get('retCode')) is not int
                or page['retCode'] != 0 or type(page.get('time')) is not int
                or not 0 < page['time'] <= observed_ms
                or observed_ms-page['time'] > ATT1_BROKER_IDENTITY_MAX_AGE_MS):
            raise AdapterViolation('invalid/stale position diagnostic envelope')
        result = page.get('result')
        if (not isinstance(result, Mapping) or result.get('category') != 'linear'
                or not isinstance(result.get('list'), list) or len(result['list']) > 2):
            raise AdapterViolation('invalid position diagnostic rows')
        cursor = result.get('nextPageCursor')
        if (not isinstance(cursor, str) or (page_index==len(position_pages)-1)!=(cursor=='')
                or (cursor and cursor in cursors)):
            raise AdapterViolation('incomplete/cyclic position diagnostic pages')
        cursors.add(cursor)
        for row_index, row in enumerate(result['list']):
            if not isinstance(row, Mapping) or row.get('symbol') != symbol:
                raise AdapterViolation('foreign position diagnostic symbol')
            idx = row.get('positionIdx');size = _number(row.get('size'),'position size',nonnegative=True)
            side = row.get('side')
            if (type(idx) is not int or idx not in (0,1,2) or side not in ('','Buy','Sell')
                    or (size>0 and not side) or (idx==1 and side=='Sell') or (idx==2 and side=='Buy')):
                raise AdapterViolation('invalid position diagnostic mode')
            if (idx==0 and size==0 and side=='' and type(row.get('seq')) is int and row['seq']==-1
                    and all(row.get(k)=='' for k in ('createdTime','updatedTime','positionStatus',
                                                     'stopLoss','takeProfit','trailingStop'))):
                templates.append(len(indices))
            indices.append(idx)
            sources.append({'page':page_index,'row':row_index,'row_sha256':digest(row)})
    unique = set(indices)
    status = ('BLOCKED_MODE_CONFLICT' if 0 in unique and len(unique)>1 else
              'BLOCKED_DUPLICATE_POSITION_INDEX' if len(unique)!=len(indices) else
              'NO_SOURCE_AMBIGUITY_DETECTED')
    return {'schema_id':'att1_position_source_diagnostic_v1','symbol':symbol,
            'status':status,'raw_row_count':len(indices),'position_indices':indices,
            'uninitialized_zero_template_rows':templates,'row_sources':sources,
            'rows_discarded':0,'source_sha256':digest(position_pages),
            'orders_allowed':False,'money_ready':False}


def collect_att1_symbol_input_evidence(client, symbol):
    """Explicit selected-account GET pass; no DB, mode writes, filtering or money runner."""
    identity = client.identity()
    positions = client.pages('/v5/position/list', {'category':'linear','symbol':symbol,'limit':200})
    sources = {}; failures = {}
    for name, path in [('instrument_page','/v5/market/instruments-info'),('fee_page','/v5/account/fee-rate')]:
        try:sources[name] = client.get(path, {'category':'linear','symbol':symbol})
        except ValueError as error:
            # A rejected/malformed/negative envelope never becomes a guessed fee.
            sources[name] = None; failures[name] = type(error).__name__
    evidence = validate_att1_symbol_input_evidence(client.redacted_config, identity,
        symbol=symbol, position_pages=positions, observed_ms=client.last_received_ms, **sources)
    return {'evidence':evidence,'position_pages':positions,**sources,
        'collection_failures':failures,'orders_allowed':False}


def collect_new_att1_entry_recovery(client, db_path, decision_key, *, session, source_dir):
    """Connect the existing signed GET client to NEW entry recovery, sends OFF.

    Raw pages and mapper source records are fsynced privately before journal
    writes. This is an explicit recovery operation, not a background owner or
    permission to create an order. Empty history never means safe to retry.
    """
    import os
    import stat
    from scripts.run_att1_lifecycle_zero_risk import _save_json_once

    key = _decision_key(decision_key)
    _validate_new_lifecycle_session(session,key)
    root = Path(source_dir)
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    info = root.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise AdapterViolation('private evidence directory required')
    def save(value):
        sha = digest(value)
        _save_json_once(root/(sha+'.json'),value)
        return sha
    truth = collect_att1_authenticated_snapshot(client)
    if truth['identity'].account != key[0]:
        raise AdapterViolation('NEW recovery account mismatch')
    snapshot_sha = save({'snapshot':truth['snapshot'],'position_pages':truth['position_pages'],
                         'order_pages':truth['order_pages']})
    link = _stable_link_id(key[0],key[2],key[3],key[4])
    order_pages = client.pages('/v5/order/history',
        {'category':'linear','symbol':key[2],'orderLinkId':link,'limit':50,
         'startTime':session.receipt['plan']['submit_ms'],
         'endTime':min(client.last_received_ms,session.receipt['plan']['submit_ms']+7*86400000)})
    rows = _complete_att1_rows(order_pages,received_ms=client.last_received_ms,identity_field='orderId')
    if len(rows)>1:
        raise AdapterViolation('ambiguous NEW broker order')
    if rows:
        executions = client.pages('/v5/execution/list',{'category':'linear','symbol':key[2],
            'orderId':_text(rows[0].get('orderId'),'orderId'),'limit':100,
            'startTime':session.receipt['plan']['submit_ms'],
            'endTime':min(client.last_received_ms,session.receipt['plan']['submit_ms']+7*86400000)})
    else:
        executions = [{'retCode':0,'time':client.last_received_ms,
            'result':{'category':'linear','list':[],'nextPageCursor':''}}]
    # The empty execution envelope is not a broker query and is labelled in
    # the receipt. No ACK/fill/finality is ever derived from it.
    source_sha = save({'order_pages':order_pages,'execution_pages':executions,
        'executions_queried':bool(rows),'received_ms':client.last_received_ms,
        'account':key[0],'snapshot_sha256':snapshot_sha})
    for row in rows:
        save(row)
        save({k:row[k] for k in ('symbol','orderId','orderLinkId','createdTime')})
    for page in executions:
        for row in page['result']['list']:
            save(row)
    protection=None
    positions=[r for pg in truth['position_pages'] for r in pg['result']['list']
               if r.get('symbol')==key[2] and _number(r.get('size'),'size',nonnegative=True)>0]
    stops=[r for pg in truth['order_pages'] for r in pg['result']['list']
           if r.get('symbol')==key[2] and r.get('stopOrderType')=='StopLoss']
    if len(positions)==1 and len(stops)==1 and rows:
        protection=(positions[0],stops[0])
        save({'position':positions[0],'stop_order':stops[0]})
    result = recover_new_att1_broker_entry(db_path,key,session=session,
        account_config=client.redacted_config,broker_identity=truth['identity'],
        order_pages=order_pages,execution_pages=executions,received_ms=client.last_received_ms,
        protection=protection)
    result.update(authenticated_account=key[0],source_sha256=source_sha,
                  blocker='PROTECTION_AND_EXIT_FUNDING_BINDING_PENDING')
    return result


def reconcile_new_att1_broker_finality(db_path, decision_key, *, session, account_config,
        broker_identity, transaction_pages, funding_pages, coverage_start_ms,
        coverage_end_ms, position_pages, order_pages, received_ms, validated_budget=None):
    """Reconcile actual funding cash against independently collected settlements.

    The trusted signed caller supplies full, explicitly bounded query windows.
    Empty cash pages never imply no funding. An absent expected cash settlement
    keeps net-R null and the reservation occupied. Direct flat/no-orders truth
    is necessary in addition to complete incident-free journal accounting.
    """
    key = _decision_key(decision_key)
    account = _validated_old_att1_account(account_config,broker_identity,now_ms=received_ms)
    if account!=key[0]:raise AdapterViolation('finality account mismatch')
    _validate_new_lifecycle_session(session,key)
    snapshot = validate_att1_broker_snapshot(account_config,broker_identity,
        position_pages=position_pages,order_pages=order_pages,observed_ms=received_ms)
    if not snapshot['flat_no_orders']:
        raise AdapterViolation('broker flat/no-orders finality not confirmed')
    records = list(session.journal.read())
    receipt = session.refresh()
    fills = [e for e in records if e['kind'] in {'ENTRY_FILL','EXIT_FILL'}]
    exits = [e for e in fills if e['kind']=='EXIT_FILL']
    if (not exits or receipt['held_qty']!='0' or receipt['pending_exit'] is not None
            or receipt['entry_status'] not in {'FILLED','CANCELLED','REJECTED','EXPIRED'}):
        raise AdapterViolation('exposure finality not confirmed')
    start,end = coverage_start_ms,coverage_end_ms
    if (type(start) is not int or type(end) is not int or not 0<start<end<=received_ms-60000
            or start>min(e['exchange_ms'] for e in fills)-5000
            or end<max(e['exchange_ms'] for e in exits)+5000):
        raise AdapterViolation('funding coverage window incomplete or publication pending')
    if not isinstance(funding_pages,list) or not 1<=len(funding_pages)<=16:
        raise AdapterViolation('funding pagination incomplete')
    upper=end;times=set()
    for index,page in enumerate(funding_pages):
        if (not isinstance(page,Mapping) or type(page.get('retCode')) is not int or page['retCode']!=0
                or type(page.get('time')) is not int or not 0<page['time']<=received_ms
                or received_ms-page['time']>60000):
            raise AdapterViolation('invalid public funding envelope')
        result=page.get('result')
        if not isinstance(result,Mapping) or result.get('category')!='linear' or not isinstance(result.get('list'),list):
            raise AdapterViolation('invalid public funding rows')
        batch=result['list']
        if len(batch)>200:raise AdapterViolation('funding page bound')
        local=[]
        for row in batch:
            when=_positive_int(row.get('fundingRateTimestamp'),'funding timestamp')
            if row.get('symbol')!=key[2] or not start<=when<=upper or when in times:
                raise AdapterViolation('foreign/duplicate funding schedule')
            _number(row.get('fundingRate'),'funding rate')
            times.add(when);local.append(when)
        complete=len(batch)<200 or (local and min(local)==start)
        if complete != (index==len(funding_pages)-1):raise AdapterViolation('funding pagination incomplete')
        if local:upper=min(local)-1
    if transaction_pages and isinstance(transaction_pages[0],Mapping) and 'pages' in transaction_pages[0]:
        rows=[];next_start=start;seen_ids=set()
        for window in transaction_pages:
            lo,hi=window.get('start_ms'),window.get('end_ms')
            if (type(lo) is not int or type(hi) is not int or lo!=next_start
                    or not lo<=hi<=end or hi-lo>7*86400000):
                raise AdapterViolation('transaction window gap/overlap')
            batch=_complete_att1_rows(window['pages'],received_ms=received_ms,identity_field='id',category_on_rows=True)
            for row in batch:
                if row['id'] in seen_ids or not lo<=_positive_int(row.get('transactionTime'),'transaction time')<=hi:
                    raise AdapterViolation('transaction window duplicate/mismatch')
                seen_ids.add(row['id'])
            rows.extend(batch);next_start=hi+1
        if next_start!=end+1:raise AdapterViolation('incomplete transaction windows')
    else:
        if end-start>7*86400000:raise AdapterViolation('transaction window exceeds API bound')
        rows=_complete_att1_rows(transaction_pages,received_ms=received_ms,identity_field='id',category_on_rows=True)
    events=[]
    for row in rows:
        when=_positive_int(row.get('transactionTime'),'transaction time')
        if not start<=when<=end:raise AdapterViolation('transaction outside coverage window')
        if row.get('symbol')!=key[2]:continue
        if row.get('type')!='SETTLEMENT':raise AdapterViolation('unexpected transaction type')
        if when not in times:raise AdapterViolation('cash settlement absent from funding schedule')
        events.append(map_funding(row,symbol=key[2],received_ms=received_ms))
    events.sort(key=lambda event:(event['exchange_ms'],event['event_id']))
    # Stable identity independent of the arrival of delayed cash or re-poll time.
    coverage_source={'symbol':key[2],'start_ms':start,'end_ms':end,'settlement_ms':sorted(times)}
    source=digest(coverage_source)
    events.append({'schema_id':'att1_lifecycle_event_v1','event_id':'bybit:coverage:'+source,
        'kind':'FUNDING_COVERAGE','exchange_ms':end,'received_ms':received_ms,
        'source_sha256':source,'start_ms':start,'end_ms':end,'settlement_ms':sorted(times),'complete':True})
    with sqlite3.connect(db_path) as con:
        row=con.execute('''SELECT broker_order_id FROM att1_decisions
            WHERE account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?''',key).fetchone()
    if row is None or not row[0]:raise AdapterViolation('entry broker binding absent')
    result=reconcile_new_att1_lifecycle_receipts(db_path,key,session=session,
        broker_order_id=row[0],events=events,now_ms=received_ms,release_reservation=False)
    if result['lifecycle_terminal']:
        with sqlite3.connect(db_path) as con:
            finalize_att1_reservation(con,key[0],key,flat=True,order_final=True,
                costs_complete=result['accounting']['costs_complete'],now_ms=received_ms,
                validated_budget=validated_budget,lifecycle_session=session)
    return result


def att1_exit_order_link_id(decision_key, exit_order_id):
    """Stable lookup identity for one existing coordinator exit; not a send API."""
    key=_decision_key(decision_key)
    return 'a1x'+digest([*key,_text(exit_order_id,'exit_order_id')])[:26]


def recover_new_att1_broker_exit(db_path, decision_key, *, session, account_config,
        broker_identity, order_pages, execution_pages, received_ms):
    """Recover exact reduce-only exit receipts with entry reservation still held."""
    from research_lab.att1_lifecycle_coordinator import replay_lifecycle
    key=_decision_key(decision_key)
    if _validated_old_att1_account(account_config,broker_identity,now_ms=received_ms)!=key[0]:
        raise AdapterViolation('exit account mismatch')
    _validate_new_lifecycle_session(session,key)
    orders=_complete_att1_rows(order_pages,received_ms=received_ms,identity_field='orderId')
    fills=_complete_att1_rows(execution_pages,received_ms=received_ms,identity_field='execId')
    if not orders:
        if fills:raise AdapterViolation('exit fills without order')
        return {'orders_allowed':False,'dispatch':{'status':'SEND_DISABLED_UNRESOLVED'},'receipt':session.receipt}
    if len(orders)!=1:raise AdapterViolation('ambiguous exit order')
    order=orders[0]; records=list(session.journal.read()); existing=records[1:]
    pending=session.receipt['pending_exit']
    ids={e['exit_order_id'] for e in existing if e['kind']=='EXIT_ACK'}
    if pending:ids.add(pending['exit_order_id'])
    matches=[x for x in ids if att1_exit_order_link_id(key,x)==order.get('orderLinkId')]
    if len(matches)!=1:raise AdapterViolation('foreign exit link')
    xid=matches[0];oid=_text(order.get('orderId'),'orderId')
    # Recover the original pending intent even when EXIT_FINAL was fsynced
    # before a process crash. This replay is read-only and never rewrites history.
    final_index=next((i for i,e in enumerate(existing) if e['kind']=='EXIT_FINAL' and e['exit_order_id']==xid),len(existing))
    before_final=replay_lifecycle(session.profile,records[0]['intent'],existing[:final_index])
    pending=before_final['pending_exit']
    if pending is None or pending['exit_order_id']!=xid:
        raise AdapterViolation('exit intent not recoverable')
    for field,value in (('symbol',key[2]),('side','Buy'),('timeInForce','IOC'),('orderType','Market')):
        if order.get(field)!=value:raise AdapterViolation('exit contract mismatch: '+field)
    if (order.get('reduceOnly') is not True or type(order.get('positionIdx')) is not int
            or order['positionIdx']!=0 or _number(order.get('qty'),'exit qty',positive=True)!=Fraction(pending['qty'])):
        raise AdapterViolation('exit exposure mismatch')
    created=_positive_int(order.get('createdTime'),'createdTime')
    if not pending['submit_ms']<=created<=received_ms:raise AdapterViolation('exit clock mismatch')
    ack_source={k:order[k] for k in ('symbol','orderId','orderLinkId','createdTime')}
    ack=_event(ack_source,'EXIT_ACK',oid,str(created),received_ms,{'exit_order_id':xid})
    prior_ack=[e for e in existing if e['kind']=='EXIT_ACK' and e['exit_order_id']==xid]
    if prior_ack and any(e['event_id']!=ack['event_id'] or e['source_sha256']!=ack['source_sha256'] for e in prior_ack):
        raise AdapterViolation('conflicting exit broker binding')
    events=[ack]+[map_execution(f,symbol=key[2],expected_order_id=oid,
        expected_order_link_id=order['orderLinkId'],kind='EXIT_FILL',received_ms=received_ms,
        exit_order_id=xid) for f in fills]
    events.sort(key=lambda e:(e['exchange_ms'],e['kind']!='EXIT_ACK',e['event_id']))
    durable={e['event_id']:e for e in existing}
    additions=[]
    for event in events:
        old=durable.get(event['event_id'])
        if old is not None:
            if {k:v for k,v in old.items() if k!='received_ms'}!={k:v for k,v in event.items() if k!='received_ms'}:
                raise AdapterViolation('conflicting exit execution')
        else:additions.append(event)
    interim=replay_lifecycle(session.profile,records[0]['intent'],existing[:final_index]+additions)
    if order.get('orderStatus') in {'Filled','Cancelled','Rejected','PartiallyFilledCanceled'}:
        events.append(map_order_final(order,receipt=interim,expected_order_id=oid,
            expected_order_link_id=order['orderLinkId'],received_ms=received_ms,entry=False))
    else:
        filled=Fraction(pending['qty'])-Fraction(interim['pending_exit']['remaining_qty'])
        if (order.get('orderStatus') not in {'New','PartiallyFilled'}
                or _number(order.get('cumExecQty'),'cumExecQty',nonnegative=True)!=filled
                or (order['orderStatus']=='New' and filled!=0)
                or (order['orderStatus']=='PartiallyFilled' and not 0<filled<Fraction(pending['qty']))):
            raise AdapterViolation('exit status/executions mismatch')
    # Whole batch preflight avoids releasing or partially persisting an invalid final order.
    unseen=[e for e in events if e['event_id'] not in durable]
    replay_lifecycle(session.profile,records[0]['intent'],existing+unseen)
    with sqlite3.connect(db_path) as con:
        row=con.execute('''SELECT broker_order_id FROM att1_decisions
            WHERE account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?''',key).fetchone()
    if row is None or not row[0]:raise AdapterViolation('entry binding absent')
    result=reconcile_new_att1_lifecycle_receipts(db_path,key,session=session,
        broker_order_id=row[0],events=events,now_ms=received_ms,release_reservation=False)
    return {'orders_allowed':False,'dispatch':{'status':'EXISTING_ORDER_RECOVERED',
        'order_link_id':order['orderLinkId'],'broker_order_id':oid},'receipt':result}


def reconcile_new_att1_authenticated(client, db_path, decision_key, *, session, source_dir,
                                      validated_budget=None):
    """One explicit read-only recovery pass through the existing NEW lifecycle.

    Does not scan, create intents, run a service, or submit an order. The caller
    supplies the existing durable session. Native exchange SL executions bind
    to the original durably acknowledged protective order and its raw source;
    missing or conflicting protection identity still fails closed.
    """
    from scripts.run_att1_lifecycle_zero_risk import _save_json_once
    key=_decision_key(decision_key)
    outcome=collect_new_att1_entry_recovery(client,db_path,key,session=session,source_dir=source_dir)
    root=Path(source_dir)
    def save(value):
        sha=digest(value);_save_json_once(root/(sha+'.json'),value);return sha
    pending=session.receipt['pending_exit']
    native_pending=pending is not None and pending['exit_order_id'].startswith('broker-stop:')
    if native_pending or (pending is None and Fraction(session.receipt['held_qty'])>0):
        armed_ack,armed_source=_att1_saved_protection(session,source_dir)
        stop=armed_source['stop_order']
        start=_positive_int(stop.get('createdTime'),'stop creation time')
        orders=client.pages('/v5/order/history',{'category':'linear','symbol':key[2],
            'orderId':stop['orderId'],'startTime':start,'endTime':min(client.last_received_ms,start+7*86400000),'limit':50})
        rows=_complete_att1_rows(orders,received_ms=client.last_received_ms,identity_field='orderId')
        if len(rows)>1:raise AdapterViolation('ambiguous native stop')
        if rows and rows[0].get('orderStatus') in {'Filled','PartiallyFilled','PartiallyFilledCanceled','Cancelled'} and _number(rows[0].get('cumExecQty'),'stop cumExecQty',nonnegative=True)>0:
            # Include the complete bounded execution history, never just the
            # default last-seven-days window. Raw windows are retained below.
            windows=[];lo=armed_ack['exchange_ms'];end=client.last_received_ms
            while lo<=end:
                if len(windows)>=4:raise AdapterViolation('native stop recovery history bound')
                hi=min(end,lo+7*86400000)
                pages=client.pages('/v5/execution/list',{'category':'linear','symbol':key[2],
                    'orderId':stop['orderId'],'startTime':lo,'endTime':hi,'limit':100})
                windows.append({'start_ms':lo,'end_ms':hi,'pages':pages});lo=hi+1
            flat=[];seen=set()
            for window in windows:
                for row in _complete_att1_rows(window['pages'],received_ms=client.last_received_ms,identity_field='execId'):
                    when=_positive_int(row.get('execTime'),'execTime')
                    if not window['start_ms']<=when<=window['end_ms'] or row['execId'] in seen:
                        raise AdapterViolation('native stop execution window conflict')
                    seen.add(row['execId']);flat.append(row)
            # Derived page shape for the pure mapper; it is NOT a broker receipt.
            executions=[{'retCode':0,'time':client.last_received_ms,'result':{'category':'linear',
                'list':flat,'nextPageCursor':''}}]
            save({'account':key[0],'order_pages':orders,'execution_windows':windows,
                  'received_ms':client.last_received_ms,'execution_page_is_derived':True})
            identity=client.identity()
            outcome['receipt']=recover_new_att1_native_stop(db_path,key,session=session,
                account_config=client.redacted_config,broker_identity=identity,order_pages=orders,
                execution_pages=executions,source_dir=source_dir,received_ms=client.last_received_ms)
        pending=session.receipt['pending_exit']
    if pending is not None and not pending['exit_order_id'].startswith('broker-stop:'):
        link=att1_exit_order_link_id(key,pending['exit_order_id'])
        start=pending['submit_ms']
        orders=client.pages('/v5/order/history',{'category':'linear','symbol':key[2],
            'orderLinkId':link,'startTime':start,'endTime':min(client.last_received_ms,start+7*86400000),'limit':50})
        rows=_complete_att1_rows(orders,received_ms=client.last_received_ms,identity_field='orderId')
        if len(rows)>1:raise AdapterViolation('ambiguous exit order')
        if not rows:
            outcome['blocker']='EXIT_SEND_DISABLED_UNRESOLVED'
            return outcome
        executions=client.pages('/v5/execution/list',{'category':'linear','symbol':key[2],
            'orderId':rows[0]['orderId'],'startTime':start,
            'endTime':min(client.last_received_ms,start+7*86400000),'limit':100})
        save({'orders':orders,'executions':executions,'account':key[0],'received_ms':client.last_received_ms})
        for row in rows:
            save(row);save({k:row[k] for k in ('symbol','orderId','orderLinkId','createdTime')})
        for page in executions:
            for row in page['result']['list']:save(row)
        identity=client.identity()
        outcome=recover_new_att1_broker_exit(db_path,key,session=session,account_config=client.redacted_config,
            broker_identity=identity,order_pages=orders,execution_pages=executions,received_ms=client.last_received_ms)
    receipt=session.refresh()
    if receipt['held_qty']!='0' or receipt['pending_exit'] is not None:
        outcome.update(blocker='EXPOSURE_STILL_OPEN_ORDERS_OFF',receipt=receipt)
        return outcome
    fills=[e for e in session.journal.read() if e['kind'] in {'ENTRY_FILL','EXIT_FILL'}]
    exits=[e for e in fills if e['kind']=='EXIT_FILL']
    if not exits:
        outcome.update(blocker='NO_FILLED_TERMINAL',receipt=receipt)
        return outcome
    start=min(e['exchange_ms'] for e in fills)-5000
    end=max(e['exchange_ms'] for e in exits)+5000
    if client.last_received_ms<end+60000:
        outcome.update(blocker='FUNDING_PUBLICATION_PENDING',receipt=receipt)
        return outcome
    transactions=[];lo=start
    while lo<=end:
        if len(transactions)>=4:raise AdapterViolation('transaction lifetime query bound')
        hi=min(end,lo+7*86400000)
        pages=client.pages('/v5/account/transaction-log',{'category':'linear','accountType':'UNIFIED',
            'currency':'USDT','type':'SETTLEMENT','startTime':lo,'endTime':hi,'limit':50})
        transactions.append({'start_ms':lo,'end_ms':hi,'pages':pages});lo=hi+1
    funding=[];upper=end
    for _ in range(16):
        page=client.get('/v5/market/funding/history',{'category':'linear','symbol':key[2],
            'startTime':start,'endTime':upper,'limit':200})
        funding.append(page);rows=page['result']['list']
        if len(rows)<200:break
        earliest=min(_positive_int(r.get('fundingRateTimestamp'),'funding timestamp') for r in rows)
        if earliest<=start:break
        if earliest>=upper:raise AdapterViolation('funding pagination stalled')
        upper=earliest-1
    else:raise AdapterViolation('funding pagination incomplete')
    truth=collect_att1_authenticated_snapshot(client)
    save({'account':key[0],'funding_pages':funding,'transaction_windows':transactions,
        'snapshot':truth['snapshot'],'position_pages':truth['position_pages'],
        'order_pages':truth['order_pages'],'received_ms':client.last_received_ms})
    for window in transactions:
        for page in window['pages']:
            for row in page['result']['list']:save(row)
    times=sorted({_positive_int(r.get('fundingRateTimestamp'),'funding timestamp')
                  for p in funding for r in p['result']['list']})
    save({'symbol':key[2],'start_ms':start,'end_ms':end,'settlement_ms':times})
    result=reconcile_new_att1_broker_finality(db_path,key,session=session,
        account_config=client.redacted_config,broker_identity=truth['identity'],
        transaction_pages=transactions,funding_pages=funding,coverage_start_ms=start,
        coverage_end_ms=end,position_pages=truth['position_pages'],order_pages=truth['order_pages'],
        received_ms=client.last_received_ms,validated_budget=validated_budget)
    outcome.update(receipt=result,orders_allowed=False,
        blocker=None if result['lifecycle_terminal'] else 'COSTS_OR_INTEGRITY_NOT_FINAL',
        authenticated_account=key[0])
    return outcome


def _att1_saved_protection(session, source_dir):
    """Load the immutable broker source for the last durably acknowledged stop."""
    from research_lab.att1_lifecycle_coordinator import replay_lifecycle
    from research_lab.att1_lifecycle_journal import _pairs, _constant
    records=list(session.journal.read())
    matches=[(i,e) for i,e in enumerate(records) if e.get('kind')=='PROTECTION_ACK']
    if not matches:raise AdapterViolation('durable protection receipt missing')
    index,ack=matches[-1];p=Path(source_dir)/(ack['source_sha256']+'.json')
    try:
        if p.is_symlink() or p.stat().st_size>1000000:raise ValueError('unsafe source')
        source=json.loads(p.read_text(),object_pairs_hook=_pairs,parse_constant=_constant)
        if digest(source)!=ack['source_sha256']:raise ValueError('source hash')
        before=replay_lifecycle(session.profile,records[0]['intent'],records[1:index])
        mapped=map_protection(source['position'],source['stop_order'],receipt=before,received_ms=ack['received_ms'])
        if mapped!=ack:raise ValueError('source does not reproduce acknowledgement')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise AdapterViolation('protection source not verified') from exc
    return ack,source


def recover_new_att1_native_stop(db_path, decision_key, *, session, account_config,
        broker_identity, order_pages, execution_pages, source_dir, received_ms):
    """Account for execution of a durably armed exchange SL, without fake PRICE.

    The protective order identity, immutable creation time and frozen stop must
    match the original raw source. Missing/competing protection fails closed.
    No reservation is released here: cash/funding plus fresh broker finality
    still use the existing finality reconciler.
    """
    from research_lab.att1_lifecycle_coordinator import replay_lifecycle
    from scripts.run_att1_lifecycle_zero_risk import _save_json_once
    key=_decision_key(decision_key)
    if _validated_old_att1_account(account_config,broker_identity,now_ms=received_ms)!=key[0]:
        raise AdapterViolation('native stop account mismatch')
    _validate_new_lifecycle_session(session,key)
    ack,source=_att1_saved_protection(session,source_dir);armed=source['stop_order']
    orders=_complete_att1_rows(order_pages,received_ms=received_ms,identity_field='orderId')
    fills=_complete_att1_rows(execution_pages,received_ms=received_ms,identity_field='execId')
    if len(orders)!=1 or not fills:raise AdapterViolation('native stop order/executions incomplete')
    order=orders[0]
    for field in ('orderId','symbol','orderLinkId','createdTime','triggerPrice','stopOrderType','positionIdx','side','closeOnTrigger','reduceOnly'):
        if field not in armed or order.get(field)!=armed[field]:
            raise AdapterViolation('native stop differs from armed identity: '+field)
    if order.get('orderType')!='Market' or order.get('orderStatus') not in {'Filled','PartiallyFilled','PartiallyFilledCanceled','Cancelled'}:
        raise AdapterViolation('native stop execution type/status')
    if type(order.get('positionIdx')) is not int or order.get('closeOnTrigger') is not True or order.get('reduceOnly') is not True:
        raise AdapterViolation('native stop mode/authority')
    records=list(session.journal.read());durable={e['event_id']:e for e in records[1:]}
    xid='broker-stop:'+digest([key[0],order['orderId']])
    previous=[e for e in records[1:] if e.get('kind')=='BROKER_STOP_TRIGGER' and e['exit_order_id']==xid]
    from research_lab.att1_lifecycle_profile import _decimal_text
    quantity=previous[0]['qty'] if previous else _decimal_text(Fraction(session.receipt['held_qty']))
    if _number(order.get('qty'),'stop quantity',positive=True)!=Fraction(quantity):
        raise AdapterViolation('native stop quantity mismatch')
    first=min(_positive_int(f.get('execTime'),'execTime') for f in fills)
    trigger_source={'orderId':order['orderId'],'account':key[0],'protection_source_sha256':ack['source_sha256'],
                    'first_execution_ms':first,'qty':quantity}
    events=[_event(trigger_source,'BROKER_STOP_TRIGGER',order['orderId'],str(first),received_ms,
        {'exit_order_id':xid,'protection_event_id':ack['event_id'],'qty':quantity,'stop':armed['triggerPrice']})]
    events.extend(sorted([map_execution(f,symbol=key[2],expected_order_id=order['orderId'],
        expected_order_link_id=order['orderLinkId'],kind='EXIT_FILL',received_ms=received_ms,
        exit_order_id=xid,native_stop=True) for f in fills],key=lambda e:(e['exchange_ms'],e['event_id'])))
    def additions(batch):
        out=[]
        for e in batch:
            old=durable.get(e['event_id'])
            if old is not None:
                if {k:v for k,v in old.items() if k!='received_ms'}!={k:v for k,v in e.items() if k!='received_ms'}:
                    raise AdapterViolation('conflicting native stop evidence')
            else:out.append(e)
        return out
    # Replay up to its final receipt for repeat polls of an already-final order.
    end=next((i for i,e in enumerate(records) if e.get('kind')=='EXIT_FINAL' and e['exit_order_id']==xid),len(records))
    interim=replay_lifecycle(session.profile,records[0]['intent'],records[1:end]+additions(events))
    pending=interim['pending_exit']
    if pending is None:raise AdapterViolation('native stop intent not recoverable')
    filled=Fraction(quantity)-Fraction(pending['remaining_qty'])
    if _number(order.get('cumExecQty'),'stop cumExecQty',nonnegative=True)!=filled:
        raise AdapterViolation('native stop executions incomplete')
    statuses={'Filled':'FILLED','PartiallyFilledCanceled':'CANCELLED','Cancelled':'CANCELLED'}
    if order['orderStatus'] in statuses:
        if order['orderStatus']=='Filled' and pending['remaining_qty']!='0':
            raise AdapterViolation('native stop incomplete filled status')
        events.append(_event(order,'EXIT_FINAL',order['orderId'],order.get('updatedTime'),received_ms,
            {'exit_order_id':xid,'status':statuses[order['orderStatus']]}))
    replay_lifecycle(session.profile,records[0]['intent'],records[1:]+additions(events))
    for value in (trigger_source,order,*fills):
        _save_json_once(Path(source_dir)/(digest(value)+'.json'),value)
    with sqlite3.connect(db_path) as con:
        row=con.execute('''SELECT broker_order_id FROM att1_decisions WHERE account=? AND family=? AND symbol=? AND side=? AND h1_close_ms=?''',key).fetchone()
    if row is None or not row[0]:raise AdapterViolation('native stop entry binding absent')
    return reconcile_new_att1_lifecycle_receipts(db_path,key,session=session,
        broker_order_id=row[0],events=events,now_ms=received_ms,release_reservation=False)
