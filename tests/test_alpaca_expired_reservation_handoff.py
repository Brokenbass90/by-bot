"""Proven non-dispatch retirement is append-only; no strategy/risk changes."""
import copy
import sqlite3
import pytest
from test_alpaca_dynamic_v1 import api,policy,calendar,snapshot,ranking,book,NOW


def proof(api,policy,plan,observed):
    account='paper-selected';identity=api.digest({'parent':plan['receipt_id'],'paper_account':account})
    return {'schema':'ALPACA_EXPIRED_NONDISPATCH_PROOF_V1','policy_sha256':api.digest(policy),
      'receipt_id':plan['receipt_id'],'original_plan_sha256':api.digest(plan),
      'observed_ms':observed,'paper_account_id':'paper-selected','live_account_id':policy['account_id'],
      'live_entry_halted':True,'single_owner_reviewed':True,'entry_client_id_http_status':404,
      'stop_client_id_http_status':404,'symbol_position_absent':True,'symbol_orders_absent':True,
      'entry_client_order_id':'dyp-'+identity[:32],'stop_client_order_id':'dys-'+identity[:32],
      'paper_store_intents':0,'paper_hwm_present':False,'source_sha256':'a'*64,
      'broker_authenticated_by_this_validator':False}


def test_retirement_keeps_original_and_frees_only_the_unfilled_lineage(book,snapshot,calendar,api,policy):
    plan=book.propose(snapshot,calendar,NOW);observed=NOW+300000
    before=book.path.read_bytes()
    assert hasattr(book,'retire_undispatched'),'append-only handoff missing'
    with sqlite3.connect(book.path) as db:original=db.execute('SELECT * FROM intents').fetchall()
    p=proof(api,policy,plan,observed);result=book.retire_undispatched(plan['receipt_id'],p,observed)
    assert result['status']=='EXPIRED_NEVER_DISPATCHED' and result['orders_allowed'] is False
    with sqlite3.connect(book.path) as db:assert db.execute('SELECT * FROM intents').fetchall()==original
    assert book.intent_count()==1 and book.active_intents()==[] and before!=book.path.read_bytes()
    assert book.retire_undispatched(plan['receipt_id'],p,observed+1)==result
    snapshot['observed_ms']=NOW+86400000;snapshot['quotes']['NET']['received_ms']=snapshot['observed_ms']
    second=book.propose(snapshot,calendar,snapshot['observed_ms'])
    assert second['status']=='RESERVED_ORDERS_OFF' and second['receipt_id']!=plan['receipt_id']
    assert second['slot_entry_order_id']==plan['slot_entry_order_id']
    assert book.intent_count()==2 and len(book.active_intents())==1
    assert book.propose(snapshot,calendar,snapshot['observed_ms'])==second


@pytest.mark.parametrize('change',[{'entry_client_id_http_status':200},{'stop_client_id_http_status':None},
  {'paper_store_intents':1},{'paper_hwm_present':True},{'symbol_position_absent':False},
  {'symbol_orders_absent':False},{'single_owner_reviewed':False},{'live_entry_halted':False},
  {'original_plan_sha256':'f'*64},{'source_sha256':'bad'}])
def test_uncertain_or_conflicting_non_dispatch_evidence_cannot_free_slot(book,snapshot,calendar,api,policy,change):
    plan=book.propose(snapshot,calendar,NOW);now=NOW+300000
    assert hasattr(book,'retire_undispatched'),'append-only handoff missing'
    p=proof(api,policy,plan,now);p.update(change)
    with pytest.raises(ValueError):book.retire_undispatched(plan['receipt_id'],p,now)
    assert len(book.active_intents())==1 and book.intent_count()==1


def test_unexpired_or_stale_proof_is_rejected(book,snapshot,calendar,api,policy):
    plan=book.propose(snapshot,calendar,NOW)
    assert hasattr(book,'retire_undispatched'),'append-only handoff missing'
    with pytest.raises(ValueError):book.retire_undispatched(plan['receipt_id'],proof(api,policy,plan,NOW),NOW)
    later=NOW+600001
    with pytest.raises(ValueError):book.retire_undispatched(plan['receipt_id'],proof(api,policy,plan,NOW),later)


def test_retired_intent_cannot_gain_a_synthetic_fill_child(book,snapshot,calendar,api,policy):
    plan=book.propose(snapshot,calendar,NOW);now=NOW+300000
    assert hasattr(book,'retire_undispatched'),'append-only handoff missing'
    book.retire_undispatched(plan['receipt_id'],proof(api,policy,plan,now),now)
    with pytest.raises(ValueError,match='RETIRED_PARENT_INTENT'):
        book.register_paper_fill(plan['receipt_id'],{})


def test_original_schema_without_retirement_tables_remains_active_fail_closed(book,snapshot,calendar,api):
    plan=book.propose(snapshot,calendar,NOW)
    assert hasattr(api.DynamicBook,'active_from_db'),'read-only history projection missing'
    with sqlite3.connect(book.path) as db:
        db.execute('DROP TABLE IF EXISTS intent_retirements');db.execute('DROP TABLE IF EXISTS intent_attempts')
        assert api.DynamicBook.active_from_db(db)==[plan]
