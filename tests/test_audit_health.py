import json
import os
from datetime import datetime, timezone
from pathlib import Path

from research_lab.audit_health import build_health
from research_lab.audit_health import _pid_alive


def _seed(root: Path, now: float, *, complete: bool = True) -> None:
    audit = root / "runtime" / "project_audit"
    audit.mkdir(parents=True)
    stamp = datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds")
    (audit / "supervisor_status.json").write_text(json.dumps({"last_success_utc": stamp}), encoding="utf-8")
    payload = {"summary": {"total": 1}, "findings": [{"id": "one"}]}
    (audit / "registry.json").write_text(json.dumps(payload), encoding="utf-8")
    (audit / "registry.csv").write_text("id\none\n", encoding="utf-8")
    (audit / "registry.md").write_text("ok\n", encoding="utf-8")
    (root / "runtime" / "ai_audit").mkdir(parents=True)
    ai = root / "runtime" / "ai_audit" / "today.md"
    ai.write_text("ok\n", encoding="utf-8")
    ai.touch()
    negative = root / "runtime" / "strategy_diagnostics"
    negative.mkdir(parents=True)
    (negative / "registry.json").write_text(json.dumps({
        "generated_at_utc": stamp,
        "findings": [],
    }), encoding="utf-8")
    marker = "LIVENESS_SWEEP_COMPLETE total=1 live=1 dead=0 skipped=0 timeouts=0\n" if complete else ""
    (root / "runtime" / "liveness_table.txt").write_text("header\n" + marker, encoding="utf-8")


def test_health_passes_consistent_completed_artifacts(tmp_path: Path):
    now = datetime.now(timezone.utc).timestamp()
    _seed(tmp_path, now)
    result = build_health(tmp_path, now_epoch=now)
    assert result["healthy"] is True
    assert all(row["ok"] for row in result["checks"] if row["severity"] == "high")


def test_health_fails_closed_on_partial_liveness(tmp_path: Path):
    now = datetime.now(timezone.utc).timestamp()
    _seed(tmp_path, now, complete=False)
    result = build_health(tmp_path, now_epoch=now)
    assert result["healthy"] is False
    assert any(row["name"] == "liveness_complete" and not row["ok"] for row in result["checks"])


def test_pid_permission_error_means_process_exists(monkeypatch):
    def denied(_pid: int, _sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(os, "kill", denied)
    assert _pid_alive(12345) is True
