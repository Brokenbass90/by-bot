"""Source adapters must not turn archive availability into broker/feed truth."""
from dataclasses import asdict
import hashlib
import io
import json

import numpy as np
import pytest

from research_lab.brain_v2_frozen_primitives import BrainBlocked, canonical, digest
from research_lab.brain_v2_a1 import HOUR
from research_lab.brain_v2_a3 import COST_MODEL
from research_lab.brain_v2_sources import PinnedSources

NOW = 1_704_067_200_000  # 2024-01-01, spent developing history.


def make_sources(tmp_path, contents):
    files = []
    for name, (raw, role) in contents.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files.append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest(),
                          bytes=len(raw), role=role))
    body = dict(schema='BRAIN_V2_DEVELOP_SOURCE_MANIFEST', files=files,
                orders_allowed=False)
    pin = digest(body)
    manifest = {**body, 'sha256': pin}
    return PinnedSources(tmp_path, canonical(manifest), expected_manifest_sha256=pin), manifest


def stream(rows=None):
    return canonical(rows if rows is not None else [dict(
        leg='ATT1', sym='BTCUSDT', side='short', ts=NOW,
        lev=49.99, R=1.25, hours=2, reg='BULL_TREND')])


def npz(ts, *, invalid_price=False):
    buffer = io.BytesIO()
    prices = np.array([[100, 103, 97, 101, 500]] * len(ts), dtype=np.float32)
    if invalid_price:
        prices[-1, 3] = np.nan
    np.savez(buffer, ts=np.array(ts, dtype=np.int64), ohlcv=prices,
             nsub=np.full(len(ts), 12, dtype=np.int16))
    return buffer.getvalue()


def test_pin_is_external_and_changed_manifest_or_archive_blocks(tmp_path):
    sources, manifest = make_sources(tmp_path, {'stream.json': (stream(), 'stream')})
    changed = {**manifest, 'orders_allowed': True}
    with pytest.raises(BrainBlocked, match='manifest'):
        PinnedSources(tmp_path, canonical(changed), expected_manifest_sha256=manifest['sha256'])
    (tmp_path / 'stream.json').write_bytes(stream([]))
    with pytest.raises(BrainBlocked, match='source_bytes_or_hash'):
        sources.read('stream.json')


@pytest.mark.parametrize('name', ['../escape', '/tmp/escape', 'a/../escape', './stream.json'])
def test_manifest_paths_cannot_escape_or_alias_root(tmp_path, name):
    body = dict(schema='BRAIN_V2_DEVELOP_SOURCE_MANIFEST', orders_allowed=False,
                files=[dict(path=name, bytes=1, sha256='a' * 64, role='stream')])
    pin = digest(body)
    with pytest.raises(BrainBlocked, match='source_path'):
        PinnedSources(tmp_path, canonical({**body, 'sha256': pin}),
                      expected_manifest_sha256=pin)


def test_symlink_and_unmanifested_file_cannot_supply_evidence(tmp_path):
    sources, _ = make_sources(tmp_path, {'stream.json': (stream(), 'stream')})
    (tmp_path / 'stream.json').rename(tmp_path / 'real.json')
    (tmp_path / 'stream.json').symlink_to(tmp_path / 'real.json')
    with pytest.raises(BrainBlocked, match='source_symlink'):
        sources.read('stream.json')
    with pytest.raises(BrainBlocked, match='source_not_manifested'):
        sources.read('real.json')


def test_causal_entry_projection_never_contains_terminal_outcome(tmp_path):
    sources, _ = make_sources(tmp_path, {'stream.json': (stream(), 'stream')})
    archive = sources.stream('stream.json', sleeves=('ATT1',))
    entry, = archive.entries(start_ms=NOW, end_ms=NOW + 2 * HOUR)
    assert entry.opportunity.t_available == NOW + HOUR
    assert entry.opportunity.stop_distance_frac == 1 / 49.99
    assert entry.opportunity.cost_model_id == COST_MODEL
    assert entry.opportunity.max_hold_h == 336
    assert entry.metadata == dict(lev=49.99, source_hash=entry.opportunity.source_hash,
                                 t_available=NOW + HOUR, entry_rule='next_open')
    assert not {'R', 'hours', 'release_time', 'reg'} & set(asdict(entry.opportunity))
    assert not {'R', 'hours', 'release_time', 'reg'} & set(entry.metadata)
    assert entry.availability_basis == 'FROZEN_A2_A3_HISTORICAL_MODEL'
    with pytest.raises(TypeError):
        entry.metadata['lev'] = 2


def test_entry_numeric_projection_does_not_depend_on_future_R_or_hold(tmp_path):
    row = json.loads(stream())[0]
    left, _ = make_sources(tmp_path / 'left', {'s.json': (stream(), 'stream')})
    right, _ = make_sources(tmp_path / 'right', {'s.json': (stream([{**row, 'R': -50, 'hours': 300}]), 'stream')})
    a, = left.stream('s.json', sleeves=('ATT1',)).entries(start_ms=NOW, end_ms=NOW+2*HOUR)
    b, = right.stream('s.json', sleeves=('ATT1',)).entries(start_ms=NOW, end_ms=NOW+2*HOUR)
    # Source hashes bind exact archives, but projection/numeric sizing is outcome independent.
    assert a.opportunity.source_hash != b.opportunity.source_hash
    assert {k:v for k,v in asdict(a.opportunity).items() if k!='source_hash'} == {
        k:v for k,v in asdict(b.opportunity).items() if k!='source_hash'}


@pytest.mark.parametrize('mutation', ['duplicate', 'off_grid', 'unknown_sleeve', 'nan_lev'])
def test_stream_conflicts_never_sort_deduplicate_or_round(tmp_path, mutation):
    row = json.loads(stream())[0]
    if mutation == 'duplicate': rows = [row, row]
    elif mutation == 'off_grid': rows = [{**row, 'ts': NOW+1}]
    elif mutation == 'unknown_sleeve': rows = [{**row, 'leg': 'NEW_STRATEGY'}]
    else: rows = [{**row, 'lev': 'NaN'}]
    sources, _ = make_sources(tmp_path, {'s.json': (canonical(rows), 'stream')})
    with pytest.raises(BrainBlocked, match='stream'):
        sources.stream('s.json', sleeves=('ATT1',))


def test_terminal_is_projected_only_at_exact_frozen_release_tick(tmp_path):
    sources, _ = make_sources(tmp_path, {'s.json': (stream(), 'stream')})
    archive = sources.stream('s.json', sleeves=('ATT1',))
    entry, = archive.entries(start_ms=NOW, end_ms=NOW+2*HOUR)
    for at in [NOW+HOUR, NOW+4*HOUR]:
        with pytest.raises(BrainBlocked, match='terminal_not_release_tick'):
            archive.terminal(entry.opportunity.id, tick_ms=at, funding={'synthetic': True})
    term = archive.terminal(entry.opportunity.id, tick_ms=NOW+3*HOUR, funding={'synthetic': True})
    assert term['hours'] == 2 and term['R'] == 1.25
    assert term['available_ms'] == NOW+3*HOUR
    assert term['source_hash'] == entry.opportunity.source_hash


def test_quarter_hour_mapping_and_sealed_boundary_are_literal(tmp_path):
    row = {**json.loads(stream())[0], 'leg':'ETS2', 'hours':1}
    sources, _ = make_sources(tmp_path, {'s.json': (stream([row]), 'stream')})
    archive = sources.stream('s.json', sleeves=('ETS2',))
    entry, = archive.entries(start_ms=NOW, end_ms=NOW+HOUR)
    assert entry.opportunity.t_available == NOW+HOUR//4
    with pytest.raises(BrainBlocked, match='develop_window'):
        archive.entries(start_ms=NOW, end_ms=1_759_276_800_001)


def test_h1_prefix_is_closed_and_h4_never_uses_incomplete_bucket(tmp_path):
    times = [NOW+i*HOUR for i in range(6)]
    sources, _ = make_sources(tmp_path, {'btc.npz': (npz(times), 'h1')})
    bars = sources.h1('btc.npz')
    assert len(bars.closed(NOW+3*HOUR)) == 3
    assert bars.closed(NOW+3*HOUR)[-1].available_ms == NOW+3*HOUR
    assert bars.h4_closed(NOW+3*HOUR) == ()
    h4, = bars.h4_closed(NOW+5*HOUR)
    assert h4.open_ms == NOW and h4.available_ms == NOW+4*HOUR
    assert (h4.o,h4.h,h4.l,h4.c,h4.v) == (100,103,97,101,2000)
    assert bars.publication_basis == 'HISTORICAL_CLOSE_MODEL_NOT_FEED_TIMESTAMP'


def test_missing_child_stays_gap_not_synthetic_h4(tmp_path):
    sources, _ = make_sources(tmp_path, {'btc.npz': (npz([NOW,NOW+HOUR,NOW+3*HOUR,NOW+4*HOUR]), 'h1')})
    bars = sources.h1('btc.npz')
    assert len(bars.closed(NOW+5*HOUR)) == 4
    assert bars.h4_closed(NOW+5*HOUR) == ()


@pytest.mark.parametrize('bad', ['duplicate','unordered','off_grid','nonfinite'])
def test_h1_source_does_not_repair_bad_bars(tmp_path, bad):
    ts = [NOW,NOW+HOUR]
    if bad == 'duplicate': ts[1] = NOW
    elif bad == 'unordered': ts.reverse()
    elif bad == 'off_grid': ts[1] += 1
    sources, _ = make_sources(tmp_path, {'b.npz': (npz(ts,invalid_price=bad=='nonfinite'), 'h1')})
    with pytest.raises(BrainBlocked, match='h1'):
        sources.h1('b.npz')


def test_real_funding_pairs_cannot_claim_calendar_or_publication(tmp_path):
    raw = canonical(dict(symbol='BTCUSDT', daily=[], funding=[[NOW,.001],[NOW+HOUR,-.0002]]))
    sources, _ = make_sources(tmp_path, {'funding.json': (raw,'funding')})
    archive = sources.funding('funding.json', symbol='BTCUSDT')
    coverage = archive.coverage(start_ms=NOW,end_ms=NOW+HOUR)
    assert coverage['archive_event_count'] == 1  # entry excluded, release included.
    assert coverage['status'] == 'BLOCKED_DATA'
    assert coverage['calendar_status'] == coverage['publication_status'] == 'UNKNOWN'
    assert coverage['rate_sum'] is None


@pytest.mark.parametrize('bad', ['duplicate','unordered','nonfinite','symbol'])
def test_funding_conflicts_block_without_silent_dedup(tmp_path,bad):
    rows = [[NOW,.001],[NOW+HOUR,-.0002]]
    if bad == 'duplicate': rows[1][0] = NOW
    elif bad == 'unordered': rows.reverse()
    elif bad == 'nonfinite': rows[0][1] = 'NaN'
    raw = canonical(dict(symbol='ETHUSDT' if bad=='symbol' else 'BTCUSDT',funding=rows))
    sources,_ = make_sources(tmp_path,{'f.json':(raw,'funding')})
    with pytest.raises(BrainBlocked,match='funding'):
        sources.funding('f.json',symbol='BTCUSDT')


def test_contexts_use_closed_full_seed_and_unknown_for_absent_symbol(tmp_path):
    times = [NOW+i*HOUR for i in range(2174)]
    sources,_ = make_sources(tmp_path, {'b.npz':(npz(times),'h1'),
        's.json':(stream([{**json.loads(stream())[0],'ts':times[-1]}]),'stream')})
    entries = sources.stream('s.json',sleeves=('ATT1',)).entries(
        start_ms=times[-1],end_ms=times[-1]+2*HOUR)
    hour = times[-1]+HOUR
    known = sources.contexts(entries,hour_ms=hour,btc_path='b.npz',h1_paths={'BTCUSDT':'b.npz'})
    envelope = known[entries[0].opportunity.id]
    assert envelope['vol']['vol']=='MID'
    assert envelope['vol']['closed_cutoff_ms']==hour
    assert envelope['vol']['window_count']==2160
    assert envelope['regime']['reason']=='A1_CLOSED_DATA'
    assert envelope['sha256']==digest({k:v for k,v in envelope.items() if k!='sha256'})
    missing = sources.contexts(entries,hour_ms=hour,btc_path=None,h1_paths={})
    envelope = missing[entries[0].opportunity.id]
    assert envelope['vol']['vol']==envelope['regime']['regime']=='UNKNOWN'


def test_funding_empty_archive_is_unknown_never_zero(tmp_path):
    sources,_=make_sources(tmp_path,{'f.json':(canonical(dict(symbol='BTCUSDT',funding=[])),'funding')})
    result=sources.funding('f.json',symbol='BTCUSDT').coverage(start_ms=NOW,end_ms=NOW+HOUR)
    assert result['archive_event_count']==0 and result['rate_sum'] is None
    assert result['status']=='BLOCKED_DATA'


def test_terminal_crossing_sealed_boundary_never_exposes_post_develop_R(tmp_path):
    end=1_759_276_800_000
    row={**json.loads(stream())[0],'ts':end-2*HOUR,'hours':2}
    sources,_=make_sources(tmp_path,{'s.json':(stream([row]),'stream')})
    archive=sources.stream('s.json',sleeves=('ATT1',))
    entry,=archive.entries(start_ms=end-2*HOUR,end_ms=end)
    with pytest.raises(BrainBlocked,match='terminal_outside_develop'):
        archive.terminal(entry.opportunity.id,tick_ms=end+HOUR,funding={})


def test_malformed_stream_symbol_is_explicit_blocked_not_unhashable_crash(tmp_path):
    row={**json.loads(stream())[0],'sym':['BTCUSDT']}
    sources,_=make_sources(tmp_path,{'s.json':(stream([row]),'stream')})
    with pytest.raises(BrainBlocked,match='stream_entry'):
        sources.stream('s.json',sleeves=('ATT1',))
