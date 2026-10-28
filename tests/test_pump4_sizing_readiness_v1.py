"""Audit cross-checks: rounding/cost attribution must match the unchanged owner."""
import copy
import importlib.util
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/pump4_native_reference_84_20261026.json'


def audit_module():
    assert importlib.util.find_spec('research_lab.pump4_sizing_readiness_v1'), 'Sizing attribution missing'
    from research_lab import pump4_sizing_readiness_v1
    return pump4_sizing_readiness_v1


def test_all_saved_cases_match_real_source_sizing_and_receipt(tmp_path):
    # Catches dropped costs, wrong rounding or a false pass despite a lot floor.
    from pump4_native_84_harness import inputs, FP
    from scripts.rehearse_pump4_bybit_v1 import MemoryBybit
    from research_lab.pump4_account_owner_v1 import source_sizing
    data = json.loads(FIXTURE.read_bytes())
    saved = json.loads((ROOT / 'reports/evidence/pump4_native_off_20261026/cases84-memory-receipt.json').read_bytes())
    report = audit_module().analyze(data)
    assert report['sizing_statuses'] == saved['sizing_statuses']
    for index, (case, row, previous) in enumerate(zip(data['cases'], report['rows'], saved['rows'], strict=True)):
        exchange = MemoryBybit(tmp_path / f'{index}.json', 'normal')
        now = case['plan']['entry_bar_open_ms'] + 20
        bundle, public, _ = inputs(exchange, case, now, case['plan']['entry'])
        try:
            size = source_sizing(case['plan'], bundle, public, data['policy'], fingerprint=FP, now_ms=now)
            status = 'FIXTURE_SOURCE_SIZING_PASS'
            assert D(row['selected_quantity']) == D(size['quantity'])
            assert D(row['selected_cost_inclusive_risk']) == D(size['scenario_stop_and_cost_usdt'])
        except ValueError as exc:
            status = str(exc)
        assert row['status'] == status == previous['sizing_status']
    assert report['live_ready_cases'] == 0
    assert report['money_authority'] is report['orders_allowed'] is False


def test_minimum_keeps_40_60_lot_floors_without_exit_min_notional():
    data = json.loads(FIXTURE.read_bytes())
    row = audit_module().analyze(data)['rows'][12]
    assert row['symbol'] == 'ALGOUSDT'
    assert D(row['minimum_quantity']) == D('42.5')
    assert D(row['minimum_notional']) == D('5.033275')
    assert D(row['minimum_tp1_quantity']) == 17
    assert D(row['minimum_tp2_quantity']) == D('25.5')
    assert D(row['minimum_cost_inclusive_risk']) == D('0.785464345000002125')


@pytest.mark.parametrize('fault', ['missing_funding', 'invalid_price', 'changed_fraction'])
def test_incomplete_or_changed_contract_never_gets_classified_as_ready(fault):
    data = json.loads(FIXTURE.read_bytes())
    bad = copy.deepcopy(data)
    if fault == 'missing_funding':
        del bad['cases'][0]['instrument']['lowerFundingRate']
    elif fault == 'invalid_price':
        bad['cases'][0]['plan']['entry'] = float('nan')
    else:
        bad['cases'][0]['plan']['fractions'] = [0.5, 0.5]
    with pytest.raises((ValueError, KeyError)):
        audit_module().analyze(bad)
