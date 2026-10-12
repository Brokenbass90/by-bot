"""Source-only capture/check. Never calls a strategy, judge or terminal adapter."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from research_lab.brain_v2_sources import PinnedSources
from research_lab.brain_v2_frozen_primitives import digest, DEVELOP_END_EXCLUSIVE_MS, HOUR

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / '.superpowers/sdd/brain-v2-develop-20261012/source'
CLAUDE = ROOT.parent / 'bybit-bot-clean-v28'
TRAIN_MANIFEST_PIN = 'a2325b0b534713f072f5e50559d57633e389646b7a5e85861d5d72c8461050bf'
START = 1_672_531_200_000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    path = OUT / name
    if path.exists():
        raise RuntimeError('Evidence already exists; do not recapture/repin: '+str(path))
    with path.open('xb') as f:
        f.write((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def main():
    # Exclusive source-check marker only. No filter permission is consumed.
    with (OUT/'adapter_source_check.started').open('x') as f:
        f.write(datetime.now(timezone.utc).isoformat()+'\n')
    manifest = json.loads((OUT/'source_manifest.json').read_bytes())
    sources = PinnedSources(SOURCE,(OUT/'source_manifest.json').read_bytes(),
                            expected_manifest_sha256=TRAIN_MANIFEST_PIN)
    verified = sources.verify()
    symbols, streams = set(), []
    for row in manifest['files']:
        if row['role'] != 'trade_stream':
            continue
        legs = tuple(sorted({r['leg'] for r in json.loads(sources.read(row['path']))}))
        entries = sources.stream(row['path'],sleeves=legs).entries(
            start_ms=START,end_ms=DEVELOP_END_EXCLUSIVE_MS)
        symbols.update(x.opportunity.symbol for x in entries)
        streams.append(dict(path=row['path'],sleeves=legs,closed_signal_entry_count=len(entries),
                            source_sha256=row['sha256'],terminal_projection_calls=0))
    bars = []
    for row in manifest['files']:
        if row['role'] != 'h1_bars':
            continue
        archive = sources.h1(row['path'])
        history = archive.closed(DEVELOP_END_EXCLUSIVE_MS)
        bars.append(dict(path=row['path'],source_sha256=row['sha256'],closed_count=len(history),
                         incomplete_m5_children_count=archive.incomplete_subbar_count,
                         publication_basis=archive.publication_basis,
                         raw_m5_pit_provenance='UNKNOWN'))
    # Byte capture only, never a claim that mutable local funding is a Git blob.
    captured_at = datetime.now(timezone.utc).isoformat()
    extra_rows, funding, missing = [], [], []
    candidates = [(symbol,CLAUDE/'research_lab/data/pit_daily'/f'{symbol}.json')
                  for symbol in sorted(symbols)]
    total = sum(p.stat().st_size for _,p in candidates if p.is_file())
    if total > 100_000_000:
        raise RuntimeError('Funding capture exceeds bounded100MB')
    for symbol,path in candidates:
        if not path.is_file():
            missing.append(symbol)
            continue
        raw = path.read_bytes()
        name = f'external/funding/{symbol}.json'
        target = SOURCE/name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:
            f.write(raw)
        if path.read_bytes() != raw or target.read_bytes() != raw:
            raise RuntimeError('Funding source changed during capture: '+symbol)
        row = dict(path=name,sha256=sha(raw),bytes=len(raw),role='funding',git_blob=None,
                   capture_origin=str(path),captured_at_utc=captured_at,
                   provenance='LOCAL_PUBLIC_RESEARCH_ARCHIVE_NOT_GIT_PINNED')
        extra_rows.append(row)
    body = dict(schema='BRAIN_V2_DEVELOP_INPUT_MANIFEST',
                train_manifest_sha256=TRAIN_MANIFEST_PIN,
                research_commit=manifest['research_commit'],
                files=manifest['files']+extra_rows,
                funding_absent_symbols=missing,orders_allowed=False,
                filter_runs=0,judge_runs=0)
    adapter_manifest = {**body,'sha256':digest(body)}
    save('adapter_manifest.json',adapter_manifest)
    adapter = PinnedSources(SOURCE,(OUT/'adapter_manifest.json').read_bytes(),
                            expected_manifest_sha256=adapter_manifest['sha256'])
    adapter_integrity = adapter.verify()
    for row in extra_rows:
        symbol = Path(row['path']).stem
        archive = adapter.funding(row['path'],symbol=symbol)
        funding.append(archive.coverage(start_ms=START,end_ms=DEVELOP_END_EXCLUSIVE_MS))
    # Market-context parity only; no opportunity selection/PnL/MTM/filter.
    spec = importlib.util.spec_from_file_location('brain_frozen_rezhim_check',
                    SOURCE/'research_lab/os2/rezhim_v1.py')
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    with np.load(SOURCE/'research_lab/data/h1/BTCUSDT.npz',allow_pickle=False) as z:
        mask=z['ts']<DEVELOP_END_EXCLUSIVE_MS
        expected=ref.agg4h(z['ts'][mask],z['ohlcv'][mask].astype(float))
    actual=adapter.h1('research_lab/data/h1/BTCUSDT.npz').h4_closed(DEVELOP_END_EXCLUSIVE_MS)
    actual_rows=[[b.open_ms,b.o,b.h,b.l,b.c,b.v] for b in actual]
    if actual_rows != expected:
        raise RuntimeError('Frozen BTC H4 parity mismatch')
    implementation_paths = [
        'research_lab/brain_v2_sources.py','research_lab/brain_v2_a1.py',
        'research_lab/brain_v2_a3.py','research_lab/brain_v2_frozen_primitives.py',
        'research_lab/os2_shadow_journal.py','research_lab/os2_shadow_bridge.py',
        'bot/regime_orchestrator.py']
    implementation_pins={p:sha((ROOT/p).read_bytes()) for p in implementation_paths}
    save('real_adapter_source_check.json',dict(
        schema='BRAIN_V2_REAL_ADAPTER_SOURCE_CHECK',captured_at_utc=captured_at,
        train_manifest=verified,adapter_manifest=adapter_integrity,
        implementation_sha256=implementation_pins,streams=streams,h1=bars,
        symbols_count=len(symbols),funding=funding,funding_absent_symbols=missing,
        btc_h4_parity=dict(status='PASS',bars=len(actual),rows_sha256=digest(actual_rows)),
        table_hash_publication_raw_sha256=sha((OUT/'TABLE_HASH_PUBLICATION.json').read_bytes()),
        future_terminal_projection_calls=0,filter_runs=0,judge_runs=0,
        holdout_evaluation_runs=0,orders_allowed=False,
        funding_integration_status='BLOCKED_DATA_CALENDAR_PUBLICATION_UNBOUND'))


if __name__=='__main__':
    main()
