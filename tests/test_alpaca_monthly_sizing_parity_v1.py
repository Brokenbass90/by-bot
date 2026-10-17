"""Sizing proof must include the real request serializer, with no network."""
import copy
from decimal import Decimal
from types import MethodType
import pytest

from test_alpaca_monthly_native_binding_v1 import setup,ticket
from scripts import equities_alpaca_paper_bridge as native


def test_monthly_native_wire_notional_cannot_round_above_approved_size(setup):
    book,selection,adapter,broker,now=setup
    prepared=ticket(setup);wire=[]
    def request(method,path,payload):
        assert method=='POST' and path=='/v2/orders'
        wire.append(copy.deepcopy(payload))
        row=dict(**payload,id='entry',qty='.3',status='filled',filled_qty='.3',
            filled_avg_price='311.222',filled_at='2026-11-02T14:30:01Z')
        broker.orders['entry']=row
        broker.positions=[dict(symbol='NET',qty='.3',avg_entry_price='311.222',side='long')]
        return copy.deepcopy(row)
    broker._request=request
    # Exercise the actual client serializer, rather than the old fixture's
    # unformatted float. No HTTP client/credentials are constructed here.
    broker.submit_market_buy=MethodType(native.AlpacaClient.submit_market_buy,broker)
    result=adapter.enter(prepared,now_ms=now+1000,apply=True)
    assert result['status']=='MONTHLY_NATIVE_PROTECTED'
    assert Decimal(wire[0]['notional'])<=Decimal(str(prepared['notional']))
    assert abs(float(wire[0]['notional'])-prepared['notional'])<=1e-9


@pytest.mark.parametrize('cash,equity,weight,cap,expected',[
    (1000.,1000.,.6,None,420.),
    (10.,1000.,.6,None,10.),
    (1000.,1500.,.6,487.42,204.7164),
    (1000.,200.,.6,487.42,84.),
])
def test_actual_compiler_math_and_explicit_live_ceiling(cash,equity,weight,cap,expected):
    from scripts import audit_alpaca_monthly_sizing_v1 as audit
    assert abs(audit.compile_notional(cash,equity,weight,capital_ceiling=cap)-expected)<1e-9


def test_reference_scale_fixture_does_not_relax_production_constructor(tmp_path):
    from research_lab.alpaca_monthly_binding_v1 import MonthlyBook,CONTRACT
    from research_lab.alpaca_monthly_native_binding_v1 import MonthlyNativeBinding
    book=MonthlyBook(tmp_path/'book.sqlite',CONTRACT)
    with pytest.raises(ValueError,match='MONTHLY_CAPITAL_CAP'):
        MonthlyNativeBinding(book,client=object(),base_url=native._PAPER_API_URL,account_id='fixture',
            capital=1000.,runtime=tmp_path/'runtime',lock_path=tmp_path/'lock',entry_halt_path=tmp_path/'HALT')
