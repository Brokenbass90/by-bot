import copy

import pytest

from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
from research_lab.kity_execution_micro_runtime_v1 import MicroJournal,prepare_micro_plan
from research_lab.kity_micro_transport_v1 import SourceError
from test_kity_micro_runtime_v1 import dossier,BASKET
from test_kity_micro_integration_v3 import V3


def journal(tmp_path):return MicroJournal(tmp_path/'j.sqlite',prepare_micro_plan(dossier(),V3))


class Owner:
    """Offline stand-in for the separately installed exclusive physical owner."""
    def __init__(self,j,fail=False):self.j=j;self.sent=[];self.fail=fail
    def assert_exclusive(self,plan):assert plan['plan_id']==self.j.plan['plan_id']
    def validate_preflight(self,plan,request,role):assert role in ('ENTRY','EXIT')
    def post_once(self,path,request):
        assert self.j.snapshot()['entries'] or self.j.snapshot()['exits']
        self.sent.append((path,request))
        if self.fail:raise TimeoutError('uncertain delivery')
        return dict(retCode=0,result=dict(orderId='broker-1',orderLinkId=request['orderLinkId']))


def test_no_physical_owner_or_exact_go_means_no_intent_and_no_send(tmp_path):
    j=journal(tmp_path);b=MicroAccountBridge(j,None,clock=lambda:2100)
    with pytest.raises(SourceError,match='PHYSICAL_OWNER_UNBOUND'):b.dispatch_next('anything')
    assert j.snapshot()['entries']=={}
    owner=Owner(j);b=MicroAccountBridge(j,None,owner=owner,clock=lambda:2100)
    with pytest.raises(SourceError,match='EXACT_OWNER_GO'):b.dispatch_next('GO')
    assert owner.sent==[] and j.snapshot()['entries']=={}


def test_offline_owner_ack_is_not_a_fill_and_send_intent_precedes_transport(tmp_path):
    j=journal(tmp_path);o=Owner(j);b=MicroAccountBridge(j,None,owner=o,clock=lambda:2100)
    r=b.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    assert r['status']=='ACK_REQUIRES_READBACK' and len(o.sent)==1
    assert j.snapshot()['held'][BASKET[0][0]]=='0'
    assert b.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])['status']=='RECONCILE'
    assert len(o.sent)==1


def test_unknown_send_survives_restart_without_any_resend(tmp_path):
    j=journal(tmp_path);o=Owner(j,fail=True);b=MicroAccountBridge(j,None,owner=o,clock=lambda:2100)
    assert b.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])['status']=='DISPATCH_UNKNOWN'
    p=j.plan;j.close();j=MicroJournal(tmp_path/'j.sqlite',p);o2=Owner(j)
    b=MicroAccountBridge(j,None,owner=o2,clock=lambda:2200)
    assert b.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+p['plan_id'])['status']=='RECONCILE'
    assert o2.sent==[] and j.snapshot()['entry_blocked'] is True


class Reader:
    def __init__(self,row,execs=None):self.row=row;self.execs=execs or [];self.calls=[]
    def pages(self,path,params):
        self.calls.append((path,params))
        rows=[] if path.endswith('realtime') else self.execs if path.endswith('/list') else [self.row]
        return dict(complete=True,pages=[dict(body=dict(retCode=0,result=dict(list=rows)),http_status=200)])


def order(j):
    l=j.plan['legs'][0]
    return dict(orderId='broker-1',orderLinkId=l['request']['orderLinkId'],symbol=l['symbol'],
      side=l['side'],qty='1',price='1',timeInForce='IOC',orderType='Limit',positionIdx=0,
      reduceOnly=False,orderStatus='Filled',cumExecQty='1')


def test_empty_realtime_uses_history_and_execs_never_proves_no_order(tmp_path):
    j=journal(tmp_path);o=Owner(j);b=MicroAccountBridge(j,None,owner=o,clock=lambda:2100)
    b.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id']);r=order(j)
    x=dict(r,execId='x1',execType='Trade',execTime='2100',execQty='1',execPrice='1',execFee='.01')
    reader=Reader(r,[x]);b=MicroAccountBridge(j,reader,clock=lambda:2200)
    b.reconcile_orders()
    assert len(reader.calls)==3 and j.snapshot()['held'][BASKET[0][0]]=='1'
    assert j.snapshot()['entries'][BASKET[0][0]]['terminal'] is True
    assert j.actions(2200)[0]['kind']=='PROTECTION_READBACK'


def test_terminal_without_complete_execution_rows_stays_reconciliation(tmp_path):
    j=journal(tmp_path);o=Owner(j);MicroAccountBridge(j,None,owner=o,clock=lambda:2100).dispatch_next(
      'GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    MicroAccountBridge(j,Reader(order(j)),clock=lambda:2200).reconcile_orders()
    assert j.actions(2200)[0]['kind']=='RECONCILE'


@pytest.mark.parametrize('field,value',[('symbol','FOREIGNUSDT'),('price','2'),('timeInForce','GTC')])
def test_material_history_conflict_is_not_adopted(tmp_path,field,value):
    j=journal(tmp_path);o=Owner(j);MicroAccountBridge(j,None,owner=o,clock=lambda:2100).dispatch_next(
      'GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    row=order(j);row[field]=value
    with pytest.raises((ValueError,SourceError)):
        MicroAccountBridge(j,Reader(row),clock=lambda:2200).reconcile_orders()
    assert j.snapshot()['held'][BASKET[0][0]]=='0'
    assert j.snapshot()['entry_blocked'] is True


def test_stale_duplicate_dispatch_proposal_does_not_post_again(tmp_path):
    j=journal(tmp_path);o=Owner(j);b=MicroAccountBridge(j,None,owner=o,clock=lambda:2100)
    stale=j.actions(2100);j.actions=lambda now:stale
    go='GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id']
    b.dispatch_next(go);r=b.dispatch_next(go)
    assert len(o.sent)==1 and r['status']=='RECONCILE'


class AccountReader:
    def __init__(self,positions=None,transactions=None):
        self.positions=positions or [];self.transactions=transactions or []
    def pages(self,path,params):
        rows=self.positions if path=='/v5/position/list' else self.transactions if path=='/v5/account/transaction-log' else []
        return dict(complete=True,pages=[dict(http_status=200,body=dict(retCode=0,result=dict(list=rows)))])


def test_same_symbol_foreign_position_is_never_adopted(tmp_path):
    j=journal(tmp_path);s=BASKET[0][0]
    b=MicroAccountBridge(j,AccountReader([dict(symbol=s,side='Buy',positionIdx=0,size='2')]),clock=lambda:2100)
    b.reconcile_positions()
    assert j.snapshot()['ownership_conflict'] is True
    assert j.snapshot()['held'][s]=='0'


def test_terminal_cash_rows_must_cover_each_exact_owned_execution(tmp_path):
    from test_kity_micro_runtime_v1 import enter,exit_leg,event
    j=journal(tmp_path);s=BASKET[0][0];enter(j,s)
    j.append(event('UNWIND',reason='test'));exit_leg(j,s)
    rows=[]
    for xid,fill in j.snapshot()['fills'].items():
        rows.append(dict(id='cash-'+xid,type='TRADE',tradeId=xid,orderId=fill['order_id'],
            symbol=s,currency='USDT',category='linear',qty='1',fee='.01',change='-.01'))
    b=MicroAccountBridge(j,AccountReader(transactions=rows),owner=Owner(j),clock=lambda:2200)
    assert b.finalize_accounting({s:[]})['terminal_net_usdt']=='-0.02'


def test_missing_fee_cash_row_cannot_be_zero_or_false_finality(tmp_path):
    from test_kity_micro_runtime_v1 import enter,exit_leg,event
    j=journal(tmp_path);s=BASKET[0][0];enter(j,s)
    j.append(event('UNWIND',reason='test'));exit_leg(j,s)
    with pytest.raises(SourceError,match='OWNED_EXECUTION_CASH_SOURCE_MISSING'):
        MicroAccountBridge(j,AccountReader(),owner=Owner(j),clock=lambda:2200).finalize_accounting({s:[]})
    assert j.snapshot()['phase']!='TERMINAL'


def test_documented_parameter_rejection_is_terminal_no_fill_not_unknown_resend(tmp_path):
    j=journal(tmp_path)
    class Reject(Owner):
        def post_once(self,path,request):
            self.sent.append((path,request));return dict(retCode=10001,retMsg='Request parameter error',result={})
    o=Reject(j);b=MicroAccountBridge(j,None,owner=o,clock=lambda:2100)
    r=b.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    assert r['status']=='DEFINITE_REJECTION'
    assert j.snapshot()['entries'][BASKET[0][0]]['terminal'] is True
    assert j.snapshot()['entry_blocked'] and len(o.sent)==1
    b.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    assert len(o.sent)==1
