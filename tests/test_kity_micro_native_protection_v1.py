from decimal import Decimal as D
import pytest

from research_lab.kity_execution_micro_runtime_v1 import MicroJournal,prepare_micro_plan
from test_kity_micro_runtime_v1 import dossier,BASKET,event,send,fill,terminal,exit_leg
from test_kity_micro_integration_v3 import V3


def protected_journal(tmp_path):
    d=dossier()
    for leg in d['profiles'][0]['legs']:
        leg['draft_entry'].update(stopLoss='.9' if leg['side']=='Buy' else '1.1',
           slTriggerBy='LastPrice',slOrderType='Market',tpslMode='Full')
    j=MicroJournal(tmp_path/'j.sqlite',prepare_micro_plan(d,V3));s=BASKET[0][0]
    send(j,s);fill(j,s);terminal(j,s)
    return j,s


def bind(j,s):
    j.append(event('NATIVE_PROTECTION_BIND',symbol=s,order_id='native-stop-1',quantity='1',
       trigger_price='.9',side='Sell',reduce_only=True,position_idx=0))


def test_native_protection_does_not_block_next_leg_but_is_durable_owned_exit(tmp_path):
    j,s=protected_journal(tmp_path);bind(j,s)
    assert j.actions(2100)[0]['kind']=='ENTRY' and j.actions(2100)[0]['symbol']==BASKET[1][0]
    native=next(iter(j.snapshot()['exits'].values()))
    assert native['order_id']=='native-stop-1' and native['is_native_protection'] is True
    p=j.plan;j.close();j=MicroJournal(tmp_path/'j.sqlite',p)
    assert j.snapshot()['entries'][s]['protected']=='1'


def test_filled_native_stop_blocks_new_entries_and_unwinds_remaining_legs(tmp_path):
    j,s=protected_journal(tmp_path);bind(j,s);native=next(iter(j.snapshot()['exits'].values()))
    j.append(event('EXIT_FILL',symbol=s,order_link_id=native['link'],order_id='native-stop-1',
       execution_id='sl-fill',quantity='1',price='.9',fee_usdt='.01'))
    assert j.snapshot()['entry_blocked'] is True
    assert j.snapshot()['held'][s]=='0'


@pytest.mark.parametrize('field,value',[('trigger_price','.8'),('quantity','2'),('side','Buy'),('reduce_only',False)])
def test_conflicting_native_protection_cannot_be_adopted(tmp_path,field,value):
    j,s=protected_journal(tmp_path)
    e=event('NATIVE_PROTECTION_BIND',symbol=s,order_id='native-stop-1',quantity='1',
       trigger_price='.9',side='Sell',reduce_only=True,position_idx=0)
    e[field]=value
    with pytest.raises(ValueError,match='NATIVE_PROTECTION'):j.append(e)


def test_owned_market_exit_can_proceed_while_native_stop_is_active_then_cancel_once(tmp_path):
    j,s=protected_journal(tmp_path);bind(j,s)
    j.append(event('UNWIND',reason='deadline'))
    assert j.actions(2100)[0]['kind']=='EXIT'
    exit_leg(j,s)
    a=j.actions(2100)[0]
    assert a['kind']=='CANCEL_NATIVE_PROTECTION' and a['request']['orderId']=='native-stop-1'
    j.append(event('NATIVE_CANCEL_INTENT',symbol=s,order_link_id=a['order_link_id']))
    assert j.actions(2100)[0]['kind']=='RECONCILE'


def test_actual_shaped_native_readback_binds_only_exact_attached_stop(tmp_path):
    from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
    from test_kity_micro_account_bridge_v1 import Reader,Owner
    j,s=protected_journal(tmp_path)
    row=dict(symbol=s,side='Sell',orderId='native-stop-1',orderLinkId='',qty='1',
        orderType='Market',positionIdx=0,reduceOnly=True,orderStatus='Untriggered',
        cumExecQty='0',stopOrderType='StopLoss',triggerPrice='.9',createdTime='2000')
    b=MicroAccountBridge(j,Reader(row),owner=Owner(j),clock=lambda:2100)
    b.bind_native_protection()
    assert j.snapshot()['entries'][s]['stop_id']=='native-stop-1'


def test_protection_readback_missing_causes_durable_unwind(tmp_path):
    from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
    from test_kity_micro_account_bridge_v1 import AccountReader,Owner
    j,s=protected_journal(tmp_path)
    b=MicroAccountBridge(j,AccountReader(),owner=Owner(j),clock=lambda:2100)
    b.bind_native_protection()
    assert j.snapshot()['entry_blocked'] is True


def test_protection_api_unknown_durably_blocks_entries_and_keeps_owned_exit_available(tmp_path):
    from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
    from test_kity_micro_account_bridge_v1 import Owner
    class FailedReader:
        def pages(self,*args):return dict(complete=False,pages=[])
    j,s=protected_journal(tmp_path)
    MicroAccountBridge(j,FailedReader(),owner=Owner(j),clock=lambda:2100).bind_native_protection()
    assert j.snapshot()['entry_blocked'] is True and j.actions(2200)[0]['kind']=='EXIT'


def test_bound_native_reconciliation_queries_broker_id_not_synthetic_link(tmp_path):
    from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
    j,s=protected_journal(tmp_path);bind(j,s)
    class Reader:
        def pages(self,path,params):
            if params.get('orderLinkId','').endswith('-SL'):
                pytest.fail('native SL has no exchange orderLinkId; must query orderId')
            return dict(complete=True,pages=[dict(http_status=200,body=dict(retCode=0,result=dict(list=[])))])
    MicroAccountBridge(j,Reader(),clock=lambda:2100).reconcile_orders()


def test_one_order_readback_failure_does_not_skip_other_owned_order(tmp_path):
    from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
    j,s=protected_journal(tmp_path);bind(j,s);seen=[]
    class Reader:
        def pages(self,path,params):
            seen.append(params)
            if params.get('orderLinkId')==j.plan['legs'][0]['request']['orderLinkId']:
                return dict(complete=False,pages=[])
            return dict(complete=True,pages=[dict(http_status=200,body=dict(retCode=0,result=dict(list=[])))])
    with pytest.raises(ValueError):MicroAccountBridge(j,Reader(),clock=lambda:2100).reconcile_orders()
    assert any(p.get('orderId')=='native-stop-1' for p in seen)


def test_bound_full_native_stop_can_shrink_after_partial_owned_unwind(tmp_path):
    from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
    from test_kity_micro_account_bridge_v1 import Reader
    j,s=protected_journal(tmp_path);bind(j,s)
    native=next(iter(j.snapshot()['exits'].values()))
    row=dict(symbol=s,side='Sell',orderId='native-stop-1',orderLinkId='',qty='.5',orderType='Market',
        positionIdx=0,reduceOnly=True,orderStatus='Filled',cumExecQty='.5',stopOrderType='StopLoss',triggerPrice='.9')
    execution=dict(row,execId='half-native',execType='Trade',execTime='2100',execQty='.5',execPrice='.9',execFee='.001')
    reader=Reader(row,[execution])
    # Isolate the bound native query; parent terminal order was already proved.
    j.snapshot
    b=MicroAccountBridge(j,reader,clock=lambda:2200)
    b._reconcile_one(native)
    assert j.snapshot()['exits'][native['link']]['quantity']=='0.5'
    assert j.snapshot()['exits'][native['link']]['terminal']
    assert j.snapshot()['held'][s]=='0.5'
