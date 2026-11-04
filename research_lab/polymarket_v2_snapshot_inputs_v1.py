"""Normalize exact public GET snapshots; no network, strategy or order authority.

REST verifies one captured response, never continuity of a WebSocket stream.
Unsupported protocol/fee semantics remain unknown rather than inferred defaults.
"""
import hashlib
import json
import re
from .polymarket_v2_orders_off_v1 import _number, _levels, _ms


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def bad_constant(value):
    raise ValueError('NONFINITE_JSON')


def decoded(capture, url, decision_ms, max_age_ms):
    need(isinstance(capture, dict) and _ms(decision_ms), 'CAPTURE_SCHEMA')
    need(type(max_age_ms) is int and max_age_ms > 0, 'AGE_BOUND')
    need(capture.get('method') == 'GET' and capture.get('url') == url, 'CAPTURE_ENDPOINT')
    need(type(capture.get('http_status')) is int and capture['http_status'] == 200, 'CAPTURE_HTTP')
    start, received = capture.get('request_ms'), capture.get('received_ms')
    need(_ms(start) and _ms(received) and start <= received <= decision_ms, 'CAPTURE_TIME')
    need(decision_ms - received <= max_age_ms, 'STALE_SNAPSHOT')
    text = capture.get('raw_text')
    need(isinstance(text, str), 'RAW_BODY_REQUIRED')
    raw = text.encode('utf-8')
    need(0 < len(raw) <= 2_000_000 and hashlib.sha256(raw).hexdigest() == capture.get('raw_sha256'), 'RAW_BODY_HASH')
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
    need(isinstance(value, dict), 'CAPTURE_JSON_OBJECT')
    return value


def market_input(capture, market_id, *, decision_ms, max_age_ms=60000):
    need(isinstance(market_id, str) and re.fullmatch(r'[0-9]{1,32}', market_id), 'MARKET_ID')
    value = decoded(capture, 'https://gamma-api.polymarket.com/markets/' + market_id, decision_ms, max_age_ms)
    need(str(value.get('id')) == market_id, 'MARKET_IDENTITY')
    need(type(value.get('version')) is not bool and value.get('version') in (None, 'v1', 'ctf', 1), 'UNSUPPORTED_MARKET_PROTOCOL')
    tokens = value.get('clobTokenIds')
    if isinstance(tokens, str):
        tokens = json.loads(tokens, object_pairs_hook=pairs, parse_constant=bad_constant)
    need(isinstance(tokens, list) and len(tokens) == 2
         and all(isinstance(t, str) and re.fullmatch(r'[0-9]{1,100}', t) for t in tokens) and len(set(tokens)) == 2, 'MARKET_TOKENS')
    condition = value.get('conditionId')
    need(isinstance(condition, str) and re.fullmatch(r'0x[0-9a-fA-F]{64}', condition), 'CONDITION_ID')
    accepting = value.get('acceptingOrders')
    if value.get('closed') is True or value.get('active') is False or value.get('enableOrderBook') is False:
        accepting = False
    if type(accepting) is not bool:
        accepting = None
    result = dict(market_id=market_id, condition_id=condition, tokens=list(tokens),
                  accepting_orders=accepting, received_ms=capture['received_ms'],
                  source_sha256=capture['raw_sha256'], fee_issues=[],
                  fee_schedule=None, fee_source_sha256=None,
                  tick_size=value.get('orderPriceMinTickSize'),
                  minimum_order_size=value.get('orderMinSize'))
    enabled = value.get('feesEnabled')
    schedule = value.get('feeSchedule')
    if enabled is False and schedule is None:
        result.update(fee_rate='0', fee_source_sha256=capture['raw_sha256'])
    elif enabled is True and isinstance(schedule, dict):
        try:
            rate = _number(schedule.get('rate'))
            need(0 <= rate <= 1, 'FEE_RATE_RANGE')
            need(type(schedule.get('exponent')) in (int, float) and schedule['exponent'] == 1, 'UNSUPPORTED_FEE_EXPONENT')
            need(schedule.get('takerOnly') is True, 'UNSUPPORTED_FEE_SIDE')
            result.update(fee_rate=str(rate), fee_source_sha256=capture['raw_sha256'],
                          fee_schedule=dict(rate=str(rate), exponent=1, takerOnly=True))
        except ValueError as error:
            result['fee_issues'].append(str(error))
    else:
        result['fee_issues'].append('FEE_SCHEDULE_UNAVAILABLE_OR_CONFLICTING')
    return result


def book_input(capture, market, token, *, decision_ms, max_age_ms=10000):
    need(token in market['tokens'], 'BOOK_TOKEN_NOT_IN_MARKET')
    value = decoded(capture, 'https://clob.polymarket.com/book?token_id=' + token, decision_ms, max_age_ms)
    need(value.get('asset_id') == token and value.get('market') == market['condition_id'], 'BOOK_IDENTITY')
    bids, asks = value.get('bids'), value.get('asks')
    _levels(bids)
    _levels(asks)
    state_hash = value.get('hash')
    need(isinstance(state_hash, str) and 0 < len(state_hash) <= 256 and state_hash.isascii(), 'VENUE_BOOK_HASH_MISSING')
    stamp = value.get('timestamp')
    need(type(stamp) is int or isinstance(stamp, str) and re.fullmatch(r'[0-9]+', stamp), 'BOOK_TIMESTAMP')
    stamp = int(stamp)
    need(0 <= stamp <= capture['received_ms'] + 1000, 'BOOK_CLOCK_FUTURE')
    tick = _number(value.get('tick_size'))
    need(0 < tick <= 1, 'BOOK_TICK')
    if market.get('tick_size') is not None:
        need(tick == _number(market['tick_size']), 'MARKET_BOOK_TICK_MISMATCH')
    minimum = _number(value.get('min_order_size'))
    need(minimum > 0, 'MINIMUM_ORDER_SIZE')
    return dict(asset_id=token, asks=[dict(x) for x in asks], bids=[dict(x) for x in bids],
                received_ms=capture['received_ms'], time_origin='RESPONSE_RECEIVED',
                continuity='VERIFIED_FULL_REST_SNAPSHOT', source_sha256=capture['raw_sha256'],
                venue_book_hash=state_hash, venue_timestamp_ms=stamp, tick_size=str(tick),
                minimum_order_size=str(minimum), minimum_order_size_unit='CAPTURED_FIELD_NO_ORDER_ADMISSION',
                stream_continuity_proven=False)
