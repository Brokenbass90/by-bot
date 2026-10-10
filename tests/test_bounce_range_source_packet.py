"""Source mechanics only: no strategy decisions or outcome evaluation."""
import pytest
import hashlib
import json
from pathlib import Path

import numpy as np

from research_lab.bounce_range_source_packet import HOUR_MS, derive_closed_h4
from scripts import prepare_bounce_range_sources as prep


def bars(start=0, count=8):
    return [[(start + i) * HOUR_MS, 100 + i, 102 + i, 99 + i, 101 + i, i + 1]
            for i in range(count)]


def test_four_closed_children_open_timestamp_and_ohlcv():
    result = derive_closed_h4(bars(), [12] * 8, as_of_ms=8 * HOUR_MS)
    assert result['rows'] == [[0, 100., 105., 99., 104., 10.],
                              [4 * HOUR_MS, 104., 109., 103., 108., 26.]]
    assert result['excluded_leading_open_ms'] == []
    assert result['excluded_trailing_open_ms'] == []
    assert result['last_available_ms'] == 8 * HOUR_MS


def test_h4_requires_all_four_hours_closed_exactly_at_as_of():
    with pytest.raises(ValueError, match='OPEN_OR_FUTURE_H1'):
        derive_closed_h4(bars(count=4), [12] * 4, as_of_ms=4 * HOUR_MS - 1)
    assert len(derive_closed_h4(bars(count=4), [12] * 4, as_of_ms=4 * HOUR_MS)['rows']) == 1


def test_partial_edges_are_explicit_never_shifted_to_rolling_four_hours():
    result = derive_closed_h4(bars(start=1, count=9), [12] * 9, as_of_ms=10 * HOUR_MS)
    assert [r[0] for r in result['rows']] == [4 * HOUR_MS]
    assert result['excluded_leading_open_ms'] == [HOUR_MS, 2 * HOUR_MS, 3 * HOUR_MS]
    assert result['excluded_trailing_open_ms'] == [8 * HOUR_MS, 9 * HOUR_MS]


@pytest.mark.parametrize('change', ['gap', 'duplicate', 'reverse', 'misaligned', 'float_ts', 'bool_ts'])
def test_grid_failures_are_not_silently_repaired(change):
    rows = bars()
    if change == 'gap': rows.pop(3)
    if change == 'duplicate': rows[3] = list(rows[2])
    if change == 'reverse': rows.reverse()
    if change == 'misaligned': rows[3][0] += 1
    if change == 'float_ts': rows[3][0] = float(rows[3][0])
    if change == 'bool_ts': rows[0][0] = False
    with pytest.raises(ValueError):
        derive_closed_h4(rows, [12] * len(rows), as_of_ms=8 * HOUR_MS)


@pytest.mark.parametrize('value', [11, 13, 12.5, True])
def test_incomplete_or_invalid_declared_m5_count_blocks(value):
    counts = [12] * 8
    counts[3] = value
    with pytest.raises(ValueError, match='H1_SUBBAR_COUNT'):
        derive_closed_h4(bars(), counts, as_of_ms=8 * HOUR_MS)


@pytest.mark.parametrize('field,value', [(1, 0), (2, 90), (3, 110), (4, float('nan')), (5, -1)])
def test_bad_price_or_volume_geometry_blocks(field, value):
    rows = bars()
    rows[3][field] = value
    with pytest.raises(ValueError):
        derive_closed_h4(rows, [12] * 8, as_of_ms=8 * HOUR_MS)


def test_prefix_h4_does_not_depend_on_later_prices():
    first = derive_closed_h4(bars(count=4), [12] * 4, as_of_ms=4 * HOUR_MS)
    full = bars()
    for row in full[4:]: row[1:5] = [10000., 10002., 9999., 10001.]
    later = derive_closed_h4(full, [12] * 8, as_of_ms=8 * HOUR_MS)
    assert first['rows'] == later['rows'][:1]


def test_empty_no_complete_bucket_and_count_mismatch_block():
    for rows, counts in [([], []), (bars(count=3), [12] * 3), (bars(), [12])]:
        with pytest.raises(ValueError):
            derive_closed_h4(rows, counts, as_of_ms=8 * HOUR_MS)


@pytest.mark.parametrize('as_of', [True, 1.5, -1])
def test_invalid_as_of_blocks(as_of):
    with pytest.raises(ValueError):
        derive_closed_h4(bars(), [12] * 8, as_of_ms=as_of)


@pytest.fixture
def prepared_fixture(tmp_path, monkeypatch):
    original = prep.ROOT
    inputs = dict(prep.INPUT_PINS)
    for name in list(inputs) + ['strategies/alt_support_bounce_v1.py',
                               'research_lab/build_h1_bundle.py',
                               'bot/closed_bar_aggregation_v1.py',
                               'research_lab/bounce_range_source_packet.py',
                               'scripts/prepare_bounce_range_sources.py']:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith('.npz'):
            rows = bars(count=8)
            np.savez(p, ts=np.array([r[0] for r in rows], dtype='int64'),
                     ohlcv=np.array([r[1:] for r in rows], dtype='float32'),
                     nsub=np.full(8, 12, dtype='int16'))
            inputs[name] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            p.write_bytes((original / name).read_bytes())
    monkeypatch.setattr(prep, 'ROOT', tmp_path)
    monkeypatch.setattr(prep, 'INPUT_PINS', inputs)
    return tmp_path


def test_packet_stays_blocked_and_records_costs_provenance_and_config(prepared_fixture):
    out = prepared_fixture / 'new_evidence'
    manifest = prep.prepare(out)
    assert manifest['status'] == 'BLOCKED_RESEARCH_SOURCE_CONTRACT'
    assert manifest['orders_allowed'] is manifest['outcomes_evaluated'] is manifest['signals_evaluated'] is False
    assert manifest['universe']['symbols'] == ['BTCUSDT', 'ETHUSDT']
    assert manifest['baseline_config']['sl_atr_mult'] == 1.6
    assert manifest['baseline_config']['tp1_frac'] == .15
    assert manifest['costs']['funding_treatment'] is None
    assert manifest['bar_availability']['point_in_time_claim'] is False
    assert manifest['untouched_validation_periods'] == []
    assert json.loads((out / 'manifest.json').read_text()) == manifest
    for symbol, evidence in manifest['artifacts'].items():
        for tf, spec in evidence['files'].items():
            raw = (out / spec['filename']).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == spec['sha256']
            assert len(raw.splitlines()) == (8 if tf == 'H1' else 2)


def test_source_drift_blocks_before_any_output(prepared_fixture):
    path = prepared_fixture / 'research_lab/data/h1/BTCUSDT.npz'
    path.write_bytes(path.read_bytes() + b'drift')
    out = prepared_fixture / 'new_evidence'
    with pytest.raises(ValueError, match='INPUT_PIN_CONFLICT'):
        prep.prepare(out)
    assert not out.exists()


@pytest.mark.parametrize('relative', ['research_lab/data/h1/BTCUSDT.npz',
                                     'configs/research/bounce1_majors_three_regime_prereg_20260802.json'])
def test_replacement_after_pin_read_cannot_change_consumed_sources(prepared_fixture, monkeypatch, relative):
    path = prepared_fixture / relative
    original_read = Path.read_bytes
    changed = False

    def replace_after_first_read(self):
        nonlocal changed
        raw = original_read(self)
        if self == path and not changed:
            changed = True
            # Appended bytes are still valid to the original np.load/JSON reader.
            self.write_bytes(raw + b'\n ')
        return raw

    monkeypatch.setattr(Path, 'read_bytes', replace_after_first_read)
    out = prepared_fixture / 'new_evidence'
    with pytest.raises(ValueError, match='INPUT_CHANGED_DURING_PREPARATION|INPUT_PIN_CONFLICT'):
        prep.prepare(out)
    assert changed and not out.exists()


def test_existing_evidence_is_not_overwritten(prepared_fixture):
    out = prepared_fixture / 'sealed'
    out.mkdir()
    (out / 'manifest.json').write_text('retained')
    with pytest.raises(FileExistsError):
        prep.prepare(out)
    assert list(out.iterdir()) == [out / 'manifest.json']
    assert (out / 'manifest.json').read_text() == 'retained'
