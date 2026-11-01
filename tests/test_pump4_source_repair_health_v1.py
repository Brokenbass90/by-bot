"""End-to-end health semantics without broker calls or a financial owner."""
import os,stat
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path
import pytest
from scripts import pump4_source_repair_health_v1 as H

def sample(status='ENTRY_WINDOW_CLOSED_COVERAGE_CHECKED',complete=True):
    scan=dict(status=status,coverage_complete=complete)
    return dict(unit=dict(ActiveState='active',MainPID='123'),old_inhibited=True,lock_held=True,
        go_present=True,go_verified=True,mode='OWNER_TINY_LIVE',scope_digest='scope',config_sha256='config',
        receipt=dict(schema='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1',mode='OWNER_TINY_LIVE',broker_writes=None,
            pid=123,scope_sha256='scope',runner_config_sha256='config',observed_ms=1000,
            result=dict(status=status,source_scan=scan)),
        live_evidence=dict(source_ms=1000,status='LIVE_FLAT_WAITING_SIGNAL',actual_protection_proven=False,financial_trading_proven=False))

@pytest.mark.parametrize('status',['WAITING_H1_PUBLICATION_PREFIX','WAITING_H1_CENSUS_FINALIZATION'])
def test_pending_source_never_reports_fully_healthy_or_notifies_owner(status):
    r=H.assess(sample(status,False),1001)
    assert r['status']=='PENDING_SOURCE' and r['reason']==status
    assert H.notify_required(r,{}) is False

def test_verified_completed_source_and_flat_account_is_healthy():
    r=H.assess(sample(),1001)
    assert r['status']=='HEALTHY' and r['source_coverage']['coverage_complete'] is True

@pytest.mark.parametrize('fault',['missing_scan','wrong_semantics','blocked'])
def test_process_alive_and_flat_account_do_not_mask_source_failure(fault):
    v=sample()
    if fault=='missing_scan':v['receipt']['result']=dict(status='NO_NEW_SIGNAL')
    elif fault=='wrong_semantics':v['receipt']['result']['source_scan']['coverage_complete']=False
    else:v['receipt']['result']=dict(status='BLOCKED_NEW_INPUTS')
    r=H.assess(v,1001)
    assert r['status']=='UNHEALTHY' and H.notify_required(r,{}) is True
    assert H.notify_required(r,r) is False

def test_protected_custody_does_not_require_a_new_entry_scan():
    v=sample();v['receipt']['result']=dict(status='RECONCILED_CUSTODY')
    v['live_evidence'].update(status='LIVE_NATIVE_PROTECTED',actual_protection_proven=True,financial_trading_proven=True)
    r=H.assess(v,1001)
    assert r['status']=='HEALTHY' and r['actual_protection_proven'] is True

def test_health_handles_240001_receipts_with_streaming_metadata_not_a_lifetime_cap(monkeypatch,tmp_path):
    @contextmanager
    def entries(root):
        def rows():
            for i in range(240001):
                yield SimpleNamespace(name=str(i)+'.json',path=str(tmp_path/(str(i)+'.json')),
                    stat=lambda follow_symlinks=False,i=i:SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_nlink=1,st_uid=os.geteuid(),st_mtime_ns=i))
        yield rows()
    monkeypatch.setattr(H.os,'scandir',entries)
    assert H.latest_receipt(tmp_path)==tmp_path/'240000.json'
