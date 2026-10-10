"""Source tampering must stop this one-off operation before opening SSH."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
OP='reports/evidence/alpaca_handoff_20261010/apply_non_dispatch.py'
CAP='reports/evidence/alpaca_handoff_20261010/capture_non_dispatch.py'
PARENT='reports/evidence/alpaca_opening_20261009/read_postcheck.py'
MODULE='research_lab/alpaca_dynamic_v1.py'
POLICY='reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

@pytest.mark.parametrize('changed,key',[(PARENT,'parent_capture_script_sha256'),
    (CAP,'capture_script_sha256'),(MODULE,'module_sha256')])
def test_changed_executed_source_is_rejected_before_ssh(tmp_path,monkeypatch,changed,key):
    for rel in [OP,CAP,PARENT,MODULE,POLICY]:
        dest=tmp_path/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dest)
    base=tmp_path/'.private/alpaca_handoff_20261010/custody_v3.json'
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({'response':{'book':{'sha256':'a'*64},'paper':{'sha256':'b'*64},
        'root_crontab':{'sha256':'c'*64},'writer_sources':{},'services':{},
        'source_manifests':{},'legacy_exclusions':{'sha256':'d'*64}}}))
    permit={'status':'APPROVED_ORDERS_OFF_RETIREMENT_ONLY',
        'operation_sha256':sha(tmp_path/OP),'capture_script_sha256':sha(tmp_path/CAP),
        'parent_capture_script_sha256':sha(tmp_path/PARENT),'module_sha256':sha(tmp_path/MODULE),
        'baseline_capture_sha256':sha(base),'single_owner_for_non_dispatch_handoff_reviewed':True}
    assert key in permit
    permit_path=tmp_path/'permit.json';permit_path.write_text(json.dumps(permit))
    with (tmp_path/changed).open('a') as f:f.write('\n# drift after approval\n')
    monkeypatch.setattr(sys,'argv',[str(tmp_path/OP),str(tmp_path/'output.json'),'--apply',str(permit_path)])
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:pytest.fail('drifted source reached SSH'))
    with pytest.raises(AssertionError):runpy.run_path(str(tmp_path/OP),run_name='__main__')
    assert not (tmp_path/'output.json').exists()
