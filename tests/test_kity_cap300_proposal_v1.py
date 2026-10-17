"""Market-only real capture; no credentials, orders or account balances."""
import hashlib
import json
from decimal import Decimal as D
from pathlib import Path
import subprocess
import sys

import pytest

from research_lab.kity_cap300_proposal_v1 import calculate_proposal, build_saved_proposal, owner_review_packet
from research_lab.kity_execution_micro_runtime_v1 import _owner_bounds, BASKET
from research_lab.kity_micro_feasibility_v1 import assess_market_geometry

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    raw = (ROOT / 'tests/fixtures/kity_capacity_20261017/cap300_market.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '6fcb1b0265a39dbffb451fa7db73fdd097ca5e27fe7196c779d1d628913731e5'
    fixture = json.loads(raw)
    bounds = json.loads((ROOT / 'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json').read_bytes())
    return fixture, bounds


def run(fixture=None):
    source, bounds = inputs()
    source = source if fixture is None else fixture
    return calculate_proposal(source['rows'], source['instruments'], observed_ms=source['observed_ms'], original_bounds=bounds)


def test_real_capture_capacity_passes_300_but_original_215_remains_blocked():
    f, bounds = inputs()
    old = assess_market_geometry(f['rows'], bounds)
    proposal = run()
    assert old['status'] == 'CAPACITY_BLOCKED'
    assert proposal['capacity_status'] == 'FITS_PROPOSED_CAP'
    assert D(proposal['minimum_required_gross_usdt']) == D('246.149420')
    assert [l['qty'] for l in old['legs']] == [l['qty'] for l in proposal['legs']]
    assert proposal['proposed_gross_cap_usdt'] == '300'
    assert proposal['loss_exit_trigger_usdt'] == '15'
    assert not proposal['money_authority'] and not proposal['orders_allowed']
    assert not proposal['source_fresh_for_dispatch']
    assert proposal['new_policy_created'] is False
    assert proposal['old_attempt_reusable'] is False
    assert proposal['owner_command'] is None
    changed = dict(bounds, max_gross_usdt='300')
    with pytest.raises(ValueError, match='OWNER_BOUND_CONFLICT'):
        _owner_bounds(changed)
    with pytest.raises(ValueError):
        _owner_bounds(proposal)


def test_per_symbol_fees_are_used_not_a_global_default():
    p = run()
    assert D(p['constant_price_roundtrip_fees_usdt']) == D('0.25711816075')
    fees = {l['symbol']: l['taker_fee_rate'] for l in p['legs']}
    assert fees['VVVUSDT'] == '0.0011'
    assert fees['XAUUSDT'] == '0.000275'
    assert fees['BTWUSDT'] == '0.00055'
    assert D(p['initial_margin_reference_usdt']) == D('35.13890533333333333333333333')


def test_native_stops_and_funding_keep_original_threshold_without_guarantee():
    p = run()
    assert D(p['funding_reserve_30min_usdt']) == 0
    assert p['guaranteed_final_loss_cap_usdt'] is None
    for l in p['legs']:
        entry, stop, tick = D(l['collar_entry_price']), D(l['native_stop_draft']), D(l['tick'])
        assert stop % tick == 0
        assert (stop < entry) if l['side'] == 'Buy' else (stop > entry)
    assert D(p['native_guard_price_loss_usdt']) + D(p['collar_roundtrip_fee_reserve_usdt']) <= 15


def test_gap_stresses_use_cap_300_and_never_claim_15_is_a_hard_loss_cap():
    p = run()
    scenario = next(s for s in p['after_trigger_stresses'] if s['adverse_move_fraction'] == '0.10')
    assert D(scenario['scenario_loss_usdt']) > D('45')
    assert scenario['gross_basis_usdt'] == '300'
    assert p['stress_is_guaranteed_bound'] is False
    assert p['price_growth_scenarios'][0]['uniform_price_multiplier'] == '1'
    assert any(s['capacity_status'] == 'BLOCKED' for s in p['price_growth_scenarios'])


def test_funding_is_recomputed_when_30_minutes_crosses_a_real_boundary():
    f, _ = inputs()
    f['observed_ms'] = 1792266300000  # 19:45 UTC: seven 4h legs fund at 20:00.
    p = run(f)
    assert sum(l['funding_events_30min'] for l in p['legs']) == 7
    assert D(p['funding_reserve_30min_usdt']) > 0
    assert D(p['native_guard_price_loss_usdt']) + D(p['collar_roundtrip_fee_reserve_usdt']) + D(p['funding_reserve_30min_usdt']) <= 15


def test_capacity_insufficient_never_builds_an_activation_request():
    from research_lab.kity_cap300_proposal_v1 import _scaled_rows
    f, _ = inputs()
    f['rows'] = _scaled_rows(f['rows'], D('1.50'))
    p = run(f)
    assert p['capacity_status'] == 'CAPACITY_BLOCKED'
    packet = owner_review_packet(p)
    assert 'CAPACITY_BLOCKED_NO_ACTIVATION' in packet['remaining_gates']
    assert packet['owner_command'] is None and packet['money_authority'] is False


@pytest.mark.parametrize('mutation', ['fees_nan', 'funding_stale', 'hedge_mode', 'missing_leg', 'wrong_order', 'leverage_zero', 'tick_mismatch', 'metadata_mismatch', 'funding_nan'])
def test_unknown_or_changed_inputs_fail_closed(mutation):
    f, _ = inputs()
    if mutation == 'fees_nan': f['instruments'][0]['taker_fee'] = 'NaN'
    if mutation == 'funding_stale': f['instruments'][0]['next_funding_ms'] = str(f['observed_ms'])
    if mutation == 'hedge_mode': f['instruments'][0]['position_idx'] = 1
    if mutation == 'missing_leg': f['rows'].pop()
    if mutation == 'wrong_order': f['instruments'].reverse()
    if mutation == 'leverage_zero': f['instruments'][0]['configured_leverage'] = '0'
    if mutation == 'tick_mismatch': f['instruments'][0]['tick_size'] = '.01'
    if mutation == 'metadata_mismatch': f['instruments'][0]['minimum_quantity'] = '1'
    if mutation == 'funding_nan': f['instruments'][0]['funding_rate_observed'] = 'NaN'
    with pytest.raises(ValueError): run(f)


def test_proposal_cap_cannot_be_changed_through_existing_bounds():
    f, bounds = inputs()
    bounds['max_gross_usdt'] = '300'
    with pytest.raises(ValueError, match='OWNER_BOUND_CONFLICT'):
        calculate_proposal(f['rows'], f['instruments'], observed_ms=f['observed_ms'], original_bounds=bounds)


def test_owner_packet_is_an_inert_one_shot_request_not_a_renewal():
    from bot.kity_m3_orders_off import digest
    p = run()
    # Market-only proof cannot be presented as authenticated custody readiness.
    packet = owner_review_packet(p)
    assert 'DATED_AUTHENTICATED_ACCOUNT_CAPTURE_REQUIRED' in packet['remaining_gates']
    assert packet['orders_allowed'] is False and packet['owner_command'] is None
    assert packet['scope']['gross_cap_usdt'] == '300'
    assert packet['scope']['loss_trigger_usdt'] == '15'
    assert packet['scope']['max_personal_attempts'] == 1
    assert packet['spent_policy_sha256'] == 'a1c97e6b94e3d1a1c8927e7dba252cbd12a1c6f49012133587a85c27fb8845c8'
    assert packet['packet_id'] == digest({k:v for k,v in packet.items() if k != 'packet_id'})
    p['loss_exit_trigger_usdt'] = '20'
    with pytest.raises(ValueError, match='PROPOSAL_PIN_CONFLICT'):
        owner_review_packet(p)


def test_saved_capture_hash_and_path_are_checked_before_readiness(tmp_path):
    f, bounds = inputs()
    p = tmp_path / 'source.json'; p.write_text('{}')
    with pytest.raises(ValueError, match='CAPTURE_PIN_CONFLICT'):
        build_saved_proposal(p, '0' * 64, bounds)
    link = tmp_path / 'link.json'; link.symlink_to(p)
    with pytest.raises(ValueError, match='PROPOSAL_CAPTURE_PATH'):
        build_saved_proposal(link, hashlib.sha256(p.read_bytes()).hexdigest(), bounds)


def test_cli_default_is_offline_without_capture_or_owner_command():
    p = subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_kity_cap300_proposal_v1.py')], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {'status': 'NO_NETWORK_ORDERS_OFF', 'orders_allowed': False, 'money_authority': False}
