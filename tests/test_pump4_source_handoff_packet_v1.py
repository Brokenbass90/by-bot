"""Exact production-shaped CONFIGURATION only. Never apply or construct ops.

Keys/env contents are absent. All mutations and synthetic PASS proofs stay under
pytest tmp_path; positive financial transitions use the fictional separate tests.
"""
import copy,json,os,subprocess,sys
from pathlib import Path
import pytest
from scripts import pump4_source_handoff_v1 as H
from scripts import build_pump4_source_handoff_v1 as B

@pytest.fixture
def shape(tmp_path,monkeypatch):
    default=Path(__file__).resolve().parents[1]/'.private/pump4_physical_handoff_20261101/fixture-input.json'
    fixture=Path(os.environ.get('PUMP4_HANDOFF_FIXTURE',str(default)))
    if not fixture.is_file():pytest.skip('Nonsecret pinned production-shaped fixture not supplied')
    data=json.loads(fixture.read_bytes())
    # The reviewed current source is used, not a cached candidate implementation.
    data['installer_source']=Path(H.__file__).read_text()
    data['health_source']=Path(H.__file__).with_name('pump4_source_repair_health_v1.py').read_text()
    monkeypatch.setattr(H,'BASE',tmp_path)
    def build(binding=None,name='packet'):
        folder=tmp_path/name
        p=B.assemble(copy.deepcopy(data),folder,str(folder),namespace_base=tmp_path,new_binding=binding)
        return folder,p,H.sha(H.encode(p))
    return data,build

def rewrite(folder,p):
    # Adversarial test packet: recompute its own claimed hash to test CODE guards,
    # rather than merely a bad checksum. This never touches the real candidate.
    p['files']={n:H.sha(H.read(folder/n)) for n in p['files']}
    material={k:v for k,v in p.items() if k not in {'files','material_sha256'}}
    material['files']={k:v for k,v in p['files'].items() if k not in {'offline-acceptance.json','independent-review.json'}}
    p['material_sha256']=H.digest(material);(folder/'candidate.json').write_bytes(H.encode(p))
    return H.sha(H.encode(p))

def test_exact_built_shape_preserves_source_epoch_lock_risk_and_has_no_go(shape):
    data,build=shape;folder,p,pin=build();e=H.load_packet(folder/'candidate.json',pin)
    assert e['acceptance_ready'] is False
    assert e['new_scope']['policy']==data['scope']['policy']
    assert e['new_config']['epoch_started_ms']==data['config']['epoch_started_ms']
    assert e['new_scope']['account_lock_inode']==818853
    assert e['new_scope']['valid_from_ms']==data['scope']['valid_until_ms']
    assert e['new_scope']['valid_until_ms']==data['scope']['valid_until_ms']+7*H.DAY
    assert e['required_key_until_ms']==e['new_scope']['valid_until_ms']+8*H.DAY
    assert not (folder/'owner-go.json').exists() and not (folder/'packet.json').exists()

@pytest.mark.parametrize('fault',['budget','entry_window','unit','health','missing_file_pin'])
def test_rehashed_bad_package_cannot_bypass_frozen_contract(shape,fault):
    _,build=shape;folder,p,_=build()
    if fault=='budget':
        s=json.loads((folder/'scope.json').read_bytes());s['policy']['gross_usdt']='31';(folder/'scope.json').write_bytes(H.encode(s))
    elif fault=='entry_window':
        c=json.loads((folder/'runner.json').read_bytes());c['entry_max_delay_ms']=60001;(folder/'runner.json').write_bytes(H.encode(c))
    elif fault=='unit':(folder/'new-owner.service').write_text((folder/'new-owner.service').read_text()+'ExecStartPost=/bin/false\n')
    elif fault=='health':(folder/'health.py').write_text((folder/'health.py').read_text()+'\nUNREVIEWED=True\n')
    else:p['files'].pop('scope.json')
    pin=rewrite(folder,p)
    with pytest.raises(H.HandoffError):H.load_packet(folder/'candidate.json',pin)

def test_separate_key_binding_preserves_original_account_lock_and_legacy_file(shape):
    data,build=shape
    binding=dict(credential_source='/private/fixture/new-source.env',credential_source_sha256='b'*64,account_fingerprint='c'*64)
    folder,p,pin=build(binding);e=H.load_packet(folder/'candidate.json',pin)
    assert e['new_scope']['account_fingerprint']=='c'*64
    assert e['new_scope']['account_lock_path']==data['scope']['account_lock_path']
    assert json.loads((folder/'old-original-owner.json').read_bytes())==data['original']
    assert e['acceptance_ready'] is False
    with pytest.raises(H.HandoffError):build(dict(binding,credential_source=data['config']['credential_source']),name='bad')

def test_model_only_receipts_must_bind_same_material(shape):
    _,build=shape;folder,p,_=build()
    offline=dict(status='PASS',material_sha256=p['material_sha256'],network_denied=True,broker_requests=0,broker_writes=0)
    review=dict(status='PASS',material_sha256=p['material_sha256'],unresolved_important=0,runtime_model_verified=True,model='gpt-6-astra',effort='high')
    pin=B.seal(folder,offline,review);e=H.load_packet(folder/'packet.json',pin)
    assert e['acceptance_ready'] is True  # Synthetic only; no SystemOps or apply.
    review['material_sha256']='0'*64;(folder/'independent-review.json').write_bytes(H.encode(review))
    p=json.loads((folder/'packet.json').read_bytes());p['files']['independent-review.json']=H.sha(H.encode(review))
    (folder/'packet.json').write_bytes(H.encode(p))
    with pytest.raises(H.HandoffError):H.load_packet(folder/'packet.json',H.sha(H.encode(p)))

def test_wrapper_rejects_modified_health_even_with_python_optimization(shape):
    _,build=shape;folder,_,_=build()
    (folder/'health.py').write_text('print("UNSAFE_EXECUTION")\n')
    run=subprocess.run([sys.executable,'-O','-B',str(folder/'new-wrapper.py')],capture_output=True,text=True)
    assert run.returncode!=0 and 'UNSAFE_EXECUTION' not in run.stdout
