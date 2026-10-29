"""File-only PUMP4 facts receiver. No policy execution or trading authority.

Input manifests are externally pinned capture evidence, not broker attestations.
Status receipt samples do not establish an exhaustive opportunity census. Advice
is deliberately UNKNOWN until a versioned, independently pre-recorded source is
available; historical model outcomes are never treated as fills.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from research_lab.brain_shadow_readonly_bridge_v1 import (
    BrainEventJournal, _preflight_capacity, require, sha, timestamp,
)
from research_lab.os2_shadow_bridge import BridgeBlocked, canonical, digest
from research_lab.os2_shadow_journal import strict_json
from research_lab.att1_lifecycle_journal import LifecycleJournal, JournalViolation

ObserverBlocked = BridgeBlocked
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
MAX_FILES = 512


def safe_path(value):
    p = Path(os.path.abspath(value))
    require(not any(x.is_symlink() for x in (p, *p.parents)), 'symlink_path')
    return p


def read_file(path):
    path = safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'source_file_type_links')
        require(before.st_size <= MAX_FILE_BYTES, 'source_byte_bound')
        raw = b''
        while len(raw) <= MAX_FILE_BYTES:
            part = os.read(fd, min(1024 * 1024, MAX_FILE_BYTES + 1 - len(raw)))
            if not part: break
            raw += part
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and len(raw) == before.st_size, 'source_changed')
        return raw
    finally:
        os.close(fd)


def expiry_status(now_ms, expires_ms, captured_ms, has_admission, inventory_complete, broker_flat):
    require(all(timestamp(t) for t in (now_ms, expires_ms, captured_ms)) and captured_ms <= now_ms,
            'expiry_clock')
    require(all(type(v) is bool for v in (has_admission, inventory_complete, broker_flat)), 'expiry_flags')
    if now_ms < expires_ms: return 'WAITING_WITHIN_ENTRY_PERIOD'
    if captured_ms < expires_ms: return 'UNKNOWN_NEED_POST_EXPIRY_CAPTURE'
    if has_admission: return 'ENTRY_PERIOD_EXPIRED_CUSTODY_CONTINUES'
    if inventory_complete and broker_flat: return 'NO_TRADE_CONFIRMED'
    return 'UNKNOWN_NEED_DURABLE_HISTORY_AND_BROKER_GET'


class ExecutionFactsJournal(BrainEventJournal):
    receipt_schema = 'PUMP4_READONLY_BRAIN_RECEIPT_V1'
    state_schema = 'PUMP4_READONLY_BRAIN_STATE_V1'


def _bundle(event):
    event = dict(event, money_authority=False, execution_authority=False,
                 accounting_authority=False, orders_allowed=False)
    return {'request_id': event['event_id'], 'event': event}


def import_capture(manifest_path, manifest_sha256, target, *, expected_scope, expected_config):
    """Validate all source files before receiver writes. Never repairs sources.

    Every receipt has stable (scope, run_id, tick) identity and immutable source
    hash. Later lifecycle events receive separate identities. Identity-derived shards keep
    the existing journal's strict bounds, with every batch preflighted.
    """
    journals = []
    try:
        path, target = safe_path(manifest_path), safe_path(target)
        source = path.parent
        require(target != source and source not in target.parents and target not in source.parents,
                'source_target_overlap')
        raw = read_file(path)
        require(sha(manifest_sha256) and hashlib.sha256(raw).hexdigest() == manifest_sha256, 'manifest_pin')
        m = strict_json(raw)
        require(m.get('schema') == 'PUMP4_OBSERVER_CAPTURE_V1', 'manifest_schema')
        require(sha(expected_scope) and sha(expected_config) and m.get('scope_sha256') == expected_scope
                and m.get('config_sha256') == expected_config, 'scope_config_pin')
        require(timestamp(m.get('observed_ms')), 'capture_clock')
        require(m.get('coverage') == 'SAMPLED_STATUS_NOT_OPPORTUNITY_CENSUS', 'coverage_contract')
        files = m.get('files')
        require(isinstance(files, list) and 2 <= len(files) <= MAX_FILES, 'capture_file_bound')
        artifacts = []; seen = set(); total = 0
        for info in files:
            name = info['name']
            require(isinstance(name, str) and Path(name).name == name and name not in ('.', '..', 'manifest.json')
                    and name not in seen, 'capture_filename')
            seen.add(name)
            data = read_file(source / name); total += len(data)
            require(total <= MAX_CAPTURE_BYTES and sha(info.get('sha256')) and
                    hashlib.sha256(data).hexdigest() == info['sha256'], 'source_pin_or_bound')
            require(info.get('kind') in ('scope', 'config', 'receipt', 'lifecycle'), 'capture_kind')
            artifacts.append((info, data))
        scopes = [data for info, data in artifacts if info['kind'] == 'scope']
        configs = [data for info, data in artifacts if info['kind'] == 'config']
        require(len(scopes) == len(configs) == 1 and digest(strict_json(scopes[0])) == expected_scope
                and hashlib.sha256(configs[0]).hexdigest() == expected_config, 'scope_config_bytes')
        scope = strict_json(scopes[0]); config = strict_json(configs[0])
        if 'runner_config_sha256' in scope:
            require(scope['runner_config_sha256'] == digest({k:v for k,v in config.items()
                    if k not in {'authority','_config_path','_config_sha256'}}), 'scope_config_binding')
        if 'scope_sha256' in config:
            require(config['scope_sha256'] == expected_scope, 'config_scope_binding')
        bundles = []; receipt_count = lifecycle_count = 0; partial = False
        for info, data in artifacts:
            kind = info['kind']
            if kind in ('scope', 'config'): continue
            if kind == 'receipt':
                row = strict_json(data)
                require(row.get('schema') == 'PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1'
                        and row.get('scope_sha256') == expected_scope
                        and row.get('runner_config_sha256') == expected_config
                        and row.get('mode') == 'OWNER_TINY_LIVE', 'receipt_binding')
                ts = row.get('observed_ms')
                require(timestamp(ts) and ts <= m['observed_ms'] and type(row.get('tick')) is int
                        and row['tick'] >= 0 and isinstance(row.get('run_id'), str) and bool(row['run_id']),
                        'receipt_identity_clock')
                key = digest({'scope': expected_scope, 'run_id': row['run_id'], 'tick': row['tick']})
                event = dict(schema='PUMP4_LIVE_OBSERVATION_V1', event_id=key,
                             record_kind='ACTUAL_EXECUTION_RECEIPT', observed_ms=ts,
                             scope_sha256=expected_scope, config_sha256=expected_config,
                             source_sha256=info['sha256'], receipt=row,
                             brain_advice_comparison='UNKNOWN_NO_CAUSAL_VERSIONED_ADVICE',
                             net_pnl_status='NOT_PROVEN', coverage=m['coverage'])
                receipt_count += 1; bundles.append(_bundle(event))
            else:
                # Capturer copies only the completed newline prefix, flags any
                # uncompleted tail, and never edits the production journal.
                require(type(info.get('partial_tail_bytes', 0)) is int and info.get('partial_tail_bytes',0) >= 0,
                        'partial_tail_contract')
                partial |= bool(info.get('partial_tail_bytes', 0))
                # Parse the already-pinned snapshot, never reopen a mutable
                # source path. Existing journal validator operates on a private
                # unlinked tempfile descriptor; no source repair/write occurs.
                with tempfile.TemporaryFile() as snapshot:
                    snapshot.write(data);snapshot.flush()
                    rows = LifecycleJournal(source / info['name'], max_bytes=MAX_FILE_BYTES)._load(snapshot.fileno())[0]
                for row in rows:
                    ts = row.get('observed_ms', row.get('observation', {}).get('observed_ms'))
                    require(timestamp(ts) and ts <= m['observed_ms'], 'lifecycle_clock')
                    # Source event ID alone is not globally unique across flows.
                    identity = {'scope': expected_scope, 'stream': info.get('source_stream', info['name']),
                                'event_id': row['event_id']}
                    event = dict(schema='PUMP4_LIVE_OBSERVATION_V1', event_id=digest(identity),
                                 record_kind='ACTUAL_LIFECYCLE_EVENT', observed_ms=ts,
                                 scope_sha256=expected_scope, source_event=row,
                                 source_event_sha256=digest(row), net_pnl_status='NOT_PROVEN',
                                 brain_advice_comparison='UNKNOWN_NO_CAUSAL_VERSIONED_ADVICE')
                    lifecycle_count += 1; bundles.append(_bundle(event))
        grouped = defaultdict(list); unique = {}
        for bundle in bundles:
            key = bundle['request_id']
            require(key not in unique or unique[key] == bundle, 'source_identity_conflict')
            if key in unique: continue
            unique[key] = bundle
            # Stable bucket prevents a changed source timestamp moving the same
            # receipt into a new shard and bypassing revision detection.
            grouped[key[:2]].append(bundle)
        # Open/validate all existing shards before the first append. No all-shard
        # atomic commit is promised; a failed run safely replays stable identities.
        parent = target / expected_scope
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        new = 0
        for hour, items in sorted(grouped.items()):
            journal = ExecutionFactsJournal(parent / hour); journals.append((journal, items))
            for bundle in items:
                old = journal.receipts.get(bundle['request_id'])
                require(old is None or old['input_sha256'] == digest(bundle), 'source_revision_conflict')
            _preflight_capacity(journal, items)
        for journal, items in journals:
            for bundle in items:
                new += bundle['request_id'] not in journal.receipts
                journal.process(bundle)
        return dict(schema='PUMP4_OBSERVER_IMPORT_V1', status='IMPORTED', new_events=new,
                    receipt_events=receipt_count, lifecycle_events=lifecycle_count,
                    manifest_sha256=manifest_sha256, scope_sha256=expected_scope,
                    coverage=m['coverage'], source_partial_tail=partial,
                    source_completeness='UNKNOWN_PARTIAL_TAIL' if partial else 'CAPTURED_PREFIX_ONLY',
                    brain_advice_comparison='UNKNOWN_NO_CAUSAL_VERSIONED_ADVICE',
                    money_authority=False, orders_allowed=False, broker_requests=0, broker_writes=0)
    except ObserverBlocked:
        raise
    except (OSError, ValueError, TypeError, KeyError, JournalViolation) as error:
        raise ObserverBlocked('BLOCKED_DATA', 'observer_source_import_failed') from error
    finally:
        for journal, _ in journals: journal.close()


def audit_advice(path):
    """Verify existing legacy advice bytes only; never execute or score a Brain.

    A producer's do_ishoda flag means 'before its outcome', not independently
    observed before the LIVE entry. Even a version label alone cannot prove that.
    """
    from research_lab.brain_shadow_readonly_bridge_v1 import producer_hash
    raw=read_file(path)
    require(not raw or raw.endswith(b'\n'), 'advice_partial_tail')
    previous='0'*64;count=pump4=versioned=0
    for line in raw.splitlines():
        require(bool(line.strip()), 'advice_blank_row')
        row=strict_json(line); claimed=row.get('hash')
        require(row.get('prev')==previous and sha(claimed) and
                producer_hash({k:v for k,v in row.items() if k!='hash'})==claimed,'advice_chain')
        previous=claimed;count+=1
        is_pump4=row.get('noga')=='PUMP4'
        pump4+=is_pump4
        versioned+=is_pump4 and row.get('brain_version') in ('V1.1','V1.2')
    return dict(schema='PUMP4_BRAIN_ADVICE_SOURCE_AUDIT_V1',source_sha256=hashlib.sha256(raw).hexdigest(),
                chain_records=count,pump4_rows=pump4,version_label_rows=versioned,
                comparison_status='UNKNOWN_NO_CAUSAL_VERSIONED_ADVICE',
                missing_contract='version+policy_sha+stable_signal_id+independent_predecision_availability_receipt',
                money_authority=False,orders_allowed=False)
