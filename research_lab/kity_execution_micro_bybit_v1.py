"""Pure Bybit material-identity adapters. No sender/authentication capability.

Caller must retain and authenticate full GET payloads/account scope. Canonical
row hashes below supplement that raw evidence; they are not wire-byte hashes.
No old generic manager or strategy imports; no fallback to foreign holdings.
"""
from bot.kity_m3_orders_off import digest
from research_lab.kity_execution_micro_runtime_v1 import (
    TERMINAL, integer, numeric, signed, text, validate_plan,
)


def _identity(plan, state, row):
    validate_plan(plan)
    orders = [(v, False) for v in state['entries'].values()] + [(v, True) for v in state['exits'].values()]
    link, broker_id = row.get('orderLinkId'), row.get('orderId')
    if not isinstance(broker_id, str) or not broker_id:
        raise ValueError('BROKER_ORDER_ID_REQUIRED')
    matches = [(v, exit) for v, exit in orders
               if (v['link'] == link if link else v['order_id'] == broker_id and v['order_id'] is not None)]
    if len(matches) != 1:
        raise ValueError('OWNED_ORDER_REQUIRED')
    order, exit = matches[0]
    leg = next(l for l in plan['legs'] if l['symbol'] == order['symbol'])
    side = ('Sell' if leg['side'] == 'Buy' else 'Buy') if exit else leg['side']
    if (row.get('symbol') != leg['symbol'] or row.get('side') != side
            or order['order_id'] not in (None, broker_id)):
        raise ValueError('MATERIAL_ORDER_IDENTITY_CONFLICT')
    return order, leg, exit


def _event(kind, row, observed_ms, **fields):
    pin = digest(row)
    return dict(kind=kind, event_id=kind + '-' + digest(dict(row=row, observed_ms=observed_ms)),
                at_ms=integer(observed_ms), source_sha256=pin, **fields)


def execution_event(plan, state, row, *, observed_ms):
    order, _, exit = _identity(plan, state, row)
    if row.get('execType') != 'Trade' or not isinstance(row.get('execId'), str) or not row['execId']:
        raise ValueError('EXACT_TRADE_EXECUTION_REQUIRED')
    # Actual API uses decimal-string milliseconds. No bool/float coercion.
    ts = row.get('execTime')
    if isinstance(ts, str) and ts.isascii() and ts.isdecimal():
        ts = int(ts)
    if integer(ts) > integer(observed_ms):
        raise ValueError('EXECUTION_CLOCK_CONFLICT')
    quantity, price = numeric(row.get('execQty')), numeric(row.get('execPrice'))
    value = row.get('execFee')
    fee = None if value is None or value == '' else text(signed(value))
    if row.get('feeCurrency') not in (None, '', 'USDT'):
        raise ValueError('FEE_CURRENCY_CONFLICT')
    return _event('EXIT_FILL' if exit else 'ENTRY_FILL', row, observed_ms,
        symbol=order['symbol'], order_link_id=order['link'], order_id=row['orderId'],
        execution_id=row['execId'], quantity=text(quantity), price=text(price), fee_usdt=fee,
        source_execution_ms=ts)


def order_events(plan, state, row, *, observed_ms):
    order, leg, exit = _identity(plan, state, row)
    expected = numeric(order['quantity'] if exit else leg['quantity'])
    # Full native stops are exchange-resized/cancelled with the position. Only
    # a bound broker ID and zero-fill deactivation may shrink this identity field.
    native_cancel=(order.get('is_native_protection') and row.get('stopOrderType')=='StopLoss'
        and row.get('orderStatus') in {'Cancelled','Deactivated'}
        and numeric(row.get('cumExecQty'),zero=True)==0
        and numeric(row.get('qty'),zero=True)<=expected)
    resized=None
    if order.get('is_native_protection') and not native_cancel and numeric(row.get('qty'))!=expected:
        q=numeric(row['qty'])
        if (row.get('stopOrderType')!='StopLoss' or row['orderId']!=order['order_id']
            or numeric(row.get('triggerPrice'))!=numeric(leg['request'].get('stopLoss'))
            or q>expected or q<numeric(order['filled'],zero=True)):
            raise ValueError('NATIVE_RESIZE_IDENTITY_CONFLICT')
        resized=_event('NATIVE_PROTECTION_RESIZE',row,observed_ms,symbol=order['symbol'],
            order_link_id=order['link'],order_id=order['order_id'],quantity=text(q))
        expected=q
    if ((not native_cancel and numeric(row.get('qty')) != expected) or row.get('reduceOnly') is not exit
            or row.get('positionIdx') != 0 or type(row.get('positionIdx')) is not int
            or row.get('orderType') != ('Market' if exit else 'Limit')):
        raise ValueError('EXACT_OWNED_REQUEST_CONFLICT')
    role = 'EXIT' if exit else 'ENTRY'
    common = dict(symbol=order['symbol'], order_link_id=order['link'], order_id=row['orderId'])
    result = ([resized] if resized else [])+[_event(role + '_ACK', row, observed_ms, **common)]
    status = row.get('orderStatus')
    if status in TERMINAL:
        quantity = numeric(row.get('cumExecQty'), zero=True)
        if quantity > expected:
            raise ValueError('CUMULATIVE_FILL_EXCEEDS_REQUEST')
        result.append(_event(role + '_TERMINAL', row, observed_ms,
                             status=status, filled_quantity=text(quantity), **common))
    elif status not in {'New', 'PartiallyFilled', 'Untriggered', 'Triggered', 'Created'}:
        raise ValueError('UNKNOWN_ORDER_STATUS')
    return result
