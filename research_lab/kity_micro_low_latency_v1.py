"""Bounded reusable GET connections. No cached sources, redirects or retries.

The existing authenticated reader still constructs/signs every request and
retains actual timestamps/bytes. The order writer is deliberately unchanged.
"""
import http.client
import queue
import ssl
import threading
import time
import concurrent.futures as cf
from contextlib import contextmanager
from decimal import Decimal
from urllib.parse import urlsplit

from bot.kity_m3_orders_off import digest
from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
from research_lab.kity_micro_transport_v1 import ALLOW, SourceError


class ReusableGetWire:
    def __init__(self,*,connection_factory=None,clock=time.monotonic,sleep=time.sleep):
        self.factory=connection_factory or http.client.HTTPSConnection
        self.clock=clock; self.sleep=sleep; self.context=ssl.create_default_context()
        self.pool=queue.LifoQueue(maxsize=10)
        for _ in range(10):self.pool.put(None)
        self.lock=threading.Lock()
        self.stats=dict(requests=0,new_connections=0,reused_connections=0,errors=0,rate_wait_ms=0)
        self.next_request={}

    def metrics(self):
        with self.lock:return dict(self.stats)

    def __call__(self,method,url,headers,data,timeout):
        u=urlsplit(url)
        if (method!='GET' or data is not None or u.scheme!='https'
                or u.hostname!='api.bybit.com' or u.port not in (None,443)
                or u.username is not None or u.password is not None
                or u.fragment or u.path not in ALLOW):
            raise SourceError('GET_ONLY_PINNED_ORIGIN_SCOPE')
        # Official limits: fee-rate5/s and account instruments10/s. Reserve
        # below those limits BEFORE sending, not retry after retCode10006.
        # No response/price is cached; every request retains its actual clock.
        spacing={'/v5/account/fee-rate':.25,'/v5/account/instruments-info':.125}.get(u.path,.025)
        with self.lock:
            at=max(self.clock(),self.next_request.get('*',0),self.next_request.get(u.path,0))
            wait=at-self.clock()
            if wait>5:raise SourceError('GET_RATE_WAIT_BOUND_EXCEEDED')
            self.next_request['*']=at+.025; self.next_request[u.path]=at+spacing
            self.stats['rate_wait_ms']+=max(0,wait)*1000
        if wait>0:self.sleep(wait)
        # Keep the original physical owner's 2s network timeout. No permission
        # to wait longer is acquired by reusing an established TLS connection.
        slot=self.pool.get(timeout=2); connection=None; reusable=False
        try:
            if slot is not None:
                connection,last=slot
                if not 0<=self.clock()-last<2:
                    connection.close(); connection=None
            if connection is None:
                connection=self.factory('api.bybit.com',443,timeout=2,context=self.context)
                with self.lock:self.stats['new_connections']+=1
            else:
                with self.lock:self.stats['reused_connections']+=1
            with self.lock:self.stats['requests']+=1
            connection.request('GET',u.path+('?'+u.query if u.query else ''),body=None,headers=headers)
            response=connection.getresponse(); body=response.read(2000001)
            reusable=not response.will_close and len(body)<=2000000
            return response.status,body
        except Exception:
            with self.lock:self.stats['errors']+=1
            raise  # no retry, alternate host, source substitution or zero
        finally:
            if connection is not None and not reusable:connection.close()
            self.pool.put((connection,self.clock()) if reusable else None)


class ParallelPages:
    """One method-local set of real GET groups, never synthesized empty pages."""
    def __init__(self,reader,tasks):
        self.reader=reader;self.groups={}
        tasks={digest(dict(path=p,params=v)):(p,v) for p,v in tasks}
        with cf.ThreadPoolExecutor(max_workers=10) as pool:
            jobs={pool.submit(reader.pages,p,v):key for key,(p,v) in tasks.items()}
            for job in cf.as_completed(jobs):self.groups[jobs[job]]=job.result()

    def pages(self,path,params):
        key=digest(dict(path=path,params=params))
        return self.groups[key] if key in self.groups else self.reader.pages(path,params)


class ParallelPreflightGets:
    """One entry-validation call only; retain every original raw capture/clock."""
    def __init__(self,reader,symbol,include_eligibility):
        self.reader=reader
        tasks=[('/v5/user/query-api',{}),('/v5/account/info',{}),
            ('/v5/account/wallet-balance',dict(accountType='UNIFIED'))]
        tasks.extend((p,dict(category='linear',symbol=symbol)) for p in (
            '/v5/market/instruments-info','/v5/position/list',
            '/v5/account/fee-rate','/v5/market/tickers'))
        if include_eligibility:tasks.append(('/v5/account/instruments-info',dict(category='linear',symbol=symbol)))
        self.captures={}
        with cf.ThreadPoolExecutor(max_workers=10) as pool:
            jobs={pool.submit(reader.get,p,v):digest(dict(path=p,params=v)) for p,v in tasks}
            for job in cf.as_completed(jobs):self.captures[jobs[job]]=job.result()

    def get(self,path,params):
        key=digest(dict(path=path,params=params))
        return self.captures[key] if key in self.captures else self.reader.get(path,params)

    def result(self,cap):return self.reader.result(cap)


class ParallelReadBridge(MicroAccountBridge):
    @contextmanager
    def views(self,tasks):
        original=self.reader
        self.reader=ParallelPages(original,tasks)
        try:yield
        finally:self.reader=original

    def _bind_native_protection(self):
        state=self.journal.snapshot();tasks=[]
        for leg in self.journal.plan['legs']:
            symbol=leg['symbol'];entry=state['entries'].get(symbol)
            if (not entry or Decimal(state['held'][symbol])<=0
                    or Decimal(entry['protected'])==Decimal(state['held'][symbol])
                    or (state['entry_blocked'] and entry['stop_id'] is not None)
                    or not leg['request'].get('stopLoss') or not entry['terminal']
                    or Decimal(entry['terminal_quantity'])!=Decimal(entry['filled'])):continue
            params=dict(category='linear',symbol=symbol,limit='50')
            tasks.extend((('/v5/order/realtime',params),
                ('/v5/order/history',dict(params,startTime=str(state['first_send_ms'])))))
        if not tasks:return super()._bind_native_protection()
        with self.views(tasks):return super()._bind_native_protection()

    def reconcile_positions(self):
        tasks=[('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200')),
            ('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))]
        with self.views(tasks):return super().reconcile_positions()


def cycle_delay(before,after):
    if after and after['phase']=='ENTERING' and not after['entry_blocked']:
        def progress(s):
            return tuple(sorted((k,v['filled'],v['protected'],v['terminal'])
                for k,v in (s or {}).get('entries',{}).items()))
        return .01 if progress(before)!=progress(after) else .25
    return 1


class CycleSources:
    """Overlap independent owned readbacks and risk metadata in one cycle.

    Positions and executable books are NEVER prefetched here. Their original
    fresh queries still run after fills/protection have been reconciled.
    """
    all_symbol_fee_snapshot=True
    def __init__(self,reader,state):
        self.reader=reader;self.captures={};self.groups={};tasks=[]
        for order in list(state['entries'].values())+list(state['exits'].values()):
            unknown=any(f['order_id']==order['order_id'] and f['fee_usdt'] is None for f in state['fills'].values())
            if order['terminal'] and Decimal(order['terminal_quantity'])==Decimal(order['filled']) and not unknown:continue
            identity={'orderId':order['order_id']} if order.get('is_native_protection') else {'orderLinkId':order['link']}
            p=dict(category='linear',symbol=order['symbol'],**identity)
            tasks.extend(('pages',path,dict(p,limit=limit)) for path,limit in (
                ('/v5/order/realtime','50'),('/v5/order/history','50'),('/v5/execution/list','100')))
        tasks.append(('get','/v5/account/fee-rate',dict(category='linear')))
        for s in state['entries']:
            tasks.extend(('get',path,dict(category='linear',symbol=s)) for path in (
                '/v5/market/tickers','/v5/market/instruments-info'))
        with cf.ThreadPoolExecutor(max_workers=10) as pool:
            jobs={pool.submit(getattr(reader,kind),path,p):(kind,digest(dict(path=path,params=p)))
                for kind,path,p in tasks}
            for job in cf.as_completed(jobs):
                kind,key=jobs[job]
                (self.groups if kind=='pages' else self.captures)[key]=job.result()
    def get(self,path,params):
        key=digest(dict(path=path,params=params))
        return self.captures[key] if key in self.captures else self.reader.get(path,params)
    def pages(self,path,params):
        key=digest(dict(path=path,params=params))
        return self.groups[key] if key in self.groups else self.reader.pages(path,params)
    def result(self,cap):return self.reader.result(cap)


def cycle_with_sources(supervisor,run,*,view_type=None):
    from research_lab.kity_micro_supervisor_v1 import now_ms
    if not supervisor.journal or not supervisor.owner:return run()
    supervisor.journal.actions(now_ms())  # persist deadline BEFORE network, as before
    state=supervisor.journal.snapshot()
    if state['phase']!='ENTERING' or state['entry_blocked']:return run()
    original=supervisor.reader;owner_reader=supervisor.owner.reader;bridge_reader=supervisor.bridge.reader
    view=(view_type or CycleSources)(original,state)
    supervisor.reader=view;supervisor.owner.reader=view;supervisor.bridge.reader=view
    try:return run()
    finally:
        supervisor.reader=original;supervisor.owner.reader=owner_reader;supervisor.bridge.reader=bridge_reader
