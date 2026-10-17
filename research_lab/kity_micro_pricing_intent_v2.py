"""Transport-free bounded-price compiler for a separately approved micro test.

An intent is a proposal, never an order permit. Literal human GO, one durable
claim, a new actual GET capture and the existing physical writer are required.
The original exact-plan V1 sender and its spent NO_SEND records are unchanged.
"""
import copy
import hashlib
import json
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR
import re

from bot.kity_m3_orders_off import digest, _levels, _vwap
from research_lab.kity_execution_micro_runtime_v1 import BASKET, numeric, validate_plan
from research_lab.kity_execution_micro_v1 import common_source_clock
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_micro_preflight_v1 import attach_native_guards
from research_lab.kity_micro_transport_v1 import SourceError

SCHEMA='KITY_EXECUTION_MICRO_PRICING_INTENT_V2'
SHA=re.compile(r'[0-9a-f]{64}\Z')


def load_source(path,expected_sha,bounds,physical_config_sha256):
    """Use the existing full raw/cursor/account/cost parser, never pass flags alone."""
    from pathlib import Path
    from research_lab.kity_micro_preflight_v1 import build_preflight
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise SourceError('INTENT_CAPTURE_PATH')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=_sha(expected_sha):raise SourceError('CAPTURE_PIN_CONFLICT')
    x=json.loads(raw)['response']
    if x.get('physical_config_sha256')!=_sha(physical_config_sha256):raise SourceError('INTENT_CAPTURE_CONFIG_CONFLICT')
    d=build_preflight(path,expected_sha,bounds)
    d['physical_config_sha256']=physical_config_sha256
    d['materialization_capture_path']=str(path.absolute())
    return d,x['captures']


def _sha(value):
    if not isinstance(value,str) or not SHA.fullmatch(value):raise SourceError('INTENT_SOURCE_PIN')
    return value


def _clock(value):
    if type(value) is not int or value<=0:raise SourceError('INTENT_CLOCK')
    return value


def _window(intent,at):
    _clock(at)
    if not intent['created_ms']<=at<intent['expires_ms']:raise SourceError('INTENT_CLOCK_EXPIRED_OR_FUTURE')


def _bands(plan,instruments,bps):
    if [(i['symbol'],i['side']) for i in instruments]!=list(BASKET):raise SourceError('INTENT_INSTRUMENT_IDENTITY')
    out=[]
    for leg,i in zip(plan['legs'],instruments):
        price=numeric(leg['request']['price']);tick=numeric(i['tick_size'])
        if price%tick:raise SourceError('INTENT_REFERENCE_TICK')
        low=(price*(1-bps/10000)/tick).to_integral_value(rounding=ROUND_CEILING)*tick
        high=(price*(1+bps/10000)/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        if low<=0 or low>price or high<price:raise SourceError('INTENT_PRICE_BAND_EMPTY')
        out.append(dict(symbol=leg['symbol'],side=leg['side'],quantity=leg['quantity'],
            tick_size=str(tick),min_price=str(low),max_price=str(high)))
    # Reference sizing must fit the cap even at every band's high end. This is
    # a preparation bound; exchange improvement/slippage is not a guarantee.
    if sum((numeric(r['quantity'])*numeric(r['max_price']) for r in out),D(0))>D(plan['bounds']['max_gross_usdt']):
        raise SourceError('INTENT_WORST_REFERENCE_GROSS_EXCEEDS_'+plan['bounds']['max_gross_usdt'])
    return out


def make_intent(dossier,*,at_ms,collar_bps,ttl_ms,predecessor_plan_id):
    p=copy.deepcopy(dossier['plan']);validate_plan(p)
    if p['bounds']['schema'] not in ('kity_execution_micro_owner_bounds_v3','kity_execution_micro_owner_bounds_v4') or p['blocked_reasons']:
        raise SourceError('INTENT_REFERENCE_PLAN_BLOCKED')
    _clock(at_ms)
    if not 0<=at_ms-p['reference_source_ms']<=2000:raise SourceError('INTENT_REFERENCE_SOURCE_STALE')
    bps=numeric(collar_bps)
    if bps>50 or type(ttl_ms) is not int or not 0<ttl_ms<=600000:raise SourceError('INTENT_PROPOSAL_BOUND')
    instruments=copy.deepcopy(dossier['instruments'])
    # Only the tick identity is needed from the proposal. Execution costs and
    # funding are obtained again from the actual fresh materialization capture.
    instruments=[{k:r[k] for k in ('symbol','side','tick_size')} for r in instruments]
    x=dict(schema=SCHEMA,purpose='EXECUTION_MICRO_LIVE',created_ms=at_ms,
        expires_ms=at_ms+ttl_ms,ttl_ms=ttl_ms,collar_bps=str(bps),
        predecessor_plan_id=_sha(predecessor_plan_id),
        physical_config_sha256=_sha(dossier['physical_config_sha256']),
        reference_plan=p,reference_instruments=instruments,
        price_bands=_bands(p,instruments,bps),orders_allowed=False,
        research_evidence_eligible=False,counts_toward_C1_C2_C3=False)
    x['intent_id']=digest(x)
    return x


def validate_intent(intent):
    if not isinstance(intent,dict):raise SourceError('INTENT_SCHEMA')
    try:
        d=dict(plan=intent['reference_plan'],instruments=intent['reference_instruments'],
            physical_config_sha256=intent['physical_config_sha256'])
        expected=make_intent(d,at_ms=intent['created_ms'],collar_bps=intent['collar_bps'],
            ttl_ms=intent['ttl_ms'],predecessor_plan_id=intent['predecessor_plan_id'])
        if intent!=expected:raise SourceError('INTENT_PIN_OR_BAND_CONFLICT')
    except (KeyError,TypeError) as exc:raise SourceError('INTENT_SCHEMA') from exc
    return intent


def materialize(intent,fresh,captures,*,now_ms):
    """One immutable plan at outer legal IOC prices, fixed original quantities.

    Input must come from the existing build_preflight capture/hash validator.
    This pure calculation adds no transport, permit, account adoption or retry.
    All existing fresh checks still run again immediately before each real POST.
    """
    validate_intent(intent);_window(intent,now_ms)
    fresh=copy.deepcopy(fresh);p=fresh['plan'];validate_plan(p)
    if (p['bounds']!=intent['reference_plan']['bounds'] or p['blocked_reasons']
        or fresh.get('physical_config_sha256')!=intent['physical_config_sha256']):
        raise SourceError('INTENT_FRESH_CUSTODY_OR_BOUNDS_CONFLICT')
    if (any(type(fresh.get(k)) is not int or fresh[k]!=0 for k in
            ('all_linear_usdt_positions','all_linear_usdt_open_orders'))
        or fresh.get('account_trade_permissions_observed') is not True):raise SourceError('INTENT_ACCOUNT_NOT_FLAT_OR_PERMISSION_UNKNOWN')
    if (fresh.get('common_clock_at_capture',{}).get('status')!='OBSERVED_COMMON_2S_PASS'
        or type(fresh.get('observed_end_ms')) is not int
        or not 0<=now_ms-fresh['observed_end_ms']<=2000):raise SourceError('INTENT_FRESH_SOURCE_CLOCK')
    instruments=fresh['instruments']
    if [(i['symbol'],i['side']) for i in instruments]!=list(BASKET):raise SourceError('INTENT_INSTRUMENT_IDENTITY')
    books=[captures['book:'+s] for s,_ in BASKET]
    if common_source_clock(books,now_ms)['status']!='OBSERVED_COMMON_2S_PASS':raise SourceError('INTENT_COMMON_2S_SOURCE_UNKNOWN')
    profile=dict(legs=[],constant_price_roundtrip_fees='0')
    gross=fees=spread=margin=reserve=D(0)
    for ref,band,i in zip(intent['reference_plan']['legs'],intent['price_bands'],instruments):
        s,side=ref['symbol'],ref['side'];q=numeric(ref['quantity']);tick=numeric(i['tick_size'])
        if tick!=numeric(band['tick_size']):raise SourceError('INTENT_INSTRUMENT_TICK_CHANGED')
        book=captures['book:'+s]['body']['result']
        if book.get('s')!=s:raise SourceError('INTENT_BOOK_IDENTITY')
        bid,ask=_levels(book['b'],True),_levels(book['a'],False)
        levels=ask if side=='Buy' else bid
        vwap,notional=_vwap(levels,q);_,exit_n=_vwap(bid if side=='Buy' else ask,q)
        remaining=q;consumed=[]
        for price,available in levels:
            if remaining<=0:break
            consumed.append(price);remaining-=min(remaining,available)
        low,high=numeric(band['min_price']),numeric(band['max_price'])
        if any(price<low or price>high for price in consumed):raise SourceError('INTENT_PRICE_ENVELOPE_EXCEEDED:'+s)
        price=high if side=='Buy' else low
        rows=captures['instrument:'+s]['body']['result']['list']
        if len(rows)!=1 or rows[0]['symbol']!=s:raise SourceError('INTENT_INSTRUMENT_IDENTITY')
        lot=rows[0]['lotSizeFilter']
        if (q<numeric(lot['minOrderQty']) or q>numeric(lot['maxOrderQty']) or q%numeric(lot['qtyStep'])
            or q*price<numeric(lot['minNotionalValue'])):raise SourceError('INTENT_FIXED_QUANTITY_NOT_EXECUTABLE')
        rate=numeric(i['taker_fee'],zero=True)
        # Conservative entry-fee reserve at high end, actual current full exit
        # depth; future cash and final loss remain explicitly unguaranteed.
        fees+=(q*high+exit_n)*rate;gross+=notional;spread+=abs(notional-exit_n)
        margin+=q*high/numeric(i['configured_leverage'])
        next_ms=_clock(int(i['next_funding_ms']));period=int(i['funding_interval_minutes'])*60000
        if period<=0 or next_ms<=now_ms:raise SourceError('INTENT_FUNDING_CALENDAR_UNKNOWN')
        upper=numeric(i['funding_upper'] if side=='Buy' else str(-D(i['funding_lower'])),zero=True)
        end=now_ms+p['bounds']['duration_ms'];count=0 if next_ms>end else (end-next_ms)//period+1
        reserve+=q*high*upper*count
        req=copy.deepcopy(ref['request']);req.update(price=str(price),qty=str(q))
        profile['legs'].append(dict(draft_entry=req))
    profile['constant_price_roundtrip_fees']=str(fees)
    attach_native_guards(profile,instruments,D('15'),reserve)
    namespace=digest(dict(intent_id=intent['intent_id'],capture=p['captured_source_sha256']))[:12]
    legs=[]
    for n,(ref,l) in enumerate(zip(intent['reference_plan']['legs'],profile['legs'])):
        req=l['draft_entry'];req['orderLinkId']=f'KXM2-{namespace}-E{n:02d}'
        legs.append(dict(symbol=ref['symbol'],side=ref['side'],quantity=ref['quantity'],
            rounding_shortfall_fraction=ref['rounding_shortfall_fraction'],request=req,
            exit_prefix=f'KXM2-{namespace}-X{n:02d}'))
    limit_gross=sum((numeric(l['quantity'])*numeric(l['request']['price']) for l in legs),D(0))
    if max(gross,limit_gross)>D(p['bounds']['max_gross_usdt']):raise SourceError('INTENT_FRESH_GROSS_CAP_EXCEEDED')
    if numeric(fresh['wallet_total_available_usd'],zero=True)<gross+fees+reserve:raise SourceError('INTENT_BALANCE_INSUFFICIENT')
    p.update(legs=legs,reference_gross_usdt=str(gross),planned_limit_gross_usdt=str(limit_gross),
        source_dossier_sha256=digest(fresh),pricing_intent=dict(intent_id=intent['intent_id'],
            expires_ms=intent['expires_ms'],materialized_ms=now_ms,captures_sha256=digest(captures)))
    p['plan_id']=digest({k:v for k,v in p.items() if k!='plan_id'});validate_plan(p)
    fresh.update(plan=p,status='BOUNDED_PLAN_MATERIALIZED_ORDERS_OFF',
        pricing_intent=copy.deepcopy(intent),rounding_basis='FROZEN_INTENT_REFERENCE_ONLY',
        exact_orders=[l['request'] for l in legs],current_basket_gross_usdt=str(gross),
        constant_price_entry_exit_fees_usdt=str(fees),constant_price_spread_usdt=str(spread),
        fully_funded_reference_including_fees_and_funding_reserve_usdt=str(gross+fees+reserve),
        margin_reference_at_actual_configured_leverage=str(margin),
        funding_30min_observed_limit_scenario_usdt=str(reserve),broker_writes=0,orders_allowed=False)
    return fresh


def consume_once(store,intent,owner_go_text,capture,*,clock):
    """Claim before GET, not a sender. Any failure consumes this intent forever."""
    from pathlib import Path
    validate_intent(intent)
    if owner_go_text!='GO KITY_EXECUTION_MICRO_INTENT_V2 '+intent['intent_id']:
        raise SourceError('EXACT_INTENT_GO_REQUIRED')
    at=clock();_window(intent,at);store=Path(store)
    publish(store/'intent-claim.json',dict(intent_id=intent['intent_id'],owner_go_text=owner_go_text,at_ms=at))
    try:
        fresh,captures=capture()
        out=materialize(intent,fresh,captures,now_ms=clock())
        publish(store/'materialized.json',out)
        return out
    except Exception as exc:
        publish(store/'no-send.json',dict(status='BOUNDED_INTENT_NO_SEND',intent_id=intent['intent_id'],
            reason=type(exc).__name__+':'+str(exc)[:512],observed_ms=clock(),broker_writes=0))
        raise
