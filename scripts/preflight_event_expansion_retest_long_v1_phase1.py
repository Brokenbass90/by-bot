#!/usr/bin/env python3
"""Fail-closed phase-1 identity preflight for the event-long research sleeve.

Phase 1 freezes causal mechanics, durable single-writer state/outbox storage,
and the exact research execution bridge.  It deliberately cannot load bars,
simulate trades, calculate returns, call a broker, or authorize performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT
    / "configs"
    / "preregistered"
    / "event_expansion_retest_long_v1_phase1_20260713.json"
)

EXPECTED_NAME = "event_expansion_retest_long_v1_20260713_phase1"
EXPECTED_PHASE = "PHASE_1_CAUSAL_CONTRACTS_ONLY"
EXPECTED_PHASE0_PATH = (
    "configs/preregistered/event_expansion_retest_long_v1_20260713.json"
)
EXPECTED_PHASE0_SHA256 = (
    "8660ae7718951a9acfb510df0549d38ebef265c5dd67e1a692029bd9d7dc88de"
)
EXPECTED_PHASE0_FINGERPRINT = (
    "317a3a63d437a2ce0aad06bee7dcea61a12e333fd1306ac7236719729fe40c7d"
)
EXPECTED_DEV_MANIFEST_PATH = (
    "data_cache/immutable/"
    "pump_exhaustion_unwind_short_v1_720d_20260711/manifest.json"
)
EXPECTED_DEV_MANIFEST_SHA256 = (
    "f1f425e8822a5a8de56676fb24f257982d4c5fb33e254a328dc2b8243aedffd8"
)
EXPECTED_DEV13 = (
    "1000PEPEUSDT", "ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT",
    "DOGEUSDT", "ETHUSDT", "ONDOUSDT", "SOLUSDT", "SUIUSDT",
    "TAOUSDT", "WIFUSDT", "XRPUSDT",
)
EXPECTED_EXTERNAL8 = (
    "FILUSDT", "UNIUSDT", "ETCUSDT", "ICPUSDT",
    "TRXUSDT", "TONUSDT", "MNTUSDT", "IMXUSDT",
)
EXPECTED_COMPONENT_COMMITS = {
    "closed_bar_aggregation": "f07dd012810d55028d238fe5d6780e591768bb64",
    "level_evidence": "7249b45a9542055ec9e1b25740f1afde5e478456",
    "mtf_orchestrator": "72c273d05cc93b945bea8709e25275a8e9f51b25",
    "execution_contract": "dd427c4194c702405677cf1ee7dca3cad61c65f3",
    "durable_state_outbox": "d7608d8432c637eb8222d9ae5f2d72360bd064ad",
    "mtf_execution_bridge": "1f95e85637e4fb79e33441f727e6d40447003efd",
}
EXPECTED_PIN_ROLES = {
    "phase1_preflight": "scripts/preflight_event_expansion_retest_long_v1_phase1.py",
    "closed_bar_aggregation_source": "bot/closed_bar_aggregation_v1.py",
    "closed_bar_aggregation_tests": "tests/test_closed_bar_aggregation_v1.py",
    "level_snapshot_source": "bot/level_snapshot_v1.py",
    "level_snapshot_tests": "tests/test_level_snapshot_v1.py",
    "market_context_dependency": "bot/market_context.py",
    "mtf_orchestrator_source": "strategies/event_expansion_retest_long_mtf_v1.py",
    "mtf_orchestrator_tests": "tests/test_event_expansion_retest_long_mtf_v1.py",
    "execution_contract_source": "bot/event_long_execution_v1.py",
    "execution_contract_tests": "tests/test_event_long_execution_v1.py",
    "mtf_execution_bridge_source": "bot/event_long_mtf_execution_bridge_v1.py",
    "mtf_execution_bridge_tests": "tests/test_event_long_mtf_execution_bridge_v1.py",
    "durable_state_outbox_source": "bot/event_expansion_retest_long_mtf_state_store.py",
    "durable_state_outbox_tests": "tests/test_event_expansion_retest_long_mtf_state_store.py",
    "phase1_preflight_tests": "tests/test_preflight_event_expansion_retest_long_v1_phase1.py",
}
EXPECTED_RESOLVED_PHASE0 = (
    "MULTITIMEFRAME_ORCHESTRATOR_ABSENT",
    "EXIT_MODEL_ABSENT",
    "COST_FUNDING_MODEL_ABSENT",
)
EXPECTED_BLOCKERS = (
    "PERFORMANCE_RUNNER_ABSENT",
    "DURABLE_EXECUTION_RECEIPT_AND_ACK_RUNNER_ABSENT",
    "FUNDING_COMPLETENESS_PROOF_ABSENT",
    "DEV13_UNIFORM_WINDOW_MANIFEST_ABSENT",
    "EXTERNAL8_MARKET_DATA_ABSENT",
    "EXTERNAL8_METADATA_ABSENT",
    "EXTERNAL8_LIQUIDITY_ABSENT",
    "EXTERNAL8_FUNDING_ABSENT",
    "ATT1_REFERENCE_ABSENT",
)


class Phase1PreflightError(ValueError):
    """The phase-1 freeze is malformed or its identity has drifted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _repo_file(root: Path, raw: object) -> Path:
    text = str(raw or "")
    relative = Path(text)
    if not text or relative.is_absolute() or "\\" in text:
        raise Phase1PreflightError(f"path must be non-empty and repo-relative: {text!r}")
    if any(part in {"", ".", ".."} for part in relative.parts) or ".git" in relative.parts:
        raise Phase1PreflightError(f"unsafe repo-relative path: {text!r}")
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise Phase1PreflightError(f"pinned path contains a symlink: {text!r}")
    return cursor


def _contract_fingerprint(cfg: Mapping[str, Any]) -> str:
    frozen = dict(cfg)
    frozen.pop("contract_fingerprint_sha256", None)
    return canonical_sha256(frozen)


def _contains_outcomes(value: object) -> bool:
    forbidden = {
        "performance_results", "outcome_results", "trade_results",
        "observed_metrics", "selected_winner", "promotion_verdict",
        "profit_factor", "return_pct", "max_drawdown_pct", "win_rate",
    }
    if isinstance(value, Mapping):
        return any(
            str(key) in forbidden or _contains_outcomes(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_outcomes(item) for item in value)
    return False


def validate_contract(cfg: Mapping[str, Any]) -> None:
    if cfg.get("schema_version") != 1 or cfg.get("name") != EXPECTED_NAME:
        raise Phase1PreflightError("phase-1 schema/name changed")
    if cfg.get("phase") != EXPECTED_PHASE:
        raise Phase1PreflightError("phase must remain causal-contracts-only")
    if not all(cfg.get(key) is True for key in (
        "research_only", "no_parameter_scan", "no_performance_access",
    )):
        raise Phase1PreflightError("research-only performance embargo is mandatory")
    if cfg.get("live_or_broker_calls") is not False or cfg.get("risk_pct") != 0:
        raise Phase1PreflightError("phase 1 must remain broker-free and risk-zero")
    if cfg.get("current_automatic_verdict") != "BLOCKED_RESEARCH_RUNNER_DATA":
        raise Phase1PreflightError("phase-1 verdict must remain blocked")
    if cfg.get("current_performance_permission") != "PERFORMANCE_FORBIDDEN":
        raise Phase1PreflightError("performance permission must remain forbidden")
    if cfg.get("current_live_permission") != "LIVE_FORBIDDEN":
        raise Phase1PreflightError("live permission must remain forbidden")

    history = cfg.get("phase0_history")
    if not isinstance(history, Mapping) or history.get("path") != EXPECTED_PHASE0_PATH:
        raise Phase1PreflightError("phase-0 history reference changed")
    if (
        history.get("sha256") != EXPECTED_PHASE0_SHA256
        or history.get("contract_fingerprint_sha256") != EXPECTED_PHASE0_FINGERPRINT
        or history.get("mutation_allowed") is not False
        or history.get("current_preflight_expected_to_pass") is not False
    ):
        raise Phase1PreflightError("phase-0 historical identity/semantics changed")

    identity = cfg.get("implementation_identity")
    if not isinstance(identity, Mapping):
        raise Phase1PreflightError("implementation identity is missing")
    if identity.get("side_identity") != "long_only":
        raise Phase1PreflightError("physical long-only identity changed")
    if identity.get("level_scope") != "horizontal_h1_h4_resistance_flip_only":
        raise Phase1PreflightError("phase 1 is horizontal H1/H4 only")
    if identity.get("sloped_levels") != "DEFERRED_TO_A_SEPARATE_VERSIONED_CONTRACT":
        raise Phase1PreflightError("sloped levels must remain separate")
    if identity.get("default_mtf_config_fingerprint_sha256") != (
        "b2a0529e343ed273675f9b3e11af27be95ca62c42b94c842c68929a87ecd3d4e"
    ):
        raise Phase1PreflightError("default MTF configuration identity changed")
    if identity.get("component_commits") != EXPECTED_COMPONENT_COMMITS:
        raise Phase1PreflightError("component commit set changed")
    pins = identity.get("pinned_files")
    if not isinstance(pins, list) or len(pins) != len(EXPECTED_PIN_ROLES):
        raise Phase1PreflightError("pinned source/dependency/test set is incomplete")
    pin_map: dict[str, Mapping[str, Any]] = {}
    for row in pins:
        if not isinstance(row, Mapping) or set(row) != {"role", "path", "sha256"}:
            raise Phase1PreflightError("each pinned file needs role/path/sha256 only")
        role = str(row.get("role") or "")
        if role in pin_map:
            raise Phase1PreflightError(f"duplicate pinned role: {role}")
        pin_map[role] = row
    if set(pin_map) != set(EXPECTED_PIN_ROLES):
        raise Phase1PreflightError("pinned roles changed")
    for role, expected_path in EXPECTED_PIN_ROLES.items():
        if pin_map[role].get("path") != expected_path or not _is_sha256(pin_map[role].get("sha256")):
            raise Phase1PreflightError(f"invalid frozen pin: {role}")

    contracts = cfg.get("frozen_contracts")
    if not isinstance(contracts, Mapping):
        raise Phase1PreflightError("frozen causal contracts are missing")
    expected_sequence = [
        "closed_H1_expansion",
        "later_closed_M15_hold",
        "later_first_M15_retest_consumed_once",
        "later_confirmed_M15_higher_low_pivot",
        "strictly_later_closed_M15_BOS",
        "exact_same_boundary_next_M5_open",
    ]
    if contracts.get("causal_sequence") != expected_sequence:
        raise Phase1PreflightError("causal multi-timeframe sequence changed")
    if contracts.get("same_bar_stage_collapse_allowed") is not False:
        raise Phase1PreflightError("same-bar stage collapse is forbidden")
    if contracts.get("future_bar_access_allowed") is not False:
        raise Phase1PreflightError("future-bar access is forbidden")
    if contracts.get("execution") != {
        "entry": "actual_exact_next_M5_open",
        "stop": "frozen_below_min_retest_low_and_zone_low_with_ATR_buffer",
        "targets": "reanchored_from_actual_open_1R_50pct_2R_50pct",
        "max_hold_m5": 96,
        "same_bar_ambiguity": "STOP_FIRST",
        "base_fee_slippage_bps_per_side": [6.0, 2.0],
        "stress_fee_slippage_bps_per_side": [10.0, 5.0],
        "funding_credit_bps": 0.0,
        "stress_min_funding_debit_bps_per_event": 5.0,
        "missing_funding": "FAIL_CLOSED",
    }:
        raise Phase1PreflightError("execution/cost contract changed")
    if contracts.get("durable_state_outbox") != {
        "atomic_single_file": True,
        "file_mode": "0600",
        "temp_fsync_replace_directory_fsync": True,
        "pending_outbox_blocks_replay": True,
        "ack_is_atomic_and_reload_verified": True,
        "interprocess_writers": False,
    }:
        raise Phase1PreflightError("durable state/outbox contract changed")
    if contracts.get("research_bridge") != {
        "requires_exact_pending_outbox_plan": True,
        "binds_M5_H1_M15_level_event_state_and_config": True,
        "persists_or_acknowledges": False,
        "live_or_broker_calls": False,
    }:
        raise Phase1PreflightError("MTF-to-execution bridge contract changed")

    cohorts = cfg.get("cohorts")
    if not isinstance(cohorts, Mapping) or set(cohorts) != {"dev13", "sealed_external8", "prospective"}:
        raise Phase1PreflightError("cohort split changed")
    dev = cohorts["dev13"]
    external = cohorts["sealed_external8"]
    prospective = cohorts["prospective"]
    if tuple(dev.get("symbols", ())) != EXPECTED_DEV13:
        raise Phase1PreflightError("dev13 symbols changed")
    if (
        dev.get("manifest_path") != EXPECTED_DEV_MANIFEST_PATH
        or dev.get("manifest_sha256") != EXPECTED_DEV_MANIFEST_SHA256
        or dev.get("performance_authority") is not False
        or dev.get("uniform_window_status") != "BLOCKED_BTC_ETH_MISSING_FINAL_119_M5"
    ):
        raise Phase1PreflightError("dev13 data-quality status changed")
    if tuple(external.get("symbols", ())) != EXPECTED_EXTERNAL8:
        raise Phase1PreflightError("sealed external8 symbols changed")
    if external.get("data_status") != "ABSENT_AND_UNREAD" or external.get("sealed_before_data_access") is not True:
        raise Phase1PreflightError("external8 seal/status changed")
    if external.get("manifest_path") or external.get("manifest_sha256"):
        raise Phase1PreflightError("external8 data cannot be attached silently")
    if prospective.get("status") != "NOT_STARTED" or prospective.get("start_utc") is not None:
        raise Phase1PreflightError("prospective period cannot start in phase 1")

    transitions = cfg.get("phase0_blocker_transitions")
    if not isinstance(transitions, list) or tuple(
        row.get("phase0_code") for row in transitions if isinstance(row, Mapping)
    ) != EXPECTED_RESOLVED_PHASE0:
        raise Phase1PreflightError("phase-0 blocker transitions changed")
    if any(row.get("status") != "RESOLVED_CODE_CONTRACT_ONLY" for row in transitions):
        raise Phase1PreflightError("a resolved code contract was overstated")

    blockers = cfg.get("remaining_blockers")
    if not isinstance(blockers, list) or tuple(
        row.get("code") for row in blockers if isinstance(row, Mapping)
    ) != EXPECTED_BLOCKERS:
        raise Phase1PreflightError("remaining blocker set/order changed")
    for row in blockers:
        if set(row) != {"code", "required_artifact", "path", "sha256"}:
            raise Phase1PreflightError("blocker artifact fields changed")
        if row.get("path") or row.get("sha256"):
            raise Phase1PreflightError("missing phase-1 artifacts cannot be pre-filled")

    gates = cfg.get("evaluation_gate_inheritance")
    if gates != {
        "source_path": EXPECTED_PHASE0_PATH,
        "source_sha256": EXPECTED_PHASE0_SHA256,
        "source_contract_fingerprint_sha256": EXPECTED_PHASE0_FINGERPRINT,
        "relaxation_allowed": False,
        "pass_authorizes_live_automatically": False,
    }:
        raise Phase1PreflightError("strict phase-0 evaluation gates are not inherited exactly")
    if _contains_outcomes(cfg):
        raise Phase1PreflightError("phase-1 freeze contains forbidden outcome metrics")
    if cfg.get("contract_fingerprint_sha256") != _contract_fingerprint(cfg):
        raise Phase1PreflightError("contract fingerprint mismatch")


def _phase0_identity(cfg: Mapping[str, Any], root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    history = cfg["phase0_history"]
    path = _repo_file(root, history["path"])
    actual = sha256_file(path) if path.is_file() else None
    fingerprint = None
    if actual == history["sha256"]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            fingerprint = raw.get("contract_fingerprint_sha256")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            fingerprint = None
    ok = actual == history["sha256"] and fingerprint == history["contract_fingerprint_sha256"]
    blockers = [] if ok else [{
        "code": "PHASE0_HISTORY_IDENTITY_MISMATCH",
        "severity": "CRITICAL",
        "reason": "the immutable historical phase-0 contract changed or disappeared",
    }]
    return {
        "path": history["path"],
        "expected_sha256": history["sha256"],
        "actual_sha256": actual,
        "expected_contract_fingerprint_sha256": history["contract_fingerprint_sha256"],
        "actual_contract_fingerprint_sha256": fingerprint,
        "match": ok,
    }, blockers


def build_preflight(cfg: Mapping[str, Any], root: Path) -> dict[str, Any]:
    validate_contract(cfg)
    identity = cfg["implementation_identity"]
    file_rows: list[dict[str, Any]] = []
    integrity_blockers: list[dict[str, str]] = []
    for pin in identity["pinned_files"]:
        path = _repo_file(root, pin["path"])
        actual = sha256_file(path) if path.is_file() else None
        match = actual == pin["sha256"]
        file_rows.append({
            "role": pin["role"],
            "path": pin["path"],
            "expected_sha256": pin["sha256"],
            "actual_sha256": actual,
            "match": match,
        })
        if not match:
            integrity_blockers.append({
                "code": "PINNED_FILE_HASH_MISMATCH",
                "severity": "CRITICAL",
                "reason": f"pinned identity mismatch: {pin['role']}",
            })
    phase0, phase0_blockers = _phase0_identity(cfg, root)
    integrity_blockers.extend(phase0_blockers)
    dev = cfg["cohorts"]["dev13"]
    manifest_path = _repo_file(root, dev["manifest_path"])
    manifest_actual = sha256_file(manifest_path) if manifest_path.is_file() else None
    manifest_match = manifest_actual == dev["manifest_sha256"]
    if not manifest_match:
        integrity_blockers.append({
            "code": "DEV13_MANIFEST_HASH_MISMATCH",
            "severity": "CRITICAL",
            "reason": "the pinned development manifest changed or disappeared",
        })
    declared = [{
        "code": row["code"],
        "severity": "CRITICAL",
        "reason": row["required_artifact"],
    } for row in cfg["remaining_blockers"]]
    return {
        "schema": "event_expansion_retest_long_v1_phase1_preflight",
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "BLOCKED_RESEARCH_RUNNER_DATA",
        "performance_permission": "PERFORMANCE_FORBIDDEN",
        "live_permission": "LIVE_FORBIDDEN",
        "identity": {
            "preregistration": cfg["name"],
            "contract_fingerprint_sha256": cfg["contract_fingerprint_sha256"],
            "side_identity": identity["side_identity"],
            "component_commits": identity["component_commits"],
            "pinned_files": file_rows,
            "phase0_history": phase0,
            "dev13_manifest": {
                "path": dev["manifest_path"],
                "expected_sha256": dev["manifest_sha256"],
                "actual_sha256": manifest_actual,
                "match": manifest_match,
                "uniform_window_status": dev["uniform_window_status"],
            },
            "sealed_external8": list(cfg["cohorts"]["sealed_external8"]["symbols"]),
            "prospective_status": cfg["cohorts"]["prospective"]["status"],
            "integrity_pass": not integrity_blockers,
        },
        "resolved_phase0_code_contracts": [
            row["phase0_code"] for row in cfg["phase0_blocker_transitions"]
        ],
        "blockers": integrity_blockers + declared,
    }


def _failure_payload(message: str) -> dict[str, Any]:
    return {
        "schema": "event_expansion_retest_long_v1_phase1_preflight",
        "status": "BLOCKED_RESEARCH_RUNNER_DATA",
        "performance_permission": "PERFORMANCE_FORBIDDEN",
        "live_permission": "LIVE_FORBIDDEN",
        "identity": {"integrity_pass": False},
        "blockers": [{
            "code": "PHASE1_PREREGISTRATION_INTEGRITY_FAILURE",
            "severity": "CRITICAL",
            "reason": str(message),
        }],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(cfg, Mapping):
            raise Phase1PreflightError("config root must be an object")
        payload = build_preflight(cfg, args.root.resolve())
        exit_code = 0 if payload["identity"]["integrity_pass"] else 2
    except (OSError, TypeError, ValueError, json.JSONDecodeError, Phase1PreflightError) as exc:
        payload = _failure_payload(str(exc))
        exit_code = 2
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
