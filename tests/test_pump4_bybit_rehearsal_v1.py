import pytest
from decimal import Decimal as D
from scripts.rehearse_pump4_bybit_v1 import run

@pytest.mark.parametrize('scenario',['normal','entry_reply_loss','tp1_reply_loss','partial_entry','partial_tp1','native_stop_race','time_exit'])
def test_whole_trade_reuses_durable_sender_and_preserves_protection(tmp_path,scenario):
    r=run(tmp_path/scenario,scenario=scenario)
    assert r['status']=='PROTOCOL_ORDERS_OFF_REHEARSAL_PASS'
    assert D(r['remaining_qty'])==0 and r['real_broker_requests']==0
    assert r['orders_allowed'] is r['tiny_ready'] is False
    assert r['duplicate_order_links']==0 and r['native_protection_verified']
    if scenario not in ('native_stop_race','time_exit'):
        assert D(r['tp1_filled'])==4 and D(r['tp2_filled'])==6

@pytest.mark.parametrize('scenario,reason',[('intent_reply_loss','UNCERTAIN_DISPATCH_NO_RETRY'),('missing_native_stop','NATIVE_PROTECTION_UNKNOWN'),('unrepresentable_partial','PARTIAL_SPLIT_UNREPRESENTABLE'),('unknown_costs','ACTUAL_COSTS_UNKNOWN')])
def test_uncertain_lifecycle_never_reports_ready_or_blindly_repeats(tmp_path,scenario,reason):
    r=run(tmp_path/scenario,scenario=scenario)
    assert r['status']=='BLOCKED' and r['reason']==reason
    assert r['orders_allowed'] is r['tiny_ready'] is False
    assert r['duplicate_order_links']==0 and r['real_broker_requests']==0

def test_unknown_fault_name_cannot_claim_a_fault_pass_or_create_evidence(tmp_path):
    target=tmp_path/'partial_tp2'
    with pytest.raises(ValueError,match='UNKNOWN_REHEARSAL_SCENARIO'):
        run(target,scenario='partial_tp2')
    assert not target.exists()

@pytest.mark.parametrize('scenario,calls,remaining',[
    ('entry_api_error',1,'0'),('entry_rate_limit',1,'0'),
    ('tp1_api_error',2,'10'),('tp2_api_error',3,'6'),('reduce_race_api_error',2,'0')])
def test_nonzero_bybit_reply_never_becomes_fill_or_retry(tmp_path,scenario,calls,remaining):
    r=run(tmp_path/scenario,scenario=scenario)
    assert r['status']=='BLOCKED' and r['reason']=='UNCERTAIN_DISPATCH_NO_RETRY'
    assert r['simulated_create_calls']==calls and D(r['remaining_qty'])==D(remaining)
    assert r['duplicate_order_links']==0 and r['real_broker_requests']==0
    assert r['orders_allowed'] is r['tiny_ready'] is False
