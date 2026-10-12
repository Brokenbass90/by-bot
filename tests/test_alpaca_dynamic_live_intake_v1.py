"""Counterexamples at the orders-OFF Dynamic/LIVE intake boundary."""
import copy
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOW = 1791984601000  # Oct14 opening; not an actual broker attempt.


@pytest.fixture
def case():
    from research_lab.alpaca_dynamic_v1 import digest
    policy = json.loads((ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_text())
    slot = next(s for s in policy['inherited_slots'] if s['symbol']=='AMD')
    core = dict(epoch_sha256=digest(policy), slot_entry_order_id=slot['entry_order_id'],
        symbol='NET', qty='.5', reference_ask='100', stop_price='96', risk_distance='4',
        notional_usd='50', modeled_stop_risk_usd='2', protection_qty='.5',
        notional_limit_usd='50', funding_limit_usd='50', fee_rate='0', protection_tif='day',
        ranking_sha256='b'*64, snapshot_sha256='c'*64, source_sha256='d'*64,
        session='2026-10-14', prepared_ms=NOW)
    plan = {**core, 'receipt_id':digest(core), 'client_order_id':'dyn1-'+digest(core)[:32],
        'status':'RESERVED_ORDERS_OFF','money_authority':False,'orders_allowed':False}
    scope = dict(schema='ALPACA_DYNAMIC_LIVE_INTAKE_V1', endpoint='https://api.alpaca.markets',
        account_id=policy['account_id'], policy_sha256=digest(policy), plan_sha256=digest(plan),
        source_book_kind='LIVE_DYNAMIC_SEPARATE', source_plan_sha256=digest(plan),
        paper_lifecycle_status='PAPER_EXECUTION_PASS', paper_lifecycle_sha256='e'*64,
        old_terminal_entry_order_id=slot['entry_order_id'], old_terminal_qty=slot['qty'],
        old_terminal_account_id=policy['account_id'], old_terminal_evidence_kind='BROKER_LIVE',
        old_terminal_sha256='f'*64, single_entry_owner_verified=True,
        old_monthly_entries_off=True, single_manager_verified=True,
        original_shared_lock_sha256='1'*64, native_manager_source_sha256='2'*64,
        compatibility='BASELINE_NATIVE_PROTECTION_DYNAMIC_SELECTION_V1',
        gross_before_usd='0', positions_before=0, session_entries_before=0,
        cash_usd='50.01', nonmarginable_cash_usd='50.01', liability_reserve_usd='.01',
        cost_source_sha256='3'*64, quote_cts_ms=NOW-1000, observed_ms=NOW,
        tradable=True, fractionable=True, earnings=True, concentration=True,
        reentry=True, protection=True, owner_go=False)
    return policy, plan, scope


def api():
    try: return importlib.import_module('research_lab.alpaca_dynamic_live_intake_v1')
    except ImportError: return None


def compiled(case):
    policy, plan, scope = case
    module=api(); assert module is not None, 'isolated Dynamic LIVE intake missing'
    return module.compile_intake(plan,policy,scope,NOW)


def test_compiles_quantity_limit_without_go_or_order_authority(case):
    r=compiled(case)
    assert r['status']=='LIVE_INTAKE_PREPARED_ORDERS_OFF'
    assert r['entry_payload']['qty']=='.5' and r['entry_payload']['type']=='limit'
    assert r['entry_payload']['limit_price']=='100.00'
    assert r['entry_payload']['client_order_id'].startswith('dyl-')
    assert r['orders_allowed'] is False and r['ready_for_live_go'] is False
    assert r['owner_go_present'] is False


@pytest.mark.parametrize('change', [
    {'endpoint':'https://paper-api.alpaca.markets'}, {'account_id':'other'},
    {'source_book_kind':'PAPER'}, {'old_terminal_evidence_kind':'BROKER_PAPER'},
    {'old_terminal_entry_order_id':'paper-validation-exit'}, {'old_terminal_qty':'1'},
    {'paper_lifecycle_status':'ENTRY_PROTECTED_LIFECYCLE_PENDING'},
    {'old_monthly_entries_off':False}, {'single_manager_verified':False},
    {'single_entry_owner_verified':False}, {'native_manager_source_sha256':'bad'},
    {'compatibility':'monthly_v38'}, {'quote_cts_ms':None}, {'quote_cts_ms':NOW+1},
    {'quote_cts_ms':NOW-300001}, {'observed_ms':NOW+1},
    {'liability_reserve_usd':'-.01'}, {'cash_usd':'50'}, {'nonmarginable_cash_usd':'50'},
    {'cost_source_sha256':'bad'}, {'gross_before_usd':'300'}, {'positions_before':4},
    {'session_entries_before':1}, {'earnings':False}, {'protection':False},
])
def test_incompatible_unknown_or_infeasible_sources_block_without_a_payload(case,change):
    case[2].update(change); r=compiled(case)
    assert r['status']=='BLOCKED_DATA' and 'entry_payload' not in r
    assert r['orders_allowed'] is False


def test_changed_plan_cannot_be_accepted_under_old_source_pin(case):
    case[1]['qty']='1'; assert compiled(case)['status']=='BLOCKED_DATA'


def test_owner_go_boolean_cannot_grant_sending_authority(case):
    case[2]['owner_go']=True; r=compiled(case)
    assert r['status']=='LIVE_INTAKE_PREPARED_ORDERS_OFF'
    assert r['orders_allowed'] is False and r['money_authority'] is False


def orders(r,qty='.5'):
    buy={**r['entry_payload'],'id':'live-buy','status':'filled','filled_qty':qty,
        'filled_avg_price':'99','filled_at':'2026-10-14T13:30:02Z'}
    stop=dict(id='live-stop',client_order_id=r['stop_client_order_id'],symbol='NET',
        side='sell',type='stop',qty=qty,filled_qty='0',stop_price='95',
        status='new',time_in_force='day')
    return buy,stop


def test_partial_readback_exports_exact_native_record_with_dynamic_selection_tag(case):
    r=compiled(case); buy,stop=orders(r,'.2')
    out=api().native_handoff(r,buy,stop,observed_ms=NOW+3000)
    assert out['status']=='NATIVE_HANDOFF_PREPARED_ORDERS_OFF'
    native=out['native_record']
    assert native['entry_order_id']=='live-buy' and native['accepted_order_id']=='live-stop'
    assert native['qty']==.2 and native['accepted_stop_floor']==95
    assert native['entry_selection_policy']=='ALPACA_DYNAMIC_V1'
    assert out['orders_allowed'] is False and out['manager_installed'] is False


@pytest.mark.parametrize('target,change', [
    ('buy',{'client_order_id':'dyp-foreign'}),('buy',{'filled_qty':'.6'}),
    ('buy',{'status':'partially_filled'}),('buy',{'filled_avg_price':'101'}),
    ('buy',{'filled_at':'2026-10-13T13:30:00Z'}),
    ('stop',{'status':'rejected'}),('stop',{'status':'partially_filled','filled_qty':'.1'}),
    ('stop',{'qty':'.2'}),('stop',{'stop_price':'94.99'}),
    ('stop',{'client_order_id':'foreign'}),('stop',{'time_in_force':'gtc'}),
])
def test_uncertain_partial_wrong_or_underprotected_sources_never_claim_handoff(case,target,change):
    r=compiled(case); buy,stop=orders(r)
    (buy if target=='buy' else stop).update(change)
    out=api().native_handoff(r,buy,stop,observed_ms=NOW+3000)
    assert out['status']=='BLOCKED_DATA' and 'native_record' not in out


def test_handoff_detects_changed_prepared_entry_payload(case):
    r=compiled(case); buy,stop=orders(r); r['entry_payload']['qty']='1'
    assert api().native_handoff(r,buy,stop,observed_ms=NOW+3000)['status']=='BLOCKED_DATA'


def test_existing_floor_and_hwm_do_not_reset_on_replay(case):
    r=compiled(case); buy,stop=orders(r)
    first=api().native_handoff(r,buy,stop,observed_ms=NOW+3000)['native_record']
    existing={**first,'hwm':110.,'accepted_stop_floor':96.}
    assert api().native_handoff(r,buy,stop,observed_ms=NOW+3000,existing=existing)['status']=='BLOCKED_DATA'
    stop['stop_price']='96'
    native=api().native_handoff(r,buy,stop,observed_ms=NOW+3000,existing=existing)['native_record']
    assert native['hwm']==110. and native['accepted_stop_floor']==96.
    assert api().native_handoff(r,buy,stop,observed_ms=NOW+3000,existing=native)['native_record']==native


def test_new_readback_metadata_cannot_change_once_only_order_ids(case):
    first=compiled(case)
    case[2].update(observed_ms=NOW+1000, cash_usd='51', cost_source_sha256='4'*64)
    second=api().compile_intake(case[1],case[0],case[2],NOW+1000)
    assert first['entry_payload']['client_order_id']==second['entry_payload']['client_order_id']
    assert first['stop_client_order_id']==second['stop_client_order_id']


def test_inconsistent_leaves_qty_cannot_pass_native_float_tolerance(case):
    r=compiled(case); buy,stop=orders(r)
    stop['leaves_qty']='0.499999999'
    assert api().native_handoff(r,buy,stop,observed_ms=NOW+3000)['status']=='BLOCKED_DATA'


@pytest.mark.parametrize('missing', ['entry','stop'])
def test_missing_order_source_is_unknown_instead_of_a_handoff(case,missing):
    r=compiled(case); buy,stop=orders(r)
    if missing=='entry': buy=None
    else: stop=None
    assert api().native_handoff(r,buy,stop,observed_ms=NOW+3000)['status']=='BLOCKED_DATA'


def test_raw_quote_timestamp_may_not_follow_its_capture(case):
    case[2]['observed_ms']=NOW-2000
    assert compiled(case)['status']=='BLOCKED_DATA'


def test_an_already_executed_stop_requires_exit_reconciliation_not_initial_handoff(case):
    r=compiled(case); buy,stop=orders(r)
    stop.update(qty='.6',filled_qty='.1')
    assert api().native_handoff(r,buy,stop,observed_ms=NOW+3000)['status']=='BLOCKED_DATA'
