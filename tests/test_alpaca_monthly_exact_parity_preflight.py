from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.preflight_alpaca_monthly_exact_parity import (
    CONFORMANCE_CASES,
    DEFAULT_CONFIG,
    EXPECTED_ARMS,
    EXPECTED_AUTOMATIC_VERDICT,
    EXPECTED_EVALUATION_CONTRACT,
    EXPECTED_EXECUTION_CONTRACT,
    EXPECTED_SHARED_EXIT_CONTRACT,
    FROZEN_ARM_IDS,
    PreflightError,
    REQUIRED_ARTIFACT_TYPES,
    SOURCE_PATHS,
    actual_source_hashes,
    compute_contract_fingerprint,
    evaluate_preflight,
    sha256_file,
    validate_frozen_contract,
)


def _cfg() -> dict:
    return {
        "schema_version": 1,
        "name": "alpaca_monthly_exact_parity_replay_test",
        "frozen_at_utc": "2026-07-13T00:00:00Z",
        "research_only": True,
        "frozen_before_results": True,
        "no_parameter_scan": True,
        "performance_forbidden_until_preflight_pass": True,
        "live_or_broker_calls": False,
        "risk_pct": 0,
        "current_permission": "BLOCKED_FAIL_CLOSED_UNTIL_ALL_REQUIRED_INPUTS_PINNED",
        "arms": copy.deepcopy(list(EXPECTED_ARMS)),
        "source_code": {key: "" for key in SOURCE_PATHS},
        "contract_fingerprint": "",
        "required_artifacts": {
            key: {"content_type": content_type, "path": "", "sha256": ""}
            for key, content_type in REQUIRED_ARTIFACT_TYPES.items()
        },
        "execution_contract": copy.deepcopy(EXPECTED_EXECUTION_CONTRACT),
        "shared_exit_contract": copy.deepcopy(EXPECTED_SHARED_EXIT_CONTRACT),
        "evaluation_contract": copy.deepcopy(EXPECTED_EVALUATION_CONTRACT),
        "automatic_verdict": copy.deepcopy(EXPECTED_AUTOMATIC_VERDICT),
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _pin(cfg: dict, root: Path, name: str, relative_path: str, payload: object | None) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload is not None:
        _write_json(path, payload)
    cfg["required_artifacts"][name]["path"] = relative_path
    cfg["required_artifacts"][name]["sha256"] = sha256_file(path)
    return path


def _refresh_fingerprint(root: Path, cfg: dict) -> None:
    cfg["source_code"] = actual_source_hashes(root)
    cfg["contract_fingerprint"] = compute_contract_fingerprint(cfg, cfg["source_code"])


def _prepare_ready_root(tmp_path: Path) -> tuple[Path, dict, dict[str, Path]]:
    root = tmp_path
    for rel in SOURCE_PATHS.values():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"frozen source: {rel}\n", encoding="utf-8")

    cfg = _cfg()
    paths: dict[str, Path] = {}

    historical = root / "inputs" / "historical_AAPL.json"
    _write_json(historical, [{"date": "2026-01-02", "o": 100, "h": 102, "l": 99, "c": 101}])
    forward = root / "inputs" / "forward_AAPL.json"
    _write_json(forward, [{"date": "2026-07-13", "o": 110, "h": 111, "l": 109, "c": 110.5}])
    raw_broker = root / "inputs" / "broker_export_redacted.json"
    _write_json(raw_broker, {"orders": ["order-1"], "redacted": True})

    paths["point_in_time_universe"] = _pin(
        cfg,
        root,
        "point_in_time_universe",
        "inputs/universe.json",
        {
            "schema_id": "alpaca_point_in_time_universe_v1",
            "point_in_time_membership": True,
            "selection_frozen_before_performance": True,
            "membership_intervals": [
                {
                    "symbol": "AAPL",
                    "effective_from_utc": "2022-01-01T00:00:00Z",
                    "effective_to_utc_exclusive": None,
                    "source_record_sha256": "a" * 64,
                }
            ],
        },
    )
    paths["market_data_manifest"] = _pin(
        cfg,
        root,
        "market_data_manifest",
        "inputs/market_manifest.json",
        {
            "schema_id": "alpaca_point_in_time_market_data_manifest_v1",
            "point_in_time": True,
            "completed_bars_only": True,
            "calendar": "XNYS",
            "bar_interval": "1d",
            "price_basis": "split_and_dividend_adjusted_ohlcv",
            "files": [
                {
                    "symbol": "AAPL",
                    "path": str(historical.relative_to(root)),
                    "sha256": sha256_file(historical),
                }
            ],
        },
    )

    broker_payload = {
        "schema_id": "alpaca_broker_lifecycle_v1",
        "window_start_utc": "2026-07-06T00:00:00Z",
        "window_end_utc_exclusive": "2026-07-10T00:00:00Z",
        "reconstruction_complete": True,
        "unresolved_conflicts": 0,
        "duplicate_fill_ids": 0,
        "redacted_no_secrets": True,
        "raw_export_files": [
            {
                "path": str(raw_broker.relative_to(root)),
                "sha256": sha256_file(raw_broker),
            }
        ],
        "broker_order_count": 1,
        "broker_fill_count": 1,
        "order_lifecycles": [
            {
                "broker_order_id": "order-1",
                "client_order_id": "client-1",
                "symbol": "AAPL",
                "side": "buy",
                "events": [
                    {"event_type": "submitted", "timestamp_utc": "2026-07-06T13:30:00Z"},
                    {"event_type": "filled", "timestamp_utc": "2026-07-06T13:30:01Z"},
                ],
                "fills": [
                    {
                        "fill_id": "fill-1",
                        "timestamp_utc": "2026-07-06T13:30:01Z",
                        "qty": 1.0,
                        "price": 100.0,
                    }
                ],
            }
        ],
    }
    paths["broker_fill_order_lifecycle_20260706_20260709"] = _pin(
        cfg,
        root,
        "broker_fill_order_lifecycle_20260706_20260709",
        "inputs/broker_lifecycle.json",
        broker_payload,
    )
    broker_sha = cfg["required_artifacts"]["broker_fill_order_lifecycle_20260706_20260709"]["sha256"]

    paths["cost_gap_calibration"] = _pin(
        cfg,
        root,
        "cost_gap_calibration",
        "inputs/cost_gap.json",
        {
            "schema_id": "alpaca_cost_gap_calibration_v1",
            "frozen_before_performance": True,
            "base_cost_bps_per_side": 5.0,
            "stress_cost_bps_per_side": 10.0,
            "entry_gap_fill": "next_session_open_plus_adverse_cost",
            "stop_gap_fill": "opening_price_if_open_beyond_stop",
            "target_gap_fill": "frozen_target_price_no_favorable_gap_credit",
            "same_bar_stop_and_target": "stop_first",
            "broker_lifecycle_sha256": broker_sha,
        },
    )
    paths["regime_labels"] = _pin(
        cfg,
        root,
        "regime_labels",
        "inputs/regimes.json",
        {
            "schema_id": "alpaca_causal_regime_labels_v1",
            "rule_frozen_before_performance": True,
            "uses_future_data": False,
            "labels": ["bull", "bear", "sideways"],
            "intervals": [
                {"start_utc": "2022-01-01T00:00:00Z", "end_utc_exclusive": "2023-01-01T00:00:00Z", "label": "bear"},
                {"start_utc": "2023-01-01T00:00:00Z", "end_utc_exclusive": "2024-01-01T00:00:00Z", "label": "bull"},
                {"start_utc": "2024-01-01T00:00:00Z", "end_utc_exclusive": "2025-01-01T00:00:00Z", "label": "sideways"},
            ],
        },
    )
    paths["corporate_actions_survivorship"] = _pin(
        cfg,
        root,
        "corporate_actions_survivorship",
        "inputs/survivorship.json",
        {
            "schema_id": "alpaca_survivorship_receipt_v1",
            "point_in_time_membership": True,
            "includes_delisted_names": True,
            "corporate_actions_known_as_of_event_time": True,
            "delisting_return_policy": "last_tradable_open_or_close_then_cash_with_frozen_costs",
        },
    )
    paths["untouched_forward_manifest"] = _pin(
        cfg,
        root,
        "untouched_forward_manifest",
        "inputs/forward_manifest.json",
        {
            "schema_id": "alpaca_untouched_forward_manifest_v1",
            "window_start_utc": "2026-07-13T00:00:00Z",
            "window_end_utc_exclusive": "2026-08-01T00:00:00Z",
            "sealed_before_performance": True,
            "used_for_strategy_development": False,
            "outcome_values_read_before_freeze": False,
            "calendar": "XNYS",
            "price_basis": "split_and_dividend_adjusted_ohlcv",
            "files": [
                {
                    "symbol": "AAPL",
                    "path": str(forward.relative_to(root)),
                    "sha256": sha256_file(forward),
                }
            ],
        },
    )

    exit_path = root / "research" / "shared_exit.py"
    exit_path.parent.mkdir(parents=True, exist_ok=True)
    exit_path.write_text("def simulate_position(*args, **kwargs):\n    raise NotImplementedError\n", encoding="utf-8")
    paths["shared_exit_model_implementation"] = _pin(
        cfg,
        root,
        "shared_exit_model_implementation",
        str(exit_path.relative_to(root)),
        None,
    )
    exit_sha = cfg["required_artifacts"]["shared_exit_model_implementation"]["sha256"]
    paths["shared_exit_model_conformance"] = _pin(
        cfg,
        root,
        "shared_exit_model_conformance",
        "inputs/exit_conformance.json",
        {
            "schema_id": "alpaca_shared_exit_conformance_v1",
            "entrypoint": "simulate_position",
            "arm_ids": list(FROZEN_ARM_IDS),
            "implementation_sha256": exit_sha,
            "broker_lifecycle_sha256": broker_sha,
            "all_cases_passed": True,
            "passed_cases": sorted(CONFORMANCE_CASES),
            "broker_lifecycle_exact_match": True,
            "unresolved_mismatches": 0,
        },
    )
    _refresh_fingerprint(root, cfg)
    return root, cfg, paths


def test_persisted_prereg_is_valid_but_blocks_all_performance_until_inputs_are_pinned():
    cfg = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))

    validate_frozen_contract(cfg)
    result = evaluate_preflight(DEFAULT_CONFIG.parents[2], cfg)

    assert result["permission"] == "BLOCKED_FAIL_CLOSED"
    assert result["performance_computed"] is False
    assert result["performance_fields_present"] is False
    assert result["outcome_access_allowed"] is False
    assert result["promotion_authorized"] is False
    assert result["live_or_broker_calls"] is False
    assert result["safe_hold_changed"] is False
    assert result["frozen_arm_ids"] == list(FROZEN_ARM_IDS)
    assert "required_hash_pinned_inputs_not_ready" in result["blockers"]


def test_only_exact_four_arms_and_frozen_methodology_are_accepted():
    cfg = _cfg()
    validate_frozen_contract(cfg)

    changed = copy.deepcopy(cfg)
    changed["arms"].append(copy.deepcopy(changed["arms"][0]))
    with pytest.raises(PreflightError, match="four frozen arms"):
        validate_frozen_contract(changed)

    changed = copy.deepcopy(cfg)
    changed["arms"][0]["schedule"]["entry_time"] = "same_close"
    with pytest.raises(PreflightError, match="four frozen arms"):
        validate_frozen_contract(changed)

    changed = copy.deepcopy(cfg)
    changed["execution_contract"]["stress_cost_bps_per_side"] = 0.0
    with pytest.raises(PreflightError, match="execution/cost/gap"):
        validate_frozen_contract(changed)

    changed = copy.deepcopy(cfg)
    changed["evaluation_contract"]["daily_max_drawdown_required"] = False
    with pytest.raises(PreflightError, match="daily equity/DD"):
        validate_frozen_contract(changed)


def test_fully_pinned_semantically_valid_inputs_only_allow_risk_zero_performance_replay(tmp_path):
    root, cfg, _ = _prepare_ready_root(tmp_path)

    result = evaluate_preflight(root, cfg)

    assert result["permission"] == "PERFORMANCE_REPLAY_ALLOWED"
    assert result["blockers"] == []
    assert all(row["ok"] for row in result["source_status"])
    assert all(row["ok"] for row in result["artifacts"])
    assert result["performance_computed"] is False
    assert result["outcome_access_allowed"] is True
    assert result["promotion_authorized"] is False
    assert result["safe_hold_changed"] is False


def test_tampered_nested_market_data_blocks_even_when_manifest_hash_is_still_pinned(tmp_path):
    root, cfg, _ = _prepare_ready_root(tmp_path)
    nested = root / "inputs" / "historical_AAPL.json"
    nested.write_text("tampered after manifest freeze\n", encoding="utf-8")

    result = evaluate_preflight(root, cfg)

    assert result["permission"] == "BLOCKED_FAIL_CLOSED"
    market = next(row for row in result["artifacts"] if row["name"] == "market_data_manifest")
    assert "nested_file_0_hash_mismatch" in market["reasons"]
    assert result["performance_computed"] is False


def test_pinned_but_incomplete_jul6_9_lifecycle_blocks_cost_and_exit_parity(tmp_path):
    root, cfg, paths = _prepare_ready_root(tmp_path)
    lifecycle_path = paths["broker_fill_order_lifecycle_20260706_20260709"]
    payload = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    payload["reconstruction_complete"] = False
    _write_json(lifecycle_path, payload)
    new_sha = sha256_file(lifecycle_path)
    cfg["required_artifacts"]["broker_fill_order_lifecycle_20260706_20260709"]["sha256"] = new_sha

    for artifact_name, field in (
        ("cost_gap_calibration", "broker_lifecycle_sha256"),
        ("shared_exit_model_conformance", "broker_lifecycle_sha256"),
    ):
        path = paths[artifact_name]
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt[field] = new_sha
        _write_json(path, receipt)
        cfg["required_artifacts"][artifact_name]["sha256"] = sha256_file(path)
    _refresh_fingerprint(root, cfg)

    result = evaluate_preflight(root, cfg)

    assert result["permission"] == "BLOCKED_FAIL_CLOSED"
    assert "jul6_9_broker_fill_order_lifecycle_not_reconstructed" in result["blockers"]
    lifecycle = next(
        row for row in result["artifacts"]
        if row["name"] == "broker_fill_order_lifecycle_20260706_20260709"
    )
    assert "broker_lifecycle_incomplete" in lifecycle["reasons"]


def test_incomplete_shared_exit_conformance_blocks_all_four_arms(tmp_path):
    root, cfg, paths = _prepare_ready_root(tmp_path)
    path = paths["shared_exit_model_conformance"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["passed_cases"] = payload["passed_cases"][:-1]
    _write_json(path, payload)
    cfg["required_artifacts"]["shared_exit_model_conformance"]["sha256"] = sha256_file(path)
    _refresh_fingerprint(root, cfg)

    result = evaluate_preflight(root, cfg)

    assert result["permission"] == "BLOCKED_FAIL_CLOSED"
    assert "one_shared_executable_exit_model_not_proven" in result["blockers"]
    receipt = next(
        row for row in result["artifacts"] if row["name"] == "shared_exit_model_conformance"
    )
    assert "exit_conformance_cases_incomplete" in receipt["reasons"]
    assert result["performance_computed"] is False


def test_outcome_or_promotion_sections_are_forbidden_in_preregistration():
    cfg = _cfg()
    cfg["performance_results"] = {"return_pct": 999}
    with pytest.raises(PreflightError, match="outcome/performance"):
        validate_frozen_contract(cfg)

    cfg = _cfg()
    cfg["metadata"] = {"promotion_verdict": "PROMOTE"}
    with pytest.raises(PreflightError, match="outcome/performance"):
        validate_frozen_contract(cfg)
