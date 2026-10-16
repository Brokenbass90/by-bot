"""Account GET coalescing keeps real pages and strict per-order identity."""
import copy,json
from decimal import Decimal
import pytest
from bot.kity_m3_orders_off import digest
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError
from research_lab.kity_micro_account_readbacks_v2 import AccountCycleSources,AccountReadBridge


def state():
    return dict(first_send_ms=1000,entries={'BTWUSDT':dict(symbol='BTWUSDT',link='KXM-entry',order_id='entry',terminal=False,filled='0',terminal_quantity=None)},
        exits={'KXM-native':dict(symbol='BTWUSDT',link='KXM-native',order_id='native',is_native_protection=True,terminal=False,filled='0',terminal_quantity=None)},fills={})


class Reader:
    all_symbol_fee_snapshot=True
    def __init__(self):self.calls=[];self.incomplete=False;self.conflict=False;self.category='linear'
    def get(self,path,p):
        self.calls.append(('get',path,p));return dict(endpoint=path,params=p,body=dict(retCode=0,result=dict(list=[])),http_status=200)
    def pages(self,path,p):
        self.calls.append(('pages',path,dict(p)))
        rows=[dict(symbol='BTWUSDT',orderId='entry',orderLinkId='KXM-entry'),
              dict(symbol='BTWUSDT',orderId='native',orderLinkId=''),
              dict(symbol='BTWUSDT',orderId='foreign',orderLinkId='foreign')]
        if self.conflict:rows[0]['symbol']='LTCUSDT'
        return dict(complete=not self.incomplete,pages=[dict(endpoint=path,params=dict(p),method='GET',
            http_status=200,body=dict(retCode=0,result=dict(category=self.category,list=rows,nextPageCursor='')))])
    result=staticmethod(BybitReadTransport.result)


def test_all_owned_order_reads_share_four_complete_actual_account_groups():
    r=Reader();s=state();view=AccountCycleSources(r,s)
    bridge=AccountReadBridge(None,view)
    for path,limit in [('/v5/order/realtime','50'),('/v5/order/history','50'),('/v5/execution/list','100')]:
        for identity,value,expected in [('orderLinkId','KXM-entry','entry'),('orderId','native','native')]:
            params=dict(category='linear',symbol='BTWUSDT',limit=limit,**{identity:value})
            rows=bridge._rows(path,params)
            assert rows and all(row['orderId']==expected for row in rows)
    groups=[(p,v) for k,p,v in r.calls if k=='pages']
    assert len(groups)==4
    assert not any('symbol' in p or 'orderId' in p or 'orderLinkId' in p for _,p in groups)
    assert {p['openOnly'] for path,p in groups if path.endswith('/realtime')}=={'0','1'}
    # Fresh position/custody/discovery reads must still hit their original source.
    q=dict(category='linear',settleCoin='USDT',openOnly='0',limit='50');view.pages('/v5/order/realtime',q)
    assert len([x for x in r.calls if x[0]=='pages'])==5


@pytest.mark.parametrize('mutation',['incomplete','conflict','wrong_category'])
def test_unknown_or_identity_conflict_is_never_normalized_to_empty_or_adopted(mutation):
    r=Reader()
    if mutation=='wrong_category':r.category='inverse'
    else:setattr(r,mutation,True)
    view=AccountCycleSources(r,state());bridge=AccountReadBridge(None,view)
    with pytest.raises(SourceError):bridge._rows('/v5/order/history',dict(category='linear',symbol='BTWUSDT',orderLinkId='KXM-entry',limit='50'))


def test_unknown_order_identity_is_not_covered_by_an_unrelated_account_view():
    r=Reader();view=AccountCycleSources(r,state());before=len(r.calls)
    params=dict(category='linear',symbol='LTCUSDT',orderId='not-owned',limit='50')
    view.pages('/v5/order/history',params)
    assert len(r.calls)==before+1 and r.calls[-1]==('pages','/v5/order/history',params)


def test_actual_raw_pages_are_retained_unchanged_and_no_network_during_selection():
    r=Reader();view=AccountCycleSources(r,state());n=len(r.calls)
    q=dict(category='linear',symbol='BTWUSDT',orderId='native',limit='50')
    a=view.pages('/v5/order/history',q);raw=copy.deepcopy(a['pages']);bridge=AccountReadBridge(None,view)
    assert bridge._rows('/v5/order/history',q)==[dict(symbol='BTWUSDT',orderId='native',orderLinkId='')]
    assert a['pages']==raw and len(r.calls)==n
    assert a['pages'][0]['params']==dict(category='linear',startTime='1000',limit='50')


@pytest.mark.parametrize('window',[60000,70000])
def test_actual_nine_leg_trace_with_exact_authorized_entry_window(tmp_path,monkeypatch,window):
    """Same measured paging/gates: 60s refuses, separately authorized70s works."""
    import collections
    from pathlib import Path
    import test_kity_micro_physical_e2e_v1 as venue
    import test_kity_micro_post_go_owner_v1 as policy_venue
    from research_lab import kity_micro_low_latency_v1 as ll
    from kity_latency_clock import Latency,Executor
    profile=json.loads((Path(__file__).parents[1]/'reports/evidence/kity_closeout_20261016/actual_timing_profile.json').read_bytes())
    class ActualTraceLatency(Latency):
        production_pagination=True
        real_account_instrument_gate=True
        entry_window_ms=window
        def __init__(self):super().__init__();self.index=collections.Counter()
        def bind(self,clock):self.clock=clock;self.go_ms=clock[0];clock[0]+=profile['initial_authorization_ms']
        def network(self,method,path):
            self.calls.append((method,path,self.clock[0]));i=self.index[path];self.index[path]+=1
            if method=='POST':
                self.posts.append(self.clock[0]);values=profile['entry_post_ack_samples_ms']
                self.clock[0]+=values[i] if i<len(values) else max(values)
            else:
                values=profile['get_samples_ms'][path];self.clock[0]+=values[i%len(values)]
        def custody(self):self.clock[0]+=profile['model_custody_call_ms']
        def get_wire(self,wire):
            # Captured request_ms→receive_ms already includes the production
            # pool's pacing and TLS wait. Do not charge that wait a second time.
            # Pacing itself is exercised separately by the real-wire tests.
            return wire
        def entry_complete(self,state):
            assert len(self.posts)==10 and self.protected_ms is not None
            assert all(p<self.go_ms+self.entry_window_ms for p in self.posts)
            self.last_entry_ms=self.posts[-1]-self.go_ms
            self.all_protected_ms=self.protected_ms-self.go_ms
    sim=ActualTraceLatency()
    monkeypatch.setattr(ll.cf,'ThreadPoolExecutor',lambda max_workers:Executor(sim,max_workers))
    monkeypatch.setattr(venue,'MicroAccountBridge',AccountReadBridge)
    class AccountSupervisor(venue.Supervisor):
        def cycle(self):return ll.cycle_with_sources(self,super().cycle,view_type=AccountCycleSources)
    monkeypatch.setattr(venue,'Supervisor',AccountSupervisor)
    if window==60000:
        with pytest.raises(AssertionError,match='POST_GO_DISPATCH_DEADLINE'):
            policy_venue.test_post_go_owner_all_ten_native_restart_deadline_and_final_cash(tmp_path,monkeypatch,latency=sim)
    else:
        policy_venue.test_post_go_owner_all_ten_native_restart_deadline_and_final_cash(tmp_path,monkeypatch,latency=sim)
        assert sim.all_protected_ms<window
    print(json.dumps(dict(mode='ACTUAL_TRACE_DETERMINISTIC_REPLAY_NOT_REAL_FILLS',entry_window_ms=window,
        expected_block=window==60000,last_entry_ms=getattr(sim,'last_entry_ms',None),
        all_protected_ms=getattr(sim,'all_protected_ms',None),initial_ms=profile['initial_authorization_ms'],
        custody_ms=profile['model_custody_call_ms'],permission_gate=True,cursor_tail_pages=True,
        source_profile_sha256=digest(profile),owner_window_changed=window==70000)))


def test_positions_and_executable_books_are_never_cached_across_risk_and_entry():
    r=Reader();view=AccountCycleSources(r,state())
    p=dict(category='linear',symbol='BTWUSDT',limit='50')
    a=view.get('/v5/market/orderbook',p);b=view.get('/v5/market/orderbook',p)
    assert a is not b
    assert len([x for x in r.calls if x[1]=='/v5/market/orderbook'])==2


@pytest.mark.parametrize('change',[dict(method='POST'),dict(endpoint='/v5/position/list'),dict(params=dict(category='inverse'))])
def test_account_pages_must_prove_their_actual_get_origin_and_parameters(change):
    r=Reader();view=AccountCycleSources(r,state());view.account_groups['history']['pages'][0].update(change)
    with pytest.raises(SourceError):AccountReadBridge(None,view)._rows('/v5/order/history',dict(category='linear',symbol='BTWUSDT',orderId='native',limit='50'))
