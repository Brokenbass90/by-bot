"""Safety counterexamples for the prospective orders-OFF replacement book."""
import copy
import importlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
NOW=1791379801000

@pytest.fixture
def api():
    try:return importlib.import_module('research_lab.alpaca_dynamic_v1')
    except ImportError:return None

@pytest.fixture
def policy():return json.loads((ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_text())

@pytest.fixture
def calendar(policy):return copy.deepcopy(policy['calendar_sessions'])

@pytest.fixture
def snapshot(policy):
    slots=policy['inherited_slots'];amd=next(s for s in slots if s['symbol']=='AMD')
    return {'account_id':policy['account_id'],'observed_ms':NOW,'source_sha256':'a'*64,
        'single_owner_verified':True,'cash_finality_verified':True,'cash_usd':'200',
        'liability_reserve_usd':'0.02','fee_rate':'0.001','positions':[{'symbol':'CRWD','qty':'0.469970151','market_value':'120'},{'symbol':'META','qty':'0.141939508','market_value':'80'}],
        'open_orders':[], 'exits':[{'entry_order_id':amd['entry_order_id'],'orders':[{'id':'amd-exit','symbol':'AMD','side':'sell','status':'filled','filled_qty':amd['qty'],'filled_avg_price':'622.312','filled_ms':1791200000000}]}],
        'blocked_symbols':['AMD'], 'gates':{'NET':{'earnings':True,'concentration':True,'symbol':True,'protection':True}},
        'quotes':{'NET':{'ask':'100','received_ms':NOW,'qty_step':'0.000000001','min_qty':'0.000000001','min_notional':'1','tradable':True,'fractionable':True}}}

@pytest.fixture
def ranking(policy):
    return {'policy_sha256':None,'window_ms':1791379800000,'signal_session':'2026-10-06','input_sha256':'b'*64,'source_available_ms':NOW,
        'selector_source_hashes':copy.deepcopy(policy['selector_source_hashes']), 'gate_ok':True,'picks':[{'symbol':'NET','signal_close':100,'stop_price':96,'atr20':2,'rawscore':0.5}], 'blocked_symbols':['AMD','CRWD','META']}

@pytest.fixture
def book(api,policy,ranking,calendar,tmp_path):
    if api is None:return None
    b=api.DynamicBook(tmp_path/'book.sqlite',policy);ranking['policy_sha256']=api.digest(policy);b.seal_ranking(ranking,calendar,NOW);return b


def test_one_confirmed_exit_proposes_one_bounded_entry_with_full_qty_protection(book,snapshot,calendar,policy):
    assert book is not None,'prospective replacement implementation is missing'
    r=book.propose(snapshot,calendar,NOW)
    assert r['status']=='RESERVED_ORDERS_OFF' and r['money_authority'] is False
    assert r['symbol']=='NET' and r['stop_price']=='96.00' and r['protection_tif']=='day'
    assert r['qty']=='1.136099997'  # old AMD entry notional /100, floored to9dp
    assert r['slot_entry_order_id']==next(s['entry_order_id'] for s in policy['inherited_slots'] if s['symbol']=='AMD')


def test_zero_commission_still_deducts_source_bound_regulatory_reserve_before_sizing(book,snapshot,calendar):
    from decimal import Decimal
    from reports.evidence.alpaca_b3_gate_closure_20261008.fee_reserve_input import prepare_entry_cost_input
    cost=prepare_entry_cost_input('1','0',ROOT/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json')
    snapshot.update(cash_usd='100',fee_rate=cost['fee_rate'],liability_reserve_usd=cost['liability_reserve_usd'])
    receipt=book.propose(snapshot,calendar,NOW)
    assert receipt['status']=='RESERVED_ORDERS_OFF'
    assert receipt['fee_rate']=='0' and Decimal(receipt['qty'])==Decimal('0.9999')
    assert Decimal(receipt['funding_limit_usd'])+Decimal(cost['liability_reserve_usd'])==Decimal('100')
    assert receipt['orders_allowed'] is False  # numerical/source rehearsal is not broker readiness


def test_price_change_after_restart_cannot_reprice_or_issue_another_intent(book,snapshot,calendar,api,policy):
    first=book.propose(snapshot,calendar,NOW);snapshot['quotes']['NET']['ask']='120'
    restarted=api.DynamicBook(book.path,policy)
    assert restarted.propose(snapshot,calendar,NOW+1000)==first
    assert restarted.intent_count()==1


@pytest.mark.parametrize('field,value', [('filled_qty','0.1'),('status','partially_filled'),('filled_ms',NOW+1),('symbol','META'),('side','buy')])
def test_partial_pending_future_or_wrong_exit_does_not_free_slot(book,snapshot,calendar,field,value):
    snapshot['exits'][0]['orders'][0][field]=value
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_CONFIRMED_VACANCY'
    assert book.intent_count()==0


def test_flat_position_without_owned_terminal_exit_does_not_create_a_fourth_slot(book,snapshot,calendar):
    snapshot['exits']=[]
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_CONFIRMED_VACANCY'
    assert book.intent_count()==0


def test_late_open_order_or_remaining_position_prevents_replacement(book,snapshot,calendar):
    snapshot['open_orders']=[{'symbol':'AMD','side':'sell'}]
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_CONFIRMED_VACANCY'
    snapshot['open_orders']=[];snapshot['positions'].append({'symbol':'AMD','qty':'0.01','market_value':'6'})
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_CONFIRMED_VACANCY'


@pytest.mark.parametrize('gate',['earnings','concentration','symbol','protection'])
def test_missing_or_rejected_safety_gate_keeps_cash(book,snapshot,calendar,gate):
    snapshot['gates']['NET'].pop(gate)
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_ELIGIBLE_CANDIDATE'
    assert book.intent_count()==0


@pytest.mark.parametrize('change',[{'cash_finality_verified':False},{'single_owner_verified':False},{'account_id':'other'},{'observed_ms':NOW+1},{'fee_rate':'NaN'},{'liability_reserve_usd':'-1'}])
def test_unknown_cash_owner_future_or_nonfinite_costs_fail_closed(book,snapshot,calendar,change):
    snapshot.update(change)
    assert book.propose(snapshot,calendar,NOW)['status']=='BLOCKED_DATA'
    assert book.intent_count()==0


def test_held_cooldown_name_and_untradeable_minimum_cannot_be_bought(book,snapshot,calendar):
    snapshot['blocked_symbols'].append('NET')
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_ELIGIBLE_CANDIDATE'
    snapshot['blocked_symbols'].remove('NET');snapshot['quotes']['NET']['min_notional']='150'
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_ELIGIBLE_CANDIDATE'


def test_marked_gross_and_cost_liability_bound_quantity_without_upscaling_survivors(book,snapshot,calendar):
    snapshot['positions'][0]['market_value']='250';snapshot['positions'][1]['market_value']='80'
    before=copy.deepcopy(snapshot['positions']);snapshot['cash_usd']='5';snapshot['liability_reserve_usd']='1'
    r=book.propose(snapshot,calendar,NOW)
    assert r['qty']=='0.039960039'  # $4 usable cash /$100.10 all-in cost
    assert snapshot['positions']==before


def test_sealed_ranking_cannot_change_reference_stop(book,snapshot,calendar,ranking):
    ranking['picks'][0]['stop_price']=80;ranking['input_sha256']='c'*64
    # A different ranking for the sealed window must be rejected, never overwrite.
    with pytest.raises(ValueError,match='RANKING_CONFLICT'):book.seal_ranking(ranking,calendar,NOW)
    assert book.intent_count()==0


def test_no_late_selection_or_implicit_daily_ranking_refresh(book,snapshot,calendar):
    assert book.propose(snapshot,calendar,NOW+300001)['status']=='NOT_SELECTION_WINDOW'
    next_day=1791466201000;snapshot['observed_ms']=next_day;snapshot['quotes']['NET']['received_ms']=next_day
    r=book.propose(snapshot,calendar,next_day)
    assert r['status']=='RESERVED_ORDERS_OFF'  # same frozen weekly list, first unused vacancy
    monday=1791811801000;snapshot['observed_ms']=monday
    assert book.propose(snapshot,calendar,monday)['status']=='BLOCKED_DATA'


def test_policy_change_on_restart_cannot_increase_risk_or_cap(book,policy,api):
    policy['capital_usd']='1000'
    with pytest.raises(ValueError):api.DynamicBook(book.path,policy)


def test_ranking_cannot_precede_epoch_or_use_future_source(book,ranking,calendar):
    ranking['window_ms']=1791293400000
    with pytest.raises(ValueError):book.seal_ranking(ranking,calendar,NOW)
    ranking['window_ms']=1791379800000;ranking['source_available_ms']=NOW+1
    with pytest.raises(ValueError):book.seal_ranking(ranking,calendar,NOW)


def test_exit_from_an_earlier_lifecycle_and_negative_mark_cannot_release_risk(book,snapshot,calendar,policy):
    snapshot['exits'][0]['orders'][0]['filled_ms']=1
    assert book.propose(snapshot,calendar,NOW)['status']=='NO_CONFIRMED_VACANCY'
    snapshot['exits'][0]['orders'][0]['filled_ms']=1791200000000
    snapshot['positions'][0]['market_value']='-10'
    assert book.propose(snapshot,calendar,NOW)['status']=='BLOCKED_DATA'


def test_sealing_on_thursday_cannot_secretly_refresh_ranking_daily(book,ranking,calendar):
    ranking['window_ms']=1791466200000;ranking['signal_session']='2026-10-07'
    with pytest.raises(ValueError):book.seal_ranking(ranking,calendar,1791466201000)


def test_paper_fill_requires_full_protection_and_one_child_per_parent(book,snapshot,calendar,policy):
    plan=book.propose(snapshot,calendar,NOW)
    fill={'evidence_kind':'PAPER_SIMULATED','account_id':policy['account_id'],'symbol':'NET','entry_status':'filled','entry_order_id':'paper-net',
        'qty':plan['qty'],'price':'100','stop_qty':plan['qty'],'stop_price':'96','stop_status':'new','filled_ms':NOW+2000}
    assert book.register_paper_fill(plan['receipt_id'],fill)['symbol']=='NET'
    assert book.register_paper_fill(plan['receipt_id'],fill)['symbol']=='NET'
    fill['entry_order_id']='another-paper-net'
    with pytest.raises(ValueError):book.register_paper_fill(plan['receipt_id'],fill)


def test_unprotected_paper_partial_fill_cannot_create_next_owned_slot(book,snapshot,calendar,policy):
    plan=book.propose(snapshot,calendar,NOW)
    fill={'evidence_kind':'PAPER_SIMULATED','account_id':policy['account_id'],'symbol':'NET','entry_status':'filled','entry_order_id':'paper-net',
        'qty':'0.5','price':'100','stop_qty':'0.4','stop_price':'96','stop_status':'new','filled_ms':NOW+2000}
    with pytest.raises(ValueError):book.register_paper_fill(plan['receipt_id'],fill)


def test_replacement_full_exit_can_free_next_slot_but_cooldown_preserves_old_name(book,snapshot,calendar,ranking,policy):
    plan=book.propose(snapshot,calendar,NOW)
    fill={'evidence_kind':'PAPER_SIMULATED','account_id':policy['account_id'],'symbol':'NET','entry_status':'filled','entry_order_id':'paper-net',
        'qty':plan['qty'],'price':'100','stop_qty':plan['qty'],'stop_price':'96','stop_status':'new','filled_ms':NOW+2000}
    book.register_paper_fill(plan['receipt_id'],fill)
    t=1791466201000;snapshot['observed_ms']=t;snapshot['exits']=[{'entry_order_id':'paper-net','orders':[{'id':'net-exit','symbol':'NET','side':'sell','status':'filled','filled_qty':plan['qty'],'filled_avg_price':'104','filled_ms':t-10000}]}]
    assert book.propose(snapshot,calendar,t)['status']=='NO_ELIGIBLE_CANDIDATE'  # only NET in frozen weekly list, cannot reenter it


def test_two_independent_readers_racing_for_same_vacancy_emit_one_persisted_intent(book,snapshot,calendar,api,policy):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as ex:
        results=list(ex.map(lambda _:api.DynamicBook(book.path,policy).propose(snapshot,calendar,NOW),range(2)))
    assert results[0]==results[1] and book.intent_count()==1


def test_paper_price_slippage_cannot_exceed_cash_or_gross_allowance(book,snapshot,calendar,policy):
    snapshot['cash_usd']='5';snapshot['liability_reserve_usd']='1'
    plan=book.propose(snapshot,calendar,NOW)
    fill={'evidence_kind':'PAPER_SIMULATED','account_id':policy['account_id'],'symbol':'NET','entry_status':'filled','entry_order_id':'overbudget',
        'qty':plan['qty'],'price':'200','stop_qty':plan['qty'],'stop_price':'196','stop_status':'new','filled_ms':NOW+2000}
    with pytest.raises(ValueError,match='FILL_EXCEEDS_PLAN_BUDGET'):book.register_paper_fill(plan['receipt_id'],fill)


def test_unresolved_previous_intent_blocks_independent_next_day_reservation(book,snapshot,calendar,policy):
    first=book.propose(snapshot,calendar,NOW)
    t=1791466201000;snapshot['observed_ms']=t;snapshot['quotes']['NET']['received_ms']=t
    crwd=next(s for s in policy['inherited_slots'] if s['symbol']=='CRWD')
    snapshot['positions']=[p for p in snapshot['positions'] if p['symbol']!='CRWD']
    snapshot['exits'].append({'entry_order_id':crwd['entry_order_id'],'orders':[{'id':'crwd-exit','symbol':'CRWD','side':'sell','status':'filled','filled_qty':crwd['qty'],'filled_avg_price':'280','filled_ms':t-10000}]})
    assert book.propose(snapshot,calendar,t)['status']=='PENDING_RESERVATION'
    assert book.intent_count()==1


def test_selector_hash_omission_or_drift_cannot_be_sealed(book,ranking,calendar):
    ranking.pop('selector_source_hashes',None)
    with pytest.raises(ValueError,match='SELECTOR_SOURCE_CONFLICT'):book.seal_ranking(ranking,calendar,NOW)


def test_incomplete_calendar_cannot_turn_thursday_into_weekly_refresh(book,ranking):
    start=1792071000000  # October15 regular open
    rows=[{'session':'2026-10-09','open_ms':1791552600000,'close_ms':1791576000000},
          {'session':'2026-10-15','open_ms':start,'close_ms':start+23400000}]
    ranking.update(window_ms=start,signal_session='2026-10-09',source_available_ms=start)
    with pytest.raises(ValueError,match='CALENDAR_SOURCE_CONFLICT'):book.seal_ranking(ranking,rows,start+1000)

@pytest.fixture
def causal_bundle(policy,snapshot):
    end=date(2026,10,6);days=[];d=end
    while len(days)<300:
        if d.weekday()<5:days.append(d)
        d-=timedelta(days=1)
    days.reverse();history={}
    for symbol in policy['universe']:
        rows=[]
        for i,d in enumerate(days):
            close=100*(1.004 if symbol=='NET' else 1.001)**i
            if symbol=='NET' and i==len(days)-1:close*=.96
            rows.append({'session':d.isoformat(),'open':close,'high':close*1.01,'low':close*.99,'close':close})
        history[symbol]=rows
    return {'schema':'ALPACA_DYNAMIC_INPUT_BUNDLE_V1','captured_ms':NOW,'history_available_ms':NOW-1000,'history':history,'snapshot':copy.deepcopy(snapshot)}


def test_frozen_selector_ignores_future_candles_without_an_empty_result(api,policy,calendar,causal_bundle):
    from scripts.run_alpaca_dynamic_v1_orders_off import load_history
    args=[policy,calendar,load_history(causal_bundle['history']),['AMD','CRWD','META'],'d'*64,NOW-1000,NOW]
    first=api.build_ranking(*args)
    assert first['gate_ok'] and first['picks'] and first['picks'][0]['symbol']=='NET'
    causal_bundle['history']['NET'].append({'session':'2026-10-07','open':1000000,'high':1100000,'low':900000,'close':1000000})
    args[2]=load_history(causal_bundle['history']);later=api.build_ranking(*args)
    assert later['picks']==first['picks'] and later['signal_session']=='2026-10-06'


def test_offline_cli_pre_epoch_does_not_create_book_or_claim_first_signal(policy,tmp_path):
    from scripts.run_alpaca_dynamic_v1_orders_off import run
    assert run(policy,tmp_path,None,policy['first_window_ms']-1)['status']=='NOT_DUE'
    assert list(tmp_path.iterdir())==[]


def test_offline_cli_reconstructs_candidate_and_restart_keeps_the_exact_intent(policy,causal_bundle,tmp_path):
    from scripts.run_alpaca_dynamic_v1_orders_off import run
    first=run(policy,tmp_path,causal_bundle,NOW)
    assert first['status']=='RESERVED_ORDERS_OFF' and first['symbol']=='NET'
    assert first['broker_truth_authenticated'] is False and first['live_deployed'] is False
    causal_bundle['snapshot']['quotes']['NET']['ask']='120'
    second=run(policy,tmp_path,causal_bundle,NOW+1000)
    assert second['receipt_id']==first['receipt_id'] and second['qty']==first['qty']


def test_offline_cli_unknown_universe_or_future_input_blocks_without_intent(policy,causal_bundle,tmp_path):
    from scripts.run_alpaca_dynamic_v1_orders_off import run
    causal_bundle['history']['NEW_SCAN']=causal_bundle['history']['NET']
    assert run(policy,tmp_path,causal_bundle,NOW)['reason']=='UNIVERSE_SOURCE_CONFLICT'
    del causal_bundle['history']['NEW_SCAN'];causal_bundle['captured_ms']=NOW+1
    assert run(policy,tmp_path,causal_bundle,NOW)['reason']=='FUTURE_INPUT_BUNDLE'


def test_weekly_refresh_rejects_a_changed_selector_dependency(api,policy,calendar,causal_bundle,monkeypatch):
    from scripts import alpaca_adaptive_paper
    from scripts.run_alpaca_dynamic_v1_orders_off import load_history
    changed=copy.deepcopy(policy['selector_source_hashes']);changed['portfolio_engine']='e'*64
    monkeypatch.setattr(alpaca_adaptive_paper,'_frozen_source_hashes',lambda:changed)
    with pytest.raises(ValueError,match='SELECTOR_SOURCE_CONFLICT'):
        api.build_ranking(policy,calendar,load_history(causal_bundle['history']),[],'d'*64,NOW-1000,NOW)


def test_filled_paper_child_missing_from_account_and_exit_source_blocks_new_slot(book,snapshot,calendar,policy):
    plan=book.propose(snapshot,calendar,NOW)
    fill={'evidence_kind':'PAPER_SIMULATED','account_id':policy['account_id'],'symbol':'NET','entry_status':'filled','entry_order_id':'paper-net',
        'qty':plan['qty'],'price':'100','stop_qty':plan['qty'],'stop_price':'96','stop_status':'new','filled_ms':NOW+2000}
    book.register_paper_fill(plan['receipt_id'],fill)
    t=1791466201000;snapshot['observed_ms']=t;snapshot['quotes']['NET']['received_ms']=t
    crwd=next(s for s in policy['inherited_slots'] if s['symbol']=='CRWD')
    snapshot['positions']=[p for p in snapshot['positions'] if p['symbol']!='CRWD']
    snapshot['exits'].append({'entry_order_id':crwd['entry_order_id'],'orders':[{'id':'crwd-exit','symbol':'CRWD','side':'sell','status':'filled','filled_qty':crwd['qty'],'filled_avg_price':'280','filled_ms':t-10000}]})
    assert book.propose(snapshot,calendar,t)['reason']=='PAPER_POSITION_UNRECONCILED'
