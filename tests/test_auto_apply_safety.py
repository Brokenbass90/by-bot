import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "auto_apply_research_winner.py"
SPEC = importlib.util.spec_from_file_location("auto_apply_safety_target", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _receipt(tmp_path, **updates):
    payload = {
        "authority": "research_promotion_v1",
        "operator_identity": "operator:test",
        "prereg_hash": "sha256:prereg",
        "holdout_status": "PASS",
        "adapter_parity_status": "PASS",
        "zero_risk_shadow_status": "PASS",
        "clean_incident_count": 0,
        "sha_linkage": "git:abc123",
    }
    payload.update(updates)
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_filter_is_exact_whitelist_only():
    result = MODULE._filter_safe_params({"ATT1_RR": "1.5", "ATT1_NEW_UNREVIEWED": "1"})
    assert result == {"ATT1_RR": "1.5"}


def test_evidence_receipt_requires_all_independent_gates(tmp_path):
    receipt = _receipt(tmp_path)
    assert MODULE._validate_evidence_receipt(str(receipt))["clean_incident_count"] == 0

    bad = _receipt(tmp_path, adapter_parity_status="FAIL")
    with pytest.raises(RuntimeError, match="adapter_parity_status must be PASS"):
        MODULE._validate_evidence_receipt(str(bad))


def test_evidence_receipt_rejects_incidents_and_missing_file(tmp_path):
    bad = _receipt(tmp_path, clean_incident_count=1)
    with pytest.raises(RuntimeError, match="clean_incident_count must be 0"):
        MODULE._validate_evidence_receipt(str(bad))
    with pytest.raises(RuntimeError, match="cannot read evidence receipt"):
        MODULE._validate_evidence_receipt(str(tmp_path / "missing.json"))


def test_cron_is_explicitly_dry_run():
    text = (ROOT / "scripts" / "setup_server_crons.sh").read_text(encoding="utf-8")
    assert "scripts/auto_apply_research_winner.py --dry-run" in text
