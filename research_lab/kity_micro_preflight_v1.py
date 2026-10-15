"""Fresh captured-source preparation; no network, owner permit or money GO.

Reuses the pinned intake builder's exact sizing/depth/rounding mathematics.
The captured source is new; the original builder and old captures stay intact.
"""
from decimal import Decimal as D,ROUND_CEILING,ROUND_FLOOR
import hashlib
import importlib.util
import json
from pathlib import Path

from research_lab.kity_execution_micro_runtime_v1 import prepare_micro_plan,assess_micro_readiness
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError
from research_lab.kity_execution_micro_v1 import first_target_within_rounding,basket_geometry
from bot.kity_m3_orders_off import _levels,_vwap

ROOT=Path(__file__).resolve().parents[1]
BUILDER='reports/evidence/kity_micro_live_20261015/build_readonly_dossier.py'
BUILDER_SHA='73f4870d8a6c24cb14180f5157fcbdaee2a5756a75a14839bb9f8d473276ef5c'


def bounded_profile(captures,instruments,tolerance):
    """Smallest common target satisfying the already approved floor tolerance."""
    rows=[]
    for i in instruments:
        s=i['symbol'];book=captures['book:'+s]['body']['result']
        maximum=captures['instrument:'+s]['body']['result']['list'][0]['lotSizeFilter']['maxMktOrderQty']
        rows.append(dict(symbol=s,side=i['side'],price=book['a'][0][0] if i['side']=='Buy' else book['b'][0][0],
            bid=book['b'][0][0],step=i['quantity_step'],minimum=i['minimum_quantity'],
            min_notional=i['minimum_notional'],maximum=maximum))
    target=first_target_within_rounding(rows,tolerance)
    geometry=basket_geometry(rows,target);legs=[];gross=fees=spread=margin=D(0)
    for leg,i in zip(geometry,instruments):
        book=captures['book:'+leg['symbol']]['body']['result']
        bids,asks=_levels(book['b'],True),_levels(book['a'],False);q=D(leg['quantity'])
        entry=bids if leg['side']=='Sell' else asks
        vwap,notional=_vwap(entry,q)
        _,exit_n=_vwap(asks if leg['side']=='Sell' else bids,q)
        remaining=q
        for price,available in entry:
            remaining-=min(remaining,available)
            if remaining==0:break
        gross+=notional;fees+=(notional+exit_n)*D(i['taker_fee'])
        spread+=abs(notional-exit_n);margin+=notional/D(i['configured_leverage'])
        legs.append(dict(leg,entry_book_notional=str(notional),entry_book_vwap=str(vwap),
            draft_entry=dict(category='linear',symbol=leg['symbol'],side=leg['side'],orderType='Limit',
                timeInForce='IOC',qty=leg['quantity'],price=str(price),positionIdx=0,reduceOnly=False)))
    return dict(profile='VENUE_FLOOR_DIAGNOSTIC',selection='MINIMUM_APPROVED_ROUNDING_FRONTIER',
        common_reference_target=str(target),observed_depth_gross=str(gross),legs=legs,
        constant_price_roundtrip_fees=str(fees),constant_price_spread=str(spread),
        approximate_initial_margin_at_unchanged_configured_leverage=str(margin))


def attach_native_guards(profile,instruments,loss_threshold,funding_reserve):
    """Supplement the portfolio monitor with attached Full market SLs.

    Allocate the same remaining $15 budget proportionally to planned notional;
    round each stop toward entry. These are execution-only fallback proposals,
    sealed in the exact GO plan, never changes to KITY's research seven-day rule.
    """
    budget=loss_threshold-D(profile['constant_price_roundtrip_fees'])-funding_reserve
    gross=sum((D(l['draft_entry']['qty'])*D(l['draft_entry']['price']) for l in profile['legs']),D(0))
    if budget<=0 or budget>=gross:raise SourceError('NATIVE_GUARD_BUDGET_NOT_FEASIBLE')
    distance=budget/gross
    for leg,i in zip(profile['legs'],instruments):
        req=leg['draft_entry'];price=D(req['price']);tick=D(i['tick_size'])
        buy=req['side']=='Buy'
        stop=price*(1-distance if buy else 1+distance)
        stop=(stop/tick).to_integral_value(rounding=ROUND_CEILING if buy else ROUND_FLOOR)*tick
        if stop<=0 or (stop>=price if buy else stop<=price):raise SourceError('NATIVE_GUARD_TICK_NOT_FEASIBLE')
        req.update(stopLoss=str(stop),slTriggerBy='LastPrice',slOrderType='Market',tpslMode='Full')
    profile['native_guard_note']='Proportional remaining $15 budget, tick rounded toward entry; not a final loss guarantee'


def build_preflight(capture_path,expected_sha,bounds):
    capture_path=Path(capture_path);raw=capture_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha:raise SourceError('CAPTURE_PIN_CONFLICT')
    wrapper=json.loads(raw);x=wrapper['response']
    if x.get('schema')!='kity_execution_micro_get_capture_v2':raise SourceError('CAPTURE_VERSION_CONFLICT')
    builder_path=ROOT/BUILDER
    if hashlib.sha256(builder_path.read_bytes()).hexdigest()!=BUILDER_SHA:
        raise SourceError('ORIGINAL_GEOMETRY_SOURCE_DRIFT')
    spec=importlib.util.spec_from_file_location('_pinned_kity_intake_builder',builder_path)
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    builder.CAPTURE_SHA=expected_sha  # explicit new source parameter; frozen file unchanged
    intake=builder.build(capture_path,ROOT/'reports/evidence/kity_bybit_c2_actual_20261015/c2_public_receipt.json')
    intake['profiles']=[bounded_profile(x['captures'],intake['instruments'],D(bounds['max_rounding_shortfall_fraction']))]
    profile=intake['profiles'][0]
    reserve=D(0);end=x['completed_ms']+1800000
    for leg,i in zip(profile['legs'],intake['instruments']):
        interval=int(i['funding_interval_minutes'])*60000;next_ms=int(i['next_funding_ms'])
        if interval<=0 or next_ms<=0:raise SourceError('FUNDING_CALENDAR_UNKNOWN')
        rate=D(i['funding_upper']) if leg['side']=='Buy' else -D(i['funding_lower'])
        if not rate.is_finite() or rate<0:raise SourceError('FUNDING_RATE_LIMIT_UNKNOWN')
        if next_ms<=x['completed_ms']:raise SourceError('FUNDING_NEXT_TIME_STALE')
        count=0 if next_ms>end else (end-next_ms)//interval+1
        reserve+=D(leg['entry_book_notional'])*rate*count
    attach_native_guards(profile,intake['instruments'],D(bounds['max_all_in_loss_usdt']),reserve)
    plan=prepare_micro_plan(intake,bounds)
    connectivity={}
    for name in ('history_connectivity','execution_connectivity','transaction_connectivity'):
        group=x['captures'][name]
        # Replay only the already saved page: never repeat an endpoint query.
        known_empty_null=(name=='transaction_connectivity' and len(group['pages'])==1
            and BybitReadTransport.result(group['pages'][0]).get('list')==[]
            and BybitReadTransport.result(group['pages'][0]).get('nextPageCursor','') is None)
        for cap in group['pages']:BybitReadTransport.result(cap)
        connectivity[name]=dict(authenticated_get_success=True,
            complete=group['complete'] or known_empty_null,
            original_complete=group['complete'],
            source_contract='EMPTY_TRANSACTION_NULL_CURSOR_V1' if known_empty_null else 'STANDARD_CURSOR_V1')
    fees=D(profile['constant_price_roundtrip_fees'])
    gross=D(profile['observed_depth_gross'])
    return dict(schema='kity_micro_real_transport_preflight_v1',
        status='BLOCKED_EXECUTION',orders_allowed=False,owner_money_go=False,
        actual_current_blocker='PHYSICAL_SINGLE_WRITER_INTEGRATION_OR_HANDOFF_NOT_APPLIED',
        expected_capture_sha256=expected_sha,observed_start_ms=x['started_ms'],observed_end_ms=x['completed_ms'],
        source_is_fresh_now=False,source_use='DATED_NO_SEND_PREPARATION_NOT_DISPATCH',
        plan=plan,readiness=assess_micro_readiness(plan,dict(marginMode=intake['configured_margin_mode'])),
        account_trade_permissions_observed=intake['api_trade_permissions_observed'],
        account_key_expires_at=intake['api_expires_at'],account_margin_mode=intake['configured_margin_mode'],
        wallet_total_available_usd=intake['wallet_total_available_usd'],
        all_linear_usdt_positions=intake['all_positions'],all_linear_usdt_open_orders=intake['all_open_orders'],
        current_basket_gross_usdt=str(gross),gross_cap_usdt=bounds['max_gross_usdt'],
        margin_reference_at_actual_configured_leverage=profile['approximate_initial_margin_at_unchanged_configured_leverage'],
        fully_funded_reference_including_fees_and_funding_reserve_usdt=str(gross+fees+reserve),
        exact_exchange_required_margin_not_certified=True,
        constant_price_entry_exit_fees_usdt=str(fees),
        constant_price_spread_usdt=profile['constant_price_spread'],
        funding_30min_observed_limit_scenario_usdt=str(reserve),
        future_funding_bound_guaranteed=False,
        common_clock_at_capture=intake['common_clock_at_capture'],instruments=intake['instruments'],
        exact_orders=[l['request'] for l in plan['legs']],
        native_guard_derivation=profile['native_guard_note'],native_protection_actually_sent=False,
        owner_go_template_for_future_bound_ready_dossier='GO KITY_EXECUTION_MICRO_LIVE <exact executable plan_id>',
        owner_go_template_active=False,
        writer_identity='existing bybot.service PID1648585; handoff not performed',
        authenticated_connectivity=connectivity,services=x['services'],
        broker_writes=0,remote_writes=0,research_evidence_eligible=False,counts_toward_C1_C2_C3=False)
