import json
from pathlib import Path

from research_lab.audit_registry import (
    collect_continuous,
    collect_technology_inventory,
    finding_id,
    merge_registry,
)


def test_finding_id_is_stable_and_source_sensitive():
    first = finding_id("static", "E1", "a.py:1", "mixed units")
    assert first == finding_id("static", "E1", "a.py:1", "mixed units")
    assert first != finding_id("model", "E1", "a.py:1", "mixed units")


def test_merge_preserves_manual_status_and_marks_missing_not_seen():
    now1 = "2026-08-08T00:00:00+00:00"
    now2 = "2026-08-08T06:00:00+00:00"
    row = {
        "id": "abc",
        "source": "static",
        "rule": "E1",
        "severity": "high",
        "status": "open",
        "current": True,
        "where": "a.py:1",
        "what": "mixed units",
        "why": "bad expiry",
        "how_to_verify": "trace",
        "how_to_falsify": "show conversion",
    }
    first = merge_registry([row], now=now1)
    first["findings"][0]["status"] = "confirmed"
    first["findings"][0]["resolution_note"] = "reproduced"
    second = merge_registry([row], first, now=now2)
    assert second["findings"][0]["status"] == "confirmed"
    assert second["findings"][0]["resolution_note"] == "reproduced"
    assert second["findings"][0]["occurrences"] == 2

    gone = merge_registry([], second, now="2026-08-08T12:00:00+00:00")
    assert gone["findings"][0]["current"] is False
    assert gone["findings"][0]["status"] == "confirmed"


def test_info_inventory_is_counted_separately_from_actionable_defects():
    inventory = {
        "id": "inventory",
        "source": "technology_inventory",
        "rule": "tested_static_runtime_not_observed",
        "severity": "info",
        "status": "needs_triage",
        "current": True,
        "where": "bot/helper.py",
        "what": "not statically observed",
        "why": "inventory",
        "how_to_verify": "trace",
        "how_to_falsify": "show runtime path",
    }
    defect = dict(inventory, id="defect", severity="high", status="open")
    payload = merge_registry([inventory, defect], now="2026-08-08T00:00:00+00:00")
    assert payload["summary"]["actionable"] == 1
    assert payload["summary"]["inventory_needs_triage"] == 1


def test_technology_inventory_is_triage_not_defect(tmp_path: Path):
    path = tmp_path / "runtime" / "ai_context" / "technology_registry.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "modules": [{
            "module": "bot/orphan.py",
            "inventory_status": "tested_static_runtime_not_observed",
            "test_reference_files": ["tests/test_orphan.py"],
            "purpose": "Research helper",
        }]
    }), encoding="utf-8")
    rows = collect_technology_inventory(tmp_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "needs_triage"
    assert rows[0]["severity"] == "info"
    assert "static" in rows[0]["why"]


def test_noisy_continuous_rule_is_triage_not_actionable(tmp_path: Path):
    path = tmp_path / "runtime" / "audit_ledger.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "noisy_rules": ["E2"],
        "findings": {
            "old-id": {
                "rule": "E2",
                "where": "bot/example.py:1",
                "what": "possible timestamp mismatch",
                "how_to_refute": "trace units",
                "status": "new",
            }
        },
    }), encoding="utf-8")
    rows = collect_continuous(tmp_path)
    assert rows[0]["status"] == "needs_triage"
    assert rows[0]["severity"] == "info"
