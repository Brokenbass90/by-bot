from __future__ import annotations

import ast
import copy
import json
import shutil
from pathlib import Path

import pytest

from scripts.preflight_event_expansion_retest_long_v1_phase1 import (
    DEFAULT_CONFIG,
    EXPECTED_BLOCKERS,
    EXPECTED_PHASE0_SHA256,
    EXPECTED_PIN_ROLES,
    EXPECTED_RESOLVED_PHASE0,
    Phase1PreflightError,
    build_preflight,
    canonical_sha256,
    sha256_file,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict:
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def _refingerprint(cfg: dict) -> None:
    frozen = dict(cfg)
    frozen.pop("contract_fingerprint_sha256", None)
    cfg["contract_fingerprint_sha256"] = canonical_sha256(frozen)


def test_current_phase1_identity_is_clean_but_performance_and_live_are_blocked() -> None:
    payload = build_preflight(_config(), ROOT)

    assert payload["status"] == "BLOCKED_RESEARCH_RUNNER_DATA"
    assert payload["performance_permission"] == "PERFORMANCE_FORBIDDEN"
    assert payload["live_permission"] == "LIVE_FORBIDDEN"
    assert payload["identity"]["integrity_pass"] is True
    assert payload["identity"]["phase0_history"]["match"] is True
    assert payload["identity"]["dev13_manifest"]["match"] is True
    assert tuple(row["code"] for row in payload["blockers"]) == EXPECTED_BLOCKERS
    assert tuple(payload["resolved_phase0_code_contracts"]) == EXPECTED_RESOLVED_PHASE0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("current_automatic_verdict", "READY"),
        ("current_performance_permission", "PERFORMANCE_ALLOWED"),
        ("current_live_permission", "LIVE_ALLOWED"),
        ("risk_pct", 0.001),
        ("live_or_broker_calls", True),
        ("no_performance_access", False),
    ],
)
def test_safety_permissions_fail_closed(field: str, value: object) -> None:
    cfg = _config()
    cfg[field] = value
    _refingerprint(cfg)
    with pytest.raises(Phase1PreflightError):
        validate_contract(cfg)


def test_phase0_history_is_preserved_not_rewritten_or_expected_to_pass_now() -> None:
    cfg = _config()
    history = cfg["phase0_history"]
    assert history["mutation_allowed"] is False
    assert history["current_preflight_expected_to_pass"] is False
    assert sha256_file(ROOT / history["path"]) == EXPECTED_PHASE0_SHA256

    history["sha256"] = "0" * 64
    _refingerprint(cfg)
    with pytest.raises(Phase1PreflightError, match="phase-0"):
        validate_contract(cfg)


def test_resolved_contracts_cannot_remove_current_runner_or_data_blockers() -> None:
    cfg = _config()
    cfg["remaining_blockers"].pop(0)
    _refingerprint(cfg)
    with pytest.raises(Phase1PreflightError, match="blocker"):
        validate_contract(cfg)


def test_no_outcome_metrics_can_be_smuggled_into_phase1() -> None:
    cfg = _config()
    cfg["observed_metrics"] = {"profit_factor": 99.0}
    _refingerprint(cfg)
    with pytest.raises(Phase1PreflightError, match="outcome"):
        validate_contract(cfg)


def test_cohorts_and_dev_window_mismatch_remain_explicit() -> None:
    cfg = _config()
    assert cfg["cohorts"]["dev13"]["uniform_window_status"] == (
        "BLOCKED_BTC_ETH_MISSING_FINAL_119_M5"
    )
    assert cfg["cohorts"]["dev13"]["performance_authority"] is False
    assert cfg["cohorts"]["sealed_external8"]["data_status"] == "ABSENT_AND_UNREAD"
    assert cfg["cohorts"]["prospective"]["status"] == "NOT_STARTED"


def test_active_contract_pin_set_includes_bridge_store_and_conformance_tests() -> None:
    cfg = _config()
    roles = {
        row["role"]: row["path"]
        for row in cfg["implementation_identity"]["pinned_files"]
    }
    assert roles == EXPECTED_PIN_ROLES
    assert "mtf_execution_bridge_source" in roles
    assert "durable_state_outbox_source" in roles
    assert "mtf_execution_bridge_tests" in roles
    assert "durable_state_outbox_tests" in roles


def test_changed_pinned_file_marks_integrity_failed_without_unlocking_performance(
    tmp_path: Path,
) -> None:
    cfg = _config()
    relative_paths = [
        row["path"] for row in cfg["implementation_identity"]["pinned_files"]
    ]
    relative_paths.extend([
        cfg["phase0_history"]["path"],
        cfg["cohorts"]["dev13"]["manifest_path"],
    ])
    for relative in relative_paths:
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (tmp_path / "bot" / "event_long_mtf_execution_bridge_v1.py").write_text(
        "# changed after freeze\n", encoding="utf-8"
    )

    payload = build_preflight(cfg, tmp_path)

    assert payload["identity"]["integrity_pass"] is False
    assert payload["performance_permission"] == "PERFORMANCE_FORBIDDEN"
    assert payload["live_permission"] == "LIVE_FORBIDDEN"
    assert payload["blockers"][0]["code"] == "PINNED_FILE_HASH_MISMATCH"


def test_contract_fingerprint_detects_unacknowledged_edit() -> None:
    cfg = _config()
    cfg["purpose"] = "changed after freeze"
    with pytest.raises(Phase1PreflightError, match="fingerprint"):
        validate_contract(cfg)


def test_preflight_imports_only_standard_library() -> None:
    script = ROOT / "scripts" / "preflight_event_expansion_retest_long_v1_phase1.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots <= {
        "__future__", "argparse", "hashlib", "json", "sys",
        "datetime", "pathlib", "typing",
    }
