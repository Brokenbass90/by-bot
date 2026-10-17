"""Actual controller + SQLite; external broker I/O is the existing simulator."""
import json
import sqlite3
from pathlib import Path
import pytest

from tests.test_alpaca_dynamic_live_runtime_v1 import setup, case, run
from research_lab.alpaca_dynamic_v1 import canonical


def lineage_case(s):
    assert run(s,apply=True)['status']=='LIVE_PROTECTED'
    m,b,r,p,binding,permit=s
    with sqlite3.connect(binding['source_book']) as db:
        db.execute('CREATE TABLE slots(entry TEXT PRIMARY KEY,payload TEXT)')
        for row in p['inherited_slots']:
            db.execute('INSERT INTO slots VALUES (?,?)',(row['entry_order_id'],canonical(row).decode()))
    return s


def module():
    import research_lab.alpaca_dynamic_live_lineage_v1 as lineage
    return lineage


def test_read_only_preview_does_not_promote_or_send(setup):
    m,b,r,p,binding,permit=lineage_case(setup)
    writes=list(b.writes)
    out=module().reconcile_live_lineage(binding,p,b,now_ms=1791984604000)
    assert out['status']=='LIVE_LINEAGE_PREVIEW'
    assert out['children'][0]['symbol']=='NET'
    assert out['children'][0]['notional_cap']=='49.5'
    assert out['children'][0]['risk_cap']=='2.00'
    assert out['broker_writes']==0 and b.writes==writes
    with sqlite3.connect(binding['source_book']) as db:
        assert db.execute('SELECT count(*) FROM slots').fetchone()[0]==3


def test_apply_is_idempotent_and_keeps_parent_and_source_plan(setup):
    m,b,r,p,binding,permit=lineage_case(setup)
    out=module().reconcile_live_lineage(binding,p,b,now_ms=1791984604000,apply=True)
    again=module().reconcile_live_lineage(binding,p,b,now_ms=1791984605000,apply=True)
    assert out['inserted']==1 and again['inserted']==0
    assert out['children']==again['children']
    assert out['children'][0]['parent_receipt_id']==r['plan']['receipt_id']
    with sqlite3.connect(binding['source_book']) as db:
        assert db.execute('SELECT count(*) FROM slots').fetchone()[0]==4
        assert json.loads(db.execute('SELECT payload FROM intents').fetchone()[0])==r['plan']


@pytest.mark.parametrize('bad',['position_qty','account','ledger_entry','ledger_floor','paper_book','pending_runtime','foreign_position'])
def test_unconfirmed_or_foreign_lifecycle_never_promotes(setup,bad):
    m,b,r,p,binding,permit=lineage_case(setup)
    if bad=='position_qty':b.positions[0]['qty']='.4'
    if bad=='account':b.account['id']='other'
    if bad=='foreign_position':b.positions.append(dict(symbol='SHOP',qty='1',side='long',avg_entry_price='10'))
    if bad.startswith('ledger'):
        path=Path(binding['ledger_path']);ledger=json.loads(path.read_bytes())
        ledger['NET']['entry_order_id' if bad=='ledger_entry' else 'accepted_stop_floor']='other' if bad=='ledger_entry' else 90
        path.write_text(json.dumps(ledger))
    if bad=='paper_book':
        with sqlite3.connect(binding['source_book']) as db:db.execute("UPDATE meta SET value='PAPER' WHERE key='runtime_kind'")
    if bad=='pending_runtime':
        with sqlite3.connect(Path(binding['runtime'])/'live.sqlite') as db:
            item=json.loads(db.execute('SELECT payload FROM intents').fetchone()[0]);item['phase']='RESERVED'
            db.execute('UPDATE intents SET payload=?',(canonical(item).decode(),))
    with pytest.raises(ValueError):module().reconcile_live_lineage(binding,p,b,now_ms=1791984604000,apply=True)
    with sqlite3.connect(binding['source_book']) as db:assert db.execute('SELECT count(*) FROM slots').fetchone()[0]==3
