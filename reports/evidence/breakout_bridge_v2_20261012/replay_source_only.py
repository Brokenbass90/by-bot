"""Reproduce two already-parity-consumed AVAX plans; never simulate outcomes."""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timezone
import subprocess
import hashlib
import json
import gzip
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from strategies import event_expansion_retest_long_mtf_v1 as mtf
from bot.event_long_mtf_execution_bridge_v1 import bridge_mtf_research_plan_v1, EventLongMTFBridgeError as OldError
from bot.event_long_mtf_execution_bridge_v2 import bridge_mtf_research_plan_v2

REF = 'e22c0e0b4837b9dbfea89fb6ea72baa1a510f5d7'
BASE = Path(__file__).resolve().parent
SIBLING = ROOT.parent / 'bybit-bot-clean-v28'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run():
    manifest_raw = subprocess.check_output(['git', 'show', REF+':research_lab/data/breakout_m5_v2/MANIFEST.json'], cwd=SIBLING)
    man = json.loads(manifest_raw); prov = sha(manifest_raw)
    start = int(datetime(2026, 8, 12, tzinfo=timezone.utc).timestamp()*1000)
    end = int(datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp()*1000)
    rows, sources = [], []
    for month in ('2026-08', '2026-09', '2026-10'):
        key = f'AVAXUSDT/AVAXUSDT_{month}.jsonl.gz'
        path = SIBLING / 'research_lab/data/breakout_m5_v2' / key
        raw = path.read_bytes(); body = gzip.decompress(raw)
        assert sha(body) == man['fayly'][key]['sha256']
        sources.append(dict(path=str(path), compressed_sha256=sha(raw), manifest_uncompressed_sha256=sha(body)))
        for line in body.splitlines():
            r = json.loads(line); ts = int(r[0])
            if start <= ts < end:
                # Same exact six-column projection as frozen breakout_paritet_v2.py.
                # Venue column7 is turnover, not part of canonical OHLCV.
                rows.append([ts, *map(float, r[1:6])])
    rows.sort(key=lambda r: r[0])
    assert rows[0][0] == start and rows[-1][0]+mtf.M5 == end
    assert all(b[0]-a[0] == mtf.M5 for a, b in zip(rows, rows[1:]))
    core = {p: sha((ROOT/p).read_bytes()) for p in (
        'strategies/event_expansion_retest_long_mtf_v1.py', 'bot/level_snapshot_v1.py',
        'bot/closed_bar_aggregation_v1.py', 'bot/event_long_execution_v1.py',
        'bot/event_long_mtf_execution_bridge_v1.py')}
    for path, pin in core.items():
        assert sha(subprocess.check_output(['git', 'show', REF+':'+path], cwd=SIBLING)) == pin
    state, cases = None, []
    provider = 'bybit_v5_kline_linear_m5_breakout_m5_v2'
    while True:
        step = mtf.process_closed_m5_prefix('AVAXUSDT', rows, as_of_ms=end,
            provider_identity=provider, provider_fingerprint=prov, prior=state)
        state = step.state
        if step.plan is None: break
        level = state.active.event.level_snapshot
        count = state.source_count; prefix = rows[:count]
        assert prefix[-1][0]+mtf.M5 == step.plan.known_at_ms
        try:
            bridge_mtf_research_plan_v1(step.plan, state)
        except OldError as error:
            old_reason = str(error)
        else:
            raise AssertionError('reported V1 rejection not reproduced')
        assert old_reason == 'level lacks matching M5-to-HTF aggregation evidence'
        new = bridge_mtf_research_plan_v2(step.plan, state, raw_closed_m5=prefix)
        serialized = mtf.state_to_json(state)
        restored = mtf.state_from_json(serialized, expected_provider_fingerprint=prov,
            expected_cfg=mtf.EventExpansionRetestLongMTFConfigV1())
        assert new == bridge_mtf_research_plan_v2(restored.plan_outbox[0], restored, raw_closed_m5=prefix)
        assert new.frozen_plan.entry_reference == step.plan.entry_reference
        assert new.frozen_plan.frozen_stop == step.plan.stop_price
        cases.append(dict(mtf_plan_id=step.plan.plan_id, known_at_ms=step.plan.known_at_ms,
            raw_prefix_count=count, state_pri_plane=serialized, old_v1_reason=old_reason,
            v2_result=asdict(new), restart_exact=True,
            full_aggregate_count=level.source_provenance.output_count,
            window_count=new.receipt.level_window_count))
        print('AVAX', step.plan.plan_id, datetime.fromtimestamp(step.plan.known_at_ms/1000, timezone.utc).isoformat(), 'V1_BLOCKED V2_PASS', flush=True)
        # Pure local signal replay; no durable acknowledgement/shadow mutation.
        state = mtf.acknowledge_plan(state, step.plan.plan_id)
    assert len(cases) == 2
    maxcount = max(c['raw_prefix_count'] for c in cases)
    fixture = json.dumps(rows[:maxcount], separators=(',', ':'), allow_nan=False).encode()
    with (BASE/'avax_decision_prefix.json.gz').open('xb') as f:
        with gzip.GzipFile(filename='', fileobj=f, mode='wb', mtime=0) as z: z.write(fixture)
    with (BASE/'cases.json').open('x') as f:
        json.dump(cases, f, sort_keys=True, indent=2); f.write('\n')
    receipt = dict(status='BRIDGE_V2_SOURCE_ONLY_REPLAY_PASS', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        research_local_commit=REF, research_origin_at_intake='e2d668ce415c82c1c22c44454df84e168a8c5f7d',
        research_local_published=False, provider=provider, provider_manifest_sha256=prov,
        input_window=[start, end], plans=2, v1_rejects=2, v2_conversions=2,
        raw_source_files=sources, unchanged_core_pins=core,
        new_bridge_sha256=sha((ROOT/'bot/event_long_mtf_execution_bridge_v2.py').read_bytes()),
        fixture_canonical_sha256=sha(fixture), fixture_compressed_sha256=sha((BASE/'avax_decision_prefix.json.gz').read_bytes()),
        cases_sha256=sha((BASE/'cases.json').read_bytes()), fixture_rows=maxcount,
        mechanics_only=True, judge_runs=0, outcome_simulations=0, broker_calls=0,
        runtime_changes=0, orders_allowed=False, money_authority=False)
    with (BASE/'replay_receipt.json').open('x') as f:
        json.dump(receipt, f, sort_keys=True, indent=2); f.write('\n')
    print(json.dumps({k: receipt[k] for k in ('status', 'plans', 'v1_rejects', 'v2_conversions', 'fixture_rows')}, indent=2))


if __name__ == '__main__':
    run()
