import gzip
import json

import pytest

from research_lab.brain_v2_frozen_primitives import BrainBlocked, digest
from research_lab.brain_v2_develop_run import CompressedLedger, execute_once


def test_single_success_refuses_second_driver_invocation(tmp_path):
    calls=[]
    def driver(out):
        calls.append(out);return dict(status='DEVELOPING_FILTER_PASS',filter_runs=1,orders_allowed=False)
    report=execute_once(tmp_path/'run','a'*64,driver)
    assert report['run_permission_consumed'] is True
    with pytest.raises(BrainBlocked,match='single_run_already_started'):
        execute_once(tmp_path/'run','a'*64,driver)
    assert len(calls)==1


def test_early_failure_preserves_explicit_blocked_and_spent_marker(tmp_path):
    def failed(_):raise BrainBlocked('funding_timestamp_duplicate_order')
    report=execute_once(tmp_path/'run','b'*64,failed)
    assert report['status']=='BLOCKED_DATA' and report['filter_runs']==1
    assert json.loads((tmp_path/'run'/'TERMINAL.json').read_bytes())['reason']=='funding_timestamp_duplicate_order'
    assert (tmp_path/'run'/'STARTED.json').is_file()
    with pytest.raises(BrainBlocked):execute_once(tmp_path/'run','b'*64,lambda _:None)


def test_existing_empty_crash_directory_still_blocks(tmp_path):
    (tmp_path/'run').mkdir()
    with pytest.raises(BrainBlocked,match='single_run_already_started'):
        execute_once(tmp_path/'run','a'*64,lambda _:None)


def test_offline_ledger_hash_chain_and_deterministic_gzip(tmp_path):
    hashes=[]
    for i in range(2):
        ledger=CompressedLedger(tmp_path/f'{i}.gz')
        ledger.append(dict(tick_ms=0,arms={'RAW_SAFE':{'risk':'500'}}))
        ledger.append(dict(tick_ms=900000,arms={'RAW_SAFE':{'risk':'0'}}))
        receipt=ledger.close();hashes.append(receipt['compressed_sha256'])
        rows=[json.loads(row) for row in gzip.decompress((tmp_path/f'{i}.gz').read_bytes()).splitlines()]
        assert rows[0]['previous_sha256']=='0'*64
        assert rows[1]['previous_sha256']==rows[0]['sha256']==digest({k:v for k,v in rows[0].items() if k!='sha256'})
        assert receipt['records']==2 and receipt['last_record_sha256']==rows[1]['sha256']
    assert hashes[0]==hashes[1]
