#!/usr/bin/env python3
"""Fail-closed preregistration preflight for the Alpaca monthly parity replay.

This command is deliberately incapable of calculating returns, reading a
broker, changing SAFE-HOLD, or authorizing promotion.  It only verifies that
the frozen four-arm comparison, source code, point-in-time inputs, reconstructed
broker lifecycle, shared exit implementation, and untouched-forward lockbox
were hash-pinned before any performance runner is allowed to start.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT
    / "configs"
    / "preregistered"
    / "alpaca_monthly_exact_parity_replay_20260713.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "reports"
    / "research"
    / "alpaca_monthly_exact_parity_replay_20260713_preflight.json"
)

SOURCE_PATHS = {
    "preflight_sha256": "scripts/preflight_alpaca_monthly_exact_parity.py",
    "monthly_sim_sha256": "scripts/equities_monthly_research_sim.py",
    "monthly_refresh_sha256": "scripts/run_equities_monthly_v36_refresh.sh",
    "adaptive_selector_sha256": "strategies/alpaca_adaptive_v1.py",
    "adaptive_reference_replay_sha256": "backtest/alpaca_bakeoff_wf.py",
    "live_bridge_reference_sha256": "scripts/equities_alpaca_paper_bridge.py",
}

FROZEN_ARM_IDS = (
    "true_monthly_v38_top4",
    "accidental_daily_rotation_negative_control",
    "adaptive_default_gated",
    "adaptive_ungated_control",
)

MONTHLY_SCHEDULE = {
    "signal_time": "completed_last_xnys_session_close_of_calendar_month",
    "entry_time": "next_tradable_xnys_session_open",
    "same_close_or_same_bar_entry_allowed": False,
    "target_refresh": "calendar_monthly",
}
DAILY_NEGATIVE_CONTROL_SCHEDULE = {
    "signal_time": "each_completed_xnys_session_close",
    "entry_time": "next_tradable_xnys_session_open",
    "same_close_or_same_bar_entry_allowed": False,
    "target_refresh": "daily_full_rotation_negative_control",
}
V38_SELECTOR = {
    "selector_id": "v38_momentum_top4_frozen",
    "top_n": 4,
    "candidate_pool_n": 12,
    "universe_top_k": 18,
    "momentum_lookback_sessions": 28,
    "minimum_momentum_pct": 5.0,
    "max_positions": 4,
    "max_per_sector": 2,
    "position_weight_mode": "score_inv_vol",
    "parameter_scan": False,
}
ADAPTIVE_SELECTOR = {
    "selector_id": "alpaca_adaptive_v1_defaults_frozen",
    "mom_fast": 20,
    "mom_slow": 60,
    "vol_period": 60,
    "trend_sma": 50,
    "regime_index": "SPY",
    "regime_index_sma": 200,
    "min_entry_mom": 0.0,
    "target_vol": 0.02,
    "max_position_frac": 0.40,
    "max_per_sector": 2,
    "max_portfolio_dd_pct": 15.0,
    "top_n": 5,
    "max_positions": 4,
    "soft_regime": False,
    "ai_approver": False,
    "parameter_scan": False,
}
EXPECTED_ARMS = (
    {
        "id": FROZEN_ARM_IDS[0],
        "role": "candidate",
        "schedule": MONTHLY_SCHEDULE,
        "selector": V38_SELECTOR,
        "market_regime_gate": "v38_frozen_native_gate",
    },
    {
        "id": FROZEN_ARM_IDS[1],
        "role": "negative_control",
        "schedule": DAILY_NEGATIVE_CONTROL_SCHEDULE,
        "selector": V38_SELECTOR,
        "market_regime_gate": "v38_frozen_native_gate",
    },
    {
        "id": FROZEN_ARM_IDS[2],
        "role": "challenger",
        "schedule": MONTHLY_SCHEDULE,
        "selector": ADAPTIVE_SELECTOR,
        "market_regime_gate": "spy_sma200_enabled",
        "force_regime_ok": False,
    },
    {
        "id": FROZEN_ARM_IDS[3],
        "role": "gate_ab_control",
        "schedule": MONTHLY_SCHEDULE,
        "selector": ADAPTIVE_SELECTOR,
        "market_regime_gate": "disabled_for_frozen_control_only",
        "force_regime_ok": True,
    },
)

EXPECTED_EXECUTION_CONTRACT = {
    "calendar": "XNYS",
    "signal_data": "completed_bars_only",
    "monthly_signal_to_fill": "completed_month_close_to_next_session_open",
    "daily_negative_control_signal_to_fill": "completed_day_close_to_next_session_open",
    "same_bar_fill_allowed": False,
    "price_basis": "split_and_dividend_adjusted_ohlcv",
    "entry_gap_fill": "next_session_open_plus_adverse_cost",
    "stop_gap_fill": "opening_price_if_open_beyond_stop",
    "target_gap_fill": "frozen_target_price_no_favorable_gap_credit",
    "same_bar_stop_and_target": "stop_first",
    "base_cost_bps_per_side": 5.0,
    "stress_cost_bps_per_side": 10.0,
    "costs_applied_on_entries_and_exits": True,
    "broker_or_live_calls": False,
    "risk_pct": 0,
}

EXPECTED_SHARED_EXIT_CONTRACT = {
    "id": "alpaca_v38_atr_be_trail_shared_v1",
    "entrypoint": "simulate_position",
    "used_by_arm_ids": list(FROZEN_ARM_IDS),
    "one_implementation_for_all_arms": True,
    "initial_stop_atr": 2.0,
    "profit_target_atr": 3.2,
    "break_even_trigger_r": 0.8,
    "trail_atr": 1.5,
    "max_hold_sessions": 22,
    "intramonth_portfolio_stop_pct": 0.08,
    "daily_mark_to_market": True,
    "opening_gap_processed_before_intraday_path": True,
    "same_bar_stop_and_target": "stop_first",
    "implementation_artifact": "shared_exit_model_implementation",
    "conformance_artifact": "shared_exit_model_conformance",
}

EXPECTED_EVALUATION_CONTRACT = {
    "development_cutoff_utc": "2026-07-13T00:00:00Z",
    "untouched_forward_start_utc": "2026-07-13T00:00:00Z",
    "untouched_forward_used_for_parameter_selection": False,
    "daily_equity_curve_required": True,
    "daily_mark_to_market_required": True,
    "daily_max_drawdown_required": True,
    "monthly_returns_required": True,
    "turnover_required": True,
    "sector_and_symbol_concentration_required": True,
    "required_regimes": ["bull", "bear", "sideways"],
    "point_in_time_membership_required": True,
    "delisted_names_and_corporate_actions_required": True,
    "all_four_arms_same_data_costs_and_exit_model": True,
    "broker_lifecycle_window_start_utc": "2026-07-06T00:00:00Z",
    "broker_lifecycle_window_end_utc_exclusive": "2026-07-10T00:00:00Z",
    "parameter_search_after_freeze": False,
}

EXPECTED_AUTOMATIC_VERDICT = {
    "preflight_blocked": "NO_PERFORMANCE_RUN",
    "preflight_passed": "PERFORMANCE_REPLAY_ONLY_NO_PROMOTION_AUTHORITY",
    "any_parity_failure": "REMAIN_SAFE_HOLD",
    "all_parity_checks_pass": "RESEARCH_REVIEW_REQUIRED_NO_AUTOMATIC_LIVE_CHANGE",
}

REQUIRED_ARTIFACT_TYPES = {
    "point_in_time_universe": "alpaca_point_in_time_universe_v1",
    "market_data_manifest": "alpaca_point_in_time_market_data_manifest_v1",
    "broker_fill_order_lifecycle_20260706_20260709": "alpaca_broker_lifecycle_v1",
    "cost_gap_calibration": "alpaca_cost_gap_calibration_v1",
    "regime_labels": "alpaca_causal_regime_labels_v1",
    "corporate_actions_survivorship": "alpaca_survivorship_receipt_v1",
    "untouched_forward_manifest": "alpaca_untouched_forward_manifest_v1",
    "shared_exit_model_implementation": "python_source_v1",
    "shared_exit_model_conformance": "alpaca_shared_exit_conformance_v1",
}

CONFORMANCE_CASES = {
    "completed_bar_only",
    "next_open_entry",
    "entry_gap_adverse_cost",
    "stop_gap_at_open",
    "target_gap_no_favorable_credit",
    "same_bar_stop_first",
    "break_even_trigger",
    "atr_trailing_stop",
    "max_hold_exit",
    "daily_mark_to_market",
}


class PreflightError(ValueError):
    """The frozen contract itself is unsafe or internally inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _repo_file(root: Path, raw: object) -> Path:
    text = str(raw or "")
    candidate = Path(text)
    if not text or candidate.is_absolute() or "\\" in text:
        raise PreflightError(f"artifact path must be repo-relative: {text!r}")
    if any(part in {"", ".", ".."} for part in candidate.parts) or ".git" in candidate.parts:
        raise PreflightError(f"unsafe artifact path: {text!r}")
    cursor = root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PreflightError(f"artifact path contains a symlink: {text!r}")
    return cursor


def _has_forbidden_outcome_section(value: object) -> bool:
    forbidden = {"performance_results", "outcome_results", "selected_winner", "promotion_verdict"}
    if isinstance(value, Mapping):
        return any(key in forbidden or _has_forbidden_outcome_section(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_forbidden_outcome_section(item) for item in value)
    return False


def validate_frozen_contract(cfg: Mapping[str, Any]) -> None:
    if cfg.get("schema_version") != 1:
        raise PreflightError("schema_version must remain 1")
    required_true = (
        "research_only",
        "frozen_before_results",
        "no_parameter_scan",
        "performance_forbidden_until_preflight_pass",
    )
    if not all(cfg.get(key) is True for key in required_true):
        raise PreflightError("research freeze and performance embargo are mandatory")
    if cfg.get("live_or_broker_calls") is not False or cfg.get("risk_pct") != 0:
        raise PreflightError("preflight must remain risk-zero with no broker calls")
    if cfg.get("current_permission") != "BLOCKED_FAIL_CLOSED_UNTIL_ALL_REQUIRED_INPUTS_PINNED":
        raise PreflightError("the persisted preregistration must remain fail-closed")
    if cfg.get("arms") != list(EXPECTED_ARMS):
        raise PreflightError("exactly the four frozen arms and schedules are required")
    if cfg.get("execution_contract") != EXPECTED_EXECUTION_CONTRACT:
        raise PreflightError("execution/cost/gap/next-open contract changed")
    if cfg.get("shared_exit_contract") != EXPECTED_SHARED_EXIT_CONTRACT:
        raise PreflightError("one frozen executable exit contract must serve every arm")
    if cfg.get("evaluation_contract") != EXPECTED_EVALUATION_CONTRACT:
        raise PreflightError("daily equity/DD, regimes, survivorship or forward contract changed")
    if cfg.get("automatic_verdict") != EXPECTED_AUTOMATIC_VERDICT:
        raise PreflightError("automatic verdict must never authorize performance or live changes early")
    source_code = cfg.get("source_code")
    if not isinstance(source_code, Mapping) or set(source_code) != set(SOURCE_PATHS):
        raise PreflightError("source hash contract is incomplete")
    artifacts = cfg.get("required_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(REQUIRED_ARTIFACT_TYPES):
        raise PreflightError("required input artifact set changed")
    for key, expected_type in REQUIRED_ARTIFACT_TYPES.items():
        contract = artifacts[key]
        if not isinstance(contract, Mapping) or contract.get("content_type") != expected_type:
            raise PreflightError(f"artifact contract changed: {key}")
        if set(contract) != {"content_type", "path", "sha256"}:
            raise PreflightError(f"artifact pin fields changed: {key}")
    if _has_forbidden_outcome_section(cfg):
        raise PreflightError("outcome/performance sections are forbidden in preregistration")


def actual_source_hashes(root: Path) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for key, rel in SOURCE_PATHS.items():
        try:
            path = _repo_file(root, rel)
            out[key] = sha256_file(path) if path.is_file() else None
        except (OSError, PreflightError):
            out[key] = None
    return out


def compute_contract_fingerprint(
    cfg: Mapping[str, Any], source_hashes: Mapping[str, object]
) -> str:
    return _canonical_sha(
        {
            "frozen_at_utc": cfg.get("frozen_at_utc"),
            "arms": cfg.get("arms"),
            "source_code": dict(source_hashes),
            "required_artifacts": cfg.get("required_artifacts"),
            "execution_contract": cfg.get("execution_contract"),
            "shared_exit_contract": cfg.get("shared_exit_contract"),
            "evaluation_contract": cfg.get("evaluation_contract"),
            "automatic_verdict": cfg.get("automatic_verdict"),
        }
    )


def _nested_file_reasons(root: Path, rows: object) -> list[str]:
    if not isinstance(rows, list) or not rows:
        return ["nested_files_missing"]
    reasons: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            reasons.append(f"nested_file_{index}_invalid")
            continue
        path_text = str(row.get("path") or "")
        expected = row.get("sha256")
        if path_text in seen:
            reasons.append("nested_file_path_duplicate")
        seen.add(path_text)
        if not _is_sha(expected):
            reasons.append(f"nested_file_{index}_unpinned")
            continue
        try:
            path = _repo_file(root, path_text)
        except PreflightError:
            reasons.append(f"nested_file_{index}_unsafe_path")
            continue
        if not path.is_file():
            reasons.append(f"nested_file_{index}_missing")
            continue
        try:
            if sha256_file(path) != expected:
                reasons.append(f"nested_file_{index}_hash_mismatch")
        except OSError:
            reasons.append(f"nested_file_{index}_unreadable")
    return sorted(set(reasons))


def _validate_universe(payload: object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["universe_payload_invalid"]
    reasons: list[str] = []
    if payload.get("schema_id") != "alpaca_point_in_time_universe_v1":
        reasons.append("universe_schema_invalid")
    if payload.get("point_in_time_membership") is not True:
        reasons.append("universe_not_point_in_time")
    if payload.get("selection_frozen_before_performance") is not True:
        reasons.append("universe_selection_not_frozen")
    rows = payload.get("membership_intervals")
    if not isinstance(rows, list) or not rows:
        reasons.append("universe_membership_missing")
    else:
        for row in rows:
            if not isinstance(row, Mapping) or not all(
                row.get(key) for key in ("symbol", "effective_from_utc", "source_record_sha256")
            ) or not _is_sha(row.get("source_record_sha256")):
                reasons.append("universe_membership_invalid")
                break
    return reasons


def _validate_market_manifest(root: Path, payload: object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["market_manifest_invalid"]
    reasons: list[str] = []
    expected = {
        "schema_id": "alpaca_point_in_time_market_data_manifest_v1",
        "point_in_time": True,
        "completed_bars_only": True,
        "calendar": "XNYS",
        "bar_interval": "1d",
        "price_basis": EXPECTED_EXECUTION_CONTRACT["price_basis"],
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        reasons.append("market_manifest_semantics_invalid")
    reasons.extend(_nested_file_reasons(root, payload.get("files")))
    return reasons


def _validate_broker_lifecycle(root: Path, payload: object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["broker_lifecycle_invalid"]
    reasons: list[str] = []
    if payload.get("schema_id") != "alpaca_broker_lifecycle_v1":
        reasons.append("broker_lifecycle_schema_invalid")
    if (
        payload.get("window_start_utc")
        != EXPECTED_EVALUATION_CONTRACT["broker_lifecycle_window_start_utc"]
        or payload.get("window_end_utc_exclusive")
        != EXPECTED_EVALUATION_CONTRACT["broker_lifecycle_window_end_utc_exclusive"]
    ):
        reasons.append("broker_lifecycle_window_invalid")
    if payload.get("reconstruction_complete") is not True:
        reasons.append("broker_lifecycle_incomplete")
    if payload.get("unresolved_conflicts") != 0 or payload.get("duplicate_fill_ids") != 0:
        reasons.append("broker_lifecycle_conflicts")
    if payload.get("redacted_no_secrets") is not True:
        reasons.append("broker_lifecycle_not_redacted")
    reasons.extend(_nested_file_reasons(root, payload.get("raw_export_files")))
    rows = payload.get("order_lifecycles")
    if not isinstance(rows, list) or not rows:
        reasons.append("broker_order_lifecycles_missing")
    else:
        order_ids: set[str] = set()
        fill_ids: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                reasons.append("broker_order_lifecycle_invalid")
                continue
            order_id = str(row.get("broker_order_id") or "")
            events = row.get("events")
            if not order_id or order_id in order_ids or not row.get("symbol"):
                reasons.append("broker_order_identity_invalid")
            order_ids.add(order_id)
            if not isinstance(events, list) or not events or any(
                not isinstance(event, Mapping)
                or not event.get("event_type")
                or not event.get("timestamp_utc")
                for event in events
            ):
                reasons.append("broker_order_events_invalid")
            fills = row.get("fills", [])
            if not isinstance(fills, list):
                reasons.append("broker_fills_invalid")
                continue
            for fill in fills:
                if not isinstance(fill, Mapping):
                    reasons.append("broker_fills_invalid")
                    continue
                fill_id = str(fill.get("fill_id") or "")
                try:
                    qty = float(fill.get("qty"))
                    price = float(fill.get("price"))
                except (TypeError, ValueError):
                    qty = price = 0.0
                if (
                    not fill_id
                    or fill_id in fill_ids
                    or not fill.get("timestamp_utc")
                    or not math.isfinite(qty)
                    or not math.isfinite(price)
                    or qty <= 0
                    or price <= 0
                ):
                    reasons.append("broker_fill_identity_or_value_invalid")
                fill_ids.add(fill_id)
        if payload.get("broker_order_count") != len(rows):
            reasons.append("broker_order_count_mismatch")
        if payload.get("broker_fill_count") != len(fill_ids):
            reasons.append("broker_fill_count_mismatch")
    return sorted(set(reasons))


def _validate_cost_gap(payload: object, broker_sha: object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["cost_gap_payload_invalid"]
    reasons: list[str] = []
    expected = {
        "schema_id": "alpaca_cost_gap_calibration_v1",
        "frozen_before_performance": True,
        "base_cost_bps_per_side": EXPECTED_EXECUTION_CONTRACT["base_cost_bps_per_side"],
        "stress_cost_bps_per_side": EXPECTED_EXECUTION_CONTRACT["stress_cost_bps_per_side"],
        "entry_gap_fill": EXPECTED_EXECUTION_CONTRACT["entry_gap_fill"],
        "stop_gap_fill": EXPECTED_EXECUTION_CONTRACT["stop_gap_fill"],
        "target_gap_fill": EXPECTED_EXECUTION_CONTRACT["target_gap_fill"],
        "same_bar_stop_and_target": EXPECTED_EXECUTION_CONTRACT["same_bar_stop_and_target"],
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        reasons.append("cost_gap_contract_mismatch")
    if not _is_sha(broker_sha) or payload.get("broker_lifecycle_sha256") != broker_sha:
        reasons.append("cost_gap_broker_receipt_mismatch")
    return reasons


def _validate_regimes(payload: object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["regime_payload_invalid"]
    reasons: list[str] = []
    if payload.get("schema_id") != "alpaca_causal_regime_labels_v1":
        reasons.append("regime_schema_invalid")
    if payload.get("rule_frozen_before_performance") is not True or payload.get("uses_future_data") is not False:
        reasons.append("regime_labels_not_causal")
    labels = payload.get("labels")
    if not isinstance(labels, list) or set(labels) != set(EXPECTED_EVALUATION_CONTRACT["required_regimes"]):
        reasons.append("required_regimes_missing")
    if not isinstance(payload.get("intervals"), list) or not payload.get("intervals"):
        reasons.append("regime_intervals_missing")
    return reasons


def _validate_survivorship(payload: object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["survivorship_payload_invalid"]
    expected = {
        "schema_id": "alpaca_survivorship_receipt_v1",
        "point_in_time_membership": True,
        "includes_delisted_names": True,
        "corporate_actions_known_as_of_event_time": True,
        "delisting_return_policy": "last_tradable_open_or_close_then_cash_with_frozen_costs",
    }
    return ["survivorship_contract_invalid"] if any(
        payload.get(key) != value for key, value in expected.items()
    ) else []


def _validate_forward(root: Path, payload: object) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["forward_manifest_invalid"]
    reasons: list[str] = []
    expected = {
        "schema_id": "alpaca_untouched_forward_manifest_v1",
        "window_start_utc": EXPECTED_EVALUATION_CONTRACT["untouched_forward_start_utc"],
        "sealed_before_performance": True,
        "used_for_strategy_development": False,
        "outcome_values_read_before_freeze": False,
        "calendar": "XNYS",
        "price_basis": EXPECTED_EXECUTION_CONTRACT["price_basis"],
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        reasons.append("forward_lockbox_semantics_invalid")
    if not payload.get("window_end_utc_exclusive"):
        reasons.append("forward_window_end_missing")
    reasons.extend(_nested_file_reasons(root, payload.get("files")))
    return reasons


def _validate_exit_conformance(
    payload: object,
    implementation_sha: object,
    broker_sha: object,
) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["exit_conformance_invalid"]
    reasons: list[str] = []
    if payload.get("schema_id") != "alpaca_shared_exit_conformance_v1":
        reasons.append("exit_conformance_schema_invalid")
    if payload.get("entrypoint") != EXPECTED_SHARED_EXIT_CONTRACT["entrypoint"]:
        reasons.append("exit_entrypoint_mismatch")
    if payload.get("arm_ids") != list(FROZEN_ARM_IDS):
        reasons.append("exit_not_shared_by_exact_arms")
    if payload.get("implementation_sha256") != implementation_sha or not _is_sha(implementation_sha):
        reasons.append("exit_implementation_receipt_mismatch")
    if payload.get("broker_lifecycle_sha256") != broker_sha or not _is_sha(broker_sha):
        reasons.append("exit_broker_receipt_mismatch")
    if payload.get("all_cases_passed") is not True or set(payload.get("passed_cases") or []) != CONFORMANCE_CASES:
        reasons.append("exit_conformance_cases_incomplete")
    if payload.get("broker_lifecycle_exact_match") is not True or payload.get("unresolved_mismatches") != 0:
        reasons.append("exit_broker_parity_unproven")
    return reasons


def _read_artifact(
    root: Path,
    name: str,
    contract: object,
) -> tuple[dict[str, Any], object | None]:
    base: dict[str, Any] = {"name": name, "ok": False, "reasons": []}
    if not isinstance(contract, Mapping):
        base["reasons"] = ["artifact_contract_missing"]
        return base, None
    base["content_type"] = contract.get("content_type")
    expected_sha = contract.get("sha256")
    if not _is_sha(expected_sha) or not contract.get("path"):
        base["reasons"] = ["artifact_unpinned"]
        return base, None
    try:
        path = _repo_file(root, contract.get("path"))
    except PreflightError as exc:
        base["reasons"] = [f"unsafe_path:{exc}"]
        return base, None
    base["path"] = str(path.relative_to(root))
    if not path.is_file():
        base["reasons"] = ["artifact_missing"]
        return base, None
    try:
        actual_sha = sha256_file(path)
    except OSError:
        base["reasons"] = ["artifact_unreadable"]
        return base, None
    base["sha256"] = actual_sha
    if actual_sha != expected_sha:
        base["reasons"] = ["artifact_hash_mismatch"]
        return base, None
    if contract.get("content_type") == "python_source_v1":
        reasons: list[str] = []
        if path.suffix != ".py":
            reasons.append("exit_implementation_not_python")
        else:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError):
                reasons.append("exit_implementation_not_parseable")
            else:
                functions = {
                    node.name
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                if EXPECTED_SHARED_EXIT_CONTRACT["entrypoint"] not in functions:
                    reasons.append("exit_entrypoint_missing")
        base.update({"ok": not reasons, "reasons": reasons})
        return base, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        base["reasons"] = [f"artifact_json_invalid:{type(exc).__name__}"]
        return base, None
    return base, payload


def evaluate_preflight(root: Path, cfg: Mapping[str, Any]) -> dict[str, Any]:
    validate_frozen_contract(cfg)
    actual_sources = actual_source_hashes(root)
    expected_sources = cfg["source_code"]
    source_status: list[dict[str, Any]] = []
    for key in SOURCE_PATHS:
        expected = expected_sources.get(key)
        actual = actual_sources.get(key)
        reasons: list[str] = []
        if not _is_sha(expected):
            reasons.append("source_unpinned")
        elif actual is None:
            reasons.append("source_missing")
        elif actual != expected:
            reasons.append("source_hash_mismatch")
        source_status.append({"name": key, "ok": not reasons, "reasons": reasons, "sha256": actual})

    expected_fingerprint = str(cfg.get("contract_fingerprint") or "")
    actual_fingerprint = compute_contract_fingerprint(cfg, actual_sources)
    fingerprint_ok = _is_sha(expected_fingerprint) and expected_fingerprint == actual_fingerprint

    contracts = cfg["required_artifacts"]
    artifact_status: dict[str, dict[str, Any]] = {}
    payloads: dict[str, object | None] = {}
    for name in REQUIRED_ARTIFACT_TYPES:
        status, payload = _read_artifact(root, name, contracts[name])
        artifact_status[name] = status
        payloads[name] = payload

    semantic_reasons: dict[str, list[str]] = {}
    semantic_reasons["point_in_time_universe"] = _validate_universe(payloads["point_in_time_universe"])
    semantic_reasons["market_data_manifest"] = _validate_market_manifest(root, payloads["market_data_manifest"])
    semantic_reasons["broker_fill_order_lifecycle_20260706_20260709"] = _validate_broker_lifecycle(
        root, payloads["broker_fill_order_lifecycle_20260706_20260709"]
    )
    broker_sha = contracts["broker_fill_order_lifecycle_20260706_20260709"].get("sha256")
    semantic_reasons["cost_gap_calibration"] = _validate_cost_gap(
        payloads["cost_gap_calibration"], broker_sha
    )
    semantic_reasons["regime_labels"] = _validate_regimes(payloads["regime_labels"])
    semantic_reasons["corporate_actions_survivorship"] = _validate_survivorship(
        payloads["corporate_actions_survivorship"]
    )
    semantic_reasons["untouched_forward_manifest"] = _validate_forward(
        root, payloads["untouched_forward_manifest"]
    )
    semantic_reasons["shared_exit_model_implementation"] = []
    semantic_reasons["shared_exit_model_conformance"] = _validate_exit_conformance(
        payloads["shared_exit_model_conformance"],
        contracts["shared_exit_model_implementation"].get("sha256"),
        broker_sha,
    )
    for name, reasons in semantic_reasons.items():
        if artifact_status[name]["reasons"]:
            continue
        artifact_status[name]["reasons"] = sorted(set(reasons))
        artifact_status[name]["ok"] = not reasons

    statuses = [artifact_status[name] for name in REQUIRED_ARTIFACT_TYPES]
    blockers: list[str] = []
    if any(not row["ok"] for row in source_status):
        blockers.append("frozen_source_hashes_not_ready")
    if not fingerprint_ok:
        blockers.append("contract_fingerprint_mismatch")
    if any(not row["ok"] for row in statuses):
        blockers.append("required_hash_pinned_inputs_not_ready")
    exit_names = {"shared_exit_model_implementation", "shared_exit_model_conformance"}
    if any(not artifact_status[name]["ok"] for name in exit_names):
        blockers.append("one_shared_executable_exit_model_not_proven")
    lifecycle_name = "broker_fill_order_lifecycle_20260706_20260709"
    if not artifact_status[lifecycle_name]["ok"]:
        blockers.append("jul6_9_broker_fill_order_lifecycle_not_reconstructed")
    if not artifact_status["untouched_forward_manifest"]["ok"]:
        blockers.append("untouched_forward_not_sealed")

    permission = "PERFORMANCE_REPLAY_ALLOWED" if not blockers else "BLOCKED_FAIL_CLOSED"
    return {
        "schema_version": 1,
        "experiment": cfg.get("name"),
        "permission": permission,
        "blockers": blockers,
        "frozen_arm_ids": list(FROZEN_ARM_IDS),
        "source_status": source_status,
        "contract_fingerprint_ok": fingerprint_ok,
        "artifacts": statuses,
        "performance_computed": False,
        "performance_fields_present": False,
        "outcome_access_allowed": permission == "PERFORMANCE_REPLAY_ALLOWED",
        "live_or_broker_calls": False,
        "promotion_authorized": False,
        "safe_hold_changed": False,
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_symlink():
        raise PreflightError("refusing output symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    output_path = args.output.resolve()
    try:
        config_path.relative_to(ROOT / "configs" / "preregistered")
        output_path.relative_to(ROOT / "reports" / "research")
    except ValueError as exc:
        raise SystemExit("config/output must remain in their prereg/research directories") from exc
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite evidence: {output_path}")
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        result = evaluate_preflight(ROOT, cfg)
        _atomic_json(output_path, result)
    except (OSError, json.JSONDecodeError, PreflightError) as exc:
        raise SystemExit(f"alpaca monthly parity preflight refused: {exc}") from exc
    print(json.dumps({"output": str(output_path), **result}, sort_keys=True))
    return 0 if result["permission"] == "PERFORMANCE_REPLAY_ALLOWED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
