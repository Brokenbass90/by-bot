"""One pinned historical path, distinct from new forward or financial proof."""
import hashlib,json,subprocess,sys
from pathlib import Path
import pytest
from scripts.rehearse_pump4_cycle_v1 import run

FIXTURE=Path(__file__).parent/'fixtures/pump4_cycle_20261022.json'
PIN='7edc45fbfaee84e8fefb89adc09054c6b038883853d27a65e7403b05c38aa36e'

def test_actual_cli_intake_through_native_requests_and_40_60_flat(tmp_path):
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()==PIN
    root=tmp_path/'cycle'
    cmd=[sys.executable,'-B','scripts/rehearse_pump4_cycle_v1.py','--input',str(FIXTURE),'--input-sha256',PIN,'--root',str(root)]
    result=json.loads(subprocess.check_output(cmd,text=True))
    assert result['status']=='HISTORICAL_PIPELINE_ORDERS_OFF_PASS'
    assert [x['role'] for x in result['actions']]==['ENTRY','TP1','TP2']
    assert result['tp1_qty']=='4' and result['tp2_qty']=='6'
    assert result['orders_allowed'] is result['tiny_ready'] is False
    assert result['real_broker_requests']==result['real_broker_writes']==0
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='EXCLUSIVE_REHEARSAL_ROOT_REQUIRED'):run(root,FIXTURE,PIN)
    assert before=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}

def test_unpinned_pipeline_cannot_create_an_execution_directory(tmp_path):
    root=tmp_path/'bad'
    with pytest.raises(ValueError,match='PIPELINE_FIXTURE_PIN'):run(root,FIXTURE,'0'*64)
    assert not root.exists()
