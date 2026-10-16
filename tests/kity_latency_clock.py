"""Deterministic network scheduler for the actual owner/bridge test fixture.

Only independent GET jobs overlap; POSTs and journal mutation remain serial.
No real network, source credentials, broker or outcome data.
"""
from concurrent.futures import Future
import heapq


class Executor:
    def __init__(self,sim,max_workers):
        self.sim=sim;self.workers=[sim.clock[0]]*max_workers;self.end=sim.clock[0]
    def __enter__(self):return self
    def __exit__(self,*args):self.sim.clock[0]=max(self.end,self.sim.clock[0])
    def submit(self,fn,*args,**kwargs):
        self.sim.clock[0]=heapq.heappop(self.workers);f=Future()
        try:f.set_result(fn(*args,**kwargs))
        except BaseException as exc:f.set_exception(exc)
        self.end=max(self.end,self.sim.clock[0]);heapq.heappush(self.workers,self.sim.clock[0])
        self.sim.clock[0]=self.end
        return f


class Latency:
    def __init__(self,get_ms=300):self.get_ms=get_ms;self.posts=[];self.protected_ms=None;self.calls=[]
    def bind(self,clock):
        self.clock=clock;self.go_ms=clock[0];clock[0]+=9000 # conservative actual initial queue/capture/compile envelope
    def now(self):return self.clock[0]/1000
    def sleep(self,seconds):self.clock[0]+=round(seconds*1000)
    def network(self,method,path):
        self.calls.append((method,path,self.clock[0]))
        if method=='POST':self.posts.append(self.clock[0]);self.clock[0]+=600
        else:self.clock[0]+=self.get_ms
    def custody(self):self.clock[0]+=100
    def get_wire(self,wire):
        from research_lab.kity_micro_low_latency_v1 import ReusableGetWire
        class Connection:
            sock=None
            def __init__(self,*args,**kwargs):pass
            def request(self,method,path,body=None,headers=None):self.req=(method,path,headers)
            def getresponse(self):
                method,path,headers=self.req
                status,raw=wire(method,'https://api.bybit.com'+path,headers,None,2)
                class Response:
                    will_close=False
                    def read(self,n):return raw[:n]
                r=Response();r.status=status;return r
            def close(self):pass
        self.pool=ReusableGetWire(connection_factory=Connection,clock=self.now,sleep=self.sleep)
        return self.pool
    def between_cycles(self,before,after):
        from research_lab.kity_micro_low_latency_v1 import cycle_delay
        if (len(after['entries'])==10 and all(v['terminal'] and v['filled']==v['protected'] for v in after['entries'].values())
                and self.protected_ms is None):self.protected_ms=self.clock[0]
        self.sleep(cycle_delay(before,after))
    def entry_complete(self,state):
        assert len(self.posts)==10 and self.protected_ms is not None
        assert all(p<self.go_ms+60000 for p in self.posts)
