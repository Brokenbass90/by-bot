from decimal import Decimal as D
import pytest

from research_lab.kity_execution_micro_bybit_v1 import execution_event, order_events
from test_kity_micro_runtime_v1 import plan


def context():
    p=plan();leg=p['legs'][0]
    return p,dict(entries={leg['symbol']:dict(symbol=leg['symbol'],link=leg['request']['orderLinkId'],
        order_id='broker-owned',filled='0',terminal=False)},exits={})


def execution():
    p,s=context()
    return dict(symbol=p['legs'][0]['symbol'],orderId='broker-owned',
        orderLinkId=p['legs'][0]['request']['orderLinkId'],side='Buy',execType='Trade',
        execId='owned-exec-1',execQty='1.00',execPrice='1.0200',execFee='.001',execTime='2000')


def order():
    e=execution()
    return dict(symbol=e['symbol'],orderId=e['orderId'],orderLinkId=e['orderLinkId'],
        side='Buy',qty='1.00',positionIdx=0,reduceOnly=False,orderType='Limit',
        cumExecQty='1.00',orderStatus='Filled')


def test_actual_trade_fields_map_without_adding_or_dropping_fee():
    p,s=context();e=execution_event(p,s,execution(),observed_ms=2100)
    assert e['kind']=='ENTRY_FILL' and D(e['quantity'])==1
    assert D(e['price'])==D('1.02') and D(e['fee_usdt'])==D('.001')
    assert len(e['source_sha256'])==64


@pytest.mark.parametrize('field,value', [('symbol','FOREIGNUSDT'),('side','Sell'),
    ('orderId','foreign'),('orderLinkId','foreign'),('execType','Funding')])
def test_foreign_material_identity_is_blocked(field,value):
    p,s=context();r=execution();r[field]=value
    with pytest.raises(ValueError):execution_event(p,s,r,observed_ms=2100)


@pytest.mark.parametrize('field,value', [('execQty',True),('execQty','NaN'),('execPrice','0'),
    ('execFee','Infinity'),('execTime','3000')])
def test_invalid_or_future_execution_fields_are_not_zero(field,value):
    p,s=context();r=execution();r[field]=value
    with pytest.raises(ValueError):execution_event(p,s,r,observed_ms=2100)


def test_unknown_fee_is_none_not_zero():
    p,s=context();r=execution();del r['execFee']
    assert execution_event(p,s,r,observed_ms=2100)['fee_usdt'] is None


def test_missing_link_requires_already_bound_broker_order_id():
    p,s=context();r=execution();r['orderLinkId']=''
    assert execution_event(p,s,r,observed_ms=2100)['order_link_id']==p['legs'][0]['request']['orderLinkId']
    s['entries'][p['legs'][0]['symbol']]['order_id']=None
    with pytest.raises(ValueError):execution_event(p,s,r,observed_ms=2100)


@pytest.mark.parametrize('field,value', [('qty','2'),('side','Sell'),('reduceOnly',True),
    ('positionIdx',True),('orderType','Market')])
def test_order_readback_preserves_exact_owned_request(field,value):
    p,s=context();r=order();r[field]=value
    with pytest.raises(ValueError):order_events(p,s,r,observed_ms=2100)


def test_order_ack_is_not_a_fill_and_terminal_does_not_fabricate_executions():
    p,s=context();events=order_events(p,s,order(),observed_ms=2100)
    assert [e['kind'] for e in events]==['ENTRY_ACK','ENTRY_TERMINAL']
    assert all('execution_id' not in e for e in events)


def test_exit_mapping_requires_known_reduce_only_order():
    p,s=context();leg=p['legs'][0];link=leg['exit_prefix']+'-0'
    s['exits'][link]=dict(symbol=leg['symbol'],link=link,order_id='broker-exit',quantity='1')
    r=execution();r.update(orderId='broker-exit',orderLinkId=link,side='Sell')
    assert execution_event(p,s,r,observed_ms=2100)['kind']=='EXIT_FILL'
    o=order();o.update(orderId='broker-exit',orderLinkId=link,side='Sell',reduceOnly=True,orderType='Market')
    assert order_events(p,s,o,observed_ms=2100)[-1]['kind']=='EXIT_TERMINAL'
