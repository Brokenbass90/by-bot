"""Session recovery cannot create an entry or borrow legacy PAPER authority."""
import json
import sqlite3
import pytest
from scripts import run_alpaca_dynamic_paper as cli
from test_alpaca_dynamic_paper import policy, plan


def guard():
    from scripts import run_alpaca_paper_session_guard as module
    return module


def test_guard_client_refuses_buy_even_if_recovery_code_requests_it():
    client = guard().MaintenanceClient('unused', 'unused')
    with pytest.raises(ValueError, match='GUARD_CANNOT_SUBMIT_ENTRY'):
        client._request('POST', '/v2/orders', {'side':'buy'})


def test_absent_dispatch_has_no_broker_call(tmp_path):
    class NoBroker:
        def __getattr__(self, name):
            raise AssertionError('no broker calls without dispatch')
    module = guard()
    assert module.guard_once({}, tmp_path, {}, NoBroker(), 1791812100001)['status'] == 'PAPER_NO_ENTRY'


def test_guard_waits_for_dispatch_from_open_instead_of_exiting_or_waiting_five_minutes(tmp_path):
    class NoBroker:
        def __getattr__(self, name):raise AssertionError('no broker without dispatch')
    r=guard().guard_once({},tmp_path,{},NoBroker(),1791811800001)
    assert r['status']=='PAPER_WAITING_FOR_DISPATCH'


def test_reserved_but_not_invoked_never_starts_an_entry(tmp_path):
    from research_lab.alpaca_dynamic_v1 import digest
    value = {'value':{'receipt_id':'uninvoked'}, 'sha256':'unused'}
    value['sha256'] = digest(value['value'])
    (tmp_path/'reserve.json').write_text(json.dumps({'value':value,'sha256':digest(value)}))
    class NoBroker:
        def __getattr__(self, name):raise AssertionError('no broker calls')
    assert guard().guard_once({}, tmp_path, {}, NoBroker(), 1791812100001)['reason'] == 'NO_ADAPTER_INVOKED'


def test_missing_paper_intent_cannot_call_recovery(tmp_path, monkeypatch):
    module = guard()
    from research_lab.alpaca_dynamic_v1 import digest
    plan = {'receipt_id':'x', 'symbol':'NET', 'session':'2026-10-12'}
    def save(name, value):
        (tmp_path/name).write_text(json.dumps({'value':value,'sha256':digest(value)}))
    save('reserve.json', {'value':plan})
    save('invoking_adapter.json', {'parent_receipt_id':'x','plan_sha256':digest(plan)})
    runtime=tmp_path/'paper';runtime.mkdir()
    with sqlite3.connect(runtime/'paper.sqlite') as db:db.execute('CREATE TABLE intents(id TEXT,payload TEXT)')
    monkeypatch.setattr(module,'require_source_plan',lambda path, p:p)
    monkeypatch.setattr(module,'execute_paper',lambda *a,**k:pytest.fail('entry recovery without persisted intent'))
    r=module.guard_once({'source_book':'unused','paper_runtime':str(runtime),'paper_account':'paper'},tmp_path,{},object(),1791812100001)
    assert r['reason']=='NO_PERSISTED_PAPER_INTENT_NO_ENTRY'


def test_guard_recovers_accepted_lost_buy_during_window_without_second_entry(tmp_path, plan, policy):
    from research_lab.alpaca_dynamic_paper import execute_paper, CORE
    from research_lab.alpaca_dynamic_v1 import digest
    from test_alpaca_dynamic_paper_maintenance import DayBroker
    module=guard();now=1791811801000
    plan.update(session='2026-10-12',prepared_ms=now)
    plan['receipt_id']=digest({k:plan[k] for k in CORE});plan['client_order_id']='dyn1-'+plan['receipt_id'][:32]
    class LostBuy(DayBroker):
        def __init__(self):super().__init__();self.sent=False
        def get_clock(self):return {'is_open':True,'timestamp':'2026-10-12T13:30:01Z'}
        def _request(self,method,path,payload):
            assert not self.sent,'second entry is forbidden'
            order=super()._request(method,path,payload)
            self.orders[payload['client_order_id']]['filled_at']='2026-10-12T13:30:02Z'
            self.sent=True;raise TimeoutError('accepted buy response lost')
    b=LostBuy();runtime=tmp_path/'paper'
    assert execute_paper(plan,policy,b,b.account_id,runtime,now,send=True)['status']=='BLOCKED_EXECUTION'
    source=tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE intents(entry TEXT,payload TEXT)')
        db.execute('INSERT INTO intents VALUES (?,?)',(plan['slot_entry_order_id'],json.dumps(plan)))
    opening=tmp_path/'opening';opening.mkdir()
    for name,value in [('reserve.json',{'value':plan}),('invoking_adapter.json',{'parent_receipt_id':plan['receipt_id'],'plan_sha256':digest(plan)})]:
        (opening/name).write_text(json.dumps({'value':value,'sha256':digest(value)}))
    packet={'source_book':str(source),'paper_runtime':str(runtime),'paper_account':b.account_id}
    recovered=module.guard_once(packet,opening,policy,b,now+3000)
    assert recovered['status']=='PAPER_PROTECTED'
    assert len([w for w in b.writes if w.get('side')=='buy'])==1
    assert b.positions[0]['symbol']=='OLD'
    writes=list(b.writes)
    assert module.guard_once(packet,opening,policy,b,now+4000)['status']=='PAPER_PROTECTED' and b.writes==writes
