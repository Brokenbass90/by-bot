"""Concrete Bybit-shaped lifecycle, never a financial writer."""
import copy,json,subprocess,sys
from decimal import Decimal as D
import pytest
from research_lab.pump4_execution_plan_v1 import build_plan
from strategies.signals import TradeSignal
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle

START=7200000

def setup(tmp_path,**kw):
    signal=TradeSignal(strategy='pump_fade',symbol='ZROUSDT',side='short',entry=100.,sl=101.,tp=97.9,
        tps=[97.9,95.8,93.],tp_fracs=[.4,.3,.3])
    plan=build_plan(signal,signal_bar_open_ms=START-3600000,next_open_ms=START,next_open=100.)
    defaults=dict(qty='10',qty_step='1',min_qty='1',min_notional='5',tick_size='.1')
    defaults.update(kw)
    return Pump4Lifecycle(tmp_path,plan,**defaults)

def observation(now=START,held='0',orders=None,fills=None,price='100',stop=True):
    return dict(schema='PUMP4_BYBIT_OBSERVATION_V1',observed_ms=now,source_ms=now,
        pagination_complete=True,symbol='ZROUSDT',positionIdx=0,position_side='Sell',held_qty=held,
        price=price,orders=orders or [],executions=fills or [],funding=[],costs_complete=False,
        native_stop=(dict(orderId='native-1',symbol='ZROUSDT',side='Buy',qty=held,triggerPrice='104',
            stopOrderType='StopLoss',orderStatus='Untriggered',positionIdx=0) if stop and D(held)>0 else None))

def filled(request,qty=None,status='Filled'):
    q=request['qty'] if qty is None else qty
    row=dict(orderId='id-'+request['orderLinkId'],orderLinkId=request['orderLinkId'],symbol='ZROUSDT',
        side=request['side'],qty=request['qty'],cumExecQty=q,orderStatus=status,
        reduceOnly=request['reduceOnly'],positionIdx=0)
    fill=dict(execId='exec-'+request['orderLinkId'],orderId=row['orderId'],orderLinkId=request['orderLinkId'],
        symbol='ZROUSDT',side=request['side'],execQty=q,execPrice='100',execFee='.1',feeCurrency='USDT')
    return row,fill

def enter(flow,qty='10',status='Filled'):
    r=flow.advance(observation(),now_ms=START)['request']
    row,fill=filled(r,qty,status)
    return r,row,fill

def test_causal_entry_and_exact_request_restart(tmp_path):
    f=setup(tmp_path);a=f.advance(observation(),now_ms=START)
    assert a['request']['side']=='Sell' and a['request']['stopLoss']=='104.0'
    assert a['request']['tpslMode']=='Full' and a['orders_allowed'] is False
    # Reserved before handoff; absent exchange answer cannot cause another order.
    g=setup(tmp_path)
    b=g.advance(observation(),now_ms=START)
    assert b['status']=='RECONCILE_ONLY' and b['request'] is None
    assert len(g.requests())==1

@pytest.mark.parametrize('fault',['stale','incomplete','wrong_symbol','foreign_position'])
def test_uncertain_snapshot_cannot_admit_entry(tmp_path,fault):
    f=setup(tmp_path);o=observation()
    if fault=='stale':o['source_ms']-=5001
    elif fault=='incomplete':o['pagination_complete']=False
    elif fault=='wrong_symbol':o['symbol']='BTCUSDT'
    else:o['held_qty']='1'
    with pytest.raises(ValueError):f.advance(o,now_ms=START)
    assert not f.requests()

def test_target_triggers_40_60_with_process_restart(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f)
    wait=f.advance(observation(held='10',orders=[row],fills=[fill],price='99'),now_ms=START)
    assert wait['status']=='PROTECTED_WAIT' and wait['request'] is None
    a=f.advance(observation(held='10',orders=[row],fills=[fill],price='97.8'),now_ms=START)
    assert D(a['request']['qty'])==4 and a['request']['reduceOnly']
    row1,fill1=filled(a['request'])
    # New interpreter, same root/bytes; no in-memory cursor is required.
    code="from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle; import sys,json; print(json.dumps(Pump4Lifecycle.resume(sys.argv[1]).advance(json.loads(sys.argv[2]),now_ms=7200000)))"
    o=observation(held='6',orders=[row,row1],fills=[fill,fill1],price='95.7')
    out=json.loads(subprocess.check_output([sys.executable,'-B','-c',code,str(tmp_path),json.dumps(o)],text=True))
    assert D(out['request']['qty'])==6
    row2,fill2=filled(out['request'])
    done=setup(tmp_path).advance(observation(orders=[row,row1,row2],fills=[fill,fill1,fill2]),now_ms=START)
    assert done['status']=='FLAT_COSTS_PENDING' and done['request'] is None
    assert len(set(r['orderLinkId'] for r in f.requests()))==3

@pytest.mark.parametrize('status',['PartiallyFilled','PartiallyFilledCanceled'])
def test_partial_entry_requires_native_stop_before_wait_or_size_decision(tmp_path,status):
    f=setup(tmp_path);r,row,fill=enter(f,'3',status)
    o=observation(held='3',orders=[row],fills=[fill],stop=False)
    result=f.advance(o,now_ms=START)
    assert result['status']=='NATIVE_PROTECTION_UNKNOWN' and result['request'] is None
    o['native_stop']=observation(held='3')['native_stop']
    result=f.advance(o,now_ms=START)
    assert result['status']==('ENTRY_PENDING_PROTECTED' if status=='PartiallyFilled' else 'PARTIAL_SPLIT_UNREPRESENTABLE')
    assert result['request'] is None

def test_partial_exit_new_cid_only_after_terminal(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f)
    a=f.advance(observation(held='10',orders=[row],fills=[fill],price='97'),now_ms=START)['request']
    part,execution=filled(a,'2','PartiallyFilled')
    o=observation(held='8',orders=[row,part],fills=[fill,execution],price='97')
    assert f.advance(o,now_ms=START)['request'] is None
    part['orderStatus']='PartiallyFilledCanceled'
    b=f.advance(o,now_ms=START)['request']
    assert D(b['qty'])==2 and b['orderLinkId']!=a['orderLinkId']

def test_stop_takes_priority_and_no_profit_exit_after_native_fill(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f)
    o=observation(held='10',orders=[row],fills=[fill],price='104')
    assert f.advance(o,now_ms=START)['status']=='NATIVE_STOP_TRIGGER_WAIT'
    native=dict(execId='native-fill',orderId='native-1',orderLinkId='',symbol='ZROUSDT',side='Buy',execQty='10',execPrice='104',execFee='.6',feeCurrency='USDT')
    done=f.advance(observation(orders=[row],fills=[fill,native]),now_ms=START)
    assert done['status']=='FLAT_COSTS_PENDING' and len(f.requests())==1

def test_hold_limit_reduce_only_and_missing_costs_not_zero(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f)
    end=START+168*3600000
    a=f.advance(observation(now=end,held='10',orders=[row],fills=[fill],price='99'),now_ms=end)
    assert a['role']=='TIME_EXIT' and D(a['request']['qty'])==10
    row1,fill1=filled(a['request'])
    o=observation(now=end,orders=[row,row1],fills=[fill,fill1])
    assert f.advance(o,now_ms=end)['status']=='FLAT_COSTS_PENDING'
    o['costs_complete']=True;o['funding']=[dict(id='funding-1',amount='-.01',currency='USDT')]
    result=f.advance(o,now_ms=end)
    assert result['status']=='FLAT_COSTS_RECONCILED_ORDERS_OFF'
    assert D(result['actual_fees_usdt'])==D('.2') and result['money_authority'] is False

@pytest.mark.parametrize('fault',['dup_execution','unknown_fill','overfill','changed_request','changed_config'])
def test_conflicts_fail_closed_without_extra_order(tmp_path,fault):
    f=setup(tmp_path);r,row,fill=enter(f)
    o=observation(held='10',orders=[row],fills=[fill],price='97')
    if fault=='dup_execution':o['executions'].append(copy.deepcopy(fill))
    elif fault=='unknown_fill':o['executions'].append(dict(fill,execId='foreign',orderId='unknown',orderLinkId='foreign'))
    elif fault=='overfill':row['cumExecQty']='11';fill['execQty']='11';o['held_qty']='11'
    elif fault=='changed_request':row['qty']='11'
    else:
        with pytest.raises(ValueError):setup(tmp_path,qty='15')
        return
    with pytest.raises(ValueError):f.advance(o,now_ms=START)
    assert len(f.requests())==1

def test_invalid_lot_and_noncausal_entry_fail_without_request(tmp_path):
    with pytest.raises(ValueError):setup(tmp_path,qty='9')
    f=setup(tmp_path)
    with pytest.raises(ValueError):f.advance(observation(now=START+6000),now_ms=START+6000)
    assert not f.requests()

def test_missing_stop_does_not_forget_observed_partial_fill(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f,'3','PartiallyFilled')
    assert f.advance(observation(held='3',orders=[row],fills=[fill],stop=False),now_ms=START)['status']=='NATIVE_PROTECTION_UNKNOWN'
    row['cumExecQty']='0';row['orderStatus']='Rejected'
    with pytest.raises(ValueError):f.advance(observation(orders=[row]),now_ms=START)

def test_hold_exit_does_not_depend_on_partial_40_60_representability(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f,'3','PartiallyFilledCanceled')
    end=START+168*3600000
    a=f.advance(observation(now=end,held='3',orders=[row],fills=[fill],price='99'),now_ms=end)
    assert a['role']=='TIME_EXIT' and D(a['request']['qty'])==3

def test_terminal_order_cannot_reopen_or_change_identity(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f,'5','PartiallyFilledCanceled')
    assert f.advance(observation(held='5',orders=[row],fills=[fill],price='99'),now_ms=START)['status']=='PROTECTED_WAIT'
    row['orderStatus']='PartiallyFilled'
    with pytest.raises(ValueError):f.advance(observation(held='5',orders=[row],fills=[fill]),now_ms=START)

def test_funding_history_cannot_disappear_after_finality(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f)
    end=START+168*3600000
    a=f.advance(observation(now=end,held='10',orders=[row],fills=[fill],price='99'),now_ms=end)
    row1,fill1=filled(a['request'])
    o=observation(now=end,orders=[row,row1],fills=[fill,fill1]);o['costs_complete']=True
    o['funding']=[dict(id='settled-1',amount='-.2',currency='USDT')]
    assert f.advance(o,now_ms=end)['status']=='FLAT_COSTS_RECONCILED_ORDERS_OFF'
    o['funding']=[]
    with pytest.raises(ValueError):f.advance(o,now_ms=end)

def test_unverified_current_stop_cannot_self_authorize_flat_execution(tmp_path):
    f=setup(tmp_path);r,row,fill=enter(f,'3','PartiallyFilledCanceled')
    assert f.advance(observation(held='3',orders=[row],fills=[fill],stop=False),now_ms=START)['status']=='NATIVE_PROTECTION_UNKNOWN'
    fake=dict(execId='foreign-stop',orderId='NEVER_VERIFIED',orderLinkId='',symbol='ZROUSDT',side='Buy',execQty='3',execPrice='104',execFee='.1',feeCurrency='USDT')
    o=observation(orders=[row],fills=[fill,fake]);o['costs_complete']=True
    o['native_stop']=dict(orderId='NEVER_VERIFIED',symbol='ZROUSDT',side='Buy',qty='0',triggerPrice='999',stopOrderType='StopLoss',orderStatus='Filled',positionIdx=0)
    with pytest.raises(ValueError):f.advance(o,now_ms=START)
