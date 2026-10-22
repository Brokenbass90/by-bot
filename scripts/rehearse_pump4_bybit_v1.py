#!/usr/bin/env python3
"""PUMP4 whole-protocol rehearsal, memory-only Bybit, no LIVE switch/profile.

Reuses the actual SignedPostOnce durability/signature/send barrier. Its wire is
always the memory exchange below. This is an acceptance harness, not a production
executor or authenticated account/minimum-size/funding readiness proof.
"""
import argparse
from decimal import Decimal as D
import hashlib,json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.kity_micro_physical_owner_v1 import SignedPostOnce,publish
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.pump4_execution_plan_v1 import build_plan
from strategies.signals import TradeSignal

SCENARIOS=('normal','entry_reply_loss','tp1_reply_loss','partial_entry','partial_tp1',
    'native_stop_race','time_exit','intent_reply_loss','missing_native_stop',
    'unrepresentable_partial','unknown_costs')

class MemoryBybit:
    def __init__(self,path,scenario):
        self.path=Path(path);self.scenario=scenario
        self.state=json.loads(self.path.read_bytes()) if self.path.exists() else dict(
            orders={},executions=[],held='0',stop=None,tp1_filled='0',tp2_filled='0',native_observations=[],calls=0,submitted_links=[])
        self.save()
    def save(self):publish(self.path,self.state,exclusive=False)
    def order(self,cid):return self.state['orders'].get(cid)
    def wire(self,method,url,headers,data,timeout):
        assert method=='POST' and url=='https://api.bybit.com/v5/order/create'
        r=json.loads(data);s=self.state;cid=r['orderLinkId'];assert cid not in s['orders']
        assert r['category']=='linear' and r['positionIdx']==0 and len(cid)<=36
        s['calls']+=1;s['submitted_links'].append(cid);self.save()
        if self.scenario=='intent_reply_loss':raise TimeoutError('fixture before exchange receipt')
        q=D(r['qty']);entry=r['reduceOnly'] is False
        if entry:
            assert r['orderType']=='Market' and r['tpslMode']=='Full' and D(r['stopLoss'])>0
            chunks=[D(4),D(6)] if self.scenario=='partial_entry' else [D(3)] if self.scenario=='unrepresentable_partial' else [q]
        else:
            assert 'stopLoss' not in r and q<=D(s['held'])
            chunks=[D(2)] if self.scenario=='partial_tp1' and cid.endswith('-t10') else [q]
        filled=sum(chunks,D(0));oid='order-'+str(len(s['orders'])+1)
        for i,part in enumerate(chunks):
            s['held']=str(D(s['held'])+(part if entry else -part))
            price=s.get('fixture_entry_price','100') if entry else s.get('fixture_exit_price','97')
            s['executions'].append(dict(execId=oid+'-'+str(i),orderId=oid,orderLinkId=cid,
                execQty=str(part),execPrice=price,execFee=str(part*D(price)*D('.0006'))))
            if entry and self.scenario!='missing_native_stop':
                s['stop']=dict(orderId='native-stop',symbol=r['symbol'],side='Buy' if r['side']=='Sell' else 'Sell',
                    qty=s['held'],triggerPrice=r['stopLoss'],positionIdx=0,stopOrderType='StopLoss',orderStatus='Untriggered')
                s['native_observations'].append(s['held'])
            elif not entry and s['stop']:s['stop']['qty']=s['held']
        if not entry:
            if '-t1' in cid:s['tp1_filled']=str(D(s['tp1_filled'])+filled)
            elif '-t2' in cid:s['tp2_filled']=str(D(s['tp2_filled'])+filled)
        row=dict(request=r,orderId=oid,orderLinkId=cid,cumExecQty=str(filled),
            orderStatus='Filled' if filled==q else 'PartiallyFilledCanceled')
        s['orders'][cid]=row;self.save()
        lost=(self.scenario=='entry_reply_loss' and entry) or (self.scenario=='tp1_reply_loss' and cid.endswith('-t10'))
        if lost:raise TimeoutError('fixture accepted order, reply lost')
        return 200,json.dumps(dict(retCode=0,result=dict(orderId=oid,orderLinkId=cid))).encode()
    def stop_fill(self):
        self.state['executions'].append(dict(execId='stop-fill',orderId='native-stop',orderLinkId='',
            execQty=self.state['held'],execPrice='104',execFee='0.36'))
        self.state['held']='0';self.state['stop']['qty']='0';self.save()


def run(directory,*,scenario='normal'):
    if scenario not in SCENARIOS:raise ValueError('UNKNOWN_REHEARSAL_SCENARIO')
    root=Path(directory).absolute()
    if root.exists() or '..' in root.parts or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError('EXCLUSIVE_REHEARSAL_ROOT_REQUIRED')
    root.mkdir(mode=0o700,parents=True)
    signal=TradeSignal(strategy='pump_fade',symbol='ZROUSDT',side='short',entry=100.,sl=101.,tp=97.9,
        tps=[97.9,95.8,93.],tp_fracs=[.4,.3,.3])
    plan=build_plan(signal,signal_bar_open_ms=3600000,next_open_ms=7200000,next_open=100.)
    exchange=MemoryBybit(root/'memory-exchange.json',scenario);prefix='p4-'+digest(plan)[:20]
    def sender():
        return SignedPostOnce('NONFINANCIAL_FIXTURE_KEY','NONFINANCIAL_FIXTURE_SECRET',root/'send-barriers',wire=exchange.wire)
    def send(cid,request):
        nonlocal exchange
        known=exchange.order(cid)
        if known:
            if known['request']!=request:raise ValueError('REQUEST_IDENTITY_CONFLICT')
            return known
        try:sender().post('/v5/order/create',request)
        except Exception:
            # New object reloads durable exchange evidence; never retry POST.
            exchange=MemoryBybit(exchange.path,scenario)
            known=exchange.order(cid)
            if not known:raise ValueError('UNCERTAIN_DISPATCH_NO_RETRY')
            if known['request']!=request:raise ValueError('REQUEST_IDENTITY_CONFLICT')
        return exchange.order(cid)
    protection=False;reason=None
    try:
        cid=prefix+'-entry';entry=dict(category='linear',symbol=plan['symbol'],side='Sell',orderType='Market',
            qty='10',positionIdx=0,reduceOnly=False,orderLinkId=cid,stopLoss=str(plan['stop']),
            slTriggerBy='LastPrice',tpslMode='Full')
        got=send(cid,entry);again=send(cid,entry);assert got==again
        held=D(exchange.state['held']);stop=exchange.state['stop']
        if not stop or D(stop['qty'])!=held or D(stop['triggerPrice'])!=D(str(plan['stop'])):
            raise ValueError('NATIVE_PROTECTION_UNKNOWN')
        protection=True
        # Fixture qtyStep=1. A non-representable 40/60 partial is never rounded.
        if held*D('.4')!=(held*D('.4')).to_integral_value():raise ValueError('PARTIAL_SPLIT_UNREPRESENTABLE')
        def reduce(role,q,attempt=0):
            cid=prefix+'-'+role+str(attempt)
            request=dict(category='linear',symbol=plan['symbol'],side='Buy',orderType='Market',qty=str(q),
                positionIdx=0,reduceOnly=True,orderLinkId=cid)
            row=send(cid,request)
            assert D(row['cumExecQty'])<=q and D(exchange.state['stop']['qty'])==D(exchange.state['held'])
            if row['orderStatus'] not in ('Filled','PartiallyFilledCanceled'):
                raise ValueError('EXIT_TERMINAL_NOT_CONFIRMED')
            return D(row['cumExecQty'])
        if scenario=='time_exit':reduce('time',held)
        else:
            target=held*D('.4');filled=reduce('t1',target)
            if filled<target:
                # Only after actual terminal IOC cancellation, new CID for remainder.
                reduce('t1',target-filled,1)
            if scenario=='native_stop_race':exchange.stop_fill()
            remaining=D(exchange.state['held'])
            if remaining:reduce('t2',remaining)
        if scenario=='unknown_costs':raise ValueError('ACTUAL_COSTS_UNKNOWN')
    except ValueError as exc:reason=str(exc)
    s=exchange.state
    fees=sum((D(e['execFee']) for e in s['executions']),D(0))
    result=dict(schema='PUMP4_BYBIT_WHOLE_PROTOCOL_REHEARSAL_V1',
        status='BLOCKED' if reason else 'PROTOCOL_ORDERS_OFF_REHEARSAL_PASS',reason=reason,scenario=scenario,
        remaining_qty=s['held'],tp1_filled=s['tp1_filled'],tp2_filled=s['tp2_filled'],
        native_protection_verified=protection,partial_entry_protection_sizes=s['native_observations'],
        simulated_create_calls=s['calls'],duplicate_order_links=len(s['submitted_links'])-len(set(s['submitted_links'])),fee_fixture_usdt=str(fees),
        funding_fixture_usdt='0.01',actual_cost_source='NOT_VERIFIED',
        instrument_minimums='FIXTURE_QTY_STEP1_ONLY_NOT_REAL_SOURCE',
        production_owner_gateway='NOT_IMPLEMENTED',margin_and_risk_policy='NOT_ACCEPTED',
        real_broker_requests=0,real_broker_writes=0,orders_allowed=False,money_authority=False,tiny_ready=False)
    publish(root/'receipt.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    p.add_argument('--scenario',default='normal',choices=SCENARIOS);a=p.parse_args()
    print(json.dumps(run(a.root,scenario=a.scenario),sort_keys=True))
