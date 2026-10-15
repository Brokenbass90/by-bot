"""Orders-OFF execution geometry for a separately labelled micro experiment.

No strategy signal calculation, account credentials, sender, permit, ledger
reservation or broker client. Never returns money readiness. Rounding frontiers
are alternative owner decisions, not selected policy or historical optimization.
"""
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR


def numeric(value, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('INVALID_NUMBER')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('INVALID_NUMBER') from exc
    if not number.is_finite() or (number < 0 if zero else number <= 0):
        raise ValueError('INVALID_NUMBER')
    return number


def _text(number):
    return format(number, 'f')


def _rows(rows):
    if not rows or len({r['symbol'] for r in rows}) != len(rows):
        raise ValueError('EMPTY_OR_DUPLICATE_SYMBOLS')
    normalized = []
    for row in rows:
        if row['side'] not in ('Buy', 'Sell'):
            raise ValueError('INVALID_SIDE')
        row = dict(row)
        for field in ('price', 'bid', 'step', 'minimum', 'min_notional', 'maximum'):
            row[field] = numeric(row[field])
        normalized.append(row)
    return normalized


def sizing_floor(rows):
    """Smallest shared target meeting every per-leg quantity/notional minimum.

    Use bid for minimum-notional validation, including buys, consistent with the
    existing public assessor's conservative reference. This is not an order fill.
    """
    targets = []
    for row in _rows(rows):
        lots = max((row['minimum'] / row['step']).to_integral_value(rounding=ROUND_CEILING),
                   (row['min_notional'] / (row['bid'] * row['step'])).to_integral_value(rounding=ROUND_CEILING))
        q = lots * row['step']
        if q > row['maximum']:
            raise ValueError('MINIMUM_EXCEEDS_MAXIMUM')
        targets.append(q * row['price'])
    return max(targets)


def basket_geometry(rows, target):
    target = numeric(target)
    legs = []
    for row in _rows(rows):
        q = (target / (row['price'] * row['step'])).to_integral_value(rounding=ROUND_FLOOR) * row['step']
        if q < row['minimum'] or q * row['bid'] < row['min_notional']:
            raise ValueError('VENUE_MINIMUM_REJECT')
        if q > row['maximum']:
            raise ValueError('VENUE_MAXIMUM_REJECT')
        notional = q * row['price']
        legs.append(dict(symbol=row['symbol'], side=row['side'], quantity=_text(q),
                         entry_reference_notional=_text(notional),
                         rounding_shortfall_fraction=_text((target - notional) / target)))
    return legs


def first_target_within_rounding(rows, tolerance, *, max_jumps=100_000):
    """First feasible target for declared floor-rounding tolerance.

    At a violated leg, no target before its next quantity breakpoint can work:
    its current quantity is unchanged while relative shortfall only increases.
    Jump to the latest required breakpoint. No outcome/ranking data are read.
    """
    e = numeric(tolerance)
    if e >= 1:
        raise ValueError('INVALID_ROUNDING_TOLERANCE')
    rows = _rows(rows)
    target = sizing_floor(rows)
    for _ in range(max_jumps):
        jump = []
        for row in rows:
            delta = row['price'] * row['step']
            lots = (target / delta).to_integral_value(rounding=ROUND_FLOOR)
            if target - lots * delta > e * target:
                jump.append((lots + 1) * delta)
        if not jump:
            basket_geometry(rows, target)  # enforce market maximums too
            return target
        target = max(jump)
    raise ValueError('ROUNDING_SEARCH_BOUND')


def common_source_clock(books, observed_ms, *, clock_captures=None):
    """Historical common-time observation, never a current dispatch freshness.

    Offset intervals assume response `time` was generated between GET request
    and receive; matching-engine CTS is required separately and never substituted
    with HTTP receive or public response `ts`.
    """
    unknown = dict(status='SOURCE_UNKNOWN', valid_for_dispatch=False)
    if not books or type(observed_ms) is not int:
        return unknown
    envelopes = clock_captures if clock_captures is not None else books
    intervals = []
    for cap in envelopes:
        start, end, server = cap.get('request_ms'), cap.get('receive_ms'), cap.get('body', {}).get('time')
        if type(server) is not int:
            continue
        if any(type(v) is not int or v <= 0 for v in (start, end, server)) or start > end or end > observed_ms:
            return dict(status='SOURCE_CLOCK_CONFLICT', valid_for_dispatch=False)
        intervals.append((server - end, server - start))
    if not intervals:
        return unknown
    lower, upper = max(i[0] for i in intervals), min(i[1] for i in intervals)
    if lower > upper:
        return dict(status='SOURCE_CLOCK_CONFLICT', valid_for_dispatch=False)
    ages = []
    for cap in books:
        cts = cap.get('body', {}).get('result', {}).get('cts')
        received = cap.get('receive_ms')
        if type(cts) is not int or cts <= 0 or type(received) is not int:
            return unknown
        if received > observed_ms or cts > received + upper:
            return dict(status='SOURCE_CLOCK_CONFLICT', valid_for_dispatch=False)
        ages.append(max(0, observed_ms + upper - cts))
    worst = max(ages)
    return dict(status='OBSERVED_COMMON_2S_PASS' if worst <= 2000 else 'COMMON_BASKET_STALE',
                server_offset_interval_ms=[lower, upper], max_engine_age_upper_ms=worst,
                common_observation_ms=observed_ms, valid_for_dispatch=False)
