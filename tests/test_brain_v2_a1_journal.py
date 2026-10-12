import json
import os
from dataclasses import replace

import pytest

from research_lab.brain_v2_a1 import BrainJournal, empty_brain_state
from research_lab.brain_v2_frozen_primitives import digest
from research_lab.os2_shadow_bridge import BridgeBlocked
from research_lab.os2_shadow_journal import ShadowJournal
from tests.test_brain_v2_a1_allocator import NOW, PIN, batch, op, terminal, HOUR


def init():
    return dict(request_id='epoch1',kind='INIT',initial_equity_usd=1000,
                epoch_start_ms=NOW,source_hash=PIN,capital_known=True,
                positions_known=True,protection_known=True)


def test_restart_exact_receipts_and_separate_arms_atomic(tmp_path):
    root=tmp_path/'brain'; x=op()
    with BrainJournal(root) as j:
        j.process(init()); receipt=j.process(batch([x]))
    with BrainJournal(root) as j:
        assert j.process(batch([x]))==receipt
        close=j.process(batch([],hour=NOW+HOUR,exits=[terminal(x)]))
        assert all(x.id in a['closed'] for a in close['state_after']['arms'].values())
    with BrainJournal(root) as j:
        assert j.process(batch([],hour=NOW+HOUR,exits=[terminal(x)]))==close
        assert j.state==close['state_after']


def test_duplicate_writer_payload_conflict_and_caller_mutation(tmp_path):
    root=tmp_path/'brain'
    with BrainJournal(root) as j:
        with pytest.raises(BridgeBlocked,match='writer_busy'): BrainJournal(root)
        receipt=j.process(init()); receipt['state_after']['arms']['RAW_SAFE']['positions']['evil']=1
        assert not j.state['arms']['RAW_SAFE']['positions']
        conflict=init();conflict['initial_equity_usd']=1001
        with pytest.raises(BridgeBlocked,match='request_identity_conflict'): j.process(conflict)


def test_blocked_data_is_durable_inert_receipt_not_a_fake_empty_population(tmp_path):
    with BrainJournal(tmp_path/'brain') as j:
        j.process(init()); before=j.state
        req=batch([op()]);req['costs_known']=False
        result=j.process(req)
        assert result['status']=='BLOCKED_DATA'
        assert result['state_after']==before
        assert result['decisions']=={}
        assert result['orders_allowed'] is False


@pytest.mark.parametrize('fault',['partial','hash','rehash_state','wrong_schema'])
def test_corrupt_tail_and_semantic_rehash_do_not_adopt_state(tmp_path,fault):
    root=tmp_path/'brain'
    with BrainJournal(root) as j: j.process(init())
    path=root/'journal.jsonl'; raw=path.read_bytes()
    if fault=='partial': path.write_bytes(raw[:-1])
    else:
        r=json.loads(raw)
        if fault in ('hash','rehash_state'):
            r['state_after']['arms']['RAW_SAFE']['realized_equity_usd']='1001'
            if fault=='rehash_state':
                s=r['state_after'];s['state_sha256']=digest({k:v for k,v in s.items() if k!='state_sha256'})
                r['sha256']=digest({k:v for k,v in r.items() if k!='sha256'})
        else: r['schema']='OS2_SHADOW_RECEIPT_V1'
        path.write_text(json.dumps(r)+'\n')
    before=path.read_bytes()
    with pytest.raises(BridgeBlocked): BrainJournal(root)
    assert path.read_bytes()==before


def test_brain_journal_cannot_be_opened_by_os2_writer(tmp_path):
    root=tmp_path/'brain'
    with BrainJournal(root) as j:j.process(init())
    with pytest.raises(BridgeBlocked,match='journal_corrupt_prefix'): ShadowJournal(root)


def test_uncertain_append_reopen_reconciles_without_duplicate_transaction(tmp_path,monkeypatch):
    root=tmp_path/'brain'; real=os.fsync
    with BrainJournal(root) as j:
        j.process(init())
        def fail(fd): raise OSError('injected uncertainty')
        monkeypatch.setattr(os,'fsync',fail)
        with pytest.raises(BridgeBlocked,match='append_uncertain'):j.process(batch([op()]))
        monkeypatch.setattr(os,'fsync',real)
        with pytest.raises(BridgeBlocked,match='instance_poisoned'):j.process(batch([op()]))
    with BrainJournal(root) as j:
        result=j.process(batch([op()]))
        assert result['sequence']==2
        assert len(j.state['arms']['RAW_SAFE']['positions'])==1


def test_multiple_fractional_cash_closures_survive_canonical_order_and_restart(tmp_path):
    root=tmp_path/'brain'
    xs=[replace(op(i),stop_distance_frac=.0137+i*.00001) for i in range(3)]
    with BrainJournal(root) as j:
        j.process(init());j.process(batch(xs))
        last=j.process(batch([],hour=NOW+HOUR,exits=[terminal(x,gross=.03779) for x in reversed(xs)]))
    with BrainJournal(root) as j:
        assert j.state==last['state_after']
        assert all(len(a['closed'])==3 for a in j.state['arms'].values())
