from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json"


def test_preexecution_audit_is_metadata_only_and_ready() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import build_preexecution_audit

    receipt = build_preexecution_audit(ROOT)

    assert receipt["decision"] == "READY_FOR_OWNER_AUTHORIZATION"
    assert receipt["reserved_market_files_opened"] == 0
    assert receipt["reserved_market_rows_decoded"] == 0
    assert receipt["performance_computed"] is False
    assert receipt["owner_authorization_present"] is False
    assert receipt["claim_present"] is False
    assert receipt["result_present"] is False


def test_preexecution_audit_rejects_authorization_claim_or_result(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, build_preexecution_audit

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    (tmp_path / "configs/research").mkdir(parents=True)
    (tmp_path / "configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json").write_text("{}\n")

    with pytest.raises(AuditViolation, match="owner authorization"):
        build_preexecution_audit(tmp_path, config=config)


def test_preexecution_audit_does_not_import_runner() -> None:
    import sys

    from scripts.audit_att1_sbr1_reserved_oos_v1 import build_preexecution_audit

    sys.modules.pop("scripts.run_att1_sbr1_reserved_oos_v1", None)
    build_preexecution_audit(ROOT)
    assert "scripts.run_att1_sbr1_reserved_oos_v1" not in sys.modules


def test_audit_receipt_self_hash_tampering_fails_closed() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, canonical_sha256, verify_audit_receipt

    receipt = {"schema_id": "fixture", "decision": "AUDIT_PASS_RESEARCH_ONLY", "money_authority": False}
    receipt["audit_receipt_sha256"] = canonical_sha256(receipt)
    verify_audit_receipt(receipt)
    receipt["decision"] = "PASS_ZERO_RISK_INTEGRATION_ONLY"
    with pytest.raises(AuditViolation, match="audit receipt self hash drift"):
        verify_audit_receipt(receipt)


def test_reported_runner_decision_tampering_fails_independent_check() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_reported_sleeves

    independent = {
        "ATT1": {"modes": {"base": {"metrics": {"n": 1}}, "stress": {"metrics": {"n": 1}}}, "checks": {"base": {"n_gte": False}, "stress": {"n_gte": False}}, "decision": "INCONCLUSIVE_LOW_N"},
        "SBR1": {"modes": {"base": {"metrics": {"n": 1}}, "stress": {"metrics": {"n": 1}}}, "checks": {"base": {"n_gte": False}, "stress": {"n_gte": False}}, "decision": "INCONCLUSIVE_LOW_N"},
    }
    reported = json.loads(json.dumps(independent))
    reported["ATT1"]["decision"] = "PASS_ZERO_RISK_INTEGRATION_ONLY"
    with pytest.raises(AuditViolation, match="runner sleeve decision drift:ATT1"):
        verify_reported_sleeves(reported, independent)


def test_postexecution_missing_artifacts_fail_before_ledger_access(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, audit_postexecution

    with pytest.raises(AuditViolation, match="missing regular file"):
        audit_postexecution(tmp_path)


def test_claim_receipt_timing_inversion_fails_closed() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_claim_timing

    with pytest.raises(AuditViolation, match="claim receipt timing inversion"):
        verify_claim_timing("2026-08-27T00:00:01Z", "2026-08-27T00:00:00Z", "2026-08-27T00:00:02Z")


def test_ledger_mismatch_fails_independent_comparator() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_ledger_parity

    with pytest.raises(AuditViolation, match="research/live ledger mismatch:ATT1:base"):
        verify_ledger_parity({("BTCUSDT", 1, "long"): {}}, {}, "ATT1", "base")


def test_missing_output_artifact_fails_exact_inventory(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_output_inventory

    with pytest.raises(AuditViolation, match="output hash inventory drift"):
        verify_output_inventory(tmp_path, {})
