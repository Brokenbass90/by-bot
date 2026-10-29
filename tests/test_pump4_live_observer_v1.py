import hashlib
import json
from pathlib import Path
import pytest
from research_lab.pump4_live_observer_v1 import import_capture, expiry_status, ObserverBlocked


def sha(raw): return hashlib.sha256(raw).hexdigest()
def put(root, name, value):
    raw = json.dumps(value, sort_keys=True, separators=(',',':')).encode()
    (root / name).write_bytes(raw)
    return {'name': name, 'sha256': sha(raw), 'kind': 'receipt'}


@pytest.fixture
def capture(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    scope = put(root, 'scope.json', {'expires_ms': 9000}); scope['kind'] = 'scope'
    config = put(root, 'config.json', {'scope_sha256': scope['sha256']}); config['kind'] = 'config'
    row = {'schema': 'PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1', 'observed_ms': 1000,
           'run_id': 'abc', 'tick': 1, 'mode': 'OWNER_TINY_LIVE', 'pid': 7,
           'scope_sha256': scope['sha256'], 'runner_config_sha256': config['sha256'],
           'result': {'status': 'NO_NEW_SIGNAL', 'broker_writes': 0}, 'final_costs_proven': False}
    receipt = put(root, 'receipt.json', row)
    manifest = {'schema': 'PUMP4_OBSERVER_CAPTURE_V1', 'observed_ms': 2000,
                'scope_sha256': scope['sha256'], 'config_sha256': config['sha256'],
                'files': [scope, config, receipt], 'coverage': 'SAMPLED_STATUS_NOT_OPPORTUNITY_CENSUS'}
    return root, manifest, tmp_path / 'target'


def run(capture):
    root, m, target = capture
    raw = json.dumps(m, sort_keys=True).encode(); (root / 'manifest.json').write_bytes(raw)
    return import_capture(root / 'manifest.json', sha(raw), target,
                          expected_scope=m['scope_sha256'], expected_config=m['config_sha256'])


def test_replay_and_capture_time_do_not_revise_facts(capture):
    a = run(capture); capture[1]['observed_ms'] = 3000; b = run(capture)
    assert a['new_events'] == 1 and b['new_events'] == 0
    assert a['receipt_events'] == 1
    rows = list(capture[2].rglob('journal.jsonl'))
    event = json.loads(rows[0].read_text())['event']
    assert event['record_kind'] == 'ACTUAL_EXECUTION_RECEIPT'
    assert event['money_authority'] is False
    assert event['brain_advice_comparison'] == 'UNKNOWN_NO_CAUSAL_VERSIONED_ADVICE'
    assert event['net_pnl_status'] == 'NOT_PROVEN'


@pytest.mark.parametrize('mutation', ['hash', 'scope', 'future', 'symlink', 'hardlink'])
def test_invalid_source_has_no_receiver_writes(capture, mutation):
    root, m, target = capture
    if mutation == 'hash': (root / 'receipt.json').write_text('{}')
    elif mutation == 'scope': m['scope_sha256'] = 'f' * 64
    elif mutation == 'future': m['observed_ms'] = 500
    elif mutation == 'symlink':
        p = root / 'receipt.json'; data = p.read_bytes(); p.unlink()
        q = root.parent / 'alias'; q.write_bytes(data); p.symlink_to(q)
    else:
        import os
        os.link(root / 'receipt.json', root / 'alias')
    with pytest.raises(ObserverBlocked): run(capture)
    assert not target.exists()


def test_changed_existing_receipt_is_conflict(capture):
    run(capture)
    root, m, _ = capture
    row = json.loads((root / 'receipt.json').read_bytes()); row['result']['status'] = 'CHANGED'
    m['files'][-1] = put(root, 'receipt.json', row)
    with pytest.raises(ObserverBlocked, match='conflict'): run(capture)


def test_receiver_partial_tail_not_repaired(capture):
    run(capture)
    path = next(capture[2].rglob('journal.jsonl'))
    with path.open('ab') as out: out.write(b'{')
    before = path.read_bytes()
    with pytest.raises(ObserverBlocked): run(capture)
    assert path.read_bytes() == before


def test_source_target_overlap(capture):
    root, m, _ = capture
    with pytest.raises(ObserverBlocked): run((root, m, root / 'observer'))


@pytest.mark.parametrize('now,captured,admitted,expected', [
    (8000,8000,False,'WAITING_WITHIN_ENTRY_PERIOD'),
    (10000,8000,False,'UNKNOWN_NEED_POST_EXPIRY_CAPTURE'),
    (10000,10000,False,'NO_TRADE_CONFIRMED'),
    (10000,10000,True,'ENTRY_PERIOD_EXPIRED_CUSTODY_CONTINUES'),
])
def test_expiry_requires_post_deadline_inventory_and_get(now,captured,admitted,expected):
    assert expiry_status(now, 9000, captured, admitted, True, True) == expected
    assert expiry_status(10000,9000,9001,False,False,True) != 'NO_TRADE_CONFIRMED'
    assert expiry_status(10000,9000,9001,False,True,False) != 'NO_TRADE_CONFIRMED'


def test_changed_timestamp_cannot_evade_receipt_identity(capture):
    run(capture)
    root, m, _ = capture
    row = json.loads((root / 'receipt.json').read_bytes()); row['observed_ms'] = 3700000
    m['observed_ms'] = 3800000
    m['files'][-1] = put(root, 'receipt.json', row)
    with pytest.raises(ObserverBlocked, match='conflict'): run(capture)


def test_scope_uses_contract_canonical_hash_while_manifest_pins_raw_bytes(capture):
    root,m,_=capture
    v=json.loads((root/'scope.json').read_bytes())
    raw=json.dumps(v,indent=2).encode();(root/'scope.json').write_bytes(raw)
    m['files'][0]['sha256']=sha(raw)
    assert run(capture)['receipt_events']==1


def test_lifecycle_prefix_replay_and_partial_tail_is_unknown(capture):
    from research_lab.att1_lifecycle_journal import LifecycleJournal
    root,m,_=capture
    p=root/'life.jsonl'
    LifecycleJournal(p).append({'schema_id':'att1_lifecycle_event_v1','event_id':'obs-1',
                               'kind':'OBSERVATION','observation':{'observed_ms':1200,'held_qty':'0'}})
    raw=p.read_bytes()
    m['files'].append({'name':p.name,'sha256':sha(raw),'kind':'lifecycle',
                       'source_stream':'flows/exact/observations.jsonl','partial_tail_bytes':3})
    a=run(capture);m['observed_ms']=4000;b=run(capture)
    assert a['lifecycle_events']==1 and a['new_events']==2 and b['new_events']==0
    assert a['source_completeness']=='UNKNOWN_PARTIAL_TAIL'
    assert p.read_bytes()==raw


def test_corrupt_lifecycle_rejected_before_receiver_writes(capture):
    root,m,target=capture
    raw=b'{}\n';p=root/'life.jsonl';p.write_bytes(raw);p.chmod(0o600)
    m['files'].append({'name':p.name,'sha256':sha(raw),'kind':'lifecycle'})
    with pytest.raises(ObserverBlocked):run(capture)
    assert not target.exists()


def test_capture_save_rejects_path_escape_and_existing_directory(tmp_path):
    import base64,runpy
    pull=runpy.run_path(str(Path(__file__).parents[1]/'scripts/pull_pump4_observer_capture_v1.py'))
    data=b'{}';f={'name':'../escape','sha256':sha(data),'kind':'scope'}
    b={'manifest':{'scope_sha256':pull['SCOPE'],'config_sha256':pull['CONFIG'],'files':[f,dict(f,name='config.json')]},
       'payload':{'../escape':base64.b64encode(data).decode(),'config.json':base64.b64encode(data).decode()}}
    with pytest.raises(ValueError,match='capture_name'):pull['save_bundle'](b,tmp_path/'capture')
    assert not (tmp_path/'capture').exists()


def test_production_config_projection_binding(capture):
    from research_lab.os2_shadow_bridge import digest
    root,m,_=capture
    c={'source':'unchanged','authority':{'path':'owner-scope.json'}}
    raw=json.dumps(c,sort_keys=True,separators=(',',':')).encode();(root/'config.json').write_bytes(raw)
    m['config_sha256']=sha(raw);m['files'][1]['sha256']=sha(raw)
    scope={'runner_config_sha256':digest({'source':'unchanged'})}
    raw=json.dumps(scope,sort_keys=True,separators=(',',':')).encode();(root/'scope.json').write_bytes(raw)
    m['scope_sha256']=sha(raw);m['files'][0]['sha256']=sha(raw)
    row=json.loads((root/'receipt.json').read_bytes());row['scope_sha256']=m['scope_sha256'];row['runner_config_sha256']=m['config_sha256']
    m['files'][-1]=put(root,'receipt.json',row)
    assert run(capture)['receipt_events']==1


def test_legacy_advice_does_not_become_causal_v11_v12(tmp_path):
    from research_lab.brain_shadow_readonly_bridge_v1 import producer_hash
    from research_lab.pump4_live_observer_v1 import audit_advice
    row={'kl':'PUMP4|TESTUSDT|1000','noga':'PUMP4','t_signala':1000,'t_soveta':1500,
         'sovet':'VHOD','do_ishoda':True,'prev':'0'*64}
    row['hash']=producer_hash(row)
    p=tmp_path/'sovety.jsonl';p.write_text(json.dumps(row,ensure_ascii=False)+'\n')
    result=audit_advice(p)
    assert result['chain_records']==1 and result['pump4_rows']==1
    assert result['comparison_status']=='UNKNOWN_NO_CAUSAL_VERSIONED_ADVICE'
    p.write_bytes(p.read_bytes()+b'{')
    with pytest.raises(ObserverBlocked,match='partial'):audit_advice(p)
