"""Synthetic contract tests; never opens producer outcomes or executes Brain."""
import json

import pytest

from research_lab.brain_shadow_readonly_bridge_v1 import (
    ImportBlocked, import_sources, producer_hash, registry_hash,
)


def chain(path, rows):
    previous = '0' * 64
    out = []
    for body in rows:
        row = dict(body, prev_hash=previous)
        row['record_hash'] = producer_hash(row)
        previous = row['record_hash']
        out.append(row)
    path.write_text(''.join(json.dumps(row) + '\n' for row in out))
    return out


@pytest.fixture
def packet(tmp_path):
    producer = tmp_path / 'producer'; producer.mkdir()
    opp = dict(schema='OpportunityRecord V2', opp_id='a' * 32,
               source_ref='synthetic/signal', source_sha256='b' * 64,
               t_observation_ms=10, t_available_ms=20, t_decision_ms=30,
               t_recorded_ms=31, context={'schema': 'ContextRecord v2', 'funding': 'UNKNOWN'},
               sleeve='ELDER', symbol='BTCUSDT', side=-1, execution_owner_id='UNKNOWN')
    decision = dict(opp_id=opp['opp_id'], policy='BRAIN_V2_DET', policy_sha='c' * 64,
                    allocation_units=1.0, constraints=['HEDGE'], t_recorded_ms=32)
    registry = {'BRAIN_V2_DET': {'policy_sha': 'c' * 64, 'brain_version': 'BRAIN_V2_DET/v1',
                               'source_revision': '0efbca7'}}
    op = producer / 'opportunities.jsonl'; dec = producer / 'decisions.jsonl'
    chain(op, [opp]); chain(dec, [decision])
    return dict(opportunities=op, decisions=dec, registry=registry,
                registry_sha256=registry_hash(registry), target=tmp_path / 'receiver',
                source_id='research-brain-shadow', now_ms=100), opp, decision


def test_duplicate_restart_and_unknown_relationship(packet):
    args, _, _ = packet
    first = import_sources(**args)
    again = import_sources(**args)
    assert first == again
    event = first[0]['event']
    assert event['action'] == 'HEDGE'
    assert event['relationship'] == 'UNKNOWN'
    assert event['context']['funding'] == 'UNKNOWN'
    assert event['money_authority'] is False
    assert event['record_kind'] == 'SHADOW_PROPOSAL'
    assert len((args['target'] / 'journal.jsonl').read_text().splitlines()) == 1


@pytest.mark.parametrize('change', ['future', 'dangling', 'policy', 'causality', 'context'])
def test_reject_bad_contract(packet, change):
    args, opp, decision = packet
    if change == 'future': decision['t_recorded_ms'] = 101
    if change == 'dangling': decision['opp_id'] = 'd' * 32
    if change == 'policy': decision['policy_sha'] = 'd' * 64
    if change == 'causality': opp['t_available_ms'] = 40
    if change == 'context': opp['context'] = None
    chain(args['opportunities'], [opp]); chain(args['decisions'], [decision])
    with pytest.raises(ImportBlocked): import_sources(**args)
    assert not args['target'].exists()


def test_tampered_chain(packet):
    args, _, _ = packet
    args['decisions'].write_text(args['decisions'].read_text().replace('HEDGE', 'TRADE'))
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_conflicting_revision(packet):
    args, _, decision = packet
    import_sources(**args)
    decision['allocation_units'] = 0.5
    chain(args['decisions'], [decision])
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_partial_tail_blocks_without_truncation(packet):
    args, _, _ = packet
    import_sources(**args)
    path = args['target'] / 'journal.jsonl'
    with path.open('ab') as stream: stream.write(b'{"partial":')
    before = path.read_bytes()
    with pytest.raises(ImportBlocked): import_sources(**args)
    assert path.read_bytes() == before


@pytest.mark.parametrize('relation', ['HEDGE', 'CONFLICT', 'INDEPENDENT'])
def test_explicit_relation_separate_from_action(packet, relation):
    args, _, decision = packet
    decision['relationship'] = relation
    chain(args['decisions'], [decision])
    assert import_sources(**args)[0]['event']['relationship'] == relation


@pytest.mark.parametrize('alias', ['same_parent', 'symlink', 'hardlink'])
def test_source_target_overlap_and_alias(packet, alias):
    args, _, _ = packet
    if alias == 'same_parent': args['target'] = args['decisions'].parent
    elif alias == 'symlink':
        link = args['target']; link.symlink_to(args['decisions'].parent, target_is_directory=True)
    else:
        args['target'].mkdir(mode=0o700)
        (args['target'] / 'journal.jsonl').hardlink_to(args['decisions'])
    before = args['decisions'].read_bytes()
    with pytest.raises(ImportBlocked): import_sources(**args)
    assert args['decisions'].read_bytes() == before


def test_source_incomplete_tail_rejected(packet):
    args, _, _ = packet
    with args['decisions'].open('ab') as stream: stream.write(b'{')
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_no_outcome_fields(packet):
    args, _, decision = packet
    decision['realized_net_bps'] = 50
    chain(args['decisions'], [decision])
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_concurrent_writer_refused(packet):
    from research_lab.brain_shadow_readonly_bridge_v1 import BrainEventJournal
    args, _, _ = packet
    with BrainEventJournal(args['target']):
        with pytest.raises(ImportBlocked, match='writer_busy'):
            import_sources(**args)


def test_receiver_hash_tampering_refused(packet):
    args, _, _ = packet
    import_sources(**args)
    path = args['target'] / 'journal.jsonl'
    path.write_text(path.read_text().replace('"allocation_units":1.0', '"allocation_units":2.0'))
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_unknown_context_is_preserved(packet):
    args, opp, _ = packet
    opp['context'] = {'schema': 'UNKNOWN', 'rezhim_v1': 'UNKNOWN'}
    chain(args['opportunities'], [opp])
    assert import_sources(**args)[0]['event']['context'] == opp['context']


def test_context_future_refused(packet):
    args, opp, _ = packet
    opp['context']['t_available_ms'] = 11
    chain(args['opportunities'], [opp])
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_incremental_source_append_preserves_old_receipts(packet):
    args, opp, decision = packet
    first = import_sources(**args)
    second_opp = dict(opp, opp_id='e' * 32)
    second_decision = dict(decision, opp_id=second_opp['opp_id'])
    chain(args['opportunities'], [opp, second_opp]); chain(args['decisions'], [decision, second_decision])
    rows = import_sources(**args)
    assert rows[0] == first[0]
    assert len(rows) == 2


def test_two_sleeves_share_context_decision_receiver_without_financial_authority(packet):
    args,opp,decision=packet
    kity=dict(opp,opp_id='f'*32,sleeve='KITY_BYBIT',side=1)
    kity_decision=dict(decision,opp_id=kity['opp_id'],allocation_units=0.5,
      constraints=['TRADE','vol_vysokaya'],relationship='INDEPENDENT')
    chain(args['opportunities'],[opp,kity]);chain(args['decisions'],[decision,kity_decision])
    events=[r['event'] for r in import_sources(**args)]
    assert {e['producer_opportunity']['sleeve'] for e in events}=={'ELDER','KITY_BYBIT'}
    assert events[0]['context_sha256']==events[1]['context_sha256']
    assert events[1]['reasons']==kity_decision['constraints'] and events[1]['allocation_units']==0.5
    assert all(e['record_kind']=='SHADOW_PROPOSAL' and not e['accounting_authority']
               and not e['execution_authority'] for e in events)


def test_revised_context_conflicts_after_restart(packet):
    args, opp, _ = packet
    import_sources(**args)
    opp['context']['rezhim_v1'] = 'BEAR_TREND'
    chain(args['opportunities'], [opp])
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_opportunity_outcome_extension_refused(packet):
    args, opp, _ = packet
    opp['realized_net_bps'] = 1
    chain(args['opportunities'], [opp])
    with pytest.raises(ImportBlocked): import_sources(**args)


def test_refuses_join_filename_before_open(packet):
    args, _, _ = packet
    args['decisions'] = args['decisions'].parent / 'joins.jsonl'
    with pytest.raises(ImportBlocked, match='source_filename_contract'): import_sources(**args)


def test_streams_source_larger_than_eight_mb_and_filters_decisions(packet):
    args, opp, decision = packet
    # Real-shaped single large features payload avoids generating thousands of
    # slow test rows; existing producer histories are tens of megabytes.
    opp['features'] = {'diagnostic': 'x' * (8 * 1024 * 1024)}
    chain(args['opportunities'], [opp])
    assert args['opportunities'].stat().st_size > 8 * 1024 * 1024
    assert import_sources(**args, since_ms=33) == []
    assert (args['target'] / 'journal.jsonl').read_bytes() == b''


def test_since_filters_only_after_full_chain_verification(packet):
    args, _, _ = packet
    args['decisions'].write_text(args['decisions'].read_text().replace('HEDGE', 'TRADE'))
    with pytest.raises(ImportBlocked, match='source_chain_hash'):
        import_sources(**args, since_ms=33)


def test_since_is_inclusive_and_registry_is_intake_pin(packet):
    args, opp, decision = packet
    old = dict(decision, policy='OLD_POLICY', t_recorded_ms=31)
    chain(args['decisions'], [old, decision])
    rows = import_sources(**args, since_ms=32)
    assert len(rows) == 1
    assert rows[0]['event']['policy'] == 'BRAIN_V2_DET'


def test_capacity_preflight_leaves_zero_partial_batch(packet, monkeypatch):
    from research_lab import os2_shadow_journal as durable
    args, opp, decision = packet
    chain(args['opportunities'], [opp, dict(opp, opp_id='e' * 32)])
    chain(args['decisions'], [decision, dict(decision, opp_id='e' * 32)])
    monkeypatch.setattr(durable, 'MAX_RECEIPTS', 1)
    with pytest.raises(ImportBlocked, match='receiver_capacity') as failure:
        import_sources(**args)
    assert failure.value.capacity['projected_receipts'] == 2
    assert (args['target'] / 'journal.jsonl').read_bytes() == b''


def test_stream_row_bound_is_enforced_even_for_filtered_history(packet, monkeypatch):
    from research_lab import brain_shadow_readonly_bridge_v1 as receiver
    args, _, decision = packet
    chain(args['decisions'], [decision, dict(decision, policy='OLD')])
    monkeypatch.setattr(receiver, 'MAX_SOURCE_ROWS', 1)
    with pytest.raises(ImportBlocked, match='source_row_bound'):
        import_sources(**args, since_ms=99)


def test_receiver_byte_capacity_preflight_is_exact(packet, monkeypatch):
    from research_lab import os2_shadow_journal as durable
    args, _, _ = packet
    monkeypatch.setattr(durable, 'MAX_JOURNAL_BYTES', 100)
    with pytest.raises(ImportBlocked, match='receiver_capacity') as failure:
        import_sources(**args)
    capacity = failure.value.capacity
    assert capacity['projected_bytes'] > capacity['max_bytes'] == 100
    assert capacity['projected_receipts'] == 1
    assert (args['target'] / 'journal.jsonl').read_bytes() == b''
