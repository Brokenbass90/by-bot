"""Bybit raw GET evidence -> inert KITY weekly observations.

No sender, financial owner, credentials or permission minting. A declared
ORDERS_OFF request manifest is not proof of LIVE ownership. Fixture provenance
is retained; ACKs, terminal orders and flatness never prove execution/finality.
"""
from decimal import Decimal as D
from research_lab.pump4_bybit_sources_v1 import checked,paged,number
from research_lab.pump4_account_adapter_v1 import checked_order_ack,time_windows
from research_lab.kity_weekly_rehearsal_v1 import validate
from research_lab.alpaca_dynamic_v1 import digest


def need(ok,why):
    if not ok:raise ValueError('KITY_BYBIT_'+why)


def signed(value):
    need(not isinstance(value,bool) and value not in (None,''),'SIGNED_AMOUNT_UNKNOWN')
    v=D(str(value));need(v.is_finite(),'NONFINITE_AMOUNT');return v


def millis(value):
    need(type(value) is int or (isinstance(value,str) and value.isascii() and value.isdecimal()),'MILLISECOND_SCHEMA')
    value=int(value);need(value>0,'MILLISECOND_SCHEMA');return value


def ack_only(response,request):
    return checked_order_ack(response,request)


def observe(profile,requests,bundle,*,expected_fingerprint,now_ms,native_bindings):
    validate(profile)
    need(bundle['schema']=='KITY_WEEKLY_BYBIT_GET_V1' and bundle['account_fingerprint']==expected_fingerprint,'ACCOUNT_IDENTITY')
    origin=bundle['origin'];need(origin in ('SYNTHETIC_API_FORMAT_FIXTURE','SAVED_READONLY_GET_CAPTURE'),'SOURCE_ORIGIN')
    need(isinstance(expected_fingerprint,str) and len(expected_fingerprint)==64 and set(expected_fingerprint)<=set('0123456789abcdef'),'FINGERPRINT')
    legs={l['symbol']:l for l in profile['legs']};owned={};by_broker={};entry_symbols=set()
    need(isinstance(requests,list) and 0<len(requests)<=100,'REQUEST_BOUND')
    for item in requests:
        req=item['request'];symbol=req['symbol'];role=item['role'];link=req['orderLinkId']
        need(symbol in legs and role in ('ENTRY','EXIT') and isinstance(link,str) and 0<len(link)<=36
             and link not in owned,'REQUEST_IDENTITY')
        side='Buy' if legs[symbol]['side']==1 else 'Sell'
        need(req['category']=='linear' and type(req['positionIdx']) is int and req['positionIdx']==0
             and req['reduceOnly'] is (role=='EXIT') and req['orderType'] in ('Limit','Market')
             and req['side']==(side if role=='ENTRY' else ('Sell' if side=='Buy' else 'Buy')),'REQUEST_MATERIAL')
        q=number(req['qty']);need(q<=number(legs[symbol]['qty']),'REQUEST_EXCEEDS_PLAN')
        tif=req.get('timeInForce','IOC' if req['orderType']=='Market' else 'GTC')
        need(tif in ('GTC','IOC','FOK','PostOnly') and (req['orderType']!='Market' or tif=='IOC'),'REQUEST_TIF')
        if req['orderType']=='Limit':number(req['price'])
        if role=='ENTRY':
            need(symbol not in entry_symbols and q==number(legs[symbol]['qty']),'ENTRY_REQUEST_QUANTITY');entry_symbols.add(symbol)
        oid=item.get('order_id')
        if oid is not None:need(isinstance(oid,str) and oid and oid not in by_broker,'BROKER_ID_COLLISION');by_broker[oid]=link
        owned[link]=item
    need(entry_symbols==set(legs),'WHOLE_BASKET_REQUESTS_REQUIRED')
    start=millis(bundle['history_start_ms']);end=millis(bundle['history_end_ms'])
    need(end<=now_ms and start<=end,'HISTORY_CLOCK')
    need(all(millis(x['first_send_ms'])>=start for x in requests)
         and min(millis(x['first_send_ms']) for x in requests)==start,'HISTORY_ANCHOR')
    groups=bundle['captures']
    positions=paged(groups['positions'],'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),now_ms=now_ms,fingerprint=expected_fingerprint)
    current=paged(groups['orders'],'/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),now_ms=now_ms,fingerprint=expected_fingerprint)
    windows=time_windows(start,end);need(len(windows)==len(bundle['history_windows']),'HISTORY_WINDOWS')
    history=[];fills=[];transactions=[]
    for (a,z),w in zip(windows,bundle['history_windows']):
        need((w['start_ms'],w['end_ms'])==(a,z),'HISTORY_WINDOW_GAP')
        for name,path,limit,extra,target in [('history','/v5/order/history','50',{},history),('executions','/v5/execution/list','100',{},fills),
             ('transactions','/v5/account/transaction-log','50',dict(accountType='UNIFIED',currency='USDT'),transactions)]:
            params=dict(category='linear',startTime=str(a),endTime=str(z),limit=limit,**extra)
            target.extend(paged(w['groups'][name],path,params,now_ms=now_ms,fingerprint=expected_fingerprint))
    native={}
    for row in native_bindings:
        oid=row['order_id'];symbol=row['symbol']
        need(symbol in legs and isinstance(oid,str) and oid and oid not in native and oid not in by_broker
             and row['profile_sha256']==digest(profile) and row['contract']=='CONTINGENCY_FIXTURE_ONLY','NATIVE_BINDING')
        number(row['trigger_price']);native[oid]=row
    normalized_orders={};native_rows={};resolved_cids={};resolved_brokers=dict(by_broker)
    def bind_ids(link,oid):
        need(link not in resolved_cids or resolved_cids[link]==oid,'CID_MULTIPLE_BROKER_ORDERS')
        need(oid not in resolved_brokers or resolved_brokers[oid]==link,'BROKER_ID_MULTIPLE_CIDS')
        need(oid not in native,'BROKER_NATIVE_COLLISION')
        resolved_cids[link]=oid;resolved_brokers[oid]=link
    for row in history+current:
        oid=row['orderId'];link=row.get('orderLinkId','');symbol=row['symbol']
        need(isinstance(oid,str) and oid and symbol in legs,'FOREIGN_ORDER')
        if link not in owned:
            need(oid in native,'UNBOUND_NATIVE_OR_FOREIGN_ORDER');binding=native[oid]
            need(binding['symbol']==symbol and row.get('stopOrderType')=='StopLoss' and row['reduceOnly'] is True
                 and row.get('closeOnTrigger') is True and type(row['positionIdx']) is int and row['positionIdx']==0
                 and row['side']==('Sell' if legs[symbol]['side']==1 else 'Buy') and row.get('triggerBy')=='LastPrice'
                 and row.get('orderType')=='Market' and number(row['triggerPrice'])==number(binding['trigger_price']),'NATIVE_MATERIAL')
            need(oid not in native_rows or native_rows[oid]==row,'CHANGED_NATIVE_STATE_REQUIRES_RECONCILIATION')
            native_rows[oid]=row;continue
        item=owned[link];req=item['request']
        bind_ids(link,oid)
        need(item.get('order_id') in (None,oid) and by_broker.get(oid,link)==link,'ORDER_ID_DRIFT')
        need(all(row[k]==req[k] for k in ('symbol','side','reduceOnly','positionIdx','orderType'))
             and type(row['positionIdx']) is int and number(row['qty'])==number(req['qty']),'ORDER_MATERIAL')
        need(row['timeInForce']==req.get('timeInForce','IOC' if req['orderType']=='Market' else 'GTC'),'ORDER_TIF_DRIFT')
        if req['orderType']=='Limit':need(number(row['price'])==number(req['price']),'ORDER_LIMIT_PRICE_DRIFT')
        cumulative=number(row['cumExecQty'],zero=True);quantity=number(req['qty']);status=row['orderStatus']
        need(status in {'New','Created','PartiallyFilled','Filled','Cancelled','Rejected','Deactivated','PartiallyFilledCanceled','Untriggered','Triggered'},'ORDER_STATUS')
        need(0<=cumulative<=quantity and (status!='Filled' or cumulative==quantity)
             and (status not in {'New','Created','Rejected','Untriggered'} or cumulative==0)
             and (status!='PartiallyFilled' or 0<cumulative<quantity),'ORDER_CUMULATIVE_STATUS')
        stamp=millis(row['updatedTime']);need(start<=stamp<=end,'ORDER_CLOCK')
        old=normalized_orders.get(link)
        if old:
            need(old['orderId']==oid and number(row['cumExecQty'],zero=True)>=number(old['cumExecQty'],zero=True)
                 and stamp>=millis(old['updatedTime']),'ORDER_STATE_REGRESSION')
            if old['orderStatus'] in ('Filled','Cancelled','Rejected','Deactivated','PartiallyFilledCanceled'):
                need(row['orderStatus']==old['orderStatus'],'TERMINAL_ORDER_REOPENED')
        normalized_orders[link]=row
    unique={};executions=[];entry={s:D(0) for s in legs};exited=dict(entry);per_order={};timeline={s:[] for s in legs}
    for row in fills:
        xid=row['execId'];need(isinstance(xid,str) and xid,'EXECUTION_ID')
        if xid in unique:need(unique[xid]==row,'CONFLICTING_EXECUTION');continue
        unique[xid]=row;symbol=row['symbol'];link=row.get('orderLinkId','');oid=row['orderId']
        need(symbol in legs and (link in owned or oid in native),'FOREIGN_EXECUTION')
        if link in owned:
            item=owned[link];req=item['request'];role=item['role']
            bind_ids(link,oid)
            need(symbol==req['symbol'] and oid not in native and item.get('order_id') in (None,oid)
                 and by_broker.get(oid,link)==link and row['side']==req['side'],'EXECUTION_MATERIAL')
            need(link not in normalized_orders or normalized_orders[link]['orderId']==oid,'EXECUTION_ORDER_CONFLICT')
            first_send=millis(item['first_send_ms'])
        else:
            binding=native[oid];need(binding['symbol']==symbol and row['side']==('Sell' if legs[symbol]['side']==1 else 'Buy'),'NATIVE_EXECUTION_SIDE')
            role='NATIVE_STOP_EXIT';first_send=start
        stamp=millis(row['execTime']);need(row['execType']=='Trade' and max(start,first_send)<=stamp<=end,'EXECUTION_TIME_OR_TYPE')
        qty=number(row['execQty']);price=number(row['execPrice']);fee=None
        if row.get('execFee') not in (None,''):
            need(row.get('feeCurrency')=='USDT','FEE_CURRENCY');fee=signed(row['execFee'])
        bucket=entry if role=='ENTRY' else exited;bucket[symbol]+=qty
        per_order[oid]=per_order.get(oid,D(0))+qty
        if link in owned:need(per_order[oid]<=number(req['qty']),'EXECUTION_ORDER_OVERFILL')
        need(bucket[symbol]<=number(legs[symbol]['qty']),'EXECUTION_BASKET_OVERFILL')
        timeline[symbol].append((stamp,qty if role=='ENTRY' else -qty))
        executions.append(dict(exec_id=xid,order_id=oid,order_link_id=link,symbol=symbol,role=role,
              qty=str(qty),price=str(price),fee_usdt=None if fee is None else str(fee),executed_ms=stamp,source_row_sha256=digest(row)))
    for row in normalized_orders.values():
        need(number(row['cumExecQty'],zero=True)==per_order.get(row['orderId'],D(0)),'ORDER_EXECUTION_CUMULATIVE_CONFLICT')
    for s in legs:
        need(entry[s]>=exited[s],'EXIT_EXCEEDS_ENTRY')
        running=D(0)
        for _,delta in sorted(timeline[s],key=lambda x:(x[0],-x[1])):
            running+=delta;need(0<=running<=number(legs[s]['qty']),'EXECUTION_TIMELINE_CONFLICT')
    pos={}
    for row in positions:
        q=number(row['size'],zero=True);s=row['symbol']
        if not q:continue
        need(s in legs and s not in pos and type(row['positionIdx']) is int and row['positionIdx']==0
             and row['side']==('Buy' if legs[s]['side']==1 else 'Sell'),'FOREIGN_POSITION_OR_MODE')
        pos[s]=row
    for s in legs:need(entry[s]-exited[s]==(number(pos[s]['size']) if s in pos else D(0)),'POSITION_EXECUTION_RECONCILIATION')
    protection={}
    for s in legs:
        rows=[v for v in native_rows.values() if v['symbol']==s and v['orderStatus'] in ('New','Untriggered')]
        need(len(rows)<=1,'AMBIGUOUS_NATIVE_STOP')
        q=entry[s]-exited[s]
        protection[s]=bool(q and len(rows)==1 and number(rows[0]['qty'],zero=True)==q and
             number(pos[s].get('stopLoss','0'),zero=True)==number(rows[0]['triggerPrice']))
    settlements={};funding=[]
    for row in transactions:
        if row.get('type')!='SETTLEMENT':continue
        s=row['symbol'];need(s in legs and row.get('category')=='linear' and row.get('currency')=='USDT','FOREIGN_FUNDING')
        tid=row['id'];need(isinstance(tid,str) and tid,'FUNDING_ID')
        if tid in settlements:need(settlements[tid]==row,'CONFLICTING_FUNDING');continue
        settlements[tid]=row;stamp=millis(row['transactionTime']);need(start<=stamp<=end,'FUNDING_CLOCK')
        amount=signed(row['funding']);fee=signed(row['fee']);cashflow=signed(row['cashFlow'])
        need(signed(row['change'])==cashflow+amount-fee,'FUNDING_CASH_IDENTITY')
        q=number(row['qty']);mark=number(row['tradePrice']);rate=signed(row['feeRate'])
        need(row['side']==('Buy' if legs[s]['side']==1 else 'Sell') and amount==-q*mark*rate
             and q==sum((v for t,v in timeline[s] if t<=stamp),D(0)),'FUNDING_POSITION_OR_SIGN')
        funding.append(dict(id=tid,symbol=s,settlement_ms=stamp,qty=str(q),mark=str(mark),
              market_rate=str(rate*legs[s]['side']),cash_usdt=str(amount),source_row_sha256=digest(row)))
    return dict(schema='KITY_WEEKLY_BYBIT_OBSERVATION_V1',source_origin=origin,observed_ms=now_ms,
         profile_sha256=digest(profile),capture_sha256=digest(bundle),positions=sorted(pos.values(),key=lambda x:x['symbol']),
         orders=list(normalized_orders.values()),executions=sorted(executions,key=lambda x:(x['executed_ms'],x['exec_id'])),
         funding=sorted(funding,key=lambda x:(x['settlement_ms'],x['id'])),technical_native_coverage=protection,
         protection_status='UNKNOWN_UNAPPROVED_STOP_POLICY',costs_complete=False,real_cost_finality_proven=False,
         entry_ready=False,orders_allowed=False,money_authority=False,broker_writes=0,
         ownership_basis='DECLARED_ORDERS_OFF_MANIFEST_NOT_LIVE_ADOPTION',account_limits_status='NOT_EVALUATED',
         funding_coverage_status='SOURCE_ROWS_ONLY_NOT_COMPLETE_SCHEDULE')
