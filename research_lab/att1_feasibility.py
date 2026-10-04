"""Pure ATT1 orders-OFF economics diagnostic, never a signal/admission oracle.

Prices describe one captured bid. The nearest tick stop is an optimistic
minimum-lot scenario, not a frozen strategy stop. Branch bounds apply to any
positive frozen broker quantity at that entry under the captured cost policy.
They do not prove future venue limits, profitability, or money readiness.
"""
from collections.abc import Mapping
from fractions import Fraction

from bot.att1_canary_preparation import assess_att1_14day_quantity, _clock
from bot.att1_coordinator_adapter import AdapterViolation, _number
from research_lab.att1_lifecycle_coordinator import digest
from research_lab.att1_lifecycle_profile import _decimal_text


def assess_symbol_feasibility(*, symbol, instrument_page, fee_page, ticker_page,
        now_ms, absolute_risk_usdt, daily_remaining_usdt, max_notional_usdt):
    """Bound all three frozen sizing branches; return no trading authority.

    For target t>=one step, floor(t/step)*step > t/2. Thus risk-limited
    sizing retains >R/2 risk; notional-limited sizing retains >N/2 stop
    notional. Market-max sizing has the exact floored market maximum. Every
    admitted size must also have q>=the rounded venue minimum at this bid.
    Taking the minimum of the three bounds covers ties and all branches.
    """
    out = {'schema_id':'att1_symbol_feasibility_v1','symbol':symbol,
           'scenario_kind':'CAPTURED_BID_MINIMUM_LOT_NEAREST_TICK_NOT_A_SIGNAL',
           'actual_signal_available':False,'money_ready':False,'orders_allowed':False,
           'future_ceiling_proven':False,'quantity_changed':False,
           'source_sha256':digest({'instrument':instrument_page,'fee':fee_page,'ticker':ticker_page})}
    try:
        if type(now_ms) is not int or now_ms<=0:
            raise AdapterViolation('invalid diagnostic clock')
        if (not isinstance(ticker_page,Mapping) or type(ticker_page.get('retCode')) is not int
                or ticker_page['retCode']!=0):
            raise AdapterViolation('invalid ticker envelope')
        _clock(ticker_page.get('time'),now_ms,'ticker')
        result=ticker_page.get('result')
        if (not isinstance(result,Mapping) or result.get('category')!='linear'
                or not isinstance(result.get('list'),list) or len(result['list'])!=1
                or not isinstance(result['list'][0],Mapping)
                or result['list'][0].get('symbol')!=symbol):
            raise AdapterViolation('ambiguous ticker source')
        price=_number(result['list'][0].get('bid1Price'),'captured bid',positive=True)
        instrument=instrument_page['result']['list'][0]
        lots=instrument['lotSizeFilter']
        step=_number(lots['qtyStep'],'qty step',positive=True)
        minimum=_number(lots['minOrderQty'],'min qty',positive=True)
        min_n=_number(lots['minNotionalValue'],'min notional',positive=True)
        maximum=_number(lots['maxMktOrderQty'],'market maximum',positive=True)
        tick=_number(instrument['priceFilter']['tickSize'],'tick',positive=True)
        # Round UP to a valid venue minimum; never apply this to frozen admission.
        minimum_qty=(-(-max(minimum,min_n/price)//step))*step
        stop=(price//tick+1)*tick
        assessment=assess_att1_14day_quantity(symbol=symbol,
            instrument_page=instrument_page,fee_page=fee_page,now_ms=now_ms,
            requested_qty=_decimal_text(minimum_qty),entry_price=_decimal_text(price),
            original_stop=_decimal_text(stop),absolute_risk_usdt=absolute_risk_usdt,
            daily_remaining_usdt=daily_remaining_usdt,max_notional_usdt=max_notional_usdt)
        if assessment['status']=='BLOCKED_SOURCE_INPUTS':
            raise AdapterViolation(assessment.get('reason','invalid cost sources'))
        if assessment['status']=='BLOCKED_VENUE_MINIMUM_OR_STEP':
            out.update(status='REJECT_VENUE_MINIMUM',minimum_scenario=assessment)
            return out
        events=assessment['funding_settlements']
        fee=_number(fee_page['result']['list'][0]['takerFeeRate'],'taker fee',nonnegative=True)
        lower=_number(instrument['lowerFundingRate'],'funding lower bound')
        cost_rate=2*fee+events*max(-lower,Fraction(0))
        risk=_number(absolute_risk_usdt,'risk cap',positive=True)
        daily=_number(daily_remaining_usdt,'daily remaining',nonnegative=True)
        notional=_number(max_notional_usdt,'notional cap',positive=True)
        bounds={'risk_limited':risk/2+cost_rate*minimum_qty*price,
                'notional_limited':cost_rate*notional/2,
                'market_max_limited':cost_rate*(maximum//step)*step*price}
        bound=min(bounds.values())
        out.update(captured_bid=_decimal_text(price),
            nearest_tick_stop=_decimal_text(stop),minimum_venue_quantity=_decimal_text(minimum_qty),
            minimum_scenario=assessment,cost_reserve_rate=_decimal_text(cost_rate),
            sizing_lower_bounds_usdt={k:_decimal_text(v) for k,v in bounds.items()},
            all_branches_lower_bound_usdt=_decimal_text(bound),
            status=('REJECT_FROZEN_SIZING_BUDGET' if bound>=daily else 'NOT_PROVEN_FEASIBLE'),
            bound_scope='same captured entry price, instrument/fee limits and frozen R/N/hold; no signal or future ceiling')
    except (AdapterViolation,KeyError,TypeError,ValueError,IndexError) as exc:
        out.update(status='BLOCKED_SOURCE_INPUTS',reason=str(exc))
    return out
