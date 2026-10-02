"""Inert archive acceptance uses synthetic caps, never owner risk approval."""
from copy import deepcopy
import hashlib,json,tarfile,importlib,os,subprocess,sys
from pathlib import Path
import pytest
from test_att1_canary_preparation import entry_inputs,N


def api():
    return importlib.import_module('scripts.package_att1_canary_orders_off')


def files(tmp_path):
    m=api();_,_,v=entry_inputs()
    b=tmp_path/'private-binding.json';b.write_text(json.dumps(v))
    sources={p:hashlib.sha256((m.ROOT/p).read_bytes()).hexdigest() for p in m.SOURCES}
    a={'schema_id':'att1_canary_package_acceptance_v1','evidence_kind':'SYNTHETIC_TEST_FIXTURE',
       'source_tree_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=m.ROOT,text=True).strip(),
       'observed_ms':N,'source_hashes':sources,'monolith_sha256':hashlib.sha256((m.ROOT/'smart_pump_reversal_bot.py').read_bytes()).hexdigest(),
       'checks':{k:'PASS' for k in ('local_targeted','target_python','historical_receipts','critical_review')},
       'target_receipt_sha256':'a'*64,'critical_review_receipt_sha256':'b'*64,
       'provenance_receipt_sha256':'c'*64,'owner_go':False,'orders_allowed':False}
    ap=tmp_path/'acceptance.json';ap.write_text(json.dumps(a))
    return b,ap


def test_package_is_deterministic_inert_and_private_binding_excluded(tmp_path):
    m=api();b,a=files(tmp_path)
    one=m.build(tmp_path/'one',binding_path=b,acceptance_path=a)
    two=m.build(tmp_path/'two',binding_path=b,acceptance_path=a)
    assert one['archive_sha256']==two['archive_sha256']
    assert one['orders_allowed'] is False and one['owner_go'] is False
    assert one['readiness']=='ENGINEERING_FIXTURE_ONLY'
    private=Path(one['private_binding']);assert private.stat().st_mode&0o777==0o600
    with tarfile.open(one['archive']) as t:
        names=t.getnames()
        assert 'app/smart_pump_reversal_bot.py' not in names
        assert all('.env' not in p and '.private' not in p and 'allowlist_change_log' not in p for p in names)
        assert not any(p.endswith('private-binding.json') for p in names)
        seam=t.extractfile('app/bot/att1_canary_monolith_seam.py').read().decode()
        ns={};exec(seam,ns)
        assert ns['_att1_prepare_new_canary'](None)['status']=='PREPARATION_DISABLED'
        ns['ATT1_CANARY_PREPARATION_ENABLE']=True
        with pytest.raises(ValueError):ns['_att1_prepare_new_canary'](None)


@pytest.mark.parametrize('mutation',['missing_caps','send_true','missing_check','stale','source_mismatch','authority','missing_dependency'])
def test_package_blocks_unproven_or_changed_inputs(tmp_path,mutation,monkeypatch):
    m=api();b,a=files(tmp_path);v=json.loads(b.read_text());acc=json.loads(a.read_text())
    if mutation=='missing_caps':del v['binding']['absolute_risk_cap']
    elif mutation=='send_true':v['binding']['send_enabled']=True
    elif mutation=='missing_check':acc['checks']['target_python']='BLOCKED'
    elif mutation=='stale':acc['observed_ms']=N-61000
    elif mutation=='source_mismatch':acc['source_hashes'][m.SOURCES[0]]='f'*64
    elif mutation=='authority':acc['owner_go']=True
    elif mutation=='missing_dependency':monkeypatch.setattr(m,'SOURCES',tuple(p for p in m.SOURCES if p!='research_lab/att1_lifecycle_session.py'))
    b.write_text(json.dumps(v));a.write_text(json.dumps(acc))
    with pytest.raises(ValueError):m.build(tmp_path/'bad',binding_path=b,acceptance_path=a)
    assert not (tmp_path/'bad').exists()


def test_extracted_candidate_import_and_capture_with_enabled_flag(tmp_path):
    m=api();b,a=files(tmp_path);r=m.build(tmp_path/'out',binding_path=b,acceptance_path=a)
    extract=tmp_path/'extract';extract.mkdir()
    with tarfile.open(r['archive']) as t:t.extractall(extract,filter='data')
    script="from bot.att1_canary_preparation import preparation_implementation_hash;from bot.att1_coordinator_adapter import SEND_ENABLED;from bot import att1_canary_monolith_seam as s;assert not SEND_ENABLED;s.ATT1_CANARY_PREPARATION_ENABLE=True;print(preparation_implementation_hash())"
    p=subprocess.run([sys.executable,'-B','-c',script],cwd=extract/'app',env={'PATH':os.environ['PATH'],'ATT1_CANARY_PREPARATION_ENABLE':'1'},capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert len(p.stdout.strip())==64
