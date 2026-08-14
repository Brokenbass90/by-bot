import json
from datetime import datetime, timezone

from research_lab.research_pipeline_audit import audit


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
    assert result["verdict"] == "PARTIAL_PIPELINE_NOT_SELF_IMPROVING_CLOSED_LOOP"
