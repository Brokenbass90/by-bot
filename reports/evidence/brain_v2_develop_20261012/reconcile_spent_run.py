"""Forensics of the spent run only. Never imports/runs the allocator or judge.

Reads sealed journals and original rows for ALREADY admitted open positions.
Reconciles recorded cash, then explains releases at the first unsaved tick.
Does not choose/admit positions, advance the simulation or produce a filter verdict.
"""
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
RUN = BASE / 'run_a5_a6'
SOURCE = ROOT / '.superpowers/sdd/brain-v2-develop-20261012/source'
ARMS = ('RAW_SAFE', 'FOUNDATION', 'BRAIN_DET')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def pin(raw):
    return hashlib.sha256(raw).hexdigest()


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def run():
    artifacts = json.loads((RUN / 'ARTIFACTS.json').read_bytes())
    integrity = {}

    def rows(name):
        info = artifacts[name]
        path = RUN / info['path']
        assert pin(path.read_bytes()) == info['compressed_sha256']
        count, size, previous = 0, 0, '0' * 64
        with gzip.open(path, 'rb') as f:
            for raw in f:
                record = json.loads(raw)
                count += 1; size += len(raw)
                assert record['sequence'] == count and record['previous_sha256'] == previous
                body = {k: v for k, v in record.items() if k != 'sha256'}
                assert record['sha256'] == pin(canonical(body))
                assert raw == canonical(record) + b'\n'
                previous = record['sha256']
                yield record['data']
        assert count == info['records'] and size == info['raw_bytes']
        assert previous == info['last_record_sha256']
        integrity[name] = {'status': 'PASS', **info}

    accepted = {a: {} for a in ARMS}
    accepted_counts = Counter()
    rejected = {a: Counter() for a in ARMS}
    for row in rows('paired_decisions'):
        for arm, decision in row['arms'].items():
            if decision['accepted']:
                accepted[arm][row['opportunity_id']] = row
                accepted_counts[arm] += 1
            else:
                rejected[arm][decision['reason']] += 1

    summaries, closed = {}, {}
    with localcontext() as ctx:
        ctx.prec = 50
        for arm in ARMS:
            E = Decimal(100000); counts = Counter(); unknown = Counter(); symbols = Counter()
            events = []
            for row in rows('closed_' + arm):
                assert row['opportunity_id'] in accepted[arm]
                del accepted[arm][row['opportunity_id']]
                counts[row['status']] += 1
                if row['status'] == 'KNOWN':
                    # Independent algebraic reconciliation of already recorded terminal cash.
                    assert Decimal(row['r_pnl_usd']) == Decimal(str(row['R'])) * Decimal(row['risk_usd'])
                    assert Decimal(row['slippage_usd']) == Decimal('.0004') * Decimal(row['notional_usd'])
                    assert Decimal(row['net_usd']) == (Decimal(row['r_pnl_usd']) - Decimal(row['slippage_usd']) - Decimal(row['funding_usd']))
                    E += Decimal(row['net_usd'])
                else:
                    assert row['net_usd'] is None
                    unknown[row['funding_reason']] += 1; symbols[row['symbol']] += 1
                events.append(row)
            closed[arm] = events
            summaries[arm] = dict(recorded_closed=len(events), recorded_known=counts['KNOWN'],
                recorded_unknown=counts['FUNDING_UNKNOWN'], unknown_by_reason=dict(unknown),
                unknown_by_symbol=dict(symbols), accepted=accepted_counts[arm],
                rejections=dict(rejected[arm]), still_open_at_saved_boundary=len(accepted[arm]),
                realized_from_recorded_closed_usd=str(E), partial_only=True)

        E = {a: Decimal(100000) for a in ARMS}; cursor = {a: 0 for a in ARMS}
        count = 0; last = None
        for tick in rows('equity_ticks'):
            at = tick['tick_ms']
            assert last is None or at == last['tick_ms'] + 900000
            for arm in ARMS:
                events = closed[arm]
                while cursor[arm] < len(events) and events[cursor[arm]]['release_ms'] <= at:
                    row = events[cursor[arm]]
                    if row['status'] == 'KNOWN': E[arm] += Decimal(row['net_usd'])
                    cursor[arm] += 1
                assert E[arm] == Decimal(tick['arms'][arm]['realized_usd'])
            count += 1; last = tick
        for arm in ARMS:
            assert cursor[arm] == len(closed[arm])
            assert E[arm] == Decimal(summaries[arm]['realized_from_recorded_closed_usd'])
        failure_tick = last['tick_ms'] + 900000

        manifest = json.loads((BASE / 'adapter_manifest.json').read_bytes())
        sources = {r['path']: r for r in manifest['files']}
        source_hashes = {}

        def source(path):
            raw = (SOURCE / path).read_bytes()
            assert pin(raw) == sources[path]['sha256']
            source_hashes[path] = pin(raw)
            return json.loads(raw)

        streams = {}
        for path, descriptor in sources.items():
            if descriptor['role'] == 'trade_stream':
                for row in source(path):
                    key = (row['leg'], row['sym'], row['side'], row['ts'])
                    assert key not in streams
                    streams[key] = row

        pending = {}
        for arm in ARMS:
            due = []
            for key, record in sorted(accepted[arm].items()):
                op = record['opportunity']; decision = record['arms'][arm]
                row = streams[(op['sleeve'], op['symbol'], op['side'], op['t_signal'])]
                release = op['t_available'] + row['hours'] * 3600000
                if release != failure_tick: continue
                archive = source('external/funding/' + op['symbol'] + '.json')
                timestamps = [r[0] for r in archive['funding']]
                rates = [r[1] for r in archive['funding']]
                a = bisect_right(timestamps, op['t_available']) - 1
                b = bisect_left(timestamps, release)
                assert a >= 10 and b < len(timestamps)
                gaps = sorted(timestamps[i] - timestamps[i-1] for i in range(a-9, a+1))
                median = Decimal(gaps[4] + gaps[5]) / 2
                assert all(timestamps[i] - timestamps[i-1] <= median for i in range(a+1, b+1))
                selected = rates[a+1:bisect_right(timestamps, release)]
                rate_sum = sum((Decimal(str(r)) for r in selected), Decimal(0))
                risk = Decimal(decision['risk_usd']); lev = Decimal(str(row['lev']))
                notional = risk * lev; r_cash = risk * Decimal(str(row['R']))
                slip = Decimal('.0004') * notional
                funding = (1 if op['side'] == 'long' else -1) * notional * rate_sum
                net = r_cash - slip - funding
                due.append(dict(opportunity_id=key, source_row=row, source_sha256=op['source_hash'],
                    entry_ms=op['t_available'], release_ms=release, risk_usd=str(risk),
                    notional_usd=str(notional), funding_status='A6_COVERED', funding_rate_sum=str(rate_sum),
                    funding_settlement_count=len(selected), r_pnl_usd=str(r_cash),
                    slippage_usd=str(slip), funding_usd=str(funding), net_usd=str(net)))
            projected = E[arm]
            for row in due: projected += Decimal(row['net_usd'])
            pending[arm] = dict(due_releases=due, projected_equity_after_due_usd=str(projected),
                nonpositive=projected <= 0, status='FORENSIC_ARITHMETIC_NOT_SAVED_ENGINE_STATE')

    result = dict(schema='BRAIN_V2_SPENT_RUN_PARTIAL_RECONCILIATION', status='PARTIAL_EVIDENCE_RECONCILED',
        allocator_runs=0, judge_runs=0, no_new_decisions=True, filter_permission_spent=True,
        started_sha256=pin((RUN/'STARTED.json').read_bytes()),
        terminal_sha256=pin((RUN/'TERMINAL.json').read_bytes()),
        artifacts_sha256=pin((RUN/'ARTIFACTS.json').read_bytes()),
        ledger_integrity=integrity, recorded_ticks=count,
        last_saved_tick_ms=last['tick_ms'], last_saved_tick_utc=utc(last['tick_ms']),
        first_unsaved_tick_ms=failure_tick, first_unsaved_tick_utc=utc(failure_tick),
        last_saved_arms=last['arms'], partial_summaries=summaries,
        first_unsaved_release_arithmetic=pending, traced_source_hashes=source_hashes,
        complete_four_fold_comparison=False, money_authority=False, orders_allowed=False,
        limitation='Failure tick was not journaled: engine raises before returning the tick. Due cash is source-bound forensic arithmetic, not a recovered full engine state or second run.')
    target = RUN / 'PARTIAL_CAPITAL_RECONCILIATION.json'
    payload = canonical(result) + b'\n'
    if target.exists(): assert target.read_bytes() == payload
    else:
        with target.open('xb') as f: f.write(payload)
    print(json.dumps({k:result[k] for k in ('status','recorded_ticks','last_saved_tick_utc','first_unsaved_tick_utc')}, indent=2))
    for arm in ARMS:
        print(arm, json.dumps(pending[arm], indent=2))


if __name__ == '__main__':
    run()
