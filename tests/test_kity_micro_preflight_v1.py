from decimal import Decimal as D
import pytest

from research_lab.kity_micro_preflight_v1 import bounded_profile,build_preflight,attach_native_guards
from research_lab.kity_execution_micro_runtime_v1 import BASKET
from research_lab.kity_micro_transport_v1 import SourceError


def market():
    captures={};instruments=[]
    for index,(s,side) in enumerate(BASKET):
        price=D('7.16') if s=='BNBUSDT' else D('1')
        i=dict(symbol=s,side=side,quantity_step='1',minimum_quantity='10' if index==0 else '1',
            minimum_notional='.1',tick_size='.0001',configured_leverage='3',position_idx=0,
            taker_fee='.00055')
        instruments.append(i)
        captures['instrument:'+s]=dict(body=dict(result=dict(list=[dict(lotSizeFilter=dict(maxMktOrderQty='1000'))])))
        captures['book:'+s]=dict(body=dict(result=dict(b=[[str(price),'1000']],a=[[str(price+D('.0001')),'1000']])))
    return captures,instruments


def test_bound_profile_searches_exact_rounding_frontier_instead_of_stopping_at_invalid_floor():
    c,i=market();p=bounded_profile(c,i,D('.203'))
    assert D(p['common_reference_target'])>D('10.001')
    assert next(l for l in p['legs'] if l['symbol']=='BNBUSDT')['quantity']=='2'
    assert max(D(l['rounding_shortfall_fraction']) for l in p['legs'])<=D('.203')
    assert len(p['legs'])==10
    assert all(l['draft_entry']['timeInForce']=='IOC' for l in p['legs'])


def test_private_capture_pin_failure_occurs_before_geometry_or_account_adoption(tmp_path):
    p=tmp_path/'capture.json';p.write_text('{}')
    with pytest.raises(SourceError,match='CAPTURE_PIN_CONFLICT'):
        build_preflight(p,'a'*64,{})


def test_native_guard_distances_use_only_the_approved_loss_budget_and_source_ticks():
    c,i=market();p=bounded_profile(c,i,D('.203'))
    attach_native_guards(p,i,D('15'),D('.10'))
    price_loss=D(0)
    for leg in p['legs']:
        req=leg['draft_entry'];q=D(req['qty']);entry=D(req['price']);stop=D(req['stopLoss'])
        price_loss+=q*abs(entry-stop)
        assert req['tpslMode']=='Full' and req['slOrderType']=='Market' and req['slTriggerBy']=='LastPrice'
    assert price_loss+D(p['constant_price_roundtrip_fees'])+D('.10')<=D('15')
