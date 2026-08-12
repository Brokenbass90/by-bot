import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.backtest_candidates import load_1h_ohlc


ROOT = Path(__file__).resolve().parents[1]


def test_explicit_input_resamples_and_rejects_symbol_mismatch(tmp_path):
    records = []
    for index in range(12):
        records.append({
            "ts_ms": index * 300_000,
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100.5 + index,
        })
    path = tmp_path / "ETHUSDT.json"
    path.write_text(json.dumps({"symbol": "ETHUSDT", "records": records}))

    ts, opens, highs, lows, closes = load_1h_ohlc("ETHUSDT", input_json=str(path))

    assert ts == [0]
    assert opens == [100]
    assert highs == [112]
    assert lows == [99]
    assert closes == [111.5]
    with pytest.raises(ValueError, match="symbol mismatch"):
        load_1h_ohlc("BTCUSDT", input_json=str(path))


def test_input_root_explicitly_records_zero_holdout_reads(tmp_path):
    symbol_dir = tmp_path / "BTCUSDT"
    symbol_dir.mkdir()
    path = symbol_dir / "BTCUSDT.json"
    records = []
    for index in range(12 * 400):
        price = 100.0 + (index % 17) * 0.01
        records.append({
            "ts_ms": index * 300_000,
            "open": price,
            "high": price + 0.1,
            "low": price - 0.1,
            "close": price,
        })
    path.write_text(json.dumps({"symbol": "BTCUSDT", "records": records}))
    result_path = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/backtest_candidates.py"),
            "--strategy", "rmr1",
            "--symbols", "BTCUSDT",
            "--input-root", str(tmp_path),
            "--result-out", str(result_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text())
    assert result["sealed_holdout_rows_decoded"] == 0
    assert result["input_files"] == {"BTCUSDT": str(path)}
