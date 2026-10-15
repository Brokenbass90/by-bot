"""Replay the single private capture into a sanitized, no-send dossier.

No broker/network imports or new observations. Outputs are create-exclusive.
"""
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research_lab.kity_execution_micro_v1 import (
    sizing_floor, basket_geometry, first_target_within_rounding, common_source_clock,
)
from bot.kity_m3_orders_off import _levels, _vwap

CAPTURE_SHA = 'f11cea6d70dcbe70e7cbd6b95dd9424a7512af041f74ab13fae468e34cff38e9'
C2_RECONSTRUCTION = 'ec4f6ab451922ac12420868dde09dbb6b46738e594bdaff8ceb1dcbcaf09c406'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(capture_path, c2_path):
    if sha(capture_path) != CAPTURE_SHA:
        raise ValueError('CAPTURE_PIN_CONFLICT')
    x = json.loads(capture_path.read_bytes())['response']
    c = x['captures']
    c2 = json.loads(c2_path.read_bytes())
    if (c2['status'] != 'C2_PASS_MATCH_ONLY' or not c2['reconstruction_sealed_before_shadow_read']
            or c2['independent_reconstruction_receipt_sha256'] != C2_RECONSTRUCTION
            or c2['day'] != '2026-10-15'):
        raise ValueError('C2_PIN_CONFLICT')
    basket = [(s, 'Buy') for s in c2['long']] + [(s, 'Sell') for s in c2['short']]
    if [s for s, _ in basket] != x['symbols'] or len(basket) != 10:
        raise ValueError('EXACT_TEN_BASKET_CONFLICT')
    for cap in c.values():
        if 'raw' in cap:
            if (hashlib.sha256(cap['raw'].encode()).hexdigest() != cap['raw_sha256']
                    or json.loads(cap['raw']) != cap['body']):
                raise ValueError('RAW_HASH_OR_BODY_CONFLICT')

    def body(label):
        cap = c[label]
        if cap.get('error_type') or cap.get('http_status') != 200 or cap['body']['retCode'] != 0:
            raise ValueError('SOURCE_UNKNOWN:' + label)
        return cap['body']['result']

    rows, instruments = [], []
    for symbol, side in basket:
        irows, frows = body('instrument:' + symbol)['list'], body('fee:' + symbol)['list']
        prows, book = body('position:' + symbol)['list'], body('book:' + symbol)
        if len(irows) != 1 or len(frows) != 1 or len(prows) != 1:
            raise ValueError('AMBIGUOUS_SYMBOL_SOURCE')
        i, fee, pos = irows[0], frows[0], prows[0]
        if any(v.get('symbol') != symbol for v in (i, fee, pos)) or book.get('s') != symbol:
            raise ValueError('SYMBOL_IDENTITY_CONFLICT')
        if (i.get('contractType'), i.get('status'), i.get('quoteCoin'), i.get('settleCoin')) != ('LinearPerpetual', 'Trading', 'USDT', 'USDT') or i.get('unifiedMarginTrade') is not True:
            raise ValueError('INSTRUMENT_NOT_ELIGIBLE')
        bid, ask = D(book['b'][0][0]), D(book['a'][0][0])
        if bid >= ask or pos.get('isReduceOnly') is not False or D(pos['size']) != 0:
            raise ValueError('BOOK_OR_POSITION_CONFLICT')
        lot = i['lotSizeFilter']
        rows.append(dict(symbol=symbol, side=side, price=ask if side == 'Buy' else bid,
                         bid=bid, step=D(lot['qtyStep']), minimum=D(lot['minOrderQty']),
                         min_notional=D(lot['minNotionalValue']), maximum=D(lot['maxMktOrderQty'])))
        instruments.append(dict(symbol=symbol, side=side, status=i['status'],
            contract_type=i['contractType'], symbol_type=i.get('symbolType'),
            quantity_step=lot['qtyStep'], minimum_quantity=lot['minOrderQty'],
            minimum_notional=lot['minNotionalValue'], tick_size=i['priceFilter']['tickSize'],
            configured_leverage=pos['leverage'], position_idx=pos['positionIdx'],
            is_reduce_only=pos['isReduceOnly'], taker_fee=fee['takerFeeRate'],
            maker_fee=fee['makerFeeRate'], funding_interval_minutes=i['fundingInterval'],
            funding_rate_observed=body('ticker:' + symbol)['list'][0]['fundingRate'],
            next_funding_ms=body('ticker:' + symbol)['list'][0]['nextFundingTime'],
            funding_upper=i['upperFundingRate'], funding_lower=i['lowerFundingRate']))

    profiles = []
    targets = [('VENUE_FLOOR_DIAGNOSTIC', sizing_floor(rows), None)]
    for tolerance in ('.05', '.02', '.01'):
        targets.append(('ROUNDING_' + tolerance, first_target_within_rounding(rows, D(tolerance)), tolerance))
    for label, target, tolerance in targets:
        geometry = basket_geometry(rows, target)
        total = fees = spread = margin = long = short = weekly = D(0)
        legs = []
        namespace = hashlib.sha256((CAPTURE_SHA + label).encode()).hexdigest()[:12]
        for n, (leg, instrument) in enumerate(zip(geometry, instruments)):
            symbol, side, quantity = leg['symbol'], leg['side'], D(leg['quantity'])
            book = body('book:' + symbol)
            bids, asks = _levels(book['b'], True), _levels(book['a'], False)
            entry_price, entry_n = _vwap(asks if side == 'Buy' else bids, quantity)
            _, exit_n = _vwap(bids if side == 'Buy' else asks, quantity)
            remaining = quantity
            for limit_price, available in (asks if side == 'Buy' else bids):
                remaining -= min(remaining, available)
                if remaining == 0:
                    break
            tick = D(instrument['tick_size'])
            if any(p % tick for p, q in bids + asks):
                raise ValueError('PRICE_GRID_CONFLICT')
            fee = (entry_n + exit_n) * D(instrument['taker_fee'])
            total += entry_n; fees += fee; spread += abs(entry_n - exit_n)
            margin += entry_n / D(instrument['configured_leverage'])
            if side == 'Buy':
                long += entry_n
            else:
                short += entry_n
            events = (10080 + instrument['funding_interval_minutes'] - 1) // instrument['funding_interval_minutes']
            rate = D(instrument['funding_upper']) if side == 'Buy' else -D(instrument['funding_lower'])
            weekly += entry_n * rate * events
            legs.append(dict(leg, entry_book_vwap=str(entry_price), entry_book_notional=str(entry_n),
                roundtrip_fee_constant_price=str(fee),
                draft_entry=dict(category='linear', symbol=symbol, side=side, orderType='Limit',
                    timeInForce='IOC', qty=leg['quantity'], price=str(limit_price),
                    positionIdx=instrument['position_idx'], reduceOnly=False,
                    orderLinkId=f'KXM1-{namespace}-E{n:02d}'),
                draft_exit_link_id=f'KXM1-{namespace}-X{n:02d}',
                draft_is_executable=False, note='Historical diagnostic template; owner controls and fresh prices absent.'))
        profiles.append(dict(profile=label, approved=False, tolerance=tolerance,
            common_reference_target=str(target), nominal_target_gross=str(target * 10),
            observed_depth_gross=str(total), net_direction_reference=str(long - short),
            constant_price_roundtrip_fees=str(fees), constant_price_spread=str(spread),
            constant_price_roundtrip_total=str(fees + spread),
            approximate_initial_margin_at_unchanged_configured_leverage=str(margin),
            fully_funded_1x_reference_plus_flat_costs=str(total + fees + spread),
            seven_day_funding_scenario_at_observed_rate_limits=str(weekly),
            future_funding_bound_proven=False, exact_required_capital_known=False, legs=legs))
    identity, account = body('identity'), body('account')
    wallet = body('wallet')['list'][0]
    counts = {}
    for label in ('all_positions', 'all_open_orders'):
        group = c[label]
        if not group['complete']:
            raise ValueError('INCOMPLETE_ACCOUNT_PAGINATION')
        rs = []
        for page in group['pages']:
            if page['body']['retCode'] != 0:
                raise ValueError('ACCOUNT_PAGE_ERROR')
            rs += page['body']['result']['list']
        counts[label] = len(rs)
    contract = identity.get('permissions', {}).get('ContractTrade', [])
    books = [c['book:' + s] for s, _ in basket]
    timing = common_source_clock(books, x['completed_ms'], clock_captures=[v for v in c.values() if 'body' in v])
    return dict(schema='kity_execution_micro_readonly_dossier_v1',
        status='BLOCKED_EXECUTION', money_ready=False, orders_allowed=False,
        purpose='EXECUTION_ONLY_NOT_RESEARCH', experiment='KITY_EXECUTION_MICRO_LIVE_V1',
        observed_start_ms=x['started_ms'], observed_end_ms=x['completed_ms'],
        private_capture_sha256=CAPTURE_SHA, c2_public_receipt_sha256=sha(c2_path),
        c2_reconstruction_receipt_sha256=C2_RECONSTRUCTION,
        configured_margin_mode=account['marginMode'], unified_margin_status=account['unifiedMarginStatus'],
        api_trade_permissions_observed=(identity.get('readOnly') == 0 and 'Order' in contract and 'Position' in contract),
        api_expires_at=identity.get('expiredAt'), api_acceptance_not_guaranteed=True,
        positions_orders_observation_scope='linear USDT only; not account-wide spot/inverse/USDC clearance',
        wallet_total_available_usd=wallet['totalAvailableBalance'],
        wallet_total_equity_usd=wallet['totalEquity'], **counts,
        instruments=instruments, common_clock_at_capture=timing, profiles=profiles,
        blockers=['OWNER_GROSS_LOSS_DURATION_AND_ROUNDING_LIMITS_UNSET',
                  'CONFIGURED_3X_10X_CROSS_MARGIN_NOT_AN_APPROVED_MICRO_RISK_POLICY',
                  'TEN_LEG_SENDER_OWNERSHIP_UNWIND_RESTART_AND_FINALITY_NOT_YET_WIRED',
                  'FRESH_DISPATCH_CHECKS_REQUIRED_AT_ACTUAL_APPROVED_EXECUTION_TIME'],
        research_firewall=dict(counts_toward_C1_C2_C3=False, counts_toward_edge=False,
            research_or_policy_changes_allowed=False), broker_writes=0, remote_writes=0)


def main():
    output = ROOT / 'reports/evidence/kity_micro_live_20261015/execution_intake_terminal.json'
    result = build(ROOT / '.private/kity_micro_live_20261015/bybit_capture_v1.json',
                   ROOT / 'reports/evidence/kity_bybit_c2_actual_20261015/c2_public_receipt.json')
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    print(json.dumps(dict(status=result['status'], sha256=hashlib.sha256(raw).hexdigest(),
        profiles=len(result['profiles']), exact_symbols=len(result['instruments']), orders_allowed=False)))


if __name__ == '__main__':
    main()
