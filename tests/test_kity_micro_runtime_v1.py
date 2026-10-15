import copy
import json
import itertools
from decimal import Decimal as D
from pathlib import Path

import pytest

from research_lab.kity_execution_micro_runtime_v1 import (
    BASKET, MicroJournal, prepare_micro_plan, assess_micro_readiness, liquidation_value,
)

BOUNDS = json.loads((Path(__file__).resolve().parents[1] /
    'configs/research/kity_execution_micro_owner_bounds_20261015.json').read_text())


def dossier():
    legs = []
    for n, (symbol, side) in enumerate(BASKET):
        legs.append(dict(symbol=symbol, side=side, quantity='1',
            entry_reference_notional='1', entry_book_notional='1',
            rounding_shortfall_fraction='0', draft_entry=dict(category='linear', symbol=symbol,
                side=side, orderType='Limit', timeInForce='IOC', qty='1', price='1',
                positionIdx=0, reduceOnly=False, orderLinkId=f'old-{n}')))
    return dict(private_capture_sha256='a'*64, c2_reconstruction_receipt_sha256='b'*64,
        observed_end_ms=1000, common_clock_at_capture=dict(status='OBSERVED_COMMON_2S_PASS'),
        profiles=[dict(profile='VENUE_FLOOR_DIAGNOSTIC', common_reference_target='1',
            observed_depth_gross='10', legs=legs)])


def plan():
    return prepare_micro_plan(dossier(), BOUNDS)


_ids = itertools.count()


def event(kind, **fields):
    return dict(kind=kind, event_id=kind + '-' + str(next(_ids)), at_ms=2000,
                source_sha256='c'*64, **fields)


def send(j, symbol):
    j.append(event('ENTRY_INTENT', symbol=symbol))


def fill(j, symbol, *, exit=False, qty='1', price='1', fee='.01', xid=None, link=None):
    state = j.snapshot(); order = (list(state['exits'].values())[-1] if exit else state['entries'][symbol])
    return j.append(event('EXIT_FILL' if exit else 'ENTRY_FILL', symbol=symbol,
        order_link_id=link or order['link'], order_id='broker-' + order['link'],
        execution_id=xid or ('fill-' + order['link']), quantity=qty, price=price, fee_usdt=fee))


def terminal(j, symbol, qty='1', *, exit=False, status='Filled'):
    state = j.snapshot(); order = (list(state['exits'].values())[-1] if exit else state['entries'][symbol])
    j.append(event('EXIT_TERMINAL' if exit else 'ENTRY_TERMINAL', symbol=symbol,
        order_link_id=order['link'], order_id='broker-' + order['link'],
        status=status, filled_quantity=qty))


def protect(j, symbol):
    j.append(event('PROTECTION_READBACK', symbol=symbol, quantity=j.snapshot()['held'][symbol],
        stop_id='stop-' + symbol, side='Sell' if dict(BASKET)[symbol]=='Buy' else 'Buy'))


def enter(j, symbol):
    send(j, symbol); fill(j, symbol); terminal(j, symbol); protect(j, symbol)


def exit_leg(j, symbol, *, qty='1', price='1', fee='.01'):
    j.append(event('EXIT_INTENT', symbol=symbol, quantity=qty))
    fill(j, symbol, exit=True, qty=qty, price=price, fee=fee)
    terminal(j, symbol, qty, exit=True)


def flat(j):
    j.append(event('BROKER_SNAPSHOT', positions={s:'0' for s,_ in BASKET}, open_order_links=[]))


def test_exact_owner_bounds_and_ten_leg_research_firewall():
    p = plan()
    assert len(p['legs']) == 10
    assert p['bounds']['max_gross_usdt']=='210'
    assert p['bounds']['max_all_in_loss_usdt']=='15'
    assert p['bounds']['duration_ms']==1800000
    assert p['bounds']['max_rounding_shortfall_fraction']=='0.203'
    assert p['purpose']=='EXECUTION_MICRO_LIVE'
    assert not p['orders_allowed'] and not p['research_evidence_eligible']


@pytest.mark.parametrize('key,value', [('max_gross_usdt','211'), ('max_all_in_loss_usdt','16'),
    ('duration_ms',1800001), ('hard_final_loss_cap_required',False)])
def test_bounds_cannot_be_relaxed(key, value):
    b = copy.deepcopy(BOUNDS); b[key] = value
    with pytest.raises(ValueError, match='OWNER_BOUND'):
        prepare_micro_plan(dossier(), b)


def test_no_symbol_omission_or_substitution():
    d = dossier(); d['profiles'][0]['legs'].pop()
    with pytest.raises(ValueError, match='EXACT_TEN'):
        prepare_micro_plan(d, BOUNDS)


def test_rounding_limit_203_percent_is_exact_not_rounded_up():
    d = dossier(); d['profiles'][0]['legs'][0]['rounding_shortfall_fraction']='.20300001'
    with pytest.raises(ValueError, match='ROUNDING'):
        prepare_micro_plan(d, BOUNDS)


def test_saved_gross_over_cap_stays_nonexecutable():
    d=dossier();d['profiles'][0]['observed_depth_gross']='210.266660'
    p=prepare_micro_plan(d,BOUNDS)
    assert 'GROSS_CAP_EXCEEDED' in p['blocked_reasons']
    assert p['orders_allowed'] is False


def test_hard_loss_guarantee_cannot_be_self_attested_into_a_stop_trigger():
    r=assess_micro_readiness(plan(),dict(marginMode='REGULAR_MARGIN', guaranteed_loss='15', owner_go=True))
    assert r['status']=='BLOCKED_EXECUTION'
    assert 'HARD_FINAL_LOSS_CAP_NOT_ENFORCEABLE_ON_PERPETUALS' in r['reasons']
    assert not r['orders_allowed']


def test_restart_after_persisted_send_intent_never_proposes_entry_resend(tmp_path):
    path=tmp_path/'journal.sqlite';j=MicroJournal(path,plan());send(j,BASKET[0][0]);j.close()
    j=MicroJournal(path,plan());actions=j.actions(2100)
    assert actions[0]['kind']=='RECONCILE'
    assert not any(a['kind']=='ENTRY' for a in actions)
    assert j.snapshot()['deadline_ms']==1802000


def test_same_event_is_idempotent_and_conflicting_duplicate_rejected(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());e=event('ENTRY_INTENT',symbol=BASKET[0][0])
    assert j.append(e) is True and j.append(e) is False
    e2=dict(e,at_ms=2001)
    with pytest.raises(ValueError,match='EVENT_CONFLICT'):j.append(e2)


def test_execution_deduplication_under_a_new_event_id(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,xid='same')
    state=j.snapshot();order=state['entries'][s]
    j.append(event('ENTRY_FILL',symbol=s,order_link_id=order['link'],order_id='broker-'+order['link'],
        execution_id='same',quantity='1',price='1',fee_usdt='.01',event_alias='new-envelope'))
    assert j.snapshot()['held'][s]=='1'
    assert D(j.snapshot()['fees_usdt'])==D('.01')


def test_foreign_order_link_does_not_adopt_position(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s)
    with pytest.raises(ValueError,match='OWNERSHIP'):fill(j,s,link='foreign')
    assert j.snapshot()['held'][s]=='0'


def test_partial_entry_aborts_remaining_basket_and_owns_only_actual_fills(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,qty='.4')
    terminal(j,s,'.4',status='Cancelled')
    assert j.actions(2100)[0]['kind']=='EXIT'
    assert D(j.actions(2100)[0]['quantity'])==D('.4')
    with pytest.raises(ValueError,match='ENTRY_BLOCKED'):send(j,BASKET[1][0])


def test_terminal_before_execution_rows_requires_reconciliation(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);terminal(j,s)
    assert j.actions(2100)[0]['kind']=='RECONCILE'
    with pytest.raises(ValueError,match='ENTRY_RECONCILIATION'):j.append(event('EXIT_INTENT',symbol=s,quantity='1'))


def test_unknown_dispatch_is_persistent_and_not_resubmitted(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s)
    j.append(event('DISPATCH_UNKNOWN',symbol=s,order_link_id=j.snapshot()['entries'][s]['link']))
    assert j.actions(2100)[0]['kind']=='RECONCILE'
    with pytest.raises(ValueError,match='ENTRY_BLOCKED'):send(j,BASKET[1][0])


def test_missing_fees_preserve_fill_and_block_money_metrics(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,fee=None)
    assert j.snapshot()['held'][s]=='1'
    assert j.snapshot()['fee_unknown_execution_ids']
    result=liquidation_value(j.snapshot(),{s:{'bid':'1','ask':'1','exit_taker_fee':'.001'}},funding_reserve_usdt='0')
    assert result['net_usdt'] is None and result['action']=='UNWIND_DATA_UNKNOWN'


def test_all_in_loss_uses_actual_fill_slippage_once(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,price='1.02',fee='.01')
    result=liquidation_value(j.snapshot(),{s:{'bids':[['1','1']], 'asks':[['1.01','1']], 'exit_taker_fee':'.01'}},funding_reserve_usdt='.02')
    assert D(result['net_usdt'])==D('-.06')
    assert result['slippage_already_in_fill_and_liquidation_prices'] is True


def test_15_dollar_threshold_triggers_unwind_without_claiming_guarantee(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,price='20',fee='0')
    result=liquidation_value(j.snapshot(),{s:{'bids':[['5','1']], 'asks':[['5.1','1']], 'exit_taker_fee':'0'}},funding_reserve_usdt='0')
    assert result['action']=='UNWIND_LOSS_LIMIT' and result['guaranteed_final_loss_cap'] is False


def test_30_minutes_not_reset_by_restart_or_late_fills(tmp_path):
    path=tmp_path/'j.sqlite';j=MicroJournal(path,plan());s=BASKET[0][0];enter(j,s);j.close()
    j=MicroJournal(path,plan());assert j.actions(1801999)[0]['kind']=='ENTRY'
    actions=j.actions(1802000);assert actions[0]['kind']=='EXIT'
    assert j.snapshot()['deadline_ms']==1802000


def test_exit_cannot_exceed_held_or_reuse_entry_side(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];enter(j,s)
    with pytest.raises(ValueError,match='EXIT_QUANTITY'):j.append(event('EXIT_INTENT',symbol=s,quantity='2'))
    action=j.actions(1802000)[0]
    assert action['request']['reduceOnly'] is True and action['request']['side']=='Sell'


def test_partial_exit_retains_residual_and_disallows_uncertain_resend(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];enter(j,s)
    j.append(event('UNWIND',reason='test'));j.append(event('EXIT_INTENT',symbol=s,quantity='1'))
    fill(j,s,exit=True,qty='.4');assert j.snapshot()['held'][s]=='0.6'
    assert j.actions(2100)[0]['kind']=='RECONCILE'
    terminal(j,s,'.4',exit=True,status='Cancelled')
    assert j.actions(2100)[0]['quantity']=='0.6'


def test_all_ten_legs_entry_protection_exit_and_final_accounting(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan())
    for s,_ in BASKET:enter(j,s)
    assert j.actions(2100)[0]['kind']=='MONITOR'
    j.append(event('UNWIND',reason='duration'))
    for s,_ in BASKET:exit_leg(j,s)
    flat(j)
    j.append(event('FINALITY',funding_complete=True,net_cash_usdt='-.20'))
    assert j.snapshot()['phase']=='TERMINAL'
    assert j.snapshot()['terminal_net_usdt']=='-0.20'
    assert j.snapshot()['research_evidence_eligible'] is False
    assert j.snapshot()['orders_allowed'] is False
    assert j.actions(1803000)==[]
    with pytest.raises(ValueError,match='ENTRY_BLOCKED'):send(j,BASKET[0][0])


def test_finality_requires_broker_flat_costs_and_no_pending_order(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];enter(j,s)
    with pytest.raises(ValueError,match='FINALITY'):j.append(event('FINALITY',funding_complete=True,net_cash_usdt='0'))
    exit_leg(j,s);flat(j)
    with pytest.raises(ValueError,match='FUNDING'):j.append(event('FINALITY',funding_complete=False,net_cash_usdt='-.02'))
    with pytest.raises(ValueError,match='CASH'):j.append(event('FINALITY',funding_complete=True,net_cash_usdt='0'))


def test_foreign_overlap_snapshot_is_not_flat_or_authority_to_flatten(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());positions={s:'0' for s,_ in BASKET};positions[BASKET[0][0]]='2'
    j.append(event('BROKER_SNAPSHOT',positions=positions,open_order_links=['foreign']))
    assert j.actions(2100)[0]['kind']=='OWNERSHIP_CONFLICT'
    assert not j.snapshot()['broker_flat_proven']


def test_journal_plan_conflict_and_corrupt_hash_chain(tmp_path):
    path=tmp_path/'j.sqlite';j=MicroJournal(path,plan());send(j,BASKET[0][0]);j.close()
    p=plan();p['plan_id']='f'*64
    with pytest.raises(ValueError,match='PLAN'):MicroJournal(path,p)
    import sqlite3
    with sqlite3.connect(path) as c:c.execute("UPDATE events SET hash='broken'")
    with pytest.raises(ValueError,match='JOURNAL'):MicroJournal(path,plan())


def test_unknown_leg_does_not_block_unwind_of_other_reconciled_owned_legs(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());enter(j,BASKET[0][0]);send(j,BASKET[1][0])
    j.append(event('DISPATCH_UNKNOWN',symbol=BASKET[1][0],order_link_id=j.snapshot()['entries'][BASKET[1][0]]['link']))
    actions=j.actions(2100)
    assert any(a['kind']=='EXIT' and a['symbol']==BASKET[0][0] for a in actions)
    assert any(a['kind']=='RECONCILE' and a['symbol']==BASKET[1][0] for a in actions)


def test_partial_fill_can_get_protection_readback_before_entry_terminal(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,qty='.4')
    assert any(a['kind']=='PROTECTION_READBACK' and a['symbol']==s for a in j.actions(2100))


def test_funding_ids_are_scoped_by_symbol(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan())
    for symbol,_ in BASKET[:2]:
        enter(j,symbol)
        j.append(event('FUNDING_CASH',symbol=symbol,settlement_id='same-time',settlement_ms=2000,cash_usdt='-.01'))
    assert D(j.snapshot()['funding_cash_usdt'])==D('-.02')


def test_money_bounds_cannot_be_forged_by_rehashing_a_modified_plan(tmp_path):
    from bot.kity_m3_orders_off import digest
    p=plan();p['bounds']['max_gross_usdt']='1000';del p['plan_id'];p['plan_id']=digest(p)
    with pytest.raises(ValueError,match='OWNER_BOUND'):MicroJournal(tmp_path/'j.sqlite',p)


def test_rounding_report_must_match_recomputed_reference_weight():
    d=dossier();d['profiles'][0]['legs'][0]['entry_reference_notional']='.7'
    with pytest.raises(ValueError,match='ROUNDING'):prepare_micro_plan(d,BOUNDS)


def test_no_entry_proposal_for_over_cap_plan(tmp_path):
    d=dossier();d['profiles'][0]['observed_depth_gross']='210.266660'
    j=MicroJournal(tmp_path/'j.sqlite',prepare_micro_plan(d,BOUNDS))
    assert j.actions(2100)[0]['kind']=='BLOCKED_PLAN'
    with pytest.raises(ValueError,match='ENTRY_BLOCKED'):send(j,BASKET[0][0])


def test_deadline_observation_is_durable_against_restart_and_clock_rollback(tmp_path):
    path=tmp_path/'j.sqlite';j=MicroJournal(path,plan());enter(j,BASKET[0][0]);j.actions(1802000);j.close()
    j=MicroJournal(path,plan())
    assert j.snapshot()['entry_blocked'] is True
    assert not any(a['kind']=='ENTRY' for a in j.actions(2100))


def test_final_loss_breach_is_explicit_not_a_clean_execution_pass(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,price='20',fee='0');terminal(j,s);protect(j,s)
    j.append(event('UNWIND',reason='loss'));exit_leg(j,s,price='1',fee='0');flat(j)
    j.append(event('FINALITY',funding_complete=True,net_cash_usdt='-19'))
    assert j.snapshot()['requested_loss_bound_breached'] is True
    assert j.snapshot()['terminal_verdict']=='LOSS_BOUND_BREACHED'


def test_liquidation_cannot_assume_unlimited_best_price_depth(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s)
    result=liquidation_value(j.snapshot(),{s:{'bids':[['1','.1']], 'asks':[['1.01','1']],
        'exit_taker_fee':'.001'}},funding_reserve_usdt='0')
    assert result['net_usdt'] is None and result['action']=='UNWIND_DATA_UNKNOWN'


def test_liquidation_walks_full_depth_instead_of_best_price(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,price='1',fee='0')
    result=liquidation_value(j.snapshot(),{s:{'bids':[['1','.1'],['.9','.9']],
        'asks':[['1.01','1']], 'exit_taker_fee':'0'}},funding_reserve_usdt='0')
    assert D(result['net_usdt'])==D('-.09')


def test_existing_unrelated_database_is_never_initialized_or_adopted(tmp_path):
    import sqlite3
    path=tmp_path/'foreign.sqlite'
    with sqlite3.connect(path) as c:c.execute('CREATE TABLE unrelated(value TEXT)')
    original=path.read_bytes()
    with pytest.raises(ValueError,match='JOURNAL_IDENTITY'):MicroJournal(path,plan())
    assert path.read_bytes()==original


def test_fee_enrichment_of_duplicate_fill_counts_quantity_once(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s);fill(j,s,fee=None,xid='late-fee')
    fill(j,s,fee='.01',xid='late-fee')
    assert j.snapshot()['held'][s]=='1'
    assert j.snapshot()['fee_unknown_execution_ids']==[]
    assert D(j.snapshot()['fees_usdt'])==D('.01')


def test_duplicate_trade_after_finality_does_not_reopen_or_double_pnl(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];enter(j,s);exit_leg(j,s);flat(j)
    j.append(event('FINALITY',funding_complete=True,net_cash_usdt='-.02'))
    before=j.snapshot();fill(j,s,xid='fill-'+before['entries'][s]['link'])
    assert j.snapshot()==before


def test_changed_execution_source_time_under_same_exec_id_is_conflict(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',plan());s=BASKET[0][0];send(j,s)
    order=j.snapshot()['entries'][s]
    e=event('ENTRY_FILL',symbol=s,order_link_id=order['link'],order_id='broker-'+order['link'],
        execution_id='time-bound',quantity='1',price='1',fee_usdt='0',source_execution_ms=2000)
    j.append(e);later=dict(e,event_id='different-envelope',source_execution_ms=2001)
    with pytest.raises(ValueError,match='EXECUTION_CONFLICT'):j.append(later)
