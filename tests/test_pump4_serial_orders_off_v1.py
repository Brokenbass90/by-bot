"""Two sequential fictional-account lifecycles; no real keys or network."""
import copy
import hashlib
import json
from decimal import Decimal as D

import pytest

from test_pump4_account_owner_v1 import KEY, FP, inputs
from test_pump4_bybit_sources_v1 import NOW, H
from research_lab.kity_micro_physical_owner_v1 import AccountLease
from research_lab.pump4_execution_plan_v1 import build_plan
from scripts.rehearse_pump4_bybit_v1 import MemoryBybit
from strategies.signals import TradeSignal


def setup_case(tmp_path, *, valid_period_ms=7*24*H, **overrides):
    from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
    lock = tmp_path / 'fictional-account.lock'
    lease = AccountLease(lock)
    scope = dict(schema='PUMP4_SERIAL_ORDERS_OFF_SCOPE_V1', mode='ORDERS_OFF',
        fixture_only=True, account_fingerprint=FP, root=str(tmp_path/'serial'),
        account_lock_path=str(lock), account_lock_inode=lease.inode,
        valid_from_ms=NOW, valid_until_ms=NOW+valid_period_ms,
        policy=dict(allocation_usdt='50', gross_usdt='30', reserve_usdt='20',
            risk_usdt='1', slippage_bps='10', day_loss_usdt='2',
            week_loss_usdt='3', drawdown_usdt='6', lifetime_loss_usdt='3',
            max_entries=2, max_positions=1))
    scope['policy'].update(overrides)
    clock = [NOW+2]
    obj = Pump4SerialOrdersOff(scope, lease=lease, clock=lambda:clock[0])
    exchange = MemoryBybit(tmp_path/'memory.json', 'normal')
    return obj, exchange, clock, lease, scope


def plan_at(entry):
    s=TradeSignal(strategy='pump_fade',symbol='ZROUSDT',side='short',entry=100.,
        sl=101.,tp=97.9,tps=[97.9,95.8,93.],tp_fracs=[.4,.3,.3])
    return build_plan(s,signal_bar_open_ms=entry-H,next_open_ms=entry,next_open=100.)


def sources(exchange, *, now, entry, price='100'):
    """Reuse the accepted API fixture; retain one exchange across the series."""
    bundle,public=inputs(exchange,now=now,price=price)
    w=bundle['history_windows'][0]
    w['start_ms']=entry
    bundle['history_start_ms']=entry
    for name,group in w['groups'].items():
        cap=group['pages'][0]
        cap['params']['startTime']=str(entry)
        rows=cap['body']['result']['list']
        if name=='history':
            for row in rows:row['updatedTime']=str(exchange.state['test_order_times'][row['orderLinkId']])
            rows[:]=[r for r in rows if int(r['updatedTime'])>=entry]
        elif name=='executions':
            for row in rows:row['execTime']=str(exchange.state['test_exec_times'][row['execId']])
            rows[:]=[r for r in rows if int(r['execTime'])>=entry]
    caps=list(bundle['captures'].values())+[g for g in w['groups'].values()]
    for group in caps:
        for cap in group.get('pages',[group]):
            cap['raw']=json.dumps(cap['body'])
            cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
    return bundle,public


def memory_tick(obj, exchange, clock, entry, price='100', lose_reply=False):
    b,p=sources(exchange,now=clock[0],entry=entry,price=price)
    result=obj.tick(b,p)
    request=result.get('request')
    if request:
        exchange.state.setdefault('test_order_times',{})[request['orderLinkId']]=clock[0]
        old={r['execId'] for r in exchange.state['executions']}
        exchange.wire('POST','https://api.bybit.com/v5/order/create',{},json.dumps(request).encode(),1)
        for row in exchange.state['executions']:
            if row['execId'] not in old:exchange.state.setdefault('test_exec_times',{})[row['execId']]=clock[0]
        exchange.save()
        if lose_reply:raise TimeoutError('FICTIONAL exchange accepted; reply was lost')
    return result


def full_model_cycle(case, entry):
    obj,e,t,lease,scope=case;t[0]=entry+2
    b,p=sources(e,now=t[0],entry=entry)
    obj.reserve(plan_at(entry),b,p)
    assert memory_tick(obj,e,t,entry)['role']=='ENTRY'
    t[0]+=1000;assert memory_tick(obj,e,t,entry,'97.8')['role']=='TP1'
    t[0]+=1000;assert memory_tick(obj,e,t,entry,'95.7')['role']=='TP2'
    t[0]+=1000;assert memory_tick(obj,e,t,entry,'95.7')['status']=='FLAT_COSTS_PENDING'
    assert D(e.state['held'])==0
    return obj.settle_model(pending_fee_upper_bound_usdt='.05')


def test_two_full_cycles_restart_and_duplicate_signal_never_reenter(tmp_path):
    from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
    case=setup_case(tmp_path);o,e,t,l,s=case
    try:
        r=full_model_cycle(case,NOW)
        assert r['completed_model_cycles']==1 and r['cost_finality_proven'] is False
        with pytest.raises(ValueError,match='DUPLICATE_SIGNAL'):
            o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        resumed=Pump4SerialOrdersOff(s,lease=l,clock=lambda:t[0])
        full_model_cycle((resumed,e,t,l,s),NOW+H)
        r=resumed.summary()
        assert r['completed_model_cycles']==2 and r['active_ordinal'] is None
        assert len(e.state['submitted_links'])==len(set(e.state['submitted_links']))==6
        assert r['pending_fee_reserve_usdt']=='0.10'
        cash=D(0)
        for fill in e.state['executions']:
            req=next(v['request'] for v in e.state['orders'].values() if v['orderId']==fill['orderId'])
            amount=D(fill['execQty'])*D(fill['execPrice'])
            cash+=(amount if req['side']=='Sell' else -amount)-D(fill['execFee'])
        assert D(r['model_net_usdt'])==cash-D('.10')
        assert r['money_authority'] is False and r['broker_writes']==0
        t[0]=NOW+2*H+2
        with pytest.raises(ValueError,match='ENTRY_LIMIT'):
            resumed.reserve(plan_at(NOW+2*H),*sources(e,now=t[0],entry=NOW+2*H))
    finally:l.close()


def test_reservation_before_first_send_blocks_second_plan_after_restart(tmp_path):
    from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        o=Pump4SerialOrdersOff(s,lease=l,clock=lambda:t[0])
        with pytest.raises(ValueError,match='ACTIVE_LIFECYCLE'):
            o.reserve(plan_at(NOW+H),*sources(e,now=t[0],entry=NOW))
        with pytest.raises(ValueError,match='TERMINAL_REQUIRED'):
            o.settle_model(pending_fee_upper_bound_usdt='.05')
    finally:l.close()


def test_lost_entry_response_restart_reconciles_without_resend(tmp_path):
    from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        with pytest.raises(TimeoutError):memory_tick(o,e,t,NOW,lose_reply=True)
        o=Pump4SerialOrdersOff(s,lease=l,clock=lambda:t[0]);t[0]+=1000
        result=memory_tick(o,e,t,NOW)
        assert result['request'] is None and len(e.state['submitted_links'])==1
        assert o.summary()['active_ordinal']==1
    finally:l.close()


@pytest.mark.parametrize('override', [dict(mode='OWNER_TINY_LIVE'),dict(fixture_only=False),dict(account_fingerprint='a'*64)])
def test_no_live_scope_or_actual_account_can_be_instantiated(tmp_path,override):
    from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
    o,e,t,l,s=setup_case(tmp_path)
    try:
        changed=dict(s,**override)
        with pytest.raises(ValueError):Pump4SerialOrdersOff(changed,lease=l,clock=lambda:t[0])
    finally:l.close()


def test_lifetime_loss_is_persistent_across_new_flow_and_utc_day(tmp_path):
    from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
    case=setup_case(tmp_path,lifetime_loss_usdt='.04');o,e,t,l,s=case
    try:
        # A valid fixture exit at entry price produces a small net fee loss.
        e.state['fixture_exit_price']='100';e.save()
        full_model_cycle(case,NOW)
        t[0]=NOW+24*H+2;o=Pump4SerialOrdersOff(s,lease=l,clock=lambda:t[0])
        assert o.summary()['entry_loss_latched'] is True
        with pytest.raises(ValueError,match='ENTRY_LOSS_LATCHED'):
            o.reserve(plan_at(NOW+24*H),*sources(e,now=t[0],entry=NOW+24*H))
    finally:l.close()


def test_expiry_blocks_new_entries_but_keeps_owned_model_custody(tmp_path):
    o,e,t,l,s=setup_case(tmp_path,valid_period_ms=H)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        memory_tick(o,e,t,NOW)
        t[0]=s['valid_until_ms']+1
        r=memory_tick(o,e,t,NOW,'97.8')
        assert r['role'] in ('TP1','TIME_EXIT')
    finally:l.close()


def test_missing_fee_bound_cannot_release_flat_cycle(tmp_path):
    o,e,t,l,s=setup_case(tmp_path)
    try:
        with pytest.raises((TypeError,ValueError)):o.settle_model()
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        memory_tick(o,e,t,NOW)
        with pytest.raises(ValueError):o.settle_model(pending_fee_upper_bound_usdt='NaN')
    finally:l.close()


def test_partial_journal_never_repairs_or_accepts_another_entry(tmp_path):
    from research_lab.pump4_serial_orders_off_v1 import Pump4SerialOrdersOff
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        p=o.root/'serial-events.jsonl'
        with p.open('ab') as f:f.write(b'{"partial":')
        before=p.read_bytes()
        with pytest.raises(ValueError):Pump4SerialOrdersOff(s,lease=l,clock=lambda:t[0]).summary()
        assert p.read_bytes()==before
    finally:l.close()


def test_source_failure_latches_entries_but_does_not_abandon_model_custody(tmp_path):
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        memory_tick(o,e,t,NOW)
        bad,public=sources(e,now=t[0],entry=NOW)
        bad['completed_ms']-=60000
        with pytest.raises(ValueError):o.tick(bad,public)
        r=o.summary()
        assert r['entry_block_latched'] is True
        assert r['entry_loss_latched'] is False
        t[0]+=1000
        assert memory_tick(o,e,t,NOW)['request'] is None
        assert D(e.state['held'])>0 and o.summary()['active_ordinal']==1
    finally:l.close()


def test_a_go_file_inside_child_never_enables_a_sender(tmp_path):
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        (o.root/'slots/0001/owner-go.json').write_text('{}')
        with pytest.raises(ValueError,match='GO_FORBIDDEN'):
            memory_tick(o,e,t,NOW)
        assert e.state['calls']==0
    finally:l.close()


def test_unsent_reservation_cannot_bypass_source_latch(tmp_path):
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        bad,p=sources(e,now=t[0],entry=NOW);bad['completed_ms']-=60000
        with pytest.raises(ValueError):o.tick(bad,p)
        with pytest.raises(ValueError,match='ENTRY_SAFETY_LATCHED'):
            memory_tick(o,e,t,NOW)
        assert e.state['calls']==0
    finally:l.close()


def test_unsent_reservation_cannot_bypass_expiry(tmp_path):
    o,e,t,l,s=setup_case(tmp_path,valid_period_ms=1000)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        t[0]=NOW+1001
        with pytest.raises(ValueError,match='ENTRY_EXPIRED'):
            memory_tick(o,e,t,NOW)
        assert e.state['calls']==0
    finally:l.close()


def test_terminal_cannot_settle_stale_risk_after_child_append_failure(tmp_path,monkeypatch):
    from research_lab.att1_lifecycle_journal import LifecycleJournal
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        memory_tick(o,e,t,NOW)
        t[0]+=1000;memory_tick(o,e,t,NOW,'97.8')
        t[0]+=1000;memory_tick(o,e,t,NOW,'95.7')
        append=LifecycleJournal.append
        def fail_risk(self,event):
            if self.path.name=='risk.jsonl':raise ValueError('fixture risk journal full')
            return append(self,event)
        monkeypatch.setattr(LifecycleJournal,'append',fail_risk)
        t[0]+=1000
        with pytest.raises(ValueError,match='RISK_OBSERVATION_BINDING'):
            memory_tick(o,e,t,NOW,'95.7')
        with pytest.raises(ValueError,match='TERMINAL_REQUIRED'):
            o.settle_model(pending_fee_upper_bound_usdt='.05')
        assert o.summary()['completed_model_cycles']==0
        assert o.summary()['entry_block_latched'] is True
    finally:l.close()


def test_unknown_risk_does_not_suppress_reduce_only_model_exit(tmp_path,monkeypatch):
    from research_lab.att1_lifecycle_journal import LifecycleJournal
    o,e,t,l,s=setup_case(tmp_path)
    try:
        o.reserve(plan_at(NOW),*sources(e,now=t[0],entry=NOW))
        memory_tick(o,e,t,NOW)
        append=LifecycleJournal.append
        def fail_risk(self,event):
            if self.path.name=='risk.jsonl':raise ValueError('fixture risk journal full')
            return append(self,event)
        monkeypatch.setattr(LifecycleJournal,'append',fail_risk)
        t[0]+=1000
        result=memory_tick(o,e,t,NOW,'97.8')
        assert result['role']=='TP1' and result['serial_accounting_status']=='UNKNOWN'
        assert result['request']['reduceOnly'] is True
        assert o.summary()['entry_block_latched'] is True
    finally:l.close()
