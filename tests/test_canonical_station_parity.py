from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research_lab.canonical_station import (
    AUTHORITY,
    MigrationError,
    ParityState,
    ProcessKind,
    ProcessReceipt,
    compare_collector_snapshots,
    compare_deterministic_receipts,
    compare_market_snapshot_receipts,
    register_run_identity,
    validate_completion_proof,
)
from research_lab.station_v3 import run_station


def receipt(kind: str, **kwargs: object) -> ProcessReceipt:
    base: dict[str, object] = dict(
        job_name="fixture",
        screen_name="fixture",
        pid=1,
        cwd="/repo",
        command="run",
        process_kind=ProcessKind(kind),
        identity={
            "source_sha256": "a" * 64,
            "config_sha256": "b" * 64,
            "input_sha256": "c" * 64,
            "code_sha256": "d" * 64,
            "content_sha256": "e" * 64,
            "decision_id": "decision-1",
            "intended_fill": "100.0",
            "exit": "101.0",
            "cost": "0.1",
            "funding": "0.0",
            "net_r": "1.0",
        },
        counters={"decisions": 1, "count": 2, "size_bytes": 12},
        timestamps={"source_ts": "2026-08-29T10:00:00Z"},
        evidence_paths=("runtime/fixture.json",),
        evidence_epoch="e1",
        authority={
            "authority": AUTHORITY,
            "promotion_authority": False,
            "network_authority": False,
            "private_api_authority": False,
            "order_authority": False,
            "live_write_authority": False,
            "public_data_read_authority": True,
        },
        status=ParityState.PASS,
        eligible_for_parity=True,
    )
    base.update(kwargs)
    return ProcessReceipt(**base)


def test_deterministic_parity_requires_exact_decision_and_economic_fields() -> None:
    old = receipt("deterministic_decision_loop")
    new = receipt("deterministic_decision_loop")
    assert compare_deterministic_receipts(old, new).state == ParityState.PASS

    changed = receipt(
        "deterministic_decision_loop",
        identity={**old.identity, "net_r": "0.9"},
    )
    result = compare_deterministic_receipts(old, changed)
    assert result.state == ParityState.FAIL_CLOSED
    assert result.stop_allowed is False
    assert "net_r" in result.compared_fields


def test_deterministic_parity_treats_blank_mandatory_fields_as_missing() -> None:
    old = receipt(
        "deterministic_decision_loop",
        identity={**receipt("deterministic_decision_loop").identity, "code_sha256": None},
    )
    with pytest.raises(MigrationError, match="SHA-256"):
        compare_deterministic_receipts(old, old)


def test_deterministic_parity_rejects_source_timestamp_drift() -> None:
    old = receipt("deterministic_decision_loop")
    new = receipt(
        "deterministic_decision_loop",
        timestamps={"source_ts": "2026-08-29T10:01:00Z"},
    )
    assert compare_deterministic_receipts(old, new).state == ParityState.FAIL_CLOSED

    malformed = receipt(
        "deterministic_decision_loop", timestamps={"source_ts": "garbage"}
    )
    with pytest.raises(MigrationError, match="source_ts"):
        compare_deterministic_receipts(malformed, malformed)

    subsecond = receipt(
        "deterministic_decision_loop",
        timestamps={"source_ts": "2026-08-29T10:00:00.123Z"},
    )
    with pytest.raises(MigrationError, match="whole-second"):
        compare_deterministic_receipts(subsecond, subsecond)

    aliases = receipt(
        "deterministic_decision_loop",
        timestamps={
            "closed_source_ts": "2026-08-29T10:00:00Z",
            "source_ts": "2026-08-29T10:01:00Z",
        },
    )
    with pytest.raises(MigrationError, match="conflicting source timestamp"):
        compare_deterministic_receipts(aliases, aliases)


def test_timestamp_parity_normalizes_equivalent_utc_forms() -> None:
    old = receipt(
        "deterministic_decision_loop",
        timestamps={"source_ts": "2026-08-29T10:00:00Z"},
    )
    new = receipt(
        "deterministic_decision_loop",
        timestamps={"source_ts": "2026-08-29T10:00:00+00:00"},
    )
    assert compare_deterministic_receipts(old, new).state == ParityState.PASS

    old_market = receipt(
        "market_snapshot_loop",
        timestamps={"closed_source_ts": "2026-08-29T10:00:00Z"},
    )
    new_market = receipt(
        "market_snapshot_loop",
        timestamps={"closed_source_ts": "2026-08-29T10:00:00+00:00"},
    )
    assert compare_market_snapshot_receipts(old_market, new_market).state == ParityState.PASS


def test_deterministic_parity_allows_evidence_relocation_between_epochs() -> None:
    old = receipt(
        "deterministic_decision_loop",
        screen_name="legacy_fixture",
        evidence_paths=("legacy/fixture.json",),
        evidence_epoch="legacy_epoch",
    )
    new = receipt(
        "deterministic_decision_loop",
        screen_name="canonical_fixture",
        evidence_paths=("canonical/fixture.json",),
        evidence_epoch="canonical_epoch",
    )
    assert compare_deterministic_receipts(old, new).state == ParityState.PASS


def test_parity_requires_explicit_eligibility_and_pass_status() -> None:
    old = receipt("deterministic_decision_loop")
    ineligible = receipt("deterministic_decision_loop", eligible_for_parity=False)
    result = compare_deterministic_receipts(old, ineligible)
    assert result.state == ParityState.FAIL_CLOSED
    assert result.stop_allowed is False

    not_confirmed = receipt(
        "deterministic_decision_loop", status=ParityState.NOT_CONFIRMED
    )
    result = compare_deterministic_receipts(old, not_confirmed)
    assert result.state == ParityState.FAIL_CLOSED
    assert result.stop_allowed is False


def test_parity_rejects_cross_job_scope_even_when_economics_match() -> None:
    old = receipt("deterministic_decision_loop", job_name="legacy_job")
    new = receipt("deterministic_decision_loop", job_name="different_job")
    result = compare_deterministic_receipts(old, new)
    assert result.state == ParityState.FAIL_CLOSED
    assert result.reason == "job_scope_mismatch"
    assert result.stop_allowed is False


def test_parity_rejects_structurally_incomplete_receipt_scope() -> None:
    complete = receipt("deterministic_decision_loop")
    for malformed in (
        receipt("deterministic_decision_loop", job_name=None),
        receipt("deterministic_decision_loop", command=""),
        receipt("deterministic_decision_loop", evidence_paths=()),
        receipt("deterministic_decision_loop", status="PASS"),
        receipt("deterministic_decision_loop", process_kind="deterministic_decision_loop"),
    ):
        with pytest.raises(MigrationError, match="malformed receipt"):
            compare_deterministic_receipts(complete, malformed)


def test_receipt_authority_drift_fails_closed() -> None:
    old = receipt("deterministic_decision_loop")
    new = receipt(
        "deterministic_decision_loop",
        authority={**old.authority, "public_data_read_authority": False},
    )
    with pytest.raises(MigrationError, match="receipt authority drift"):
        compare_deterministic_receipts(old, new)


def test_unknown_authority_claim_is_rejected_but_factual_false_is_allowed() -> None:
    old = receipt("deterministic_decision_loop")
    unsafe = receipt(
        "deterministic_decision_loop",
        authority={**old.authority, "unlisted_order_capability": True},
    )
    with pytest.raises(MigrationError, match="unknown authority"):
        compare_deterministic_receipts(unsafe, old)
    truthy_string = receipt(
        "deterministic_decision_loop",
        authority={**old.authority, "execution_authority": "money"},
    )
    with pytest.raises(MigrationError, match="unknown authority"):
        compare_deterministic_receipts(truthy_string, old)
    numeric = receipt(
        "deterministic_decision_loop",
        authority={**old.authority, "orders_allowed": 1},
    )
    with pytest.raises(MigrationError, match="unknown authority"):
        compare_deterministic_receipts(numeric, old)
    factual = receipt(
        "deterministic_decision_loop",
        authority={**old.authority, "orders_sent": False, "private_api_calls": False},
    )
    assert compare_deterministic_receipts(factual, old).state == ParityState.PASS


def test_authority_booleans_must_be_exact_booleans() -> None:
    old = receipt("deterministic_decision_loop")
    numeric = receipt(
        "deterministic_decision_loop",
        authority={**old.authority, "promotion_authority": 0},
    )
    with pytest.raises(MigrationError, match="receipt authority drift"):
        compare_deterministic_receipts(numeric, old)


def test_malformed_receipt_mappings_raise_migration_error() -> None:
    malformed = receipt("deterministic_decision_loop", identity=None)
    with pytest.raises(MigrationError, match="malformed receipt"):
        compare_deterministic_receipts(malformed, malformed)
    malformed_key = receipt("deterministic_decision_loop", identity={1: "value"})
    with pytest.raises(MigrationError, match="malformed receipt"):
        compare_deterministic_receipts(malformed_key, malformed_key)


def test_parity_rejects_invalid_hashes_and_counter_types() -> None:
    invalid_hash = receipt(
        "deterministic_decision_loop",
        identity={**receipt("deterministic_decision_loop").identity, "code_sha256": "bad"},
    )
    with pytest.raises(MigrationError, match="SHA-256"):
        compare_deterministic_receipts(invalid_hash, invalid_hash)
    invalid_counter = receipt(
        "deterministic_decision_loop", counters={"decisions": True}
    )
    with pytest.raises(MigrationError, match="counter"):
        compare_deterministic_receipts(invalid_counter, invalid_counter)

    invalid_size = receipt(
        "collector_supervisor",
        identity={
            "source_sha256": "a" * 64,
            "content_sha256": "b" * 64,
            "count": "2",
            "size_bytes": 12,
        },
        counters={"count": 2},
    )
    with pytest.raises(MigrationError, match="counter"):
        compare_collector_snapshots(invalid_size, invalid_size)

    negative = receipt(
        "collector_supervisor",
        identity={
            "source_sha256": "a" * 64,
            "content_sha256": "b" * 64,
            "count": -1,
            "size_bytes": -1,
        },
        counters={"count": -1},
    )
    with pytest.raises(MigrationError, match="non-negative"):
        compare_collector_snapshots(negative, negative)


def test_market_snapshot_without_shared_closed_timestamp_stays_not_confirmed() -> None:
    old = receipt(
        "market_snapshot_loop",
        timestamps={"closed_source_ts": "2026-08-29T10:00:00Z"},
    )
    new = receipt(
        "market_snapshot_loop",
        timestamps={"closed_source_ts": "2026-08-29T10:01:00Z"},
    )
    result = compare_market_snapshot_receipts(old, new)
    assert result.state == ParityState.NOT_CONFIRMED
    assert result.stop_allowed is False


def test_market_snapshot_requires_timestamp_even_when_source_ts_exists() -> None:
    old = receipt("market_snapshot_loop", timestamps={})
    new = receipt("market_snapshot_loop", timestamps={})
    result = compare_market_snapshot_receipts(old, new)
    assert result.state == ParityState.NOT_CONFIRMED
    assert result.reason == "shared_closed_source_timestamp_unavailable"

    fallback = receipt(
        "market_snapshot_loop",
        timestamps={"source_ts": "2026-08-29T10:00:00Z"},
    )
    assert compare_market_snapshot_receipts(fallback, fallback).state == ParityState.NOT_CONFIRMED

    malformed = receipt(
        "market_snapshot_loop",
        timestamps={"closed_source_ts": "2026-08-29T10:00:00"},
    )
    with pytest.raises(MigrationError, match="closed_source_ts"):
        compare_market_snapshot_receipts(malformed, malformed)


def test_market_snapshot_accepts_explicit_zero_utc_offset() -> None:
    value = receipt(
        "market_snapshot_loop",
        timestamps={"closed_source_ts": "2026-08-29T10:00:00+00:00"},
    )
    assert compare_market_snapshot_receipts(value, value).state == ParityState.PASS


def test_market_snapshot_rejects_wrong_kind_and_missing_snapshot_identity() -> None:
    old = receipt("deterministic_decision_loop")
    new = receipt("deterministic_decision_loop")
    assert compare_market_snapshot_receipts(old, new).state == ParityState.FAIL_CLOSED

    incomplete = receipt(
        "market_snapshot_loop",
        identity={"source_sha256": "a" * 64},
        timestamps={"closed_source_ts": "2026-08-29T10:00:00Z"},
    )
    result = compare_market_snapshot_receipts(incomplete, incomplete)
    assert result.state == ParityState.FAIL_CLOSED
    assert "mandatory" in result.reason


def test_market_snapshot_does_not_require_trade_execution_fields() -> None:
    identity = {
        "source_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "input_sha256": "c" * 64,
        "content_sha256": "d" * 64,
        "decision_id": "snapshot-decision-1",
        "universe_sha256": "e" * 64,
        "target_usd": {"BTCUSDT": 10.0},
    }
    value = receipt(
        "market_snapshot_loop",
        identity=identity,
        timestamps={"closed_source_ts": "2026-08-29T10:00:00Z"},
    )
    assert compare_market_snapshot_receipts(value, value).state == ParityState.PASS


def test_collector_parity_ignores_freshness_but_requires_content_and_counts() -> None:
    old = receipt(
        "collector_supervisor",
        identity={
            "source_sha256": "a" * 64,
            "count": 2,
            "size_bytes": 12,
            "content_sha256": "e" * 64,
            "updated_at_utc": "2026-08-29T10:00:00Z",
            "freshness": "old",
        },
        counters={"count": 2},
        timestamps={"fresh": "1"},
    )
    new = receipt(
        "collector_supervisor",
        identity={
            "source_sha256": "a" * 64,
            "count": 2,
            "size_bytes": 12,
            "content_sha256": "e" * 64,
            "updated_at_utc": "2026-08-29T10:01:00Z",
            "freshness": "new",
        },
        counters={"count": 2},
        timestamps={"fresh": "2"},
    )
    assert compare_collector_snapshots(old, new).state == ParityState.PASS

    changed = receipt(
        "collector_supervisor",
        identity={**old.identity, "content_sha256": "f" * 64, "count": 3},
        counters={"count": 3},
    )
    assert compare_collector_snapshots(old, changed).state == ParityState.FAIL_CLOSED


def test_collector_parity_normalizes_hash_and_counter_aliases() -> None:
    old = receipt(
        "collector_supervisor",
        identity={
            "source_sha256": "a" * 64,
            "content_sha256": "b" * 64,
            "count": 2,
            "size_bytes": 12,
        },
        counters={"count": 2},
    )
    new = receipt(
        "collector_supervisor",
        identity={
            "source_hash": "a" * 64,
            "content_hash": "b" * 64,
        },
        counters={"records": 2, "size": 12},
    )
    assert compare_collector_snapshots(old, new).state == ParityState.PASS


def test_collector_compares_non_freshness_timestamps() -> None:
    identity = {
        "source_sha256": "a" * 64,
        "content_sha256": "b" * 64,
        "count": 2,
        "size_bytes": 12,
    }
    old = receipt(
        "collector_supervisor",
        identity=identity,
        counters={"count": 2},
        timestamps={"source_ts": "2026-08-29T10:00:00Z"},
    )
    equivalent = receipt(
        "collector_supervisor",
        identity=identity,
        counters={"count": 2},
        timestamps={"source_ts": "2026-08-29T10:00:00+00:00"},
    )
    assert compare_collector_snapshots(old, equivalent).state == ParityState.PASS

    drifted = receipt(
        "collector_supervisor",
        identity=identity,
        counters={"count": 2},
        timestamps={"source_ts": "2026-08-29T10:01:00Z"},
    )
    assert compare_collector_snapshots(old, drifted).state == ParityState.FAIL_CLOSED


def test_deterministic_parity_normalizes_identity_aliases() -> None:
    old = receipt("deterministic_decision_loop")
    aliased_identity = dict(old.identity)
    aliased_identity["source_hash"] = aliased_identity.pop("source_sha256")
    aliased_identity["config_hash"] = aliased_identity.pop("config_sha256")
    aliased_identity["input_hash"] = aliased_identity.pop("input_sha256")
    aliased_identity["code_hash"] = aliased_identity.pop("code_sha256")
    aliased_identity["exit_price"] = aliased_identity.pop("exit")
    aliased_identity["costs"] = aliased_identity.pop("cost")
    new = receipt("deterministic_decision_loop", identity=aliased_identity)
    assert compare_deterministic_receipts(old, new).state == ParityState.PASS


def test_collector_rejects_missing_immutable_identity_or_counters() -> None:
    incomplete = receipt(
        "collector_supervisor",
        identity={},
        counters={},
    )
    result = compare_collector_snapshots(incomplete, incomplete)
    assert result.state == ParityState.FAIL_CLOSED
    assert "mandatory" in result.reason


def test_conflicting_run_identity_is_terminal(tmp_path: Path) -> None:
    path = tmp_path / "run_identity_registry.jsonl"
    register_run_identity(path, "run-1", "hash-a", {"source": "old"})
    with pytest.raises(RuntimeError, match="incompatible identity"):
        register_run_identity(path, "run-1", "hash-b", {"source": "new"})


def test_same_run_identity_registration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "run_identity_registry.jsonl"
    register_run_identity(path, "run-1", "hash-a", {"source": "old"})
    register_run_identity(path, "run-1", "hash-a", {"source": "old"})
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_registry_checks_later_conflicts_before_idempotent_return(tmp_path: Path) -> None:
    path = tmp_path / "run_identity_registry.jsonl"
    path.write_text(
        '{"run_id":"run-1","fingerprint":"hash-a","receipt":{}}\n'
        '{"run_id":"run-1","fingerprint":"hash-b","receipt":{}}\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="incompatible identity"):
        register_run_identity(path, "run-1", "hash-a", {})


def test_validate_completion_proof_requires_complete_successful_ledger(
    tmp_path: Path,
) -> None:
    runner = tmp_path / "runner.py"
    spec = tmp_path / "spec.json"
    bars = tmp_path / "bars.csv"
    config = tmp_path / "station.json"
    runner.write_text(
        "import argparse, json\n"
        "p=argparse.ArgumentParser(); p.add_argument('--request'); p.add_argument('--result'); a=p.parse_args()\n"
        "r=json.load(open(a.request)); json.dump({'status':'ok','idempotency_key':r['idempotency_key']}, open(a.result,'w'))\n",
        encoding="utf-8",
    )
    spec.write_text('{"strategy":"fixture"}\n', encoding="utf-8")
    bars.write_text("timestamp,close\n0,100\n300,101\n", encoding="utf-8")
    config.write_text(json.dumps({
        "schema_version": 3, "authority": AUTHORITY, "promotion_authority": False,
        "runner": {"path": "runner.py", "args": []}, "spec_path": "spec.json",
        "code_paths": [], "inputs": [{
            "name": "bars", "path": "bars.csv", "timestamp_column": "timestamp",
            "timestamp_format": "epoch_s", "interval_seconds": 300,
            "coverage_start": 0, "coverage_end_exclusive": 600, "source_as_of": 900,
            "finality_lag_seconds": 300, "calendar": {"kind": "continuous", "timezone": "UTC"},
        }], "trial_timeout_seconds": 20,
        "trials": [{"id": "trial_a", "params": {}}, {"id": "trial_b", "params": {}}],
    }, sort_keys=True), encoding="utf-8")
    runs = tmp_path / "runs"
    run_station(config_path=config, runs_root=runs, run_id="run-1", project_root=tmp_path)
    run_dir = runs / "run-1"
    validate_completion_proof(run_dir)

    manifest_path = run_dir / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest_payload = json.loads(manifest_bytes)
    manifest_payload["unexpected_field"] = False
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    with pytest.raises(MigrationError, match="manifest field set"):
        validate_completion_proof(run_dir)
    manifest_path.write_bytes(manifest_bytes)

    original_manifest_text = manifest_bytes.decode("utf-8")
    manifest_path.write_text(
        '{"schema_version":999,' + original_manifest_text.lstrip()[1:],
        encoding="utf-8",
    )
    with pytest.raises(MigrationError, match="duplicate JSON key"):
        validate_completion_proof(run_dir)
    manifest_path.write_bytes(manifest_bytes)

    receipt_path = next((run_dir / "receipts").glob("*.json"))
    receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    artifact_path = run_dir / receipt_payload["result_path"]
    artifact_bytes = artifact_path.read_bytes()
    artifact_path.write_bytes(artifact_bytes + b"tamper")
    with pytest.raises(MigrationError, match="artifact hash drift"):
        validate_completion_proof(run_dir)
    artifact_path.write_bytes(artifact_bytes)
    receipt_bytes = receipt_path.read_bytes()
    receipt_path.unlink()
    with pytest.raises(MigrationError, match="missing receipt"):
        validate_completion_proof(run_dir)
    receipt_path.write_bytes(receipt_bytes)

    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    original_completion = dict(completion)
    completion["network_authority"] = True
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    with pytest.raises(MigrationError, match="completion field set"):
        validate_completion_proof(run_dir)
    completion = dict(original_completion)

    completion["schema_version"] = 999
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    with pytest.raises(MigrationError, match="schema version"):
        validate_completion_proof(run_dir)
    completion = dict(original_completion)

    completion["completed_at"] = "garbage"
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    with pytest.raises(MigrationError, match="completion.completed_at"):
        validate_completion_proof(run_dir)
    completion = dict(original_completion)

    completion["completed_trials"] = True
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    with pytest.raises(MigrationError, match="completed_trials"):
        validate_completion_proof(run_dir)
    completion = dict(original_completion)

    completion["manifest_sha256"] = "0" * 64
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    with pytest.raises(MigrationError, match="manifest_sha256"):
        validate_completion_proof(run_dir)
    completion["manifest_sha256"] = original_completion["manifest_sha256"]
    completion["ledger_tail_sha256"] = "0" * 64
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    with pytest.raises(MigrationError, match="ledger_tail_sha256"):
        validate_completion_proof(run_dir)

    completion["ledger_tail_sha256"] = original_completion["ledger_tail_sha256"]
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    checkpoint_path = run_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["ledger_tail_sha256"] = "0" * 64
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(MigrationError, match="checkpoint/ledger prefix mismatch"):
        validate_completion_proof(run_dir)


def test_validate_completion_proof_rejects_manifest_hash_drift(tmp_path: Path) -> None:
    # Keep this fixture intentionally minimal: the missing proof files should
    # be rejected before any log text can influence the result.
    (tmp_path / "completion.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "checkpoint.json").write_text("{}", encoding="utf-8")
    (tmp_path / "trials.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "old.log").write_text("COMPLETED", encoding="utf-8")
    with pytest.raises(MigrationError, match="manifest authority|no manifest trials"):
        validate_completion_proof(tmp_path)
