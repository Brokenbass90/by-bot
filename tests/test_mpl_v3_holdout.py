import json
from pathlib import Path

import numpy as np
import pytest

from research_lab import mpl_v3
from research_lab.mpl_v3_holdout import (
    BAR_MS,
    END_MS_EXCLUSIVE,
    START_MS,
    HoldoutError,
    _write_once,
    metadata_preflight,
    validate_loaded_inputs,
)


def _series(*, bars: int = 200, skip_index: int | None = None):
    ts = START_MS - 100 * BAR_MS + np.arange(bars, dtype=np.int64) * BAR_MS
    if skip_index is not None:
        ts = np.delete(ts, skip_index)
    close = 100.0 + np.arange(len(ts), dtype=float) * 0.01
    return {
        "ts": ts,
        "o": close - 0.01,
        "h": close + 0.03,
        "l": close - 0.03,
        "c": close,
        "v": np.full(len(ts), 10.0),
    }


def test_holdout_window_is_exact_utc_boundary():
    assert START_MS == 1_759_276_800_000
    assert END_MS_EXCLUSIVE == 1_782_864_000_000


def test_metadata_preflight_requires_every_allowlisted_file_and_ignores_extras(tmp_path: Path):
    (tmp_path / "AAAUSDT.npz").write_bytes(b"metadata-only")
    (tmp_path / "EXTRAUSDT.npz").write_bytes(b"ignored")
    result = metadata_preflight(tmp_path, ["AAAUSDT"])
    assert result["expected_symbol_count"] == 1
    assert result["extra_npz_ignored"] == ["EXTRAUSDT.npz"]
    with pytest.raises(HoldoutError, match="missing 1 MPL files"):
        metadata_preflight(tmp_path, ["AAAUSDT", "MISSINGUSDT"])


def test_input_integrity_rejects_gap_affected_or_invalid_ohlc():
    symbols = [f"S{i:02d}USDT" for i in range(10)]
    clean = {symbol: _series() for symbol in symbols}
    receipt = validate_loaded_inputs(clean, symbols)
    assert receipt["usable_symbol_count"] == 10

    gapped = dict(clean)
    gap_series = _series()
    gap_series["ts"][80:] += 10 * BAR_MS
    gapped[symbols[0]] = gap_series
    with pytest.raises(HoldoutError, match="coverage"):
        validate_loaded_inputs(gapped, symbols)

    bad = {symbol: dict(values) for symbol, values in clean.items()}
    bad[symbols[0]] = dict(bad[symbols[0]])
    bad[symbols[0]]["h"] = bad[symbols[0]]["h"].copy()
    bad[symbols[0]]["h"][0] = 1.0
    with pytest.raises(HoldoutError, match="OHLC geometry"):
        validate_loaded_inputs(bad, symbols)


def test_write_once_receipt_cannot_be_overwritten(tmp_path: Path):
    path = tmp_path / "receipt.json"
    _write_once(path, {"n": 1})
    assert json.loads(path.read_text())["n"] == 1
    with pytest.raises(HoldoutError, match="already exists"):
        _write_once(path, {"n": 2})


def test_engine_load_rejects_missing_explicit_universe(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mpl_v3, "DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="missing MPL input files"):
        mpl_v3.load(symbols=["BTCUSDT"])


def test_simulator_uses_decision_time_turnover_and_blocks_overlapping_symbol_trades():
    bars = 220
    close = np.full(bars, 100.0)
    data = {
        "h": np.full(bars, 100.1),
        "l": np.full(bars, 99.9),
        "c": close,
        "v": np.full(bars, 20_000.0),
        "hidx": np.zeros(bars, dtype=np.int64),
        "H": {"ema": np.full(1, 100.0)},
    }
    signals = [
        (1, 100, 100.0, 99.0, 110.3, 1.0),
        (2, 104, 100.0, 99.0, 110.3, 1.0),
    ]
    rows = mpl_v3.simulate(data, signals, "TESTUSDT", enforce_no_overlap=True)
    assert len(rows) == 1
    assert rows[0]["exit_i"] == 195
    assert rows[0]["slip_bps"] == 2.0
    assert rows[0]["trailing_turnover_usd"] == pytest.approx(192_000_000.0)
