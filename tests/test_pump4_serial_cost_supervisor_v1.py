"""Real isolated owner/lifecycle, fictional exchange only; no live credentials."""
import copy,hashlib,json
from decimal import Decimal as D
from pathlib import Path
import pytest
from research_lab import pump4_serial_accounting_v1 as A
from research_lab.pump4_execution_plan_v1 import HOUR_MS as H
from test_pump4_serial_source_supervisor_v1 import configured,module
from test_pump4_execution_supervisor_v1 import provider
from test_pump4_account_owner_v1 import inputs
from test_pump4_serial_accounting_v1 import sync
from test_pump4_bybit_sources_v1 import NOW


def bind_policy(path,config,scope):
    from research_lab.pump4_selected_runner_v1 import config_sha
    config['serial_orders_off']['cost_release_policy_sha256']=A.COST_RELEASE_POLICY_SHA
    config['serial_orders_off']['valid_until_ms']=NOW+3*H
    scope['valid_until_ms']=NOW+3*H
    scope['runner_config_sha256']=config_sha(config)
    target=Path(config['authority']['path']);target.write_text(json.dumps(scope))
    config['authority']['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    path.write_text(json.dumps(config));return hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_source_cycles_late_cost_restart_and_same_h1_never_duplicates(tmp_path,monkeypatch):
    from research_lab.pump4_selected_runner_v1 import causal_plan
    import test_pump4_supervisor_v1 as fixture_source
    state,path,pin,config,scope,_=configured(tmp_path,monkeypatch)
    pin=bind_policy(path,config,scope)
    first=fixture_source.fixture_candidate(tmp_path/'first')
    with monkeypatch.context() as mm:
        mm.setattr(fixture_source,'NOW',NOW+H)
        second=fixture_source.fixture_candidate(tmp_path/'second')
    # Bootstrap BEFORE the common epoch, then append each newly closed bar.
    # Recreating a bootstrap after epoch must not masquerade as continuity.
    from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
    ev=second['intake'].journal.read();seed=ev[0]['bars']
    continuous=Pump4Intake(tmp_path/'second-continuous.jsonl','ZROUSDT')
    continuous.seed(seed[:-1],available_ms=NOW-H,observed_ms=NOW-H)
    continuous.accept(seed[-1],available_ms=NOW,observed_ms=NOW)
    d=continuous.accept(ev[-1]['bar'],available_ms=NOW+H+1,observed_ms=NOW+H+1)['decision']
    second.update(intake=continuous,decision_id=d['decision_id'])
    chosen=[first];price=['100'];times={};late=[False]
    Base=provider(state,first)
    class Sources(Base):
        def candidate(self):return chosen[0]
        def fixed(self,b):
            q=b['captures']['quote']['body']['result']['list'][0]
            q.update(lastPrice=price[0],bid1Price=price[0],ask1Price=price[0])
            for w in b['history_windows']:
                for p in w['groups']['executions']['pages']:
                    for x in p['body']['result']['list']:x['execTime']=str(times[x['orderLinkId']])
                if late[0]:
                    first_time=min(times.values())
                    w['groups']['transactions']['pages'][0]['body']['result']['list'].append(dict(id='late-funding-first',symbol='ZROUSDT',type='SETTLEMENT',category='linear',currency='USDT',transactionTime=str(first_time+1),funding='-.05'))
            return sync(b)
        def _capture(self,symbol,begin,*,custody):
            b,p=inputs(state[1],now=state[2][0]);return self.fixed(b),p
        def account(self,plan,*,custody):
            b,p=super().account(plan,custody=custody);self.fixed(b)
            begin=plan['entry_bar_open_ms'];b['history_start_ms']=begin
            for w in b['history_windows']:
                w['start_ms']=begin
                for key,group in w['groups'].items():
                    for cap in group['pages']:
                        cap['params']['startTime']=str(begin)
                        rows=cap['body']['result']['list']
                        cap['body']['result']['list']=[r for r in rows if
                            (times[r['orderLinkId']] if key=='history' else
                             int(r['execTime'] if key=='executions' else r['transactionTime']))>=begin]
            return sync(b),p
        def serial_closed_pnl(self,begin,end):
            b,_=self._capture(None,begin,custody=True)
            w=b['history_windows'][0];cap=copy.deepcopy(w['groups']['history']['pages'][0])
            cap['endpoint']='/v5/position/closed-pnl';cap['params']=dict(category='linear',startTime=str(begin),endTime=str(end),limit='100')
            fills=w['groups']['executions']['pages'][0]['body']['result']['list'];out=[];entry=[];number=0
            for order in state[1].state['orders'].values():
                req=order['request'];own=[x for x in fills if x['orderId']==order['orderId']]
                if not req['reduceOnly']:entry=own;number+=1;continue
                qty=sum((D(x['execQty']) for x in own),D(0));eq=sum((D(x['execQty']) for x in entry),D(0))
                assert qty>0 and eq>0
                ev=sum(D(x['execQty'])*D(x['execPrice']) for x in entry)*qty/eq
                xv=sum(D(x['execQty'])*D(x['execPrice']) for x in own)
                of=sum(D(x['execFee']) for x in entry)*qty/eq;cf=sum(D(x['execFee']) for x in own)
                funding=D('.05')*qty/eq if number==1 else D(0)
                out.append(dict(symbol='ZROUSDT',orderId=order['orderId'],side='Buy',qty=str(qty),closedSize=str(qty),cumEntryValue=str(ev),cumExitValue=str(xv),openFee=str(of),closeFee=str(cf),closedPnl=str(ev-xv-of-cf-funding),execType='Trade',createdTime=str(times[req['orderLinkId']]),updatedTime=str(times[req['orderLinkId']])))
            cap['body']['result'].update(category='linear',list=out,nextPageCursor='');cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
            return [dict(start_ms=begin,end_ms=end,group=dict(complete=True,pages=[cap]))]
    def tick():
        return module().run(path,pin,orders_off=True,once=True,source_factory=Sources,clock=lambda:state[2][0])[0]
    def cycle(candidate,number):
        chosen[0]=candidate;plan=causal_plan(**candidate,epoch_started_ms=config['epoch_started_ms'],max_delay_ms=config['entry_max_delay_ms'],now_ms=state[2][0]);results=[]
        for target in ['100',str(plan['targets'][0]-.01),str(plan['targets'][1]-.01),str(plan['targets'][1]-.01)]:
            price[0]=target;r=tick();results.append(r)
            request=r['result'].get('request')
            if request:
                times[request['orderLinkId']]=state[2][0]+1
                state[1].state['fixture_exit_price']=target
                state[1].wire('POST','https://api.bybit.com/v5/order/create',{},json.dumps(request).encode(),1)
                if not request['reduceOnly']:state[1].state['stop']['orderId']='native-stop-'+str(number)
            state[2][0]+=1000
        assert [x['result'].get('role') for x in results[:3]]==['ENTRY','TP1','TP2'],[(r['result'],r['source_accounting']) for r in results]
        assert results[-1]['result']['status']=='FLAT_COSTS_PENDING'
    cycle(first,1)
    duplicate=tick()
    assert duplicate['result']['status']=='ALREADY_SEEN_SIGNAL'
    assert state[1].state['calls']==3
    state[2][0]=NOW+H+2
    cycle(second,2)
    late[0]=True
    final=tick()
    assert final['result']['status']=='ALREADY_SEEN_SIGNAL'
    assert final['source_accounting']['entry_loss_latched'] is False
    assert state[1].state['calls']==6 and D(state[1].state['held'])==0
    rr=module().read_events(Path(scope['root'])/'serial-source/series.jsonl')
    assert [x['kind'] for x in rr]==['RESERVATION','CLOSED_COSTS_PENDING','RESERVATION','CLOSED_COSTS_PENDING']
    assert final['source_accounting']['cost_finality_proven'] is False


def test_read_transport_allows_only_explicit_closed_pnl_get_scope():
    from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError
    calls=[]
    def wire(method,url,headers,data,timeout):
        calls.append((method,url,data));return 200,json.dumps(dict(retCode=0,result=dict(list=[],nextPageCursor=''),time=NOW)).encode()
    r=BybitReadTransport('fictional-key','fictional-secret',wire=wire,clock=lambda:NOW,symbols=('BTCUSDT',))
    out=r.pages('/v5/position/closed-pnl',dict(category='linear',startTime='1',endTime='2',limit='100'))
    assert out['complete'] is True and len(calls)==1 and calls[0][0]=='GET' and calls[0][2] is None
    with pytest.raises(SourceError):r.get('/v5/position/closed-pnl',dict(category='inverse'))
    assert len(calls)==1
