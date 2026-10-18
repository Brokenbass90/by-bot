import hashlib,importlib,json
import pytest


def test_inspection_reads_only_and_requires_exact_manifest_and_custody(tmp_path):
    p=tmp_path/'original.service';p.write_text('original manager')
    candidate=tmp_path/'prepared.service';candidate.write_text('prepared manager')
    manifest=dict(schema='ALPACA_NEXT_OWNER_HANDOFF_V1',old_pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest()},
        prepared_pins={str(candidate):hashlib.sha256(candidate.read_bytes()).hexdigest()},
        deadline_ms=1792415700000,personal_arm=str(tmp_path/'arm.json'),claim=str(tmp_path/'claim.json'),
        scope_sha256='a'*64,new_units=[])
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    try:m=importlib.import_module('scripts.alpaca_next_owner_handoff_v1')
    except ImportError:m=None
    assert m is not None,'personal next-entry handoff missing'
    before=p.read_bytes()
    out=m.inspect(path,pin,now_ms=1792290000000)
    assert out['status']=='ALPACA_NEXT_OWNER_PACKET_INSPECTION_PASS' and out['broker_requests']==0
    assert p.read_bytes()==before and not (tmp_path/'claim.json').exists() and not (tmp_path/'arm.json').exists()
    p.write_text('foreign')
    with pytest.raises(ValueError):m.inspect(path,pin,now_ms=1792290000000)
