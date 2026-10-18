"""One actual frozen58-source → selector → native lifecycle rehearsal."""
import importlib
import pytest


def test_complete_frozen_monthly_cycle_needs_no_market_or_broker(tmp_path):
    r=importlib.import_module('scripts.rehearse_alpaca_monthly_cycle_v1').run(tmp_path/'rehearsal')
    assert r['status']=='MONTHLY_ORDERS_OFF_END_TO_END_PASS'
    assert r['source_symbols']==58 and r['selector_monkeypatched'] is False
    assert r['simulated_entries']==1 and r['duplicate_entries']==0
    assert r['full_native_stop'] and r['day_rearm'] and r['daily_close_ratchet']
    assert r['response_loss_recovered'] and r['broker_flat'] and r['accounting_final']
    assert r['next_month_selection_ready'] and r['capital_released']
    assert r['real_broker_requests']==r['real_broker_writes']==0


def test_two_monthly_cycles_use_one_standing_grant_and_one_book(tmp_path):
    r=importlib.import_module('scripts.rehearse_alpaca_monthly_cycle_v1').run(
        tmp_path/'standing',standing_grant=True)
    assert r['status']=='MONTHLY_STANDING_ORDERS_OFF_REPEAT_PASS'
    assert r['simulated_entries']==2 and r['closed_roundtrips']==2
    assert r['standing_grant_count']==1 and r['duplicate_entries']==0
    assert r['broker_flat'] and r['accounting_final'] and r['capital_released']
    assert r['selector_monkeypatched'] is False
