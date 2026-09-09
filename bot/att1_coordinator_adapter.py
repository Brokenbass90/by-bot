"""Bybit evidence -> existing ATT1 event contract. No transport or send API.

These pure mappers validate broker-shaped records, not their authenticity.
The owning process must durably bind account/order identities and collect
complete signed evidence before any live use. No ACK manufactures a fill or
protective stop. Synthetic fixtures exercise this boundary without credentials.
"""
from collections.abc import Mapping
from fractions import Fraction
from research_lab.att1_ets2s_accounting import _decimal, AccountingViolation
from research_lab.att1_lifecycle_coordinator import digest

SEND_ENABLED = False


class AdapterViolation(ValueError):
    """Unsupported, mismatched or incomplete broker evidence."""


def _text(value, name):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise AdapterViolation('missing/invalid ' + name)
    return value


def _number(value, name, **kw):
    try:
        return _decimal(value, name, **kw)
    except AccountingViolation as exc:
        raise AdapterViolation(str(exc)) from exc


def _event(row, kind, identity, exchange_text, received_ms, fields):
    if not isinstance(exchange_text, str) or not exchange_text.isascii() or not exchange_text.isdigit() or len(exchange_text)>16:
        raise AdapterViolation('invalid broker timestamp')
    ex = int(exchange_text)
    if type(received_ms) is not int or not 0 < ex <= received_ms:
        raise AdapterViolation('invalid receive clock')
    source = digest(row)
    return {'schema_id':'att1_lifecycle_event_v1','event_id':'bybit:'+kind+':'+identity+':'+str(received_ms),
            'kind':kind,'exchange_ms':ex,'received_ms':received_ms,'source_sha256':source,**fields}


def map_execution(row, *, symbol, expected_order_id, expected_order_link_id,
                  kind, received_ms, exit_order_id=None):
    """Map Trade only. Funding execFee has a different sign and is refused."""
    if not isinstance(row, Mapping) or kind not in {'ENTRY_FILL','EXIT_FILL'}:
        raise AdapterViolation('invalid execution input/kind')
    for name, expected in (('symbol',symbol),('orderId',expected_order_id),('orderLinkId',expected_order_link_id)):
        _text(expected,name)
        if row.get(name) != expected:
            raise AdapterViolation('foreign ' + name)
    if row.get('execType') != 'Trade' or row.get('side') != ('Sell' if kind=='ENTRY_FILL' else 'Buy'):
        raise AdapterViolation('unsupported execution type/side')
    if row.get('feeCurrency') != 'USDT' or row.get('extraFees') != '':
        raise AdapterViolation('unmapped fee currency/extraFees')
    if type(row.get('isMaker')) is not bool:
        raise AdapterViolation('invalid liquidity')
    qty = _number(row.get('execQty'),'execQty',positive=True)
    _number(row.get('execPrice'),'execPrice',positive=True)
    # Missing fee stays unknown, never zero-filled by the adapter.
    fee = row.get('execFee')
    if fee is not None: _number(fee,'execFee')
    closed = _number(row.get('closedSize'),'closedSize',nonnegative=True)
    if closed != (0 if kind=='ENTRY_FILL' else qty):
        raise AdapterViolation('execution exposure direction mismatch')
    fields = {'execution_id':_text(row.get('execId'),'execId'), 'qty':row['execQty'],
              'price':row['execPrice'],'fee_amount':fee,'fee_source_sha256':digest(row),
              'liquidity':'MAKER' if row['isMaker'] else 'TAKER'}
    if kind == 'EXIT_FILL': fields['exit_order_id'] = _text(exit_order_id,'exit_order_id')
    elif exit_order_id is not None: raise AdapterViolation('exit identity on entry')
    return _event(row,kind,fields['execution_id'],row.get('execTime'),received_ms,fields)


def map_funding(row, *, symbol, received_ms):
    """UTA linear-USDT SETTLEMENT funding is signed cash: receive +, pay -.

    Require the transaction cash equation and unambiguous short quantity. Never
    derive an effective mark/rate to make a proxy equal broker-rounded cash.
    """
    if not isinstance(row, Mapping): raise AdapterViolation('invalid funding input')
    for key,value in (('symbol',symbol),('category','linear'),('currency','USDT'),
                      ('type','SETTLEMENT'),('side','Sell')):
        if row.get(key) != value: raise AdapterViolation('funding ' + key)
    for name in ('extraFees','transSubType'):
        if row.get(name) != '': raise AdapterViolation('unmapped funding ' + name)
    bonus = row.get('bonusChange')
    if bonus != '' and _number(bonus,'bonusChange') != 0:
        raise AdapterViolation('unmapped funding bonus')
    qty = _number(row.get('qty'),'funding qty',positive=True)
    if _number(row.get('size'),'funding size') != -qty:
        raise AdapterViolation('ambiguous funding quantity')
    amount = _number(row.get('funding'),'funding')
    if (_number(row.get('cashFlow'),'cashFlow') != 0 or _number(row.get('fee'),'fee') != 0
            or _number(row.get('change'),'change') != amount):
        raise AdapterViolation('funding cash reconciliation mismatch')
    identity = _text(row.get('id'),'settlement id')
    event = _event(row,'FUNDING_CASH',identity,row.get('transactionTime'),received_ms,
                  {'settlement_id':identity,'qty_at_settlement':row['qty'],
                   'cash_amount':row['funding'],'currency':'USDT'})
    event['settlement_ms'] = event['exchange_ms']
    return event


def _broker_receipt(receipt):
    if not isinstance(receipt, Mapping) or receipt.get('plan',{}).get('profile_id') != 'BROKER_REPLAY_ATT1_V1':
        raise AdapterViolation('broker replay receipt required')
    return receipt['plan']


def map_order_final(row, *, receipt, expected_order_id, expected_order_link_id,
                    received_ms, entry):
    """Terminal order evidence only, after executions have been reconciled."""
    p = _broker_receipt(receipt)
    if not isinstance(row, Mapping) or type(entry) is not bool:
        raise AdapterViolation('invalid order input')
    for name,expected in (('symbol',p['symbol']),('orderId',expected_order_id),
                          ('orderLinkId',expected_order_link_id)):
        _text(expected,name)
        if row.get(name) != expected: raise AdapterViolation('foreign order ' + name)
    if (type(row.get('positionIdx')) is not int or row['positionIdx'] != 0
            or row.get('side') != ('Sell' if entry else 'Buy')
            or row.get('reduceOnly') is not (not entry)):
        raise AdapterViolation('order direction/mode mismatch')
    statuses = {'Filled':'FILLED','Cancelled':'CANCELLED','Rejected':'REJECTED',
                'PartiallyFilledCanceled':'CANCELLED'}
    status = statuses.get(row.get('orderStatus'))
    if status is None: raise AdapterViolation('order finality not confirmed')
    if entry:
        requested = _number(p['requested_qty'],'requested_qty',positive=True)
        filled = Fraction(receipt['accounting']['aggregate_entry_qty'])
    else:
        pending = receipt.get('pending_exit')
        if pending is None: raise AdapterViolation('no coordinator exit intent')
        requested = Fraction(pending['qty'])
        filled = requested - Fraction(pending['remaining_qty'])
    if _number(row.get('qty'),'order qty',positive=True) != requested:
        raise AdapterViolation('order quantity mismatch')
    if _number(row.get('cumExecQty'),'cumExecQty',nonnegative=True) != filled:
        raise AdapterViolation('unreconciled order executions')
    if (status=='FILLED' and filled != requested) or (status=='REJECTED' and filled != 0):
        raise AdapterViolation('inconsistent order finality')
    fields = {'status':status}
    if not entry: fields['exit_order_id'] = pending['exit_order_id']
    return _event(row,'ENTRY_FINAL' if entry else 'EXIT_FINAL',expected_order_id,
                  row.get('updatedTime'),received_ms,fields)


def map_protection(position, stop_order, *, receipt, received_ms):
    """Prove exact full-position stop from position AND live conditional order."""
    p = _broker_receipt(receipt)
    if not isinstance(position,Mapping) or not isinstance(stop_order,Mapping):
        raise AdapterViolation('missing protection evidence')
    held = Fraction(receipt['held_qty'])
    if held <= 0: raise AdapterViolation('no exposure to protect')
    for row in (position,stop_order):
        if row.get('symbol') != p['symbol'] or type(row.get('positionIdx')) is not int or row['positionIdx'] != 0:
            raise AdapterViolation('protection symbol/mode mismatch')
    if (position.get('side')!='Sell' or _number(position.get('size'),'position size',positive=True)!=held
            or _number(position.get('stopLoss'),'stopLoss',positive=True)!=Fraction(p['original_stop'])):
        raise AdapterViolation('position protection mismatch')
    if (stop_order.get('side')!='Buy' or stop_order.get('orderStatus')!='Untriggered'
            or stop_order.get('stopOrderType')!='StopLoss' or stop_order.get('reduceOnly') is not True
            or stop_order.get('closeOnTrigger') is not True
            or _number(stop_order.get('qty'),'stop qty',positive=True)!=held
            or _number(stop_order.get('triggerPrice'),'triggerPrice',positive=True)!=Fraction(p['original_stop'])):
        raise AdapterViolation('conditional stop not proven')
    identity = _text(stop_order.get('orderId'),'stop orderId')
    # Validate both clocks independently before taking their latest timestamp.
    events = [_event(row,'PROTECTION_ACK',identity,row.get('updatedTime'),received_ms,{})
              for row in (position,stop_order)]
    from research_lab.att1_lifecycle_profile import _decimal_text
    result = _event({'position':position,'stop_order':stop_order},'PROTECTION_ACK',identity,
                   str(max(e['exchange_ms'] for e in events)),received_ms,
                   {'qty':_decimal_text(held),'stop':p['original_stop']})
    return result
