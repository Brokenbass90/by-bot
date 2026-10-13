"""Fee-to-dossier mechanics only; no broker, money permit or reservation."""
import copy
import importlib
import json
from pathlib import Path

import pytest

from research_lab.alpaca_dynamic_v1 import canonical, digest
from tests.test_alpaca_live_readiness_v1 import lifecycle, posted_case, pre_entry_case
from tests.test_alpaca_dynamic_live_runtime_v1 import setup, case


def api():
    return importlib.import_module('research_lab.alpaca_fee_to_live_closure_v1')


@pytest.fixture
def closure(posted_case,lifecycle,setup,tmp_path):
    # Actual-posted fee arithmetic and actual readiness checks are reused.
    arm,initial,before,after,paths=posted_case
    data=pre_entry_case(lifecycle,setup,tmp_path)
    inputs={n:paths[n] for n in ('cash_before','initial','rearm','protocol')}
    def source(name,value):
        p=tmp_path/(name+'-closure.json');p.write_bytes(canonical(value));inputs[name]=p
    source('arm',arm);source('initial_evidence',initial)
    # The inert deployed files are real fixture files; core money verifier unmodified.
    source('deployment',data['deployment'])
    b=copy.deepcopy(data['binding']);b['sources'].pop('paper')
    source('binding_template',b);source('policy',data['policy'])
    intent=data['intent']
    fixed={k:intent[k] for k in ('session','ranking_sha256','slot_entry_order_id')}
    fixed.update(ticker=intent['symbol'],risk_distance=intent['reference_risk_distance'],
        max_qty=intent['max_qty'],max_notional_usd=intent['max_notional_usd'],
        max_risk_usd=intent['max_risk_usd'])
    source('fixed_intent',fixed)
    # Quote and account source remains separately fresh, not part of a static pin.
    preparation=tmp_path/'live-preparation.json';preparation.write_bytes(canonical(data['preparation']))
    return inputs,paths['terminal'],preparation,data['now_ms'],tmp_path/'attempt'


def run(c):
    inputs,terminal,preparation,now,out=c
    manifest=api().freeze_manifest(inputs,output_dir=out)
    return api().close_once(manifest,terminal_capture=terminal,live_preparation=preparation,now_ms=now)


def test_full_fee_to_bound_dossier_has_no_money_authority(closure):
    r=run(closure)
    assert r['status']=='READY_FOR_LIVE_GO',r
    assert r['orders_allowed'] is False and r['live_orders_allowed'] is False
    p=closure[-1]
    paper=json.loads((p/'paper.json').read_bytes())
    bound=json.loads((p/'deployment-bound.json').read_bytes())
    binding=json.loads((p/'binding.json').read_bytes())
    assert paper['status']=='PAPER_EXECUTION_PASS'
    assert paper['net_usd']=='-4.535524745824'
    assert bound['paper_receipt_sha256']==paper['receipt_sha256']
    assert binding['sources']['paper']['path']==str(p/'paper.json')
    assert r['required_owner_go_text'].startswith('GO ALPACA_DYNAMIC_FIRST_INTENT_V1 ')
    assert not (p/'owner-go.json').exists()
    assert not Path(binding['runtime']).exists()


def test_missing_fees_end_without_binding_or_intent(closure):
    terminal=closure[1];r=json.loads(terminal.read_bytes())
    r['response']['paper_broker']['activities']['payload'].pop()
    terminal.write_bytes(canonical(r))
    out=run(closure)
    assert out['status']=='BLOCKED_DATA' and out['reason']=='PAPER_POSTED_EXIT_FEE_FINALITY_PENDING_OR_CONFLICT'
    assert list(closure[-1].iterdir())==[closure[-1]/'terminal.json']


@pytest.mark.parametrize('fault',['static_drift','stale_quote','no_cash','wrong_gate','no_preparation'])
def test_source_defects_cannot_produce_intent(closure,fault):
    inputs,t,p,now,out=closure
    manifest=api().freeze_manifest(inputs,output_dir=out)
    if fault=='static_drift':inputs['fixed_intent'].write_text('{}')
    elif fault=='no_preparation':p.unlink()
    else:
        prep=json.loads(p.read_bytes());sp=Path(prep['source_files'][0]['path'])
        snapshot=prep['snapshot']
        if fault=='stale_quote':snapshot['observed_ms']-=300001
        if fault=='no_cash':snapshot['account']['cash']='0'
        if fault=='wrong_gate':snapshot['gates']['earnings']=False
        sp.write_bytes(canonical(snapshot))
        import hashlib
        prep['source_files'][0]['sha256']=hashlib.sha256(sp.read_bytes()).hexdigest()
        prep['source_manifest_sha256']=digest(prep['source_files']);p.write_bytes(canonical(prep))
    r=api().close_once(manifest,terminal_capture=t,live_preparation=p,now_ms=now)
    assert r['status']=='BLOCKED_DATA' and r['ready_for_live_go'] is False
    assert not (out/'first-intent.json').exists()


def test_second_call_never_overwrites_or_creates_new_attempt(closure):
    inputs,t,p,now,out=closure
    manifest=api().freeze_manifest(inputs,output_dir=out)
    first=api().close_once(manifest,terminal_capture=t,live_preparation=p,now_ms=now)
    old={f.name:f.read_bytes() for f in out.iterdir()}
    with pytest.raises(ValueError,match='CLOSURE_ATTEMPT_ALREADY_EXISTS'):
        api().close_once(manifest,terminal_capture=t,live_preparation=p,now_ms=now+1000)
    assert old=={f.name:f.read_bytes() for f in out.iterdir()}


def test_manifest_must_be_exact_and_cannot_select_new_session(closure):
    inputs,t,p,now,out=closure
    manifest=api().freeze_manifest(inputs,output_dir=out);manifest['output_dir']+='-other'
    with pytest.raises(ValueError,match='CLOSURE_MANIFEST_PIN_CONFLICT'):
        api().close_once(manifest,terminal_capture=t,live_preparation=p,now_ms=now)
    assert not out.exists()


def test_cli_checks_external_manifest_pin_before_creating_attempt(closure,tmp_path):
    from scripts.close_alpaca_fee_to_live_v1 import main
    inputs,t,p,now,out=closure
    manifest=tmp_path/'manifest.json';manifest.write_bytes(canonical(api().freeze_manifest(inputs,output_dir=out)))
    assert main(['--manifest',str(manifest),'--manifest-sha256','0'*64,
        '--terminal-capture',str(t),'--live-preparation',str(p)])==2
    assert not out.exists()


@pytest.mark.parametrize('drift',[False,True])
def test_installed_verify_only_cannot_observe_broker_or_create_output(closure,tmp_path,monkeypatch,drift):
    import importlib.util
    source=Path(__file__).resolve().parents[1]/'reports/evidence/alpaca_live_readiness_20261013/observe_fee_closure_v1.py'
    spec=importlib.util.spec_from_file_location('closure_observer_test',source)
    observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
    base=tmp_path/'base';kit=base/'kit';kit.mkdir(parents=True)
    monkeypatch.setattr(observer,'BASE',base);monkeypatch.setattr(observer,'KIT',kit)
    inputs,t,p,now,out=closure
    manifest=kit/'manifest.json';manifest.write_bytes(canonical(api().freeze_manifest(inputs,output_dir=out)))
    # A sentinel source must be hashed, never executed by verification.
    reader=kit/'finality-query.py';reader.write_text("raise AssertionError('BROKER_QUERY_NOT_ALLOWED')")
    k=dict(files=[api().pin(manifest),api().pin(reader)])
    k['kit_sha256']=digest(k);(kit/'kit.json').write_bytes(canonical(k))
    before={f.name:f.read_bytes() for f in kit.iterdir()}
    if drift:
        reader.write_text('changed')
        with pytest.raises(ValueError,match='CLOSURE_STATIC_SOURCE_DRIFT'):
            observer.main(k['kit_sha256'],verify_only=True)
    else:
        assert observer.main(k['kit_sha256'],verify_only=True)==0
        assert before=={f.name:f.read_bytes() for f in kit.iterdir()}
    assert not out.exists()
