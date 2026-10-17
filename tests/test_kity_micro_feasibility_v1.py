"""Frozen saved raw-market geometry; no credentials or market requests."""
import hashlib,json
from pathlib import Path
import pytest
from research_lab.kity_micro_feasibility_v1 import assess_saved_capture,assess_market_geometry

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'tests/fixtures/kity_capacity_20261017'

@pytest.mark.parametrize('name,status,gross',[('prepare_0910','CAPACITY_FITS_SAVED_CAPTURE','207.668760'),('owner_attempt','CAPACITY_BLOCKED','229.584550')])
def test_exact_saved_capture_regression(name,status,gross):
    raw=(FIX/(name+'.json')).read_bytes();manifest=json.loads((FIX/'manifest.json').read_bytes())
    bounds=json.loads((ROOT/'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json').read_bytes())
    fixture=json.loads(raw);assert hashlib.sha256(raw).hexdigest()==manifest['sources'][name]['fixture_sha256']
    r=assess_market_geometry(fixture['rows'],bounds)
    assert r['status']==status and r['minimum_required_reference_gross']==gross
    assert not r['money_authority'] and r['broker_requests']==0 and r['broker_writes']==0
    assert [x['symbol'] for x in r['legs']]==manifest['symbols']
    assert r['minimum_common_target']==('21.6654' if name=='prepare_0910' else '23.88530')
    assert r['venue_floor_common_target']==('20.37970' if name=='prepare_0910' else '23.88530')
    assert r['source_fresh_for_dispatch'] is False


def test_cap_or_source_cannot_be_silently_changed(tmp_path):
    raw=(FIX/'owner_attempt.json').read_bytes();p=tmp_path/'source.json';p.write_bytes(raw)
    b=json.loads((ROOT/'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json').read_bytes())
    with pytest.raises(ValueError,match='HASH'):assess_saved_capture(p,'0'*64,b)
    b['max_gross_usdt']='230'
    with pytest.raises(ValueError,match='OWNER_BOUND_CONFLICT|CAP_REQUIRED'):assess_market_geometry(json.loads(raw)['rows'],b)


def test_future_packet_stays_inert_and_cannot_renew_spent_authority():
    from research_lab.kity_micro_feasibility_v1 import future_owner_proposal
    b=json.loads((ROOT/'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json').read_bytes())
    f=json.loads((FIX/'owner_attempt.json').read_bytes())
    packet=future_owner_proposal(assess_market_geometry(f['rows'],b))
    assert packet['status']=='CAPACITY_BLOCKED_NO_GO_PACKET'
    assert packet['owner_command'] is None and packet['new_policy_created'] is False
    assert packet['preserved_scope']['gross_cap_usdt']=='215' and packet['old_attempt_reusable'] is False


@pytest.mark.parametrize('corrupt',['unknown_status','false_fit'])
def test_future_packet_rejects_unknown_or_inconsistent_capacity(corrupt):
    from research_lab.kity_micro_feasibility_v1 import future_owner_proposal
    b=json.loads((ROOT/'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json').read_bytes())
    f=json.loads((FIX/'owner_attempt.json').read_bytes())
    evidence=assess_market_geometry(f['rows'],b)
    evidence['status']='UNKNOWN' if corrupt=='unknown_status' else 'CAPACITY_FITS_SAVED_CAPTURE'
    with pytest.raises(ValueError,match='CAPACITY_EVIDENCE_REQUIRED'):future_owner_proposal(evidence)
