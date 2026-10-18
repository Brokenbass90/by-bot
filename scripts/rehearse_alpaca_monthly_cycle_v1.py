#!/usr/bin/env python3
"""Offline Monthly integration rehearsal. Synthetic prices, no sockets/keys.

This is an execution/operational test, never research, a broker receipt or a
financial owner grant. The frozen source QA and selector are called unchanged.
"""
import argparse
from contextlib import contextmanager
import copy
import csv
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal as D,ROUND_DOWN,ROUND_HALF_UP
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit,parse_qs

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab import alpaca_monthly_source_ops_v1 as ops
from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager,publish
from research_lab.alpaca_monthly_binding_v1 import CONTRACT
from research_lab.alpaca_dynamic_v1 import canonical,digest
from scripts import equities_alpaca_paper_bridge as native
from scripts.run_alpaca_dynamic_v1_orders_off import load_history
from research_lab.alpaca_dynamic_live_runtime_v1 import DynamicLiveClient


def iso(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat().replace('+00:00','Z')


class MemoryBroker(native.AlpacaClient):
    """Only _request below is used; there is no HTTP implementation here."""
    def __init__(self,path,calendar):
        super().__init__(native._PAPER_API_URL,'NON_FINANCIAL_FIXTURE','NON_FINANCIAL_FIXTURE')
        self.path=Path(path);self.calendar=calendar;self.permit=None
        self.lose_buy=False;self.lose_stop=False
        self.state=json.loads(self.path.read_bytes()) if self.path.exists() else dict(
            cash='487.42',orders={},positions={},writes=[],clock_ms=calendar[0]['open_ms'])
        self.save()

    def save(self):native._atomic_write_json(self.path,self.state)
    def permit_write(self,method,path,payload=None):self.permit=(method,path,canonical(payload))
    def set_clock(self,now):
        self.state['clock_ms']=now
        day=iso(now)[:10]
        for o in self.state['orders'].values():
            if o['status']=='new' and o['time_in_force']=='day' and o['submitted_at'][:10]!=day:o['status']='expired'
        self.save()
    def get_asset(self,symbol):return dict(symbol=symbol,status='active',tradable=True,fractionable=True)
    def latest_quote(self,symbol):return dict(ap=str(self.price(symbol)),t=iso(self.state['clock_ms']))
    def price(self,symbol):return D(self.state.get('quotes',{}).get(symbol,'100'))
    def mark(self,prices):self.state['quotes']={k:str(v) for k,v in prices.items()};self.save()
    def _request(self,method,path,payload=None):
        route=urlsplit(path).path;query=parse_qs(urlsplit(path).query);s=self.state
        if method=='GET':
            if route=='/v2/account':
                equity=D(s['cash'])+sum((D(p['qty'])*self.price(sym) for sym,p in s['positions'].items()),D(0))
                return dict(id='MONTHLY_REHEARSAL_ONLY',cash=s['cash'],non_marginable_buying_power=s['cash'],
                    equity=str(equity),trading_blocked=False,account_blocked=False)
            if route=='/v2/clock':return dict(timestamp=iso(s['clock_ms']),is_open=any(
                r['open_ms']<=s['clock_ms']<r['close_ms'] for r in self.calendar))
            if route=='/v2/positions':return [dict(p,current_price=str(self.price(sym)),market_value=str(D(p['qty'])*self.price(sym)))
                for sym,p in s['positions'].items()]
            if route=='/v2/orders:by_client_order_id':
                row=next((o for o in s['orders'].values() if o['client_order_id']==query['client_order_id'][0]),None)
                if row is None:raise native.AlpacaAPIError(404,'fixture absent')
                return copy.deepcopy(row)
            if route=='/v2/orders':return [copy.deepcopy(o) for o in s['orders'].values()
                if query.get('status',['open'])[0]!='open' or o['status'] in {'new','accepted','partially_filled'}]
            return copy.deepcopy(s['orders'][route.rsplit('/',1)[1]])
        permit=self.permit;self.permit=None
        if permit!=(method,path,canonical(payload)):raise ValueError('FIXTURE_EXACT_PERMIT_REQUIRED')
        if method=='POST':
            DynamicLiveClient._monthly_payload(payload)
            if any(o['client_order_id']==payload['client_order_id'] for o in s['orders'].values()):
                raise ValueError('FIXTURE_DUPLICATE_ORDER')
            oid='sim-'+hashlib.sha256(payload['client_order_id'].encode()).hexdigest()[:24]
            o=dict(payload,id=oid,status='new',filled_qty='0',submitted_at=iso(s['clock_ms']))
            if payload['side']=='buy':
                px=self.price(payload['symbol']);qty=(D(payload['notional'])/px).quantize(D('.000000001'),rounding=ROUND_DOWN)
                o.update(qty=str(qty),filled_qty=str(qty),filled_avg_price=str(px),status='filled',filled_at=iso(s['clock_ms']))
                s['cash']=str(D(s['cash'])-qty*px-D('.01'))
                s['positions'][payload['symbol']]=dict(symbol=payload['symbol'],side='long',qty=str(qty),avg_entry_price=str(px))
            elif payload['type']=='market':
                self._sell(o,self.price(payload['symbol']))
            s['orders'][oid]=o;s['writes'].append(dict(method=method,payload=payload));self.save()
            if payload['side']=='buy' and self.lose_buy:self.lose_buy=False;raise TimeoutError('SIMULATED_ACCEPTED_BUY_RESPONSE_LOST')
            if payload['type']=='stop' and self.lose_stop:self.lose_stop=False;raise TimeoutError('SIMULATED_ACCEPTED_STOP_RESPONSE_LOST')
            return copy.deepcopy(o)
        oid=route.rsplit('/',1)[1];o=s['orders'][oid]
        if method=='DELETE':o['status']='canceled'
        elif method=='PATCH':o.update(payload)
        else:raise ValueError('FIXTURE_ROUTE_REFUSED')
        s['writes'].append(dict(method=method,payload=payload));self.save();return copy.deepcopy(o)

    def _sell(self,o,price):
        qty=D(o['qty']);p=self.state['positions'][o['symbol']]
        if qty!=D(p['qty']):raise ValueError('FIXTURE_FULL_EXIT_REQUIRED')
        o.update(status='filled',filled_qty=str(qty),filled_avg_price=str(price),filled_at=iso(self.state['clock_ms']))
        self.state['cash']=str(D(self.state['cash'])+qty*price-D('.01'));del self.state['positions'][o['symbol']]
    def hit_stop(self,order_id):
        o=self.state['orders'][order_id];self._sell(o,D(o['stop_price']));self.save()


def fixture_calendar():
    days=[];d=date(2026,10,30)
    while len(days)<200:
        if d.weekday()<5:days.append(d)
        d-=timedelta(days=1)
    days=list(reversed(days));d=date(2026,11,2)
    while d<=date(2026,12,2):
        if d.weekday()<5:days.append(d)
        d+=timedelta(days=1)
    return ops.normalize_calendar([dict(date=str(d),open='09:30',close='16:00') for d in days])


def fixture_source(root,calendar,session,overrides=None):
    root.mkdir(mode=0o700);target=next(r for r in calendar if r['session']==session);files={};last={}
    for j,symbol in enumerate(ops.required_symbols()):
        p=root/(symbol+'_M5.csv')
        with p.open('w') as f:
            w=csv.writer(f);w.writerow(['ts','o','h','l','c','v'])
            for i,r in enumerate(calendar):
                if r['session']>session:break
                slope=.001 if symbol=='SPY' else .003+(j%5)*.00008
                close=100*math.exp(slope*i)*(1+.002*math.sin(i*.6+j))
                if symbol!='SPY' and r['session'] in {'2026-10-28','2026-10-29','2026-10-30','2026-11-26','2026-11-27','2026-11-30'}:close*=.97
                close=(overrides or {}).get((symbol,r['session']),close);last[symbol]=close
                for stamp in range(r['open_ms']//1000,r['close_ms']//1000,3600):
                    w.writerow([stamp,close*.999,close*1.005,close*.995,close,1000+j])
        files[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    cap=dict(schema=ops.CAPTURE_SCHEMA,files=files,started_ms=target['close_ms']+600000,
        completed_ms=target['close_ms']+660000,fetcher_sha256=ops.SOURCE_PINS['scripts/fetch_equities_yfinance.py'],
        interval='1h',period='2y',prepost=False,auto_adjust=False,returncode=0)
    now=target['close_ms']+1260000;publish(root/'capture.json',cap)
    return ops.compile_source(root,cap,calendar,now_ms=now),now,last


@contextmanager
def paper_mode():
    saved={k:os.environ.get(k) for k in ('ALPACA_INTENDED_PAPER','ALPACA_INTENDED_LIVE')}
    os.environ.update(ALPACA_INTENDED_PAPER='1',ALPACA_INTENDED_LIVE='0')
    try:yield
    finally:
        for k,v in saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


def run(directory):
    root=ops.safe_path(directory);root.mkdir(mode=0o700)  # never reuse/adopt an existing runtime
    calendar=fixture_calendar();bundle,now,prices=fixture_source(root/'source-oct30',calendar,'2026-10-30')
    args=dict(account_id='MONTHLY_REHEARSAL_ONLY',capital='487.42',account_lock_path=root/'fixture-account.lock',
        entry_halt_path=root/'fixture-HALT.json')
    m=MonthlyManager(root/'cycle',**args);bound=m.source(bundle,now_ms=now)
    selection=m.book.rows('selections')[0]
    if not selection['picks']:raise ValueError('REHEARSAL_FIXTURE_MUST_EXERCISE_REAL_SELECTOR_ENTRY')
    symbol=selection['picks'][0]['symbol'];opening=next(r['open_ms'] for r in calendar if r['session']=='2026-11-02')
    broker_path=root/'broker.json';broker=MemoryBroker(broker_path,calendar);broker.mark(prices);broker.set_clock(opening+1000)
    history=load_history(bundle['history']);quotes={symbol:dict(ask=prices[symbol],quote_ts=opening,
        received_ms=opening,source='SYNTHETIC_ORDERS_OFF_FIXTURE')}
    with paper_mode():
        for lost in ('buy','stop',None):
            m=MonthlyManager(root/'cycle',**args);broker=MemoryBroker(broker_path,calendar)
            broker.lose_buy=lost=='buy';broker.lose_stop=lost=='stop'
            native_binding=m.native(broker,base_url=native._PAPER_API_URL)
            try:m.opening(native_binding,history,selection['selection_id'],quotes=quotes,now_ms=opening+1000,apply=True,symbols=[symbol])
            except TimeoutError:
                if lost is None:raise
        held=m.book.rows('positions')[0];entry=held['raw_entry'];initial=held['native_floor']
        assert len([w for w in broker.state['writes'] if (w['payload'] or {}).get('side')=='buy'])==1
        override={(symbol,'2026-11-02'):float(entry['filled_avg_price'])*1.08}
        daily,close_time,marks=fixture_source(root/'source-nov02',calendar,'2026-11-02',override)
        m.source(daily,now_ms=close_time);broker.mark(marks)
        new_open=next(r['open_ms'] for r in calendar if r['session']=='2026-11-03');broker.set_clock(new_open+1000)
        m.maintain(native_binding,now_ms=new_open+1000,apply=True)
        held=m.book.rows('positions')[0];assert held['native_floor']>initial
        assert held['native_stop_id']!=entry['id']
        broker.hit_stop(held['native_stop_id']);m.maintain(native_binding,now_ms=new_open+1000,apply=True)
        exited=m.book.rows('exits')[0];assert not broker.list_positions() and not broker.list_orders(status='open')
        try:native_binding._require_exit_accounting()
        except ValueError:pass
        else:raise AssertionError('EXIT_MUST_WAIT_FOR_ACCOUNTING')
        evidence=root/'simulated-activity.json';publish(evidence,broker.state)
        source_files=[dict(path=str(evidence),sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())]
        orders=[broker.get_order(o['id']) for o in exited['orders']]
        gross=sum((D(o['filled_qty'])*(D(o['filled_avg_price'])-D(entry['filled_avg_price'])) for o in orders),D(0))
        cost=dict(schema='ALPACA_DYNAMIC_BROKER_COST_FINALITY_V1',account_id=args['account_id'],
            intake_sha256=digest(dict(schema=CONTRACT['schema'],entry_id=entry['id'])),
            closure_status='ACCOUNT_DAY_FEES_RECONCILED',exit_orders_sha256=digest(orders),gross_before_fees=str(gross),
            observed_ms=new_open+1000,source_files=source_files,source_manifest_sha256=digest(source_files),
            coverage_end_ms=new_open+1000,commission_usd='.02',regulatory_fees_usd='0',unresolved_liability_usd='0',
            cash_before_entry='487.42',cash_after_exit=str(D(broker.state['cash']).quantize(D('.01'),rounding=ROUND_HALF_UP)),
            other_cash_net_usd='0')
        # Existing finalizer compares the broker's posted (cent) cash, as in LIVE.
        account=broker.get_account
        broker.get_account=lambda:dict(account(),cash=cost['cash_after_exit'])
        cost_path=root/'simulated-cost-finality.json';publish(cost_path,cost)
        final=m.finalize(native_binding,entry['id'],cost_path,now_ms=new_open+1000)
        native_binding._require_exit_accounting()
        future,future_time,_=fixture_source(root/'source-nov30',calendar,'2026-11-30',override)
        next_bound=m.source(future,now_ms=future_time)
        dec_open=next(r['open_ms'] for r in calendar if r['session']=='2026-12-01')
        next_plan=m.book.monthly_actions(next_bound['selection_id'],now_ms=dec_open)
        assert next_plan['status']=='MONTHLY_PLAN_ORDERS_OFF' and next_plan['new_symbols']
    out=dict(status='MONTHLY_ORDERS_OFF_END_TO_END_PASS',source_symbols=len(bundle['history']),
        selector_monkeypatched=False,selected_symbols=[p['symbol'] for p in selection['picks']],
        executed_fixture_subset=[symbol],simulated_entries=1,duplicate_entries=0,full_native_stop=True,
        day_rearm=True,daily_close_ratchet=True,response_loss_recovered=True,restarts=2,broker_flat=True,
        accounting_final=final['status']=='LIVE_TERMINAL_COST_FINALITY',capital_released=True,
        next_month_selection_ready=bool(next_plan['new_symbols']),initial_floor=initial,raised_floor=held['native_floor'],
        source_ids=[bundle['source_id'],daily['source_id'],future['source_id']],
        fixture_calendar='WEEKDAY_FIXTURE_NOT_OFFICIAL_XNYS_OR_PROSPECTIVE_EVIDENCE',
        real_broker_requests=0,real_broker_writes=0,money_authority=False,orders_allowed=False)
    publish(root/'receipt.json',out);return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',required=True,type=Path)
    args=p.parse_args(argv);print(json.dumps(run(args.runtime),sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
