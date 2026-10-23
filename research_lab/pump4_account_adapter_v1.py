"""Account-wide GET captures -> owned PUMP4 lifecycle and TINY diagnostics.

No credentials, POST, ownership adoption or financial authority. Fee/funding
observations are retained; complete pagination never establishes final costs
from absent or potentially delayed activities. Exact-stop tick policy remains
fail-closed. Quantization candidates are reported, never silently selected.
"""
from decimal import Decimal as D,ROUND_CEILING,ROUND_FLOOR
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.pump4_bybit_sources_v1 import account_view,checked,paged,number,need,H
from research_lab.pump4_execution_plan_v1 import frozen_sources

DAY=24*H
TERMINAL={'Filled','Cancelled','Rejected','Deactivated','PartiallyFilledCanceled'}


def frozen_plan(plan):
    need(plan['schema']=='PUMP4_V1_REFERENCE_EXECUTION_PLAN_V1'
        and plan['plan_sha256']==digest({k:v for k,v in plan.items() if k!='plan_sha256'})
        and plan['source_pins']==frozen_sources() and plan['fractions']==[.4,.6]
        and plan['hold_bars']==168 and plan['stop_checked_first'] is True
        and plan['orders_allowed'] is False and plan['money_authority'] is False,'FROZEN_PLAN')


def time_windows(start,end):
    need(type(start) is int and type(end) is int and 0<start<=end,'HISTORY_WINDOW')
    result=[]
    while start<=end:
        stop=min(start+7*DAY,end);result.append((start,stop));start=stop+1
    need(len(result)<=4,'HISTORY_RANGE_BOUND');return result


def _unique(rows,key):
    out={};duplicates=0
    for r in rows:
        k=r[key];need(isinstance(k,str) and bool(k),'ROW_IDENTITY')
        need(k not in out or out[k]==r,'CHANGED_DUPLICATE_ROW')
        if k in out:duplicates+=1
        out[k]=r
    return list(out.values()),duplicates


def owned_observation(bundle,plan,requests,*,first_send_ms,expected_fingerprint,now_ms,known_native_ids=()):
    frozen_plan(plan)
    view=account_view(bundle,expected_fingerprint=expected_fingerprint,now_ms=now_ms)
    need(bundle['history_start_ms']==first_send_ms and bundle['history_end_ms']<=now_ms,'OWNED_HISTORY_ANCHOR')
    windows=time_windows(first_send_ms,bundle['history_end_ms']);groups=bundle['history_windows']
    need(len(groups)==len(windows),'COMPLETE_HISTORY_WINDOWS')
    history=[];fills=[];transactions=[]
    for w,(start,end) in zip(groups,windows):
        need(w['start_ms']==start and w['end_ms']==end,'HISTORY_WINDOW_GAP')
        for name,path,limit,extra in [('history','/v5/order/history','50',{}),
            ('executions','/v5/execution/list','100',{}),
            ('transactions','/v5/account/transaction-log','50',dict(accountType='UNIFIED',currency='USDT'))]:
            params=dict(category='linear',startTime=str(start),endTime=str(end),limit=limit,**extra)
            rows=paged(w['groups'][name],path,params,now_ms=now_ms,fingerprint=expected_fingerprint)
            (history if name=='history' else fills if name=='executions' else transactions).extend(rows)
    owned={r['orderLinkId']:r for r in requests};need(len(owned)==len(requests),'OWNED_REQUEST_IDENTITY')
    symbol=plan['symbol'];side='Sell' if plan['side']=='short' else 'Buy';opposite='Buy' if side=='Sell' else 'Sell'
    need(all(r['category']=='linear' and r['symbol']==symbol and r['positionIdx']==0 for r in requests),'OWNED_REQUEST_SCOPE')
    positions=[p for p in view['positions'] if number(p['size'],zero=True)>0]
    held_positions=[p for p in positions if p['symbol']==symbol]
    need(len(held_positions)<=1 and all(p['positionIdx']==0 and p['side']==side for p in held_positions),'OWNED_POSITION_MODE')
    position=held_positions[0] if held_positions else None;held=number(position['size']) if position else D(0)
    current=[r for r in view['orders'] if r['symbol']==symbol];native=[]
    for row in current:
        if row['orderLinkId'] in owned:continue
        need(row.get('stopOrderType')=='StopLoss' and row.get('reduceOnly') is True
            and row.get('closeOnTrigger') is True and row.get('positionIdx')==0
            and row.get('side')==opposite and row.get('triggerBy')=='LastPrice','FOREIGN_SAME_SYMBOL_ORDER')
        native.append(row)
    need(len(native)<=1,'AMBIGUOUS_NATIVE_STOP')
    stop=native[0] if native else None
    if stop and held:
        need(position.get('stopLoss') not in (None,'') and number(position['stopLoss'])==number(stop['triggerPrice'])
            and number(stop['qty'])==held,'NATIVE_POSITION_STOP_CONFLICT')
    # Realtime/history can overlap. Select latest state, reject identity changes
    # and reopened terminal rows. Lifecycle retains normalized monotonic history.
    byid={}
    for r in history+view['orders']:
        if r['symbol']!=symbol or r.get('orderLinkId') not in owned:continue
        key=r['orderId'];old=byid.get(key)
        if old:
            need(all(old[k]==r[k] for k in ('orderId','orderLinkId','symbol','side','qty','positionIdx','reduceOnly')),'ORDER_IDENTITY_CHANGED')
            if int(r['updatedTime'])<int(old['updatedTime']):old,r=r,old
            need(old['orderStatus'] not in TERMINAL or r['orderStatus']==old['orderStatus'],'TERMINAL_ORDER_REOPENED')
            if r['updatedTime']==old['updatedTime']:need(r==old,'CONCURRENT_ORDER_CONFLICT')
        byid[key]=r
    orders=[]
    for r in byid.values():
        req=owned[r['orderLinkId']]
        need(number(r['qty'])==number(req['qty']) and r['side']==req['side']
            and r['positionIdx']==req['positionIdx'] and r['reduceOnly'] is req['reduceOnly'],'ORDER_REQUEST_DRIFT')
        orders.append({k:r[k] for k in ('orderId','orderLinkId','symbol','side','qty','cumExecQty','orderStatus','reduceOnly','positionIdx')})
    need(len({r['orderLinkId'] for r in orders})==len(orders),'CID_MULTIPLE_ORDERS')
    fills,duplicates=_unique(fills,'execId');executions=[];native_ids=set(known_native_ids)
    if stop:native_ids.add(stop['orderId']) # broker row is still independently checked by lifecycle
    for r in fills:
        if r['symbol']!=symbol:continue
        if r.get('orderLinkId') not in owned and r['orderId'] not in native_ids:
            need(False,'FOREIGN_SAME_SYMBOL_EXECUTION')
        need(r['execType']=='Trade' and first_send_ms<=int(r['execTime'])<=bundle['history_end_ms'],'OWNED_EXECUTION_TYPE_OR_TIME')
        number(r['execQty']);number(r['execPrice']);fee=D(r['execFee']);need(fee.is_finite() and r.get('feeCurrency')=='USDT','EXECUTION_FEE_UNKNOWN')
        executions.append({k:r[k] for k in ('execId','orderId','orderLinkId','symbol','side','execQty','execPrice','execFee','feeCurrency')})
    transactions,_=_unique(transactions,'id');funding=[]
    for r in transactions:
        if r.get('symbol')!=symbol or r.get('type')!='SETTLEMENT':continue
        need(r.get('category')=='linear' and r.get('currency')=='USDT'
            and first_send_ms<=int(r['transactionTime'])<=bundle['history_end_ms'],'FUNDING_SCOPE')
        value=D(r['funding']);need(value.is_finite(),'FUNDING_UNKNOWN')
        funding.append(dict(id=r['id'],amount=str(value),currency='USDT'))
    quote=bundle['captures']['quote'];need(quote['params']==dict(category='linear'),'LAST_PRICE_QUERY')
    ticks=checked(quote,'/v5/market/tickers',now_ms=now_ms,private=False)['list']
    need(now_ms-quote['request_ms']<=5000 and now_ms-quote['body']['time']<=5000,'STALE_LAST_PRICE')
    ticker=[t for t in ticks if t['symbol']==symbol];need(len(ticker)==1,'LAST_PRICE_REQUIRED');price=number(ticker[0]['lastPrice'])
    return dict(schema='PUMP4_BYBIT_OBSERVATION_V1',observed_ms=now_ms,
        source_ms=min([view['source_ms'],quote['body']['time'],*[c['body']['time'] for w in groups for g in w['groups'].values() for c in g['pages']]]),
        symbol=symbol,positionIdx=0,position_side=side,held_qty=str(held),price=str(price),
        orders=sorted(orders,key=lambda r:r['orderId']),executions=sorted(executions,key=lambda r:r['execId']),
        native_stop=None if not stop else {k:stop[k] for k in ('orderId','symbol','side','qty','triggerPrice','positionIdx','stopOrderType','orderStatus')},
        funding=sorted(funding,key=lambda r:r['id']),costs_complete=False,pagination_complete=True,
        source_provenance='BOUND_AUTHENTICATED_GET_CAPTURES_NOT_BROKER_SIGNATURE',source_capture_sha256=digest(bundle),
        foreign_positions=[p['symbol'] for p in positions if p['symbol']!=symbol],borrowed_funds=view['borrowed_funds'],
        source_duplicate_execution_rows=duplicates,orders_allowed=False,money_authority=False)


def execution_feasibility(plan,instrument,ticker,fee,account,policy,*,now_ms):
    """Unsigned policy and current limits produce diagnostics, never a permit."""
    out=dict(schema='PUMP4_TINY_FEASIBILITY_DIAGNOSTIC_V1',status='BLOCKED',orders_allowed=False,money_authority=False)
    try:
        frozen_plan(plan)
        need(policy['schema']=='PUMP4_TINY_PROPOSAL_ONLY_V1' and policy['orders_allowed'] is False,'PROPOSAL_ONLY')
        need(plan['symbol']==instrument['symbol']==ticker['symbol']==fee['symbol']
            and instrument['status']=='Trading' and instrument['quoteCoin']=='USDT'
            and instrument['contractType']=='LinearPerpetual','INSTRUMENT_IDENTITY')
        need(account['positions_flat'] is True and account['open_orders_empty'] is True,'FOREIGN_EXPOSURE')
        need(account['borrowed_funds'] is False and account['margin_mode']=='REGULAR_MARGIN','BORROW_OR_MARGIN_UNKNOWN')
        entry,stop=number(plan['entry']),number(plan['stop']);lots=instrument['lotSizeFilter'];step=number(lots['qtyStep']);tick=number(instrument['priceFilter']['tickSize'])
        out.update(reference_stop=str(stop),rounding_candidates_not_selected=dict(floor=str((stop/tick).to_integral_value(rounding=ROUND_FLOOR)*tick),ceil=str((stop/tick).to_integral_value(rounding=ROUND_CEILING)*tick)))
        need(stop%tick==0,'STOP_TICK_UNREPRESENTABLE')
        r=number(policy['risk_usdt']);gross=number(policy['gross_usdt']);allocation=number(policy['allocation_usdt']);reserve=number(policy['reserve_usdt'],zero=True)
        rate=number(fee['takerFeeRate'],zero=True);slippage=number(policy['slippage_bps'],zero=True)/10000
        need(slippage<1 and plan['side'] in ('long','short'),'SLIPPAGE_OR_SIDE')
        price=number(ticker['ask1Price'] if plan['side']=='long' else ticker['bid1Price'])
        need(stop<price if plan['side']=='long' else price<stop,'STOP_WRONG_SIDE_OF_QUOTE')
        adverse_entry=price*(1+slippage if plan['side']=='long' else 1-slippage)
        stop_distance=max(abs(entry-stop),abs(adverse_entry-stop))
        unit=5*step;qty=(min(r/stop_distance,gross/(price*(1+slippage)),allocation/(price*(1+slippage)))/unit).to_integral_value(rounding=ROUND_FLOOR)*unit
        minimum=number(lots['minOrderQty']);need(qty>0 and min(qty*D('.4'),qty*D('.6'))>=minimum
            and qty*price>=number(lots['minNotionalValue']) and qty<=number(lots['maxMktOrderQty']),'CAPACITY_BLOCKED')
        fee_est=qty*price*2*rate;slip_est=qty*price*2*slippage
        need(qty*price+fee_est+slip_est+reserve<=min(number(account['available_balance'],zero=True),allocation),'CASH_RESERVE')
        interval=instrument['fundingInterval'];need(type(interval) is int and interval>0,'FUNDING_INTERVAL')
        due=int(ticker['nextFundingTime']);need(now_ms<due<=now_ms+interval*60000,'FUNDING_NEXT_TIME')
        current=D(ticker['fundingRate']);low=D(instrument['lowerFundingRate']);high=D(instrument['upperFundingRate'])
        need(all(n.is_finite() for n in (current,low,high)) and low<=current<=high,'FUNDING_RATE_UNKNOWN')
        count=(D(plan['hold_bars']*60)/interval).to_integral_value(rounding=ROUND_CEILING)
        out.update(status='FEASIBLE_PROPOSAL_ONLY',native_stop=str(stop),quantity=str(qty),gross_usdt=str(qty*price),
            nominal_stop_risk_usdt=str(qty*stop_distance),reference_stop_risk_usdt=str(qty*abs(entry-stop)),
            adverse_entry_price_scenario=str(adverse_entry),loss_is_guaranteed_bound=False,
            constant_price_roundtrip_fee_usdt=str(fee_est),
            constant_price_slippage_scenario_usdt=str(slip_est),funding_intervals=str(count),
            constant_notional_current_rate_funding_scenario_usdt=str(qty*price*abs(current)*count),
            constant_notional_current_cap_funding_scenario_usdt=str(qty*price*max(abs(low),abs(high))*count),
            funding_is_guaranteed_bound=False,authority_status='NOT_APPROVED',input_identity_sha256=digest(dict(plan=plan,instrument=instrument,ticker=ticker,fee=fee,account=account,policy=policy)))
    except (ValueError,KeyError,TypeError,ArithmeticError) as e:out['blocker']=str(e).removeprefix('PUMP4_SOURCE_')
    return out
