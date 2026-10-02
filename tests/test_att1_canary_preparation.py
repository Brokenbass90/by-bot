"""Captured NEW commands exercise the real frozen coordinator, without sending."""
import ast
from copy import deepcopy
from pathlib import Path
import sqlite3

import pytest

from bot import att1_coordinator_adapter as a
from bot import att1_canary_preparation as p
from research_lab.att1_lifecycle_session import LifecycleSession
from test_att1_exclusive_reservation import (ledger, ready_for_canary, canary_budget, T, H1, ACCOUNT)

N = T + H1 + 40
SHA = 'a' * 64
SYMBOLS = ('ADAUSDT','BTCUSDT','DOTUSDT','ETHUSDT','LINKUSDT','LTCUSDT','SOLUSDT','SUIUSDT')


def require(name):
    assert hasattr(p, name), 'missing preparation interface: ' + name
    return getattr(p, name)


def handoff_inputs(now=N):
    common = {'account':ACCOUNT,'observed_ms':now,'source_sha256':SHA}
    return {
        'pause_snapshot':{**common,'control':{'exists':True,'scope':'new_entries_only','read_error':None,'paused_sleeves':['att1']}},
        'broker_snapshot':{'schema_id':'att1_broker_snapshot_v1','account':ACCOUNT,'observed_ms':now,
                           'position_count':0,'order_count':0,'flat_no_orders':True,'source_sha256':SHA},
        'old_intent_inventory':{**common,'complete':True,'finality_complete':True,'costs_complete':True,
                               'unresolved':[],'drained_at_ms':T+20},
        'old_watermarks':{**common,'complete':True,'last_old_h1_ms':T,
            'symbols':[{'symbol':s,'latest_h1_ms':T,'cooldown_until_ms':T,'last_terminal_ms':0} for s in SYMBOLS]},
        'now_ms':now,
    }


def entry_inputs():
    v=canary_budget(now=N);attach=v['command_binding']
    base=p.validate_canary_budget_inputs(v['binding'],v['old_budget_evidence'],v['cash_evidence'],now_ms=N)
    bound=require('bind_canary_handoff')(base,**handoff_inputs())
    return attach['profile'],attach['intent'],bound


def prepared(con):
    profile,intent,budget=entry_inputs()
    return require('prepare_new_att1_entry')(con,ACCOUNT,profile=profile,intent=intent,validated_budget=budget,now_ms=N)


def event(kind,offset,**fields):
    return {'schema_id':'att1_lifecycle_event_v1','event_id':kind+str(offset),'kind':kind,
            'exchange_ms':N+offset,'received_ms':N+offset+1,'source_sha256':SHA,**fields}


def opened(tmp_path, *, protect=False):
    profile,intent,_=entry_inputs()
    s=LifecycleSession(tmp_path/'new-captured.jsonl',profile,intent=intent)
    s.apply(event('ENTRY_ACK',1))
    s.apply(event('ENTRY_FILL',2,execution_id='fill1',qty='0.04',price='100',fee_amount='0.004',fee_source_sha256=SHA,liquidity='TAKER'))
    if protect:s.apply(event('PROTECTION_ACK',3,qty='0.04',stop='110'))
    s.apply(event('ENTRY_FINAL',4,status='FILLED'))
    return s


def current_intent(s):
    r=s.refresh()
    return {'intents':r['intents'],'pending_exit':r['pending_exit']}


def management_binding(s):
    # Opaque fingerprint cannot recover the ledger UID used by stable exit IDs.
    return {**s.profile['broker_binding'], 'reservation_account':ACCOUNT}


def test_entry_captures_exact_quantity_and_never_claims_fill(ledger):
    require('prepare_new_att1_entry')
    con,_=ledger;ready_for_canary(con)
    result=prepared(con)
    assert result['orders_allowed'] is False
    assert result['commands'][0]['qty']=='0.04'
    assert result['commands'][0]['reduceOnly'] is False
    assert result['commands'][0]['side']=='Sell'
    assert result['reservation']['order_link_id']==result['commands'][0]['orderLinkId']
    assert result['execution_evidence']=='CAPTURED_COMMAND_NO_BROKER_ORDER'
    assert result['broker_order_id'] is None


@pytest.mark.parametrize('section,field,value', [
    ('old_intent_inventory','unresolved',['late-old-order']),
    ('old_intent_inventory','costs_complete',False), ('old_watermarks','complete',False),
    ('old_watermarks','symbols',[]), ('broker_snapshot','order_count',1),
    ('broker_snapshot','account','foreign'),
])
def test_handoff_rejects_late_fill_unknown_costs_and_missing_watermarks(section,field,value):
    fn=require('validate_canary_handoff');values=handoff_inputs();values[section][field]=value
    with pytest.raises(a.AdapterViolation):fn(**values)


def test_pause_read_error_is_not_a_valid_handoff():
    fn=require('validate_canary_handoff');values=handoff_inputs();values['pause_snapshot']['control']['read_error']='bad file'
    with pytest.raises(a.AdapterViolation):fn(**values)


def test_persisted_command_survives_crash_before_possible_send(ledger):
    require('prepare_new_att1_entry')
    con,path=ledger;ready_for_canary(con);first=prepared(con);con.close()
    with sqlite3.connect(path) as restored:
        again=prepared(restored)
        assert again['status']=='RECOVERY_REQUIRED_LOOKUP_ONLY'
        assert again['commands']==[]
        assert again['order_link_id']==first['reservation']['order_link_id']
        assert restored.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==1


def test_old_and_new_cannot_prepare_same_signal(ledger):
    require('prepare_new_att1_entry')
    con,_=ledger
    with pytest.raises(a.AdapterViolation,match='route'):
        prepared(con)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==0


@pytest.mark.parametrize('minimum', ['min_order_qty','min_notional'])
def test_below_venue_minimum_rejects_without_fallback(ledger,minimum):
    require('prepare_new_att1_entry')
    con,_=ledger;ready_for_canary(con);profile,intent,budget=entry_inputs()
    intent['instrument'][minimum]='10' if minimum=='min_notional' else '1'
    with pytest.raises(a.AdapterViolation,match='BELOW_MIN'):
        p.prepare_new_att1_entry(con,ACCOUNT,profile=profile,intent=intent,validated_budget=budget,now_ms=N)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==0


def test_captured_native_protection_does_not_manufacture_ack(tmp_path):
    fn=require('prepare_new_att1_management');s=opened(tmp_path)
    before=s.journal.read();r=fn(session=s,coordinator_intent=current_intent(s),binding=management_binding(s),now_ms=N+10)
    assert r['orders_allowed'] is False
    c=r['commands'][0]
    assert c['kind']=='NATIVE_PROTECTION' and c['size']=='0.04' and c['stopLoss']=='110'
    assert s.journal.read()==before and s.receipt['protected_qty']=='0'


def test_management_remains_available_during_incident_and_budget_block(tmp_path):
    fn=require('prepare_new_att1_management');s=opened(tmp_path,protect=True)
    # Explicit recovery-gap evidence produces the frozen INCIDENT exit.
    s.apply(event('RECOVERY_GAP',3000,reason='measured-observation-gap'))
    assert s.receipt['incidents']
    r=fn(session=s,coordinator_intent=current_intent(s),binding=management_binding(s),now_ms=N+3002)
    assert any(c['kind']=='EXIT' and c['reduceOnly'] is True and c['qty']=='0.04' for c in r['commands'])
    assert r['orders_allowed'] is False


def test_partial_exit_recovery_uses_same_link_and_exact_dust_remainder(tmp_path):
    fn=require('prepare_new_att1_management');s=opened(tmp_path,protect=True)
    s.apply(event('PRICE',10,bid='87',ask='88'))
    first=fn(session=s,coordinator_intent=current_intent(s),binding=management_binding(s),now_ms=N+12)
    exit1=next(c for c in first['commands'] if c['kind']=='EXIT')
    xid=s.receipt['pending_exit']['exit_order_id']
    s.apply(event('EXIT_ACK',13,exit_order_id=xid))
    s.apply(event('EXIT_FILL',14,exit_order_id=xid,execution_id='exit-partial',qty='0.01',price='88',fee_amount='0.00088',fee_source_sha256=SHA,liquidity='TAKER'))
    restored=LifecycleSession(s.journal.path,s.profile)
    recovery=fn(session=restored,coordinator_intent=current_intent(restored),binding=management_binding(restored),now_ms=N+16)
    assert recovery['status']=='RECOVERY_REQUIRED_LOOKUP_ONLY'
    assert recovery['commands']==[]
    assert recovery['lookup_order_links']==[exit1['orderLinkId']]
    assert restored.receipt['held_qty']=='3/100' and restored.receipt['final_net_r'] is None


def test_stale_or_changed_coordinator_intent_cannot_change_protective_qty(tmp_path):
    fn=require('prepare_new_att1_management');s=opened(tmp_path);intent=current_intent(s)
    intent['intents']['protect_qty']='0.03'
    with pytest.raises(a.AdapterViolation,match='intent'):
        fn(session=s,coordinator_intent=intent,binding=management_binding(s),now_ms=N+10)


def test_monolith_disabled_seam_and_enabled_capture_cannot_call_money_methods(ledger):
    source=Path(__file__).resolve().parents[1]/'smart_pump_reversal_bot.py'
    tree=ast.parse(source.read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_att1_prepare_new_canary']
    assert len(nodes)==1,'missing lazy monolith preparation seam'
    def forbidden(*args,**kwargs):raise AssertionError('money method called')
    namespace={'ATT1_CANARY_PREPARATION_ENABLE':False,'_submit_entry_order_guarded':forbidden,'set_tp_sl_retry':forbidden,'AdapterViolation':a.AdapterViolation}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),namespace)
    assert namespace['_att1_prepare_new_canary'](None)['status']=='PREPARATION_DISABLED'
    namespace['ATT1_CANARY_PREPARATION_ENABLE']=True
    with pytest.raises(a.AdapterViolation):namespace['_att1_prepare_new_canary'](None)
    con,_=ledger;ready_for_canary(con);profile,intent,budget=entry_inputs()
    result=namespace['_att1_prepare_new_canary']({'con':con,'account':ACCOUNT,'profile':profile,'intent':intent,'validated_budget':budget,'now_ms':N})
    assert result['orders_allowed'] is False and result['commands'][0]['qty']=='0.04'


def test_management_requires_same_reservation_account(tmp_path):
    s=opened(tmp_path)
    for binding in (s.profile['broker_binding'],{**management_binding(s),'reservation_account':'foreign'}):
        with pytest.raises(a.AdapterViolation):
            p.prepare_new_att1_management(session=s,coordinator_intent=current_intent(s),binding=binding,now_ms=N+10)


def test_enabled_dispatch_guard_returns_before_old_money_entry():
    import asyncio
    tree=ast.parse((Path(__file__).resolve().parents[1]/'smart_pump_reversal_bot.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='try_att1_entry_async')
    seen=[]
    namespace={'ATT1_CANARY_PREPARATION_ENABLE':True,'_diag_inc':seen.append}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<real-entry-guard>','exec'),namespace)
    asyncio.run(namespace['try_att1_entry_async']('BTCUSDT',100))
    assert seen==['att1_skip_new_preparation_orders_off']


def test_abrupt_process_exit_after_commit_keeps_single_command(ledger):
    import subprocess,sys,os
    con,path=ledger;ready_for_canary(con);con.close()
    code="import sqlite3,os;from test_att1_canary_preparation import prepared;con=sqlite3.connect(os.environ['ATT1_TEST_DB']);prepared(con);os._exit(23)"
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',code],cwd=root,env={**os.environ,'ATT1_TEST_DB':str(path),'PYTHONPATH':str(root/'tests')+os.pathsep+str(root)},capture_output=True)
    assert result.returncode==23,result.stderr.decode()
    with sqlite3.connect(path) as restored:
        result=prepared(restored)
        assert result['commands']==[] and result['status']=='RECOVERY_REQUIRED_LOOKUP_ONLY'
        assert restored.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==1
