"""Explain frozen 84-case sizing, never a trading admission or live-price replay.

Independent Decimal arithmetic cross-checked against source_sizing in tests.
Historical entry prices replace fixture quotes exactly as in the native84
harness; 26Oct filters/fees are dated. No account, network, writer or authority.
"""
import collections
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR


def number(value, *, zero=False):
    result = D(str(value))
    if isinstance(value, bool) or not result.is_finite() or (result < 0 if zero else result <= 0):
        raise ValueError('INVALID_SIZING_NUMBER')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def analyze(data):
    if data['schema'] != 'PUMP4_NATIVE_84_REFERENCE_FIXTURE_V1':
        raise ValueError('FROZEN_FIXTURE_REQUIRED')
    policy = data['policy']
    # This is an attribution of one preserved acceptance, not a parameter tool.
    if digest(policy) != 'befacba9bd781538b92fb6c195c0b996450fcb54656584b8c614b5f17a2d2502':
        raise ValueError('DIFFERENT_POLICY_REQUIRES_SEPARATE_ANALYSIS')
    risk, gross, allocation = (number(policy[k]) for k in ('risk_usdt', 'gross_usdt', 'allocation_usdt'))
    reserve = number(policy['reserve_usdt'], zero=True)
    slip = number(policy['slippage_bps'], zero=True) / 10000
    rows = []
    for index, case in enumerate(data['cases']):
        plan, inst = case['plan'], case['instrument']
        if plan['side'] != 'short' or plan['fractions'] != [.4, .6] or plan['hold_bars'] != 168:
            raise ValueError('DIFFERENT_EXECUTION_CONTRACT')
        if plan['plan_sha256'] != digest({k: v for k, v in plan.items() if k != 'plan_sha256'}):
            raise ValueError('PLAN_HASH_MISMATCH')
        if not (plan['symbol'] == inst['symbol'] == case['fee']['symbol']):
            raise ValueError('INSTRUMENT_IDENTITY')
        price, stop = number(plan['entry']), number(plan['stop'])
        if stop <= price:
            raise ValueError('SHORT_STOP_GEOMETRY')
        lots = inst['lotSizeFilter']
        step, min_qty, min_notional, max_qty = (number(lots[k]) for k in
            ('qtyStep', 'minOrderQty', 'minNotionalValue', 'maxMktOrderQty'))
        unit = 5 * step  # Exact .4/.6 split, both quantities integral lot multiples.
        minimum = (max(min_qty / D('.4'), min_notional / price) / unit).to_integral_value(rounding=ROUND_CEILING) * unit
        distance = max(abs(price-stop), abs(price*(1-slip)-stop))
        fee = number(case['fee']['takerFeeRate'], zero=True)
        interval = inst['fundingInterval']
        if type(interval) is not int or interval <= 0:
            raise ValueError('FUNDING_INTERVAL_UNKNOWN')
        low = D(inst['lowerFundingRate'])
        if not low.is_finite() or low > 0:
            raise ValueError('FUNDING_CAP_UNKNOWN')
        cap = max(D(0), -low)
        periods = (D(plan['hold_bars']*60) / interval).to_integral_value(rounding=ROUND_CEILING)
        fee_unit, slip_unit, fund_unit = 2*price*fee, 2*price*slip, price*cap*periods
        # Keep source operation order for exact Decimal agreement.
        cost_unit = 2*price*(fee+slip) + fund_unit
        limits = dict(risk=risk/distance, gross=gross/(price*(1+slip)),
                      allocation=allocation/(price*(1+slip)))
        base = (min(limits.values())/unit).to_integral_value(rounding=ROUND_FLOOR)*unit
        selected = (min(base, risk/(distance+cost_unit))/unit).to_integral_value(rounding=ROUND_FLOOR)*unit
        reasons = []
        for name, limit in limits.items():
            if minimum > limit:
                reasons.append(name.upper())
        if minimum > max_qty:
            reasons.append('MAX_MARKET_QTY')
        if base < minimum or base > max_qty:
            status = 'PUMP4_OWNER_CAPACITY_BLOCKED'
        elif base*price + base*(fee_unit+slip_unit) + reserve > allocation:
            status = 'PUMP4_OWNER_CASH_RESERVE'
        elif selected < minimum:
            status = 'PUMP4_OWNER_COST_INCLUSIVE_CAPACITY'
        elif selected*price + selected*cost_unit + reserve > allocation:
            status = 'PUMP4_OWNER_COST_INCLUSIVE_RESERVE'
        else:
            status = 'FIXTURE_SOURCE_SIZING_PASS'
        minimum_risk = minimum*distance
        without_funding = minimum*(distance+2*price*(fee+slip))
        values = dict(
            historical_entry=price, reference_stop=stop, qty_step=step,
            min_order_qty=min_qty, min_entry_notional=min_notional, max_market_qty=max_qty,
            split_quantity_unit=unit, minimum_quantity=minimum,
            minimum_tp1_quantity=minimum*D('.4'), minimum_tp2_quantity=minimum*D('.6'),
            minimum_notional=minimum*price, minimum_gross_with_slippage=minimum*price*(1+slip),
            minimum_stop_risk=minimum_risk, minimum_fee=minimum*fee_unit,
            minimum_slippage=minimum*slip_unit, minimum_funding_stress=minimum*fund_unit,
            minimum_risk_without_funding=without_funding,
            minimum_cost_inclusive_risk=minimum*(distance+cost_unit),
            minimum_cash_with_reserve=minimum*(price+cost_unit)+reserve,
            base_quantity=base, selected_quantity=selected,
            selected_cost_inclusive_risk=selected*distance+selected*cost_unit,
            selected_notional=selected*price,
            taker_fee_per_side=fee, adverse_funding_cap=cap, funding_intervals=periods)
        rows.append(dict(case_index=index, symbol=plan['symbol'], plan_sha256=plan['plan_sha256'],
            signal_bar_open_ms=plan['signal_bar_open_ms'], entry_bar_open_ms=plan['entry_bar_open_ms'],
            status=status, base_minimum_failures=reasons,
            funding_increment_required_for_cost_rejection=(status == 'PUMP4_OWNER_COST_INCLUSIVE_CAPACITY'
                                                          and without_funding <= risk),
            funding_interval_minutes=interval,
            **{k: str(v) for k, v in values.items()}))
    return dict(schema='PUMP4_SAVED_SIZING_ATTRIBUTION_V1', policy=policy,
        policy_sha256=digest(policy), metadata_observed_ms=data['source_metadata_observed_ms'],
        metadata_observed_utc=datetime.fromtimestamp(data['source_metadata_observed_ms']/1000, timezone.utc).isoformat(),
        price_basis='HISTORICAL_REFERENCE_ENTRY_AS_FICTIONAL_BID_ASK_LAST',
        fixture_available_balance='100', effective_allocation_cap=str(allocation),
        actual_available_balance_not_read=True, future_funding_is_known=False,
        live_ready_cases=0, live_readiness='NOT_ESTABLISHED_NO_CURRENT_SIGNAL_OR_FRESH_GET',
        sizing_statuses=dict(collections.Counter(r['status'] for r in rows)),
        base_minimum_failures=dict(collections.Counter('+'.join(r['base_minimum_failures']) for r in rows
                                                      if r['status']=='PUMP4_OWNER_CAPACITY_BLOCKED')),
        cost_failures_requiring_funding_increment=sum(r['funding_increment_required_for_cost_rejection'] for r in rows),
        orders_allowed=False, money_authority=False, real_broker_requests=0, real_broker_writes=0, rows=rows)


if __name__ == '__main__':
    import sys
    from pathlib import Path
    source = Path(sys.argv[1])
    raw = source.read_bytes()
    result = analyze(json.loads(raw))
    result['fixture_sha256'] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, indent=2, allow_nan=False))
