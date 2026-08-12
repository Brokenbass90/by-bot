import json
from pathlib import Path

from research_lab.audit_registry import (
    collect_continuous,
    collect_operational_incidents,
    collect_technology_inventory,
    finding_id,
    merge_registry,
    validate_lifecycle,
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


def test_audit_lifecycle_requires_confirmation_evidence_and_resolution_note():
    base = {
        "id": "abc",
        "status": "confirmed",
        "confirmation_evidence": "",
        "resolution_note": "",
    }
    assert validate_lifecycle({"findings": [base]}) == ["abc:confirmed_without_evidence"]
    confirmed = dict(base, confirmation_evidence="reproduced with trace")
    assert validate_lifecycle({"findings": [confirmed]}) == []
    resolved = dict(confirmed, status="resolved", resolution_note="")
    assert validate_lifecycle({"findings": [resolved]}) == ["abc:resolved_without_resolution_note"]
    assert validate_lifecycle({"findings": [dict(resolved, resolution_note="commit + tests")]}) == []


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


def test_operational_incident_enters_registry_as_confirmed_evidence(tmp_path: Path):
    path = tmp_path / "runtime" / "project_audit" / "operational_incidents.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "external_id": "ATT1_ADA_HIDDEN_DCA_20260808",
        "rule": "broker_qty_exceeds_runner_qty",
        "severity": "critical",
        "status": "confirmed",
        "where": "ADAUSDT broker lifecycle",
        "what": "broker qty rose from 180 to 270 outside the ATT1 entry event",
        "why": "legacy pump-fade DCA shared the symbol",
        "how_to_verify": "reconcile broker executions with entry and runner events",
        "how_to_falsify": "show an ATT1-authorized add event for the extra 90 ADA",
        "occurred_at_utc": "2026-08-08T00:00:00+00:00",
    }) + "\n", encoding="utf-8")

    rows = collect_operational_incidents(tmp_path)

    assert len(rows) == 1
    assert rows[0]["source"] == "operational_reconciliation"
    assert rows[0]["status"] == "confirmed"
    assert rows[0]["severity"] == "critical"
    assert rows[0]["external_id"] == "ATT1_ADA_HIDDEN_DCA_20260808"
