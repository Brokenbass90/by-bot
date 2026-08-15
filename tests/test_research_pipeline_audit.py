import json
from datetime import datetime, timezone

from research_lab.research_pipeline_audit import audit
from research_lab.experiment_lifecycle import LifecycleLedger


def test_audit_distinguishes_healthy_collectors_from_open_experiment_bridge(tmp_path) -> None:
    (tmp_path / "runtime/local_research_station").mkdir(parents=True)
    (tmp_path / "runtime/research").mkdir(parents=True)
    (tmp_path / "runtime/research_nightly").mkdir(parents=True)
    (tmp_path / "configs/autoresearch").mkdir(parents=True)
    (tmp_path / "configs/research_proposals").mkdir(parents=True)
    (tmp_path / "runtime/local_research_station/status.json").write_text(json.dumps({
        "generated_at_utc": "2026-08-14T11:59:00+00:00",
        "healthy": True,
        "live_order_authority": False,
        "jobs": [{"state": "healthy", "live_order_authority": False}],
    }))
    (tmp_path / "runtime/research/idea_intake_queue.jsonl").write_text(json.dumps({
        "proposal_key": "abc", "status": "awaiting_owner_approval"
    }) + "\n")
    (tmp_path / "runtime/research_nightly/status.json").write_text(json.dumps({"ts": "2026-05-01T00:00:00+00:00"}))
    (tmp_path / "configs/autoresearch/approved_specs.txt").write_text("legacy.json\n")

    result = audit(tmp_path, now=datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc))

    assert result["continuous_station"]["healthy"] is True
    assert result["capabilities"]["idea_to_runnable_experiment_is_fully_automatic"] is False
    assert result["capabilities"]["approval_is_content_hash_bound"] is False
    assert result["lifecycle"]["control_code_available"] is False
    assert result["verdict"] == "PARTIAL_PIPELINE_NOT_SELF_IMPROVING_CLOSED_LOOP"


def test_audit_recognizes_valid_hash_chained_lifecycle(tmp_path) -> None:
    (tmp_path / "runtime/local_research_station").mkdir(parents=True)
    (tmp_path / "runtime/research_nightly").mkdir(parents=True)
    (tmp_path / "configs/autoresearch").mkdir(parents=True)
    (tmp_path / "configs/research_proposals").mkdir(parents=True)
    (tmp_path / "research_lab").mkdir(parents=True)
    (tmp_path / "research_lab/experiment_lifecycle.py").write_text("# installed\n")
    (tmp_path / "runtime/local_research_station/status.json").write_text(json.dumps({
        "generated_at_utc": "2026-08-14T11:59:00+00:00",
        "healthy": True,
        "live_order_authority": False,
        "jobs": [{"state": "healthy", "live_order_authority": False}],
    }))
    (tmp_path / "runtime/research_nightly/status.json").write_text(json.dumps({"ts": "2026-08-14T11:59:00+00:00"}))
    (tmp_path / "configs/autoresearch/approved_specs.txt").write_text("legacy.json\n")
    ledger = LifecycleLedger(
        tmp_path / "runtime/research/experiment_lifecycle.jsonl",
        project_root=tmp_path,
    )
    ledger.append(
        experiment_id="candidate_1",
        stage="IDEA_REGISTERED",
        payload={"hypothesis": "bounded"},
    )

    result = audit(tmp_path, now=datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc))

    assert result["lifecycle"]["control_code_available"] is True
    assert result["lifecycle"]["ledger_present"] is True
    assert result["lifecycle"]["integrity_pass"] is True
    assert result["lifecycle"]["experiments"] == 1
    assert result["capabilities"]["hash_bound_lifecycle_control_is_implemented"] is True
