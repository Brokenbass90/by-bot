"""Read-only reconciliation of the already-spent V1.1 journals.

No evaluator, allocator, scorer, source outcome adapter or new decisions run.
The only runner call is its pure input-pin verifier. All calculations below
reconcile recorded admissions/releases/cash; they cannot rescue the verdict.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
RUN = BASE / 'run_v1_1'
PIN = '7f2968c722b4c1bc617c65e7c9f497fffc59108b1fa2318b7004ad33e5a5d60a'
ARMS = ('RAW_SAFE', 'FOUNDATION', 'BRAIN_DET')
sys.path.insert(0, str(ROOT))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify():
    from research_lab.brain_v2_v1_1_run import verify_inputs
    adapter, folds, prospective = verify_inputs(ROOT, (BASE / 'PREPARATION_MANIFEST.json').read_bytes(), PIN)
    terminal = json.loads((RUN / 'TERMINAL.json').read_bytes())
    assert terminal['manifest_sha256'] == PIN and terminal['filter_runs'] == 1
    assert terminal['run_permission_consumed'] is True
    assert terminal['orders_allowed'] is False and terminal['money_authority'] is False
    artifacts = json.loads((RUN / 'ARTIFACTS.json').read_bytes())
    assert artifacts == terminal['artifacts']
    integrity = {}

    def rows(name):
        info = artifacts[name]
        path = RUN / info['path']
        assert path.parent == RUN and sha(path.read_bytes()) == info['compressed_sha256']
        assert path.stat().st_size == info['compressed_bytes']
        count, size, previous = 0, 0, '0' * 64
        with gzip.open(path, 'rb') as stream:
            for raw in stream:
                record = json.loads(raw)
                count += 1; size += len(raw)
                assert record['sequence'] == count and record['previous_sha256'] == previous
                body = {k: v for k, v in record.items() if k != 'sha256'}
                assert record['sha256'] == sha(canonical(body))
                assert raw == canonical(record) + b'\n'
                previous = record['sha256']
                yield record['data']
        assert count == info['records'] and size == info['raw_bytes']
        assert previous == info['last_record_sha256']
        integrity[name] = {'status': 'PASS', **info}

    accepted = {arm: {} for arm in ARMS}
    entries = {arm: defaultdict(list) for arm in ARMS}
    rejected = {arm: Counter() for arm in ARMS}
    seen, excluded, excluded_by_fold = set(), [], Counter()
    boundaries = [1688169600000, 1704067200000, 1719792000000, 1735689600000]
    for row in rows('paired_decisions'):
        key = row['opportunity_id']; at = row['tick_ms']
        assert key not in seen and at == row['opportunity']['t_available']
        assert at % 900000 == 0 and at < terminal['new_entry_end_exclusive_ms']
        assert set(row['arms']) == set(ARMS)
        seen.add(key)
        lev = Decimal(str(row['entry_metadata']['lev']))
        infeasible = lev > 100
        if infeasible:
            assert row['context'] is None
            excluded.append(key)
            fold = max(i for i, boundary in enumerate(boundaries) if at >= boundary)
            excluded_by_fold[f"{fold}|{row['opportunity']['sleeve']}"] += 1
        for arm, decision in row['arms'].items():
            if infeasible:
                assert decision['accepted'] is False and decision['reason'] == 'infeasible_stop_lev'
                assert all(decision[k] is None for k in ('z', 'rank', 'risk_usd', 'multiplier', 'table_sha256', 'cold_start'))
            else:
                assert decision['reason'] != 'infeasible_stop_lev'
            if decision['accepted']:
                assert lev <= 100
                accepted[arm][key] = row
                entries[arm][at].append((decision['rank'], key))
            else:
                rejected[arm][decision['reason']] += 1
    assert len(seen) == terminal['opportunities']
    assert dict(excluded_by_fold) == terminal['infeasible_stop_lev_by_sleeve_fold']
    summaries, closed = {}, {}
    with localcontext() as ctx:
        ctx.prec = 50
        for arm in ARMS:
            native = terminal['arms'][arm]
            E = Decimal(100000); fold_net = [Decimal(0)] * 4
            counts, unknown, symbols = Counter(), Counter(), Counter()
            records = {}; positive = negative = Decimal(0)
            slip = funding = turnover = commission = unknown_risk = Decimal(0)
            unknown_hours = 0
            for row in rows('closed_' + arm):
                key = row['opportunity_id']
                assert key in accepted[arm] and key not in records
                entry = accepted[arm][key]
                assert row['entry_ms'] == entry['tick_ms']
                assert row['risk_usd'] == entry['arms'][arm]['risk_usd']
                assert Decimal(row['lev']) == Decimal(str(entry['entry_metadata']['lev'])) <= 100
                assert row['release_ms'] == row['entry_ms'] + row['hours'] * 3600000
                assert row['notional_usd'] and Decimal(row['notional_usd']) == Decimal(row['risk_usd']) * Decimal(row['lev'])
                counts[row['status']] += 1
                if row['status'] == 'KNOWN':
                    assert Decimal(row['r_pnl_usd']) == Decimal(str(row['R'])) * Decimal(row['risk_usd'])
                    assert Decimal(row['slippage_usd']) == Decimal('.0004') * Decimal(row['notional_usd'])
                    net = Decimal(row['net_usd'])
                    assert net == Decimal(row['r_pnl_usd']) - Decimal(row['slippage_usd']) - Decimal(row['funding_usd'])
                    E += net; fold_net[row['entry_fold']] += net
                    positive += max(Decimal(0), net); negative += min(Decimal(0), net)
                    slip += Decimal(row['slippage_usd']); funding += Decimal(row['funding_usd'])
                    turnover += 2 * Decimal(row['notional_usd'])
                    commission += Decimal('.0012') * Decimal(row['notional_usd'])
                else:
                    assert row['status'] == 'FUNDING_UNKNOWN' and row['net_usd'] is None
                    unknown[row['funding_reason']] += 1; symbols[row['symbol']] += 1
                    unknown_risk += Decimal(row['risk_usd']); unknown_hours += row['hours']
                records[key] = row
            assert set(records) == set(accepted[arm]) and native['open_positions'] == 0
            assert len(records) == native['closed'] == native['accepted']
            assert counts['KNOWN'] == native['known'] and counts['FUNDING_UNKNOWN'] == native['funding_unknown']
            assert E == Decimal(native['final_realized_usd'])
            assert E - 100000 == Decimal(native['net_usd'])
            assert fold_net == list(map(Decimal, native['fold_net_usd']))
            assert dict(rejected[arm]) == native['rejections']
            assert dict(unknown) == native['unknown_by_reason'] and dict(symbols) == native['unknown_by_symbol']
            assert counts['FUNDING_UNKNOWN'] / len(records) == native['funding_unknown_fraction']
            for field, actual in [('slippage_usd_known', slip), ('signed_funding_usd_known', funding),
                ('roundtrip_turnover_usd_known', turnover), ('commission_already_in_R_model_usd_known', commission),
                ('unknown_risk_usd', unknown_risk), ('pf_known', positive / abs(negative)),
                ('expectancy_usd_known', (positive + negative) / counts['KNOWN'])]:
                assert Decimal(native[field]) == actual, (arm, field)
            assert unknown_hours == native['unknown_slot_hours']
            closed[arm] = records
            summaries[arm] = dict(closed=len(records), known=counts['KNOWN'], funding_unknown=counts['FUNDING_UNKNOWN'],
                final_realized_usd=str(E), net_usd=str(E - 100000), fold_net_usd=list(map(str, fold_net)),
                accepted_lev_over_100=0, unknown_pnl_excluded=True, rejections=dict(rejected[arm]))

        active = {arm: {} for arm in ARMS}
        released = {arm: defaultdict(list) for arm in ARMS}
        E = {arm: Decimal(100000) for arm in ARMS}
        peaks = {arm: [Decimal(100000), Decimal(100000), Decimal(0), Decimal(0)] for arm in ARMS}
        risk_fractions = {arm: Decimal(0) for arm in ARMS}
        max_notional = {arm: Decimal(0) for arm in ARMS}
        for arm in ARMS:
            for key, row in closed[arm].items():
                released[arm][row['release_ms']].append(key)
        count = 0
        for tick in rows('equity_ticks'):
            at = tick['tick_ms']
            assert tick['before_current_packet'] is True
            assert at == terminal['test_start_ms'] + count * 900000
            count += 1
            for arm in ARMS:
                for key in sorted(released[arm].get(at, [])):
                    row = active[arm].pop(key)
                    if row['status'] == 'KNOWN': E[arm] += Decimal(row['net_usd'])
                saved = tick['arms'][arm]
                assert Decimal(saved['realized_usd']) == E[arm]
                env = E[arm] + sum((min(Decimal(-1), Decimal(str(row['R']))) * Decimal(row['risk_usd'])
                    for row in active[arm].values() if row['status'] == 'KNOWN'), Decimal(0))
                risk = sum((Decimal(row['risk_usd']) for row in active[arm].values()), Decimal(0))
                assert Decimal(saved['env_usd']) == env and Decimal(saved['open_risk_usd']) == risk
                assert saved['open_positions'] == len(active[arm])
                peak_env, peak_E, dd_env, dd_E = peaks[arm]
                peak_env = max(peak_env, env); peak_E = max(peak_E, E[arm])
                dd_env = max(dd_env, (peak_env - env) / peak_env)
                dd_E = max(dd_E, (peak_E - E[arm]) / peak_E)
                assert Decimal(saved['dd_env']) == dd_env and Decimal(saved['dd_realized']) == dd_E
                peaks[arm] = [peak_env, peak_E, dd_env, dd_E]
                risk_fractions[arm] += risk / (Decimal('.06') * E[arm])
                for _, key in sorted(entries[arm].get(at, [])):
                    active[arm][key] = closed[arm][key]
                # Native V1.1 diagnostics use the default 28-digit context.
                with localcontext() as diagnostic_ctx:
                    diagnostic_ctx.prec = 28
                    gross = sum((Decimal(row['notional_usd']) for row in active[arm].values()), Decimal(0))
                    max_notional[arm] = max(max_notional[arm], gross / E[arm])
        assert at == terminal['last_tick_ms'] and terminal['release_only_tail'] is True
        for arm in ARMS:
            native = terminal['arms'][arm]
            assert not active[arm] and count == native['ticks']
            assert peaks[arm][2] == Decimal(native['dd_env'])
            assert peaks[arm][3] == Decimal(native['dd_realized_reference'])
            assert risk_fractions[arm] / count == Decimal(native['average_open_risk_budget_fraction'])
            assert max_notional[arm] == Decimal(terminal['max_open_notional_over_equity'][arm])
        wins = [Decimal(a) >= Decimal(b) for a, b in zip(terminal['arms']['BRAIN_DET']['fold_net_usd'],
            terminal['arms']['FOUNDATION']['fold_net_usd'])]
        dd_ok = peaks['BRAIN_DET'][2] <= Decimal('1.1') * peaks['FOUNDATION'][2]
        assert wins == terminal['fold_noninferior'] and sum(wins) == terminal['fold_noninferior_count']
        assert dd_ok == terminal['dd_env_gate_pass'] and sum(wins) < 3
        assert all(a['funding_unknown'] * 20 <= a['closed'] for a in terminal['arms'].values())
        assert terminal['status'] == 'STOP_V1'

    old_run = ROOT / 'reports/evidence/brain_v2_develop_20261012/run_a5_a6'
    old_pins = json.loads((old_run / 'POST_RUN_INTEGRITY.json').read_bytes())['sealed_receipts']
    for name, expected in old_pins.items(): assert sha((old_run / name).read_bytes()) == expected
    for row in json.loads((old_run / 'ARTIFACTS.json').read_bytes()).values():
        assert sha((old_run / row['path']).read_bytes()) == row['compressed_sha256']
    foreign = sha((ROOT / 'configs/allowlist_change_log.json').read_bytes())
    assert foreign == 'add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1'
    return dict(status='RECORDED_JOURNAL_CASH_AND_PINS_PASS', terminal_status=terminal['status'],
        verified_at_utc=datetime.now(timezone.utc).isoformat(), manifest_sha256=PIN,
        source_manifest_sha256=adapter.manifest_sha256, source_files=len(adapter.rows),
        filter_runs=1, additional_evaluator_runs=0, new_decisions=0,
        table_pins=[t.source_hash for t in folds], prospective_table_pin=prospective.source_hash,
        ledger_integrity=integrity, total_records=sum(r['records'] for r in artifacts.values()),
        equity_ticks=count, opportunities=len(seen), arms=summaries,
        a7_excluded=len(excluded), a7_excluded_by_sleeve_fold=dict(excluded_by_fold),
        a7_rejected_before_context_and_score=True, full_release_tail_no_open_positions=True,
        recorded_dd_env_and_cash_pass=True, original_v1_receipts_and_ledgers_unchanged=True,
        foreign_allowlist_sha256=foreign, orders_allowed=False, money_authority=False,
        live_or_vps_operations=0, verifier_sha256=sha(Path(__file__).read_bytes()),
        sealed_run_files={p.name:sha(p.read_bytes()) for p in sorted(RUN.glob('*.json'))},
        owner_authorization_sha256=sha((BASE / 'OWNER_AUTHORIZATION_20261012.json').read_bytes()))


if __name__ == '__main__':
    result = verify()
    with (BASE / 'POST_RUN_RECONCILIATION.json').open('xb') as file:
        file.write(json.dumps(result, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({k:result[k] for k in ('status', 'terminal_status', 'filter_runs',
        'additional_evaluator_runs', 'total_records', 'a7_excluded', 'orders_allowed')}))
