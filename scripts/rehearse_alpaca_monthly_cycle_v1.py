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
import time
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
    def __init__(self,path,calendar,*,standing=False):
        super().__init__(native._PAPER_API_URL,'NON_FINANCIAL_FIXTURE','NON_FINANCIAL_FIXTURE')
        if standing:self.base_url='https://api.alpaca.markets'
        self.standing=standing;self.clock_started=time.monotonic()
        self.order_contract=CONTRACT['schema']
        self.path=Path(path);self.calendar=calendar;self.permit=None
        self.lose_buy=False;self.lose_stop=False
        self.state=json.loads(self.path.read_bytes()) if self.path.exists() else dict(
            cash='487.42',orders={},positions={},writes=[],clock_ms=calendar[0]['open_ms'])
        self.save()

    def save(self):native._atomic_write_json(self.path,self.state)
    def permit_write(self,method,path,payload=None):self.permit=(method,path,canonical(payload))
    def set_clock(self,now):
        self.clock_started=time.monotonic()
        self.state['clock_ms']=now
        day=iso(now)[:10]
        for o in self.state['orders'].values():
            if o['status']=='new' and o['time_in_force']=='day' and o['submitted_at'][:10]!=day:o['status']='expired'
        self.save()
    def get_clock(self):
        now=self.state['clock_ms']+(int((time.monotonic()-self.clock_started)*1000) if self.standing else 0)
        return dict(timestamp=iso(now),is_open=any(r['open_ms']<=now<r['close_ms'] for r in self.calendar))
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
    try:yield {}
    finally:
        for k,v in saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


@contextmanager
def standing_mode(root,manager,now):
    """Fixture-only fake-account grant. Never an actual owner permission."""
    from research_lab import alpaca_monthly_native_binding_v1 as binding
    from research_lab.alpaca_monthly_binding_v1 import strategy_identity
    manager.lock.touch();stat=manager.lock.stat()
    scope=dict(schema=binding.STANDING_SCHEMA,endpoint='https://api.alpaca.markets',
        account_id=manager.account,contract_sha256=digest(CONTRACT),strategy_identity=strategy_identity(),
        capital_usd='487.42',liability_reserve_usd='0',book=str(manager.book.path),
        runtime=str(manager.root/'native'),lock_path=str(manager.lock),entry_halt_path=str(manager.halt),
        legacy_NET_adoption=False,legacy_entry_authority=False,original_lock_identity=[stat.st_dev,stat.st_ino],
        max_new_entries_per_session=1,max_entry_notional_usd='204.7164',max_cumulative_net_loss_usd='20',
        valid_from_ms=now-86400000,valid_until_ms=now+90*86400000,
        revocation_path=str(root/'fixture-revocation.json'),
        universe_sha256=digest(list(binding.monthly_universe())),
        selection_policy='EXISTING_SEALED_FROZEN_MONTHLY_ONLY',
        source_files=[dict(path=str(binding.ROOT/n),sha256=h) for n,h in binding.standing_source_pins().items()])
    path=root/'FIXTURE-NOT-AUTHORITY-standing-scope.json';publish(path,scope);pin=ops.sha(path)
    go=root/'FIXTURE-NOT-AUTHORITY-standing-go.json'
    publish(go,dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=pin,
        owner_go_text='GO ALPACA_MONTHLY_STANDING '+pin))
    live=root/'fixture-native-binding.json'
    publish(live,dict(schema_version=1,endpoint=scope['endpoint'],strategy_id=native._INTENDED_PAPER_STRATEGY_ID,
        account_id=manager.account,enabled=True,capital_usd=487.42,max_positions=4,gross_exposure=.70,maximum_weight=.60))
    values=dict(ALPACA_INTENDED_PAPER='0',ALPACA_INTENDED_LIVE='1',ALPACA_INTENDED_LIVE_BINDING_PATH=str(live),
        ALPACA_INTENDED_LIVE_ACK='INTENDED_LIVE_CANARY',ALPACA_LIVE_ACCOUNT_ROLE='monthly_v38',
        ALPACA_LIVE_CONFIRM='MONTHLY_V38_LIVE',ALPACA_LIVE_MAX_CAPITAL_USD='487.42')
    saved={k:os.environ.get(k) for k in values};os.environ.update(values)
    try:yield dict(live_scope_path=path,live_scope_sha256=pin,owner_go_path=str(go))
    finally:
        for k,v in saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


def run(directory,*,standing_grant=False):
    root=ops.safe_path(directory);root.mkdir(mode=0o700)  # never reuse/adopt an existing runtime
    calendar=fixture_calendar();bundle,now,prices=fixture_source(root/'source-oct30',calendar,'2026-10-30')
    args=dict(account_id='MONTHLY_REHEARSAL_ONLY',capital='487.42',account_lock_path=root/'fixture-account.lock',
        entry_halt_path=root/'fixture-HALT.json')
    m=MonthlyManager(root/'cycle',**args);bound=m.source(bundle,now_ms=now)
    selection=m.book.rows('selections')[0]
    if not selection['picks']:raise ValueError('REHEARSAL_FIXTURE_MUST_EXERCISE_REAL_SELECTOR_ENTRY')
    symbol=selection['picks'][0]['symbol'];opening=next(r['open_ms'] for r in calendar if r['session']=='2026-11-02')
    broker_path=root/'broker.json';broker=MemoryBroker(broker_path,calendar,standing=standing_grant);broker.mark(prices);broker.set_clock(opening+1000)
    history=load_history(bundle['history']);quotes={symbol:dict(ask=prices[symbol],quote_ts=opening,
        received_ms=opening,source='SYNTHETIC_ORDERS_OFF_FIXTURE')}
    with (standing_mode(root,m,opening) if standing_grant else paper_mode()) as authority:
        for lost in ('buy','stop',None):
            m=MonthlyManager(root/'cycle',**args);broker=MemoryBroker(broker_path,calendar,standing=standing_grant)
            broker.lose_buy=lost=='buy';broker.lose_stop=lost=='stop'
            native_binding=m.native(broker,base_url=broker.base_url,**authority)
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
        future,future_time,future_prices=fixture_source(root/'source-nov30',calendar,'2026-11-30',override)
        next_bound=m.source(future,now_ms=future_time)
        dec_open=next(r['open_ms'] for r in calendar if r['session']=='2026-12-01')
        next_plan=m.book.monthly_actions(next_bound['selection_id'],now_ms=dec_open)
        assert next_plan['status']=='MONTHLY_PLAN_ORDERS_OFF' and next_plan['new_symbols']
        if standing_grant:
            broker.get_account=account;cash_before_second=broker.state['cash']
            broker.mark(future_prices);broker.set_clock(dec_open+1000)
            m=MonthlyManager(root/'cycle',**args);native_binding=m.native(broker,base_url=broker.base_url,**authority)
            next_quotes={s:dict(ask=px,quote_ts=dec_open,received_ms=dec_open,source='SYNTHETIC_ORDERS_OFF_FIXTURE')
                         for s,px in future_prices.items()}
            tick=m.tick(native_binding,now_ms=dec_open+1000,source_loader=lambda:future,quotes=next_quotes,apply=True)
            if tick['issues']:raise ValueError('REPEAT_CYCLE_FAILED:'+str(tick['issues']))
            assert len(m.book.rows('positions'))==1
            assert len([w for w in broker.state['writes'] if (w['payload'] or {}).get('side')=='buy'])==2
            held_second=m.book.rows('positions')[0]
            broker.set_clock(dec_open+60000);broker.hit_stop(held_second['native_stop_id'])
            m.tick(native_binding,now_ms=dec_open+60000,apply=True)
            second=next(x for x in m.book.rows('exits') if x['entry_id']==held_second['entry_id'])
            evidence_second=root/'simulated-second-activity.json';publish(evidence_second,broker.state)
            source_second=[dict(path=str(evidence_second),sha256=ops.sha(evidence_second))]
            orders_second=[broker.get_order(o['id']) for o in second['orders']]
            gross_second=sum((D(o['filled_qty'])*(D(o['filled_avg_price'])-D(held_second['raw_entry']['filled_avg_price']))
                              for o in orders_second),D(0))
            finality_second=dict(cost,intake_sha256=digest(dict(schema=CONTRACT['schema'],entry_id=second['entry_id'])),
                exit_orders_sha256=digest(orders_second),gross_before_fees=str(gross_second),
                observed_ms=dec_open+60000,coverage_end_ms=dec_open+60000,source_files=source_second,
                source_manifest_sha256=digest(source_second),cash_before_entry=cash_before_second,
                cash_after_exit=str(D(broker.state['cash']).quantize(D('.01'),rounding=ROUND_HALF_UP)))
            second_path=root/'simulated-second-cost-finality.json';publish(second_path,finality_second)
            broker.get_account=lambda:dict(account(),cash=finality_second['cash_after_exit'])
            reconciled=m.tick(native_binding,now_ms=dec_open+60000,cost_sources={second['entry_id']:second_path},apply=True)
            if reconciled['issues']:raise ValueError('REPEAT_FINALITY_FAILED:'+str(reconciled['issues']))
            native_binding._require_exit_accounting()
            assert not broker.list_positions() and not broker.list_orders(status='open')
    out=dict(status='MONTHLY_STANDING_ORDERS_OFF_REPEAT_PASS' if standing_grant else 'MONTHLY_ORDERS_OFF_END_TO_END_PASS',source_symbols=len(bundle['history']),
        selector_monkeypatched=False,selected_symbols=[p['symbol'] for p in selection['picks']],
        executed_fixture_subset=[symbol],simulated_entries=2 if standing_grant else 1,
        closed_roundtrips=2 if standing_grant else 1,standing_grant_count=1 if standing_grant else 0,
        duplicate_entries=0,full_native_stop=True,
        day_rearm=True,daily_close_ratchet=True,response_loss_recovered=True,restarts=3 if standing_grant else 2,
        broker_flat=not broker.list_positions(),
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
