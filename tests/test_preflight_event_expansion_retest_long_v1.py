from __future__ import annotations

import ast
import copy
import json
import shutil
from pathlib import Path

import pytest

from scripts.preflight_event_expansion_retest_long_v1 import (
    DEFAULT_CONFIG,
    EXPECTED_BLOCKERS,
    EXPECTED_DEV13,
    EXPECTED_EXTERNAL8,
    PreflightError,
    build_preflight,
    canonical_sha256,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict:
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def _refingerprint(cfg: dict) -> None:
    frozen = dict(cfg)
    frozen.pop("contract_fingerprint_sha256", None)
    cfg["contract_fingerprint_sha256"] = canonical_sha256(frozen)


def test_historical_phase0_detects_superseded_level_hashes_and_stays_blocked() -> None:
    payload = build_preflight(_config(), ROOT)

    assert payload["status"] == "BLOCKED_RESEARCH_MECHANICS"
    assert payload["performance_permission"] == "PERFORMANCE_FORBIDDEN"
    assert payload["live_permission"] == "LIVE_FORBIDDEN"
    # Phase 0 is intentionally immutable historical evidence.  The active
    # LevelSnapshot source/tests were causally hardened after that freeze, so
    # its old hashes must now fail rather than being silently rewritten.
    assert payload["identity"]["integrity_pass"] is False
    assert payload["identity"]["dev13_manifest"]["hash_match"] is True
    assert payload["identity"]["dev13_manifest"]["shape_match"] is True
    assert tuple(payload["identity"]["dev13_manifest"]["symbols"]) == EXPECTED_DEV13
    assert tuple(payload["identity"]["sealed_external8"]) == EXPECTED_EXTERNAL8
    assert [row["reason"] for row in payload["blockers"][:3]] == [
        "pinned identity mismatch: level_snapshot_source",
        "pinned identity mismatch: level_snapshot_tests",
        "pinned identity mismatch: phase0_preflight_tests",
    ]
    assert tuple(row["code"] for row in payload["blockers"][:3]) == (
        "PINNED_FILE_HASH_MISMATCH",
        "PINNED_FILE_HASH_MISMATCH",
        "PINNED_FILE_HASH_MISMATCH",
    )
    assert tuple(row["code"] for row in payload["blockers"][3:]) == EXPECTED_BLOCKERS
    assert "EXACT_CLOSED_BAR_AGGREGATION_ABSENT" not in EXPECTED_BLOCKERS


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("current_automatic_verdict", "READY"),
        ("current_performance_permission", "PERFORMANCE_ALLOWED"),
        ("current_live_permission", "LIVE_ALLOWED"),
        ("risk_pct", 0.001),
        ("live_or_broker_calls", True),
    ],
)
def test_safety_permissions_fail_closed(field: str, value: object) -> None:
    cfg = _config()
    cfg[field] = value
    _refingerprint(cfg)
    with pytest.raises(PreflightError):
        validate_contract(cfg)


def test_exact_cohorts_cannot_be_result_selected() -> None:
    cfg = _config()
    cfg["cohorts"]["sealed_external8"]["symbols"][-1] = "AAVEUSDT"
    _refingerprint(cfg)
    with pytest.raises(PreflightError, match="external8"):
        validate_contract(cfg)


def test_strict_future_gate_cannot_be_relaxed() -> None:
    cfg = _config()
    cfg["future_evaluation_gates"]["aggregate"]["stress_profit_factor_min"] = 1.01
    _refingerprint(cfg)
    with pytest.raises(PreflightError, match="numerical gate"):
        validate_contract(cfg)


def test_prospective_start_is_forbidden_before_successor_freeze() -> None:
    cfg = _config()
    cfg["cohorts"]["prospective"]["start_utc"] = "2026-07-13T12:00:00Z"
    cfg["cohorts"]["prospective"]["status"] = "RUNNING"
    _refingerprint(cfg)
    with pytest.raises(PreflightError, match="prospective"):
        validate_contract(cfg)


def test_phase0_cannot_smuggle_outcomes_into_preregistration() -> None:
    cfg = _config()
    cfg["outcome_results"] = {"profit_factor": 99}
    _refingerprint(cfg)
    with pytest.raises(PreflightError, match="outcome"):
        validate_contract(cfg)


def test_contract_fingerprint_detects_unacknowledged_edit() -> None:
    cfg = _config()
    cfg["purpose"] = "changed after freeze"
    with pytest.raises(PreflightError, match="fingerprint"):
        validate_contract(cfg)


def test_changed_pinned_file_keeps_status_blocked_and_marks_integrity(tmp_path: Path) -> None:
    cfg = _config()
    relative_paths = [
        row["path"] for row in cfg["implementation_identity"]["pinned_files"]
    ]
    relative_paths.append(cfg["cohorts"]["dev13"]["manifest_path"])
    for relative in relative_paths:
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (tmp_path / "bot" / "level_snapshot_v1.py").write_text(
        "# changed after freeze\n", encoding="utf-8"
    )

    payload = build_preflight(cfg, tmp_path)

    assert payload["status"] == "BLOCKED_RESEARCH_MECHANICS"
    assert payload["performance_permission"] == "PERFORMANCE_FORBIDDEN"
    assert payload["identity"]["integrity_pass"] is False
    assert payload["blockers"][0]["code"] == "PINNED_FILE_HASH_MISMATCH"


def test_preflight_imports_only_standard_library() -> None:
    script = ROOT / "scripts" / "preflight_event_expansion_retest_long_v1.py"
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


def test_horizontal_only_and_aggregation_are_explicitly_pinned() -> None:
    cfg = _config()
    identity = cfg["implementation_identity"]
    roles = {row["role"] for row in identity["pinned_files"]}
    assert identity["level_scope"] == "horizontal_h1_h4_resistance_flip_only"
    assert identity["sloped_levels"] == "DEFERRED_TO_A_SEPARATE_VERSIONED_CONTRACT"
    assert "closed_bar_aggregation_source" in roles
    assert "closed_bar_aggregation_tests" in roles
