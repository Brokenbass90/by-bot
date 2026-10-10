#!/usr/bin/env python3
"""Prepare the existing BTC/ETH bounce source intake. Never run a strategy.

Writes a new exclusive directory; cannot overwrite sealed sources. No network,
credentials, signals, performance evaluator, environment overlay or broker path.
PIT lineage/funding/independent validation remain explicit research blockers.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research_lab.bounce_range_source_packet import HOUR_MS, derive_closed_h4

INPUT_PINS = {
    'research_lab/data/h1/BTCUSDT.npz': '811c06ea3a1aadc522da4d67106591efa77905d128fac5f245b714bd33a75e49',
    'research_lab/data/h1/ETHUSDT.npz': '9c669dc6c1de71d561f42cc971c7083515116bf83086f6f556d89ba5f4bcbd8e',
    'configs/research/bounce1_majors_three_regime_prereg_20260802.json': '62f196e58e86a97c94223208164f5ff594bc06634f38ec7eb08c4e9299311a37',
    'configs/research/bounce1_exact_three_regime_prereg_20260802.json': '997e8b0524f256f636c31d42560a291bf752e67342e28dd50d59f1d147694361',
    'configs/approved_strategy_params.env': '52de3558c4afd3727211554d1f5365ee00df19479850a1bda84ab9a1b6b93184',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def frozen_bounce_defaults(source):
    """Read literal config defaults only; never import/construct the strategy."""
    tree = ast.parse(source)
    cfg = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == 'AltSupportBounceV1Config')
    defaults = {n.target.id: ast.literal_eval(n.value) for n in cfg.body
                if isinstance(n, ast.AnnAssign)}
    defaults.update(sl_atr_mult=1.6, tp1_frac=0.15, trail_atr_mult=0.0)
    return defaults


def jsonl(rows):
    return ''.join(json.dumps(r, separators=(',', ':'), allow_nan=False) + '\n'
                   for r in rows).encode()


def prepare(output):
    prepared_ms = time.time_ns() // 1_000_000
    source_paths = ['research_lab/build_h1_bundle.py', 'bot/closed_bar_aggregation_v1.py',
                    'research_lab/bounce_range_source_packet.py', 'scripts/prepare_bounce_range_sources.py',
                    'strategies/alt_support_bounce_v1.py', *INPUT_PINS]
    # Snapshot once; all parsing and identity declarations use these SAME bytes.
    payloads = {name: (ROOT / name).read_bytes() for name in source_paths}
    consumed_hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()}
    for name, expected in INPUT_PINS.items():
        if consumed_hashes[name] != expected:
            raise ValueError('INPUT_PIN_CONFLICT:' + name)
    native = payloads['strategies/alt_support_bounce_v1.py']
    blob = hashlib.sha1(b'blob ' + str(len(native)).encode() + b'\0' + native).hexdigest()
    if blob != 'b8fcdca3974161ddc1804384fd1dd5bb28168857':
        raise ValueError('NATIVE_BOUNCE_SOURCE_CONFLICT')
    prereg = json.loads(payloads['configs/research/bounce1_majors_three_regime_prereg_20260802.json'])
    if (prereg['symbols'] != ['BTCUSDT', 'ETHUSDT'] or prereg['execution'] != {
            'next_open': True, 'fee_bps_per_side': 6.0,
            'slippage_bps_per_side': 2.0, 'cache': 'data_cache'}):
        raise ValueError('FROZEN_RESEARCH_CONTRACT_CONFLICT')
    artifacts, buffers = {}, {}
    for symbol in prereg['symbols']:
        source = ROOT / f'research_lab/data/h1/{symbol}.npz'
        before = consumed_hashes[str(source.relative_to(ROOT))]
        with np.load(BytesIO(payloads[str(source.relative_to(ROOT))]), allow_pickle=False) as bundle:
            if set(bundle.files) != {'ts', 'ohlcv', 'nsub'}:
                raise ValueError('NPZ_SCHEMA_CONFLICT:' + symbol)
            ts, values, counts = bundle['ts'], bundle['ohlcv'], bundle['nsub']
        if (ts.dtype != np.dtype('int64') or values.dtype != np.dtype('float32')
                or counts.dtype != np.dtype('int16') or ts.ndim != 1
                or counts.shape != ts.shape or values.shape != (len(ts), 5)):
            raise ValueError('NPZ_SHAPE_OR_PRECISION_CONFLICT:' + symbol)
        # Explicit prefix selection, no hidden future/open-bar discard.
        eligible = ts + HOUR_MS <= prepared_ms
        if np.any(eligible[1:] & ~eligible[:-1]):
            raise ValueError('NPZ_NON_PREFIX_AS_OF:' + symbol)
        rows = [[int(t), *[float(v) for v in row]] for t, row in zip(ts[eligible], values[eligible])]
        h4 = derive_closed_h4(rows, counts[eligible], as_of_ms=prepared_ms)
        files = {}
        for tf, data in [('H1', rows), ('H4', h4['rows'])]:
            name = f'{symbol}_{tf}.jsonl'
            raw = jsonl(data)
            buffers[name] = raw
            files[tf] = {'filename': name, 'sha256': hashlib.sha256(raw).hexdigest(),
                         'bytes': len(raw), 'rows': len(data), 'first_open_ms': data[0][0],
                         'last_open_ms': data[-1][0], 'timestamp_semantics': 'OPEN_TIME_UTC_MS',
                         'last_closed_at_ms': data[-1][0] + (HOUR_MS if tf == 'H1' else 4 * HOUR_MS)}
        artifacts[symbol] = {'input_path': str(source.relative_to(ROOT)), 'input_sha256': before,
                             'input_precision': 'float32 widened to float64; no raw-exchange precision claim',
                             'as_of_ms': prepared_ms, 'excluded_open_future_h1_rows': int((~eligible).sum()),
                             'excluded_h4_leading_open_ms': h4['excluded_leading_open_ms'],
                             'excluded_h4_trailing_open_ms': h4['excluded_trailing_open_ms'],
                             'm5_completeness': 'DECLARED_COUNT_12_ONLY_RAW_LINEAGE_UNPROVEN', 'files': files}
    manifest = {
        'schema': 'BOUNCE_RANGE_SOURCE_INTAKE_V1', 'status': 'BLOCKED_RESEARCH_SOURCE_CONTRACT',
        'prepared_ms': prepared_ms, 'prepared_utc': utc(prepared_ms), 'as_of_ms': prepared_ms,
        'orders_allowed': False, 'money_authority': False, 'outcomes_evaluated': False,
        'signals_evaluated': False, 'research_ref': 'cf904086a2d887a96ac2be3324a3d78433e1a94b',
        'universe': {'symbols': prereg['symbols'], 'scope': 'EXISTING_MAJORS_ONLY_BASELINE',
                     'broader_eight_symbol_prereg_separate': True, 'new_universe_selection': False},
        'baseline_config': frozen_bounce_defaults(native.decode()), 'native_git_blob': blob,
        'environment_rule': 'No env loaded here. Future parity runner must isolate every BOUNCE1_/ASB1_ override and allowlist; constructor mutates config from environment.',
        'costs': {'fee_bps_per_side': 6.0, 'slippage_bps_per_side': 2.0,
                 'role': 'FROZEN_HISTORICAL_ASSUMPTIONS_NOT_MEASURED_CURRENT_ACCOUNT_COSTS',
                 'source': 'configs/research/bounce1_majors_three_regime_prereg_20260802.json',
                 'funding_treatment': None, 'funding_complete_history': None,
                 'missing_funding_is_not_zero': True, 'funding_policy_authority': 'CLAUDE_PREREG_REQUIRED'},
        'declared_historical_windows': prereg['windows'],
        'consumption_ledger': 'UNKNOWN; declarations are contaminated candidates, not certified unused data',
        'untouched_validation_periods': [],
        'candidate_validation_designs': [
            {'kind': 'historical', 'status': 'NOT_CERTIFIED', 'action': 'Claude must supply interval + data hashes + full consumption/discovery ledger before outcome access; absence of files is not proof'},
            {'kind': 'new prospective', 'status': 'NOT_STARTED', 'action': 'Freeze full config/cost/funding/availability/context and judge before selecting forward start; no backfill as prospective'}],
        'bar_availability': {'timestamp_semantics_source': 'research_lab/build_h1_bundle.py:file_to_h1 hkey floor',
                             'derivation': 'CLOSED_PREFIX_UTC_FULL_FOUR_H1_CHILDREN_ONLY',
                             'historical_pit_publication': 'UNPROVEN', 'provider_raw_m5_manifest': None,
                             'point_in_time_claim': False},
        'blockers': ['FUNDING_TREATMENT_AND_COVERAGE_UNSPECIFIED',
                     'VALIDATION_INDEPENDENCE_AND_CONSUMPTION_LEDGER_UNPROVEN',
                     'RAW_M5_PROVIDER_LINEAGE_AND_PIT_AVAILABILITY_UNPROVEN'],
        'artifacts': artifacts,
        'source_sha256': consumed_hashes,
        'next_action': 'Claude completes these source declarations and freezes baseline-vs-context prereg; no outcome run is authorized by this packet.'}
    # No output if any pathname ceased to match its consumed snapshot.
    for name, expected in consumed_hashes.items():
        if sha(ROOT / name) != expected:
            raise ValueError('INPUT_CHANGED_DURING_PREPARATION:' + name)
    # Fail instead of overwriting any existing evidence. Manifest written last.
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, raw in buffers.items():
        with (output / name).open('xb') as handle:
            handle.write(raw)
        (output / name).chmod(0o600)
    with (output / 'manifest.json').open('x') as handle:
        json.dump(manifest, handle, indent=2, allow_nan=False)
        handle.write('\n')
    (output / 'manifest.json').chmod(0o600)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps({'status': result['status'], 'symbols': result['universe']['symbols'],
                      'rows': {s: {tf: f['rows'] for tf, f in a['files'].items()}
                               for s, a in result['artifacts'].items()}, 'blockers': result['blockers']}, indent=2))
