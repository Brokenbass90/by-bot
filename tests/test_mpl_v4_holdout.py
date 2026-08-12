import json
from pathlib import Path

from research_lab.mpl_v4_holdout import (
    choose_arm,
    exact_input_hashes,
    metadata_preflight,
)


def _write_build_status(root: Path, symbols: list[str]) -> None:
    (root / "build_status.json").write_text(json.dumps({
        "state": "complete",
        "failed": {},
        "requested_symbols": symbols,
        "completed": symbols,
        "skipped": [],
    }), encoding="utf-8")


def test_metadata_preflight_requires_exact_complete_build(tmp_path: Path):
    symbols = ["AAAUSDT", "BBBUSDT"]
    for symbol in symbols:
        (tmp_path / f"{symbol}.npz").write_bytes(symbol.encode())
    _write_build_status(tmp_path, symbols)

    result = metadata_preflight(tmp_path, symbols)

    assert result["expected_symbol_count"] == 2
    assert result["extra_npz_ignored"] == []
    assert len(result["build_status_sha256"]) == 64


def test_metadata_preflight_rejects_incomplete_build(tmp_path: Path):
    symbols = ["AAAUSDT"]
    (tmp_path / "AAAUSDT.npz").write_bytes(b"sealed")
    _write_build_status(tmp_path, [])

    try:
        metadata_preflight(tmp_path, symbols)
    except Exception as exc:
        assert "exact complete universe" in str(exc)
    else:
        raise AssertionError("incomplete build status was accepted")


def test_input_hashes_bind_exact_bytes(tmp_path: Path):
    path = tmp_path / "AAAUSDT.npz"
    path.write_bytes(b"one")
    first = exact_input_hashes(tmp_path, [path.name])
    path.write_bytes(b"two")
    second = exact_input_hashes(tmp_path, [path.name])
    assert first != second


def test_two_arm_decision_is_frozen_primary_first():
    passed = {"verdict": "SHADOW_CANDIDATE_ONLY"}
    failed = {"verdict": "REJECT"}
    assert choose_arm(passed, passed)[0] == "V4"
    assert choose_arm(passed, failed)[0] == "V4"
    assert choose_arm(failed, passed)[0] == "V3"
    assert choose_arm(failed, failed)[0] is None
