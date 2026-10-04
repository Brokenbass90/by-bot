"""Pure research projections; no order, account or admission authority."""
from decimal import Decimal, localcontext
from fractions import Fraction as F
from itertools import product
import re


def _amount(value, *, positive=False):
    if not isinstance(value,str) or len(value)>128 or not re.fullmatch(r'-?\d+(?:\.\d+)?',value):
        raise ValueError('invalid decimal')
    out=F(value)
    if positive and out<=0:raise ValueError('amount must be positive')
    return out


def _text(value):
    with localcontext() as ctx:
        ctx.prec=100
        return format(Decimal(value.numerator)/Decimal(value.denominator),'f').rstrip('0').rstrip('.') if value.denominator!=1 else str(value.numerator)


def book_projection(raw, *, kind, received_ms, used_ms):
    if kind not in ('rest','ws') or type(received_ms) is not int or type(used_ms) is not int or used_ms<received_ms:
        raise ValueError('invalid source clocks')
    data=raw.get('result' if kind=='rest' else 'data',{})
    if not isinstance(data,dict):raise ValueError('invalid book payload')
    cts=data.get('cts',raw.get('cts'))
    if cts is not None and (type(cts) is not int or cts<=0):raise ValueError('invalid CTS')
    freshness=('UNKNOWN_CTS' if cts is None else 'FUTURE' if cts>received_ms else
               'STALE' if used_ms-cts>2000 else 'FRESH')
    return {'symbol':data.get('s'),'cts':cts,'ts':data.get('ts',raw.get('ts')),
            'server_time':raw.get('time'),'u':data.get('u'),'seq':data.get('seq'),
            'received_ms':received_ms,'used_ms':used_ms,'use_delay_ms':used_ms-received_ms,
            'receipt_cts_age_ms':None if cts is None else received_ms-cts,
            'use_cts_age_ms':None if cts is None else used_ms-cts,'freshness':freshness,
            'orders_allowed':False,'quiet_book_proven':False}


def funding_comparison(*, qty, entry, stop, lower_rate, interval_minutes,
                       taker_rate, historical43_adverse):
    q,e,s=[_amount(x,positive=True) for x in (qty,entry,stop)]
    if s<=e or type(interval_minutes) is not int or interval_minutes<=0:raise ValueError('invalid frozen short/interval')
    lower,fee,history=[_amount(x) for x in (lower_rate,taker_rate,historical43_adverse)]
    if not -1<lower<1 or not 0<=fee<1 or not 0<=history<1:raise ValueError('invalid rate')
    events=(20160+interval_minutes-1)//interval_minutes+1
    risk=q*(s-e)*F('1.1');n=q*s;old_funding=events*max(-lower,F(0));old=risk+n*(2*fee+old_funding)
    candidate=5*history
    compatible=interval_minutes==480
    scenarios=[]
    for growth,liability,gap in product(('1','1.1','1.5'),('0','0.4'),('0','0.4')):
        cost=n*_amount(growth)*(2*fee+candidate);total=risk+cost+_amount(liability)+_amount(gap)
        scenarios.append({'notional_multiplier':growth,'unresolved_liability_usdt':liability,
                          'exit_gap_stress_usdt':gap,'total_required_usdt':_text(total),
                          'fits_draft_budget':compatible and risk<=F('.4') and n<=100 and total<=F('.8'),
                          'candidate_status':('RESEARCH_ONLY_NOT_MONEY_READY' if compatible else 'BLOCKED_INTERVAL_CHANGED')})
    return {'schema_id':'att1_funding_shadow_comparison_v1','requested_qty':qty,
            'quantity_changed':False,'required_risk_usdt':_text(risk),
            'old_funding_rate_envelope':_text(old_funding),'old_required_usdt':_text(old),
            'old_fits_draft_budget':risk<=F('.4') and n<=100 and old<=F('.8'),
            'candidate_funding_rate':_text(candidate),'scenarios':scenarios,
            'historical_interval_compatible':compatible,
            'orders_allowed':False,'candidate_money_ready':False,'liquidation_bound_proven':False,
            'mark_price_bound_proven':False,'future_funding_bound_proven':False,
            'fee_tier_persistence_proven':False,'daily_ledger_enforced':False}
