from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bot.sbr1_universe import FIXED51_UNIVERSE
from research_lab.att1_ets2s_burnin import evaluate_burnin


HOUR_MS = 3_600_000
START_MS = 1_788_595_320_000
END_MS = START_MS + 72 * HOUR_MS
AUTHORITY = "research_only_public_att1_ets2s_signal_shadow_no_orders_no_private_api_no_money_no_promotion"
UNIVERSE = FIXED51_UNIVERSE
PROFILE_HASHES = {
    "ATT1": {
        "config_hash": "9d6f790d1d21b5597643a11d768d09b9234a1798b6db3f53490e0aad5af187b4",
        "fixed51_config_hash": "fbe3ad079bdf89a00786a5a9b3c27ffd8be27b7826ae3191d60dbb80ead47a9f",
        "source_hash": "a7b8d3f5d69ee3943aae8f4c9489fd1a5f5a84fe3ed89b08707231d647299f15",
    },
    "ETS2S": {
        "config_hash": "453378735642a9c27d9a5ffd94c8bd2d7ab77a28f9cc3f14dbf4334d7c8c0662",
        "fixed51_config_hash": "af1f846a73098a386d5bff84e589749372c760fc829ae49d95001e8b5f8a3cf5",
        "source_hash": "d682e034400f55e943ec1a43bfc093eee856624f1b7a1b59e0c5e5eb2ccf9c50",
    },
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_canonical(value) + b"\n")


def _chain(rows: list[dict[str, object]]) -> bytes:
    previous = "0" * 64
    encoded: list[bytes] = []
    for core in rows:
        unsigned = {**core, "prev_hash": previous}
        row = {**unsigned, "row_hash": _sha(_canonical(unsigned))}
        encoded.append(_canonical(row) + b"\n")
        previous = str(row["row_hash"])
    return b"".join(encoded)


def _fixture(tmp_path: Path, *, hours: int = 72, as_of_ms: int = END_MS) -> tuple[Path, Path]:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    profiles = copy.deepcopy(PROFILE_HASHES)
    config = {
        "schema_id": "att1_ets2s_signal_shadow_config_v1",
        "enabled": True,
        "default_off": True,
        "authority": AUTHORITY,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "release_or_promotion_authority": False,
        "sealed_data_allowed": False,
        "store_contract_id": "canonical_closed_utc_buckets_v1",
        "evidence_universe": list(UNIVERSE),
        "evidence_universe_sha256": _sha(_canonical(list(UNIVERSE))),
        "profiles": profiles,
        "expected_unavailable_symbols": ["HFTUSDT"],
        "data_policy": {
            "max_decision_age_ms": 300_000,
            "max_forward_lag_ms": 300_000,
            "min_runtime_free_bytes": 536_870_912,
        },
    }
    _write_json(snapshot / "config.json", config)
    source_files = [
        {"path": "deploy/systemd/att1-ets2s-signal-shadow.service", "bytes": 11, "sha256": "1" * 64},
        {"path": "deploy/systemd/att1-ets2s-signal-shadow.timer", "bytes": 12, "sha256": "2" * 64},
        {"path": "scripts/launch_att1_ets2s_shadow.py", "bytes": 13, "sha256": "3" * 64},
    ]
    closure = _sha(_canonical({"files": source_files, "schema_id": "att1_ets2s_source_closure_v1"}))
    manifest = {
        "schema_id": "att1_ets2s_signal_shadow_manifest_v1",
        "authority": AUTHORITY,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "release_or_promotion_authority": False,
        "sealed_data_allowed": False,
        "evidence_universe": list(UNIVERSE),
        "evidence_universe_sha256": config["evidence_universe_sha256"],
        "profiles": profiles,
        "source_closure_sha256": closure,
        "source_files": source_files,
    }
    _write_json(snapshot / "manifest.json", manifest)
    config_hash = _sha((snapshot / "config.json").read_bytes())
    manifest_hash = _sha((snapshot / "manifest.json").read_bytes())
    anchor = {
        "schema_id": "att1_ets2s_signal_shadow_deployment_anchor_v1",
        "git_commit_sha": "a" * 40,
        "config_sha256": config_hash,
        "manifest_sha256": manifest_hash,
        "source_closure_sha256": closure,
        "privileged_launcher_sha256": "3" * 64,
        "acknowledgement": "ATT1_ETS2S_SIGNAL_SHADOW",
        "enabled": True,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
    }
    _write_json(snapshot / "anchor.json", anchor)

    rows: list[dict[str, object]] = []
    chain_lines: list[bytes] = []
    previous_hash = "0" * 64
    receipts: list[dict[str, object]] = []
    systemd_lines: list[dict[str, object]] = []
    for hour in range(hours):
        observed = START_MS + hour * HOUR_MS + 1_000
        cycle_id = f"cycle:{observed}"
        bar_close = START_MS + hour * HOUR_MS - 120_000
        for symbol in (item for item in UNIVERSE if item != "HFTUSDT"):
            for sleeve in ("ATT1", "ETS2S"):
                profile = profiles[sleeve]
                rows.append(
                    {
                        "schema_id": "att1_ets2s_signal_shadow_decision_v1",
                        "claim_key": f"decision:EXECUTION_FORWARD:{sleeve}:{symbol}:{bar_close}",
                        "authority": AUTHORITY,
                        "sleeve_id": sleeve,
                        "symbol": symbol,
                        "bar_start_ms": bar_close - HOUR_MS,
                        "bar_close_ms": bar_close,
                        "observed_at_ms": observed,
                        "decision_age_ms": 121_000,
                        "stream": "EXECUTION_FORWARD",
                        "cycle_id": cycle_id,
                        "signal": None,
                        "no_signal_reason": "synthetic_no_signal",
                        "exception": None,
                        "l1_profile_config_hash": profile["config_hash"],
                        "profile_config_hash": profile["fixed51_config_hash"],
                        "profile_source_hash": profile["source_hash"],
                        "store_contract_id": "canonical_closed_utc_buckets_v1",
                        "orders_allowed": False,
                        "private_api_allowed": False,
                        "money_authority": False,
                        "broker_calls": 0,
                        "order_calls": 0,
                    }
                )
        for core in rows[-100:]:
            unsigned = {**core, "prev_hash": previous_hash}
            last = {**unsigned, "row_hash": _sha(_canonical(unsigned))}
            chain_lines.append(_canonical(last) + b"\n")
            previous_hash = last["row_hash"]
        receipt = {
            "schema_id": "att1_ets2s_signal_shadow_cycle_v1",
            "authority": AUTHORITY,
            "cycle_id": cycle_id,
            "observed_at_ms": observed,
            "healthy": True,
            "evidence_universe_count": 51,
            "available_symbols": list(UNIVERSE),
            "expected_unavailable": [],
            "unchanged_symbols": ["HFTUSDT"],
            "coverage": {"ATT1": 50, "ETS2S": 50},
            "signals": {"ATT1": 0, "ETS2S": 0},
            "no_signals": {"ATT1": 50, "ETS2S": 50},
            "exceptions": {"ATT1": 0, "ETS2S": 0},
            "stream_counts": {"ALPHA_FORWARD_BACKFILL": 0, "EXECUTION_FORWARD": 100},
            "rows_written": 100,
            "errors": [],
            "journal": {"row_count": len(rows), "tip_hash": last["row_hash"]},
            "config_sha256": config_hash,
            "manifest_sha256": manifest_hash,
            "source_closure_sha256": closure,
            "evidence_universe_sha256": config["evidence_universe_sha256"],
            "store_contract_id": "canonical_closed_utc_buckets_v1",
            "orders_allowed": False,
            "private_api_allowed": False,
            "money_authority": False,
            "broker_calls": 0,
            "order_calls": 0,
        }
        receipts.append(receipt)
        systemd_lines.append(
            {
                "__REALTIME_TIMESTAMP": str((observed + 120_000) * 1000),
                "_SYSTEMD_UNIT": "att1-ets2s-signal-shadow.service",
                "_SYSTEMD_INVOCATION_ID": f"{hour + 1:032x}",
                "MESSAGE": _canonical(receipt).decode("ascii"),
            }
        )
    (snapshot / "events.jsonl").write_bytes(b"".join(chain_lines))
    heartbeat = {"schema_id": "att1_ets2s_signal_shadow_heartbeat_v1", **receipts[-1]}
    _write_json(snapshot / "heartbeat.json", heartbeat)
    (snapshot / "systemd.jsonl").write_bytes(b"".join(_canonical(row) + b"\n" for row in systemd_lines))

    receipt = {
        "schema_id": "att1_ets2s_vps_shadow_deployment_receipt_v1",
        "authority": AUTHORITY,
        "git_commit_sha": "a" * 40,
        "config_sha256": config_hash,
        "manifest_sha256": manifest_hash,
        "source_closure_sha256": closure,
        "privileged_launcher_sha256": "3" * 64,
        "burn_in": {
            "started": True,
            "start_utc": "2026-09-05T08:02:00Z",
            "evaluation_not_before_utc": "2026-09-08T08:02:00Z",
        },
    }
    receipt_path = tmp_path / "deployment_receipt.json"
    _write_json(receipt_path, receipt)
    snapshot_meta = {
        "schema_id": "att1_ets2s_burnin_snapshot_v1",
        "captured_at_utc": datetime.fromtimestamp(as_of_ms / 1000, timezone.utc).isoformat(),
        "capture_started_at_ms": as_of_ms - 1_000,
        "capture_finished_at_ms": as_of_ms,
        "as_of_ms": as_of_ms,
        "consistent": True,
        "files": {},
        "systemd": {
            "service": {"ActiveState": "inactive", "Result": "success", "ExecMainStatus": "0", "NRestarts": "0", "MemoryPeak": "104857600", "CPUUsageNSec": "72000000000"},
            "timer": {"ActiveState": "active", "UnitFileState": "enabled"},
            "legacy_timers": {"att1-fixed51-raw-shadow.timer": "active", "sbr1-zero-risk-shadow.timer": "active"},
            "clock": {"NTPSynchronized": "yes", "Timezone": "UTC"},
        },
        "disk": {"free_bytes": 2_000_000_000, "total_bytes": 4_000_000_000, "used_bytes": 2_000_000_000},
        "source_verification": {
            "files": [{**row, "mode": "0644", "uid": 0, "gid": 1000} for row in source_files],
            "launcher": {"sha256": "3" * 64, "bytes": 13, "mode": "0755", "uid": 0, "gid": 0},
            "units": {
                "service": {"sha256": "1" * 64, "bytes": 11, "mode": "0644", "uid": 0, "gid": 0},
                "timer": {"sha256": "2" * 64, "bytes": 12, "mode": "0644", "uid": 0, "gid": 0},
            },
        },
        "host": "synthetic",
    }
    for name in ("events.jsonl", "heartbeat.json", "config.json", "manifest.json", "anchor.json", "systemd.jsonl"):
        data = (snapshot / name).read_bytes()
        snapshot_meta["files"][name] = {"sha256": _sha(data), "bytes": len(data), "remote_path": f"/evidence/{name}"}
    _write_json(snapshot / "snapshot.json", snapshot_meta)
    return snapshot, receipt_path


def _rehash_snapshot(snapshot: Path) -> None:
    meta = json.loads((snapshot / "snapshot.json").read_text())
    for name in meta["files"]:
        data = (snapshot / name).read_bytes()
        meta["files"][name]["sha256"] = _sha(data)
        meta["files"][name]["bytes"] = len(data)
    _write_json(snapshot / "snapshot.json", meta)


def _rewrite_events(snapshot: Path, mutate) -> None:
    rows = [json.loads(line) for line in (snapshot / "events.jsonl").read_bytes().splitlines()]
    cores = [{key: value for key, value in row.items() if key not in {"prev_hash", "row_hash"}} for row in rows]
    mutate(cores)
    (snapshot / "events.jsonl").write_bytes(_chain(cores))
    _rehash_snapshot(snapshot)


def test_valid_72_hour_bundle_passes_without_granting_promotion(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)

    result = evaluate_burnin(snapshot, receipt)

    assert result["status"] == "PASS_OPERATIONAL_BURN_IN", result["findings"]
    assert result["burn_in"]["completed_slots"] == 72
    assert result["statistics_semantics"] == "signals_only_not_trades_or_profit"
    assert result["promotion_authority"] is False
    assert result["money_authority"] is False


def test_preboundary_evidence_cannot_pass(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path, hours=20, as_of_ms=START_MS + 20 * HOUR_MS)
    result = evaluate_burnin(snapshot, receipt)
    assert result["status"] == "IN_PROGRESS", result["findings"]
    assert result["burn_in"]["completed_slots"] == 20


@pytest.mark.parametrize("breakage", ["tamper", "truncate", "duplicate"])
def test_journal_integrity_breakage_fails_closed(tmp_path: Path, breakage: str) -> None:
    snapshot, receipt = _fixture(tmp_path)
    path = snapshot / "events.jsonl"
    if breakage == "tamper":
        data = bytearray(path.read_bytes())
        data[50] ^= 1
        path.write_bytes(data)
    elif breakage == "truncate":
        path.write_bytes(path.read_bytes()[:-1])
    else:
        lines = path.read_bytes().splitlines(keepends=True)
        path.write_bytes(b"".join(lines + [lines[-1]]))
    _rehash_snapshot(snapshot)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_missing_hour_and_duplicate_retry_cannot_inflate_slots(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path, hours=71)
    lines = [json.loads(line) for line in (snapshot / "systemd.jsonl").read_bytes().splitlines()]
    duplicate = copy.deepcopy(lines[-1])
    duplicate["__REALTIME_TIMESTAMP"] = str(int(duplicate["__REALTIME_TIMESTAMP"]) + 1)
    lines.append(duplicate)
    (snapshot / "systemd.jsonl").write_bytes(b"".join(_canonical(row) + b"\n" for row in lines))
    _rehash_snapshot(snapshot)
    result = evaluate_burnin(snapshot, receipt)
    assert result["status"] == "FAIL_CLOSED"
    assert "missing required scheduled slots" in result["findings"][0]


@pytest.mark.parametrize("field", ["profile", "universe", "authority"])
def test_profile_universe_and_authority_drift_fail_closed(tmp_path: Path, field: str) -> None:
    snapshot, receipt = _fixture(tmp_path)
    if field == "profile":
        _rewrite_events(snapshot, lambda rows: rows[0].__setitem__("profile_source_hash", "f" * 64))
    elif field == "universe":
        _rewrite_events(snapshot, lambda rows: rows[0].__setitem__("symbol", "OUTSIDEUSDT"))
    else:
        _rewrite_events(snapshot, lambda rows: rows[0].__setitem__("money_authority", True))
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


@pytest.mark.parametrize("age_ms", [-1, 300_001])
def test_future_or_stale_forward_decision_fails_closed(tmp_path: Path, age_ms: int) -> None:
    snapshot, receipt = _fixture(tmp_path)

    def mutate(rows: list[dict[str, object]]) -> None:
        rows[0]["decision_age_ms"] = age_ms
        rows[0]["observed_at_ms"] = int(rows[0]["bar_close_ms"]) + age_ms

    _rewrite_events(snapshot, mutate)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_backfill_rows_never_count_as_burnin_slots(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path, hours=71)

    def mutate(rows: list[dict[str, object]]) -> None:
        for row in rows[-100:]:
            row["stream"] = "ALPHA_FORWARD_BACKFILL"
            row["claim_key"] = str(row["claim_key"]).replace("EXECUTION_FORWARD", "ALPHA_FORWARD_BACKFILL")

    _rewrite_events(snapshot, mutate)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_journal_cycle_without_systemd_receipt_fails_closed(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    lines = (snapshot / "systemd.jsonl").read_bytes().splitlines(keepends=True)
    (snapshot / "systemd.jsonl").write_bytes(b"".join(lines[:-1]))
    _rehash_snapshot(snapshot)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_mismatched_cycle_chain_tip_fails_closed(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    lines = [json.loads(line) for line in (snapshot / "systemd.jsonl").read_bytes().splitlines()]
    cycle = json.loads(lines[-1]["MESSAGE"])
    cycle["journal"]["tip_hash"] = "f" * 64
    lines[-1]["MESSAGE"] = _canonical(cycle).decode("ascii")
    (snapshot / "systemd.jsonl").write_bytes(b"".join(_canonical(row) + b"\n" for row in lines))
    _rehash_snapshot(snapshot)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_unavailable_peak_ram_is_reported_without_inventing_a_new_gate(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    meta = json.loads((snapshot / "snapshot.json").read_text())
    meta["systemd"]["service"]["MemoryPeak"] = "[not set]"
    _write_json(snapshot / "snapshot.json", meta)
    result = evaluate_burnin(snapshot, receipt)
    assert result["status"] == "PASS_OPERATIONAL_BURN_IN", result["findings"]
    assert result["resources"]["service"]["MemoryPeak"] is None
    assert "MemoryPeak" in result["resources"]["unavailable_optional_measurements"]


def test_snapshot_inputs_must_be_regular_and_not_symlinks(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    events = snapshot / "events.jsonl"
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(events.read_bytes())
    events.unlink()
    events.symlink_to(outside)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def _rewrite_receipts(snapshot: Path, mutate) -> None:
    lines = [json.loads(line) for line in (snapshot / "systemd.jsonl").read_bytes().splitlines()]
    for line in lines:
        cycle = json.loads(line["MESSAGE"])
        mutate(line, cycle)
        line["MESSAGE"] = _canonical(cycle).decode("ascii")
    (snapshot / "systemd.jsonl").write_bytes(b"".join(_canonical(line) + b"\n" for line in lines))
    _write_json(snapshot / "heartbeat.json", json.loads(lines[-1]["MESSAGE"]))
    _rehash_snapshot(snapshot)


def test_missing_entire_sleeve_cannot_pass_even_with_consistent_counters(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    _rewrite_events(snapshot, lambda rows: rows.__setitem__(slice(None), [r for r in rows if r["sleeve_id"] == "ATT1"]))
    rows = [json.loads(line) for line in (snapshot / "events.jsonl").read_bytes().splitlines()]

    def mutate(line, cycle):
        for field in ("coverage", "signals", "no_signals", "exceptions"):
            cycle[field]["ETS2S"] = 0
        cycle["rows_written"] = 50
        cycle["stream_counts"]["EXECUTION_FORWARD"] = 50
        count = cycle["journal"]["row_count"] // 2
        cycle["journal"] = {"row_count": count, "tip_hash": rows[count - 1]["row_hash"]}

    _rewrite_receipts(snapshot, mutate)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


@pytest.mark.parametrize("change", ["future", "wrong_unit", "no_invocation", "timeout"])
def test_cycle_completion_requires_timely_service_provenance(tmp_path: Path, change: str) -> None:
    snapshot, receipt = _fixture(tmp_path)

    def mutate(line, cycle):
        if change == "future":
            line["__REALTIME_TIMESTAMP"] = str((END_MS + 100_000_000) * 1000)
        elif change == "wrong_unit":
            line["_SYSTEMD_UNIT"] = "unrelated.service"
        elif change == "no_invocation":
            line.pop("_SYSTEMD_INVOCATION_ID")
        else:
            line["__REALTIME_TIMESTAMP"] = str((cycle["observed_at_ms"] + 1_200_001) * 1000)

    _rewrite_receipts(snapshot, mutate)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_receipt_tips_must_end_at_their_own_journal_boundary(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    _rewrite_receipts(snapshot, lambda line, cycle: cycle.__setitem__("journal", {"row_count": 0, "tip_hash": "0" * 64}))
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_heartbeat_must_be_latest_completed_receipt(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    first = json.loads((snapshot / "systemd.jsonl").read_bytes().splitlines()[0])
    _write_json(snapshot / "heartbeat.json", json.loads(first["MESSAGE"]))
    _rehash_snapshot(snapshot)
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_missing_authority_activity_counter_is_not_zero(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    _rewrite_receipts(snapshot, lambda line, cycle: cycle.pop("broker_calls"))
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_finite_json_guard_rejects_exponent_overflow(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    meta = (snapshot / "snapshot.json").read_text().rstrip()
    (snapshot / "snapshot.json").write_text(meta[:-1] + ',"overflow":1e999}\n')
    assert evaluate_burnin(snapshot, receipt)["status"] == "FAIL_CLOSED"


def test_reserved_filesystem_blocks_are_not_disk_corruption(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    meta = json.loads((snapshot / "snapshot.json").read_bytes())
    meta["disk"]["free_bytes"] -= 16_777_216
    _write_json(snapshot / "snapshot.json", meta)
    result = evaluate_burnin(snapshot, receipt)
    assert result["status"] == "PASS_OPERATIONAL_BURN_IN", result["findings"]
    assert result["resources"]["disk"]["reserved_or_unavailable_bytes"] == 16_777_216


def test_deployed_manifest_profile_source_paths_are_accepted(tmp_path: Path) -> None:
    snapshot, receipt = _fixture(tmp_path)
    manifest = json.loads((snapshot / "manifest.json").read_bytes())
    for value in manifest["profiles"].values():
        value["source_paths"] = ["strategies/signals.py"]
    _write_json(snapshot / "manifest.json", manifest)
    digest = _sha((snapshot / "manifest.json").read_bytes())
    for path in (snapshot / "anchor.json", receipt):
        value = json.loads(path.read_bytes())
        value["manifest_sha256"] = digest
        _write_json(path, value)
    _rewrite_receipts(snapshot, lambda line, cycle: cycle.__setitem__("manifest_sha256", digest))
    result = evaluate_burnin(snapshot, receipt)
    assert result["status"] == "PASS_OPERATIONAL_BURN_IN", result["findings"]


def test_in_memory_evaluation_matches_offline_snapshot(tmp_path: Path) -> None:
    import research_lab.att1_ets2s_burnin as module
    snapshot, receipt = _fixture(tmp_path, hours=2, as_of_ms=START_MS + 2 * HOUR_MS)
    files = {name: (snapshot / name).read_bytes() for name in module.EXPECTED_FILES}
    result = module.evaluate_burnin_bundle((snapshot / "snapshot.json").read_bytes(), files, receipt.read_bytes())
    assert result == evaluate_burnin(snapshot, receipt)
    files["events.jsonl"] += b"altered"
    assert module.evaluate_burnin_bundle((snapshot / "snapshot.json").read_bytes(), files, receipt.read_bytes())["status"] == "FAIL_CLOSED"


def test_cli_writes_new_receipt_and_refuses_overwrite(tmp_path: Path, capsys) -> None:
    from scripts.evaluate_att1_ets2s_burnin import main
    snapshot, receipt = _fixture(tmp_path, hours=2, as_of_ms=START_MS + 2 * HOUR_MS)
    output = tmp_path / "result.json"
    args = ["--snapshot-dir", str(snapshot), "--deployment-receipt", str(receipt), "--output", str(output)]
    assert main(args) == 0
    saved = output.read_bytes()
    assert json.loads(saved)["status"] == "IN_PROGRESS"
    assert main(args) == 2
    assert output.read_bytes() == saved
