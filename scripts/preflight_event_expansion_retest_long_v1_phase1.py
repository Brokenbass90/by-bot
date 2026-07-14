#!/usr/bin/env python3
"""Fail-closed phase-1 identity preflight for the event-long research sleeve.

Phase 1 freezes causal mechanics, durable single-writer state/outbox storage,
the exact research execution bridge, and immutable input identity.  It may hash
data files and validate a manifest, but cannot simulate trades, calculate
returns, call a broker, or authorize performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_event_long_dev13_uniform_window_v1 import (  # noqa: E402
    UniformWindowError,
    validate_uniform_window_manifest,
)

DEFAULT_CONFIG = (
    ROOT
    / "configs"
    / "preregistered"
    / "event_expansion_retest_long_v1_phase1_20260713.json"
)

EXPECTED_NAME = "event_expansion_retest_long_v1_20260713_phase1"
EXPECTED_PHASE = "PHASE_1_CAUSAL_CONTRACTS_ONLY"
EXPECTED_PHASE1_ORIGINAL_FREEZE = {
    "commit": "e05f7b376db4f643818b9b506d808a95066b6a84",
    "file_sha256": "47ff9ddff0e22a4965f4ccf99bac90690e40f586eddf559ad862c15e3df708b4",
    "contract_fingerprint_sha256": "4d1dcf764c2f183945c01919ab8e52796f72ccc2d00ad945a950745e9c1ce993",
    "history_preserved_in_git": True,
    "amendment_scope": "DEV13_UNIFORM_WINDOW_INPUT_IDENTITY_ONLY_NO_OUTCOMES",
}
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
EXPECTED_UNIFORM_MANIFEST_PATH = (
    "configs/preregistered/event_long_dev13_uniform_m5_window_v1_20260714.json"
)
EXPECTED_UNIFORM_MANIFEST_SHA256 = (
    "16b4f746a982c4e688de1c6766d93fb916173f3f3e636b7230038455d68facfb"
)
EXPECTED_UNIFORM_VALIDATOR_PATH = (
    "scripts/validate_event_long_dev13_uniform_window_v1.py"
)
EXPECTED_UNIFORM_VALIDATOR_SHA256 = (
    "f26e58cdcf9dc5002911399a731f107f9fb8ae5ae891c41e08dd89283803549f"
)
EXPECTED_UNIFORM_WINDOW_STATUS = "VERIFIED_VIRTUAL_COMMON_WINDOW_CROP"
EXPECTED_UNIFORM_START_UTC = "2024-07-15T00:00:00Z"
EXPECTED_UNIFORM_END_UTC_EXCLUSIVE = "2026-07-04T14:05:00Z"
EXPECTED_UNIFORM_ROWS = 207241
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
    "uniform_window_validator_source": "scripts/validate_event_long_dev13_uniform_window_v1.py",
    "uniform_window_validator_tests": "tests/test_validate_event_long_dev13_uniform_window_v1.py",
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
    "EXTERNAL8_MARKET_DATA_ABSENT",
    "EXTERNAL8_METADATA_ABSENT",
    "EXTERNAL8_LIQUIDITY_ABSENT",
    "EXTERNAL8_FUNDING_ABSENT",
    "ATT1_REFERENCE_ABSENT",
)
EXPECTED_RESOLVED_PHASE1 = ("DEV13_UNIFORM_WINDOW_MANIFEST_ABSENT",)

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version", "name", "frozen_at_utc", "input_identity_amended_at_utc",
    "phase1_original_freeze", "phase", "purpose", "research_only",
    "no_parameter_scan", "no_performance_access", "live_or_broker_calls",
    "risk_pct", "current_automatic_verdict", "current_performance_permission",
    "current_live_permission", "phase0_history", "implementation_identity",
    "frozen_contracts", "cohorts", "phase0_blocker_transitions",
    "resolved_phase1_blockers", "evaluation_gate_inheritance",
    "remaining_blockers", "contract_fingerprint_sha256",
}

# Outcome keys are normalized with Unicode NFKC + casefold + punctuation folding,
# then checked in both tokenized and compact forms.  This intentionally covers
# common aliases rather than only the exact spelling used by one report writer.
_OUTCOME_KEY_ALIASES = {
    "performance_results", "outcome_results", "trade_results", "observed_metrics",
    "selected_winner", "promotion_verdict", "pnl", "p_l", "profit_and_loss",
    "profit_loss", "gross_pnl", "gross_p_l", "net_pnl", "net_p_l",
    "realized_pnl", "realized_p_l", "unrealized_pnl", "unrealized_p_l",
    "sharpe", "sharpe_ratio", "sortino", "sortino_ratio", "calmar",
    "calmar_ratio", "cagr", "annual_return", "annualized_return",
    "annualised_return", "total_return", "gross_return", "net_return",
    "return", "returns", "return_pct", "roi", "monthly_return",
    "monthly_returns", "returns_by_month", "monthly_pnl", "trades",
    "trade_count", "trades_count", "number_of_trades", "num_trades",
    "n_trades", "profit_factor", "pf", "win_rate", "winrate", "loss_rate",
    "max_drawdown", "max_drawdown_pct", "drawdown", "drawdown_pct", "dd",
    "expectancy", "expectancy_r", "average_trade", "avg_trade", "equity_curve",
}
_OUTCOME_KEY_COMPACT = {alias.replace("_", "") for alias in _OUTCOME_KEY_ALIASES}
_OUTCOME_COMPACT_FRAGMENTS = {
    "pnl", "sharpe", "sortino", "calmar", "cagr", "profitfactor",
    "winrate", "drawdown", "expectancy", "monthlyreturn", "totalreturn",
    "grossreturn", "netreturn", "returnpct", "returnsbymonth", "trades",
    "annualizedreturn", "annualisedreturn", "tradecount", "numberoftrades",
    "numtrades", "closedtrades", "equitycurve",
}


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


def _require_exact_keys(value: object, expected: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise Phase1PreflightError(f"{name} schema keys changed")
    return value


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


def _normalized_key(value: object) -> tuple[str, str]:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return normalized, normalized.replace("_", "")


def _outcome_key_path(value: object, path: str = "$") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized, compact = _normalized_key(key)
            if (
                normalized in _OUTCOME_KEY_ALIASES
                or compact in _OUTCOME_KEY_COMPACT
                or any(fragment in compact for fragment in _OUTCOME_COMPACT_FRAGMENTS)
            ):
                return f"{path}.{key}"
            nested = _outcome_key_path(item, f"{path}.{key}")
            if nested is not None:
                return nested
    if isinstance(value, list):
        for index, item in enumerate(value):
            nested = _outcome_key_path(item, f"{path}[{index}]")
            if nested is not None:
                return nested
    return None


def validate_contract(cfg: Mapping[str, Any]) -> None:
    outcome_path = _outcome_key_path(cfg)
    if outcome_path is not None:
        raise Phase1PreflightError(
            f"phase-1 freeze contains forbidden outcome metric at {outcome_path}"
        )
    _require_exact_keys(cfg, EXPECTED_TOP_LEVEL_KEYS, "phase-1 root")
    if cfg.get("schema_version") != 1 or cfg.get("name") != EXPECTED_NAME:
        raise Phase1PreflightError("phase-1 schema/name changed")
    if cfg.get("phase") != EXPECTED_PHASE:
        raise Phase1PreflightError("phase must remain causal-contracts-only")
    if cfg.get("phase1_original_freeze") != EXPECTED_PHASE1_ORIGINAL_FREEZE:
        raise Phase1PreflightError("original phase-1 freeze lineage changed")
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

    history = _require_exact_keys(
        cfg.get("phase0_history"),
        {
            "path", "sha256", "contract_fingerprint_sha256", "mutation_allowed",
            "current_preflight_expected_to_pass", "reason_current_preflight_may_fail",
        },
        "phase0_history",
    )
    if history.get("path") != EXPECTED_PHASE0_PATH:
        raise Phase1PreflightError("phase-0 history reference changed")
    if (
        history.get("sha256") != EXPECTED_PHASE0_SHA256
        or history.get("contract_fingerprint_sha256") != EXPECTED_PHASE0_FINGERPRINT
        or history.get("mutation_allowed") is not False
        or history.get("current_preflight_expected_to_pass") is not False
    ):
        raise Phase1PreflightError("phase-0 historical identity/semantics changed")

    identity = _require_exact_keys(
        cfg.get("implementation_identity"),
        {
            "side_identity", "level_scope", "sloped_levels",
            "default_mtf_config_fingerprint_sha256", "component_commits", "pinned_files",
        },
        "implementation_identity",
    )
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

    contracts = _require_exact_keys(
        cfg.get("frozen_contracts"),
        {
            "raw_source", "causal_sequence", "same_bar_stage_collapse_allowed",
            "future_bar_access_allowed", "execution", "durable_state_outbox",
            "research_bridge",
        },
        "frozen_contracts",
    )
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

    cohorts = _require_exact_keys(
        cfg.get("cohorts"), {"dev13", "sealed_external8", "prospective"}, "cohorts"
    )
    dev = cohorts["dev13"]
    external = cohorts["sealed_external8"]
    prospective = cohorts["prospective"]
    _require_exact_keys(
        dev,
        {
            "role", "symbols", "source_interval", "requested_window_start_utc",
            "requested_window_end_utc_exclusive", "manifest_path", "manifest_sha256",
            "uniform_window_status", "observed_common_safe_end_utc_exclusive",
            "uniform_window_manifest_path", "uniform_window_manifest_sha256",
            "uniform_window_start_utc", "uniform_window_end_utc_exclusive",
            "uniform_window_rows_per_symbol", "performance_authority",
        },
        "cohorts.dev13",
    )
    _require_exact_keys(
        external,
        {"role", "symbols", "data_status", "sealed_before_data_access", "manifest_path", "manifest_sha256"},
        "cohorts.sealed_external8",
    )
    _require_exact_keys(
        prospective,
        {"role", "status", "start_utc", "retroactive_backfill_as_prospective"},
        "cohorts.prospective",
    )
    if tuple(dev.get("symbols", ())) != EXPECTED_DEV13:
        raise Phase1PreflightError("dev13 symbols changed")
    if (
        dev.get("manifest_path") != EXPECTED_DEV_MANIFEST_PATH
        or dev.get("manifest_sha256") != EXPECTED_DEV_MANIFEST_SHA256
        or dev.get("performance_authority") is not False
        or dev.get("uniform_window_status") != EXPECTED_UNIFORM_WINDOW_STATUS
        or dev.get("uniform_window_manifest_path") != EXPECTED_UNIFORM_MANIFEST_PATH
        or dev.get("uniform_window_manifest_sha256") != EXPECTED_UNIFORM_MANIFEST_SHA256
        or dev.get("uniform_window_start_utc") != EXPECTED_UNIFORM_START_UTC
        or dev.get("uniform_window_end_utc_exclusive") != EXPECTED_UNIFORM_END_UTC_EXCLUSIVE
        or dev.get("uniform_window_rows_per_symbol") != EXPECTED_UNIFORM_ROWS
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
    if (
        not isinstance(transitions, list)
        or len(transitions) != len(EXPECTED_RESOLVED_PHASE0)
        or not all(isinstance(row, Mapping) for row in transitions)
        or tuple(row.get("phase0_code") for row in transitions) != EXPECTED_RESOLVED_PHASE0
    ):
        raise Phase1PreflightError("phase-0 blocker transitions changed")
    if any(row.get("status") != "RESOLVED_CODE_CONTRACT_ONLY" for row in transitions):
        raise Phase1PreflightError("a resolved code contract was overstated")
    if any(set(row) != {"phase0_code", "status", "evidence"} for row in transitions):
        raise Phase1PreflightError("phase-0 transition schema changed")

    resolved_phase1 = cfg.get("resolved_phase1_blockers")
    if (
        not isinstance(resolved_phase1, list)
        or len(resolved_phase1) != len(EXPECTED_RESOLVED_PHASE1)
        or not all(isinstance(row, Mapping) for row in resolved_phase1)
        or tuple(row.get("code") for row in resolved_phase1) != EXPECTED_RESOLVED_PHASE1
    ):
        raise Phase1PreflightError("resolved phase-1 blocker set changed")
    expected_resolution = {
        "code": "DEV13_UNIFORM_WINDOW_MANIFEST_ABSENT",
        "status": "RESOLVED_INPUT_IDENTITY_ONLY_NO_OUTCOMES",
        "artifact_path": EXPECTED_UNIFORM_MANIFEST_PATH,
        "artifact_sha256": EXPECTED_UNIFORM_MANIFEST_SHA256,
        "validator_path": EXPECTED_UNIFORM_VALIDATOR_PATH,
        "validator_sha256": EXPECTED_UNIFORM_VALIDATOR_SHA256,
        "performance_permission_changed": False,
        "live_permission_changed": False,
    }
    if resolved_phase1 != [expected_resolution]:
        raise Phase1PreflightError("uniform-window resolution identity changed")

    blockers = cfg.get("remaining_blockers")
    if (
        not isinstance(blockers, list)
        or len(blockers) != len(EXPECTED_BLOCKERS)
        or not all(isinstance(row, Mapping) for row in blockers)
        or tuple(row.get("code") for row in blockers) != EXPECTED_BLOCKERS
    ):
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
    uniform_path = _repo_file(root, dev["uniform_window_manifest_path"])
    uniform_actual = sha256_file(uniform_path) if uniform_path.is_file() else None
    uniform_match = uniform_actual == dev["uniform_window_manifest_sha256"]
    uniform_receipt: dict[str, Any] = {}
    uniform_error: str | None = None
    if uniform_match:
        try:
            uniform_receipt = validate_uniform_window_manifest(
                root,
                uniform_path,
                verify_rows=False,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError, UniformWindowError) as exc:
            uniform_match = False
            uniform_error = str(exc)
    else:
        uniform_error = "the hash-pinned uniform-window manifest changed or disappeared"
    if not uniform_match:
        integrity_blockers.append({
            "code": "DEV13_UNIFORM_WINDOW_MANIFEST_INVALID",
            "severity": "CRITICAL",
            "reason": uniform_error or "uniform-window validation failed",
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
            },
            "dev13_uniform_window": {
                "path": dev["uniform_window_manifest_path"],
                "expected_sha256": dev["uniform_window_manifest_sha256"],
                "actual_sha256": uniform_actual,
                "match": uniform_match,
                "status": dev["uniform_window_status"],
                "start_utc": dev["uniform_window_start_utc"],
                "end_utc_exclusive": dev["uniform_window_end_utc_exclusive"],
                "rows_per_symbol": dev["uniform_window_rows_per_symbol"],
                "source_hashes_verified": uniform_receipt.get("source_hashes_verified", False),
                "rows_verified": uniform_receipt.get("rows_verified", False),
            },
            "sealed_external8": list(cfg["cohorts"]["sealed_external8"]["symbols"]),
            "prospective_status": cfg["cohorts"]["prospective"]["status"],
            "integrity_pass": not integrity_blockers,
        },
        "resolved_phase0_code_contracts": [
            row["phase0_code"] for row in cfg["phase0_blocker_transitions"]
        ],
        "resolved_phase1_input_contracts": [
            row["code"] for row in cfg["resolved_phase1_blockers"]
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
