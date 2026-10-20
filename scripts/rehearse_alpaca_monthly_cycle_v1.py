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


class AccountingMemoryBroker(MemoryBroker):
    """Separate deterministic fee-publication fixture; never any HTTP/socket."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.state.setdefault('activities',[]);self.save()

    def get_account(self):
        return dict(super().get_account(),currency='USD',accrued_fees='0',pending_reg_taf_fees='0')

    def _fill(self,o):
        key='fill-'+o['id']
        if not any(a['id']==key for a in self.state['activities']):
            self.state['activities'].append(dict(id=key,activity_type='FILL',order_id=o['id'],
                symbol=o['symbol'],side=o['side'],qty=o['filled_qty'],price=o['filled_avg_price'],transaction_time=o['filled_at']))

    def _request(self,method,path,payload=None):
        if method=='POST' and payload.get('side')=='buy':
            # Distinct source-receipt and exchange-execution timestamps, as in
            # actual HTTP. Do not make the pre-entry cash anchor simultaneous.
            self.state['clock_ms']+=getattr(self,'execution_latency_ms',1000)
        before=D(self.state['cash']);old=set(self.state['orders'])
        try:return super()._request(method,path,payload)
        finally:
            # Accepted buy response may be lost; its activity still exists.
            for key in set(self.state['orders'])-old:
                o=self.state['orders'][key]
                if o['side']=='buy' and o['status']=='filled':
                    self.state['cash']=str(before-(D(o['filled_qty'])*D(o['filled_avg_price'])).quantize(D('.01'),rounding=ROUND_HALF_UP))
                    self._fill(o);self.save()

    def _sell(self,o,price):
        before=D(self.state['cash']);super()._sell(o,price)
        self.state['cash']=str(before+(D(o['filled_qty'])*D(o['filled_avg_price'])).quantize(D('.01'),rounding=ROUND_HALF_UP))
        self._fill(o)

    def publish_fees(self):
        from collections import defaultdict
        from decimal import ROUND_CEILING
        from zoneinfo import ZoneInfo
        values=defaultdict(lambda:dict(qty=D(0),sells=D(0)))
        for a in self.state['activities']:
            if a['activity_type']!='FILL':continue
            day=datetime.fromisoformat(a['transaction_time'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            values[day]['qty']+=D(a['qty'])
            if a['side']=='sell':values[day]['sells']+=D(a['qty'])*D(a['price'])
        for day,v in values.items():
            close=next(r['close_ms'] for r in self.calendar if r['session']==day)
            for kind,value in (('CAT',v['qty']*D('.000003')),('REG',v['sells']*D('.0000206'))):
                amount=(value/D('.01')).to_integral_value(rounding=ROUND_CEILING)*D('.01')
                key='fee-'+day+'-'+kind
                if amount and not any(a['id']==key for a in self.state['activities']):
                    self.state['activities'].append(dict(id=key,activity_type='FEE',activity_sub_type=kind,
                        date=day,created_at=iso(close+4*3600000),currency='USD',status='executed',net_amount=str(-amount)))
                    self.state['cash']=str(D(self.state['cash'])-amount)
        self.save()

    def cost_get(self,route,params):
        now=self.state['clock_ms'];stamp=lambda s:int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)
        if route=='/v2/clock':body=dict(timestamp=iso(now))
        elif route=='/v2/account':body=self.get_account()
        else:
            assert route=='/v2/account/activities'
            rows=sorted(self.state['activities'],key=lambda a:(a.get('created_at',a.get('transaction_time')),a['id']))
            rows=[a for a in rows if stamp(params['after'])<stamp(a.get('created_at',a.get('transaction_time')))<=stamp(params['until'])]
            if params.get('page_token'):rows=rows[next(i for i,a in enumerate(rows) if a['id']==params['page_token'])+1:]
            body=rows[:params['page_size']]
        return dict(http_status=200,raw=json.dumps(body),started_ms=now+10,received_ms=now+10)


def automatic_fixture_finality(root,m,binding,broker,calendar):
    from research_lab.alpaca_monthly_cost_source_v1 import capture_and_produce_cost_sources
    protocol=dict(schema='ALPACA_PROTOCOL_SOURCE_CONTRACT_V1',account_id=m.account,commission_rate='0',
        owner_attestation={'api_commission_null_is_not_proof':True},
        regulatory_model=dict(cat_nms_executed_share_rate='.000003',sec_sell_value_rate='.0000206',taf_per_share_rate='0',
            rounding='each fee type aggregated daily per account then ceiling to USD0.01; exact fractional executed quantities'),
        fixture_only=True)
    values=dict(protocol=protocol,calendar=calendar,
        assets=[dict(id=s,symbol=s,asset_class='us_equity',exchange='NASDAQ') for s in ops.required_symbols()])
    paths={}
    for name,value in values.items():
        path=root/('automatic-'+name+'.json');publish(path,value);paths[name+'_path']=path
    now=next(r['open_ms'] for r in calendar if r['session']=='2026-11-04')-3600000
    broker.set_clock(now)
    def costs(exits):
        return capture_and_produce_cost_sources(binding,after='2026-10-30T00:00:00Z',now_ms=now+1000,**paths)
    pending=m.tick(binding,now_ms=now+2000,cost_sources=costs,apply=True)
    assert any(i['phase']=='ACCOUNTING' and 'POSTING_PENDING_OR_CONFLICT' in i.get('reason','') for i in pending['issues'])
    broker.publish_fees()
    completed=m.tick(binding,now_ms=now+2000,cost_sources=costs,apply=True)
    assert not completed['issues'] and len(completed['accounting'])==1, completed['issues']
    assert not m.tick(binding,now_ms=now+2000,cost_sources=costs,apply=True)['accounting']
    return completed['accounting'][0]


def fixture_calendar():
    days=[];d=date(2026,10,30)
    while len(days)<200:
        if d.weekday()<5:days.append(d)
        d-=timedelta(days=1)
    days=list(reversed(days));d=date(2026,11,2)
    while d<=date(2026,12,3):
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


def run(directory,*,standing_grant=False,automatic_costs=False):
    if standing_grant and automatic_costs:raise ValueError('AUTOMATIC_REHEARSAL_SINGLE_CYCLE_ONLY')
    root=ops.safe_path(directory);root.mkdir(mode=0o700)  # never reuse/adopt an existing runtime
    calendar=fixture_calendar();bundle,now,prices=fixture_source(root/'source-oct30',calendar,'2026-10-30')
    args=dict(account_id='MONTHLY_REHEARSAL_ONLY',capital='487.42',account_lock_path=root/'fixture-account.lock',
        entry_halt_path=root/'fixture-HALT.json')
    m=MonthlyManager(root/'cycle',**args);bound=m.source(bundle,now_ms=now)
    selection=m.book.rows('selections')[0]
    if not selection['picks']:raise ValueError('REHEARSAL_FIXTURE_MUST_EXERCISE_REAL_SELECTOR_ENTRY')
    symbol=selection['picks'][0]['symbol'];opening=next(r['open_ms'] for r in calendar if r['session']=='2026-11-02')
    broker_type=AccountingMemoryBroker if automatic_costs else MemoryBroker
    broker_path=root/'broker.json';broker=broker_type(broker_path,calendar,standing=standing_grant);broker.mark(prices);broker.set_clock(opening+1000)
    history=load_history(bundle['history']);quotes={symbol:dict(ask=prices[symbol],quote_ts=opening,
        received_ms=opening,source='SYNTHETIC_ORDERS_OFF_FIXTURE')}
    with (standing_mode(root,m,opening) if standing_grant else paper_mode()) as authority:
        for lost in ('buy','stop',None):
            m=MonthlyManager(root/'cycle',**args);broker=broker_type(broker_path,calendar,standing=standing_grant)
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
        if automatic_costs:
            final=automatic_fixture_finality(root,m,native_binding,broker,calendar)
        else:
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
    out=dict(status='MONTHLY_AUTOMATIC_COST_ORDERS_OFF_E2E_PASS' if automatic_costs else 'MONTHLY_STANDING_ORDERS_OFF_REPEAT_PASS' if standing_grant else 'MONTHLY_ORDERS_OFF_END_TO_END_PASS',source_symbols=len(bundle['history']),
        automatic_cost_source=automatic_costs,late_fee_block_proven=automatic_costs,
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


def run_pending_rotation(directory,*,production_entrypoint=False):
    """Frozen58 selector, sell→selected buy before fees post, memory broker only."""
    from research_lab.alpaca_monthly_cost_source_v1 import capture_and_produce_cost_sources
    root=ops.safe_path(directory);root.mkdir(mode=0o700)
    calendar=fixture_calendar();captures=root/'source-captures';captures.mkdir()
    def source_fixture(session,overrides=None):
        row=next(r for r in calendar if r['session']==session)
        folder=captures/str(row['close_ms']+1260000)
        bundle,available,prices=fixture_source(folder,calendar,session,overrides)
        publish(folder/'calendar.json',dict(schema='BROKER_CALENDAR_GET_CAPTURE_V1',method='GET',
            endpoint='/v2/calendar?start=2026-01-01&end=2026-12-03',
            started_ms=row['close_ms']+600000,completed_ms=row['close_ms']+660000,
            fixture_only=True,body=[dict(date=r['session'],open='09:30',close='16:00') for r in calendar]))
        return bundle,available,prices
    bundle,available,prices=source_fixture('2026-10-30')
    args=dict(account_id='MONTHLY_REHEARSAL_ONLY',capital='487.42',
        account_lock_path=root/'fixture-account.lock',entry_halt_path=root/'fixture-HALT')
    m=MonthlyManager(root/'cycle',**args);m.source(bundle,now_ms=available)
    first=m.book.rows('selections')[0];old=first['picks'][0]['symbol']
    opening=next(r['open_ms'] for r in calendar if r['session']=='2026-11-02')
    broker=AccountingMemoryBroker(root/'broker.json',calendar,standing=production_entrypoint)
    broker.mark(prices);broker.set_clock(opening+1000)
    protocol=dict(schema='ALPACA_PROTOCOL_SOURCE_CONTRACT_V1',account_id=m.account,commission_rate='0',
        owner_attestation={'api_commission_null_is_not_proof':True},fixture_only=True,
        regulatory_model=dict(cat_nms_executed_share_rate='.000003',sec_sell_value_rate='.0000206',
            taf_per_share_rate='0',rounding='each fee type aggregated daily per account then ceiling to USD0.01; exact fractional executed quantities'))
    paths={}
    for name,value in dict(protocol=protocol,calendar=calendar,
        assets=[dict(id=s,symbol=s,asset_class='us_equity',exchange='NASDAQ') for s in ops.required_symbols()]).items():
        path=root/(name+'.json');publish(path,value);paths[name+'_path']=path
    elapsed=[0.];context={};original=time.monotonic;original_ns=time.time_ns;cli_calls=[0]
    time.monotonic=lambda:elapsed[0]/1000
    if production_entrypoint:
        # The runner's pre-entry account snapshot is one second after the
        # fixture venue clock. Execution must be later, not simultaneous.
        broker.execution_latency_ms=2000
        broker.clock_started=time.monotonic()
        time.time_ns=lambda:int((context.get('now',broker.state['clock_ms']+1000)
            +elapsed[0]-context.get('start',elapsed[0]))*1000000)
        original_cost_get=broker.cost_get
        def cost_get(route,params):
            current=context['now']+elapsed[0]-context['start']
            elapsed[0]+=max(0,broker.state['clock_ms']+1000-current)
            return original_cost_get(route,params)
        broker.cost_get=cost_get
    try:
        with (standing_mode(root,m,opening) if production_entrypoint else paper_mode()) as authority:
            if production_entrypoint:
                from scripts import run_alpaca_monthly_cycle_v1 as cli
                import io,contextlib
                from research_lab.alpaca_monthly_native_binding_v1 import standing_source_pins,PENDING_FEE_POLICY
                nb=root/'fixture-native-binding.json'
                spec=dict(schema=cli.RUNNER_SCHEMA,enabled=True,orders_allowed=True,money_authority=True,
                    files=standing_source_pins(),manager=dict(root=str(m.root),**{k:str(v) for k,v in args.items()}),
                    source_captures=str(captures),broker_root=str(root),
                    profile=dict(path=str(root/'FIXTURE-NO-REAL-PROFILE'),sha256='0'*64),
                    native_binding=dict(path=str(nb),sha256=ops.sha(nb)),
                    native=dict(liability_reserve_usd='.03',pending_fee_admission=True),notifications=None,
                    costs=dict(after='2026-10-30T00:00:00Z',**{n:dict(path=str(p),sha256=ops.sha(p))
                        for n,p in ((n,paths[n+'_path']) for n in ('protocol','calendar','assets'))}))
                scope=json.loads(Path(authority['live_scope_path']).read_bytes())
                scope.update(liability_reserve_usd='0.03',pending_fee_admission=PENDING_FEE_POLICY,
                    pending_fee_protocol_sha256=ops.sha(paths['protocol_path']),runner_config_sha256=cli.runner_config_sha256(spec))
                sp=root/'FIXTURE-NOT-AUTHORITY-production-scope.json';publish(sp,scope);go=root/'FIXTURE-NOT-AUTHORITY-production-go.json'
                publish(go,dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=ops.sha(sp),
                    owner_go_text='GO ALPACA_MONTHLY_STANDING '+ops.sha(sp)))
                authority=dict(live_scope_path=sp,live_scope_sha256=ops.sha(sp),owner_go_path=str(go))
                spec['authority']=dict(scope_path=str(sp),scope_sha256=ops.sha(sp),owner_go_path=str(go))
                spec_path=root/'FIXTURE-production-spec.json';publish(spec_path,spec)
                def production_tick():
                    context.update(now=broker.state['clock_ms']+1000,start=elapsed[0]);stream=io.StringIO();cli_calls[0]+=1
                    with contextlib.redirect_stdout(stream):
                        rc=cli.main(['--spec',str(spec_path),'--spec-sha256',ops.sha(spec_path),'--dispatch'],
                            client_factory=lambda _:broker,now_ms=context['now'])
                    out=json.loads(stream.getvalue());assert rc in (0,2),out
                    return out
                broker.lose_buy=True;lost_buy=production_tick()
                assert any(i['code']=='TimeoutError' for i in lost_buy['issues']),lost_buy
                broker.lose_stop=True;lost_stop=production_tick()
                assert any(i['code']=='TimeoutError' for i in lost_stop['issues']),lost_stop
                recovered=production_tick();assert not recovered['issues'],recovered
            binding=m.native(broker,base_url=broker.base_url,liability_reserve_usd='.03',pending_fee_admission=True,**authority)
            if not production_entrypoint:
                m.opening(binding,load_history(bundle['history']),first['selection_id'],
                    quotes={old:dict(ask=prices[old],quote_ts=opening,received_ms=opening,source='FIXTURE')},
                    now_ms=opening+1000,apply=True,symbols=[old])
            held=m.book.rows('positions')[0];entry=held['raw_entry']
            broker.set_clock(next(r['close_ms'] for r in calendar if r['session']=='2026-11-04')+3600000)
            broker.publish_fees()  # The old buy-day penny is posted before next month.
            # Keep this fixture holding flat while other synthetic stocks trend;
            # it then leaves the frozen ranking, without a stop exit or retuning.
            px=float(entry['filled_avg_price'])
            overrides={(old,r['session']):px for r in calendar if '2026-11-02'<=r['session']<='2026-11-30'}
            overrides[(old,'2026-11-30')]=px*.995
            future,available,marks=source_fixture('2026-11-30',overrides)
            for row in calendar:
                if not '2026-11-02'<=row['session']<'2026-11-30':continue
                close=overrides[(old,row['session'])]
                raw=[dict(symbol=old,session=row['session'],open=close*.999,high=close*1.005,low=close*.995,close=close)]
                at=row['close_ms']+1200000
                m.book.observe_close(dict(schema='ALPACA_COMPLETED_SESSION_SOURCE_V1',
                    source='RECORDED_REGULAR_SESSION_OHLC',raw=raw,raw_sha256=digest(raw),
                    calendar=calendar,available_ms=at,completed_ms=at),now_ms=at)
            future_bound=m.source(future,now_ms=available)
            second=next(s for s in m.book.rows('selections') if s['selection_id']==future_bound['selection_id'])
            assert old not in {p['symbol'] for p in second['picks']}
            dec=next(r['open_ms'] for r in calendar if r['session']=='2026-12-01')
            marks[old]=float(entry['filled_avg_price'])*1.001
            broker.mark(marks);broker.set_clock(dec+1000);lost=[False]
            if production_entrypoint:
                request=broker._request;new_symbols={p['symbol'] for p in second['picks']}
                def lose_new_stop(method,path,payload=None):
                    if (method=='POST' and (payload or {}).get('type')=='stop'
                        and payload['symbol'] in new_symbols and not lost[0]):
                        broker.lose_stop=True;lost[0]=True
                    return request(method,path,payload)
                broker._request=lose_new_stop
            quotes={s:dict(ask=px,quote_ts=dec,received_ms=dec,source='FIXTURE') for s,px in marks.items()}
            def costs(exits):
                if not exits:return {}
                if not lost[0]:broker.lose_stop=True;lost[0]=True
                now=broker.state['clock_ms']+1000
                current=context['now']+elapsed[0]-context['start']
                elapsed[0]+=max(0,now-current)
                return capture_and_produce_cost_sources(binding,after='2026-10-30T00:00:00Z',
                    now_ms=now,allow_pending=True,**paths)
            def tick(source=False):
                if production_entrypoint:return production_tick()
                context.update(now=broker.state['clock_ms']+1000,start=elapsed[0])
                return m.tick(binding,now_ms=context['now'],cost_sources=costs,apply=True,
                    source_loader=(lambda:future) if source else None,quotes=quotes)
            first_attempt=tick(True)
            assert any(i['phase']=='OPENING' and i['code']=='TimeoutError' for i in first_attempt['issues']),first_attempt
            m=MonthlyManager(root/'cycle',**args)
            binding=m.native(broker,base_url=broker.base_url,liability_reserve_usd='.03',pending_fee_admission=True,**authority)
            completed=tick(True)
            assert not completed['issues'],completed['issues']
            selected_count=len(second['picks'])
            assert len(m.book.rows('positions'))==selected_count
            exits=m.book.rows('exits');assert len(exits)==1 and exits[0]['reason']=='monthly_rotation_next_open'
            with_pending=False
            try:binding._require_exit_accounting()
            except ValueError as exc:with_pending=str(exc)=='MONTHLY_ACCOUNTING_PENDING'
            assert with_pending
            buys=lambda:len([w for w in broker.state['writes'] if (w['payload'] or {}).get('side')=='buy'])
            assert buys()==1+selected_count
            assert not tick(True)['issues'] and buys()==1+selected_count
            if production_entrypoint:
                source_fixture('2026-12-01',overrides)
                broker.set_clock(next(r['close_ms'] for r in calendar if r['session']=='2026-12-01')+1260000)
                daily=tick();assert not daily['issues'],daily
                source_fixture('2026-12-02',overrides)
            broker.set_clock(next(r['close_ms'] for r in calendar if r['session']=='2026-12-02')+3600000)
            broker.publish_fees();final=tick()
            assert not final['issues'],final['issues']
            binding._require_exit_accounting()
            out=dict(status='MONTHLY_PRODUCTION_ENTRYPOINT_ORDERS_OFF_E2E_PASS' if production_entrypoint
                else 'MONTHLY_PENDING_FEE_ROTATION_ORDERS_OFF_E2E_PASS',source_symbols=58,
                selector_monkeypatched=False,rotation_exits=1,simulated_entries=buys(),owned_positions=selected_count,
                response_loss_recovered=True,old_exit_pending_during_new_entries=with_pending,
                old_exit_finalized_after_posting=True,duplicate_entries=0,fixture_liability_reserve_usd='.03',
                fixture_calendar='WEEKDAY_FIXTURE_NOT_OFFICIAL_XNYS_OR_PROSPECTIVE_EVIDENCE',
                real_broker_requests=0,real_broker_writes=0,money_authority=False,orders_allowed=False)
            if production_entrypoint:out.update(production_entrypoint=True,production_cli_calls=cli_calls[0],
                source_loader_injected=False,first_entry_buy_and_stop_response_loss_recovered=True,
                clock='DETERMINISTIC_FIXTURE_NOT_LATENCY_SLO')
            publish(root/'receipt.json',out);return out
    finally:time.monotonic=original;time.time_ns=original_ns


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',required=True,type=Path)
    p.add_argument('--pending-rotation',action='store_true')
    args=p.parse_args(argv)
    print(json.dumps(run_pending_rotation(args.runtime) if args.pending_rotation else run(args.runtime),sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
