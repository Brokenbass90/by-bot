import copy
from pathlib import Path

import pytest

from research_lab.run_passport import (
    AUTHORITY,
    REQUEST_SCHEMA_ID,
    PassportError,
    assert_comparable,
    build_passport,
    validate_passport,
    write_passport,
)


def _spec(code: Path, data: Path) -> dict:
    return {
        "schema_id": REQUEST_SCHEMA_ID,
        "experiment_id": "clean-preholdout-test",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "live_or_broker_calls": False,
        "code_paths": [str(code)],
        "inputs": [
            {
                "path": str(data),
                "role": "market_data",
                "temporal_data": True,
                "data_window": {
                    "start_utc": "2024-01-01T00:00:00Z",
                    "end_utc_exclusive": "2025-10-01T00:00:00Z",
                },
                "contains_sealed_holdout": False,
            }
        ],
        "measurement_contract": {
            "engine": "test_engine_v1",
            "timeframe": "1h",
            "window": {
                "start_utc": "2024-01-01T00:00:00Z",
                "end_utc_exclusive": "2025-10-01T00:00:00Z",
            },
            "universe": ["BTCUSDT", "ETHUSDT"],
            "costs": {"fee_bps_round_trip": 12.0, "slippage_bps_round_trip": 4.0},
            "label_contract": "barrier_1atr_vs_1atr_24h_v1",
            "split_contract": "early_train_late_test_x_train_symbols_test_symbols_v1",
        },
        "search_contract": {"variant_count": 1, "random_seed": 7, "pre_registered": True},
        "sealed_holdouts": [
            {
                "id": "reserved_2025_10_2026_06",
                "start_utc": "2025-10-01T00:00:00Z",
                "end_utc_exclusive": "2026-07-01T00:00:00Z",
                "must_not_be_read": True,
            }
        ],
    }


def test_builds_hash_bound_comparable_passport(tmp_path: Path) -> None:
    code = tmp_path / "strategy.py"
    data = tmp_path / "bars.csv"
    code.write_text("print('research')\n")
    data.write_text("ts,close\n2024-01-01,1\n")
    first = build_passport(_spec(code, data), project_root=tmp_path)
    second_spec = _spec(code, data)
    second_spec["experiment_id"] = "second-variant"
    second = build_passport(second_spec, project_root=tmp_path)
    validate_passport(first)
    assert_comparable(first, second)


def test_blocks_sealed_input_before_opening_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = tmp_path / "strategy.py"
    data = tmp_path / "combined-with-holdout.npz"
    code.write_text("pass\n")
    data.write_bytes(b"sealed bytes must remain unread")
    spec = _spec(code, data)
    spec["inputs"][0]["contains_sealed_holdout"] = True

    def forbidden_hash(_: Path) -> str:
        raise AssertionError("input hashing must not happen before the holdout guard")

    monkeypatch.setattr("research_lab.run_passport.sha256_file", forbidden_hash)
    with pytest.raises(PassportError, match="contains a sealed holdout"):
        build_passport(spec, project_root=tmp_path)


def test_blocks_declared_data_window_overlap(tmp_path: Path) -> None:
    code = tmp_path / "strategy.py"
    data = tmp_path / "bars.csv"
    code.write_text("pass\n")
    data.write_text("x\n")
    spec = _spec(code, data)
    spec["inputs"][0]["data_window"]["end_utc_exclusive"] = "2026-01-01T00:00:00Z"
    with pytest.raises(PassportError, match="declared data window overlaps"):
        build_passport(spec, project_root=tmp_path)


def test_comparison_fails_when_cost_contract_differs(tmp_path: Path) -> None:
    code = tmp_path / "strategy.py"
    data = tmp_path / "bars.csv"
    code.write_text("pass\n")
    data.write_text("x\n")
    first = build_passport(_spec(code, data), project_root=tmp_path)
    changed = _spec(code, data)
    changed["measurement_contract"]["costs"]["fee_bps_round_trip"] = 20.0
    second = build_passport(changed, project_root=tmp_path)
    with pytest.raises(PassportError, match="different measurement conditions"):
        assert_comparable(first, second)


def test_comparison_fails_when_search_budget_or_seed_differs(tmp_path: Path) -> None:
    code = tmp_path / "strategy.py"
    data = tmp_path / "bars.csv"
    code.write_text("pass\n")
    data.write_text("x\n")
    first = build_passport(_spec(code, data), project_root=tmp_path)
    changed = _spec(code, data)
    changed["search_contract"]["variant_count"] = 30
    changed["search_contract"]["random_seed"] = 99
    second = build_passport(changed, project_root=tmp_path)
    with pytest.raises(PassportError, match="different measurement conditions"):
        assert_comparable(first, second)


def test_passport_is_tamper_evident_and_write_once(tmp_path: Path) -> None:
    code = tmp_path / "strategy.py"
    data = tmp_path / "bars.csv"
    code.write_text("pass\n")
    data.write_text("x\n")
    passport = build_passport(_spec(code, data), project_root=tmp_path)
    output = tmp_path / "passport.json"
    write_passport(output, passport)
    with pytest.raises(PassportError, match="write-once"):
        write_passport(output, passport)

    tampered = copy.deepcopy(passport)
    tampered["measurement_contract"]["timeframe"] = "5m"
    with pytest.raises(PassportError, match="hash mismatch"):
        validate_passport(tampered)
