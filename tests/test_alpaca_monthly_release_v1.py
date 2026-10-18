import importlib,json
from pathlib import Path
import pytest


def test_disabled_schedule_has_one_manager_and_no_activation(tmp_path):
    release=importlib.import_module('research_lab.alpaca_monthly_release_v1')
    files=release.unit_templates('/opt/monthly/app','/opt/python','/opt/monthly/cycle.json','a'*64)
    assert len([k for k in files if k.endswith('.timer')])==2
    assert '--source' in files['alpaca-monthly-owned-source.service']
    assert '--apply' not in ''.join(files.values()) and 'enable --now' not in ''.join(files.values())
    assert 'run_alpaca_monthly_cycle_v1.py' in files['alpaca-monthly-owned-manager.service']


def test_rollback_keeps_manager_on_exposure_or_uncertain_dispatch_and_is_idempotent(tmp_path):
    release=importlib.import_module('research_lab.alpaca_monthly_release_v1')
    p=tmp_path/'selection.json';p.write_text(json.dumps(dict(schema='MONTHLY_DISABLED_RELEASE_POINTER_V1',selected='new',orders_allowed=False)))
    snapshot=dict(owned_positions=1,pending_dispatches=0,accounting_pending=False)
    assert release.rollback_disabled(p,current='new',previous='old',snapshot=snapshot)['status']=='ROLLBACK_BLOCKED_KEEP_OWNED_MANAGER'
    assert json.loads(p.read_text())['selected']=='new'
    snapshot.update(owned_positions=0,pending_dispatches=1)
    assert release.rollback_disabled(p,current='new',previous='old',snapshot=snapshot)['status']=='ROLLBACK_BLOCKED_KEEP_OWNED_MANAGER'
    snapshot.update(pending_dispatches=0,accounting_pending=True)
    assert release.rollback_disabled(p,current='new',previous='old',snapshot=snapshot)['status']=='ROLLBACK_BLOCKED_KEEP_OWNED_MANAGER'
    snapshot['accounting_pending']=False
    assert release.rollback_disabled(p,current='new',previous='old',snapshot=snapshot)['status']=='DISABLED_ROLLBACK_ACCEPTED'
    assert release.rollback_disabled(p,current='new',previous='old',snapshot=snapshot)['status']=='DISABLED_ROLLBACK_ALREADY_RECORDED'
    assert json.loads(p.read_text())['selected']=='old'
