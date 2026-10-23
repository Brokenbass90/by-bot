"""Fictional account/keys, existing memory wire, never a real credential loader."""
import copy,hashlib,json,os,subprocess,sys
from pathlib import Path
from decimal import Decimal as D
import pytest
from test_pump4_account_adapter_v1 import sizing
from test_pump4_bybit_sources_v1 import account,capture,group,NOW,H
from research_lab.pump4_execution_plan_v1 import build_plan
from research_lab.kity_micro_physical_owner_v1 import AccountLease,publish
from scripts.rehearse_pump4_bybit_v1 import MemoryBybit
from strategies.signals import TradeSignal

KEY='NONFINANCIAL_PUMP4_ACCOUNT_FIXTURE_KEY';SECRET='NONFINANCIAL_PUMP4_ACCOUNT_FIXTURE_SECRET'
FP=hashlib.sha256(KEY.encode()).hexdigest()

def inputs(exchange,*,now=NOW+2,price='100'):
    x=account();x['account_fingerprint']=FP;x.update(started_ms=now-2,completed_ms=now-1,history_start_ms=NOW,history_end_ms=now)
    state=exchange.state;orders=[];fills=[]
    for row in state['orders'].values():
        r=row['request'];orders.append(dict(row,**{k:r[k] for k in ('symbol','side','qty','positionIdx','reduceOnly')},updatedTime=str(NOW+1)))
    for i,row in enumerate(state['executions']):
        req=next((v['request'] for v in state['orders'].values() if v['orderId']==row['orderId']),None)
        fills.append(dict(row,symbol='ZROUSDT',side=req['side'] if req else 'Buy',execType='Trade',execTime=str(NOW+1+i),feeCurrency='USDT'))
    positions=[];open_orders=[r for r in orders if r['orderStatus'] not in {'Filled','PartiallyFilledCanceled'}]
    if D(state['held']):
        positions=[dict(symbol='ZROUSDT',size=state['held'],positionIdx=0,side='Sell',stopLoss='104')]
        stop=dict(state['stop'],reduceOnly=True,closeOnTrigger=True,triggerBy='LastPrice',orderLinkId='',updatedTime=str(NOW+1),cumExecQty='0')
        open_orders.append(stop)
    x['captures']['positions']=group('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),positions)
    x['captures']['symbol_position']=capture('/v5/position/list',dict(category='linear',symbol='ZROUSDT'),dict(category='linear',list=positions or [dict(symbol='ZROUSDT',size='0',positionIdx=0,side='')],nextPageCursor=''),private=True)
    x['captures']['orders']=group('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),open_orders)
    p,i,t,fee,a,policy=sizing();i.update(upperFundingRate='.00001',lowerFundingRate='-.00001',fundingInterval=480)
    t.update(lastPrice=price,bid1Price=price,ask1Price=price,fundingRate='0',nextFundingTime=str(now+H))
    quote=capture('/v5/market/tickers',dict(category='linear'),dict(category='linear',list=[t]))
    x['captures']['quote']=quote
    x['history_windows']=[dict(start_ms=NOW,end_ms=now,groups=dict(
        history=group('/v5/order/history',dict(category='linear',startTime=str(NOW),endTime=str(now),limit='50'),orders),
        executions=group('/v5/execution/list',dict(category='linear',startTime=str(NOW),endTime=str(now),limit='100'),fills),
        transactions=group('/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',startTime=str(NOW),endTime=str(now),limit='50'),[])))]
    public=dict(instruments=dict(complete=True,pages=[capture('/v5/market/instruments-info',dict(category='linear',limit=1000),dict(category='linear',list=[i],nextPageCursor=''))]),quote=quote)
    for v in [*x['captures'].values(),*[g for w in x['history_windows'] for g in w['groups'].values()],public['instruments']]:
        for c in v.get('pages',[v]):
            c.update(request_ms=now-2,receive_ms=now-1);c['body']['time']=now-2
            if c['signed']:c['account_fingerprint']=FP
            c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()
    return x,public

def create(tmp_path,*,mode='OWNER_TINY_LIVE',authorize=True,wire_kind='normal',policy_override=None):
    from research_lab.pump4_account_owner_v1 import Pump4AccountOwner
    root=tmp_path/'account';root.mkdir();lock=tmp_path/'global-existing-account.lock';lock.touch();lease=AccountLease(lock)
    scope=dict(schema='PUMP4_ACCOUNT_OWNER_SCOPE_V1',mode=mode,account_fingerprint=FP,root=str(root),account_lock_path=str(lock),account_lock_inode=lock.stat().st_ino,
        valid_from_ms=NOW,valid_until_ms=NOW+H,policy=dict(allocation_usdt='50',gross_usdt='30',reserve_usdt='20',risk_usdt='1',slippage_bps='10',day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',max_entries=1,max_positions=1))
    scope['policy'].update(policy_override or {})
    exchange=MemoryBybit(tmp_path/'memory.json',wire_kind);tick=[NOW+2];platform_calls=[]
    def platform():platform_calls.append(tick[0])
    owner=Pump4AccountOwner(scope,lease=lease,key=KEY,secret=SECRET,wire=exchange.wire,platform_check=platform,clock=lambda:tick[0])
    if authorize:publish(root/'owner-go.json',dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=owner.scope_sha256,owner_go_text='GO PUMP4_TINY '+owner.scope_sha256))
    signal=TradeSignal(strategy='pump_fade',symbol='ZROUSDT',side='short',entry=100.,sl=101.,tp=97.9,tps=[97.9,95.8,93.],tp_fracs=[.4,.3,.3])
    plan=build_plan(signal,signal_bar_open_ms=NOW-H,next_open_ms=NOW,next_open=100.)
    x,p=inputs(exchange,now=tick[0]);flow=owner.prepare(plan,x,p)
    return owner,exchange,tick,platform_calls,flow,lease

def cycle(s,price='100',*,apply=True):
    o,e,t,c,f,l=s;x,p=inputs(e,now=t[0],price=price);return o.cycle(f,x,p,apply=apply)

def test_source_bound_memory_cycle_sends_exact_40_60_and_keeps_cost_pending(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        assert cycle(s)['status']=='ACK_RECONCILE_REQUIRED'
        assert D(e.state['held'])<1 and len(c)>=2
        t[0]+=1000;assert cycle(s,'97.8')['role']=='TP1'
        t[0]+=1000;assert cycle(s,'95.7')['role']=='TP2'
        t[0]+=1000;r=cycle(s,'95.7')
        assert r['status']=='FLAT_COSTS_PENDING' and D(e.state['held'])==0
        reqs=f.requests();assert D(reqs[1]['qty'])==D(reqs[0]['qty'])*D('.4') and D(reqs[2]['qty'])==D(reqs[0]['qty'])*D('.6')
        assert len(e.state['submitted_links'])==3
        publish(tmp_path/'receipt.json',dict(schema='PUMP4_ACCOUNT_OWNER_MEMORY_E2E_V1',status='MEMORY_WIRE_FULL_CYCLE_PASS',
            entry_qty=reqs[0]['qty'],tp1_qty=reqs[1]['qty'],tp2_qty=reqs[2]['qty'],remaining_qty=e.state['held'],
            unique_wire_requests=len(set(e.state['submitted_links'])),shared_account_lease_verified=True,
            source_bound_scope_and_go='FICTIONAL_FIXTURE_ONLY',final_costs_proven=False,
            financial_actor_selected=False,real_broker_requests=0,real_broker_writes=0,orders_allowed=False,money_authority=False))
    finally:l.close()

@pytest.mark.parametrize('kind',['off','no_go','other_key','wrong_lock','platform','stale','mode_unknown','costs'])
def test_entry_fails_closed_before_wire(tmp_path,kind):
    s=create(tmp_path,mode='ORDERS_OFF' if kind=='off' else 'OWNER_TINY_LIVE',authorize=kind!='no_go');o,e,t,c,f,l=s
    try:
        if kind=='other_key':o.key='NOT_THE_PINNED_ACCOUNT_KEY'
        elif kind=='wrong_lock':o.lease.inode+=1
        elif kind=='platform':o.platform_check=lambda:(_ for _ in ()).throw(ValueError('PHYSICAL_OWNER_CONFLICT'))
        x,p=inputs(e,now=t[0])
        if kind=='stale':t[0]+=6000
        elif kind=='mode_unknown':x['captures']['symbol_position']['body']['result']['list']=[];reseal(x['captures']['symbol_position'])
        elif kind=='costs':p['instruments']['pages'][0]['body']['result']['list'][0]['lowerFundingRate']='-.5';reseal(p['instruments']['pages'][0])
        with pytest.raises((ValueError,BlockingIOError)):o.cycle(f,x,p,apply=True)
        assert e.state['calls']==0
    finally:l.close()

def reseal(cap):cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()

def test_orders_off_rehearsal_has_no_send_even_with_a_fixture_go(tmp_path):
    s=create(tmp_path,mode='ORDERS_OFF');o,e,t,c,f,l=s
    try:
        r=cycle(s,apply=False);assert r['status']=='ACTION_RESERVED_ORDERS_OFF' and e.state['calls']==0
        assert cycle(s,apply=False)['status']=='RECONCILE_ONLY'
    finally:l.close()

def test_existing_global_lease_excludes_a_second_writer(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        with pytest.raises(BlockingIOError):AccountLease(l.path)
        assert e.state['calls']==0
    finally:l.close()

def test_lost_reply_is_reconciled_without_resend_on_new_owner_object(tmp_path):
    from research_lab.pump4_account_owner_v1 import Pump4AccountOwner
    s=create(tmp_path,wire_kind='entry_reply_loss');o,e,t,c,f,l=s
    try:
        assert cycle(s)['status']=='WIRE_UNKNOWN_RECONCILE_ONLY'
        g=Pump4AccountOwner(o.scope,lease=l,key=KEY,secret=SECRET,wire=e.wire,platform_check=o.platform_check,clock=lambda:t[0])
        x,p=inputs(e,now=t[0]);r=g.cycle(f,x,p,apply=True)
        assert r['status']=='PROTECTED_WAIT' and e.state['calls']==1
    finally:l.close()

def test_loss_latch_survives_restart_and_recovery_but_owned_exits_continue(tmp_path):
    from research_lab.pump4_account_owner_v1 import Pump4AccountOwner
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);t[0]+=1000;cycle(s,'140')
        assert (o.root/'entry-loss-stop.json').is_file()
        saved=(o.root/'entry-loss-stop.json').read_bytes()
        g=Pump4AccountOwner(o.scope,lease=l,key=KEY,secret=SECRET,wire=e.wire,platform_check=o.platform_check,clock=lambda:t[0]);s=(g,e,t,c,f,l)
        t[0]+=1000;assert cycle(s,'97.8')['role']=='TP1'
        assert (o.root/'entry-loss-stop.json').read_bytes()==saved
    finally:l.close()

def test_reserved_request_cannot_be_replaced_at_the_wire(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);before=e.state['calls'];request=dict(f.requests()[0],qty='99')
        with pytest.raises(ValueError):o.post_reserved(f,request,'ENTRY',source_ms=t[0])
        assert e.state['calls']==before
    finally:l.close()

def test_delayed_preflight_never_reaches_wire(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        calls=[0]
        def late():
            calls[0]+=1
            if calls[0]>=2:t[0]+=6000
        o.platform_check=late
        result=cycle(s)
        assert e.state['calls']==0 and result['status']=='WIRE_UNKNOWN_RECONCILE_ONLY'
    finally:l.close()

def test_direct_lifecycle_reservation_is_not_an_account_owner_dispatch_ticket(tmp_path):
    from research_lab.pump4_account_adapter_v1 import owned_observation
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);t[0]+=1000;x,p=inputs(e,now=t[0],price='97.8')
        observation=owned_observation(x,f.config['plan'],f.requests(),first_send_ms=NOW,expected_fingerprint=FP,now_ms=t[0])
        action=f.advance(observation,now_ms=t[0]);assert action['role']=='TP1';before=e.state['calls']
        with pytest.raises(ValueError,match='TICKET'):o.post_reserved(f,action['request'],'TP1',source_ms=t[0])
        assert e.state['calls']==before
    finally:l.close()

def test_changed_in_memory_scope_cannot_bypass_persisted_authority(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        o.scope['policy']['day_loss_usdt']='100'
        with pytest.raises(ValueError,match='SCOPE'):cycle(s)
        assert not f.requests() and e.state['calls']==0
    finally:l.close()

def test_partial_entry_targets_use_only_actual_filled_quantity(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s;original=e.wire
    def partial(method,url,headers,data,timeout):
        result=original(method,url,headers,data,timeout);r=json.loads(data)
        if not r['reduceOnly']:
            amount=D(r['qty'])/2;e.state['held']=str(amount);e.state['stop']['qty']=str(amount)
            row=e.state['orders'][r['orderLinkId']];row.update(cumExecQty=str(amount),orderStatus='PartiallyFilledCanceled')
            e.state['executions'][0].update(execQty=str(amount),execFee=str(amount*D(100)*D('.0006')));e.save()
        return result
    o.wire=partial
    try:
        cycle(s);actual=D(e.state['held']);t[0]+=1000;cycle(s,'97.8');t[0]+=1000;cycle(s,'95.7')
        reqs=f.requests();assert D(reqs[1]['qty'])==actual*D('.4') and D(reqs[2]['qty'])==actual*D('.6')
        assert D(e.state['held'])==0
    finally:l.close()

@pytest.mark.parametrize('kind',['reply_before_accept','rate_limit'])
def test_unknown_or_api_error_keeps_one_lifecycle_and_never_resends(tmp_path,kind):
    s=create(tmp_path,wire_kind='intent_reply_loss' if kind=='reply_before_accept' else 'entry_rate_limit');o,e,t,c,f,l=s
    try:
        assert cycle(s)['status']=='WIRE_UNKNOWN_RECONCILE_ONLY'
        assert cycle(s)['status']=='RECONCILE_ONLY' and e.state['calls']==1
        assert (o.root/'admitted-lifecycle.json').is_file()
    finally:l.close()

def test_expired_entry_authority_and_revocation_do_not_abandon_owned_exits(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);publish(o.root/'entry-revoked.json',dict(reason='fixture owner revoked new entries'))
        t[0]+=H;assert cycle(s,'97.8')['role']=='TP1'
        assert e.state['calls']==2
    finally:l.close()

def test_corrupt_risk_journal_inhibits_entries_but_keeps_independent_owned_custody(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);(o.root/'risk.jsonl').write_bytes(b'{broken\n');t[0]+=1000
        assert cycle(s,'97.8')['role']=='TP1' and (o.root/'entry-loss-stop.json').is_file()
    finally:l.close()

def test_new_interpreter_preserves_loss_latch_and_exact_account_scope(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    cycle(s);t[0]+=1000;cycle(s,'140');l.close()
    context=tmp_path/'restart.json';context.write_text(json.dumps(dict(scope=o.scope,key=KEY,secret=SECRET,exchange=str(e.path),flow=str(f.root),now=t[0]+1000)))
    script='''import json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from research_lab.kity_micro_physical_owner_v1 import AccountLease
from research_lab.pump4_account_owner_v1 import Pump4AccountOwner
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
from scripts.rehearse_pump4_bybit_v1 import MemoryBybit
from tests.test_pump4_account_owner_v1 import inputs
x=json.load(open(sys.argv[1]));lease=AccountLease(x['scope']['account_lock_path'])
try:
 e=MemoryBybit(Path(x['exchange']),'normal');o=Pump4AccountOwner(x['scope'],lease=lease,key=x['key'],secret=x['secret'],wire=e.wire,platform_check=lambda:None,clock=lambda:x['now'])
 flow=Pump4Lifecycle.resume(x['flow']);bundle,public=inputs(e,now=x['now'],price='97.8')
 result=o.cycle(flow,bundle,public,apply=True)
 print(json.dumps(dict(result=result,latch=(o.root/'entry-loss-stop.json').is_file(),calls=e.state['calls'])))
finally:lease.close()
'''
    out=json.loads(subprocess.check_output([sys.executable,'-B','-c',script,str(context)],text=True))
    assert out['result']['role']=='TP1' and out['latch'] and out['calls']==2

@pytest.mark.parametrize('kind',['foreign','public_hash','private_hash','wrong_account','stale_public'])
def test_source_conflict_blocks_prepare_before_any_entry_claim(tmp_path,kind):
    from research_lab.pump4_account_owner_v1 import source_sizing
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        x,p=inputs(e,now=t[0])
        if kind=='foreign':
            cap=x['captures']['positions']['pages'][0];cap['body']['result']['list']=[dict(symbol='BTCUSDT',positionIdx=0,size='1',side='Buy')];reseal(cap)
        elif kind=='public_hash':p['instruments']['pages'][0]['raw_sha256']='0'*64
        elif kind=='private_hash':x['captures']['wallet']['raw_sha256']='0'*64
        elif kind=='wrong_account':x['captures']['wallet']['account_fingerprint']='0'*64
        else:
            cap=p['instruments']['pages'][0];cap['request_ms']-=6000;cap['receive_ms']-=6000;cap['body']['time']-=6000;reseal(cap)
        with pytest.raises(ValueError):source_sizing(f.config['plan'],x,p,o.scope['policy'],fingerprint=FP,now_ms=t[0])
        assert not (o.root/'admitted-lifecycle.json').exists() and e.state['calls']==0
    finally:l.close()

def test_funding_uses_signed_cash_effect_and_actual_execution_fees(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);t[0]+=1000;x,p=inputs(e,now=t[0]);cap=x['history_windows'][0]['groups']['transactions']['pages'][0]
        cap['body']['result']['list']=[dict(id='funding-expense',symbol='ZROUSDT',category='linear',currency='USDT',type='SETTLEMENT',transactionTime=str(NOW+3),funding='-.25')];reseal(cap)
        assert o.cycle(f,x,p,apply=True)['status']=='PROTECTED_WAIT'
        row=o.risk.read()[-1];fee=sum(D(r['execFee']) for r in e.state['executions'])
        assert D(row['total_net_usdt'])==-fee-D('.25')
    finally:l.close()

def test_new_day_gap_is_measured_from_previous_mark_not_hidden_by_reset(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);t[0]+=1000;cycle(s);prior=o.risk.read()[-1]
        t[0]=(t[0]//(24*H)+1)*24*H+2;cycle(s,'140');row=o.risk.read()[-1]
        assert row['day']!=prior['day'] and D(row['day_baseline_usdt'])==D(prior['total_net_usdt'])
        assert 'DAY' in row['reasons'] and (o.root/'entry-loss-stop.json').is_file()
    finally:l.close()

def test_drawdown_latches_after_positive_peak_without_a_daily_loss(tmp_path):
    s=create(tmp_path,policy_override=dict(drawdown_usdt='.1'));o,e,t,c,f,l=s
    try:
        cycle(s);t[0]+=1000;cycle(s,'99');assert D(o.risk.read()[-1]['high_water_usdt'])>0
        t[0]+=1000;cycle(s,'100');row=o.risk.read()[-1]
        assert row['reasons']==['DRAWDOWN'] and (o.root/'entry-loss-stop.json').is_file()
    finally:l.close()

def test_relocated_barrier_directory_cannot_resend_the_same_entry(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        cycle(s);barriers=o.root/'send-barriers';barriers.rename(o.root/'preserved-original-barriers')
        empty=o.root/'empty-barriers';empty.mkdir();barriers.symlink_to(empty,target_is_directory=True)
        attempts=[]
        def wire(*args):attempts.append(True);return 200,json.dumps(dict(retCode=0,result=dict(orderId='duplicate',orderLinkId=f.requests()[0]['orderLinkId']))).encode()
        o.wire=wire
        with pytest.raises(ValueError):o.post_reserved(f,f.requests()[0],'ENTRY',source_ms=NOW)
        assert attempts==[]
    finally:l.close()

def test_entry_ticket_includes_aging_instrument_evidence_at_final_wire(tmp_path):
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        x,p=inputs(e,now=t[0]);cap=p['instruments']['pages'][0]
        cap['request_ms']-=1600;cap['receive_ms']-=1600;cap['body']['time']-=1600;reseal(cap)
        calls=[0]
        def preflight():
            calls[0]+=1
            if calls[0]==2:t[0]+=1200
        o.platform_check=preflight
        r=o.cycle(f,x,p,apply=True)
        assert r['status']=='WIRE_UNKNOWN_RECONCILE_ONLY' and e.state['calls']==0
    finally:l.close()
