import json
from pathlib import Path
import pytest
from scripts.verify_att1_lifecycle import verify_fixture, VerificationViolation

FIXTURE=Path(__file__).parent/'fixtures/att1_lifecycle/att1_end_to_end_v1.json'


def test_end_to_end_oracle_restarts_at_every_durable_boundary():
    result=verify_fixture(FIXTURE)
    assert result['status']=='PASS'
    assert result['case_count']==2
    assert result['restart_boundaries']==23
    assert result['money_authority'] is False
    assert result['cases'][0]['final_net_r']=='36637/20000'
    assert result['cases'][1]['final_net_r']=='-757/625'


def test_bad_expected_outcome_cannot_pass(tmp_path):
    raw=json.loads(FIXTURE.read_text());raw['cases'][0]['expected_final']['final_net_r']='2'
    path=tmp_path/'invalid.json';path.write_text(json.dumps(raw))
    with pytest.raises(VerificationViolation):verify_fixture(path)


def test_real_public_runtime_fixture_restarts_with_identical_costed_state():
    from scripts.verify_att1_lifecycle import verify_public_runtime_fixture
    result=verify_public_runtime_fixture()
    assert result['status']=='PASS'
    assert [row['held_qty'] for row in result['restarted_stages']]==['1/10','1/20','0','0']
    assert result['fees']=='363/20000' and result['final_net_r']=='36637/20000'
