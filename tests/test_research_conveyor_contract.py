import json
import hashlib
from pathlib import Path

import pytest

from research_lab.research_conveyor_contract import (
    ContractError,
    freeze_hypothesis,
    load_manifest,
    read_verified_receipt,
    write_self_hashed_json,
)


AUTH = "research_only_no_live_risk_order_promotion_or_private_api_authority"


def _hypothesis(state="RUNNABLE", **extra):
    value = {
        "id": "h1",
        "title": "Fixture",
        "market": "crypto",
        "family": "test",
        "priority": 1,
        "state": state,
        "reopen_when": "fixture data exists",
        "contract_refs": ["contracts.json"],
        "data_refs": [{"path": "data", "min_count": 1, "sha256": ""}],
        "preregistration": {
            "hypothesis": "fixture",
            "universe": "fixture",
            "signal": "fixture",
            "entry": "fixture",
            "exit": "fixture",
            "costs": "fixture",
            "control": "fixture",
            "stress": "fixture",
            "concentration": "fixture",
            "death_criteria": "fixture",
            "acceptance_gate": "fixture",
        },
    }
    if state == "RUNNABLE":
        value["adapters"] = {
            phase: ["{python}", "research_lab/a.py", "--run-dir", "{run_dir}", "--hypothesis-id", "{hypothesis_id}", "--phase", "{phase}", "--receipt", "{receipt}"]
            for phase in ("prereg", "replay", "random_control", "stress")
        }
    value.update(extra)
    return value


def _manifest(hypotheses=None):
    return {
        "schema_id": "research_conveyor_manifest_v1",
        "authority": AUTH,
        "enabled": True,
        "max_jobs_per_run": 10,
        "max_runtime_seconds": 60,
        "min_free_bytes": 1,
        "allowed_script_roots": ["research_lab", "scripts"],
        "hypotheses": hypotheses or [_hypothesis()],
    }


def _write_manifest(tmp_path, value):
    (tmp_path / "contracts.json").write_text("{}\n")
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "one.csv").write_text("x\n")
    data_hash = hashlib.sha256(json.dumps([{"path": "one.csv", "sha256": hashlib.sha256(b"x\n").hexdigest()}], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    value["hypotheses"][0]["data_refs"][0]["sha256"] = data_hash
    (tmp_path / "research_lab").mkdir(exist_ok=True)
    (tmp_path / "research_lab" / "a.py").write_text("pass\n")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    return path


def test_manifest_loads_and_freezes_deterministically(tmp_path: Path):
    path = _write_manifest(tmp_path, _manifest())
    manifest = load_manifest(tmp_path, path)
    first = freeze_hypothesis(tmp_path, manifest, "h1")
    second = freeze_hypothesis(tmp_path, manifest, "h1")
    assert first["preregistration_sha256"] == second["preregistration_sha256"]
    assert len(first["contract_hashes"]) == 1
    assert first["authority"] == AUTH


def test_manifest_unknown_field_fails_closed(tmp_path: Path):
    value = _manifest()
    value["unknown"] = 1
    with pytest.raises(ContractError):
        load_manifest(tmp_path, _write_manifest(tmp_path, value))


def test_manifest_duplicate_ids_fail_closed(tmp_path: Path):
    value = _manifest([_hypothesis(), _hypothesis()])
    with pytest.raises(ContractError):
        load_manifest(tmp_path, _write_manifest(tmp_path, value))


def test_path_escape_glob_and_missing_ref_fail(tmp_path: Path):
    for change in (
        {"contract_refs": ["../outside.json"]},
        {"contract_refs": ["*.json"]},
        {"contract_refs": ["missing.json"]},
    ):
        h = _hypothesis(**change)
        with pytest.raises(ContractError):
            load_manifest(tmp_path, _write_manifest(tmp_path, _manifest([h])))


def test_blocked_card_may_omit_adapters_but_runnable_may_not(tmp_path: Path):
    blocked = _hypothesis("BLOCKED_DATA_OR_PARITY")
    load_manifest(tmp_path, _write_manifest(tmp_path, _manifest([blocked])))
    runnable = _hypothesis()
    runnable["adapters"].pop("stress")
    with pytest.raises(ContractError):
        load_manifest(tmp_path, _write_manifest(tmp_path, _manifest([runnable])))


def test_self_hash_is_atomic_and_tampering_is_rejected(tmp_path: Path):
    path = tmp_path / "receipt.json"
    written = write_self_hashed_json(path, {"schema_id": "x", "value": 3})
    assert written["receipt_sha256"]
    assert read_verified_receipt(path, expected_schema="x")["value"] == 3
    path.write_text(path.read_text().replace("3", "4"))
    with pytest.raises(ContractError):
        read_verified_receipt(path, expected_schema="x")
