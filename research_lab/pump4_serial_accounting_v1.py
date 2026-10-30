"""PUMP4 root accounting over unchanged authenticated GET capture contracts.

No transport, credential loader, sender, GO or financial release. The caller
must derive slots from the selected owner's durable lifecycle evidence; this
pure reducer cannot authenticate an arbitrary caller-created registry. Posted
amounts are known partial net, never a proof that no later costs can arrive.
"""
import copy
import re
from datetime import datetime, timezone
from decimal import Decimal

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.att1_lifecycle_journal import LifecycleJournal, SCHEMA
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_oct15_deadline_v1 import stable_bytes, decode
from research_lab.pump4_account_owner_v1 import safe
from research_lab.pump4_account_adapter_v1 import time_windows, TERMINAL
from research_lab.pump4_bybit_sources_v1 import account_view, paged, quote_for

DOMAIN = 'PUMP4_SERIAL_SOURCE_ACCOUNTING_V1'
D = Decimal


def need(ok, reason):
    if not ok:
        raise ValueError('PUMP4_SERIAL_SOURCE_' + reason)


def amount(value, *, nonnegative=False):
    need(isinstance(value, str), 'DECIMAL_STRING')
    n = D(value)
    need(n.is_finite() and (not nonnegative or n >= 0), 'AMOUNT')
    return n


def stamp(value):
    need(type(value) is int and value > 0, 'CLOCK')
    return value


def unique(rows, field):
    result = {}
    for row in rows:
        key = row[field]
        need(isinstance(key, str) and bool(key), 'ROW_IDENTITY')
        need(key not in result or result[key] == row, 'DUPLICATE_' + field)
        result[key] = copy.deepcopy(row)
    return result


def _registry(slots, now):
    requests, natives, result = {}, {}, []
    previous_end = 0
    for i, raw in enumerate(slots, 1):
        slot = copy.deepcopy(raw)
        need(slot['ordinal'] == i and type(slot['ordinal']) is int
             and re.fullmatch('[A-Z0-9]{1,24}USDT', slot['symbol'])
             and slot['side'] in ('long', 'short'), 'SLOT_IDENTITY')
        start = stamp(slot['first_send_ms'])
        end = now if slot['closed_ms'] is None else stamp(slot['closed_ms'])
        need(previous_end < start <= end <= now
             and (slot['closed_ms'] is not None or i == len(slots)), 'INTERVAL')
        previous_end = end
        need(isinstance(slot['requests'], list) and slot['requests'], 'REQUESTS_REQUIRED')
        for r in slot['requests']:
            cid = r['orderLinkId']
            need(isinstance(cid, str) and bool(cid) and cid not in requests
                 and r['category'] == 'linear' and r['symbol'] == slot['symbol']
                 and type(r['positionIdx']) is int and r['positionIdx'] == 0
                 and type(r['reduceOnly']) is bool, 'REQUEST_IDENTITY')
            side = 'Sell' if slot['side'] == 'short' else 'Buy'
            need(r['side'] == (('Buy' if side == 'Sell' else 'Sell') if r['reduceOnly'] else side)
                 and amount(r['qty'], nonnegative=True) > 0, 'REQUEST_SIDE_OR_QUANTITY')
            requests[cid] = (i, r)
        ids = slot['verified_native_ids']
        need(isinstance(ids, list) and len(ids) == len(set(ids)), 'NATIVE_IDS')
        for oid in ids:
            need(isinstance(oid, str) and bool(oid) and oid not in natives, 'NATIVE_IDENTITY')
            natives[oid] = i
        result.append(slot)
    return result, requests, natives


def source_view(bundle, slots, *, expected_fingerprint, now_ms):
    """Validate every page, then attribute actual amounts across serial slots.

    History is account-wide and anchored at the series start, not at the most
    recent child. Foreign activity remains visible and inhibits entry. Complete
    pagination and terminal orders do not establish fee/funding finality.
    """
    account = account_view(bundle, expected_fingerprint=expected_fingerprint, now_ms=now_ms)
    registry, requests, natives = _registry(slots, now_ms)
    begin, end = stamp(bundle['history_start_ms']), stamp(bundle['history_end_ms'])
    need(begin <= end <= now_ms and now_ms - end <= 5000
         and all(begin <= s['first_send_ms'] for s in registry), 'HISTORY_ANCHOR')
    windows = time_windows(begin, end)
    need(len(bundle['history_windows']) == len(windows), 'HISTORY_WINDOWS')
    collected = dict(history=[], executions=[], transactions=[])
    for w, (a, b) in zip(bundle['history_windows'], windows):
        need(w['start_ms'] == a and w['end_ms'] == b, 'HISTORY_GAP')
        for name, path, limit, extra in (
            ('history', '/v5/order/history', '50', {}),
            ('executions', '/v5/execution/list', '100', {}),
            ('transactions', '/v5/account/transaction-log', '50',
             dict(accountType='UNIFIED', currency='USDT')),
        ):
            params = dict(category='linear', startTime=str(a), endTime=str(b), limit=limit, **extra)
            rows = paged(w['groups'][name], path, params, now_ms=now_ms,
                         fingerprint=expected_fingerprint)
            clock_field = dict(history='updatedTime', executions='execTime',
                               transactions='transactionTime')[name]
            for row in rows:
                t = int(row[clock_field])
                # updatedTime may precede the requested create-time history
                # window; fills and settlements must lie within their page.
                need(0 < t <= now_ms and (name == 'history' or a <= t <= b), 'ROW_CLOCK_SCOPE')
            collected[name].extend(rows)
    records = {k: unique(v, dict(history='orderId', executions='execId', transactions='id')[k])
               for k, v in collected.items()}
    # Realtime and historical order rows have different schemas. Current orders
    # are checked separately for exposure; historical cumExecQty proves coverage.
    order_owner, order_cid = {}, {}
    unknown = []
    totals = {s['ordinal']: dict(cash=D(0), fee=D(0), funding=D(0), inventory=D(0),
                               entry_qty=D(0), exit_qty=D(0), executions=[])
              for s in registry}
    by_oid = {}
    for oid, row in records['history'].items():
        cid = row.get('orderLinkId', '')
        owner = requests.get(cid)
        ordinal = owner[0] if owner else natives.get(oid)
        if ordinal is None:
            unknown.append(dict(reason='FOREIGN_ORDER_HISTORY', source_id=oid))
            continue
        slot = registry[ordinal - 1]
        need(row['symbol'] == slot['symbol'] and type(row['positionIdx']) is int
             and row['positionIdx'] == 0, 'ORDER_SCOPE')
        need(row['orderStatus'] in TERMINAL | {'New', 'PartiallyFilled', 'Untriggered', 'Triggered'}, 'ORDER_STATUS')
        amount(row['cumExecQty'], nonnegative=True)
        if owner:
            req = owner[1]
            need(row['side'] == req['side'] and row['reduceOnly'] is req['reduceOnly']
                 and amount(row['cumExecQty'], nonnegative=True) <= amount(req['qty']), 'ORDER_REQUEST_CONFLICT')
            need(cid not in order_cid or order_cid[cid] == oid, 'ORDER_LINK_REUSED')
            order_cid[cid] = oid
        else:
            need(row.get('reduceOnly') is True and row.get('closeOnTrigger') is True
                 and row.get('stopOrderType') == 'StopLoss', 'NATIVE_PROVENANCE')
        if slot['closed_ms'] is not None:
            need(row['orderStatus'] in TERMINAL, 'CLOSED_SLOT_NONTERMINAL_ORDER')
        order_owner[oid] = ordinal
        by_oid[oid] = D(0)
    for eid, row in records['executions'].items():
        oid, cid = row['orderId'], row.get('orderLinkId', '')
        owner = requests.get(cid)
        ordinal = owner[0] if owner else natives.get(oid)
        if ordinal is None:
            unknown.append(dict(reason='FOREIGN_EXECUTION', source_id=eid))
            continue
        need(oid in order_owner and order_owner[oid] == ordinal
             and (not owner or order_cid.get(cid) == oid), 'EXECUTION_ORDER_PROOF')
        slot = registry[ordinal - 1]
        t = int(row['execTime'])
        need(slot['first_send_ms'] <= t <= (slot['closed_ms'] or now_ms)
             and row['symbol'] == slot['symbol'] and row['execType'] == 'Trade'
             and row['feeCurrency'] == 'USDT' and row['side'] in ('Buy', 'Sell'), 'EXECUTION_SCOPE')
        req_side = owner[1]['side'] if owner else ('Buy' if slot['side'] == 'short' else 'Sell')
        need(row['side'] == req_side, 'EXECUTION_SIDE')
        need('execFee' in row, 'EXECUTION_FEE_UNKNOWN')
        qty, price, fee = amount(row['execQty']), amount(row['execPrice']), amount(row['execFee'])
        need(qty > 0 and price > 0, 'EXECUTION_AMOUNT')
        state = totals[ordinal]
        state['cash'] += qty * price * (1 if row['side'] == 'Sell' else -1)
        state['fee'] += fee
        state['inventory'] += qty * (1 if row['side'] == 'Buy' else -1)
        state['entry_qty' if row['side'] == ('Sell' if slot['side'] == 'short' else 'Buy') else 'exit_qty'] += qty
        state['executions'].append((t, eid, row))
        by_oid[oid] += qty
    for oid, qty in by_oid.items():
        need(qty == amount(records['history'][oid]['cumExecQty'], nonnegative=True), 'EXECUTION_QUANTITY')
    # Every durable request must reconcile, even a rejected zero-fill request.
    need(all(cid in order_cid for cid in requests), 'MISSING_REQUEST_HISTORY')
    intervals = []
    for slot in registry:
        state = totals[slot['ordinal']]
        need(state['exit_qty'] <= state['entry_qty'], 'OVER_EXIT')
        if slot['closed_ms'] is not None:
            need(state['inventory'] == 0, 'CLOSED_SLOT_POSITION')
        # Funding ownership follows actual holding, not request/reservation time.
        held, opened = D(0), None
        for t, eid, row in sorted(state['executions']):
            q = amount(row['execQty'])
            is_entry = row['side'] == ('Sell' if slot['side'] == 'short' else 'Buy')
            if is_entry and held == 0:
                opened = t
            held += q if is_entry else -q
            need(held >= 0, 'EXECUTION_ORDER_AMBIGUOUS')
            if held == 0 and opened is not None:
                intervals.append((slot['ordinal'], slot['symbol'], opened, t))
                opened = None
        if held > 0:
            intervals.append((slot['ordinal'], slot['symbol'], opened, now_ms))
    for tid, row in records['transactions'].items():
        need(row.get('category') == 'linear' and row.get('currency') == 'USDT', 'TRANSACTION_SCOPE')
        if row['type'] == 'TRADE':
            # Execution history already charges the same trading fees. Preserve
            # this independent row, but never charge it twice or use it as finality.
            eid = row.get('tradeId')
            execution = records['executions'].get(eid) if isinstance(eid, str) else None
            if execution is None or execution['orderId'] != row.get('orderId') or execution['symbol'] != row.get('symbol') or amount(row['fee']) != amount(execution['execFee']):
                unknown.append(dict(reason='TRADE_TRANSACTION_RECONCILIATION_UNKNOWN', source_id=tid))
            continue
        if row['type'] != 'SETTLEMENT':
            unknown.append(dict(reason='UNCLASSIFIED_TRANSACTION_TYPE', source_id=tid))
            continue
        t = int(row['transactionTime'])
        candidates = [o for o, symbol, a, b in intervals if row['symbol'] == symbol and a < t < b]
        if len(candidates) != 1:
            unknown.append(dict(reason='FUNDING_OWNERSHIP_UNKNOWN', source_id=tid))
            continue
        totals[candidates[0]]['funding'] += amount(row['funding'])
    expected_positions = {}
    result_slots = []
    total = fee_total = funding_total = D(0)
    for slot in registry:
        state = totals[slot['ordinal']]
        inventory = state['inventory']
        mark = D(0)
        if inventory:
            quote_cap = bundle['captures']['quote']
            need(0 <= now_ms - quote_cap['request_ms'] <= 5000
                 and 0 <= now_ms - quote_cap['body']['time'] <= 5000, 'MARK_QUOTE_STALE')
            quote = quote_for(quote_cap, slot['symbol'], now_ms=now_ms)
            mark = inventory * amount(quote['bid1Price'] if inventory > 0 else quote['ask1Price'])
            expected_positions[slot['symbol']] = ('Buy' if inventory > 0 else 'Sell', abs(inventory))
        net = state['cash'] + mark - state['fee'] + state['funding']
        total += net
        fee_total += state['fee']
        funding_total += state['funding']
        result_slots.append(dict(ordinal=slot['ordinal'], symbol=slot['symbol'],
            known_net_usdt=str(net), posted_trade_fees_usdt=str(state['fee']),
            posted_funding_usdt=str(state['funding']), signed_inventory=str(inventory)))
    actual_positions = {}
    for row in account['positions']:
        qty = amount(row['size'], nonnegative=True)
        if qty:
            need(type(row['positionIdx']) is int and row['positionIdx'] == 0
                 and row['symbol'] not in actual_positions, 'POSITION_MODE')
            actual_positions[row['symbol']] = (row['side'], qty)
    exposure_matches = actual_positions == expected_positions
    for row in account['orders']:
        cid, oid = row.get('orderLinkId', ''), row['orderId']
        if cid not in requests and oid not in natives:
            unknown.append(dict(reason='FOREIGN_OPEN_ORDER', source_id=oid))
    if not exposure_matches:
        unknown.append(dict(reason='ACCOUNT_EXPOSURE_MISMATCH'))
    if account['borrowed_funds'] or account['margin_mode'] != 'REGULAR_MARGIN':
        unknown.append(dict(reason='ACCOUNT_BORROW_OR_MARGIN'))
    value = dict(schema='PUMP4_SERIAL_SOURCE_VIEW_V1', account_fingerprint=expected_fingerprint,
        observed_ms=now_ms, history_start_ms=begin, history_end_ms=end,
        capture_sha256=digest(bundle), registry=registry, registry_sha256=digest(registry),
        slots=result_slots, source_records=records, known_net_usdt=str(total),
        posted_trade_fees_usdt=str(fee_total), posted_funding_usdt=str(funding_total),
        account_exposure_matches=exposure_matches, account_open_orders_empty=account['open_orders_empty'],
        unclassified_activity=unknown,
        entry_inputs_complete=not unknown, cost_finality_proven=False,
        unposted_costs_usdt='UNKNOWN', release_next_entry_allowed=False,
        orders_allowed=False, money_authority=False)
    return dict(value, view_sha256=digest(value))


class SeriesAccounting:
    """Append-only partial source-risk evidence, never a next-entry permit.

    Caller holds the original single account lease. Journal append validates
    the complete candidate prefix under the existing nonblocking journal lock.
    Binding/policy cannot reset at a child restart or change of day/week.
    """
    def __init__(self, root, account_fingerprint, policy):
        need(re.fullmatch('[0-9a-f]{64}', account_fingerprint) is not None, 'ACCOUNT_FINGERPRINT')
        keys = {'day_loss_usdt', 'week_loss_usdt', 'drawdown_usdt', 'lifetime_loss_usdt'}
        need(set(policy) == keys and all(amount(policy[k]) > 0 for k in keys), 'LOSS_POLICY')
        self.root = safe(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.policy = copy.deepcopy(policy)
        self.binding = dict(schema='PUMP4_SERIAL_SOURCE_BINDING_V1', account_fingerprint=account_fingerprint,
                            policy=self.policy)
        self.binding_sha256 = digest(self.binding)
        target = self.root / 'accounting-binding.json'
        try:
            publish(target, self.binding)
        except FileExistsError:
            need(decode(stable_bytes(target)) == self.binding, 'BINDING_NO_RESET')
        self.journal = LifecycleJournal(self.root / 'source-risk.jsonl', max_record_bytes=8_388_608)
        self._validate(self.journal.read())

    def _check_binding(self):
        need(digest(self.binding) == self.binding_sha256 and self.binding['policy'] == self.policy
             and decode(stable_bytes(self.root / 'accounting-binding.json')) == self.binding, 'BINDING_DRIFT')

    def _validate(self, events):
        old = None
        for i, row in enumerate(events):
            need(row['domain'] == DOMAIN and row['binding_sha256'] == self.binding_sha256
                 and row['schema_id'] == SCHEMA and row['event_id'] == 'source-' + row['view']['view_sha256'], 'JOURNAL_BINDING')
            v = row['view']
            need(v['account_fingerprint'] == self.binding['account_fingerprint']
                 and v['view_sha256'] == digest({k: x for k, x in v.items() if k != 'view_sha256'})
                 and v['release_next_entry_allowed'] is False and v['cost_finality_proven'] is False, 'VIEW_IDENTITY')
            if old is not None:
                before = old['view']
                need(v['observed_ms'] >= before['observed_ms'] and v['history_start_ms'] == before['history_start_ms']
                     and v['history_end_ms'] >= before['history_end_ms'], 'HISTORY_CLOCK_NO_RESET')
                need(len(v['registry']) >= len(before['registry']), 'REGISTRY_SHRANK')
                for a, b in zip(before['registry'], v['registry']):
                    # Open slot may gain durable requests/native observations and
                    # later close. Existing request bytes and closed slots persist.
                    need(a['ordinal'] == b['ordinal'] and a['symbol'] == b['symbol']
                         and a['side'] == b['side'] and a['first_send_ms'] == b['first_send_ms']
                         and (a['closed_ms'] is None or a == b)
                         and b['requests'][:len(a['requests'])] == a['requests']
                         and set(a['verified_native_ids']) <= set(b['verified_native_ids']), 'REGISTRY_REWRITTEN')
                for group, rows in before['source_records'].items():
                    current = v['source_records'][group]
                    need(set(rows) <= set(current), 'SOURCE_HISTORY_SHRANK')
                    for key, a in rows.items():
                        b = current[key]
                        if group == 'executions':
                            need({k: x for k, x in a.items() if k != 'execFee'} ==
                                 {k: x for k, x in b.items() if k != 'execFee'}, 'EXECUTION_ID_REWRITTEN')
                        elif group == 'transactions':
                            need({k: x for k, x in a.items() if k != 'funding'} ==
                                 {k: x for k, x in b.items() if k != 'funding'}, 'TRANSACTION_ID_REWRITTEN')
                        else:
                            immutable = ('orderId', 'orderLinkId', 'symbol', 'side', 'positionIdx', 'reduceOnly')
                            need(all(a.get(k) == b.get(k) for k in immutable)
                                 and amount(b['cumExecQty'], nonnegative=True) >= amount(a['cumExecQty'], nonnegative=True)
                                 and (a['orderStatus'] not in TERMINAL or a['orderStatus'] == b['orderStatus']), 'ORDER_HISTORY_REWRITTEN')
            expected = self._event(v, old)
            need(row == expected, 'RISK_REPLAY_IDENTITY')
            old = row
        return old

    def _event(self, view, old):
        total = amount(view['known_net_usdt'])
        time = datetime.fromtimestamp(view['observed_ms'] / 1000, timezone.utc)
        day, week = time.date().isoformat(), list(time.isocalendar()[:2])
        previous_total = amount(old['known_net_usdt']) if old else D(0)
        daybase = amount(old['day_baseline_usdt']) if old and old['day'] == day else previous_total
        weekbase = amount(old['week_baseline_usdt']) if old and old['week'] == week else previous_total
        high = max(D(0), amount(old['high_water_usdt']) if old else D(0), total)
        reasons = [name for name, loss, key in (
            ('DAY', total - daybase, 'day_loss_usdt'), ('WEEK', total - weekbase, 'week_loss_usdt'),
            ('DRAWDOWN', total - high, 'drawdown_usdt'), ('LIFETIME', total, 'lifetime_loss_usdt'),
        ) if loss <= -amount(self.policy[key])]
        revisions = []
        if old:
            for group, field in (('executions', 'execFee'), ('transactions', 'funding')):
                for key, row in view['source_records'][group].items():
                    before = old['view']['source_records'][group].get(key)
                    if before is not None and before.get(field) != row.get(field):
                        revisions.append(dict(group=group, source_id=key, field=field,
                                              before=before.get(field), after=row.get(field)))
        return dict(schema_id=SCHEMA, event_id='source-' + view['view_sha256'], domain=DOMAIN,
            binding_sha256=self.binding_sha256, observed_ms=view['observed_ms'], view=view,
            known_net_usdt=str(total), day=day, week=week, day_baseline_usdt=str(daybase),
            week_baseline_usdt=str(weekbase), high_water_usdt=str(high), loss_reasons=reasons,
            entry_loss_latched=bool(reasons) or bool(old and old['entry_loss_latched']),
            cost_revisions=revisions, cost_finality_proven=False, release_next_entry_allowed=False,
            recognition_basis='SOURCE_OBSERVED_UTC_DAY_WEEK_NO_BACKDATED_RISK_RESET')

    def record(self, view):
        self._check_binding()
        rows = self.journal.read()
        old = self._validate(rows)
        for row in rows:
            if row['view']['view_sha256'] == view['view_sha256']:
                need(row['view'] == view, 'VIEW_REPLAY_CONFLICT')
                return row
        event = self._event(copy.deepcopy(view), old)
        self.journal.append_checked(event, self._validate)
        return event

    def summary(self):
        self._check_binding()
        rows = self.journal.read()
        last = self._validate(rows)
        return dict(source_observations=len(rows), entry_loss_latched=bool(last and last['entry_loss_latched']),
                    known_net_usdt=last['known_net_usdt'] if last else 'UNKNOWN',
                    cost_finality_proven=False, release_next_entry_allowed=False)
