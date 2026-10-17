"""Versioned KITY ten-entry batch and private read-stream, ORDERS_OFF by default.

No daemon, credential discovery or CLI money action. The existing exclusive
account owner must supply the physical lease, reviewed GO and fresh preflight.
The old sequential journal and installed writer are deliberately unchanged.
"""
import copy
import hashlib
import hmac
import json
import re
import sqlite3
import concurrent.futures as cf
import time
from pathlib import Path

from bot.kity_m3_orders_off import digest, _levels, _vwap
from research_lab import kity_execution_micro_runtime_v1 as rt
from research_lab.kity_execution_micro_bybit_v1 import execution_event, order_events
from research_lab.kity_micro_physical_owner_v1 import (
    BASE, SignedPostOnce, PhysicalOwner, publish, sha, now_ms, validate_fresh_entry,
)
from research_lab.kity_micro_transport_v1 import SourceError
from research_lab.kity_micro_post_go_pricing_v1 import (
    validate_policy, compile_after_go, verify_compilation, dispatch_window,
)

MODE = 'KITY_TEN_NATIVE_GUARDED_BATCH_V1'
PRIVATE_URL = 'wss://stream.bybit.com/v5/private'
TOPICS = ('order.linear', 'execution.linear', 'position.linear')
GO_PREFIX = 'GO KITY_EXECUTION_MICRO_BATCH_V1 '


def make_batch_policy(policy):
    validate_policy(policy)
    out = dict(schema=MODE, base_policy=copy.deepcopy(policy), orders_allowed=False)
    out['batch_policy_id'] = digest(out)
    return out


def validate_batch_policy(policy):
    if policy != make_batch_policy(policy['base_policy']):
        raise SourceError('BATCH_POLICY_PIN_CONFLICT')
    return policy


# Diagnostic vocabulary only. Unknown/remote exception text is never persisted.
_NO_SEND_CODES = frozenset({
    'INTENT_REFERENCE_PLAN_BLOCKED', 'INTENT_REFERENCE_SOURCE_STALE',
    'INTENT_WORST_REFERENCE_GROSS_EXCEEDS_215', 'INTENT_FRESH_GROSS_CAP_EXCEEDED',
    'POST_GO_DISPATCH_DEADLINE', 'POLICY_GO_SESSION_CLOCK', 'CAPTURE_PRECEDES_GO',
    'POST_GO_SOURCE_CUSTODY_CONFLICT', 'INTENT_FRESH_CUSTODY_OR_BOUNDS_CONFLICT',
    'INTENT_ACCOUNT_NOT_FLAT_OR_PERMISSION_UNKNOWN', 'INTENT_FRESH_SOURCE_CLOCK',
    'INTENT_COMMON_2S_SOURCE_UNKNOWN', 'INTENT_BALANCE_INSUFFICIENT',
    'PLAN_PIN_CONFLICT', 'PLAN_BOUND_OR_GROSS_CONFLICT',
    'BATCH_APPROVED_BOUNDS_REQUIRED', 'BATCH_EXACT_NATIVE_GUARD_REQUIRED',
    'BATCH_LINKS_NOT_UNIQUE',
})
_NO_SEND_PLAN_CODES = frozenset({'GROSS_CAP_EXCEEDED'})


def _no_send_diagnostic(exc, policy, fresh, stage, observed_ms):
    """Bounded local evidence; never serialize raw capture or exception text.

    Zero writes describes this capture/compile hook, which has no sender or
    lifecycle journal. It does not assert external-account flatness or writes.
    """
    exception_type = type(exc).__name__
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', exception_type):
        exception_type = 'EXCEPTION_TYPE_UNAVAILABLE'
    exception_code = 'UNCLASSIFIED_FAILURE'
    if type(exc) in (SourceError, ValueError) and len(exc.args) == 1:
        candidate = exc.args[0]
        if type(candidate) is str and candidate in _NO_SEND_CODES:
            exception_code = candidate
    out = dict(schema='KITY_BATCH_NO_SEND_DIAGNOSTIC_V1', status='NO_SEND',
               reason=exception_type, exception_type=exception_type,
               reason_code=exception_code, exception_reason_code=exception_code,
               batch_policy_id=policy['batch_policy_id'], observed_ms=observed_ms,
               stage=stage, broker_writes=0, broker_writes_scope='LOCAL_CAPTURE_COMPILE_HOOK_ONLY')
    # Reuse existing validation, solely to decide which evidence is safe to
    # report. It cannot change the plan, its blocked verdict, or its sizing.
    try:
        plan = fresh['plan']
        rt.validate_plan(plan)
        blocked = plan.get('blocked_reasons')
        if not isinstance(blocked, list):
            return out
        source = {'blocked_reasons': sorted({code for code in blocked[:32]
                                            if type(code) is str and code in _NO_SEND_PLAN_CODES})}
        for key in ('reference_gross_usdt', 'planned_limit_gross_usdt'):
            value = plan.get(key)
            if type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,18})?', value):
                source[key] = value
        source['max_gross_usdt'] = policy['base_policy']['bounds']['max_gross_usdt']
        for key in ('captured_source_sha256', 'source_dossier_sha256', 'plan_id'):
            value = plan.get(key)
            if type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value):
                source[key] = value
        out['source_plan'] = source
        if (exception_code == 'INTENT_REFERENCE_PLAN_BLOCKED'
                and 'GROSS_CAP_EXCEEDED' in source['blocked_reasons']):
            out['reason_code'] = 'GROSS_CAP_EXCEEDED'
    except (KeyError, TypeError, ValueError, ArithmeticError):
        # Malformed evidence must not replace or expose the original failure.
        pass
    return out


def consume_batch_policy_once(store, policy, exact_go, go_ms, capture, *, clock):
    """Human-only integration hook, no CLI/automatic caller. One capture only."""
    validate_batch_policy(policy)
    if exact_go != GO_PREFIX + policy['batch_policy_id']:
        raise SourceError('NEW_EXACT_BATCH_GO_REQUIRED')
    dispatch_window(policy['base_policy'], go_ms, clock())
    store = Path(store)
    publish(store / 'batch-policy-claim.json', dict(batch_policy_id=policy['batch_policy_id'],
        exact_go=exact_go, go_ms=go_ms, accepted_ms=clock()))
    fresh = None
    stage = 'CAPTURE'
    try:
        fresh, caps = capture()
        stage = 'COMPILE'
        dossier = compile_after_go(policy['base_policy'], fresh, caps, go_ms=go_ms, now_ms=clock())
        stage = 'PAYLOAD_VALIDATION'
        payload(dossier['plan'])
        stage = 'MATERIALIZED_PUBLICATION'
        publish(store / 'batch-materialized.json', dict(batch_policy=policy, dossier=dossier))
        return dossier
    except Exception as exc:
        publish(store / 'batch-no-send.json',
                _no_send_diagnostic(exc, policy, fresh, stage, clock()))
        raise


def payload(plan):
    rt.validate_plan(plan)
    if plan['bounds']['max_gross_usdt'] != '215' or plan['blocked_reasons']:
        raise ValueError('BATCH_APPROVED_BOUNDS_REQUIRED')
    requests = []
    allowed = {'category', 'symbol', 'side', 'orderType', 'timeInForce', 'qty',
               'price', 'positionIdx', 'reduceOnly', 'orderLinkId', 'stopLoss',
               'slTriggerBy', 'slOrderType', 'tpslMode'}
    for leg in plan['legs']:
        r = leg['request']
        if (set(r) != allowed or r.get('tpslMode') != 'Full'
                or r.get('slOrderType') != 'Market' or r.get('slTriggerBy') != 'LastPrice'
                or not isinstance(r.get('orderLinkId'), str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', r['orderLinkId'])):
            raise ValueError('BATCH_EXACT_NATIVE_GUARD_REQUIRED')
        rt.numeric(r.get('stopLoss'))
        requests.append({k: copy.deepcopy(v) for k, v in r.items() if k != 'category'})
    if len({r['orderLinkId'] for r in requests}) != 10:
        raise ValueError('BATCH_LINKS_NOT_UNIQUE')
    return dict(category='linear', request=requests)


def batch_reducer(plan, state, event):
    kind = event.get('kind')
    if kind == 'ENTRY_INTENT':
        raise ValueError('SEQUENTIAL_ENTRY_FORBIDDEN_IN_BATCH_JOURNAL')
    if kind == 'BATCH_LOCAL_NO_SEND':
        rt.integer(event.get('at_ms'))
        if (event.get('source_sha256') != digest(event.get('no_wire_proof'))
                or event['no_wire_proof'].get('plan_id') != plan['plan_id']
                or event['no_wire_proof'].get('status') != 'FINAL_FENCE_NO_WIRE'
                or len(state['entries']) != 10 or any(o['order_id'] is not None
                    or rt.signed(o['filled']) != 0 or o['terminal'] for o in state['entries'].values())):
            raise ValueError('BATCH_LOCAL_NO_SEND_CONFLICT')
        s = copy.deepcopy(state)
        for o in s['entries'].values():
            o.update(terminal=True, terminal_quantity='0', local_not_sent=True)
        s.update(entry_blocked=True, phase='UNWINDING')
        return s
    if kind != 'BATCH_ENTRY_INTENT':
        return rt.apply_event(plan, state, event)
    rt.integer(event.get('at_ms'))
    body = payload(plan)
    if (event.get('event_id') != 'batch-entry-' + plan['plan_id']
            or event.get('source_sha256') != digest(body)
            or event.get('execution_mode') != MODE or state['entries']
            or state['phase'] != 'PREPARED' or state['entry_blocked']
            or state['ownership_conflict']):
        raise ValueError('BATCH_INTENT_CONFLICT')
    s = copy.deepcopy(state)
    s['entries'] = {l['symbol']: dict(symbol=l['symbol'], link=l['request']['orderLinkId'],
        order_id=None, filled='0', terminal=False, terminal_quantity=None,
        protected='0', stop_id=None) for l in plan['legs']}
    s.update(first_send_ms=event['at_ms'], deadline_ms=event['at_ms'] + plan['bounds']['duration_ms'],
             phase='ENTERING', execution_mode=MODE)
    return s


class BatchJournal(rt.MicroJournal):
    event_reducer = staticmethod(batch_reducer)

    def __init__(self, path, plan):
        payload(plan)
        p = Path(path)
        if p.is_symlink() or any(parent.is_symlink() for parent in p.absolute().parents):
            raise ValueError('JOURNAL_SYMLINK')
        if p.exists():
            # Never add DDL to a legacy book while discovering its identity.
            db = sqlite3.connect(p.absolute().as_uri() + '?mode=ro', uri=True)
            try:
                row = db.execute('SELECT mode FROM batch_meta').fetchall()
                if row != [(MODE,)]:
                    raise ValueError('BATCH_JOURNAL_IDENTITY_CONFLICT')
            except sqlite3.Error as exc:
                raise ValueError('LEGACY_JOURNAL_NOT_BATCH') from exc
            finally:
                db.close()
        super().__init__(path, plan)
        self.db.execute('CREATE TABLE IF NOT EXISTS batch_meta(mode TEXT NOT NULL)')
        if not self.db.execute('SELECT mode FROM batch_meta').fetchone():
            self.db.execute('INSERT INTO batch_meta VALUES(?)', (MODE,))


def commit_intent(journal, *, at_ms):
    if not isinstance(journal, BatchJournal) or journal.snapshot()['entries']:
        raise ValueError('BATCH_ALREADY_COMMITTED_RECONCILE_ONLY')
    return journal.append(dict(kind='BATCH_ENTRY_INTENT', at_ms=rt.integer(at_ms),
        event_id='batch-entry-' + journal.plan['plan_id'], execution_mode=MODE,
        source_sha256=digest(payload(journal.plan))))


def _event(kind, leg, response, at_ms, **fields):
    return dict(kind=kind, symbol=leg['symbol'], order_link_id=leg['request']['orderLinkId'],
        event_id=kind + '-' + digest(dict(leg=leg['symbol'], response=response)),
        at_ms=rt.integer(at_ms), source_sha256=digest(response), **fields)


def unknown_batch(journal, source, *, at_ms):
    for leg in journal.plan['legs']:
        journal.append(_event('DISPATCH_UNKNOWN', leg, source, at_ms))


def apply_ack(journal, response, *, at_ms):
    """ACK only. Persist all identifiable own IDs even if another item is unknown."""
    if len(journal.snapshot()['entries']) != 10:
        raise ValueError('DURABLE_BATCH_INTENT_REQUIRED')
    result = response.get('result') if isinstance(response, dict) else None
    extra = response.get('retExtInfo') if isinstance(response, dict) else None
    items = result.get('list') if isinstance(result, dict) else None
    codes = extra.get('list') if isinstance(extra, dict) else None
    valid = (isinstance(response, dict) and type(response.get('retCode')) is int and response['retCode'] == 0
             and isinstance(items, list) and isinstance(codes, list) and len(items) == len(codes) == 10)
    indexed = {}
    if valid:
        for row, code in zip(items, codes):
            if not isinstance(row, dict) or not isinstance(code, dict):
                valid = False
                break
            link = row.get('orderLinkId')
            if not isinstance(link, str) or link in indexed:
                valid = False
                break
            indexed[link] = (row, code)
        ids = [row.get('orderId') for row, _ in indexed.values() if row.get('orderId')]
        if len(ids) != len(set(ids)):
            valid = False
    if not valid:
        unknown_batch(journal, dict(reason='BATCH_ACK_SCHEMA_UNKNOWN', response=response), at_ms=at_ms)
        return dict(status='BATCH_UNKNOWN_RECONCILE_REQUIRED', orders_allowed=False)
    any_unknown = False
    for leg in journal.plan['legs']:
        row, detail = indexed.get(leg['request']['orderLinkId'], ({}, {}))
        code, oid = detail.get('code'), row.get('orderId')
        current = journal.snapshot()['entries'][leg['symbol']]
        identity = row.get('symbol') == leg['symbol']
        if identity and type(code) is int and code == 0 and isinstance(oid, str) and oid:
            if current['order_id'] not in (None, oid):
                journal.append(_event('DISPATCH_UNKNOWN', leg, response, at_ms))
                any_unknown = True
            else:
                journal.append(_event('ENTRY_ACK', leg, response, at_ms, order_id=oid))
        elif (identity and type(code) is int and code in rt.DEFINITE_CREATE_REJECT
              and oid == '' and current['order_id'] is None and rt.signed(current['filled']) == 0):
            journal.append(_event('DISPATCH_REJECTED', leg, response, at_ms, ret_code=code))
        else:
            journal.append(_event('DISPATCH_UNKNOWN', leg, response, at_ms))
            any_unknown = True
    if set(indexed) != {l['request']['orderLinkId'] for l in journal.plan['legs']}:
        unknown_batch(journal, dict(reason='FOREIGN_ACK_ITEM', response=response), at_ms=at_ms)
        any_unknown = True
    return dict(status='BATCH_UNKNOWN_RECONCILE_REQUIRED' if any_unknown else 'BATCH_ACK_RECONCILE_REQUIRED',
                orders_allowed=False)


class BatchSignedPostOnce(SignedPostOnce):
    """Same durable send barrier as the old writer; new endpoint, no retry."""
    def post(self, path, request):
        if path != '/v5/order/create-batch':
            return super().post(path, request)
        if (set(request) != {'category', 'request'} or request.get('category') != 'linear'
                or not isinstance(request.get('request'), list) or len(request['request']) != 10):
            raise SourceError('EXACT_TEN_BATCH_REQUIRED')
        raw = rt.canonical(request).encode()
        pin = digest(dict(path=path, request=request))
        at = self.clock()
        try:
            publish(self.store / ('send-' + pin + '.json'), dict(path=path, request=request,
                at_ms=at, status='INTENT_WIRE_MAY_HAVE_RUN'))
        except FileExistsError as exc:
            raise SourceError('SEND_ALREADY_RECORDED_RECONCILE_ONLY') from exc
        signature = hmac.new(self._secret.encode(), (str(at) + self._key + '10000').encode() + raw,
                             hashlib.sha256).hexdigest()
        headers = {'Content-Type': 'application/json', 'X-BAPI-API-KEY': self._key,
            'X-BAPI-TIMESTAMP': str(at), 'X-BAPI-RECV-WINDOW': '10000', 'X-BAPI-SIGN': signature}
        status, body = self.wire('POST', BASE + path, headers, raw, 3)
        if len(body) > 2_000_000 or self._key.encode() in body or self._secret.encode() in body:
            raise SourceError('BATCH_RESPONSE_BOUND_OR_SECRET_ECHO')
        publish(self.store / ('response-' + pin + '.json'), dict(http_status=status,
            raw=body.decode(), raw_sha256=sha(body), receive_ms=self.clock()))
        response = json.loads(body)
        if status != 200 or not isinstance(response, dict):
            raise SourceError('BATCH_ACK_UNKNOWN')
        return response


def dispatch_batch(journal, owner, *, now_ms, apply=False):
    if apply is not True:
        return dict(status='BATCH_ORDERS_OFF', orders_allowed=False)
    owner.assert_exclusive(journal.plan)
    body = payload(journal.plan)
    owner.validate_batch(journal.plan, body)  # actual fresh ticket, not a boolean attestation
    commit_intent(journal, at_ms=owner.clock())
    try:
        response = owner.post_once('/v5/order/create-batch', body)
    except Exception as exc:
        proof = getattr(owner, 'batch_no_wire_proof', None)
        if proof is not None:
            journal.append(dict(kind='BATCH_LOCAL_NO_SEND', no_wire_proof=proof,
                at_ms=owner.clock(), event_id='batch-local-no-send-' + journal.plan['plan_id'],
                source_sha256=digest(proof)))
            return dict(status='BATCH_NO_SEND_REQUIRES_FLAT_READBACK', orders_allowed=False)
        unknown_batch(journal, dict(reason=type(exc).__name__), at_ms=owner.clock())
        return dict(status='BATCH_UNKNOWN_RECONCILE_REQUIRED', orders_allowed=False)
    return apply_ack(journal, response, at_ms=owner.clock())


class FreshBatchView:
    """One bounded GET set reused by all ten unchanged entry validators.

    Metadata/account before books. Every raw source retains its real clocks;
    no cached value from an earlier cycle, no implicit GET on a missing key.
    """
    def __init__(self, reader, plan):
        self.reader, self.captures = reader, {}
        tasks = [('/v5/user/query-api', {}), ('/v5/account/info', {}),
                 ('/v5/account/wallet-balance', dict(accountType='UNIFIED')),
                 ('/v5/order/realtime', dict(category='linear', settleCoin='USDT', openOnly='0', limit='50')),
                 ('/v5/position/list', dict(category='linear', settleCoin='USDT', limit='200'))]
        for leg in plan['legs']:
            tasks.extend((p, dict(category='linear', symbol=leg['symbol'])) for p in (
                '/v5/market/instruments-info', '/v5/account/instruments-info',
                '/v5/position/list', '/v5/account/fee-rate', '/v5/market/tickers'))
        books = [('/v5/market/orderbook', dict(category='linear', symbol=l['symbol'], limit='50')) for l in plan['legs']]
        for group in (tasks, books):
            with cf.ThreadPoolExecutor(max_workers=10) as pool:
                jobs = {pool.submit(reader.get, p, v): digest(dict(path=p, params=v)) for p, v in group}
                for job in cf.as_completed(jobs):
                    self.captures[jobs[job]] = job.result()

    def get(self, path, params):
        try:
            return self.captures[digest(dict(path=path, params=params))]
        except KeyError as exc:
            raise SourceError('BATCH_CAPTURE_ROUTE_NOT_PRESENT') from exc

    def result(self, cap):
        return self.reader.result(cap)


def validate_batch_account_and_gross(view, plan):
    """Aggregate exposure, not ten individually affordable orders.

    Sell fills may improve above their limits and increase gross. A complete
    account-wide empty source is required in addition to per-symbol mode GETs.
    Missing pagination proof blocks; never infer flat from an empty first page.
    """
    orders = view.result(view.get('/v5/order/realtime', dict(category='linear', settleCoin='USDT', openOnly='0', limit='50')))
    positions = view.result(view.get('/v5/position/list', dict(category='linear', settleCoin='USDT', limit='200')))
    for source in (orders, positions):
        if not isinstance(source.get('list'), list) or source.get('nextPageCursor') != '':
            raise SourceError('BATCH_COMPLETE_ACCOUNT_SOURCE_REQUIRED')
    if orders['list'] or any(rt.numeric(p.get('size'), zero=True) > 0 for p in positions['list']):
        raise SourceError('BATCH_ACCOUNT_NOT_EXCLUSIVE_FLAT')
    gross, max_fee = rt.signed('0'), rt.signed('0')
    for leg in plan['legs']:
        symbol, side = leg['symbol'], leg['side']
        book = view.result(view.get('/v5/market/orderbook', dict(category='linear', symbol=symbol, limit='50')))
        if book.get('s') != symbol:
            raise SourceError('BATCH_BOOK_IDENTITY_CONFLICT')
        levels = _levels(book['a'] if side == 'Buy' else book['b'], side == 'Sell')
        gross += _vwap(levels, rt.numeric(leg['quantity']))[1]
        fees = view.result(view.get('/v5/account/fee-rate', dict(category='linear', symbol=symbol)))['list']
        if len(fees) != 1 or fees[0].get('symbol') != symbol:
            raise SourceError('BATCH_FEE_SOURCE_UNKNOWN')
        max_fee = max(max_fee, rt.numeric(fees[0]['takerFeeRate'], zero=True))
    if gross > rt.numeric(plan['bounds']['max_gross_usdt']):
        raise SourceError('BATCH_AGGREGATE_FRESH_GROSS_CAP')
    wallet = view.result(view.get('/v5/account/wallet-balance', dict(accountType='UNIFIED')))
    if rt.numeric(wallet['list'][0]['totalAvailableBalance'], zero=True) < gross * (1 + 2 * max_fee):
        raise SourceError('BATCH_AGGREGATE_FUNDS_REQUIRED')
    return gross


class BatchPhysicalOwner(PhysicalOwner):
    """Same physical account lease/platform verifier, different explicit GO.

    Not installed into the active writer by this module. Exit/cancel validation
    delegates to the existing owned recovery, never a second account writer.
    """
    def __init__(self, *args, dossier, batch_policy, inbox, **kwargs):
        super().__init__(*args, **kwargs)
        validate_batch_policy(batch_policy)
        verify_compilation(dossier)
        if (self.journal.plan != dossier['plan'] or batch_policy['base_policy'] != dossier['post_go_policy']
                or not isinstance(self.journal, BatchJournal)):
            raise SourceError('BATCH_PLAN_POLICY_CONFLICT')
        self.dossier, self.batch_policy, self.inbox = dossier, batch_policy, inbox
        self._batch_ticket = None

    def accept_go(self, text):
        raise SourceError('NEW_EXACT_BATCH_GO_REQUIRED')

    def _verify_claim(self):
        try:
            c = json.loads((self.store / 'batch-policy-claim.json').read_bytes())
        except (OSError, ValueError) as exc:
            raise SourceError('BATCH_LITERAL_CLAIM_MISSING_OR_CORRUPT') from exc
        if (c.get('exact_go') != GO_PREFIX + self.batch_policy['batch_policy_id']
                or c.get('batch_policy_id') != self.batch_policy['batch_policy_id']
                or c.get('go_ms') != self.dossier['post_go_go_ms']):
            raise SourceError('BATCH_LITERAL_CLAIM_CONFLICT')

    def entry_fence(self):
        dispatch_window(self.batch_policy['base_policy'], self.dossier['post_go_go_ms'], self.clock())
        if (not self.inbox.transport_fresh(self.clock()) or (self.store / 'rollback-request.json').exists()
                or (self.lease.path.parent / 'rollback-request.json').exists()):
            raise SourceError('BATCH_STREAM_OR_ROLLBACK_INHIBITS_ENTRY')

    def accept_batch_go(self, text):
        if text != GO_PREFIX + self.batch_policy['batch_policy_id']:
            raise SourceError('NEW_EXACT_BATCH_GO_REQUIRED')
        self.assert_exclusive(self.journal.plan)
        self._verify_claim()
        self.entry_fence()
        if self.journal.snapshot()['entries']:
            raise SourceError('BATCH_GO_ALREADY_CONSUMED')
        publish(self.store / 'batch-owner-go.json', dict(exact_go=text,
            plan_id=self.journal.plan['plan_id'], batch_policy_id=self.batch_policy['batch_policy_id'],
            go_ms=self.dossier['post_go_go_ms'], at_ms=self.clock()))
        self._authorized = True

    def recover_go(self):
        self._verify_claim()
        c = json.loads((self.store / 'batch-owner-go.json').read_bytes())
        if (c.get('exact_go') != GO_PREFIX + self.batch_policy['batch_policy_id']
                or c.get('plan_id') != self.journal.plan['plan_id']
                or c.get('batch_policy_id') != self.batch_policy['batch_policy_id']
                or c.get('go_ms') != self.dossier['post_go_go_ms']):
            raise SourceError('BATCH_GO_RECOVERY_CONFLICT')
        self.assert_exclusive(self.journal.plan)
        from research_lab.kity_micro_supervisor_v1 import recover_without_reentry
        recover_without_reentry(self.journal, self.clock())
        self._authorized = True  # owned unwind only; durable entry_blocked

    def validate_preflight(self, plan, request, role):
        if role == 'ENTRY':
            raise SourceError('SEQUENTIAL_ENTRY_FORBIDDEN_IN_BATCH_OWNER')
        return super().validate_preflight(plan, request, role)

    def validate_batch(self, plan, request):
        if not self._authorized:
            raise SourceError('NEW_EXACT_BATCH_GO_REQUIRED_ORDERS_OFF')
        self.assert_exclusive(plan)
        self.entry_fence()
        if request != payload(plan) or self.journal.snapshot()['entries']:
            raise SourceError('BATCH_ALREADY_COMMITTED_OR_REQUEST_CONFLICT')
        view = FreshBatchView(self.reader, plan)
        from research_lab.kity_micro_bounded_owner_v2 import account_instrument_available
        for leg in plan['legs']:
            cap = view.get('/v5/account/instruments-info', dict(category='linear', symbol=leg['symbol']))
            account_instrument_available(cap, leg['symbol'])
            validate_fresh_entry(view, self.journal, leg['request'], self.clock)
        validate_batch_account_and_gross(view, plan)
        self.entry_fence()
        self._batch_ticket = (digest(request), self.clock(), view)

    def post_once(self, path, request):
        if path != '/v5/order/create-batch':
            return super().post_once(path, request)
        self.batch_no_wire_proof = None
        try:
            self._before_batch_wire(request)
        except Exception as exc:
            proof = dict(status='FINAL_FENCE_NO_WIRE', plan_id=self.journal.plan['plan_id'],
                         reason=type(exc).__name__, at_ms=self.clock())
            publish(self.store / 'batch-final-fence-no-wire.json', proof)
            self.batch_no_wire_proof = proof
            raise
        # Exceptions from this point are ALWAYS uncertain dispatch, even if
        # the HTTP client raises before a response. Never mark them local-only.
        return self.post(path, request)

    def _before_batch_wire(self, request):
        self.assert_exclusive(self.journal.plan)
        self.entry_fence()
        ticket, self._batch_ticket = self._batch_ticket, None
        if (not self._authorized or not ticket or ticket[0] != digest(request)
                or not 0 <= self.clock() - ticket[1] <= 2000):
            raise SourceError('BATCH_FRESH_TICKET_REQUIRED')
        s = self.journal.snapshot()
        if (request != payload(self.journal.plan) or len(s['entries']) != 10
                or s['entry_blocked'] or any(o['order_id'] or o['terminal'] for o in s['entries'].values())):
            raise SourceError('DURABLE_EXACT_BATCH_INTENT_REQUIRED')
        # Recheck the same captured sources at physical send, never refresh or
        # derive a second pricing anchor after GO.
        for leg in self.journal.plan['legs']:
            validate_fresh_entry(ticket[2], self.journal, leg['request'], self.clock)
        validate_batch_account_and_gross(ticket[2], self.journal.plan)
        self.entry_fence()


class PrivateSession:
    """Private DATA socket only; no WebSocket trading operation exists here."""
    def __init__(self, key, secret, *, clock=now_ms, url=PRIVATE_URL):
        if url != PRIVATE_URL:
            raise ValueError('PRIVATE_DATA_URL_REQUIRED')
        self.key, self.secret, self.clock, self.url = key, secret, clock, url

    def auth_frame(self):
        expires = rt.integer(self.clock()) + 10000
        signature = hmac.new(self.secret.encode(), ('GET/realtime' + str(expires)).encode(), hashlib.sha256).hexdigest()
        return dict(op='auth', args=[self.key, expires, signature])

    def validate_outbound(self, frame):
        if frame.get('op') == 'auth':
            args = frame.get('args')
            if (not isinstance(args, list) or len(args) != 3 or args[0] != self.key
                    or type(args[1]) is not int or not self.clock() < args[1] <= self.clock() + 10000
                    or not hmac.compare_digest(str(args[2]), hmac.new(self.secret.encode(),
                        ('GET/realtime' + str(args[1])).encode(), hashlib.sha256).hexdigest())):
                raise ValueError('EXACT_PRIVATE_AUTH_REQUIRED')
        elif frame.get('op') == 'subscribe':
            args = frame.get('args')
            if not isinstance(args, list) or not args or len(set(args)) != len(args) or not set(args) <= set(TOPICS):
                raise ValueError('PRIVATE_TOPICS_ONLY')
        elif frame.get('op') != 'ping' or set(frame) != {'op'}:
            raise ValueError('PRIVATE_DATA_OPS_ONLY')
        return frame


class PrivateInbox:
    """Durable raw inbox. Only the writer thread projects financial events.

    Reconnect is a REST reconciliation barrier, never an invented gap fill.
    Projection is replayable: the financial journal deduplicates execId.
    """
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._connected = self._auth = self._sub = self._rest = False
        self.connection_id = None
        self.last_receive_ms = None

    def transport_fresh(self, at_ms):
        return self.ready and self.last_receive_ms is not None and 0 <= at_ms - self.last_receive_ms <= 20000

    @property
    def ready(self):
        return self._connected and self._auth and self._sub and self._rest

    def connected(self, connection_id):
        if not isinstance(connection_id, str) or not connection_id:
            raise ValueError('CONNECTION_ID_REQUIRED')
        self.connection_id = connection_id
        self._connected = True
        self._auth = self._sub = self._rest = False
        self.last_receive_ms = None

    def authenticated(self):
        if not self._connected:
            raise ValueError('PRIVATE_NOT_CONNECTED')
        self._auth = True

    def subscribed(self):
        if not self._auth:
            raise ValueError('PRIVATE_NOT_AUTHENTICATED')
        self._sub = True

    def rest_reconciled(self):
        if not self._sub:
            raise ValueError('PRIVATE_NOT_SUBSCRIBED')
        self._rest = True

    def disconnected(self, reason):
        self._connected = self._auth = self._sub = self._rest = False
        self.last_receive_ms = None

    def ingest(self, message, *, observed_ms):
        rt.integer(observed_ms)
        if not isinstance(message, dict) or message.get('topic') not in TOPICS or not isinstance(message.get('data'), list):
            raise ValueError('PRIVATE_TOPIC_SCHEMA')
        value = dict(connection_id=self.connection_id, observed_ms=observed_ms, message=message)
        raw = rt.canonical(value).encode()
        if len(raw) > 2_000_000:
            raise ValueError('PRIVATE_MESSAGE_SIZE_BOUND')
        name = f'{observed_ms:020d}-' + sha(raw) + '.json'
        try:
            publish(self.root / name, value)
        except FileExistsError:
            if json.loads((self.root / name).read_bytes()) != value:
                raise ValueError('PRIVATE_RAW_CONFLICT')

    def project(self, journal):
        count = 0
        for path in sorted(self.root.glob('*.json')):
            capture = json.loads(path.read_bytes())
            pin = sha(rt.canonical(capture).encode())
            if path.name != f"{capture['observed_ms']:020d}-" + pin + '.json':
                raise ValueError('PRIVATE_INBOX_HASH_CONFLICT')
            msg, at = capture['message'], capture['observed_ms']
            if msg['topic'] == 'position.linear':
                continue  # raw advisory only; complete REST snapshot owns flat/finality
            for row in msg['data']:
                s = journal.snapshot()
                owned = list(s['entries'].values()) + list(s['exits'].values())
                if not any((row.get('orderLinkId') == o['link'] if row.get('orderLinkId')
                            else row.get('orderId') == o['order_id'] and o['order_id'] is not None) for o in owned):
                    continue
                if row.get('category') not in (None, 'linear'):
                    raise ValueError('PRIVATE_CATEGORY_CONFLICT')
                # Replaying an already committed old native row against a
                # later resized stop would fail material validation. Verify
                # the financial chain first (snapshot above), then skip the
                # exact committed row events, not merely a socket/sequence ID.
                matching = next(o for o in owned if (row.get('orderLinkId') == o['link']
                    if row.get('orderLinkId') else row.get('orderId') == o['order_id'] and o['order_id'] is not None))
                role = 'EXIT' if matching['link'] in s['exits'] else 'ENTRY'
                kinds = [role+'_FILL'] if msg['topic']=='execution.linear' else [role+'_ACK']
                if msg['topic']=='order.linear' and row.get('orderStatus') in rt.TERMINAL:
                    kinds.append(role+'_TERMINAL')
                row_id = digest(dict(row=row, observed_ms=at))
                if all(journal.db.execute('SELECT 1 FROM events WHERE event_id=?', (kind+'-'+row_id,)).fetchone() for kind in kinds):
                    continue
                if msg['topic'] == 'execution.linear':
                    if row.get('execType') != 'Trade':
                        continue  # funding/settlements require actual transaction source
                    events = [execution_event(journal.plan, s, row, observed_ms=at)]
                else:
                    events = order_events(journal.plan, s, row, observed_ms=at)
                for e in events:
                    # Terminal can precede executions on the independent topic.
                    # The reducer keeps pending cumExecQty, never fabricates fills.
                    count += bool(journal.append(e))
        return count


class PrivateFeed:
    """Bounded synchronous private reader, used inside the single owner loop.

    Auth frames never go into raw evidence. Any error drops the REST barrier.
    No automatic reconnect, no order operations and no journal from this socket.
    """
    def __init__(self, session, inbox, *, connect=None, clock=now_ms):
        self.session, self.inbox, self.clock = session, inbox, clock
        self.connect = connect
        self.socket = None

    def send(self, frame):
        self.session.validate_outbound(frame)
        self.socket.send(rt.canonical(frame))

    def receive(self, timeout):
        raw = self.socket.recv(timeout=timeout)
        if len(raw) > 2_000_000:
            raise SourceError('PRIVATE_WIRE_SIZE_BOUND')
        message = json.loads(raw)
        if not isinstance(message, dict):
            raise SourceError('PRIVATE_WIRE_SCHEMA')
        at = self.clock()
        self.inbox.last_receive_ms = at
        if 'topic' in message:
            self.inbox.ingest(message, observed_ms=at)
        return message

    def _control(self, op):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            m = self.receive(max(.01, deadline - time.monotonic()))
            if m.get('op') == op:
                if m.get('success') is not True:
                    raise SourceError('PRIVATE_CONTROL_REJECTED:' + op)
                return m
        raise SourceError('PRIVATE_CONTROL_DEADLINE')

    def open(self):
        if self.socket is not None:
            raise SourceError('PRIVATE_ALREADY_CONNECTED')
        if self.connect is None:
            from websockets.sync.client import connect
            self.connect = connect
        try:
            self.socket = self.connect(self.session.url, open_timeout=5, close_timeout=2, max_size=2_000_000)
            self.inbox.connected('private-' + str(self.clock()))
            self.send(self.session.auth_frame())
            auth = self._control('auth')
            self.inbox.authenticated()
            self.send(dict(op='subscribe', args=list(TOPICS)))
            subscription = self._control('subscribe')
            self.inbox.subscribed()
            return dict(authenticated=True, subscribed_topics=list(TOPICS),
                        auth_response=auth, subscribe_response=subscription, rest_barrier_required=True)
        except Exception:
            self.close()
            raise

    def poll(self, timeout=.1):
        try:
            return self.receive(timeout)
        except TimeoutError:
            return None
        except Exception:
            self.close()
            raise

    def close(self):
        self.inbox.disconnected('SOCKET_CLOSED_REST_RECONCILIATION_REQUIRED')
        socket, self.socket = self.socket, None
        if socket is not None:
            socket.close()


def reconcile_private_barrier(journal, inbox, bridge):
    """Writer thread only: full existing REST reconciliation, then lift barrier."""
    inbox.project(journal)
    bridge.reconcile_orders()
    bridge.bind_native_protection()
    bridge.reconcile_positions()
    s = journal.snapshot()
    if s['ownership_conflict']:
        raise SourceError('BATCH_REST_OWNERSHIP_CONFLICT')
    if any(not rt._entry_complete(o) for o in s['entries'].values()):
        raise SourceError('BATCH_REST_PENDING_EXECUTIONS')
    if any(rt.signed(s['held'][symbol]) > rt.signed(o['protected']) for symbol, o in s['entries'].items()):
        raise SourceError('BATCH_REST_NATIVE_PROTECTION_UNKNOWN')
    inbox.rest_reconciled()
    return s


class BatchRuntime:
    """Single-writer integration: WS projection plus existing REST safety loop.

    Construction starts no process and grants no GO. The caller is the existing
    physical owner; its source/platform/lease bindings are retained. No new
    automatic entry path or per-leg sequential fallback is introduced.
    """
    def __init__(self, journal, reader, owner, feed, funding_spec):
        from research_lab.kity_micro_supervisor_v1 import Supervisor
        from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
        if not isinstance(journal, BatchJournal) or not isinstance(owner, BatchPhysicalOwner):
            raise SourceError('BATCH_PHYSICAL_BINDING_REQUIRED')
        self.journal, self.owner, self.feed = journal, owner, feed
        self.supervisor = Supervisor.__new__(Supervisor)
        s = self.supervisor
        s.journal, s.reader, s.owner, s.spec = journal, reader, owner, funding_spec
        s.bridge = MicroAccountBridge(journal, reader, owner=owner, clock=owner.clock)

    def reconcile_before_go(self):
        return reconcile_private_barrier(self.journal, self.feed.inbox, self.supervisor.bridge)

    def dispatch_once(self):
        return dispatch_batch(self.journal, self.owner, now_ms=self.owner.clock(), apply=True)

    def tick(self):
        if not self.owner._authorized:
            return dict(status='BATCH_ORDERS_OFF', orders_allowed=False)
        state = self.journal.snapshot()
        if not state['entries'] or state['phase'] == 'TERMINAL':
            return dict(status=state['phase'], orders_allowed=False)
        try:
            self.feed.poll()
            if not self.feed.inbox.transport_fresh(self.owner.clock()):
                raise SourceError('PRIVATE_STREAM_UNKNOWN')
            self.feed.inbox.project(self.journal)
        except Exception as exc:
            self.supervisor.unwind('BATCH_PRIVATE_STREAM:' + type(exc).__name__)
        # This path only maintains/unwinds the ten already-durable intents.
        # Existing $15/30min/native/restart/accounting invariants remain in force.
        errors = self.supervisor.cycle()
        return dict(status=self.journal.snapshot()['phase'], errors=errors or [], orders_allowed=False)
