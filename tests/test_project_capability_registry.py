from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_project_capability_registry import validate_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "project_capability_registry_v1.json"


def _payload() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_canonical_capability_registry_is_valid() -> None:
    report = validate_registry(_payload(), root=ROOT)
    assert report["ok"] is True, report["errors"]
    assert report["component_count"] >= 20
    assert report["authority_counts"]["tiny_money"] == 1
    assert report["authority_counts"]["protect_existing_only"] == 1


def test_registry_rejects_duplicate_component_id() -> None:
    payload = _payload()
    payload["components"].append(copy.deepcopy(payload["components"][0]))
    report = validate_registry(payload, root=ROOT)
    assert report["ok"] is False
    assert any("duplicate component_id" in error for error in report["errors"])


def test_registry_rejects_live_stage_without_explicit_authority() -> None:
    payload = _payload()
    payload["components"][0]["execution_authority"] = "none"
    report = validate_registry(payload, root=ROOT)
    assert report["ok"] is False
    assert any("live stage requires" in error for error in report["errors"])
