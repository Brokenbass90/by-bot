import argparse
import json
from pathlib import Path

import pytest

from scripts.record_operational_incident import _record, upsert


def _args(**overrides):
    values = {
        "external_id": "incident-1",
        "rule": "broker_mismatch",
        "severity": "high",
        "status": "confirmed",
        "not_current": False,
        "where": "ADAUSDT",
        "what": "quantity mismatch",
        "why": "legacy path",
        "how_to_verify": "reconcile fills",
        "how_to_falsify": "show authorized event",
        "occurred_at_utc": "2026-08-08T00:00:00Z",
        "evidence": "redacted receipt",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_upsert_is_idempotent_by_external_id(tmp_path: Path) -> None:
    path = tmp_path / "incidents.jsonl"
    first = _record(_args(what="first"))
    second = _record(_args(what="corrected"))

    upsert(path, first)
    upsert(path, second)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["what"] == "corrected"


def test_incident_rejects_secret_like_content() -> None:
    with pytest.raises(ValueError, match="secret"):
        _record(_args(evidence="api_key=must-not-be-recorded"))
