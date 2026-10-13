import copy
import importlib
from pathlib import Path

import pytest

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_live_readiness_v1 import build_package


def api():
    return importlib.import_module('research_lab.alpaca_orders_off_handoff_v2')


@pytest.fixture(scope='module')
def package():
    return build_package(Path(__file__).resolve().parents[1])


def approval(package):
    row = dict(schema='ALPACA_ORDERS_OFF_INSTALL_HANDOFF_AUTHORIZATION_V2',
               authorization_status='DIRECT_OWNER_APPROVED',
               orders_allowed=False, halt_clear_allowed=False,
               fee_pending_install_allowed=True,
               package_sha256=package['package_sha256'],
               proposal_sha256=api().PROPOSAL_PIN)
    return {**row, 'receipt_sha256': digest(row)}


def execution():
    return dict(status='ACTUAL_EXECUTION_STAGES_PASS_COST_FINALITY_PENDING',
                actual_rearm=True, full_owned_exit=True, orders_allowed=False,
                execution_validation=dict(status='BLOCKED_DATA',
                    reason='PAPER_COST_FINALITY_SOURCE_REQUIRED'),
                receipt_sha256='pinned-original-execution')


def test_pending_fee_install_has_no_money_or_paper_pass(tmp_path, package):
    r = api().install_orders_off(package, approval(package), execution(),
                               now_ms=1791904000000, target=tmp_path/'isolated')
    assert r['status']=='DISABLED_DEPLOYMENT_VERIFIED'
    assert r['paper_receipt_sha256'] is None
    assert r['cost_finality_pending'] is True
    assert r['enabled'] is False and r['orders_allowed'] is False
    assert r['service_activation_count']==r['installed_system_units']==0
    assert (tmp_path/'isolated'/'app'/'scripts/run_alpaca_dynamic_live_v1.py').is_file()
    assert not (tmp_path/'isolated'/'session/owner-go.json').exists()


@pytest.mark.parametrize('defect',['orders','no_explicit_waiver','package','execution','manager_proposal'])
def test_authority_defects_reject_before_any_files(tmp_path, package, defect):
    a=approval(package);e=execution()
    if defect=='orders':a['orders_allowed']=True
    if defect=='no_explicit_waiver':a['fee_pending_install_allowed']=False
    if defect=='package':a['package_sha256']='wrong'
    if defect=='execution':e['execution_validation']['reason']='PROTECTION_FAILED'
    if defect=='manager_proposal':a['authorization_status']='PENDING_DIRECT_OWNER_CONFIRMATION'
    a['receipt_sha256']=digest({k:v for k,v in a.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):
        api().install_orders_off(package,a,e,now_ms=1791904000000,target=tmp_path/'isolated')
    assert not (tmp_path/'isolated').exists()


def test_install_repeat_checks_drift_and_never_repairs(tmp_path,package):
    target=tmp_path/'isolated';a=approval(package);e=execution()
    first=api().install_orders_off(package,a,e,now_ms=1791904000000,target=target)
    assert api().install_orders_off(package,a,e,now_ms=1791904000001,target=target)==first
    source=target/'app/scripts/run_alpaca_dynamic_live_v1.py';source.write_text('drift')
    with pytest.raises(ValueError,match='INSTALLED_FILE_DRIFT'):
        api().install_orders_off(package,a,e,now_ms=1791904000002,target=target)
    assert source.read_text()=='drift'


def test_partial_install_and_symlink_rejected(tmp_path,package):
    target=tmp_path/'isolated';target.mkdir()
    with pytest.raises(ValueError,match='PARTIAL_INSTALL'):
        api().install_orders_off(package,approval(package),execution(),now_ms=1791904000000,target=target)
    link=tmp_path/'link';link.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='SYMLINK'):
        api().install_orders_off(package,approval(package),execution(),now_ms=1791904000000,target=link)


def test_pending_install_cannot_bind_pending_paper(tmp_path,package):
    r=api().install_orders_off(package,approval(package),execution(),now_ms=1791904000000,target=tmp_path/'isolated')
    with pytest.raises(ValueError,match='ACTUAL_PAPER_PASS_REQUIRED'):
        api().bind_final_paper(r,dict(status='PAPER_PENDING'),now_ms=1791904000001)
    p=dict(status='PAPER_EXECUTION_PASS',live_orders_allowed=False)
    p['receipt_sha256']=digest(p)
    bound=api().bind_final_paper(r,p,now_ms=1791904000001)
    assert bound['paper_receipt_sha256']==p['receipt_sha256']
    assert bound['cost_finality_pending'] is False
    assert r['paper_receipt_sha256'] is None
    assert bound['orders_allowed'] is False


def test_cron_edit_is_exact_reversible_and_pin_bound():
    raw=b'OTHER=preserved\n'+api().OLD_LINE.encode()+b'\n# legacy comment\n'
    import hashlib
    edited=api().retired_crontab(raw,before_pin=hashlib.sha256(raw).hexdigest())
    assert edited==b'OTHER=preserved\n'+api().PREFIX.encode()+api().OLD_LINE.encode()+b'\n# legacy comment\n'
    assert edited.replace(api().PREFIX.encode(),b'',1)==raw
    with pytest.raises(ValueError,match='CRON_BEFORE_PIN'):
        api().retired_crontab(raw,before_pin='wrong')
    with pytest.raises(ValueError,match='EXACT_ONE'):
        api().retired_crontab(raw+api().OLD_LINE.encode()+b'\n',before_pin=hashlib.sha256(raw+api().OLD_LINE.encode()+b'\n').hexdigest())
