#!/usr/bin/env python3
"""Build a minimal, immutable public ATT1 deployment; never contacts a server."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    'bot/__init__.py', 'strategies/__init__.py',
    'bot/att1_ets2s_shadow_journal.py', 'bot/public_h1_cache_store.py',
    'research_lab/att1_lifecycle_public_inputs.py', 'scripts/run_att1_ets2s_signal_shadow.py',
    'bot/att1_ets2s_signal_shadow_contract.py', 'bot/att1_geometry_v2.py',
    'bot/chart_geometry.py', 'bot/liquidity_map.py', 'bot/live_native_decision_contract.py',
    'bot/sbr1_universe.py', 'research_lab/att1_ets2s_accounting.py',
    'research_lab/att1_ets2s_lifecycle.py', 'research_lab/att1_ets2s_signal_shadow_parity.py',
    'research_lab/att1_lifecycle_coordinator.py', 'research_lab/att1_lifecycle_journal.py',
    'research_lab/att1_lifecycle_profile.py', 'research_lab/att1_lifecycle_session.py',
    'research_lab/research_ohlcv_store.py', 'scripts/run_att1_lifecycle_zero_risk.py',
    'scripts/verify_att1_lifecycle.py', 'strategies/alt_trendline_touch_v1.py',
    'strategies/att1_live.py', 'strategies/elder_live.py',
    'strategies/elder_triple_screen_v2.py', 'strategies/live_kline_utils.py',
    'strategies/signals.py',
)
CONFIG = 'configs/research/att1_lifecycle_public_v1.json'
FIXTURE = 'tests/fixtures/att1_lifecycle/att1_end_to_end_v1.json'
UNIT = 'deploy/systemd/att1-lifecycle-zero-risk.service'
AUTHORITY = {'money_authority': False, 'orders_allowed': False,
             'private_api_allowed': False, 'promotion_authority': False}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def build(out: Path, *, revision='v1'):
    if revision not in {'v1','v2'}:
        raise ValueError('unknown public release revision')
    config_path = CONFIG if revision == 'v1' else 'configs/research/att1_lifecycle_public_v2.json'
    unit_path = UNIT if revision == 'v1' else 'deploy/systemd/att1-lifecycle-zero-risk-v2.service'
    config = json.loads((ROOT / config_path).read_bytes())
    if config['enabled'] is not False or set(config['authority']) != set(AUTHORITY):
        raise ValueError('repository config must be default off with exact authority fields')
    if any(config['authority'][key] is not False for key in AUTHORITY):
        raise ValueError('authority must remain exactly false')
    config['enabled'] = True  # simulation process only; money capabilities remain false
    files = {'app/' + p: (ROOT / p).read_bytes() for p in (*SOURCES, FIXTURE)}
    if revision == 'v2':
        # The standalone synthetic HTTP-tape verifier still uses this disabled
        # template and redirects both directories into its temporary fixture.
        files['app/' + CONFIG] = (ROOT / CONFIG).read_bytes()
    files['app/' + config_path] = json.dumps(config, sort_keys=True, indent=2).encode() + b'\n'
    files[unit_path] = (ROOT / unit_path).read_bytes()
    rows = [{'path': p, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            for p, data in sorted(files.items())]
    closure = hashlib.sha256(canonical(rows)).hexdigest()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = {'schema_id': 'att1_lifecycle_release_v1', 'files': rows,
                'closure_sha256': closure, 'source_tree_head': head,
                'source_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                'authority': AUTHORITY, 'execution_model': 'PUBLIC_SNAPSHOT_IOC_SIMULATION'}
    files['release_manifest.json'] = json.dumps(manifest, sort_keys=True, indent=2).encode() + b'\n'
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    archive = out / ('att1-lifecycle-' + closure[:16] + '.tar')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for relative, data in sorted(files.items()):
            info = tarfile.TarInfo(relative)
            info.size = len(data)
            info.mode = 0o644
            info.uid = info.gid = info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    raw = buffer.getvalue()
    if archive.exists() and archive.read_bytes() != raw:
        raise ValueError('refuse archive identity collision')
    archive.write_bytes(raw)
    receipt = {'archive': str(archive), 'archive_sha256': hashlib.sha256(raw).hexdigest(),
               'closure_sha256': closure, 'files': len(rows), 'bytes': len(raw),
               'source_tree_head': head, 'source_tree_dirty': manifest['source_tree_dirty'], 'authority': AUTHORITY}
    (out / 'package_receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--revision', choices=('v1','v2'), default='v1')
    args = parser.parse_args()
    print(json.dumps(build(args.out, revision=args.revision), sort_keys=True))
