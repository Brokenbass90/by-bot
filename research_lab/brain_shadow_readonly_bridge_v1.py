"""File-only receiver for existing Brain Shadow decisions; never runs a Brain.

The source contract at research 0efbca7 uses constraints/t_recorded_ms although
its prereg describes reasons/ts. Both are preserved and mapped explicitly.
No joins, outcomes, broker state, policy functions or accounting are consulted.
Policy registry pins are operator-supplied evidence, not policy approval.
ELDER-as-hedge is producer behavior; absent relationship metadata stays UNKNOWN.
A partial local tail is BLOCKED without truncation. Restore/reconcile the durable
prefix externally, then reopen; never blindly retry an uncertain write.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from pathlib import Path
import stat

from research_lab import os2_shadow_journal as durable
from research_lab.os2_shadow_journal import ShadowJournal, strict_json
from research_lab.os2_shadow_bridge import BridgeBlocked, MAX_BYTES, canonical, digest

ImportBlocked = BridgeBlocked
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_SOURCE_ROWS = 250_000


def require(condition, reason):
    if not condition:
        raise ImportBlocked('BLOCKED_DATA', reason)


def producer_hash(value):
    """Exact producer serialization; deliberately differs from receiver digest."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def registry_hash(value):
    return digest(value)


def sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def timestamp(value):
    return type(value) is int and value >= 0


def _safe_path(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink_path')
    return path.resolve()


def _read_chain(path, since_ms=None):
    """Stream and verify the entire bounded source chain before returning rows.

    Filtering controls retained decisions, never validation of the chain prefix.
    Opportunities retain every row for source-linked lookup.
    """
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    rows = []; previous = '0' * 64; total = 0; count = 0
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode), 'source_not_regular')
        require(before.st_size <= MAX_SOURCE_BYTES, 'source_byte_bound')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            while True:
                line = stream.readline(MAX_SOURCE_BYTES + 1)
                if not line:
                    break
                total += len(line); count += 1
                require(total <= MAX_SOURCE_BYTES, 'source_byte_bound')
                require(count <= MAX_SOURCE_ROWS, 'source_row_bound')
                require(line.endswith(b'\n'), 'source_partial_tail')
                require(bool(line.strip()), 'blank_source_row')
                try:
                    row = strict_json(line)
                    require(isinstance(row, dict), 'source_row_type')
                    claimed = row.get('record_hash')
                    body = {k: v for k, v in row.items() if k != 'record_hash'}
                    require(row.get('prev_hash') == previous and sha(claimed)
                            and producer_hash(body) == claimed, 'source_chain_hash')
                except (ValueError, TypeError) as error:
                    raise ImportBlocked('BLOCKED_DATA', 'invalid_source_json') from error
                previous = claimed
                if since_ms is not None:
                    require(timestamp(row.get('t_recorded_ms')), 'source_decision_recorded_time')
                if since_ms is None or row['t_recorded_ms'] >= since_ms:
                    rows.append(row)
        after = os.fstat(fd)
        require((before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and total == before.st_size, 'source_changed')
    finally:
        os.close(fd)
    return rows


class BrainEventJournal(ShadowJournal):
    """Reuse existing lock, inode guards, fsync, hash chain and replay handling."""
    receipt_schema = 'BRAIN_READONLY_RECEIPT_V1'
    state_schema = 'BRAIN_READONLY_STATE_V1'

    def initial_state(self):
        return {'schema': self.state_schema}

    def assess(self, bundle):
        return {'event': bundle['event'], 'state_after': self.initial_state()}


def _events(opportunities, decisions, registry, pin, source_id, now_ms, paths):
    require(isinstance(registry, dict) and sha(pin) and registry_hash(registry) == pin, 'policy_registry_pin')
    require(isinstance(source_id, str) and 0 < len(source_id) <= 128, 'source_identity')
    require(timestamp(now_ms), 'invalid_now')
    indexed = {}
    opportunity_fields = {'opp_id', 'schema', 'source_ref', 'source_sha256',
                          't_observation_ms', 't_available_ms', 't_decision_ms', 't_recorded_ms',
                          'sleeve', 'mechanism', 'version', 'symbol', 'side', 'horizon_ms',
                          'context', 'features', 'exp_gross_bps', 'cost_fee_bps', 'cost_spread_bps',
                          'cost_slip_bps', 'cost_funding_bps', 'exp_net_bps', 'uncertainty_bps',
                          'prior_ref', 'prior_status', 'execution_owner_id', 'late', 'prev_hash', 'record_hash'}
    for opportunity in opportunities:
        require(set(opportunity) <= opportunity_fields, 'nonopportunity_source_fields')
        require(opportunity.get('schema') == 'OpportunityRecord V2', 'opportunity_schema')
        key = opportunity.get('opp_id')
        require(isinstance(key, str) and len(key) == 32 and key not in indexed, 'opportunity_identity')
        times = [opportunity.get(k) for k in ('t_observation_ms', 't_available_ms', 't_decision_ms', 't_recorded_ms')]
        require(all(timestamp(t) for t in times) and times[0] <= times[1] <= times[2] <= times[3] <= now_ms,
                'opportunity_causality')
        context = opportunity.get('context')
        require(isinstance(context, dict), 'context_contract')
        # Source lacks a universal context-availability contract. Preserve the
        # evidence limitation rather than inventing a known/fresh regime.
        for field in ('t_observation_ms', 't_available_ms', 't_decision_ms'):
            if field in context:
                require(timestamp(context[field]) and context[field] <= times[0], 'context_future')
        require(opportunity.get('source_sha256') == 'UNKNOWN' or sha(opportunity.get('source_sha256')), 'upstream_source_hash')
        require(isinstance(opportunity.get('source_ref'), str) and opportunity['source_ref'], 'upstream_source_ref')
        require(opportunity.get('execution_owner_id') == 'UNKNOWN', 'source_execution_authority')
        indexed[key] = opportunity
    events = []; seen = set()
    allowed = {'opp_id', 'policy', 'policy_sha', 'allocation_units', 'constraints', 'reasons',
               't_recorded_ms', 'ts', 'brain_version', 'relationship', 'relationship_metadata', 'prev_hash', 'record_hash'}
    for decision in decisions:
        require(set(decision) <= allowed, 'nondecision_source_fields')
        key, policy = decision.get('opp_id'), decision.get('policy')
        require(isinstance(policy, str) and key in indexed, 'dangling_opportunity')
        require((key, policy) not in seen, 'duplicate_source_decision'); seen.add((key, policy))
        opportunity = indexed[key]
        entry = registry.get(policy)
        require(isinstance(entry, dict) and sha(entry.get('policy_sha')) and entry['policy_sha'] == decision.get('policy_sha')
                and isinstance(entry.get('brain_version'), str) and bool(entry['brain_version'])
                and isinstance(entry.get('source_revision'), str) and bool(entry['source_revision']), 'unregistered_policy')
        require(decision.get('brain_version', entry['brain_version']) == entry['brain_version'], 'brain_version_pin')
        reasons = decision.get('reasons', decision.get('constraints'))
        ts = decision.get('ts', decision.get('t_recorded_ms'))
        require(isinstance(reasons, list) and all(isinstance(r, str) for r in reasons), 'reasons_contract')
        require('constraints' not in decision or decision['constraints'] == reasons, 'reasons_alias_conflict')
        require('t_recorded_ms' not in decision or decision['t_recorded_ms'] == ts, 'time_alias_conflict')
        require(timestamp(ts) and opportunity['t_recorded_ms'] <= ts <= now_ms, 'decision_causality')
        allocation = decision.get('allocation_units')
        require(type(allocation) in (float, int) and math.isfinite(allocation) and allocation >= 0, 'allocation_contract')
        relationship = decision.get('relationship', 'UNKNOWN')
        require(relationship in ('HEDGE', 'CONFLICT', 'INDEPENDENT', 'UNKNOWN'), 'relationship_contract')
        metadata = decision.get('relationship_metadata', 'UNKNOWN')
        require(metadata == 'UNKNOWN' or isinstance(metadata, dict), 'relationship_metadata')
        actions = {r for r in reasons if r in ('TRADE', 'HEDGE', 'ABSTAIN')}
        require(len(actions) <= 1, 'ambiguous_action')
        event_id = digest({'source_id': source_id, 'opp_id': key, 'policy': policy})
        event = dict(schema='BRAIN_SHADOW_READONLY_EVENT_V1', event_id=event_id,
                     record_kind='SHADOW_PROPOSAL', mode='SHADOW', money_authority=False,
                     execution_authority=False, accounting_authority=False,
                     source_id=source_id, source_journal=paths, source_revision=entry['source_revision'],
                     source_row_sha256=decision['record_hash'], opportunity_row_sha256=opportunity['record_hash'],
                     source_sha256=opportunity['source_sha256'], source_ref=opportunity['source_ref'],
                     context_sha256=digest(opportunity['context']), context=opportunity['context'],
                     context_availability='SOURCE_TIMESTAMPS_ONLY', policy_registry_sha256=pin,
                     opp_id=key, policy=policy, policy_sha=decision['policy_sha'], brain_version=entry['brain_version'],
                     allocation_units=allocation, reasons=reasons, ts=ts,
                     observed_ms=opportunity['t_observation_ms'], available_ms=opportunity['t_available_ms'],
                     decision_ms=opportunity['t_decision_ms'], action=next(iter(actions), 'UNKNOWN'),
                     relationship=relationship, relationship_metadata=metadata,
                     producer_decision=decision, producer_opportunity=opportunity)
        events.append({'request_id': event_id, 'event': event})
    return events


def _preflight_capacity(journal, events):
    """Compute exact serialized append capacity before the first batch write."""
    journal._unchanged()
    sequence = len(journal.receipts)
    previous = journal.last_hash
    projected_bytes = journal.size
    largest_receipt = largest_input = 0
    for bundle in events:
        if bundle['request_id'] in journal.receipts:
            continue
        sequence += 1
        largest_input = max(largest_input, len(canonical(bundle)))
        receipt = {'schema': journal.receipt_schema, 'sequence': sequence,
                   'request_id': bundle['request_id'], 'input_sha256': digest(bundle),
                   'previous_sha256': previous, **journal.assess(bundle)}
        receipt['sha256'] = digest(receipt)
        length = len(canonical(receipt)) + 1
        largest_receipt = max(largest_receipt, length)
        projected_bytes += length
        previous = receipt['sha256']
    free = shutil.disk_usage(journal.root).free
    capacity = {'current_receipts': len(journal.receipts), 'projected_receipts': sequence,
                'max_receipts': durable.MAX_RECEIPTS, 'current_bytes': journal.size,
                'projected_bytes': projected_bytes, 'max_bytes': durable.MAX_JOURNAL_BYTES,
                'largest_receipt_bytes': largest_receipt, 'largest_input_bytes': largest_input,
                'max_record_bytes': MAX_BYTES, 'free_bytes': free,
                'required_free_bytes': durable.MIN_FREE_BYTES + projected_bytes - journal.size}
    if (sequence > durable.MAX_RECEIPTS or projected_bytes > durable.MAX_JOURNAL_BYTES
            or largest_receipt > MAX_BYTES or largest_input > MAX_BYTES
            or free < capacity['required_free_bytes']):
        failure = ImportBlocked('BLOCKED_DATA', 'receiver_capacity')
        failure.capacity = capacity
        raise failure


def import_sources(*, opportunities, decisions, registry, registry_sha256, target, source_id, now_ms, since_ms=0):
    """Validate complete source snapshots before creating/writing the receiver.

    Inputs are supplied files only. Journal replays use a stable source/opp/policy
    identity and reject revisions, including changed opportunity/context evidence.
    """
    try:
        require(timestamp(since_ms), 'invalid_since_ms')
        op, dec, destination = map(_safe_path, (opportunities, decisions, target))
        require(op.name == 'opportunities.jsonl' and dec.name == 'decisions.jsonl', 'source_filename_contract')
        require(op != dec and not os.path.samefile(op, dec), 'source_alias')
        for source in (op, dec):
            require(destination != source and destination not in source.parents
                    and source.parent != destination, 'source_target_overlap')
            if destination.exists():
                for name in ('journal.jsonl', 'writer.lock'):
                    candidate = destination / name
                    require(not candidate.exists() or not os.path.samefile(source, candidate), 'source_target_alias')
        events = _events(_read_chain(op), _read_chain(dec, since_ms=since_ms), registry, registry_sha256,
                         source_id, now_ms, {'opportunities': str(op), 'decisions': str(dec)})
        with BrainEventJournal(destination) as journal:
            # Preflight conflicts for all rows before appending any new ones.
            for bundle in events:
                old = journal.receipts.get(bundle['request_id'])
                require(old is None or old['input_sha256'] == digest(bundle), 'source_revision_conflict')
            _preflight_capacity(journal, events)
            return [journal.process(bundle) for bundle in events]
    except ImportBlocked:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ImportBlocked('BLOCKED_DATA', 'source_import_failed') from error
