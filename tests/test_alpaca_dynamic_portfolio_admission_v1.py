"""Real LIVE journal/native lifecycle, simulated external broker only."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import pytest
from tests.test_alpaca_dynamic_live_runtime_v1 import setup, case, run, NOW
from research_lab.alpaca_dynamic_v1 import canonical


def protected(s,tmp_path):
    assert run(s,apply=True)['status']=='LIVE_PROTECTED'
    m,b,r,p,binding,permit=s
    next(o for o in b.orders.values() if o['type']=='stop')['submitted_at']='2026-10-14T13:30:02Z'
    path=tmp_path/'existing-binding.json';path.write_bytes(canonical(binding))
    proposed={**binding,'portfolio_bindings':[{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
    return m,b,r,p,proposed,permit


def validate(s):
    m,b,r,p,binding,permit=s
    with sqlite3.connect(Path(binding['runtime'])/'live.sqlite') as db:
        return importlib.import_module('research_lab.alpaca_dynamic_portfolio_admission_v1').check_owned_portfolio(
            db,binding,p,b,positions=b.list_positions(),orders=b.list_orders(status='open',limit=500),
            target_symbol='SHOP',observed_ms=NOW+4000)


def test_existing_owned_full_stop_admitted_without_writes(setup,tmp_path):
    s=protected(setup,tmp_path);before=list(s[1].writes)
    result=validate(s)
    assert result['status']=='OWNED_PORTFOLIO_PROTECTION_PASS'
    assert result['held_symbols']==['NET'] and len(result['stop_order_ids'])==1
    assert s[1].writes==before


@pytest.mark.parametrize('bad',['unbound','binding_hash','account','foreign_position','foreign_order','qty','expired_stop','partial_stop','lower_floor','duplicate_stop','journal','native_entry','changed_entry','missing_position','old_day_stop'])
def test_changed_unprotected_or_foreign_portfolio_fails_before_new_buy(setup,tmp_path,bad):
    s=protected(setup,tmp_path);m,b,r,p,binding,permit=s
    stop=next(o for o in b.orders.values() if o['type']=='stop')
    if bad=='unbound':binding['portfolio_bindings']=[]
    if bad=='binding_hash':Path(binding['portfolio_bindings'][0]['path']).write_text('{}')
    if bad=='account':binding['account_id']='foreign'
    if bad=='foreign_position':b.positions.append(dict(symbol='XOM',qty='1',avg_entry_price='1',market_value='1'))
    if bad=='foreign_order':b.orders['foreign']={**stop,'id':'foreign','client_order_id':'unowned','symbol':'XOM'}
    if bad=='qty':stop['qty']='.4'
    if bad=='expired_stop':stop['status']='expired'
    if bad=='partial_stop':stop.update(status='partially_filled',filled_qty='.1')
    if bad=='lower_floor':stop['stop_price']='94.99'
    if bad=='duplicate_stop':b.orders['duplicate']={**stop,'id':'duplicate'}
    if bad=='missing_position':b.positions=[]
    if bad=='old_day_stop':stop['submitted_at']='2026-10-13T13:30:02Z'
    if bad=='changed_entry':b.orders['order-1']['filled_avg_price']='98'
    if bad=='native_entry':
        path=Path(binding['ledger_path']);ledger=json.loads(path.read_bytes());ledger['NET']['entry_order_id']='foreign';path.write_text(json.dumps(ledger))
    if bad=='journal':
        with sqlite3.connect(Path(binding['runtime'])/'live.sqlite') as db:
            item=json.loads(db.execute('SELECT payload FROM intents').fetchone()[0]);item['phase']='RESERVED'
            db.execute('UPDATE intents SET payload=?',(canonical(item).decode(),))
    before=list(b.writes)
    with pytest.raises((ValueError,KeyError)):validate(s)
    assert b.writes==before


def next_setup(s,tmp_path,session='2026-10-15'):
    from datetime import datetime,timezone
    from tests.test_alpaca_dynamic_live_runtime_v1 import Broker
    from research_lab.alpaca_dynamic_live_intake_v1 import compile_intake
    m,b,old,p,binding,permit=protected(s,tmp_path)
    # Monday-like next opening, not a second first-canary. Same account/runtime.
    now=int(datetime.fromisoformat(session+'T13:30:01+00:00').timestamp()*1000)
    for stop in b.orders.values():
        if stop['type']=='stop':stop['submitted_at']=session+'T13:30:00Z'
    b.positions[0]['market_value']='49.5'
    slot=next(x for x in p['inherited_slots'] if x['symbol']=='META')
    core={k:v for k,v in old['plan'].items() if k not in ('receipt_id','client_order_id','status','money_authority','orders_allowed')}
    core.update(symbol='SHOP',session=session,prepared_ms=now,slot_entry_order_id=slot['entry_order_id'])
    from research_lab.alpaca_dynamic_v1 import digest
    plan={**core,'receipt_id':digest(core),'client_order_id':'dyn1-'+digest(core)[:32],
          'status':'RESERVED_ORDERS_OFF','money_authority':False,'orders_allowed':False}
    scope={**old['scope'],'old_terminal_entry_order_id':slot['entry_order_id'],'old_terminal_qty':slot['qty'],
           'positions_before':1,'gross_before_usd':'49.5','quote_cts_ms':now-1000,'observed_ms':now,
           'plan_sha256':digest(plan),'source_plan_sha256':digest(plan)}
    terminal=Path(tmp_path/'meta-terminal.json');terminal.write_bytes(canonical(dict(
        account_id=p['account_id'],evidence_kind='BROKER_LIVE',entry_order_id=slot['entry_order_id'],qty=slot['qty'],status='TERMINAL_FINAL')))
    sources={**binding['sources'],'old_terminal':dict(path=str(terminal),sha256=hashlib.sha256(terminal.read_bytes()).hexdigest())}
    scope['old_terminal_sha256']=sources['old_terminal']['sha256']
    intake=compile_intake(plan,p,scope,now);assert intake['status']=='LIVE_INTAKE_PREPARED_ORDERS_OFF'
    binding={**binding,'sources':sources,'intake_sha256':intake['intake_sha256']}
    with sqlite3.connect(binding['source_book']) as db:
        db.execute('INSERT INTO intents VALUES (?,?,?)',(plan['slot_entry_order_id'],plan['session'],canonical(plan).decode()))
    permit=Path(tmp_path/'shop-go.json');permit.write_bytes(canonical(dict(
        schema='ALPACA_DYNAMIC_EXACT_OWNER_GO_V1',account_id=p['account_id'],endpoint=b.base_url,
        intake_sha256=intake['intake_sha256'],binding_sha256=digest(binding),
        owner_go_text='GO ALPACA_DYNAMIC_V1 '+intake['intake_sha256'],session=plan['session'])))
    class MultiBroker(Broker):
        def _request(self,method,path,payload=None):
            prior=copy.deepcopy(self.positions)
            row=super()._request(method,path,payload)
            if payload['side']=='buy':
                self.orders[row['id']]['filled_at']=datetime.fromtimestamp((self.clock_ms-1000)/1000,timezone.utc).isoformat()
                self.positions=prior+[dict(symbol=payload['symbol'],side='long',qty=self.fill,avg_entry_price='99',current_price='100',market_value='49.5')]
                row=self.get_order(row['id'])
            return row
    multi=MultiBroker(p['account_id']);multi.__dict__.update(b.__dict__);multi.clock_ms=now+3000
    return m,multi,intake,p,binding,permit,now+3000


def test_next_entry_and_restart_coexist_with_protected_net(setup,tmp_path):
    m,b,intake,p,binding,permit,now=next_setup(setup,tmp_path)
    before=len(b.writes);net=copy.deepcopy(json.loads(Path(binding['ledger_path']).read_bytes())['NET'])
    result=m.run_once(intake=intake,policy=p,binding=binding,client=b,now_ms=now,apply=True,owner_go_path=permit)
    assert result['status']=='LIVE_PROTECTED',result
    assert len(b.writes)==before+2
    assert {x['symbol'] for x in b.positions}=={'NET','SHOP'}
    state=json.loads(Path(binding['ledger_path']).read_bytes())
    assert state['NET']==net and state['SHOP']['entry_selection_policy']=='ALPACA_DYNAMIC_V1'
    again=m.run_once(intake=intake,policy=p,binding=binding,client=b,now_ms=now,apply=True,owner_go_path=permit)
    assert again['status']=='LIVE_PROTECTED' and len(b.writes)==before+2


@pytest.mark.parametrize('bad',['no_portfolio_binding','halt','wrong_go','expired_net_stop'])
def test_next_entry_preserves_existing_guards(setup,tmp_path,bad):
    m,b,intake,p,binding,permit,now=next_setup(setup,tmp_path)
    if bad=='no_portfolio_binding':binding.pop('portfolio_bindings')
    if bad=='halt':Path(binding['halt_path']).write_text('{"halted":true}')
    if bad=='wrong_go':permit.write_text('{}')
    if bad=='expired_net_stop':next(o for o in b.orders.values() if o['type']=='stop')['status']='expired'
    before=len(b.writes)
    out=m.run_once(intake=intake,policy=p,binding=binding,client=b,now_ms=now,apply=True,owner_go_path=permit)
    assert out['status'].startswith('BLOCKED') and len(b.writes)==before
