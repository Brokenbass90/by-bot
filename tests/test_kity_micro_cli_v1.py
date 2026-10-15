import json
from pathlib import Path
import subprocess
import sys

from test_kity_micro_runtime_v1 import dossier

ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'scripts/run_kity_execution_micro_v1.py'


def test_default_preview_does_not_create_any_journal_or_authority(tmp_path):
    d=tmp_path/'input.json';d.write_text(json.dumps(dossier()))
    r=subprocess.run([sys.executable,str(CLI),'--dossier',str(d)],capture_output=True,text=True,cwd=ROOT)
    assert r.returncode==2
    out=json.loads(r.stdout)
    assert out['readiness']['status']=='BLOCKED_EXECUTION' and not out['orders_allowed']
    assert set(tmp_path.iterdir())=={d}


def test_no_apply_or_owner_go_flag_can_enable_orders(tmp_path):
    r=subprocess.run([sys.executable,str(CLI),'--apply'],capture_output=True,text=True,cwd=ROOT)
    assert r.returncode==2 and 'unrecognized arguments: --apply' in r.stderr


def test_real_saved_intake_is_cap_blocked_and_hard_loss_blocked_without_network():
    r=subprocess.run([sys.executable,str(CLI),'--bounds',str(ROOT/'configs/research/kity_execution_micro_owner_bounds_20261015.json')],capture_output=True,text=True,cwd=ROOT)
    assert r.returncode==2
    out=json.loads(r.stdout)
    assert 'GROSS_CAP_EXCEEDED' in out['readiness']['reasons']
    assert 'HARD_FINAL_LOSS_CAP_NOT_ENFORCEABLE_ON_PERPETUALS' in out['readiness']['reasons']


def test_replay_is_explicit_and_remains_nonmonetary(tmp_path):
    d=tmp_path/'input.json';d.write_text(json.dumps(dossier()))
    e=tmp_path/'events.json';e.write_text('[]')
    journal=tmp_path/'kity_micro_replay.sqlite'
    r=subprocess.run([sys.executable,str(CLI),'--dossier',str(d),'--events',str(e),
        '--journal',str(journal)],capture_output=True,text=True,cwd=ROOT)
    assert r.returncode==2 and journal.exists()
    out=json.loads(r.stdout);assert out['lifecycle']['orders_allowed'] is False
