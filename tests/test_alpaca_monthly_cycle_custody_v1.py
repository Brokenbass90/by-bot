import json
import sqlite3
import pytest
from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager,publish
from research_lab.alpaca_dynamic_v1 import canonical
from test_alpaca_monthly_native_binding_v1 import setup,ticket


def wired(setup,tmp_path):
    old,selection,adapter,io,now=setup
    m=MonthlyManager(tmp_path/'cycle',account_id='fixture',capital='487.42',
        account_lock_path=adapter.lock_path,entry_halt_path=adapter.halt)
    (m.root/'book').mkdir()
    with sqlite3.connect(old.path) as source,sqlite3.connect(m.root/'book/monthly-orders-off.sqlite') as target:source.backup(target)
    return m,m.native(io,base_url=adapter.base_url),selection,io,now


@pytest.mark.parametrize('field',['account','runtime','capital','ledger','reentry'])
@pytest.mark.parametrize('operation',['opening','maintain','finalize'])
def test_native_custody_must_match_full_cycle_before_io(setup,tmp_path,field,operation):
    m,n,s,io,now=wired(setup,tmp_path)
    setattr(n,field,'OTHER_ACCOUNT' if field=='account' else 400. if field=='capital' else tmp_path/'foreign')
    io.get_account=lambda:pytest.fail('custody validation must precede client IO')
    with pytest.raises(ValueError,match='CYCLE_NATIVE_CUSTODY_CONFLICT'):
        if operation=='opening':m.opening(n,{},s['selection_id'],quotes={},now_ms=now,apply=True)
        elif operation=='maintain':m.maintain(n,now_ms=now,apply=True)
        else:m.finalize(n,'unknown',tmp_path/'missing',now_ms=now)


@pytest.mark.parametrize('scope',[[],['UNSELECTED']])
def test_saved_unsubmitted_ticket_does_not_override_current_symbol_scope(setup,tmp_path,scope):
    m,n,s,io,now=wired(setup,tmp_path);t=ticket(setup)
    publish(m.root/'tickets'/(t['client_order_id']+'.json'),t)
    try:m.opening(n,{},s['selection_id'],quotes={},now_ms=now,apply=True,symbols=scope)
    except ValueError:
        assert scope==['UNSELECTED']
    assert io.sent==[] and not n.reentry.exists()


def test_rollback_cannot_ignore_native_fill_before_book_commit(setup,tmp_path):
    from research_lab.alpaca_monthly_release_v1 import rollback_snapshot
    m,n,s,io,now=wired(setup,tmp_path)
    n.runtime.mkdir();n.ledger.write_text(json.dumps({'NET':{'protection_pending':True}}))
    assert rollback_snapshot(m)['owned_positions']==1
