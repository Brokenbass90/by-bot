#!/usr/bin/env python3
"""Generate explicit Bybit API-format fixtures and replay the existing KITY model.

No network, credentials, broker account or money owner. Every ACK/GET/position/
stop/fill is SYNTHETIC_API_FORMAT_FIXTURE. Does not establish actual Bybit acceptance.
"""
import argparse,hashlib,json,sys,time
from decimal import Decimal as D,ROUND_FLOOR
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.pump4_live_observer_v1 import read_file,safe_path
from research_lab.os2_shadow_journal import strict_json
from research_lab.kity_weekly_rehearsal_v1 import make_profile,WeeklyRehearsal
from research_lab.kity_weekly_bybit_adapter_v1 import observe,ack_only
from research_lab.pump4_account_adapter_v1 import time_windows
from research_lab.alpaca_dynamic_v1 import digest

FP='f'*64


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile',type=Path,required=True);ap.add_argument('--profile-sha256',required=True)
    ap.add_argument('--signal',type=Path,required=True);ap.add_argument('--root',type=Path,required=True)
    a=ap.parse_args();raw=read_file(a.profile)
    if hashlib.sha256(raw).hexdigest()!=a.profile_sha256:raise ValueError('PROFILE_BYTE_PIN')
    old=strict_json(raw);raw=read_file(a.signal)
    if hashlib.sha256(raw).hexdigest()!=old['source_pins']['signal']:raise ValueError('SIGNAL_PIN')
    signal=strict_json(raw);legs=[];rounding=[]
    for x in old['legs']:
        meta=signal['instrumenty'][x['symbol']];step=D(str(meta['step']));original=D(x['qty'])
        if not step.is_finite() or step<=0:raise ValueError('STEP')
        q=(original/step).to_integral_value(rounding=ROUND_FLOOR)*step
        if q<=0 or q<D(str(meta['min_qty'])) or q*D(x['entry_reference_price'])<D(str(meta['min_notional'])):raise ValueError('DATED_LOT')
        legs.append(dict(x,qty=str(q)))
        if q!=original:rounding.append(dict(symbol=x['symbol'],reference_qty=str(original),floor_qty=str(q),basis='DATED_SAVED_FILTER_NOT_CURRENT_ADMISSION'))
    p=make_profile(old['session'],legs,old['source_pins'],funding_intervals=old['funding_intervals'])
    root=safe_path(a.root)
    if root.exists():raise ValueError('NEW_ROOT_REQUIRED')
    root.mkdir(mode=0o700,parents=True);w=WeeklyRehearsal(root/'model',p)
    requests=[];bindings=[];fills=[];fund=[];order_roles={};seen={};fund_seen=set();snapshots=[];counter=0
    start=p['entry_reference_ms'];due=p['exit_reference_ms'];fee=D('.0006')
    def emit(kind,s,now,**kw):
        nonlocal counter
        counter+=1;w.append(dict(event_id='api-fixture-'+str(counter),kind=kind,symbol=s,observed_ms=now,**kw))
    def request(leg,i,role,t):
        side='Buy' if leg['side']==1 else 'Sell'
        if role=='EXIT':side='Sell' if side=='Buy' else 'Buy'
        req=dict(category='linear',symbol=leg['symbol'],side=side,qty=leg['qty'],orderType='Market',timeInForce='IOC',reduceOnly=role=='EXIT',positionIdx=0,orderLinkId=f'kw-{role.lower()}-{i}')
        item=dict(role=role,request=req,order_id=f'{role}-oid-{i}',first_send_ms=t)
        requests.append(item);order_roles[item['order_id']]=item
        return item
    def trade(item,leg,quantity,stamp,xid,missing_fee=False):
        price=D(leg['entry_reference_price']);q=D(quantity)
        fills.append(dict(orderId=item['order_id'],orderLinkId=item['request']['orderLinkId'],symbol=leg['symbol'],side=item['request']['side'],
            execType='Trade',execId=xid,execTime=str(stamp),execQty=str(q),execPrice=str(price),execFee='' if missing_fee else str(q*price*fee),feeCurrency='USDT'))
    for i,l in enumerate(legs):
        item=request(l,i,'ENTRY',start)
        # First create reply is deliberately lost, not resent. Exact CID GET
        # later resolves it; no POST implementation exists in this program.
        if i:ack_only(dict(retCode=0,result=dict(orderId=item['order_id'],orderLinkId=item['request']['orderLinkId'])),item['request'])
        q=D(l['qty']);step=D(str(signal['instrumenty'][l['symbol']]['step']))
        partial=(q*D('.4')/step).to_integral_value(rounding=ROUND_FLOOR)*step if i==0 else q
        trade(item,l,partial,start+100,'e-'+str(i))
        bindings.append(dict(symbol=l['symbol'],order_id='native-'+str(i),trigger_price=str(D(l['entry_reference_price'])*(D('.9') if l['side']==1 else D('1.1'))),profile_sha256=digest(p),contract='CONTINGENCY_FIXTURE_ONLY'))
    emit('UNKNOWN_ENTRY_ACK',legs[0]['symbol'],start)
    def capture(endpoint,params,rows,now,next_cursor=''):
        b=dict(retCode=0,retMsg='OK',result=dict(list=rows,nextPageCursor=next_cursor),time=now);raw=json.dumps(b,sort_keys=True)
        return dict(method='GET',endpoint=endpoint,params=params,signed=True,account_fingerprint=FP,http_status=200,request_ms=now-10,receive_ms=now,
                    raw=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),body=b)
    def pages(path,params,rows,now):
        limit=int(params['limit']);chunks=[rows[i:i+limit] for i in range(0,len(rows),limit)] or [[]]
        return dict(complete=True,pages=[capture(path,dict(params,**({'cursor':f'c{i}'} if i else {})),chunk,now,f'c{i+1}' if i+1<len(chunks) else '') for i,chunk in enumerate(chunks)])
    def snapshot(label,now):
        held={l['symbol']:D(0) for l in legs};history=[];current=[];positions=[]
        for f in fills:held[f['symbol']]+=D(f['execQty'])*(1 if order_roles[f['orderId']]['role']=='ENTRY' else -1)
        for item in requests:
            own=[f for f in fills if f['orderId']==item['order_id']];q=sum((D(f['execQty']) for f in own),D(0));req=item['request']
            row=dict(req,orderId=item['order_id'],cumExecQty=str(q),orderStatus='Filled' if q==D(req['qty']) else 'PartiallyFilled',
                     createdTime=str(item['first_send_ms']),updatedTime=str(max((int(f['execTime']) for f in own),default=item['first_send_ms'])))
            history.append(row)
            if row['orderStatus']!='Filled':current.append(row)
        for l,b in zip(legs,bindings):
            q=held[l['symbol']]
            if not q:continue
            positions.append(dict(symbol=l['symbol'],positionIdx=0,side='Buy' if l['side']==1 else 'Sell',size=str(q),stopLoss=b['trigger_price']))
            current.append(dict(orderId=b['order_id'],orderLinkId='',symbol=l['symbol'],side='Sell' if l['side']==1 else 'Buy',qty=str(q),reduceOnly=True,
                closeOnTrigger=True,positionIdx=0,triggerBy='LastPrice',triggerPrice=b['trigger_price'],orderType='Market',stopOrderType='StopLoss',orderStatus='Untriggered'))
        caps=dict(positions=pages('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),positions,now),
                  orders=pages('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),current,now))
        windows=[]
        for lo,hi in time_windows(start,now):
            groups={}
            for name,path,limit,extra,rows,clockfield in [('history','/v5/order/history','50',{},history,'createdTime'),
                  ('executions','/v5/execution/list','100',{},fills,'execTime'),
                  ('transactions','/v5/account/transaction-log','50',dict(accountType='UNIFIED',currency='USDT'),fund,'transactionTime')]:
                params=dict(category='linear',startTime=str(lo),endTime=str(hi),limit=limit,**extra)
                groups[name]=pages(path,params,[x for x in rows if lo<=int(x[clockfield])<=hi],now)
            windows.append(dict(start_ms=lo,end_ms=hi,groups=groups))
        bundle=dict(schema='KITY_WEEKLY_BYBIT_GET_V1',origin='SYNTHETIC_API_FORMAT_FIXTURE',account_fingerprint=FP,history_start_ms=start,
                    history_end_ms=now,captures=caps,history_windows=windows)
        declared=[dict(item,order_id=None) if label=='entry-partial' and i==0 else item for i,item in enumerate(requests)]
        result=observe(p,declared,bundle,expected_fingerprint=FP,now_ms=now,native_bindings=bindings)
        (root/(label+'-request-manifest.json')).write_text(json.dumps(declared,sort_keys=True)+'\n')
        (root/(label+'-get-fixture.json')).write_text(json.dumps(bundle,sort_keys=True)+'\n')
        snapshots.append(dict(label=label,capture_sha256=digest(bundle),observation_sha256=digest(result),observed_ms=now,origin=result['source_origin'],
                              executions=len(result['executions']),positions=len(result['positions']),technical_native_full=None if not any(held.values()) else all(result['technical_native_coverage'][l['symbol']] for l in legs if held[l['symbol']]),
                              entry_ready=result['entry_ready'],costs_complete=result['costs_complete']))
        if label=='entry-partial':emit('ACK_RECONCILED',legs[0]['symbol'],now)
        for x in result['executions']:
            key=x['exec_id']
            if key in seen:
                if seen[key]['fee_usdt'] is None and x['fee_usdt'] is not None:
                    emit('MODEL_FEE',x['symbol'],now,exec_id=key,fee_usdt=x['fee_usdt']);seen[key]=x
                elif seen[key]!=x:raise ValueError('EXECUTION_CHANGED_AFTER_CAPTURE')
                continue
            emit('MODEL_ENTRY_FILL' if x['role']=='ENTRY' else 'MODEL_EXIT_FILL',x['symbol'],now,exec_id=key,qty=x['qty'],price=x['price'],
                 fee_usdt=x['fee_usdt'],source_execution_ms=x['executed_ms']);seen[key]=x
        for x in result['funding']:
            if x['id'] in fund_seen:continue
            emit('MODEL_FUNDING',x['symbol'],now,settlement_id=x['id'],settlement_ms=x['settlement_ms'],qty=x['qty'],mark=x['mark'],rate=x['market_rate'],cash_usdt=x['cash_usdt']);fund_seen.add(x['id'])
        for l,b in zip(legs,bindings):
            if held[l['symbol']]:emit('PROTECTION',l['symbol'],now,qty=str(held[l['symbol']]),stop_price=b['trigger_price'],status='ACCEPTED',contract='CONTINGENCY_FIXTURE_ONLY')
            else:emit('PROTECTION',l['symbol'],now,qty='0',status='CANCELLED',contract='CONTINGENCY_FIXTURE_ONLY')
        return w.state()
    stages={};stages['partial']=snapshot('entry-partial',start+1000);w=WeeklyRehearsal(root/'model',p)
    first=legs[0];remaining=D(first['qty'])-D(fills[0]['execQty']);trade(requests[0],first,remaining,start+1500,'e-rest')
    stages['entry']=snapshot('entry-complete',start+2000)
    for l in legs:
        interval=p['funding_intervals'][l['symbol']]*60000
        for stamp in range((start//interval+1)*interval,due+1,interval):
            q=D(l['qty']);mark=D(l['entry_reference_price']);side='Buy' if l['side']==1 else 'Sell';r=D('.0001')*l['side'];cash=-q*mark*r
            fund.append(dict(id=l['symbol']+'-'+str(stamp),symbol=l['symbol'],side=side,type='SETTLEMENT',category='linear',currency='USDT',
                    transactionTime=str(stamp),funding=str(cash),fee='0',cashFlow='0',change=str(cash),qty=str(q),tradePrice=str(mark),feeRate=str(r)))
    stages['hold']=snapshot('seven-day-hold',due+500)
    for i,l in enumerate(legs):trade(request(l,i,'EXIT',due+1000),l,l['qty'],due+1000,'x-'+str(i),missing_fee=i==0)
    stages['flat_pending_fee']=snapshot('weekly-exit',due+2000)
    assert not stages['flat_pending_fee']['model_capital_released']
    for f in fills:
        if f['execId']=='x-0':f['execFee']=str(D(f['execQty'])*D(f['execPrice'])*fee)
    stages['costs']=snapshot('late-fee',due+3000)
    emit('MODEL_COST_FINALITY','ALL',due+3001,fees_complete=True,funding_complete=True)
    final=w.state();before=w.events.path.read_bytes();reopened=WeeklyRehearsal(root/'model',p).state()
    if not final['terminal_complete'] or final!=reopened or before!=w.events.path.read_bytes():raise ValueError('E2E_MODEL_NOT_TERMINAL')
    (root/'requests-fixture.json').write_text(json.dumps(requests,sort_keys=True)+'\n')
    (root/'native-bindings-fixture.json').write_text(json.dumps(bindings,sort_keys=True)+'\n')
    result=dict(schema='KITY_BYBIT_API_FORMAT_E2E_V1',status='ORDERS_OFF_API_FORMAT_REHEARSAL_PASS',observed_ms=time.time_ns()//1000000,
         origin='SYNTHETIC_API_FORMAT_FIXTURE',raw_snapshots=snapshots,model_stages=stages,final=final,event_count=len(w.events.read()),
         source_profile_byte_sha256=a.profile_sha256,source_signal_sha256=old['source_pins']['signal'],rounding=rounding,
         output_root=str(root),restart_replay_equal=True,broker_requests=0,broker_writes=0,actual_exchange_acceptance_proven=False,
         live_entry_ready=False,orders_allowed=False,money_authority=False,stop_policy='CONTINGENCY_FIXTURE_ONLY_NOT_APPROVED',
         account_risk_and_ownership='NOT_ACCEPTED_FOR_TINY')
    print(json.dumps(result,sort_keys=True,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
