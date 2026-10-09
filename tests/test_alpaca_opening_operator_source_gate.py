"""Missing operator source closure must block before planner reservation/network."""
import importlib,copy,json,os,subprocess,sys
from pathlib import Path
import pytest

def gate():
    try:return importlib.import_module('reports.evidence.alpaca_opening_20261009.source_gate').require_review
    except ModuleNotFoundError:return None

def fixture():
    return {'schema':'ALPACA_OPENING_OPERATOR_SOURCE_REVIEW_V1','observed_ms':1000,
            'initial_archive_sha256':'a'*64,'owner':{'status':'VERIFIED','all_installed_writers_reviewed':True,'source_sha256':'b'*64},
            'protection':{'status':'PAPER_PROTOCOL_ELIGIBILITY_ONLY','source_sha256':'c'*64,'actual_acceptance_proven':False},
            'earnings':{'source_sha256':'d'*64},'cost':{'source_sha256':'e'*64},
            'broker_authenticated_by_this_validator':False}

def test_missing_complete_review_cannot_make_a_planner_snapshot():
    validate=gate();assert validate is not None,'source guard missing'
    with pytest.raises(ValueError,match='OPENING_SOURCE_REVIEW_MISSING'):validate(None,'a'*64,1000)

def test_cli_without_review_blocks_before_any_ssh_or_output(tmp_path):
    root=Path(__file__).resolve().parents[1]
    capture=tmp_path/'capture.json';capture.write_text(json.dumps({'response':{}}))
    out=tmp_path/'receipt.json'
    completed=subprocess.run([sys.executable,str(root/'reports/evidence/alpaca_opening_20261009/prepare_opening_plan.py'),str(capture),str(out)],capture_output=True,text=True,env={**os.environ,'PATH':''})
    assert completed.returncode!=0 and 'OPENING_SOURCE_REVIEW_MISSING' in completed.stderr
    assert not out.exists() and 'FileNotFoundError' not in completed.stderr

@pytest.mark.parametrize('part',['owner','protection','earnings','cost'])
def test_missing_companion_evidence_blocks(part):
    validate=gate();assert validate is not None,'source guard missing'
    data=fixture();del data[part]
    with pytest.raises(ValueError):validate(data,'a'*64,1000)

def test_process_scan_alone_is_not_all_writer_review():
    validate=gate();assert validate is not None,'source guard missing'
    data=fixture();data['owner']['all_installed_writers_reviewed']=False
    with pytest.raises(ValueError,match='OWNER_SOURCE_REVIEW'):validate(data,'a'*64,1000)

def test_eligibility_cannot_claim_broker_protection_acceptance():
    validate=gate();assert validate is not None,'source guard missing'
    data=fixture();data['protection']['actual_acceptance_proven']=True
    with pytest.raises(ValueError,match='PROTECTION_ELIGIBILITY_ONLY'):validate(data,'a'*64,1000)

def test_companion_hash_is_bound_and_source_input_is_not_authenticated():
    validate=gate();assert validate is not None,'source guard missing'
    data=fixture();before=copy.deepcopy(data);r=validate(data,'a'*64,1000)
    data['earnings']['source_sha256']='f'*64;s=validate(data,'a'*64,1000)
    assert r['source_sha256']!=s['source_sha256']
    assert before['protection']['actual_acceptance_proven'] is False
    assert r['money_authority'] is False and r['broker_truth_authenticated'] is False

@pytest.mark.parametrize('now,archive',[(301001,'a'*64),(999,'a'*64),(1000,'0'*64)])
def test_old_future_or_different_archive_review_blocks(now,archive):
    validate=gate();assert validate is not None,'source guard missing'
    with pytest.raises(ValueError):validate(fixture(),archive,now)
