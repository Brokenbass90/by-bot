from __future__ import annotations

import json
from pathlib import Path

import pytest
import research_lab.station_v3 as station_v3

from research_lab.station_v3 import (
    AUTHORITY,
    ExclusiveRunLock,
    HashDriftError,
    InputValidationError,
    IntegrityError,
    LockHeldError,
    TrialFailedError,
    run_station,
)


RUNNER = r'''import argparse
import json

p = argparse.ArgumentParser()
p.add_argument("--request", required=True)
p.add_argument("--result", required=True)
a = p.parse_args()
with open(a.request, "r", encoding="utf-8") as f:
    request = json.load(f)
result = {
    "status": "ok",
    "idempotency_key": request["idempotency_key"],
    "trial_id": request["trial_id"],
    "advisory_metric": request["params"].get("value", 0),
}
with open(a.result, "w", encoding="utf-8") as f:
    json.dump(result, f, sort_keys=True)
'''


def _write_fixture(
    root: Path,
    *,
    timestamps: list[int] | None = None,
    calendar: dict | None = None,
    run_id: str = "station_v3_test_001",
    runner_source: str = RUNNER,
    coverage_start: int | None = None,
    coverage_end_exclusive: int | None = None,
    source_as_of: int | None = None,
) -> tuple[Path, Path, str]:
    (root / "runner.py").write_text(runner_source, encoding="utf-8")
    (root / "spec.json").write_text('{"strategy":"fixture"}\n', encoding="utf-8")
    timestamps = timestamps or [0, 300, 600]
    coverage_start = min(timestamps) if coverage_start is None else coverage_start
    coverage_end_exclusive = (
        max(timestamps) + 300 if coverage_end_exclusive is None else coverage_end_exclusive
    )
    source_as_of = coverage_end_exclusive + 300 if source_as_of is None else source_as_of
    rows = "timestamp,close\n" + "".join(f"{timestamp},{100 + index}\n" for index, timestamp in enumerate(timestamps))
    (root / "bars.csv").write_text(rows, encoding="utf-8")
    config = {
        "schema_version": 3,
        "authority": AUTHORITY,
        "promotion_authority": False,
        "runner": {"path": "runner.py", "args": []},
        "spec_path": "spec.json",
        "code_paths": [],
        "inputs": [
            {
                "name": "bars",
                "path": "bars.csv",
                "timestamp_column": "timestamp",
                "timestamp_format": "epoch_s",
                "interval_seconds": 300,
                "coverage_start": coverage_start,
                "coverage_end_exclusive": coverage_end_exclusive,
                "source_as_of": source_as_of,
                "finality_lag_seconds": 300,
                "calendar": calendar or {"kind": "continuous", "timezone": "UTC"},
            }
        ],
        "trial_timeout_seconds": 20,
        "trials": [
            {"id": "trial_a", "params": {"value": 1}},
            {"id": "trial_b", "params": {"value": 2}},
        ],
    }
    config_path = root / "station.json"
    config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
    return config_path, root / "runs", run_id


def _run(root: Path, config: Path, runs: Path, run_id: str, **kwargs):
    return run_station(
        config_path=config,
        runs_root=runs,
        run_id=run_id,
        project_root=root,
        **kwargs,
    )


def test_exclusive_per_run_lock(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(tmp_path)
    run_dir = runs / run_id
    with ExclusiveRunLock(run_dir):
        with pytest.raises(LockHeldError):
            _run(tmp_path, config, runs, run_id)


def test_stale_done_text_cannot_complete_manifest_run(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(tmp_path)
    run_dir = runs / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "old_launcher.log").write_text("[old] ГОТОВО: fake completion\n", encoding="utf-8")

    result = _run(tmp_path, config, runs, run_id)

    assert result["state"] == "COMPLETED"
    assert result["successful_trials"] == 2
    assert len((run_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert json.loads((run_dir / "completion.json").read_text(encoding="utf-8"))["manifest_sha256"]

    # A normal completed resume is manifest-bound and leaves the checkpoint honest.
    assert _run(tmp_path, config, runs, run_id)["state"] == "COMPLETED"
    assert json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))["state"] == "COMPLETED"


def test_immutable_hash_drift_refuses_even_completed_resume(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(tmp_path)
    assert _run(tmp_path, config, runs, run_id)["state"] == "COMPLETED"
    (tmp_path / "spec.json").write_text('{"strategy":"changed"}\n', encoding="utf-8")

    with pytest.raises(HashDriftError, match="immutable file drift"):
        _run(tmp_path, config, runs, run_id)

    refusal = json.loads((runs / run_id / "integrity_refusal.json").read_text(encoding="utf-8"))
    assert refusal["state"] == "FAILED_CLOSED"

    # Restoring the old bytes cannot legitimize evidence produced across an
    # observed drift window; an integrity refusal permanently poisons this run id.
    (tmp_path / "spec.json").write_text('{"strategy":"fixture"}\n', encoding="utf-8")
    with pytest.raises(IntegrityError, match="permanently failed closed"):
        _run(tmp_path, config, runs, run_id)


def test_resume_is_idempotent_after_operational_pause(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(tmp_path)
    first = _run(tmp_path, config, runs, run_id, max_trials=1)
    run_dir = runs / run_id
    first_receipt = next((run_dir / "receipts").glob("*.json"))
    original_receipt = first_receipt.read_bytes()

    assert first["state"] == "PAUSED"
    assert first["completed_trials"] == 1
    assert not (run_dir / "completion.json").exists()

    resumed = _run(tmp_path, config, runs, run_id)

    assert resumed["state"] == "COMPLETED"
    assert first_receipt.read_bytes() == original_receipt
    ledger = (run_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 2
    assert len({json.loads(line)["idempotency_key"] for line in ledger}) == 2


def test_checkpoint_prevents_silent_rerun_after_receipt_and_ledger_loss(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(tmp_path)
    assert _run(tmp_path, config, runs, run_id, max_trials=1)["state"] == "PAUSED"
    run_dir = runs / run_id
    (run_dir / "trials.jsonl").unlink()
    next((run_dir / "receipts").glob("*.json")).unlink()

    with pytest.raises(IntegrityError, match="checkpoint references 1 completed trials"):
        _run(tmp_path, config, runs, run_id)


def test_checkpoint_allows_deterministic_ledger_rebuild_from_receipt(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(tmp_path)
    assert _run(tmp_path, config, runs, run_id, max_trials=1)["state"] == "PAUSED"
    ledger_path = runs / run_id / "trials.jsonl"
    original_first_record = ledger_path.read_bytes()
    ledger_path.unlink()

    assert _run(tmp_path, config, runs, run_id)["state"] == "COMPLETED"
    assert ledger_path.read_bytes().startswith(original_first_record)


def test_checkpoint_tamper_is_not_silently_overwritten(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(tmp_path)
    assert _run(tmp_path, config, runs, run_id, max_trials=1)["state"] == "PAUSED"
    checkpoint_path = runs / run_id / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["ledger_tail_sha256"] = "0" * 64
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(IntegrityError, match="checkpoint/ledger prefix mismatch"):
        _run(tmp_path, config, runs, run_id)


def test_coverage_edges_and_source_finality_are_explicit(tmp_path: Path) -> None:
    config, runs, run_id = _write_fixture(
        tmp_path,
        timestamps=[0, 300],
        coverage_end_exclusive=900,
    )
    with pytest.raises(InputValidationError, match="after last row"):
        _run(tmp_path, config, runs, run_id)

    other = tmp_path / "finality"
    other.mkdir()
    config, runs, run_id = _write_fixture(other, source_as_of=1199)
    with pytest.raises(InputValidationError, match="does not finalize"):
        _run(other, config, runs, run_id)


def test_dir_fd_cannot_escape_per_trial_write_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("immutable\n", encoding="utf-8")
    runner = f'''import argparse
import os

p = argparse.ArgumentParser()
p.add_argument("--request", required=True)
p.add_argument("--result", required=True)
a = p.parse_args()
directory = os.open({str(tmp_path)!r}, os.O_RDONLY)
try:
    target = os.open("outside.txt", os.O_WRONLY | os.O_TRUNC, dir_fd=directory)
    os.close(target)
finally:
    os.close(directory)
'''
    config, runs, run_id = _write_fixture(tmp_path, runner_source=runner)

    with pytest.raises(TrialFailedError, match="failed closed"):
        _run(tmp_path, config, runs, run_id)

    assert outside.read_text(encoding="utf-8") == "immutable\n"
    receipt = json.loads(next((runs / run_id / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"


def test_binary_stdout_is_hashed_without_text_decode_failure(tmp_path: Path) -> None:
    runner = RUNNER + '\nimport sys\nsys.stdout.buffer.write(b"\\xff")\n'
    config, runs, run_id = _write_fixture(tmp_path, runner_source=runner)

    assert _run(tmp_path, config, runs, run_id)["state"] == "COMPLETED"
    receipt = json.loads(next((runs / run_id / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    assert (runs / run_id / receipt["stdout_path"]).read_bytes() == b"\xff"


def test_spawn_error_still_creates_failed_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, runs, run_id = _write_fixture(tmp_path)

    def fail_spawn(*args, **kwargs):
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(station_v3.subprocess, "run", fail_spawn)
    with pytest.raises(TrialFailedError, match="synthetic spawn failure"):
        _run(tmp_path, config, runs, run_id)

    receipt = json.loads(next((runs / run_id / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert "synthetic spawn failure" in receipt["failure_reason"]


@pytest.mark.parametrize(
    ("timestamps", "message"),
    [
        ([0, 300, 601], "alignment"),
        ([0, 600], "unexpected open-market gap"),
        ([0, 300, 300], "duplicate timestamp"),
        ([0, 600, 300], "not strictly sorted"),
    ],
)
def test_malformed_interval_duplicate_sort_and_open_gap_fail_closed(
    tmp_path: Path, timestamps: list[int], message: str
) -> None:
    config, runs, run_id = _write_fixture(tmp_path, timestamps=timestamps)

    with pytest.raises(InputValidationError, match=message):
        _run(tmp_path, config, runs, run_id)

    assert not (runs / run_id / "manifest.json").exists()


def test_weekly_market_closure_policy_allows_only_closed_gap(tmp_path: Path) -> None:
    # Friday 23:55 UTC -> Monday 00:00 UTC.  Every missing five-minute slot is
    # configured closed, so this is a valid deterministic market-calendar gap.
    friday = 172_500  # 1970-01-02 Friday 23:55 UTC
    monday = 345_600  # 1970-01-05 Monday 00:00 UTC
    calendar = {
        "kind": "weekly_schedule",
        "timezone": "UTC",
        "open_windows": {str(day): [["00:00", "24:00"]] for day in range(5)},
    }
    config, runs, run_id = _write_fixture(
        tmp_path,
        timestamps=[friday - 300, friday, monday, monday + 300],
        calendar=calendar,
    )

    result = _run(tmp_path, config, runs, run_id)

    assert result["state"] == "COMPLETED"
    manifest = json.loads((runs / run_id / "manifest.json").read_text(encoding="utf-8"))
    validation = manifest["inputs"][0]["validation"]
    assert validation["closure_gaps"] == 1
    assert validation["missing_closed_slots"] > 0
