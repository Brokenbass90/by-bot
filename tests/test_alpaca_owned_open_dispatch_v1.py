import importlib
import sqlite3
import json
import pytest
from tests.test_alpaca_next_entry_assembly_v1 import api,policy,calendar,snapshot,ranking,book,monday_case
from tests.test_alpaca_open_dispatch_v2 import Clock
from research_lab.alpaca_dynamic_v1 import digest,canonical


def build(book,snapshot,ranking,policy,tmp_path,bad=None):
    now,s,r=monday_case(book,snapshot,ranking,policy)
    with book.db() as db:
        prior=json.loads(db.execute('SELECT payload FROM intents').fetchone()[0])
        child=json.loads(db.execute("SELECT payload FROM slots WHERE entry='owned-net'").fetchone()[0])
        child['live_intake_sha256']='a'*64
        db.execute("UPDATE slots SET payload=? WHERE entry='owned-net'",(canonical(child).decode(),))
        if bad=='no_child':db.execute("DELETE FROM slots WHERE entry='owned-net'")
    resolved=[dict(plan_sha256=digest(prior),child_entry_order_id=child['entry_order_id'],live_intake_sha256=child['live_intake_sha256'])]
    if bad=='wrong_plan':resolved[0]['plan_sha256']='f'*64
    if bad=='wrong_child':resolved[0]['child_entry_order_id']='other'
    path=tmp_path/'static';path.write_text('source-pinned')
    from research_lab.alpaca_open_dispatch_v2 import STATIC_CHECKS
    checks={k:dict(status='VERIFIED',source_sha256='a'*64) for k in STATIC_CHECKS};checks['reservation_handoff']['status']='CLEAR_OR_REVIEWED'
    cls=importlib.import_module('research_lab.alpaca_owned_open_dispatch_v1').OwnedOpeningDispatcher
    return cls(tmp_path/'dispatch',policy,now-1000,{'static':path},checks,Clock(now-901000),plan_store=book.path,
               resolved_source_plans=resolved)


def test_verified_original_child_does_not_block_new_opening_prepare(book,snapshot,ranking,policy,tmp_path):
    d=build(book,snapshot,ranking,policy,tmp_path)
    assert d.prepare()['status']=='STATIC_PREPARED'
    assert d.ready()['status']=='READY_TO_DISPATCH'


@pytest.mark.parametrize('bad',['no_child','wrong_plan','wrong_child'])
def test_unknown_old_reservations_are_not_ignored(book,snapshot,ranking,policy,tmp_path,bad):
    d=build(book,snapshot,ranking,policy,tmp_path,bad)
    out=d.prepare()
    assert out['status']=='BLOCKED_DATA'
