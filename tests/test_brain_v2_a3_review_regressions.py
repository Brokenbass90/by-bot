import json
import os
from copy import deepcopy
from decimal import Decimal

import pytest

from research_lab.brain_v2_a3 import BrainJournal, assess_request, funding_summary
from research_lab.brain_v2_frozen_primitives import BrainBlocked, digest
from research_lab.os2_shadow_bridge import BridgeBlocked
from tests.test_brain_v2_a3_ticks import (
    NOW, HOUR, TICK, op, init, initialized, tick, terminal, funding, advance,
)


def test_complete_terminal_population_is_required_before_causal_tick():
    req=tick([op()]);req['terminals_complete']=False
    with pytest.raises(BrainBlocked,match='terminal_population_unknown'):
        assess_request(req,initialized())


@pytest.mark.parametrize('field',['R','hours','api_key','hour_ms'])
def test_request_cannot_embed_outcomes_secrets_or_hour_batch_override(field):
    req=tick([op()]);req[field]=1
    with pytest.raises(BrainBlocked,match='unknown_request_fields'):
        assess_request(req,initialized())


def test_unknown_request_fields_are_not_appended_to_journal(tmp_path):
    with BrainJournal(tmp_path/'a3') as j:
        j.process(init());before=(tmp_path/'a3/journal.jsonl').read_bytes()
        req=tick([op()]);req['api_key']='NOT_A_REAL_KEY'
        with pytest.raises(BridgeBlocked,match='unknown_request_fields'):j.process(req)
        assert (tmp_path/'a3/journal.jsonl').read_bytes()==before


def test_a4_late_settlement_rate_is_unknown_at_release_and_no_partial_cash():
    x=op();end=NOW+HOUR;ev=terminal(x,expected=[end],rates=[(end,'.001')])
    ev['funding']['rates'][0]['available_ms']=end+1
    s=assess_request(tick([x]),initialized())['state_after']
    result=advance(s,end,terminals=[ev])
    for a in result['state_after']['arms'].values():
        assert a['realized_equity_usd']=='1000'
        assert a['closed'][x.id]['net_usd'] is None
        assert x.id not in a['positions']


def test_funding_coverage_diagnostic_does_not_become_admission_veto():
    x=op();s=assess_request(tick([x]),initialized())['state_after']
    result=advance(s,NOW+HOUR,terminals=[terminal(x,expected=[NOW+HOUR])],xs=[op(2,tick=NOW+HOUR)])
    assert result['funding_coverage']['status']=='BLOCKED_DATA'
    assert all(ds[0]['accepted'] for ds in result['decisions'].values())


def test_three_arms_cash_and_unknown_populations_remain_independent():
    xs=[op(i,sleeve='BOUNCE1',side='long' if i%2 else 'short') for i in range(5)]
    result=assess_request(tick(xs),initialized());s=result['state_after']
    excluded=next(d['opportunity_id'] for d in result['decisions']['FOUNDATION'] if not d['accepted'])
    events=[terminal(x,expected=[NOW+HOUR] if x.id==excluded else []) for x in xs]
    final=advance(s,NOW+HOUR,terminals=events)
    rows=final['funding_coverage']['arms']
    assert rows['RAW_SAFE']['evaluated']==5 and rows['RAW_SAFE']['funding_unknown']==1
    assert rows['FOUNDATION']['evaluated']==4 and rows['FOUNDATION']['funding_unknown']==0
    equities={a['realized_equity_usd'] for a in final['state_after']['arms'].values()}
    assert len(equities)>1


@pytest.mark.parametrize('fault',['partial','state_rehash','wrong_schema'])
def test_corrupt_or_semantically_rehashed_receipt_cannot_be_adopted(tmp_path,fault):
    root=tmp_path/'a3'
    with BrainJournal(root) as j:j.process(init())
    path=root/'journal.jsonl';raw=path.read_bytes()
    if fault=='partial':path.write_bytes(raw[:-1])
    else:
        receipt=json.loads(raw)
        if fault=='wrong_schema':receipt['schema']='BRAIN_V2_A1_RECEIPT'
        else:
            state=receipt['state_after'];state['arms']['RAW_SAFE']['initial_equity_usd']='1001'
            state['arms']['RAW_SAFE']['realized_equity_usd']='1001'
            state['state_sha256']=digest({k:v for k,v in state.items() if k!='state_sha256'})
        receipt['sha256']=digest({k:v for k,v in receipt.items() if k!='sha256'})
        path.write_text(json.dumps(receipt)+'\n')
    before=path.read_bytes()
    with pytest.raises(BridgeBlocked):BrainJournal(root)
    assert path.read_bytes()==before


def test_single_writer_conflict_and_uncertain_append_cannot_duplicate(tmp_path,monkeypatch):
    root=tmp_path/'a3';real=os.fsync
    with BrainJournal(root) as j:
        j.process(init())
        with pytest.raises(BridgeBlocked,match='writer_busy'):BrainJournal(root)
        def fail(fd):raise OSError('uncertain')
        monkeypatch.setattr(os,'fsync',fail)
        with pytest.raises(BridgeBlocked,match='append_uncertain'):j.process(tick([op()]))
        monkeypatch.setattr(os,'fsync',real)
        with pytest.raises(BridgeBlocked,match='instance_poisoned'):j.process(tick([op()]))
    with BrainJournal(root) as j:
        receipt=j.process(tick([op()]))
        assert receipt['sequence']==2
        assert len(j.state['arms']['RAW_SAFE']['positions'])==1
        req=tick([op()]);req['source_hash']='c'*64
        with pytest.raises(BridgeBlocked,match='request_identity_conflict'):j.process(req)


def test_reordered_inputs_preserve_decisions_and_state():
    xs=[op(i,sleeve=('ETS2','SF3','BOUNCE1')[i%3]) for i in range(8)]
    a=assess_request(tick(xs),initialized());b=assess_request(tick(list(reversed(xs))),initialized())
    assert a['decisions']==b['decisions'] and a['state_after']==b['state_after']
