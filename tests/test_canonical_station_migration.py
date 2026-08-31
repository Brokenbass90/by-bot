from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.canonical_station_migration as migration
from research_lab.canonical_station import AUTHORITY, MigrationError, canonical_screen_name
from scripts.canonical_station_migration import (
    _inventory_identity_is_safe,
    _read_json_receipt,
    build_migration_parser,
    process_receipt_from_mapping,
    inventory_legacy_processes,
    run_migration,
    stop_legacy_session,
)


EPOCH = "epoch_fixture_20260831"
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
ROOT = Path(__file__).resolve().parents[1]


def _hash(payload: dict, field: str) -> dict:
    result = dict(payload)
    result[field] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return result


def _authority() -> dict:
    return {
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "public_data_read_authority": True,
    }


def _manifest() -> dict:
    return {
        "schema_id": "canonical_research_station_v1",
        **_authority(),
        "canonical_runtime_root": "runtime/local_research_station",
        "jobs": [
            {
                "name": "fixture",
                "process_kind": "market_snapshot_loop",
                "screen_session": "canonical_fixture",
                "legacy_session_markers": ["old_fixture"],
                "legacy_command_markers": ["fixture_loop.py"],
                "launcher": ["scripts/run_xsec_shadow_loop.sh"],
                "migration_mode": "canonical",
                "max_age_seconds": 60,
                "runtime_requirements": [],
                "evidence_paths": ["runtime/fixture/latest.json"],
                "canonical_evidence_files": ["latest.json"],
                "source_paths": ["scripts/run_xsec_shadow_loop.sh"],
                "config_paths": ["configs/preregistered/xsec_v4_family_landscape_20260728.json"],
                "input_paths": ["research_lab/data/bybit_instruments_linear.json"],
            }
        ],
    }


def _identity(seed: str = "a") -> dict:
    identity_paths = (
        "scripts/run_xsec_shadow_loop.sh",
        "configs/preregistered/xsec_v4_family_landscape_20260728.json",
        "research_lab/data/bybit_instruments_linear.json",
    )
    identity = {
        "source_hashes": {
            identity_paths[0]: hashlib.sha256(
                (ROOT / identity_paths[0]).read_bytes()
            ).hexdigest()
        },
        "config_hashes": {
            identity_paths[1]: hashlib.sha256(
                (ROOT / identity_paths[1]).read_bytes()
            ).hexdigest()
        },
        "input_hashes": {
            identity_paths[2]: hashlib.sha256(
                (ROOT / identity_paths[2]).read_bytes()
            ).hexdigest()
        },
        "content_hash": "d" * 64,
        "decision_id": "decision_fixture",
    }
    identity["fingerprint"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return identity


def _row(
    *,
    status: str = "CONFIRMED",
    stop_allowed: bool = False,
    job_name: str = "fixture",
    screen_name: str = "old_fixture",
) -> dict:
    evidence_bytes = (
        ROOT / "configs/preregistered/xsec_v4_family_landscape_20260728.json"
    ).read_bytes()
    evidence_source = ROOT / "runtime/fixture/latest.json"
    evidence_source.parent.mkdir(parents=True, exist_ok=True)
    evidence_source.write_bytes(evidence_bytes)
    return {
        "job_name": job_name,
        "screen_name": screen_name,
        "screen_pid": 1111,
        "pid": 1234,
        "cwd": str(ROOT),
        "command": "python fixture_loop.py",
        "process_kind": "market_snapshot_loop",
        "status": status,
        "stop_allowed": stop_allowed,
        "eligible_for_parity": status == "CONFIRMED",
        "identity": _identity(),
        "counters": {},
        "timestamps": {
            "closed_source_ts": "2026-08-31T00:00:00Z",
            "observed_at_utc": "2026-08-31T00:00:05Z",
        },
        "evidence": [
            {
                "path": "runtime/fixture/latest.json",
                "resolved_path": str(evidence_source),
                "state": "PRESENT",
                "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                "size_bytes": len(evidence_bytes),
            }
        ],
        "evidence_paths": ["runtime/fixture/latest.json"],
        "evidence_epoch": "legacy_fixture",
    }


def _inventory(*rows: dict, fresh: bool = True) -> dict:
    payload = {
        "schema_id": "canonical_station_legacy_inventory_v1",
        **_authority(),
        "fresh": fresh,
        "observed_at_utc": NOW,
        "processes": list(rows) if rows else [],
    }
    return _hash(payload, "inventory_sha256")


def _launch(*, state: str = "STARTED", dry_run: bool = False) -> dict:
    job_state = "DRY_RUN" if dry_run else state
    runtime_dir = ROOT / f"runtime/local_research_station/epochs/{EPOCH}/fixture"
    source_path = ROOT / "scripts/run_xsec_shadow_loop.sh"
    identity_paths = [
        "scripts/run_xsec_shadow_loop.sh",
        "configs/preregistered/xsec_v4_family_landscape_20260728.json",
        "research_lab/data/bybit_instruments_linear.json",
    ]
    source_hashes = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in identity_paths
    }
    argv = [str(source_path), "--runtime-dir", str(runtime_dir)]
    evidence_paths = [str(runtime_dir / "latest.json")]
    launch_identity = {
        "job_name": "fixture",
        "process_kind": "market_snapshot_loop",
        "argv": argv,
        "evidence_epoch": EPOCH,
        "evidence_paths": evidence_paths,
        "source_hashes": source_hashes,
        "runtime_requirements": [],
    }
    launch_fingerprint = hashlib.sha256(
        json.dumps(launch_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload = {
        "schema_id": "canonical_station_launch_v1",
        **_authority(),
        "observed_at_utc": NOW,
        "dry_run": dry_run,
        "orchestrator_hashes": {
            "research_lab/canonical_station.py": hashlib.sha256(
                (ROOT / "research_lab/canonical_station.py").read_bytes()
            ).hexdigest(),
            "scripts/canonical_station_migration.py": hashlib.sha256(
                (ROOT / "scripts/canonical_station_migration.py").read_bytes()
            ).hexdigest(),
        },
        "jobs": [
            {
                "job_name": "fixture",
                "screen_session": canonical_screen_name("canonical_fixture", EPOCH),
                "runtime_dir": str(runtime_dir),
                "argv": argv,
                "cwd": str(ROOT),
                "evidence_epoch": EPOCH,
                "evidence_paths": evidence_paths,
                "source_hashes": source_hashes,
                "identity_fingerprint": launch_fingerprint,
                "runtime_requirements": [],
                "runtime_missing": [],
                "state": job_state,
                "returncode": 0 if job_state == "STARTED" else None,
                "pid": 4321 if job_state == "STARTED" else None,
                "orders_sent": False,
                "private_api_calls": False,
                "live_write_authority": False,
                "public_data_read_authority": True,
            }
        ],
    }
    return _hash(payload, "launch_sha256")


def _parity(
    launch: dict,
    *,
    state: str = "PASS",
    stop_allowed: bool = True,
    authorized_screens: list[str] | None = None,
) -> dict:
    is_pass = state == "PASS" and stop_allowed
    compared_fields = [
        "config_hash",
        "content_hash",
        "decision_id",
        "evidence_hashes",
        "input_hash",
        "source_hash",
    ]
    legacy_row = _row()
    legacy_fingerprint = legacy_row["identity"]["fingerprint"]
    canonical_fingerprint = launch["jobs"][0]["identity_fingerprint"]
    heartbeat_payload = {
        "job_name": "fixture",
        "canonical_screen_session": canonical_screen_name("canonical_fixture", EPOCH),
        "canonical_pid": launch["jobs"][0]["pid"],
        "evidence_epoch": EPOCH,
        "state": "PASS" if is_pass else state,
        "observed_at_utc": NOW,
    }
    canonical_evidence_hashes: dict[str, str] = {}
    canonical_evidence_bytes = (
        ROOT / "configs/preregistered/xsec_v4_family_landscape_20260728.json"
    ).read_bytes()
    for index, raw_path in enumerate(launch["jobs"][0]["evidence_paths"]):
        path = Path(raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_evidence_bytes)
        canonical_evidence_hashes[str(index)] = hashlib.sha256(
            canonical_evidence_bytes
        ).hexdigest()
    receipt_identity = {
        key: value for key, value in legacy_row["identity"].items() if key != "fingerprint"
    }
    receipt_identity["evidence_hashes"] = canonical_evidence_hashes
    legacy_receipt = {
        "job_name": "fixture",
        "screen_name": legacy_row["screen_name"],
        "pid": legacy_row["pid"],
        "cwd": legacy_row["cwd"],
        "command": legacy_row["command"],
        "process_kind": "market_snapshot_loop",
        "status": "CONFIRMED",
        "stop_allowed": True,
        "eligible_for_parity": True,
        "identity": receipt_identity,
        "counters": {},
        "timestamps": {"closed_source_ts": "2026-08-31T00:00:00Z"},
        "evidence_paths": legacy_row["evidence_paths"],
        "evidence_epoch": legacy_row["evidence_epoch"],
        "authority": _authority(),
    }
    canonical_receipt = {
        "job_name": "fixture",
        "screen_name": launch["jobs"][0]["screen_session"],
        "pid": launch["jobs"][0]["pid"],
        "cwd": launch["jobs"][0]["cwd"],
        "command": " ".join(launch["jobs"][0]["argv"]),
        "process_kind": "market_snapshot_loop",
        "status": "CONFIRMED",
        "stop_allowed": True,
        "eligible_for_parity": True,
        "identity": receipt_identity,
        "counters": {},
        "timestamps": {"closed_source_ts": "2026-08-31T00:00:00Z"},
        "evidence_paths": launch["jobs"][0]["evidence_paths"],
        "evidence_epoch": launch["jobs"][0]["evidence_epoch"],
        "authority": _authority(),
    }
    evidence_payload = {
        "job_name": "fixture",
        "process_kind": "market_snapshot_loop",
        "legacy_identity_fingerprint": legacy_fingerprint,
        "canonical_identity_fingerprint": canonical_fingerprint,
        "compared_fields": compared_fields,
        "comparator_reason": "identity_and_economics_match",
        "legacy_receipt": legacy_receipt,
        "canonical_receipt": canonical_receipt,
        "closed_source_ts": "2026-08-31T00:00:00Z",
        "state": "PASS" if is_pass else state,
        "observed_at_utc": NOW,
    }
    payload = {
        "schema_id": "canonical_station_parity_v1",
        **_authority(),
        "state": state,
        "stop_allowed": stop_allowed,
        "reason": "fixture",
        "launch_sha256": launch["launch_sha256"],
        "inventory_sha256": _inventory(_row())["inventory_sha256"],
        "observed_at_utc": NOW,
        "fresh": True,
        "heartbeat_fresh": True,
        "evidence_fresh": True,
        "authorized_screens": (
            ["old_fixture"] if authorized_screens is None and is_pass else authorized_screens or []
        ),
        "jobs": [
            {
                "job_name": "fixture",
                "canonical_screen_session": canonical_screen_name("canonical_fixture", EPOCH),
                "state": "PASS" if is_pass else state,
                "stop_allowed": is_pass,
                "fresh": True,
                "heartbeat_fresh": True,
                "evidence_fresh": True,
                "completion_valid": True,
                "observed_at_utc": NOW,
                "process_kind": "market_snapshot_loop",
                "comparator": "compare_market_snapshot_receipts",
                "comparator_state": "PASS" if is_pass else state,
                "compared_fields": compared_fields,
                "legacy_identity_fingerprint": legacy_fingerprint,
                "canonical_identity_fingerprint": canonical_fingerprint,
                "heartbeat": {
                    "state": "PASS" if is_pass else state,
                    "fresh": True,
                    "observed_at_utc": NOW,
                    "payload": heartbeat_payload,
                    "sha256": hashlib.sha256(
                        json.dumps(heartbeat_payload, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                },
                "evidence": {
                    "state": "PASS" if is_pass else state,
                    "fresh": True,
                    "observed_at_utc": NOW,
                    "payload": evidence_payload,
                    "sha256": hashlib.sha256(
                        json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                },
            }
        ],
    }
    return _hash(payload, "parity_sha256")


def _authorization(inventory: dict, launch: dict, parity: dict) -> dict:
    payload = {
        "schema_id": "canonical_station_migration_authorization_v1",
        **_authority(),
        "state": "PASS",
        "manifest_sha256": hashlib.sha256(
            json.dumps(_manifest(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "inventory_sha256": inventory["inventory_sha256"],
        "launch_sha256": launch["launch_sha256"],
        "parity_sha256": parity["parity_sha256"],
        "authorized_screens": ["old_fixture"],
        "authorized_jobs": ["fixture"],
        "observed_at_utc": NOW,
    }
    return _hash(payload, "authorization_sha256")


def _stopper(stopped: list[str]):
    def stop(name: str, authorization: dict) -> dict:
        assert authorization["state"] == "PASS"
        stopped.append(name)
        return {
            "screen_name": name,
            "state": "STOPPED",
            "command": ["screen", "-S", name, "-X", "quit"],
            "returncode": 0,
            "post_stop_sessions": [],
            "observed_at_utc": NOW,
        }

    return stop


def test_unknown_identity_never_stops_legacy(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch()
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row(status="NOT_CONFIRMED", stop_allowed=False)),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch, state="NOT_CONFIRMED", stop_allowed=False),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "NOT_CONFIRMED"
    assert stopped == []


def test_pass_writes_all_authorization_receipts_before_exact_stop(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch()

    def stop(name: str, authorization: dict) -> dict:
        assert authorization["state"] == "PASS"
        for filename in (
            "legacy_inventory.json",
            "launch_receipt.json",
            "parity_receipt.json",
            "migration_authorization.json",
        ):
            assert (tmp_path / filename).is_file()
        stopped.append(name)
        return {
            "screen_name": name,
            "state": "STOPPED",
            "command": ["screen", "-S", name, "-X", "quit"],
            "returncode": 0,
            "post_stop_sessions": [],
            "observed_at_utc": NOW,
        }

    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=stop,
        output_dir=tmp_path,
    )
    assert result["state"] == "PASS"
    assert stopped == ["old_fixture"]
    assert result["stop_receipts"] == [
        {
            "screen_name": "old_fixture",
            "state": "STOPPED",
            "command": ["screen", "-S", "old_fixture", "-X", "quit"],
            "returncode": 0,
            "post_stop_sessions": [],
            "observed_at_utc": NOW,
        }
    ]
    assert (tmp_path / "migration_receipt.json").is_file()
    authorization = json.loads((tmp_path / "migration_authorization.json").read_text())
    assert authorization["manifest_sha256"]
    assert authorization["inventory_sha256"] == _inventory(_row())["inventory_sha256"]
    assert authorization["launch_sha256"] == launch["launch_sha256"]
    assert authorization["parity_sha256"] == _parity(launch)["parity_sha256"]
    assert authorization["authorized_screens"] == ["old_fixture"]


def test_parity_failure_is_fail_closed_and_never_stops(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch()
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch, state="FAIL_CLOSED", stop_allowed=False),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_failed_launch_cannot_be_overridden_by_green_parity(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch(state="FAIL_CLOSED")
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_dry_run_launch_is_not_confirmed_and_never_stops(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch(dry_run=True)
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "NOT_CONFIRMED"
    assert stopped == []


def test_launch_missing_explicit_dry_run_flag_never_stops(tmp_path: Path) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch.pop("dry_run")
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_external_launch_without_hash_fails_closed(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch()
    launch.pop("launch_sha256")
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: {},
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert "hash" in result["reason"]
    assert stopped == []


@pytest.mark.parametrize("receipt_name", ["inventory", "parity"])
def test_missing_external_hash_never_stops(
    tmp_path: Path, receipt_name: str
) -> None:
    stopped: list[str] = []
    inventory = _inventory(_row())
    launch = _launch()
    parity = _parity(launch)
    if receipt_name == "inventory":
        inventory.pop("inventory_sha256")
    else:
        parity.pop("parity_sha256")
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=inventory,
        launch_fn=lambda: launch,
        verify_fn=lambda: parity,
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_bool_pid_cannot_authorize_launch(tmp_path: Path) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch["jobs"][0]["pid"] = True
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_money_authority_drift_never_stops(tmp_path: Path) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch["money_authority"] = True
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_unknown_execution_capability_never_stops(tmp_path: Path) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch["execute_orders"] = True
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


@pytest.mark.parametrize("claim", [True, 1, "yes"])
def test_unknown_orders_allowed_capability_never_stops(
    tmp_path: Path, claim: object
) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch["orders_allowed"] = claim
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


@pytest.mark.parametrize(
    "field", ["wallet_access", "execution_capability", "can_submit", "permissions"]
)
def test_any_unknown_launch_field_is_fail_closed(
    tmp_path: Path, field: str
) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch[field] = 1
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_launch_job_cannot_hide_unknown_orders_allowed_capability(tmp_path: Path) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch["jobs"][0]["orders_allowed"] = 1
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_nested_authority_cannot_hide_top_level_money_authority(tmp_path: Path) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch["authority"] = _authority()
    launch["money_authority"] = True
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_launch_must_match_exact_manifest_identity(tmp_path: Path) -> None:
    launch = _launch()
    launch.pop("launch_sha256")
    launch["jobs"][0]["argv"] = ["/evil/runner", "--runtime-dir", "/evil/runtime"]
    launch["jobs"][0]["runtime_dir"] = "/evil/runtime"
    launch["jobs"][0]["evidence_paths"] = ["/evil/evidence.json"]
    launch["jobs"][0]["source_hashes"] = {}
    launch["jobs"][0]["identity_fingerprint"] = "9" * 64
    launch = _hash(launch, "launch_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_stale_per_job_parity_proof_never_stops(tmp_path: Path) -> None:
    launch = _launch()
    parity = _parity(launch)
    parity.pop("parity_sha256")
    parity["jobs"][0]["heartbeat"]["observed_at_utc"] = "2020-01-01T00:00:00Z"
    parity = _hash(parity, "parity_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: parity,
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_rehashed_fabricated_comparator_input_never_stops(tmp_path: Path) -> None:
    launch = _launch()
    parity = _parity(launch)
    parity.pop("parity_sha256")
    proof = parity["jobs"][0]["evidence"]
    proof["payload"]["canonical_receipt"]["identity"]["content_hash"] = "e" * 64
    proof["sha256"] = hashlib.sha256(
        json.dumps(proof["payload"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    parity = _hash(parity, "parity_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: parity,
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_comparator_input_cannot_hide_unknown_money_capability(tmp_path: Path) -> None:
    launch = _launch()
    parity = _parity(launch)
    parity.pop("parity_sha256")
    proof = parity["jobs"][0]["evidence"]
    proof["payload"]["canonical_receipt"]["orders_allowed"] = True
    proof["sha256"] = hashlib.sha256(
        json.dumps(proof["payload"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    parity = _hash(parity, "parity_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: parity,
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_rehashed_heartbeat_for_another_process_never_stops(tmp_path: Path) -> None:
    launch = _launch()
    parity = _parity(launch)
    parity.pop("parity_sha256")
    proof = parity["jobs"][0]["heartbeat"]
    proof["payload"]["canonical_pid"] = 999_999
    proof["sha256"] = hashlib.sha256(
        json.dumps(proof["payload"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    parity = _hash(parity, "parity_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: parity,
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_heartbeat_payload_cannot_hide_unknown_order_capability(tmp_path: Path) -> None:
    launch = _launch()
    parity = _parity(launch)
    parity.pop("parity_sha256")
    proof = parity["jobs"][0]["heartbeat"]
    proof["payload"]["orders_allowed"] = True
    proof["sha256"] = hashlib.sha256(
        json.dumps(proof["payload"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    parity = _hash(parity, "parity_sha256")
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: parity,
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_comparator_is_bound_to_current_canonical_evidence_file(tmp_path: Path) -> None:
    launch = _launch()
    parity = _parity(launch)
    Path(launch["jobs"][0]["evidence_paths"][0]).write_text(
        '{"tampered":true}\n', encoding="utf-8"
    )
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: parity,
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_incomplete_stop_receipt_is_terminal_fail_closed(tmp_path: Path) -> None:
    launch = _launch()
    called: list[str] = []

    def fake_stop(name: str, _authorization: dict) -> dict:
        called.append(name)
        return {"screen_name": name, "state": "STOPPED"}

    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=fake_stop,
        output_dir=tmp_path,
    )
    assert called == ["old_fixture"]
    assert result["state"] == "FAIL_CLOSED"
    assert result["legacy_stop"] == []
    assert result["stop_receipts"] == []


def test_reused_output_directory_with_old_pass_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "migration_authorization.json").write_text(
        '{"state":"PASS"}\n', encoding="utf-8"
    )
    launch = _launch()
    with pytest.raises(MigrationError, match="new or empty"):
        run_migration(
            manifest=_manifest(),
            legacy_inventory=_inventory(_row()),
            launch_fn=lambda: launch,
            verify_fn=lambda: _parity(launch),
            stop_fn=_stopper([]),
            output_dir=tmp_path,
        )


def test_real_inventory_builder_is_confirmed_without_pregranting_stop(tmp_path: Path) -> None:
    evidence = tmp_path / "latest.json"
    evidence.write_text('{"decisions":1}\n', encoding="utf-8")
    file_roots = {
        relative: ROOT / relative
        for relative in (
            "scripts/run_xsec_shadow_loop.sh",
            "configs/preregistered/xsec_v4_family_landscape_20260728.json",
            "research_lab/data/bybit_instruments_linear.json",
        )
    }
    file_roots["runtime/fixture/latest.json"] = evidence
    inventory = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t1111.old_fixture\t(Detached)\n",
        ps_output="1111 1 python fixture_loop.py",
        cwd_by_pid={1111: str(ROOT)},
        file_roots=file_roots,
        now_utc=NOW,
    )
    row = inventory["processes"][0]
    assert row["status"] == "CONFIRMED"
    assert row["eligible_for_parity"] is True
    assert row["stop_allowed"] is False
    assert _inventory_identity_is_safe(inventory) is True


def test_stale_inventory_never_stops(tmp_path: Path) -> None:
    inventory = _inventory(_row())
    inventory.pop("inventory_sha256")
    inventory["observed_at_utc"] = "2026-08-01T00:00:00Z"
    inventory = _hash(inventory, "inventory_sha256")
    launch = _launch()
    stopped: list[str] = []
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=inventory,
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "NOT_CONFIRMED"
    assert stopped == []


def test_authorization_write_failure_happens_before_any_stop(tmp_path: Path, monkeypatch) -> None:
    stopped: list[str] = []
    launch = _launch()
    original = migration.atomic_write_json

    def fail_authorization(path: Path, payload: dict) -> None:
        if Path(path).name == "migration_authorization.json":
            raise OSError("disk full")
        original(path, payload)

    monkeypatch.setattr(migration, "atomic_write_json", fail_authorization)
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row()),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_empty_inventory_never_becomes_global_pass(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch()
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch, authorized_screens=[]),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] == "NOT_CONFIRMED"
    assert stopped == []


def test_unresolved_row_prevents_all_stops(tmp_path: Path) -> None:
    stopped: list[str] = []
    launch = _launch()
    result = run_migration(
        manifest=_manifest(),
        legacy_inventory=_inventory(_row(status="NOT_CONFIRMED", stop_allowed=False)),
        launch_fn=lambda: launch,
        verify_fn=lambda: _parity(launch),
        stop_fn=_stopper(stopped),
        output_dir=tmp_path,
    )
    assert result["state"] in {"NOT_CONFIRMED", "FAIL_CLOSED"}
    assert stopped == []


def test_process_adapter_refuses_pass_without_closed_source_timestamp() -> None:
    row = _row(stop_allowed=True)
    row["timestamps"] = {"observed_at_utc": "2026-08-31T00:00:05Z"}
    with pytest.raises(MigrationError, match="closed_source_timestamp"):
        process_receipt_from_mapping(row, authority=_authority())


def test_stop_requires_hash_bound_pass_receipts_and_exact_authorization() -> None:
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    authorization = _authorization(inventory, launch, parity)
    with pytest.raises(MigrationError, match="hash-bound"):
        stop_legacy_session(
            "old_fixture",
            {"processes": [_row()]},
            parity,
            launch,
            authorization,
            _manifest(),
            dry_run=True,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authorized_screens", "old_fixture"),
        ("authorized_screens", ["old_fixture", "unexpected_fixture"]),
        ("authorized_jobs", "fixture"),
        ("authorized_jobs", ["fixture", "unexpected_job"]),
    ],
)
def test_stop_rejects_malformed_or_broadened_authorization_scope(
    field: str, value: object
) -> None:
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    authorization = _authorization(inventory, launch, parity)
    authorization.pop("authorization_sha256")
    authorization[field] = value
    authorization = _hash(authorization, "authorization_sha256")
    with pytest.raises(MigrationError, match="durable migration authorization"):
        stop_legacy_session(
            "old_fixture",
            inventory,
            parity,
            launch,
            authorization,
            _manifest(),
            dry_run=True,
        )

    with pytest.raises(MigrationError, match="authorization"):
        stop_legacy_session(
            "old_fixture",
            inventory,
            parity,
            launch,
            {},
            _manifest(),
            dry_run=True,
        )

    with pytest.raises(MigrationError, match="authorized"):
        unauthorized_parity = _parity(launch, authorized_screens=["another_fixture"])
        stop_legacy_session(
            "old_fixture",
            inventory,
            unauthorized_parity,
            launch,
            _authorization(inventory, launch, unauthorized_parity),
            _manifest(),
            dry_run=True,
        )


def test_stop_dry_run_is_explicit_and_does_not_call_screen(monkeypatch) -> None:
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("dry-run must not invoke subprocess"),
    )
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    result = stop_legacy_session(
        "old_fixture",
        inventory,
        parity,
        launch,
        _authorization(inventory, launch, parity),
        _manifest(),
        dry_run=True,
    )
    assert result["state"] == "DRY_RUN"
    assert result["command"] == ["screen", "-S", "old_fixture", "-X", "quit"]


def test_standalone_stop_replays_comparator_instead_of_trusting_rehashed_pass() -> None:
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    parity.pop("parity_sha256")
    proof = parity["jobs"][0]["evidence"]
    proof["payload"]["canonical_receipt"]["identity"]["content_hash"] = "e" * 64
    proof["sha256"] = hashlib.sha256(
        json.dumps(proof["payload"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    parity = _hash(parity, "parity_sha256")
    authorization = _authorization(inventory, launch, parity)
    with pytest.raises(MigrationError, match="parity job"):
        stop_legacy_session(
            "old_fixture",
            inventory,
            parity,
            launch,
            authorization,
            _manifest(),
            dry_run=True,
        )


def test_live_stop_rechecks_exact_screen_pid_before_quit(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "There is a screen on:\n\t9999.old_fixture\t(Detached)\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return Result()

    monkeypatch.setattr(migration.subprocess, "run", fake_run)
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    with pytest.raises(MigrationError, match="identity changed"):
        stop_legacy_session(
            "old_fixture",
            inventory,
            parity,
            launch,
            _authorization(inventory, launch, parity),
            _manifest(),
            dry_run=False,
        )
    assert calls == [["screen", "-ls"]]


def test_live_stop_refuses_when_canonical_replacement_is_not_running(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout="There is a screen on:\n\t1111.old_fixture\t(Detached)\n",
            stderr="",
        )

    monkeypatch.setattr(migration.subprocess, "run", fake_run)
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    with pytest.raises(MigrationError, match="canonical screen identity changed"):
        stop_legacy_session(
            "old_fixture",
            inventory,
            parity,
            launch,
            _authorization(inventory, launch, parity),
            _manifest(),
            dry_run=False,
        )
    assert calls == [["screen", "-ls"]]


def test_live_stop_refuses_when_legacy_child_command_changed(monkeypatch) -> None:
    calls: list[list[str]] = []
    canonical = canonical_screen_name("canonical_fixture", EPOCH)

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if command == ["screen", "-ls"]:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "There are screens on:\n"
                    "\t1111.old_fixture\t(Detached)\n"
                    f"\t4321.{canonical}\t(Detached)\n"
                ),
                stderr="",
            )
        if command[:3] == ["ps", "-eo", "pid=,ppid=,command="]:
            return SimpleNamespace(
                returncode=0,
                stdout="1234 1111 python another_workload.py\n",
                stderr="",
            )
        pytest.fail(f"unexpected subprocess: {command}")

    monkeypatch.setattr(migration.subprocess, "run", fake_run)
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    with pytest.raises(MigrationError, match="legacy child identity changed"):
        stop_legacy_session(
            "old_fixture",
            inventory,
            parity,
            launch,
            _authorization(inventory, launch, parity),
            _manifest(),
            dry_run=False,
        )
    assert ["screen", "-S", "old_fixture", "-X", "quit"] not in calls


def test_live_stop_rechecks_full_os_identity_and_records_post_stop(monkeypatch) -> None:
    calls: list[list[str]] = []
    canonical = canonical_screen_name("canonical_fixture", EPOCH)
    screen_reads = 0

    def fake_run(command, **kwargs):
        nonlocal screen_reads
        calls.append(list(command))
        if command == ["screen", "-ls"]:
            screen_reads += 1
            legacy = "\t1111.old_fixture\t(Detached)\n" if screen_reads == 1 else ""
            return SimpleNamespace(
                returncode=0,
                stdout=f"There are screens on:\n{legacy}\t4321.{canonical}\t(Detached)\n",
                stderr="",
            )
        if command[:3] == ["ps", "-eo", "pid=,ppid=,command="]:
            return SimpleNamespace(
                returncode=0,
                stdout="1234 1111 python fixture_loop.py\n",
                stderr="",
            )
        if command and command[0] == "lsof":
            return SimpleNamespace(
                returncode=0,
                stdout=f"p1234\nn{ROOT}\n",
                stderr="",
            )
        if command == ["screen", "-S", "old_fixture", "-X", "quit"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        pytest.fail(f"unexpected subprocess: {command}")

    monkeypatch.setattr(migration.subprocess, "run", fake_run)
    launch = _launch()
    inventory = _inventory(_row())
    parity = _parity(launch)
    result = stop_legacy_session(
        "old_fixture",
        inventory,
        parity,
        launch,
        _authorization(inventory, launch, parity),
        _manifest(),
        dry_run=False,
    )
    assert result["state"] == "STOPPED"
    assert result["returncode"] == 0
    assert "old_fixture" not in result["post_stop_sessions"]
    assert ["screen", "-S", "old_fixture", "-X", "quit"] in calls


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    receipt = tmp_path / "duplicate.json"
    receipt.write_text('{"state":"PASS","state":"FAIL_CLOSED"}', encoding="utf-8")
    with pytest.raises(MigrationError, match="duplicate JSON key"):
        _read_json_receipt(receipt)


def test_full_migrate_dry_run_never_invokes_subprocess(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    manifest = _manifest()
    for relative in (
        "scripts/run_xsec_shadow_loop.sh",
        "configs/preregistered/xsec_v4_family_landscape_20260728.json",
        "research_lab/data/bybit_instruments_linear.json",
    ):
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    manifest_path = project / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("migrate dry-run must not invoke subprocess"),
    )
    exit_code = migration._migrate_command(
        SimpleNamespace(
            project_root=str(project),
            legacy_root=str(legacy),
            manifest=str(manifest_path),
            evidence_epoch=EPOCH,
            inventory=None,
            parity=None,
            output=str(tmp_path / "migration"),
            dry_run=True,
        )
    )
    receipt = json.loads((tmp_path / "migration/migration_receipt.json").read_text())
    assert exit_code == 0
    assert receipt["state"] == "NOT_CONFIRMED"
    assert receipt["legacy_stop"] == []


def test_cli_exposes_all_migration_subcommands() -> None:
    parser = build_migration_parser()
    args = {
        "inventory": ["--project-root", ".", "--legacy-root", ".", "--manifest", "x", "--evidence-epoch", EPOCH],
        "launch": ["--project-root", ".", "--manifest", "x", "--evidence-epoch", EPOCH],
        "verify": ["--launch-receipt", "x"],
        "stop": ["--screen-name", "old_fixture", "--project-root", ".", "--manifest", "m", "--inventory", "x", "--parity", "y", "--launch", "z", "--authorization", "a"],
        "migrate": ["--project-root", ".", "--legacy-root", ".", "--manifest", "x", "--evidence-epoch", EPOCH, "--output", "out"],
    }
    for command, options in args.items():
        assert parser.parse_args([command, *options]).command == command
