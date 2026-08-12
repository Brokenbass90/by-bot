from pathlib import Path

from research_lab.static_defect_scan import scan_file


def _codes(path: Path) -> list[str]:
    return [code for _, code, _ in scan_file(path)]


def test_e1_requires_evidence_that_file_uses_millisecond_timestamps(tmp_path: Path):
    seconds_only = tmp_path / "seconds_only.py"
    seconds_only.write_text(
        "import time\nexpiry_ts = time.time() + hold_seconds\n",
        encoding="utf-8",
    )
    assert "E1" not in _codes(seconds_only)

    milliseconds = tmp_path / "milliseconds.py"
    milliseconds.write_text(
        "bars = fetch_klines()\n"
        "candle_ts = int(float(bars[-1][0]))\n"
        "expiry_ts = candle_ts + hold_seconds\n",
        encoding="utf-8",
    )
    assert "E1" in _codes(milliseconds)


def test_e2_disabled_rule_does_not_report_default_seconds_timestamp(tmp_path: Path):
    path = tmp_path / "fallback.py"
    path.write_text(
        "import time\nnow = now_ts if now_ts is not None else time.time()\n",
        encoding="utf-8",
    )
    assert "E2" not in _codes(path)
