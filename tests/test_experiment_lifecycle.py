import json
import subprocess
import sys
from pathlib import Path

import pytest

from research_lab.experiment_lifecycle import LifecycleError, LifecycleLedger


def _artifact(root: Path, name: str, text: str = "x\n") -> str:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return name


def _through_result(ledger: LifecycleLedger, root: Path, experiment_id: str = "exp_1") -> None:
    idea = ledger.append(
        experiment_id=experiment_id,
        stage="IDEA_REGISTERED",
        payload={"hypothesis": "fixed hypothesis", "falsify_if": "net <= 0"},
    )
    ledger.append(
        experiment_id=experiment_id,
        stage="OWNER_APPROVED",
        payload={"approved_by": "owner", "subject_record_sha256": idea["record_sha256"]},
    )
    ledger.append(experiment_id=experiment_id, stage="PREREG_FROZEN", artifact_paths=[_artifact(root, "prereg.md")])
    ledger.append(experiment_id=experiment_id, stage="SPEC_BOUND", artifact_paths=[_artifact(root, "spec.json")])
    ledger.append(
        experiment_id=experiment_id,
        stage="PREFLIGHT_PASSED",
        payload={"exit_code": 0},
        artifact_paths=[_artifact(root, "preflight.json")],
    )
    ledger.append(experiment_id=experiment_id, stage="PASSPORT_WRITTEN", artifact_paths=[_artifact(root, "passport.json")])
    ledger.append(experiment_id=experiment_id, stage="RESULT_WRITTEN", artifact_paths=[_artifact(root, "result.json")])


def test_complete_lifecycle_is_hash_chained_and_artifact_verified(tmp_path: Path) -> None:
    ledger = LifecycleLedger(tmp_path / "ledger.jsonl", project_root=tmp_path)
    _through_result(ledger, tmp_path)
    ledger.append(
        experiment_id="exp_1",
        stage="INDEPENDENT_AUDIT_PASSED",
        payload={"exit_code": 0},
        artifact_paths=[_artifact(tmp_path, "audit.json")],
    )
    ledger.append(experiment_id="exp_1", stage="DECISION_ACCEPTED", payload={"decision": "research_accept"})

    summary = ledger.summary()
    assert summary["integrity_pass"] is True
    assert summary["experiments"]["exp_1"]["terminal"] is True
    assert summary["experiments"]["exp_1"]["status"] == "DECISION_ACCEPTED"
    assert summary["capital_or_promotion_authority"] is False


def test_owner_approval_must_bind_prior_record_hash(tmp_path: Path) -> None:
    ledger = LifecycleLedger(tmp_path / "ledger.jsonl", project_root=tmp_path)
    ledger.append(experiment_id="exp_1", stage="IDEA_REGISTERED")
    with pytest.raises(LifecycleError, match="approval is not bound"):
        ledger.append(
            experiment_id="exp_1",
            stage="OWNER_APPROVED",
            payload={"approved_by": "owner", "subject_record_sha256": "0" * 64},
        )


def test_nonzero_independent_audit_fails_closed(tmp_path: Path) -> None:
    ledger = LifecycleLedger(tmp_path / "ledger.jsonl", project_root=tmp_path)
    _through_result(ledger, tmp_path)
    with pytest.raises(LifecycleError, match="nonzero audit"):
        ledger.append(
            experiment_id="exp_1",
            stage="INDEPENDENT_AUDIT_PASSED",
            payload={"exit_code": 2},
            artifact_paths=[_artifact(tmp_path, "audit.json")],
        )
    ledger.append(
        experiment_id="exp_1",
        stage="INDEPENDENT_AUDIT_FAILED",
        payload={"exit_code": 2},
        artifact_paths=[_artifact(tmp_path, "audit.json")],
    )
    ledger.append(experiment_id="exp_1", stage="DECISION_REJECTED", payload={"reason": "audit failed"})
    assert ledger.summary()["experiments"]["exp_1"]["status"] == "DECISION_REJECTED"


def test_changed_artifact_and_corrupt_row_fail_closed(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = LifecycleLedger(ledger_path, project_root=tmp_path)
    idea = ledger.append(experiment_id="exp_1", stage="IDEA_REGISTERED")
    ledger.append(
        experiment_id="exp_1",
        stage="OWNER_APPROVED",
        payload={"approved_by": "owner", "subject_record_sha256": idea["record_sha256"]},
    )
    prereg = _artifact(tmp_path, "prereg.md")
    ledger.append(experiment_id="exp_1", stage="PREREG_FROZEN", artifact_paths=[prereg])
    (tmp_path / prereg).write_text("changed\n", encoding="utf-8")
    with pytest.raises(LifecycleError, match="artifact changed"):
        ledger.summary()

    ledger_path.write_text(ledger_path.read_text(encoding="utf-8") + "{broken\n", encoding="utf-8")
    with pytest.raises(LifecycleError, match="invalid JSON"):
        ledger.read_verified()


def test_stage_skips_and_duplicate_result_are_rejected(tmp_path: Path) -> None:
    ledger = LifecycleLedger(tmp_path / "ledger.jsonl", project_root=tmp_path)
    ledger.append(experiment_id="exp_1", stage="IDEA_REGISTERED")
    with pytest.raises(LifecycleError, match="out-of-order"):
        ledger.append(experiment_id="exp_1", stage="RESULT_WRITTEN", artifact_paths=[_artifact(tmp_path, "result.json")])

    ledger2 = LifecycleLedger(tmp_path / "ledger2.jsonl", project_root=tmp_path)
    _through_result(ledger2, tmp_path, "exp_2")
    with pytest.raises(LifecycleError, match="duplicate stage"):
        ledger2.append(experiment_id="exp_2", stage="RESULT_WRITTEN", artifact_paths=["result.json"])


def test_tampered_record_hash_is_rejected(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = LifecycleLedger(ledger_path, project_root=tmp_path)
    ledger.append(experiment_id="exp_1", stage="IDEA_REGISTERED")
    row = json.loads(ledger_path.read_text(encoding="utf-8"))
    row["payload"] = {"tampered": True}
    ledger_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(LifecycleError, match="record hash mismatch"):
        ledger.read_verified()


def test_audit_cli_writes_atomic_receipt(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    ledger_path = project_root / "runtime/research/experiment_lifecycle.jsonl"
    LifecycleLedger(ledger_path, project_root=project_root).append(
        experiment_id="receipt_probe",
        stage="IDEA_REGISTERED",
        payload={"question": "Does the audit produce a durable receipt?"},
    )
    output = project_root / "reports/evidence/lifecycle.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "research_lab/experiment_lifecycle.py"),
            "--project-root",
            str(project_root),
            "--ledger",
            str(ledger_path),
            "audit",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["integrity_pass"] is True
    assert receipt["records"] == 1
    assert not output.with_suffix(".json.tmp").exists()
