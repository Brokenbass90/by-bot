"""Existing original weekly planner, source book and compiler; no money I/O."""
import copy
import importlib
import json
import sqlite3
from pathlib import Path
import pytest
from tests.test_alpaca_dynamic_v1 import api,policy,calendar,snapshot,ranking,book,NOW
from research_lab.alpaca_dynamic_v1 import canonical,digest


def monday_case(book,snapshot,ranking,policy):
    with book.db() as db:db.execute("INSERT INTO meta VALUES ('runtime_kind','LIVE_DYNAMIC_SEPARATE')")
    first=book.propose(snapshot,policy['calendar_sessions'],NOW)
    # This source fixture describes an independently proven LIVE child. No
    # PAPER fill API can be used to promote a production lifecycle.
    child=dict(entry_ms=NOW+2000,entry_order_id='owned-net',symbol='NET',qty='1',entry_price='100',
               notional_cap='100',risk_cap='4',parent_receipt_id=first['receipt_id'])
    with book.db() as db:db.execute('INSERT INTO slots VALUES (?,?)',(child['entry_order_id'],canonical(child).decode()))
    now=1792416601000
    s=copy.deepcopy(snapshot);s.update(observed_ms=now,positions=[dict(symbol='NET',qty='1',market_value='100')],open_orders=[])
    meta=next(x for x in policy['inherited_slots'] if x['symbol']=='META')
    s['exits'].append(dict(entry_order_id=meta['entry_order_id'],orders=[dict(id='meta-exit',symbol='META',side='sell',status='filled',filled_qty=meta['qty'],filled_avg_price='700',filled_ms=NOW)]))
    s['gates']={'SHOP':dict(earnings=True,concentration=True,symbol=True,protection=True)}
    s['quotes']={'SHOP':dict(ask='100',received_ms=now,quote_ms=now-1000,qty_step='.000000001',min_qty='.000000001',min_notional='1',tradable=True,fractionable=True)}
    s['source_evidence']={'account':dict(cash='200',non_marginable_buying_power='200')}
    r=copy.deepcopy(ranking);r.update(window_ms=now-1000,signal_session='2026-10-16',source_available_ms=now-86400000)
    r['picks']=[dict(symbol='SHOP',signal_close=100,stop_price=96,atr20=2,rawscore=.5)]
    return now,s,r


def binding(tmp_path,book,policy):
    import hashlib
    from scripts import alpaca_protective_exit_manager as manager
    meta=next(x for x in policy['inherited_slots'] if x['symbol']=='META')
    values={'paper':dict(status='PAPER_EXECUTION_PASS'),
        'authority':dict(single_entry_owner_verified=True,old_monthly_entries_off=True,single_manager_verified=True),
        'old_terminal':dict(entry_order_id=meta['entry_order_id'],qty=meta['qty'],account_id=policy['account_id'],evidence_kind='BROKER_LIVE'),'cost':{}}
    b={'source_book':str(book.path),'endpoint':'https://api.alpaca.markets','sources':{}}
    for name,value in values.items():
        p=tmp_path/(name+'.json');p.write_bytes(canonical(value));b['sources'][name]=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return b


def test_next_preview_uses_frozen_weekly_rules_without_writing_live_book(book,snapshot,ranking,policy,tmp_path):
    now,s,r=monday_case(book,snapshot,ranking,policy);b=binding(tmp_path,book,policy)
    before=book.path.read_bytes()
    out=importlib.import_module('research_lab.alpaca_next_entry_assembly_v1').preview_next_snapshot(policy,b,s,now,ranking=r)
    assert out['status']=='NEXT_ENTRY_PREVIEW_ONLY',out
    assert out['intake']['plan']['symbol']=='SHOP'
    assert out['intake']['plan']['slot_entry_order_id']==next(x['entry_order_id'] for x in policy['inherited_slots'] if x['symbol']=='META')
    assert book.path.read_bytes()==before
    assert out['source_book_writes']==out['broker_writes']==0 and out['orders_allowed'] is False


@pytest.mark.parametrize('bad',['before_open','late','stale_ranking','future_quote','missing_child'])
def test_no_synthetic_time_stale_entry_or_unresolved_prior_intent(book,snapshot,ranking,policy,tmp_path,bad):
    now,s,r=monday_case(book,snapshot,ranking,policy);b=binding(tmp_path,book,policy)
    if bad=='before_open':now-=2000
    if bad=='late':now+=300000
    if bad=='stale_ranking':r.update(signal_session='2026-10-15')
    if bad=='future_quote':s['quotes']['SHOP']['quote_ms']=now+1000
    if bad=='missing_child':
        with book.db() as db:db.execute("DELETE FROM slots WHERE entry='owned-net'")
    before=book.path.read_bytes()
    m=importlib.import_module('research_lab.alpaca_next_entry_assembly_v1')
    try:out=m.preview_next_snapshot(policy,b,s,now,ranking=r)
    except ValueError:out={'status':'BLOCKED_DATA'}
    assert out['status']!='NEXT_ENTRY_PREVIEW_ONLY'
    assert book.path.read_bytes()==before
