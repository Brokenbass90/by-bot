from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_failure_forensic_audits_existing_consumed_run_without_payload_access() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import (
        audit_failure,
        verify_tracked_forensic_receipt,
    )

    receipt = audit_failure(ROOT)
    verify_tracked_forensic_receipt(
        ROOT / "reports/receipts/ATT1_SBR1_RESERVED_OOS_FAILURE_FORENSIC_2026_08_29.json",
        receipt,
    )
    assert receipt["decision"] == "AUDIT_CONFIRMED_FAIL_CLOSED_AFTER_CLAIM"
    assert receipt["authority"] == "research_only_failure_forensic_no_money_no_promotion"
    assert receipt["root_cause"] == "AttributeError:'tuple' object has no attribute 'get'"
    assert receipt["economics"]["ATT1"]["decision"] == "FAIL_CLOSED"
    assert receipt["economics"]["SBR1"]["decision"] == "INCONCLUSIVE_LOW_N"


def test_failure_forensic_rejects_receipt_hash_tamper(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import FailureAuditViolation, verify_receipt

    receipt = {"terminal_state": "FAIL_CLOSED_AFTER_CLAIM", "receipt_sha256": "0" * 64}
    with pytest.raises(FailureAuditViolation, match="receipt canonical hash drift"):
        verify_receipt(receipt)


def _forensic_tree(tmp_path: Path) -> Path:
    config = json.loads((ROOT / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json").read_text())
    for row in config["source_pins"]:
        target = tmp_path / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / row["path"], target)
    for relative in (
        "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json",
        "configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json",
        "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json",
        "scripts/run_att1_sbr1_reserved_oos_v1.py",
        "scripts/audit_att1_sbr1_reserved_oos_v1.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    shutil.copytree(ROOT / "research_lab/results/att1_sbr1_reserved_oos_v1", tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1")
    return tmp_path


def test_failure_forensic_temp_evidence_tree_happy_and_observed_hash_tamper(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import FailureAuditViolation, audit_failure

    root = _forensic_tree(tmp_path)
    assert audit_failure(root)["decision"] == "AUDIT_CONFIRMED_FAIL_CLOSED_AFTER_CLAIM"
    path = root / "research_lab/results/att1_sbr1_reserved_oos_v1/att1_base_live.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(FailureAuditViolation, match="partial output hash drift:att1_base_live.jsonl"):
        audit_failure(root)


def _rehash_failure_receipt(root: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import RECEIPT, canonical_sha256, sha256_file

    path = root / RECEIPT
    value = json.loads(path.read_text())
    output = path.parent
    for name in value["partial_output_file_sha256"]:
        value["partial_output_file_sha256"][name] = sha256_file(output / name)
    for row in value["observed_output_entries"]:
        row["sha256"] = sha256_file(output / row["name"])
    value.pop("receipt_sha256", None)
    value["receipt_sha256"] = canonical_sha256(value)
    path.write_text(json.dumps(value, sort_keys=True))


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("extra", "actual output inventory drift"),
        ("bootstrap", "decode accounting drift:bootstrap"),
        ("authorization", "authorization contract drift"),
        ("threshold", "threshold pin drift"),
        ("parity", "parity report drift:ATT1:base"),
    ],
)
def test_failure_forensic_temp_tamper_cases_fail_closed(tmp_path: Path, kind: str, expected: str) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import AUTH, OUTPUT, RECEIPT, FailureAuditViolation, audit_failure, canonical_sha256, sha256_file

    root = _forensic_tree(tmp_path)
    if kind == "extra":
        (root / OUTPUT / "forged-extra").write_text("x")
    elif kind == "bootstrap":
        path = root / RECEIPT; value = json.loads(path.read_text()); value["decode_accounting"]["bootstrap"]["rows"] = 1; value.pop("receipt_sha256"); value["receipt_sha256"] = canonical_sha256(value); path.write_text(json.dumps(value, sort_keys=True))
    elif kind == "authorization":
        path = root / AUTH; value = json.loads(path.read_text()); value["authority"] = "forged"; path.write_text(json.dumps(value, sort_keys=True)); claim = root / OUTPUT / "one_shot_claim.json"; receipt = root / RECEIPT
        for target in (claim, receipt):
            value = json.loads(target.read_text()); value["authorization_sha256"] = sha256_file(path)
            if target == receipt: value.pop("receipt_sha256"); value["receipt_sha256"] = canonical_sha256(value)
            target.write_text(json.dumps(value, sort_keys=True))
    elif kind == "threshold":
        path = root / "research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json"; path.write_text(path.read_text() + " ")
    else:
        path = root / OUTPUT / "att1_base_parity_report.json"; value = json.loads(path.read_text()); value["decision"] = "FAIL_CLOSED"; path.write_text(json.dumps(value)); _rehash_failure_receipt(root)
    with pytest.raises(FailureAuditViolation, match=expected):
        audit_failure(root)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("manifest_accounting", "decode frozen pin drift:reserved:BTCUSDT"),
        ("classification", "terminal forensic fields drift"),
        ("evaluation_schema", "evaluation schema drift:ATT1:1"),
        ("parity_field", "parity report drift:ATT1:base"),
    ],
)
def test_failure_forensic_binds_frozen_identity_and_strict_evidence(tmp_path: Path, kind: str, expected: str) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import OUTPUT, RECEIPT, FailureAuditViolation, audit_failure, canonical_sha256

    root = _forensic_tree(tmp_path)
    if kind == "manifest_accounting":
        path = root / RECEIPT; value = json.loads(path.read_text()); value["decode_accounting"]["reserved"]["inputs"]["BTCUSDT"]["sha256"] = "0" * 64; value["decode_accounting"]["reserved"]["inputs"]["BTCUSDT"]["opened_sha256"] = "0" * 64; value.pop("receipt_sha256"); value["receipt_sha256"] = canonical_sha256(value); path.write_text(json.dumps(value, sort_keys=True))
    elif kind == "classification":
        path = root / RECEIPT; value = json.loads(path.read_text()); value["classification"] = "forged"; value.pop("receipt_sha256"); value["receipt_sha256"] = canonical_sha256(value); path.write_text(json.dumps(value, sort_keys=True))
    elif kind == "evaluation_schema":
        for shaped in ("research", "live"):
            path = root / OUTPUT / f"att1_evaluation_{shaped}.jsonl"; lines = path.read_text().splitlines(); row = json.loads(lines[0]); row["forged"] = True; lines[0] = json.dumps(row, sort_keys=True, separators=(",", ":")); path.write_text("\n".join(lines) + "\n")
        _rehash_failure_receipt(root)
    else:
        path = root / OUTPUT / "att1_base_parity_report.json"; value = json.loads(path.read_text()); value["matched_rows"] = 0; path.write_text(json.dumps(value)); _rehash_failure_receipt(root)
    with pytest.raises(FailureAuditViolation, match=expected):
        audit_failure(root)


def test_forensic_receipt_self_hash_and_tracked_drift_fail_closed(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import FailureAuditViolation, audit_failure, verify_forensic_receipt, verify_tracked_forensic_receipt

    fresh = audit_failure(_forensic_tree(tmp_path))
    forged = dict(fresh); forged["decision"] = "PASS"
    with pytest.raises(FailureAuditViolation, match="forensic receipt self hash drift"):
        verify_forensic_receipt(forged)
    path = tmp_path / "tracked.json"; path.write_text(json.dumps(forged))
    with pytest.raises(FailureAuditViolation, match="forensic receipt self hash drift"):
        verify_tracked_forensic_receipt(path, fresh)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("bootstrap_rows", "decode frozen identity drift:bootstrap:BTCUSDT"),
        ("reserved_json_decoded", "decode frozen identity drift:reserved:BTCUSDT"),
        ("accounting_timing", "decode accounting timing drift"),
        ("evaluation_identity", "evaluation schema drift:ATT1:1"),
        ("evaluation_regime_type", "evaluation schema drift:ATT1:1"),
        ("evaluation_signal_type", "evaluation signal drift:ATT1:"),
        ("evaluation_signal_decimal", "evaluation signal drift:ATT1:"),
        ("evaluation_coverage", "evaluation coverage drift:ATT1"),
        ("parity_authority_extra", "parity report drift:ATT1:base"),
    ],
)
def test_failure_forensic_rejects_coordinated_accounting_and_schema_tamper(
    tmp_path: Path,
    kind: str,
    expected: str,
) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import (
        OUTPUT,
        RECEIPT,
        FailureAuditViolation,
        audit_failure,
        canonical_sha256,
    )

    root = _forensic_tree(tmp_path)
    if kind in {"bootstrap_rows", "reserved_json_decoded", "accounting_timing"}:
        path = root / RECEIPT
        value = json.loads(path.read_text())
        if kind == "bootstrap_rows":
            value["decode_accounting"]["bootstrap"]["inputs"]["BTCUSDT"]["rows"] = 1
        elif kind == "reserved_json_decoded":
            value["decode_accounting"]["reserved"]["inputs"]["BTCUSDT"]["json_decoded"] = False
        else:
            value["decode_accounting"]["bootstrap"]["started_at_utc"] = "2020-01-01T00:00:00Z"
        value.pop("receipt_sha256")
        value["receipt_sha256"] = canonical_sha256(value)
        path.write_text(json.dumps(value, sort_keys=True))
    elif kind in {"evaluation_identity", "evaluation_regime_type", "evaluation_signal_type", "evaluation_signal_decimal", "evaluation_coverage"}:
        for shaped in ("research", "live"):
            path = root / OUTPUT / f"att1_evaluation_{shaped}.jsonl"
            lines = path.read_text().splitlines()
            if kind == "evaluation_coverage":
                lines.pop()
            else:
                line_index = (
                    0
                    if kind in {"evaluation_identity", "evaluation_regime_type"}
                    else next(
                        index
                        for index, raw in enumerate(lines)
                        if json.loads(raw)["signal"] is not None
                    )
                )
                row = json.loads(lines[line_index])
                if kind == "evaluation_identity":
                    row["symbol"] = "FORGEDUSDT"
                    row["regime_bar_ts"] = "not-an-int"
                elif kind == "evaluation_regime_type":
                    row["regime_value"] = []
                elif kind == "evaluation_signal_type":
                    row["signal"]["entry"] = 123
                else:
                    row["signal"]["entry"] = "not-a-decimal"
                lines[line_index] = json.dumps(row, sort_keys=True, separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n")
        _rehash_failure_receipt(root)
    else:
        path = root / OUTPUT / "att1_base_parity_report.json"
        value = json.loads(path.read_text())
        value["money_authority"] = True
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
        _rehash_failure_receipt(root)

    with pytest.raises(FailureAuditViolation, match=expected):
        audit_failure(root)


def test_failure_forensic_normalizes_metric_and_decision_decimal_errors() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import (
        FailureAuditViolation,
        _checks,
        _decision,
    )

    receipt = json.loads(
        (ROOT / "reports/receipts/ATT1_SBR1_RESERVED_OOS_FAILURE_FORENSIC_2026_08_29.json").read_text()
    )
    sleeve = receipt["economics"]["ATT1"]
    metrics = sleeve["modes"]["base"]["metrics"]
    thresholds = sleeve["thresholds"]

    malformed_metrics = {**metrics, "mean_r": "not-a-decimal"}
    with pytest.raises(FailureAuditViolation, match="invalid decimal"):
        _checks(malformed_metrics, thresholds)

    low_n_base = {**metrics, "n": 20}
    low_n_stress = {**metrics, "n": 20, "sum_r": "not-a-decimal"}
    with pytest.raises(FailureAuditViolation, match="invalid decimal"):
        _decision(low_n_base, low_n_stress, thresholds, 20)


def test_forensic_receipt_requires_complete_schema_even_when_resigned() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import (
        FailureAuditViolation,
        audit_failure,
        canonical_sha256,
        verify_forensic_receipt,
    )

    forged = audit_failure(ROOT)
    forged.pop("claim_sha256")
    forged.pop("forensic_receipt_sha256")
    forged["forensic_receipt_sha256"] = canonical_sha256(forged)
    with pytest.raises(FailureAuditViolation, match="forensic receipt contract drift"):
        verify_forensic_receipt(forged)


def test_json_object_rejects_symlinked_parent(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import FailureAuditViolation, _object

    real = tmp_path / "real"
    real.mkdir()
    (real / "receipt.json").write_text("{}")
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(FailureAuditViolation, match="missing or unsafe test object"):
        _object(linked / "receipt.json", "test object")


def test_failure_forensic_revalidates_candidate_manifest_source_pin(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_failure_v1 import (
        FailureAuditViolation,
        audit_failure,
    )

    root = _forensic_tree(tmp_path)
    path = root / "configs/research/att1_sbr1_live_native_parity_v1.json"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(FailureAuditViolation, match="candidate pin drift"):
        audit_failure(root)
