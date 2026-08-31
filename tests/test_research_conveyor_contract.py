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
        "contract_refs": ["contracts.json", "research_lab/a.py"],
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


def _phase_receipt(**changes):
    value = {
        "schema_id": "research_conveyor_phase_receipt_v1",
        "authority": AUTH,
        "hypothesis_id": "h1",
        "phase": "replay",
        "status": "PASS",
        "manifest_sha256": "1" * 64,
        "preregistration_sha256": "2" * 64,
        "adapter_argv_sha256": "3" * 64,
        "input_artifacts": [],
        "output_artifacts": [],
        "metrics": {},
        "live_or_broker_calls": False,
        "private_api_calls": False,
        "capital_or_promotion_authority": False,
    }
    value.update(changes)
    return value


def test_manifest_loads_and_freezes_deterministically(tmp_path: Path):
    path = _write_manifest(tmp_path, _manifest())
    manifest = load_manifest(tmp_path, path)
    first = freeze_hypothesis(tmp_path, manifest, "h1")
    second = freeze_hypothesis(tmp_path, manifest, "h1")
    assert first["preregistration_sha256"] == second["preregistration_sha256"]
    assert len(first["contract_hashes"]) == 2
    assert first["authority"] == AUTH


def test_manifest_internal_state_and_public_copies_cannot_change_frozen_content(tmp_path: Path):
    value = _manifest()
    path = _write_manifest(tmp_path, value)
    manifest = load_manifest(tmp_path, path)
    original_payload = manifest.payload
    original_sha256 = manifest.sha256
    original_freeze = freeze_hypothesis(tmp_path, manifest, "h1")

    value["hypotheses"][0]["preregistration"]["hypothesis"] = "source mutation"
    manifest.payload["hypotheses"][0]["preregistration"]["hypothesis"] = "payload mutation"
    manifest.hypotheses[0]["preregistration"]["hypothesis"] = "hypotheses mutation"
    with pytest.raises(TypeError):
        manifest._payload["hypotheses"][0]["preregistration"]["hypothesis"] = "internal mutation"

    assert manifest.payload == original_payload
    assert manifest.sha256 == original_sha256
    assert freeze_hypothesis(tmp_path, manifest, "h1") == original_freeze


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


def test_nested_unknown_fields_are_rejected(tmp_path: Path):
    for section, key in (("preregistration", "nested"), ("data_refs", "extra")):
        value = _manifest()
        if section == "preregistration":
            value["hypotheses"][0][section][key] = 1
        else:
            value["hypotheses"][0][section][0][key] = 1
        with pytest.raises(ContractError):
            load_manifest(tmp_path, _write_manifest(tmp_path, value))


@pytest.mark.parametrize("argv", [
    ["{python}", "-c", "pass"],
    ["{python}", "research_lab/missing.py"],
    ["{python}", "research_lab/../scripts/a.py"],
    ["{python}", str(Path.cwd() / "research_lab/a.py")],
])
def test_adapter_shape_and_paths_fail_closed(tmp_path: Path, argv):
    value = _manifest()
    value["hypotheses"][0]["adapters"]["replay"] = argv
    with pytest.raises(ContractError):
        load_manifest(tmp_path, _write_manifest(tmp_path, value))


def test_direct_adapter_symlink_fails_closed(tmp_path: Path):
    value = _manifest()
    _write_manifest(tmp_path, value)
    (tmp_path / "research_lab" / "linked.py").symlink_to(tmp_path / "research_lab" / "a.py")
    value["hypotheses"][0]["adapters"]["replay"][1] = "research_lab/linked.py"
    with pytest.raises(ContractError):
        load_manifest(tmp_path, _write_manifest(tmp_path, value))


def test_adapter_parent_directory_symlink_fails_closed(tmp_path: Path):
    value = _manifest()
    _write_manifest(tmp_path, value)
    real_parent = tmp_path / "research_lab" / "real_parent"
    real_parent.mkdir()
    (real_parent / "adapter.py").write_text("pass\n")
    (tmp_path / "research_lab" / "linked_parent").symlink_to(real_parent, target_is_directory=True)
    value["hypotheses"][0]["adapters"]["replay"][1] = "research_lab/linked_parent/adapter.py"

    with pytest.raises(ContractError):
        load_manifest(tmp_path, _write_manifest(tmp_path, value))


def test_receipt_unknown_and_missing_fields_fail_closed(tmp_path: Path):
    path = tmp_path / "r.json"
    with pytest.raises(ContractError):
        write_self_hashed_json(path, {"schema_id": "x", "unknown": 1})
    write_self_hashed_json(path, {"schema_id": "x", "value": 1})
    data = json.loads(path.read_text()); data["unknown"] = 2; path.write_text(json.dumps(data))
    with pytest.raises(ContractError):
        read_verified_receipt(path, expected_schema="x")


def test_phase_receipt_missing_required_field_fails_closed(tmp_path: Path):
    path = tmp_path / "phase-receipt.json"
    payload = _phase_receipt()
    payload.pop("status")
    write_self_hashed_json(path, payload)

    with pytest.raises(ContractError):
        read_verified_receipt(path, expected_schema="research_conveyor_phase_receipt_v1")


def test_data_drift_min_count_and_root_mismatch_fail_closed(tmp_path: Path):
    value = _manifest()
    manifest_path = _write_manifest(tmp_path, value)
    manifest = load_manifest(tmp_path, manifest_path)
    (tmp_path / "data" / "two.csv").write_text("y\n")
    with pytest.raises(ContractError):
        freeze_hypothesis(tmp_path, manifest, "h1")
    with pytest.raises(ContractError):
        freeze_hypothesis(tmp_path / "other", manifest, "h1")


def test_standalone_data_file_content_drift_fails_closed(tmp_path: Path):
    value = _manifest()
    manifest_path = _write_manifest(tmp_path, value)
    standalone = tmp_path / "standalone.csv"
    standalone.write_text("stable\n")
    value["hypotheses"][0]["data_refs"] = [{
        "path": "standalone.csv",
        "min_count": 1,
        "sha256": hashlib.sha256(b"stable\n").hexdigest(),
    }]
    manifest_path.write_text(json.dumps(value))
    manifest = load_manifest(tmp_path, manifest_path)

    standalone.write_text("drifted\n")
    with pytest.raises(ContractError):
        freeze_hypothesis(tmp_path, manifest, "h1")


def test_directory_data_ref_with_insufficient_min_count_fails_closed(tmp_path: Path):
    value = _manifest()
    value["hypotheses"][0]["data_refs"][0]["min_count"] = 2

    with pytest.raises(ContractError):
        load_manifest(tmp_path, _write_manifest(tmp_path, value))


def test_symlinked_data_member_is_rejected(tmp_path: Path):
    value = _manifest()
    manifest_path = _write_manifest(tmp_path, value)
    (tmp_path / "data" / "link.csv").symlink_to(tmp_path / "data" / "one.csv")
    with pytest.raises(ContractError):
        load_manifest(tmp_path, manifest_path)
