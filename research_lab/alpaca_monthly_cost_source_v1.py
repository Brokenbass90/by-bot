"""Read-only cost producer for the existing Monthly book/finalizer. No orders.

Broker assessments remain account/day facts. Per-order cents below are an
explicit accounting allocation, not invented broker per-order fee activities.
Late revisions or an unexplained cash cent block new risk; protection continues.
"""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import hashlib
import time
from zoneinfo import ZoneInfo

from research_lab.alpaca_dynamic_v1 import dec, digest
from research_lab.alpaca_monthly_binding_v1 import CONTRACT, entry_cid
from research_lab.alpaca_fee_to_live_closure_v1 import reconcile_account_day_fees

ALLOCATION_POLICY = 'ACCOUNT_DAY_CENTS_LARGEST_REMAINDER_BY_FEE_BASIS_ORDER_ID_V1'
CENT = Decimal('.01')


def _ms(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None: raise ValueError('MONTHLY_COST_TIMEZONE_REQUIRED')
    return int(stamp.timestamp() * 1000)


def _allocate(total, weights):
    """Preserve each actual charged cent; deterministic tie break by order ID."""
    if total == 0: return {k: dec(0) for k in weights}
    denominator = sum(weights.values(), dec(0))
    if denominator <= 0: raise ValueError('MONTHLY_COST_ALLOCATION_BASIS_UNKNOWN')
    raw = {k: total * v / denominator for k, v in weights.items()}
    out = {k: v.quantize(CENT, rounding=ROUND_DOWN) for k, v in raw.items()}
    pennies = (total-sum(out.values(), dec(0))) / CENT
    if pennies != pennies.to_integral_value() or not 0 <= pennies <= len(raw):
        raise ValueError('MONTHLY_COST_ALLOCATION_CONFLICT')
    for k in sorted(raw, key=lambda k: (-(raw[k]-out[k]), k))[:int(pennies)]: out[k] += CENT
    if sum(out.values(), dec(0)) != total: raise ValueError('MONTHLY_COST_ALLOCATION_CONFLICT')
    return out


def derive_owned_exit_cost(*, source, protocol, calendar, assets, anchor,
                           positions, exits, entry_id, pending=False):
    """Derive one external finality document; caller pins/persists every input.

    Full raw source replay and the pinned retail protocol precede allocation.
    The native finalizer independently re-reads entry/exit orders, flatness and
    current cash. This function cannot release a slot, submit or enable anything.
    """
    proof = reconcile_account_day_fees(source, protocol=protocol, protocol_sha256=digest(protocol),
        calendar=calendar, calendar_sha256=digest(calendar), assets=assets, assets_sha256=digest(assets),
        pending=pending)
    def require(ok, reason):
        if not ok: raise ValueError('MONTHLY_COST_'+reason)
    account = source['account_after']
    liabilities=[dec(account[k]) for k in ('accrued_fees','pending_reg_taf_fees')]
    if pending:
        require(all(v>=0 for v in liabilities)
            and sum(liabilities,dec(0))<=dec(proof['unposted_account_fees_usd']), 'LIABILITY_UNCLASSIFIED')
    else:require(all(v==0 for v in liabilities), 'LIABILITY_PENDING')
    require(anchor.get('schema') == 'ALPACA_MONTHLY_CASH_ANCHOR_V1'
        and anchor.get('account_id') == source['account_id'] == anchor['account']['id']
        and anchor['account'].get('currency') == 'USD'
        and type(anchor.get('observed_ms')) is int
        and _ms(source['coverage']['after']) <= anchor['observed_ms'] < source['observed_ms'], 'ANCHOR_UNKNOWN')
    found = [r for r in exits if r['entry_id'] == entry_id]
    require(len(found) == 1, 'OWNED_EXIT_REQUIRED')
    target = found[0]; retired = target['retired_position']; entry = retired['raw_entry']
    require(anchor.get('client_order_id') == entry.get('client_order_id'), 'ANCHOR_OWNER')
    orders = {}; owner = {}
    for p in positions + [r['retired_position'] for r in exits]:
        order = p['raw_entry']; oid = p['entry_id']
        require(oid == order['id'] and order['side'] == 'buy'
            and order['symbol'] == p['symbol']
            and order.get('client_order_id') == entry_cid(p, p['symbol'])
            and oid not in orders, 'OWNERSHIP')
        orders[oid] = order; owner[oid] = oid
    for r in exits:
        require(sum((dec(o['filled_qty']) for o in r['orders']), dec(0)) == dec(orders[r['entry_id']]['filled_qty']), 'EXIT_QUANTITY')
        for order in r['orders']:
            require(order['id'] not in orders and order['side'] == 'sell'
                and order['symbol'] == r['retired_position']['symbol'], 'OWNERSHIP')
            orders[order['id']] = order; owner[order['id']] = r['entry_id']
    trades = defaultdict(list); basis = defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
    cash_moves = []; entry_times = []
    for row in source['activities']:
        kind = row['activity_type']
        if kind == 'FILL':
            oid = row.get('order_id'); require(oid in orders, 'FOREIGN_FILL')
            order = orders[oid]; at = _ms(row['transaction_time'])
            require(row['side'] == order['side'] and row['symbol'] == order['symbol']
                and at <= _ms(order['filled_at']), 'ORDER_FILL_CONFLICT')
            qty, price = dec(row['qty']), dec(row['price'])
            trades[oid].append(row)
            day = datetime.fromisoformat(row['transaction_time'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            basis[day]['CAT'][oid] += qty
            if row['side'] == 'sell': basis[day]['SEC'][oid] += qty*price
            exact = qty*price*(1 if row['side'] == 'sell' else -1)
            cash_moves.append((at, exact.quantize(CENT, rounding=ROUND_HALF_UP), oid, exact))
            if oid == entry_id: entry_times.append(at)
        elif kind == 'FEE':
            require(row.get('status') == 'executed' and row.get('currency') == 'USD'
                and row['id'] not in proof['uncovered_fee_activity_ids'], 'UNCOVERED_FEE')
            cash_moves.append((_ms(row['created_at']), dec(row['net_amount']), None, dec(row['net_amount'])))
        else:
            require(kind in {'DIV', 'INT', 'JNLC'} and row.get('status') == 'executed'
                and row.get('currency') == 'USD' and row.get('created_at'), 'UNCLASSIFIED_CASH_ACTIVITY')
            cash_moves.append((_ms(row['created_at']), dec(row['net_amount']), None, dec(row['net_amount'])))
    require(entry_times and anchor['observed_ms'] < min(entry_times), 'ANCHOR_AFTER_ENTRY')
    for oid, order in orders.items():
        rows = trades[oid]; qty = sum((dec(r['qty']) for r in rows), dec(0))
        require(qty > 0 and qty == dec(order['filled_qty']), 'ORDER_QUANTITY_CONFLICT')
        average = sum((dec(r['qty'])*dec(r['price']) for r in rows), dec(0))/qty
        reported = dec(order['filled_avg_price'])
        if average != reported:
            precision = protocol.get('execution_average_precision', {})
            places = precision.get('decimal_places')
            require(type(places) is int and 0 <= places <= 9
                and precision.get('rounding') == 'ROUND_HALF_UP'
                and precision.get('source_sha256') in {r.get('sha256') for r in protocol.get('sources', {}).values()}
                and isinstance(precision.get('source_sha256'), str)
                and len(precision['source_sha256']) == 64
                and all(c in '0123456789abcdef' for c in precision['source_sha256']), 'ORDER_AVERAGE_PRECISION_UNKNOWN')
            require(average.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP) == reported,
                'ORDER_PRICE_CONFLICT')
    allocations = {}; charge = defaultdict(Decimal)
    for day in proof['days']:
        allocations[day['session']] = {}
        for kind in ('CAT', 'SEC'):
            parts = _allocate(dec(day['posted'][kind]), basis[day['session']][kind])
            allocations[day['session']][kind] = {k: str(v) for k,v in sorted(parts.items())}
            for oid, amount in parts.items(): charge[owner[oid]] += amount
    moves = [r for r in cash_moves if anchor['observed_ms'] < r[0] <= source['observed_ms']]
    before = dec(anchor['account']['cash']); after = dec(account['cash'])
    require(before + sum((r[1] for r in moves), dec(0)) == after, 'ACCOUNT_CASH_CONFLICT')
    owned_ids = {entry_id} | {o['id'] for o in target['orders']}
    # Keep the existing native order-identity gross, but use actual execution
    # activities for economic PnL when a pinned display-precision model applies.
    gross = sum((dec(o['filled_qty'])*(dec(o['filled_avg_price'])-dec(entry['filled_avg_price'])) for o in target['orders']), dec(0))
    own_cash = sum((r[1] for r in moves if r[2] in owned_ids), dec(0))
    activity_gross = sum((r[3] for r in moves if r[2] in owned_ids), dec(0))
    allocated = charge[entry_id]
    # Other cash is derived from the complete cash movement list, never fitted
    # to the observed ending balance or supplied as a balancing adjustment.
    other = sum((r[1] for r in moves if r[2] not in owned_ids), dec(0)) + allocated
    require(allocated >= 0, 'FEE_ALLOCATION_TIMING')
    out=dict(schema='ALPACA_DYNAMIC_BROKER_COST_FINALITY_V1', account_id=source['account_id'],
        monthly_entry_id=entry_id,
        intake_sha256=digest(dict(schema=CONTRACT['schema'], entry_id=entry_id)),
        closure_status='ACCOUNT_DAY_FEES_RECONCILED', exit_orders_sha256=digest(target['orders']),
        gross_before_fees=str(gross), observed_ms=source['observed_ms'],
        coverage_end_ms=_ms(source['coverage']['until']), commission_usd='0',
        regulatory_fees_usd=str(allocated), unresolved_liability_usd='0',
        cash_before_entry=str(before), cash_after_exit=str(after), other_cash_net_usd=str(other),
        activity_gross_before_fees=str(activity_gross),
        reported_average_difference_usd=str(activity_gross-gross),
        broker_cash_rounding_usd=str(own_cash-activity_gross), allocation_policy=ALLOCATION_POLICY,
        account_day_allocations=allocations, broker_per_order_fee_attribution=False,
        source_sha256=digest(source), cash_anchor_sha256=digest(anchor), fee_day_proof_sha256=digest(proof),
        money_authority=False, orders_allowed=False)
    if pending:
        out.update(schema='ALPACA_MONTHLY_PENDING_FEE_ESTIMATE_V1',closure_status='PENDING_NOT_FINAL',
            unposted_account_fees_usd=proof['unposted_account_fees_usd'],
            known_net_before_pending_account_fees_usd=str(activity_gross-allocated),
            terminal_cost_finality_proven=False)
    return out


def _document(inputs, entry_id, *, pending=False):
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json
    from research_lab.alpaca_fee_to_live_closure_v1 import pin, check_rows
    check_rows(inputs.values())
    values = {name: read_json(row['path']) for name,row in inputs.items()}
    snapshot = values.pop('book_snapshot')
    if (snapshot['schema'] != 'ALPACA_MONTHLY_COST_BOOK_SNAPSHOT_V1'
        or snapshot['account_id'] != values['source']['account_id']):
        raise ValueError('MONTHLY_COST_BOOK_ACCOUNT')
    derived = derive_owned_exit_cost(**values, positions=snapshot['positions'], exits=snapshot['exits'],
        entry_id=entry_id,pending=pending)
    from research_lab import alpaca_fee_to_live_closure_v1, alpaca_monthly_native_binding_v1, alpaca_dynamic_live_runtime_v1
    from research_lab import alpaca_monthly_binding_v1, alpaca_dynamic_v1, alpaca_live_readiness_v1
    code = [pin(p) for p in (__file__, alpaca_fee_to_live_closure_v1.__file__,
        alpaca_monthly_native_binding_v1.__file__, alpaca_dynamic_live_runtime_v1.__file__,
        alpaca_monthly_binding_v1.__file__, alpaca_dynamic_v1.__file__, alpaca_live_readiness_v1.__file__)]
    files = [inputs[k] for k in sorted(inputs)] + code
    return dict(derived, replay_inputs=inputs, source_files=files, source_manifest_sha256=digest(files))


def verify_generated_source(document):
    """The existing finalizer replays producer inputs before accepting rounding."""
    if _document(document['replay_inputs'], document['monthly_entry_id']) != document:
        raise ValueError('MONTHLY_COST_PRODUCER_REPLAY_CONFLICT')


def pending_admission_net(native, *, account, now_ms, owner_scope=None):
    """Replay existing immutable evidence; reserve once, without finalizing PnL."""
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,safe_path
    def require(ok,reason):
        if not ok:raise ValueError('MONTHLY_PENDING_FEE_'+reason)
    started=time.monotonic()
    from research_lab.alpaca_live_readiness_v1 import execution_identity_v1
    def same_positions(retained,observed):
        require(len(retained)==len(observed),'BOOK_CONFLICT')
        for old,new in zip(retained,observed):
            execution_identity_v1(old['raw_entry'],new['raw_entry'])
            normalized=dict(new,raw_entry=old['raw_entry'])
            require(digest(normalized)==digest(old),'BOOK_CONFLICT')
    def same_book(snapshot):
        same_positions(native.book.rows('positions'),snapshot['positions'])
        retained=native.book.rows('exits');require(len(retained)==len(snapshot['exits']),'BOOK_CONFLICT')
        for old,new in zip(retained,snapshot['exits']):
            same_positions([old['retired_position']],[new['retired_position']])
            require(len(old['orders'])==len(new['orders']),'BOOK_CONFLICT')
            for before,after in zip(old['orders'],new['orders']):execution_identity_v1(before,after)
            normalized=dict(new,retired_position=old['retired_position'],orders=old['orders'])
            require(digest(normalized)==digest(old),'BOOK_CONFLICT')
    require(native.pending_fee_sources and type(now_ms) is int,'SOURCE_REQUIRED')
    known={};common=None;bound=None;pins={}
    for eid,path in sorted(native.pending_fee_sources.items()):
        p=safe_path(str(path),exists=True);doc=read_json(str(p))
        require(doc.get('schema')=='ALPACA_MONTHLY_PENDING_FEE_ESTIMATE_V1'
            and doc.get('monthly_entry_id')==eid,'ESTIMATE_REQUIRED')
        require(_document(doc['replay_inputs'],eid,pending=True)==doc,'REPLAY_CONFLICT')
        if native.base_url=='https://api.alpaca.markets':
            require(owner_scope is not None and doc['replay_inputs']['protocol']['sha256']==
                owner_scope.get('pending_fee_protocol_sha256'),'PROTOCOL_SCOPE_CONFLICT')
        snapshot=read_json(doc['replay_inputs']['book_snapshot']['path'])
        same_book(snapshot)
        source=read_json(doc['replay_inputs']['source']['path']);after=source['account_after']
        require(doc['account_id']==native.account==account.get('id')==after.get('id')
            and account.get('currency')==after.get('currency')=='USD','ACCOUNT_CONFLICT')
        require(all(dec(account[k])==dec(after[k]) for k in ('cash','accrued_fees','pending_reg_taf_fees')),
            'CASH_OR_LIABILITY_CHANGED')
        require(0<=now_ms-source['observed_ms']<=5000
            and 0<=now_ms-_ms(source['coverage']['until'])<=5000,'STALE_SOURCE')
        identity=(doc['source_sha256'],doc['replay_inputs']['book_snapshot']['sha256'])
        require(common is None or identity==common,'MIXED_SOURCES');common=identity
        amount=dec(doc['unposted_account_fees_usd'])
        require(amount>=0 and (bound is None or amount==bound),'BOUND_CONFLICT');bound=amount
        known[eid]=doc['known_net_before_pending_account_fees_usd']
        pins[eid]=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    require(bound<=native.liability,'RESERVE_EXCEEDED')
    lower=native._accounting_net(pending=known)-bound
    effective=now_ms+int((time.monotonic()-started)*1000)
    require(0<=effective-source['observed_ms']<=5000
        and 0<=effective-_ms(source['coverage']['until'])<=5000,'STALE_SOURCE')
    return lower,dict(policy='SOURCE_CLASSIFIED_WITHIN_EXISTING_RESERVE_V1',
        unposted_account_fees_usd=str(bound),cash_reserve_usd=str(native.liability),
        conservative_realized_net_usd=str(lower),sources=pins,
        source_observed_ms=source['observed_ms'],source_coverage_end_ms=_ms(source['coverage']['until']),
        terminal_cost_finality_proven=False)


def produce_cost_sources(native, *, source_path, protocol_path, calendar_path, assets_path, now_ms,
                         allow_pending=False):
    """Existing tick cost_sources callback: only order GETs + immutable evidence.

    Does not construct a controller/journal, load credentials, submit or invoke a
    financial wrapper. Caller already owns the Monthly manager dispatch guard.
    """
    from copy import deepcopy
    from pathlib import Path
    from research_lab.alpaca_dynamic_v1 import canonical
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json, safe_path, account_lock
    from research_lab.alpaca_fee_to_live_closure_v1 import pin
    from research_lab.alpaca_live_readiness_v1 import execution_identity_v1
    from research_lab.alpaca_monthly_source_ops_v1 import safe_path as safe_directory
    from research_lab.kity_oct15_deadline_v1 import publish_once
    def publish(path, value):
        raw = canonical(value)
        if path.exists():
            if safe_path(str(path), exists=True).read_bytes() != raw:
                raise ValueError('MONTHLY_COST_IMMUTABLE_CONFLICT')
        else: publish_once(path, raw)
    if type(allow_pending) is not bool:raise ValueError('MONTHLY_COST_EXPLICIT_MODE_REQUIRED')
    paths = dict(source=source_path, protocol=protocol_path, calendar=calendar_path, assets=assets_path)
    inputs = {name: pin(path) for name,path in paths.items()}
    source = read_json(inputs['source']['path'])
    if (source['account_id'] != native.account or type(now_ms) is not int
        or not source['observed_ms'] <= now_ms): raise ValueError('MONTHLY_COST_SOURCE_ACCOUNT_OR_TIME')
    with account_lock(dict(lock_path=str(native.lock_path))):
        positions = deepcopy(native.book.rows('positions')); exits = deepcopy(native.book.rows('exits'))
        if not exits: return {}
        for p in positions + [e['retired_position'] for e in exits]:
            current = native.client.get_order(p['entry_id'])
            execution_identity_v1(p['raw_entry'], current); p['raw_entry'] = current
        for e in exits:
            for i,old in enumerate(e['orders']):
                current = native.client.get_order(old['id'])
                execution_identity_v1(old, current); e['orders'][i] = current
        snapshot = dict(schema='ALPACA_MONTHLY_COST_BOOK_SNAPSHOT_V1', account_id=native.account,
            positions=positions, exits=exits)
        root = safe_directory(native.runtime/'cost-sources'/digest(dict(inputs=inputs, snapshot=snapshot)))
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        snapshot_path = root/'book-snapshot.json'; publish(snapshot_path, snapshot)
        inputs['book_snapshot'] = pin(snapshot_path); out = {}
        for e in exits:
            eid = e['entry_id']; cid = e['retired_position']['raw_entry']['client_order_id']
            if cid != entry_cid(e['retired_position'], e['symbol']): raise ValueError('MONTHLY_COST_ANCHOR_OWNER')
            anchor_path = safe_path(str(native.runtime/'cash-anchors'/(cid+'.json')), exists=True)
            selected = dict(inputs, anchor=pin(anchor_path))
            try:document = _document(selected, eid)
            except ValueError as exc:
                if not allow_pending or str(exc) not in {
                    'COST_FEE_DAY_COVERAGE_OR_SESSION_NOT_CLOSED','COST_FEE_POSTING_PENDING_OR_CONFLICT'}:raise
                document=_document(selected,eid,pending=True)
            # A later as-of capture may reveal a correction. Never overwrite a
            # previously finalized allocation or silently keep stale net PnL.
            identity = digest(dict(schema=CONTRACT['schema'], entry_id=eid))
            import sqlite3, json
            store = native.runtime/'safety'/identity/'live.sqlite'
            if store.is_file():
                with sqlite3.connect(safe_path(str(store), exists=True).as_uri()+'?mode=ro', uri=True) as db:
                    row = db.execute('SELECT payload FROM intents WHERE id=?', (identity,)).fetchone()
                item = json.loads(row[0]) if row else {}
                if item.get('cost_finality'):
                    old = read_json(item['monthly_cost_source_path'])
                    if any(old.get(k) != document.get(k) for k in ('regulatory_fees_usd', 'commission_usd', 'gross_before_fees')):
                        raise ValueError('MONTHLY_FINALIZED_ALLOCATION_REVISED')
                    continue
            path = root/(eid+'.json')
            if Path(eid).name != eid or eid in {'', '.', '..'}: raise ValueError('MONTHLY_COST_ORDER_ID')
            publish(path, document); out[eid] = str(path)
        return out


def capture_and_produce_cost_sources(native, *, after, protocol_path, calendar_path, assets_path, now_ms=None,
                                    allow_pending=False):
    """Automatic read-only source callback for the one existing dispatcher.

    No exits means no accounting capture. Immutable raw source is kept even when
    fees are pending; a later tick may collect newly posted assessments without
    submitting a trade or overwriting prior evidence. Metadata inputs remain pinned.
    """
    import json
    from research_lab.alpaca_dynamic_v1 import canonical
    from research_lab.alpaca_fee_to_live_closure_v1 import collect_account_cost_source, CostSourceCaptureError
    from research_lab.alpaca_monthly_source_ops_v1 import safe_path
    from research_lab.kity_oct15_deadline_v1 import publish_once
    if not native.book.rows('exits'):return {}
    raw_clock=None
    try:
        raw_clock=native.client.cost_get('/v2/clock',{})
        if raw_clock['http_status']!=200:raise ValueError('MONTHLY_COST_CLOCK_GET_FAILED')
        if raw_clock.get('raw_truncated') or not isinstance(raw_clock.get('raw'),str):
            raise ValueError('MONTHLY_COST_CLOCK_RAW_REQUIRED')
        clock=json.loads(raw_clock['raw'])
        source=collect_account_cost_source(native.client.cost_get,account_id=native.account,
            after=after,until=clock['timestamp'],now_ms=now_ms)
    except Exception as exc:
        failed=dict(schema='ALPACA_COST_CAPTURE_FAILED_V1',reason=str(exc),clock_capture=raw_clock,
            captures=list(exc.captures) if isinstance(exc,CostSourceCaptureError) else [],
            request=exc.request if isinstance(exc,CostSourceCaptureError) else dict(route='/v2/clock',query={}))
        path=safe_path(native.runtime/'cost-captures'/('failed-'+digest(failed)+'.json'))
        if not path.exists():publish_once(path,canonical(failed))
        raise
    root=safe_path(native.runtime/'cost-captures'/digest(source));root.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=root/'source.json'
    if path.exists():
        if path.read_bytes()!=canonical(source):raise ValueError('MONTHLY_COST_IMMUTABLE_CONFLICT')
    else:publish_once(path,canonical(source))
    clock_path=root/'clock.json'
    # The source can repeat byte-for-byte under a deterministic reader. Keep the
    # first clock receipt, and never replace its timestamps on replay.
    if not clock_path.exists():publish_once(clock_path,canonical(raw_clock))
    return produce_cost_sources(native,source_path=path,protocol_path=protocol_path,
        calendar_path=calendar_path,assets_path=assets_path,now_ms=source['observed_ms'] if now_ms is None else now_ms,
        allow_pending=allow_pending)
