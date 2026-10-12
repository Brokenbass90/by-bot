"""Transport-free Dynamic LIVE intake and native-protection handoff candidate.

No credentials, HTTP client, reservation, sender, env mutation or LIVE authority.
Input declarations/pins are not authenticated source proof. A later source-bound
integration must read the independent LIVE book under the original account lock.
Old monthly/PAPER guards and the deployed NET lifecycle remain unchanged.
"""
from decimal import Decimal, ROUND_DOWN, ROUND_CEILING

from research_lab.alpaca_dynamic_paper import _plan_check
from research_lab.alpaca_dynamic_v1 import dec, digest, instant, pin, positive, session_at
from scripts import equities_alpaca_paper_bridge as native

LIVE = 'https://api.alpaca.markets'
SCHEMA = 'ALPACA_DYNAMIC_LIVE_INTAKE_V1'
COMPATIBILITY = 'BASELINE_NATIVE_PROTECTION_DYNAMIC_SELECTION_V1'


def result(status, **fields):
    return dict(status=status, money_authority=False, orders_allowed=False,
                ready_for_live_go=False, evidence_kind='INPUT_PROVIDED_ORDERS_OFF', **fields)


def compile_intake(plan, policy, scope, now_ms):
    """Validate fresh independently LIVE-derived inputs; emit an inert BUY payload.

    No boolean GO can turn this compiler into a sender. Actual PAPER completion,
    source custody, owner GO and broker/account-lock integration remain external.
    """
    try:
        _, slot = _plan_check(plan, policy)
        now = instant(now_ms)
        if (scope['schema'] != SCHEMA or scope['endpoint'] != LIVE
            or scope['account_id'] != policy['account_id']
            or scope['policy_sha256'] != digest(policy)
            or scope['plan_sha256'] != digest(plan)
            or scope['source_plan_sha256'] != digest(plan)
            or scope['source_book_kind'] != 'LIVE_DYNAMIC_SEPARATE'
            or scope['compatibility'] != COMPATIBILITY):
            raise ValueError('DYNAMIC_LIVE_SOURCE_SCOPE_CONFLICT')
        if scope['paper_lifecycle_status'] != 'PAPER_EXECUTION_PASS':
            raise ValueError('PAPER_LIFECYCLE_PENDING')
        if (scope['old_terminal_entry_order_id'] != slot['entry_order_id']
            or scope['old_terminal_account_id'] != policy['account_id']
            or scope['old_terminal_evidence_kind'] != 'BROKER_LIVE'
            or positive(scope['old_terminal_qty']) != positive(slot['qty'])):
            raise ValueError('ACTUAL_OLD_VACANCY_REQUIRED_NO_PAPER_ADOPTION')
        for name in ('paper_lifecycle_sha256', 'old_terminal_sha256', 'original_shared_lock_sha256',
                     'native_manager_source_sha256', 'cost_source_sha256'):
            pin(scope[name])
        for name in ('single_entry_owner_verified', 'old_monthly_entries_off',
                     'single_manager_verified', 'tradable', 'earnings', 'concentration',
                     'reentry', 'protection'):
            if scope[name] is not True:
                raise ValueError('UNCONFIRMED_' + name.upper())
        if type(scope['owner_go']) is not bool:
            raise ValueError('INVALID_OWNER_GO_DECLARATION')
        if (not session_at(policy['calendar_sessions'], now)
            or not 0 <= now - plan['prepared_ms'] <= policy['max_snapshot_age_ms']
            or not 0 <= now - instant(scope['observed_ms']) <= policy['max_snapshot_age_ms']
            or not 0 <= now - instant(scope['quote_cts_ms']) <= policy['max_snapshot_age_ms']
            or scope['quote_cts_ms'] > scope['observed_ms']):
            raise ValueError('FRESH_CLOSED_SCOPE_REQUIRED')
        qty = positive(plan['qty'])
        if qty != qty.to_integral_value() and scope['fractionable'] is not True:
            raise ValueError('FRACTIONABLE_REQUIRED')
        positions, entries = scope['positions_before'], scope['session_entries_before']
        gross, reserve = dec(scope['gross_before_usd']), dec(scope['liability_reserve_usd'])
        cash = min(dec(scope['cash_usd']), dec(scope['nonmarginable_cash_usd']))
        if (type(positions) is not int or not 0 <= positions < policy['max_positions']
            or type(entries) is not int or entries != 0 or min(gross, reserve, cash) < 0
            or gross + positive(plan['notional_usd']) > dec(policy['capital_usd']) * dec(policy['gross'])
            or cash - reserve < positive(plan['funding_limit_usd'])):
            raise ValueError('CAP_OR_LIABILITY_FUNDING_REJECT')
        # Metadata can become fresher after restart; the exact reserved plan's
        # broker IDs cannot. The independent source book owns plan consumption.
        identity = digest(dict(schema=SCHEMA, endpoint=LIVE, account=policy['account_id'],
                               plan_sha256=digest(plan)))
        payload = dict(symbol=plan['symbol'], qty=plan['qty'], side='buy', type='limit',
            limit_price=format(positive(plan['reference_ask']).quantize(Decimal('.01'),rounding=ROUND_DOWN),'.2f'),
            time_in_force='day', client_order_id='dyl-'+identity[:32])
        r = result('LIVE_INTAKE_PREPARED_ORDERS_OFF', endpoint=LIVE, account_id=policy['account_id'],
            plan=plan, scope=scope, prepared_ms=now, entry_payload=payload,
            stop_client_order_id='dyf-'+identity[:32], owner_go_present=scope['owner_go'],
            compatibility=COMPATIBILITY, broker_writes=0, manager_installed=False)
        r['intake_sha256'] = digest(r)
        return r
    except (KeyError, TypeError, ValueError, ArithmeticError, StopIteration) as error:
        return result('BLOCKED_DATA', reason=str(error) or type(error).__name__)


class _Readbacks:
    """Pure recorded-source lookup for the unchanged native stop validator."""
    def __init__(self, orders):
        if len({o['id'] for o in orders}) != len(orders):
            raise ValueError('DUPLICATE_ORDER_SOURCE')
        self.orders = {o['id']:o for o in orders}

    def get_order(self, order_id):
        return self.orders[order_id]


def native_handoff(intake, entry, stop, *, observed_ms, existing=None):
    """Construct, but never install, the native manager's exact ownership record.

    The old strategy_id identifies the reused native protection algorithm; the
    separate selection-policy tag explicitly records Dynamic rather than monthly
    selection. No _load_intended_live_binding or monthly-role override occurs.
    """
    try:
        if not all(isinstance(source, dict) for source in (intake, entry, stop)):
            raise ValueError('MISSING_ORDER_OR_INTAKE_SOURCE')
        pin(intake['intake_sha256'])
        if (intake['intake_sha256'] != digest({k:v for k,v in intake.items() if k!='intake_sha256'})
            or intake['status'] != 'LIVE_INTAKE_PREPARED_ORDERS_OFF'
            or intake['compatibility'] != COMPATIBILITY
            or intake['orders_allowed'] is not False):
            raise ValueError('INTAKE_IDENTITY_CONFLICT')
        payload, plan, account = intake['entry_payload'], intake['plan'], intake['account_id']
        now = instant(observed_ms)
        for key, expected in payload.items():
            if key in {'qty','limit_price'}:
                if positive(entry[key]) != positive(expected):
                    raise ValueError('ENTRY_READBACK_CONFLICT')
            elif entry.get(key) != expected:
                raise ValueError('ENTRY_READBACK_CONFLICT')
        if entry.get('status') not in {'filled','canceled','expired'}:
            raise ValueError('ENTRY_NOT_TERMINAL')
        qty, price = positive(entry['filled_qty']), positive(entry['filled_avg_price'])
        stamp = native._parse_iso_utc(entry.get('filled_at',''))
        if (qty > positive(payload['qty']) or price > positive(payload['limit_price'])
            or stamp is None or not intake['prepared_ms'] <= int(stamp.timestamp()*1000) <= now):
            raise ValueError('ENTRY_FILL_SIZE_PRICE_OR_TIME_CONFLICT')
        requested = (price-positive(plan['risk_distance'])).quantize(Decimal('.01'),rounding=ROUND_CEILING)
        if not 0 < requested < price or stop.get('client_order_id') != intake['stop_client_order_id']:
            raise ValueError('STOP_FLOOR_OR_OWNER_CONFLICT')
        # Require Decimal-exact remaining quantity before the legacy float tolerance.
        if (positive(stop['qty']) != qty or dec(stop.get('filled_qty','0')) != 0
            or stop.get('status') not in {'new','accepted'}):
            raise ValueError('FULL_REMAINING_PROTECTION_REQUIRED')
        if stop.get('leaves_qty') not in (None, '') and positive(stop['leaves_qty']) != qty:
            raise ValueError('EXACT_REMAINING_PROTECTION_CONFLICT')
        confirmed = native._confirmed_intended_stop(_Readbacks([entry,stop]),stop,
            symbol=plan['symbol'],qty=float(qty),requested_stop=float(requested))
        floor = positive(confirmed['stop_price'])
        if not requested <= floor < price:
            raise ValueError('FILL_RELATIVE_FLOOR_CONFLICT')
        record = dict(entry_price=float(price), qty=float(qty), entry_fill_qty=float(qty),
            hwm=float(price), accepted_stop_floor=float(floor), entry_order_id=entry['id'],
            accepted_order_id=stop['id'], accepted_order_tif=stop['time_in_force'],
            lifecycle_first_seen_at_utc=entry['filled_at'], account_id=account,
            strategy_id=native._INTENDED_PAPER_STRATEGY_ID,
            entry_selection_policy='ALPACA_DYNAMIC_V1', dynamic_intake_sha256=intake['intake_sha256'])
        if existing is not None:
            prior = native._validated_existing_intended_lifecycle(existing,account)
            if (prior['entry_order_id'] != entry['id'] or dec(prior['qty']) != qty
                or dec(prior['entry_price']) != price or floor < dec(prior['accepted_stop_floor'])
                or prior.get('dynamic_intake_sha256') != intake['intake_sha256']):
                raise ValueError('EXISTING_NATIVE_LINEAGE_OR_FLOOR_CONFLICT')
            record['hwm'] = max(record['hwm'], prior['hwm'])
            record['lifecycle_first_seen_at_utc'] = prior['lifecycle_first_seen_at_utc']
        native._validated_existing_intended_lifecycle(record,account)
        return result('NATIVE_HANDOFF_PREPARED_ORDERS_OFF', native_record=record,
            native_record_sha256=digest(record), broker_writes=0, manager_installed=False)
    except (KeyError, TypeError, ValueError, ArithmeticError, native.IntendedPaperProtectionError) as error:
        return result('BLOCKED_DATA', reason=str(error) or type(error).__name__)
