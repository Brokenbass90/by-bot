"""Saved-source cap300 calculation, never a live plan, policy or money permit.

The existing cap215 owner validators and deployed financial code are untouched.
Reuse their frozen geometry, fee parsing and native-stop derivation. A capacity
fit is dated arithmetic; it cannot authorize a writer or guarantee a loss cap.
"""
import copy
import hashlib
import json
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path

from bot.kity_m3_orders_off import _levels, _vwap, digest
from research_lab.kity_execution_micro_runtime_v1 import BASKET, _owner_bounds
from research_lab.kity_execution_micro_v1 import numeric
from research_lab.kity_micro_feasibility_v1 import assess_market_geometry
from research_lab.kity_micro_preflight_v1 import attach_native_guards, build_preflight

CAP = D('300')
TRIGGER = D('15')
COLLAR = D('.005')
DURATION = 1800000


def _scaled_rows(rows, multiplier):
    result = copy.deepcopy(rows)
    for row in result:
        tick = numeric(row['tick'])
        for key, rounding in [('bids', ROUND_FLOOR), ('asks', ROUND_CEILING)]:
            row[key] = [[str((D(p) * multiplier / tick).to_integral_value(rounding=rounding) * tick), q]
                        for p, q in row[key]]
        row['bid'] = row['bids'][0][0]
        row['price'] = row['asks' if row['side'] == 'Buy' else 'bids'][0][0]
    return result


def calculate_proposal(rows, instruments, *, observed_ms, original_bounds):
    """Market/account-setting inputs only. No I/O and no selected live bounds."""
    bounds = _owner_bounds(original_bounds)  # STILL rejects an edited 300 policy.
    if bounds['max_gross_usdt'] != '215':
        raise ValueError('ORIGINAL_215_BOUNDS_REQUIRED')
    if type(observed_ms) is not int or observed_ms <= 0:
        raise ValueError('OBSERVED_CLOCK_REQUIRED')
    if [(i['symbol'], i['side']) for i in instruments] != list(BASKET):
        raise ValueError('EXACT_INSTRUMENTS_REQUIRED')
    geometry = assess_market_geometry(rows, bounds)
    fees = spread = margin = collar_fees = collar_margin = funding = D(0)
    long = short = D(0)
    legs = []
    profile = {'legs': []}
    for row, leg, instrument in zip(rows, geometry['legs'], instruments):
        if any(D(instrument[a]) != D(row[b]) for a,b in (
                ('tick_size','tick'), ('quantity_step','step'), ('minimum_quantity','minimum'),
                ('minimum_notional','min_notional'))):
            raise ValueError('INSTRUMENT_METADATA_CONFLICT')
        if type(instrument['position_idx']) is not int or instrument['position_idx'] != 0:
            raise ValueError('UNCHANGED_ONE_WAY_MODE_REQUIRED')
        rate = numeric(instrument['taker_fee'], zero=True)
        leverage = numeric(instrument['configured_leverage'])
        if rate >= 1:
            raise ValueError('FEE_SOURCE_INVALID')
        quantity = D(leg['qty']); price = D(leg['limit_price']); tick = numeric(row['tick'])
        bids, asks = _levels(row['bids'], True), _levels(row['asks'], False)
        if D(row['bid']) != bids[0][0] or D(row['price']) != (asks if row['side'] == 'Buy' else bids)[0][0]:
            raise ValueError('TOP_OF_BOOK_CONFLICT')
        if bids[0][0] >= asks[0][0] or any(p % tick for p, _ in bids + asks):
            raise ValueError('BOOK_OR_PRICE_GRID_CONFLICT')
        entry = D(leg['depth_notional'])
        _, exit_notional = _vwap(bids if row['side'] == 'Buy' else asks, quantity)
        high = (price * (1 + COLLAR) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
        low = (price * (1 - COLLAR) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
        if low <= 0 or low > price or high < price:
            raise ValueError('COLLAR_NOT_FEASIBLE')
        collar_entry = high if row['side'] == 'Buy' else low
        fees += (entry + exit_notional) * rate
        spread += abs(entry - exit_notional)
        margin += entry / leverage
        collar_fees += (quantity * high + exit_notional) * rate
        collar_margin += quantity * high / leverage
        next_ms = int(instrument['next_funding_ms'])
        interval = instrument['funding_interval_minutes']
        if type(interval) is not int or interval <= 0 or next_ms <= observed_ms:
            raise ValueError('FUNDING_CALENDAR_UNKNOWN')
        upper, lower = D(instrument['funding_upper']), D(instrument['funding_lower'])
        if not upper.is_finite() or not lower.is_finite() or upper < 0 or lower > 0 or max(upper, -lower) >= 1:
            raise ValueError('FUNDING_LIMIT_UNKNOWN')
        observed_rate = D(instrument['funding_rate_observed'])
        if not observed_rate.is_finite() or not lower <= observed_rate <= upper:
            raise ValueError('OBSERVED_FUNDING_UNKNOWN')
        adverse_rate = upper if row['side'] == 'Buy' else -lower
        end = observed_ms + DURATION
        count = 0 if next_ms > end else (end - next_ms) // (interval * 60000) + 1
        reserve = quantity * high * adverse_rate * count
        funding += reserve
        if row['side'] == 'Buy': long += entry
        else: short += entry
        legs.append(dict(leg, taker_fee_rate=str(rate), configured_leverage=str(leverage),
                         entry_notional_usdt=str(entry), exit_depth_notional_usdt=str(exit_notional),
                         collar_min_price=str(low), collar_max_price=str(high),
                         collar_entry_price=str(collar_entry), funding_events_30min=count,
                         next_funding_ms=next_ms, funding_interval_minutes=interval,
                         observed_funding_rate=instrument['funding_rate_observed'],
                         adverse_funding_rate_limit=str(adverse_rate), funding_reserve_usdt=str(reserve)))
        profile['legs'].append({'draft_entry': {'qty': str(quantity), 'price': str(collar_entry), 'side': row['side']}})
    profile['constant_price_roundtrip_fees'] = str(collar_fees)
    attach_native_guards(profile, instruments, TRIGGER, funding)
    guard_loss = guard_fees = collar_entry_total = D(0)
    for leg, draft in zip(legs, profile['legs']):
        req = draft['draft_entry']; q = D(leg['qty']); stop = D(req['stopLoss'])
        entry = D(leg['collar_entry_price'])
        leg['native_stop_draft'] = str(stop)
        leg['native_stop_distance_fraction'] = str(abs(entry - stop) / entry)
        guard_loss += q * abs(entry - stop)
        guard_fees += q * (entry + stop) * D(leg['taker_fee_rate'])
        collar_entry_total += q * entry
    needed = D(geometry['minimum_required_reference_gross'])
    band_gross = D(geometry['collar_high_envelope_gross'])
    grows = []
    for multiplier in ('1', '1.01', '1.05', '1.10', '1.15', '1.20', '1.25', '1.50'):
        g = assess_market_geometry(_scaled_rows(rows, D(multiplier)), bounds)
        grows.append({'uniform_price_multiplier': multiplier,
                      'required_gross_usdt': g['minimum_required_reference_gross'],
                      'collar_high_gross_usdt': g['collar_high_envelope_gross'],
                      'capacity_status': 'FITS' if max(D(g['minimum_required_reference_gross']), D(g['collar_high_envelope_gross'])) <= CAP else 'BLOCKED'})
    max_fee = max(D(i['taker_fee']) for i in instruments)
    stresses = []
    for gap in ('0', '0.01', '0.05', '0.10', '0.25'):
        # Conservative fixed-notional illustration: every leg moves adversely
        # after the trigger; add 50bp exit friction and its incremental fee.
        extra = CAP * (D(gap) + (1 + D(gap)) * COLLAR) * (1 + max_fee)
        stresses.append({'gross_basis_usdt': '300', 'adverse_move_fraction': gap,
                         'extra_exit_friction_fraction': str(COLLAR),
                         'scenario_loss_usdt': str(TRIGGER + extra)})
    result = dict(schema='KITY_CAP300_CALCULATION_PROPOSAL_V1',
                  status='PROPOSAL_ONLY_AWAIT_OWNER_AND_NEW_BINDING',
                  original_bounds_sha256=digest(bounds), observed_ms=observed_ms,
                  proposed_gross_cap_usdt='300', loss_exit_trigger_usdt='15',
                  capacity_status='FITS_PROPOSED_CAP' if max(needed, band_gross) <= CAP else 'CAPACITY_BLOCKED',
                  minimum_required_gross_usdt=str(needed), common_target_usdt=geometry['minimum_common_target'],
                  collar_high_gross_usdt=str(band_gross), collar_actual_entry_gross_usdt=str(collar_entry_total),
                  reference_headroom_usdt=str(CAP - needed), collar_headroom_usdt=str(CAP - band_gross),
                  uniform_growth_headroom_fraction=str(CAP / needed - 1),
                  growth_headroom_is_nonuniform_market_guarantee=False,
                  long_gross_usdt=str(long), short_gross_usdt=str(short), net_direction_usdt=str(long - short),
                  constant_price_roundtrip_fees_usdt=str(fees), constant_price_spread_usdt=str(spread),
                  constant_price_roundtrip_cost_usdt=str(fees + spread),
                  initial_margin_reference_usdt=str(margin), initial_margin_collar_reference_usdt=str(collar_margin),
                  margin_is_exact_exchange_requirement=False, leverage_changed=False,
                  collar_roundtrip_fee_reserve_usdt=str(collar_fees), funding_reserve_30min_usdt=str(funding),
                  fully_funded_reference_plus_reserves_usdt=str(band_gross + collar_fees + funding),
                  full_cap_plus_fee_reserve_usdt=str(CAP + CAP * 2 * max_fee + funding),
                  one_extra_funding_event_at_current_limits_usdt=str(sum((D(l['qty']) * D(l['collar_max_price']) * D(l['adverse_funding_rate_limit']) for l in legs), D(0))),
                  native_guard_price_loss_usdt=str(guard_loss),
                  native_guard_ideal_all_stops_cost_usdt=str(guard_loss + guard_fees + funding),
                  guaranteed_final_loss_cap_usdt=None, stress_is_guaranteed_bound=False,
                  loss_scenario_assumptions='Fixed gross <=300; every held leg adverse after threshold; additional 50bp exit friction; unchanged fees, no new funding or execution failure. Illustrations, not upper loss bounds.',
                  failure_risks=['GAP_OR_EXIT_SLIPPAGE', 'PARTIAL_OR_UNKNOWN_FILL', 'EXCHANGE_OR_NETWORK_OUTAGE',
                                 'LASTPRICE_STOP_VS_MARKPRICE_LIQUIDATION', 'SHARED_CROSS_COLLATERAL', 'FUNDING_LIMIT_OR_FEE_CHANGE'],
                  after_trigger_stresses=stresses, price_growth_scenarios=grows, legs=legs,
                  duration_ms=DURATION, entry_window_ms=60000, collar_bps='50', common_cts_max_ms=2000,
                  max_rounding_shortfall_fraction=bounds['max_rounding_shortfall_fraction'],
                  attempts=1, allow_reentry=False, allow_scaling=False, allow_averaging=False,
                  orders_allowed=False, money_authority=False, source_fresh_for_dispatch=False,
                  new_policy_created=False, old_attempt_reusable=False, owner_command=None,
                  broker_writes=0, broker_requests=0, research_evidence_eligible=False, counts_toward_C1_C2_C3=False)
    result['proposal_id'] = digest(result)
    return result


def build_saved_proposal(path, expected_sha, original_bounds):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('PROPOSAL_CAPTURE_PATH')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('CAPTURE_PIN_CONFLICT')
    # Full existing raw source/account/permissions/cursor parser, still cap215.
    dossier = build_preflight(path, expected_sha, original_bounds)
    wrapper = json.loads(raw); source = wrapper['response']; caps = source['captures']
    for value in caps.values():
        for cap in value.get('pages', [value]):
            if cap.get('error_type') or cap.get('http_status') != 200 or cap.get('body', {}).get('retCode') != 0:
                raise ValueError('CAPTURE_SOURCE_UNKNOWN')
            if 'raw' in cap and (hashlib.sha256(cap['raw'].encode()).hexdigest() != cap.get('raw_sha256') or json.loads(cap['raw']) != cap['body']):
                raise ValueError('CAPTURE_RAW_CONFLICT')
    rows = []
    for i in dossier['instruments']:
        symbol = i['symbol']; book = caps['book:' + symbol]['body']['result']
        lot = caps['instrument:' + symbol]['body']['result']['list'][0]['lotSizeFilter']
        rows.append(dict(symbol=symbol, side=i['side'], price=book['a'][0][0] if i['side']=='Buy' else book['b'][0][0],
                         bid=book['b'][0][0], step=i['quantity_step'], minimum=i['minimum_quantity'],
                         min_notional=i['minimum_notional'], maximum=lot['maxMktOrderQty'], tick=i['tick_size'], bids=book['b'], asks=book['a']))
    result = calculate_proposal(rows, dossier['instruments'], observed_ms=source['completed_ms'], original_bounds=original_bounds)
    result.pop('proposal_id')
    result.update(capture_sha256=expected_sha, capture_started_ms=source['started_ms'],
                  common_clock_at_capture=dossier['common_clock_at_capture'],
                  source_mode='SAVED_AUTHENTICATED_GET_CAPTURE_DATED_NOT_SEND',
                  account_margin_mode=dossier['account_margin_mode'],
                  linear_usdt_positions_observed=dossier['all_linear_usdt_positions'],
                  linear_usdt_open_orders_observed=dossier['all_linear_usdt_open_orders'],
                  account_trade_permissions_observed=dossier['account_trade_permissions_observed'],
                  available_margin_ge_full_funding_reference=D(dossier['wallet_total_available_usd']) >= D(result['fully_funded_reference_plus_reserves_usdt']),
                  available_margin_ge_full_proposed_cap_plus_reserves=D(dossier['wallet_total_available_usd']) >= D(result['full_cap_plus_fee_reserve_usdt']),
                  wallet_amounts_omitted_from_public_receipt=True,
                  exact_liquidation_price_after_entry='UNKNOWN_NOT_OPENED',
                  source_get_requests=wrapper.get('requests'),
                  raw_source_hashes={k: v['raw_sha256'] for k,v in caps.items() if 'raw_sha256' in v},
                  platform_preservation=wrapper.get('preservation'))
    result['proposal_id'] = digest(result)
    return result


def owner_review_packet(proposal):
    """Concrete proposed authority; no live schema, policy token or launcher."""
    if (proposal.get('schema') != 'KITY_CAP300_CALCULATION_PROPOSAL_V1'
            or proposal.get('proposal_id') != digest({k:v for k,v in proposal.items() if k != 'proposal_id'})
            or proposal.get('proposed_gross_cap_usdt') != '300'
            or proposal.get('loss_exit_trigger_usdt') != '15'
            or any(proposal.get(k) is not False for k in ('orders_allowed','money_authority','new_policy_created','old_attempt_reusable'))):
        raise ValueError('PROPOSAL_PIN_CONFLICT')
    gates = ['NEW_EXPLICIT_OWNER_GO_FOR_THIS_PACKET',
             'SEPARATE_CAP300_BINDING_TESTED_AND_SOURCE_PINNED_BEFORE_PERSONAL_START',
             'NEW_DATED_UNSPENT_POLICY_AND_CLAIM_NAMESPACE',
             'FRESH_PRE_MONEY_CAPACITY_AND_ACCOUNT_CHECK_BEFORE_ISSUING_POLICY',
             'ONE_POST_GO_CAPTURE_AND_ORIGINAL_FINAL_DISPATCH_GATES',
             'HUMAN_ONLY_PERSONAL_ONE_SHOT_START']
    if proposal['capacity_status'] != 'FITS_PROPOSED_CAP':
        gates.insert(0, 'CAPACITY_BLOCKED_NO_ACTIVATION')
    if proposal.get('source_mode') != 'SAVED_AUTHENTICATED_GET_CAPTURE_DATED_NOT_SEND':
        gates.insert(0, 'DATED_AUTHENTICATED_ACCOUNT_CAPTURE_REQUIRED')
    else:
        checks = {'linear_usdt_positions_observed': 0, 'linear_usdt_open_orders_observed': 0,
                  'account_trade_permissions_observed': True, 'available_margin_ge_full_proposed_cap_plus_reserves': True,
                  'account_margin_mode': 'REGULAR_MARGIN'}
        if any(type(proposal.get(k)) is not type(v) or proposal[k] != v for k,v in checks.items()):
            gates.insert(0, 'ACCOUNT_OR_MARGIN_BLOCKED')
        if proposal.get('common_clock_at_capture', {}).get('status') != 'OBSERVED_COMMON_2S_PASS':
            gates.insert(0, 'DATED_COMMON_CLOCK_NOT_PROVEN')
        if proposal.get('platform_preservation', {}).get('identical') is not True:
            gates.insert(0, 'PLATFORM_PRESERVATION_UNKNOWN')
    packet = dict(schema='KITY_CAP300_OWNER_REVIEW_PACKET_V1',
                  status='INERT_PROPOSAL_REQUIRES_OWNER_GO_AND_NEW_BINDING',
                  proposal_id=proposal['proposal_id'], remaining_gates=gates,
                  scope=dict(gross_cap_usdt='300', loss_trigger_usdt='15', duration_ms=DURATION,
                             max_personal_attempts=1, entry_window_ms=60000, collar_bps='50',
                             common_cts_max_ms=2000, max_rounding_shortfall_fraction='0.203',
                             basket=[dict(symbol=s,side=side) for s,side in BASKET],
                             quantity_rule='MINIMUM_ORIGINAL_COMMON_TARGET_FLOOR_FRONTIER_NOT_SPEND_300',
                             leverage_or_margin_mode_change_allowed=False,
                             add_scale_average_reentry_allowed=False, research_promotion_allowed=False),
                  exit_rules=['ALL_IN_LIQUIDATION_VALUE_AT_OR_BELOW_MINUS_15_IMMEDIATE_OWNED_UNWIND',
                              '30_MINUTES_FROM_FIRST_SEND_ENDS_EXPERIMENT',
                              'PARTIAL_REJECT_UNKNOWN_SEND_MISSING_NATIVE_PROTECTION_OR_STALE_RISK_ABORT_ENTRIES_AND_RECONCILE_UNWIND',
                              'DURABLE_RESTART_RECOVERY_RECONCILES_OWNED_EXPOSURE_NO_BLIND_RESEND_OR_SECOND_ATTEMPT',
                              'FINAL_PAGINATED_BROKER_READBACK_FLAT_NO_OWNED_ORDERS_ALL_FEES_AND_FUNDING_ACCOUNTED'],
                  required_explicit_risk_acceptance=['15_USDT_IS_EXIT_TRIGGER_NOT_GUARANTEED_FINAL_LOSS',
                                                     'CROSS_MARGIN_EXPOSES_SHARED_COLLATERAL_NOT_RINGFENCED_300',
                                                     'NATIVE_LASTPRICE_MARKET_STOPS_CAN_GAP_OR_SLIP_AND_ARE_NOT_LIQUIDATION_GUARANTEES'],
                  spent_policy_sha256='a1c97e6b94e3d1a1c8927e7dba252cbd12a1c6f49012133587a85c27fb8845c8',
                  spent_command_id='1792247810399920355', spent_attempt_reusable=False,
                  financial_policy_created=False, owner_go_received=False, owner_command=None,
                  orders_allowed=False, money_authority=False,
                  dated_reference_legs=proposal['legs'],
                  future_policy_expiry_rule='SHORT_DATED_EXPIRY_SET_BEFORE_OWNER_PERSONAL_START_NOT_A_STANDING_PERMISSION',
                  execution_10_of_10_proven=False, actual_trading_profit_proven=False)
    packet['packet_id'] = digest(packet)
    return packet
