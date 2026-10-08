"""Offline evidence projection. No network, account mutation, or admission."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / 'reports/CODEX_SESSION_CHECKPOINT_2026_09_06.md').is_file())
RAW = ROOT / '.private/kity_bitget_intake_20261008/bitget_raw_archive.json'
OUT = ROOT / 'reports/KITY_BITGET_FEASIBILITY_2026_10_08.json'
archive = json.loads(RAW.read_text())
captures = archive['captures']
assert len(captures) == archive['api_requests'] == 39
assert archive['remote_writes'] == archive['order_calls'] == 0
for capture in captures:
    assert capture['method'] == 'GET'
    assert capture['ok']
    assert hashlib.sha256(capture['raw'].encode()).hexdigest() == capture['sha256']


def get(endpoint, symbol=None, plan_type=None):
    matches = [c for c in captures if c['endpoint'] == endpoint
               and c['params'].get('symbol') == symbol
               and c['params'].get('planType') == plan_type]
    assert len(matches) == 1
    capture = matches[0]
    return json.loads(capture['raw'])['data'], capture


def stamp(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def ds(value):
    return format(value, 'f')


census, census_capture = get('/api/v2/mix/market/contracts')
assert isinstance(census, list)
counts = Counter(row['symbol'] for row in census)
assert all(n == 1 for n in counts.values())
by_symbol = {row['symbol']: row for row in census}
symbols = archive['symbols']
missing = [s for s in symbols if s not in by_symbol]
assert missing == ['币安人生USDT']
alias_search = [row['symbol'] for row in census if any(
    term in str(row).lower() for term in ('币安', 'binancelife', 'bianrensheng'))]
assert not alias_search
books = [c for c in captures if c['endpoint'].endswith('/merge-depth')]
common_use_ms = max(c['receive_ms'] for c in books)
assert len(books) == 7
clock_intervals = []
for capture in captures:
    if capture['endpoint'].endswith('/public/time'):
        server = int(json.loads(capture['raw'])['data']['serverTime'])
        clock_intervals.append([server - capture['receive_ms'], server - capture['request_ms']])
offset_low = max(x[0] for x in clock_intervals)
offset_high = min(x[1] for x in clock_intervals)
assert offset_low <= offset_high
rows = []
for index, symbol in enumerate(symbols):
    row = {'symbol': symbol, 'side': 'LONG' if index < 4 else 'SHORT'}
    if symbol in missing:
        row.update(status='BLOCKED_EXECUTION', reason='EXACT_SYMBOL_MISSING',
                   minimum_quantity=None, minimum_notional=None,
                   account_profile=None, fees=None, book=None, funding=None)
        rows.append(row)
        continue
    contract = by_symbol[symbol]
    assert contract['symbolStatus'] == 'normal'
    assert contract['quoteCoin'] == 'USDT' and contract['symbolType'] == 'perpetual'
    account, account_capture = get('/api/v2/mix/account/account', symbol)
    fees, fees_capture = get('/api/v2/common/trade-rate', symbol)
    funding, funding_capture = get('/api/v2/mix/market/current-fund-rate', symbol)
    book, book_capture = get('/api/v2/mix/market/merge-depth', symbol)
    assert len(funding) == 1 and funding[0]['symbol'] == symbol
    bids = [[Decimal(str(p)), Decimal(str(q))] for p, q in book['bids']]
    asks = [[Decimal(str(p)), Decimal(str(q))] for p, q in book['asks']]
    assert bids and asks and bids[0][0] < asks[0][0]
    assert all(p > 0 and q > 0 for p, q in bids + asks)
    assert all(bids[i][0] > bids[i + 1][0] for i in range(len(bids) - 1))
    assert all(asks[i][0] < asks[i + 1][0] for i in range(len(asks) - 1))
    assert book['precision'] == 'scale0'
    price = asks[0][0] if index < 4 else bids[0][0]
    step = Decimal(contract['sizeMultiplier'])
    base_min = Decimal(contract['minTradeNum'])
    usdt_min = Decimal(contract['minTradeUSDT'])
    assert step > 0 and base_min > 0 and usdt_min > 0
    # Documentation says strictly greater than minTradeNum. Diagnostic only;
    # no market order or exact equal-notional allocation is constructed here.
    q_strict = (base_min / step).to_integral_value(rounding='ROUND_FLOOR') * step + step
    q_notional = (usdt_min / price / step).to_integral_value(rounding=ROUND_CEILING) * step
    quantity = max(q_strict, q_notional)
    assert quantity > base_min and quantity % step == 0 and quantity * price >= usdt_min
    assert quantity <= Decimal(contract['maxMarketOrderQty'])
    available_side = asks if index < 4 else bids
    remaining = quantity
    total = Decimal(0)
    for level_price, level_qty in available_side:
        consumed = min(remaining, level_qty)
        total += consumed * level_price
        remaining -= consumed
        if not remaining:
            break
    assert remaining == 0
    ts = int(book['ts'])
    age_low = common_use_ms + offset_low - ts
    age_high = common_use_ms + offset_high - ts
    fresh = 0 <= age_low <= age_high <= 2000 and ts <= book_capture['receive_ms'] + offset_low
    mid = (asks[0][0] + bids[0][0]) / 2
    row.update(status='PRESENT_DIAGNOSTIC_ONLY',
        instrument={k: contract[k] for k in ('symbol', 'baseCoin', 'quoteCoin', 'symbolType',
            'symbolStatus', 'minTradeNum', 'sizeMultiplier', 'minTradeUSDT', 'volumePlace',
            'maxMarketOrderQty', 'fundInterval')},
        minimum_quantity=ds(quantity), minimum_notional=ds(quantity * price),
        minimums_basis='unapproved individual top-of-book diagnostic; strict minTradeNum; not equal-notional basket',
        account_profile={k: account.get(k) for k in ('available', 'accountEquity', 'marginMode',
            'posMode', 'assetMode', 'crossedMarginLeverage', 'isolatedLongLever', 'isolatedShortLever')},
        fees=fees,
        book={'source_sha256': book_capture['sha256'], 'raw_ts': ts,
            'clock_semantics': 'matching-engine timestamp per official Bitget merge-depth documentation',
            'request_ms': book_capture['request_ms'], 'receive_ms': book_capture['receive_ms'],
            'common_use_ms': common_use_ms, 'clock_bounded_age_ms': [age_low, age_high],
            'present_seven_books_2s_check': 'PASS' if fresh else 'BLOCKED_DATA',
            'bid': ds(bids[0][0]), 'ask': ds(asks[0][0]),
            'spread_bps': ds((asks[0][0] - bids[0][0]) / mid * 10000),
            'individual_minimum_vwap': ds(total / quantity),
            'individual_minimum_visible_slippage_bps': ds(abs(total / quantity - price) / price * 10000),
            'received_depth_levels': {'bids': len(bids), 'asks': len(asks)},
            'continuous_freshness': 'NOT_PROVEN'},
        funding=funding[0], funding_reserve='UNAPPROVED_NOT_CALCULATED',
        source_pins={'contract_census': census_capture['sha256'], 'account': account_capture['sha256'],
            'actual_fees': fees_capture['sha256'], 'current_funding': funding_capture['sha256']})
    rows.append(row)

accounts, account_capture = get('/api/v2/mix/account/accounts')
spot, spot_capture = get('/api/v2/spot/account/assets')
info, info_capture = get('/api/v2/spot/account/info')
positions, position_capture = get('/api/v2/mix/position/all-position')
assert isinstance(positions, list) and not positions
orders = []
for endpoint, plan_type in [('/api/v2/mix/order/orders-pending', None)] + [
    ('/api/v2/mix/order/orders-plan-pending', t) for t in ('normal_plan', 'track_plan', 'profit_loss')]:
    data, capture = get(endpoint, plan_type=plan_type)
    assert data == {'entrustedList': None, 'endId': None}
    orders.append({'endpoint': endpoint, 'plan_type': plan_type, 'http': capture['http_status'],
        'api_code': capture['api_code'], 'returned_rows': None, 'cursor': None,
        'observation': 'successful null-list/null-cursor response; no rows reported; not ownership/finality proof',
        'sha256': capture['sha256']})
present_rows = [r for r in rows if r['symbol'] not in missing]
individual_sum = sum(Decimal(r['minimum_notional']) for r in present_rows)
receipt = {
    'schema': 'KITY_BITGET_FEASIBILITY_ORDERS_OFF_V1',
    'terminal': 'BLOCKED_EXECUTION',
    'source_intake_terminal': 'BLOCKED_DATA_UNCHANGED',
    'observed_start_utc': stamp(archive['started_ms']),
    'observed_end_utc': stamp(archive['completed_ms']),
    'raw_archive_path': str(RAW), 'raw_archive_sha256': hashlib.sha256(RAW.read_bytes()).hexdigest(),
    'api_requests': len(captures), 'order_calls': 0, 'remote_writes': 0, 'orders_allowed': False,
    'census': {'rows': len(census), 'duplicates': [], 'sha256': census_capture['sha256'],
        'exact_symbol_counts': archive['exact_symbol_counts'], 'missing_symbols': missing,
        'underlying_alias_search_terms': ['币安', 'binancelife', 'bianrensheng'],
        'underlying_alias_search_hits': alias_search,
        'authoritative_alias_mapping': 'NONE_ESTABLISHED',
        'scope': 'complete response to documented Classic USDT-FUTURES contracts endpoint; not spot/other products'},
    'account': {
        'futures': [{k: x.get(k) for k in ('marginCoin', 'available', 'accountEquity', 'usdtEquity', 'assetMode',
            'isolatedMargin', 'crossedMargin')} for x in accounts],
        'spot_usdt': [{k: x.get(k) for k in ('coin', 'available', 'frozen', 'locked')} for x in spot],
        'key_reported_authority_codes': info['authorities'],
        'derivatives_trade_permission': 'UNKNOWN_NO_AUTHORITATIVE_CODE_MAPPING_VERIFIED',
        'credentials_remained_on_vps': True, 'positions_rows': len(positions),
        'pending_orders': orders,
        'account_identifier_redacted': True,
        'source_pins': {'futures': account_capture['sha256'], 'spot': spot_capture['sha256'],
            'key_info': info_capture['sha256'], 'positions': position_capture['sha256']}},
    'clock': {'offset_intervals_ms': clock_intervals, 'intersection_ms': [offset_low, offset_high],
        'assumption': 'server time lies within request/receive interval; VPS clock offset stable over this six-second capture',
        'present_seven_books_common_use_ms': common_use_ms,
        'full_eight_leg_common_freshness': 'BLOCKED_EXECUTION_MISSING_LEG'},
    'legs': rows,
    'sizing': {'full_basket_equal_notional': None, 'full_basket_gross': None,
        'full_basket_required_margin_and_reserve': None,
        'owner_50_usdt_budget': 'HYPOTHETICAL_NOT_ACTUAL_AVAILABLE_CASH',
        'fits_50_usdt': 'NOT_ESTABLISHED',
        'seven_individual_minima_sum_diagnostic_not_basket': ds(individual_sum),
        'present_seven_taker_round_trip_constant_notional_bps': '12',
        'fees_note': 'all seven signed maker=0.0002/taker=0.0006; future exit notional/funding differ'},
    'blockers': ['EXACT_FROZEN_SHORT_LEG_MISSING', 'FUTURES_USDT_AVAILABLE_ZERO',
        'KEY_DERIVATIVES_TRADE_SCOPE_NOT_VERIFIED', 'NATIVE_BITGET_KITY_EXECUTION_CONTRACT_ABSENT',
        'FULL_EQUAL_NOTIONAL_ROUNDING_CAPS_AND_FUNDING_POLICY_UNAPPROVED',
        'OWNERSHIP_PARTIAL_BASKET_UNWIND_FINALITY_KILL_NOT_VALIDATED',
        'STRICT_GAIB_EXTERNAL_PROVENANCE_ACCEPTED_SEAL_AND_PACKET_SIZE_CONTRACT_UNCHANGED'],
    'preservation': {'strategy_universe_hold_costs_unchanged': True,
        'missing_leg_not_substituted_or_dropped': True,
        'no_money_runner_or_credentials_added': True,
        'alpaca_att1_ets2m_claude_runtime_not_touched': True,
        'production_pids_not_freshly_queried': True},
    'source_pins': [{k: c[k] for k in ('endpoint', 'params', 'method', 'signed', 'request_ms',
        'receive_ms', 'http_status', 'api_code', 'sha256')} for c in captures],
}
OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
print(json.dumps({'terminal': receipt['terminal'], 'requests': len(captures),
    'missing': missing, 'census_rows': len(census), 'individual_seven_minima': ds(individual_sum),
    'freshness_checks': [r['book']['present_seven_books_2s_check'] for r in present_rows],
    'output': str(OUT)}, ensure_ascii=False))
