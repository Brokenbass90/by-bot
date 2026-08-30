from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.local_research_station as station
from research_lab.canonical_station import MigrationError
from scripts.canonical_station_migration import (
    _safe_child_environment,
    build_canonical_launch_plan,
    launch_canonical_jobs,
)


ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return {
        "schema_id": "canonical_research_station_v1",
        "authority": "research_only_no_live_or_promotion",
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "public_data_read_authority": True,
        "canonical_runtime_root": "runtime/local_research_station",
        "jobs": [
            {
                "name": "fixture",
                "process_kind": "market_snapshot_loop",
                "screen_session": "canonical_fixture",
                "legacy_session_markers": ["legacy_fixture"],
                "legacy_command_markers": ["fixture.sh"],
                "launcher": ["scripts/fixture.sh"],
                "migration_mode": "canonical",
                "max_age_seconds": 60,
                "evidence_paths": ["runtime/legacy/decision.json"],
                "canonical_evidence_files": ["decision.json", "ledger.jsonl"],
                "source_paths": ["scripts/fixture.sh"],
                "config_paths": ["configs/fixture.json"],
                "input_paths": ["data/fixture.json"],
            }
        ],
    }


def _materialize_fixture(root: Path) -> None:
    for relative, text in (
        ("scripts/fixture.sh", "#!/bin/sh\n"),
        ("configs/fixture.json", "{}\n"),
        ("data/fixture.json", "{}\n"),
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_launch_plan_is_epoch_specific_hashed_and_research_only(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    plan = build_canonical_launch_plan(
        _manifest(), project_root=tmp_path, epoch="epoch_20260830_100000_abcd"
    )
    spec = plan[0]
    assert spec.env["RESEARCH_STATION_EVIDENCE_EPOCH"] == "epoch_20260830_100000_abcd"
    assert spec.env["RESEARCH_ONLY"] == "true"
    assert spec.env["ORDER_AUTHORITY"] == "false"
    assert spec.runtime_dir == (
        tmp_path
        / "runtime/local_research_station/epochs/epoch_20260830_100000_abcd/fixture"
    )
    assert spec.argv[-2:] == ("--runtime-dir", str(spec.runtime_dir))
    assert spec.evidence_paths == (
        spec.runtime_dir / "decision.json",
        spec.runtime_dir / "ledger.jsonl",
    )
    assert set(spec.source_hashes) == {
        "scripts/fixture.sh",
        "configs/fixture.json",
        "data/fixture.json",
    }


def test_launch_plan_rejects_missing_hashed_source(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    (tmp_path / "data/fixture.json").unlink()
    with pytest.raises(MigrationError, match="missing launch identity path"):
        build_canonical_launch_plan(
            _manifest(), project_root=tmp_path, epoch="epoch_20260830_100000_abcd"
        )


def test_dry_run_launch_receipt_has_no_process_or_money_authority(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    plan = build_canonical_launch_plan(
        _manifest(), project_root=tmp_path, epoch="epoch_20260830_100000_abcd"
    )
    receipt = launch_canonical_jobs(plan, dry_run=True)
    assert receipt["authority"] == "research_only_no_live_or_promotion"
    for field in (
        "promotion_authority",
        "network_authority",
        "private_api_authority",
        "order_authority",
        "live_write_authority",
    ):
        assert receipt[field] is False
    assert receipt["jobs"][0]["state"] == "DRY_RUN"
    assert receipt["jobs"][0]["pid"] is None
    assert receipt["jobs"][0]["orders_sent"] is False
    assert set(receipt["orchestrator_hashes"]) == {
        "research_lab/canonical_station.py",
        "scripts/canonical_station_migration.py",
    }
    assert receipt["jobs"][0]["evidence_epoch"] == "epoch_20260830_100000_abcd"
    assert receipt["jobs"][0]["cwd"] == str(tmp_path.resolve())
    receipt_path = (
        tmp_path
        / "runtime/local_research_station/epochs/epoch_20260830_100000_abcd/launch_receipt.json"
    )
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["launch_sha256"]


def test_child_environment_does_not_inherit_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _materialize_fixture(tmp_path)
    spec = build_canonical_launch_plan(
        _manifest(), project_root=tmp_path, epoch="epoch_20260830_100000_abcd"
    )[0]
    monkeypatch.setenv("BYBIT_API_KEY", "must-not-leak")
    monkeypatch.setenv("MT5_TOKEN", "must-not-leak")

    child_env = _safe_child_environment(spec)

    assert "BYBIT_API_KEY" not in child_env
    assert "MT5_TOKEN" not in child_env
    assert child_env["PRIVATE_API_AUTHORITY"] == "false"
    assert child_env["PUBLIC_DATA_READ_AUTHORITY"] == "true"
    assert Path(child_env["HOME"]).is_relative_to(spec.runtime_dir)


def test_manual_hold_job_is_not_in_canonical_launch_plan(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    manifest = _manifest()
    manifest["jobs"][0]["migration_mode"] = "manual_hold"
    manifest["jobs"][0]["migration_blocked_reason"] = "fixture lacks parity adapter"

    assert build_canonical_launch_plan(
        manifest, project_root=tmp_path, epoch="epoch_20260830_100000_abcd"
    ) == ()


def test_missing_runtime_dependency_blocks_even_dry_run_receipt(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    manifest = _manifest()
    manifest["jobs"][0]["runtime_requirements"] = [".venv/bin/python"]
    plan = build_canonical_launch_plan(
        manifest, project_root=tmp_path, epoch="epoch_20260830_100000_abcd"
    )

    receipt = launch_canonical_jobs(plan, dry_run=True)

    assert receipt["jobs"][0]["state"] == "BLOCKED_RUNTIME"
    assert receipt["jobs"][0]["runtime_missing"] == [
        str(tmp_path / ".venv/bin/python")
    ]
    assert receipt["jobs"][0]["pid"] is None


def test_project_local_venv_symlink_is_valid_runtime_requirement(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    python_link = tmp_path / ".venv/bin/python"
    python_link.parent.mkdir(parents=True)
    python_link.symlink_to(Path(sys.executable))
    manifest = _manifest()
    manifest["jobs"][0]["runtime_requirements"] = [".venv/bin/python"]

    plan = build_canonical_launch_plan(
        manifest, project_root=tmp_path, epoch="epoch_20260830_100000_abcd"
    )
    receipt = launch_canonical_jobs(plan, dry_run=True)

    assert receipt["jobs"][0]["state"] == "DRY_RUN"
    assert receipt["jobs"][0]["runtime_missing"] == []


def test_supervisor_never_starts_canonical_job_with_missing_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = station.Job(
        "fixture",
        "canonical_fixture_deadbeef",
        ("canonical_fixture_deadbeef",),
        "scripts/fixture.sh --runtime-dir /tmp/epoch/fixture",
        str(tmp_path / "decision.json"),
        60,
        runtime_requirements=(tmp_path / ".venv/bin/python",),
        canonical=True,
    )
    monkeypatch.setattr(station, "_matching_sessions", lambda _job: [])
    monkeypatch.setattr(
        station,
        "_start",
        lambda _job: (_ for _ in ()).throw(AssertionError("must not launch")),
    )

    result = station.evaluate_job(job, now=0.0, start_missing=True)

    assert result["state"] == "blocked_runtime"
    assert result["launch"]["attempted"] is False
    assert result["runtime_missing"] == [str(tmp_path / ".venv/bin/python")]


def test_supervisor_canonical_child_environment_is_secret_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "epoch/fixture"
    job = station.Job(
        "fixture",
        "canonical_fixture_deadbeef",
        ("canonical_fixture_deadbeef",),
        "scripts/fixture.sh",
        str(runtime / "decision.json"),
        60,
        runtime_dir=runtime,
        authority_env=(("PRIVATE_API_AUTHORITY", "false"),),
        canonical=True,
    )
    monkeypatch.setenv("BYBIT_API_SECRET", "must-not-leak")

    child_env = station._canonical_child_environment(job)

    assert "BYBIT_API_SECRET" not in child_env
    assert child_env["PRIVATE_API_AUTHORITY"] == "false"
    assert child_env["HOME"] == str(runtime / "home")


def test_station_status_requires_exact_authority_and_factual_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime/local_research_station"
    monkeypatch.setattr(station, "ROOT", tmp_path)
    monkeypatch.setattr(station, "RUNTIME", runtime)
    monkeypatch.setattr(station, "STATUS_PATH", runtime / "status.json")
    monkeypatch.setattr(station, "JOBS", ())
    monkeypatch.setattr(station, "load_canonical_manifest", _manifest)
    monkeypatch.setattr(station, "jobs_from_manifest", lambda *args, **kwargs: ())
    monkeypatch.setattr(station, "_manifest_hashes", lambda *args, **kwargs: ({}, {}))
    monkeypatch.setenv("RESEARCH_STATION_EVIDENCE_EPOCH", "epoch_20260830_abcd")
    payload = station.run_cycle(start_missing=False)
    assert payload["authority"] == "research_only_no_live_or_promotion"
    assert payload["network_authority"] is False
    assert payload["private_api_authority"] is False
    assert payload["order_authority"] is False
    assert payload["live_write_authority"] is False
    assert payload["evidence_epoch"] == "epoch_20260830_abcd"
    assert payload["evidence_paths"] == []
    assert payload["source_hashes"] == {}
    assert payload["run_id_identities"] == {}


def test_manifest_jobs_route_supervisor_to_epoch_runtime(tmp_path: Path) -> None:
    _materialize_fixture(tmp_path)
    manifest = _manifest()
    jobs = station.jobs_from_manifest(
        manifest,
        epoch="epoch_20260830_100000_abcd",
        project_root=tmp_path,
    )

    assert len(jobs) == 1
    job = jobs[0]
    epoch_root = (
        tmp_path
        / "runtime/local_research_station/epochs/epoch_20260830_100000_abcd/fixture"
    )
    assert job.session.startswith("canonical_fixture_")
    assert job.session_markers == (job.session,)
    assert job.evidence == str(epoch_root / "decision.json")
    assert job.script == (
        f"{tmp_path / 'scripts/fixture.sh'} --runtime-dir {epoch_root}"
    )


def test_run_cycle_uses_manifest_jobs_when_epoch_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime/local_research_station"
    _materialize_fixture(tmp_path)
    manifest = _manifest()
    seen: list[station.Job] = []

    monkeypatch.setattr(station, "ROOT", tmp_path)
    monkeypatch.setattr(station, "RUNTIME", runtime)
    monkeypatch.setattr(station, "STATUS_PATH", runtime / "status.json")
    monkeypatch.setattr(station, "JOBS", ())
    monkeypatch.setattr(station, "load_canonical_manifest", lambda: manifest)
    monkeypatch.setenv("RESEARCH_STATION_EVIDENCE_EPOCH", "epoch_20260830_100000_abcd")

    def fake_evaluate(job: station.Job, *, now: float, start_missing: bool) -> dict:
        seen.append(job)
        return {
            "name": job.name,
            "state": "starting",
            "evidence_path": job.evidence,
        }

    monkeypatch.setattr(station, "evaluate_job", fake_evaluate)
    payload = station.run_cycle(start_missing=False)

    assert [job.name for job in seen] == ["fixture"]
    assert seen[0].evidence.startswith(str(runtime / "epochs/epoch_20260830_100000_abcd"))
    assert payload["evidence_epoch"] == "epoch_20260830_100000_abcd"
    assert payload["evidence_paths"] == [seen[0].evidence]


@pytest.mark.parametrize(
    ("script", "expected_relatives"),
    (
        (
            "scripts/run_alpaca_adaptive_shadow_loop.sh",
            {"cache", "shadow_latest.json", "shadow_latest.md", "shadow_ledger.jsonl", "loop.lock", "logs"},
        ),
        (
            "scripts/run_xsec_shadow_loop.sh",
            {"universe.json", "state.json", "decision_latest.json", "ledger.jsonl", "loop.lock", "logs"},
        ),
        (
            "scripts/run_funding_positioning_dynamic_shadow_loop.sh",
            {"universe.json", "state.json", "ledger.jsonl", "summary.json", "loop.lock", "logs/shadow.log"},
        ),
        (
            "scripts/run_funding_positioning_post_n42_frozen_loop.sh",
            {"state.json", "ledger.jsonl", "summary.json", "loop.lock", "logs/shadow.log"},
        ),
        (
            "scripts/run_inplay_prospective_shadow_loop.sh",
            {"collector.flock", "historical_frequency_startup_gate.json", "status.json", "ledger.jsonl", "logs/collector.log"},
        ),
        (
            "scripts/run_project_audit_supervisor.sh",
            {"run.lock", "supervisor_status.json", "registry.json", "registry.md", "registry.csv", "logs/supervisor.log"},
        ),
    ),
)
def test_loop_print_config_routes_every_write_under_epoch(
    script: str, expected_relatives: set[str], tmp_path: Path
) -> None:
    runtime = tmp_path / Path(script).stem
    result = subprocess.run(
        ["bash", script, "--runtime-dir", str(runtime), "--print-config"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["runtime_dir"]).resolve() == runtime.resolve()
    assert payload["authority"] == "research_only_no_live_or_promotion"
    assert payload["order_authority"] is False
    assert payload["public_data_read_authority"] is True
    assert payload["write_paths"]
    assert all(Path(path).resolve().is_relative_to(runtime.resolve()) for path in payload["write_paths"])
    assert {
        str(Path(path).resolve().relative_to(runtime.resolve()))
        for path in payload["write_paths"]
    } == expected_relatives


def test_project_audit_canonical_mode_is_manual_hold(tmp_path: Path) -> None:
    runtime = tmp_path / "project_audit"
    result = subprocess.run(
        [
            "bash",
            "scripts/run_project_audit_supervisor.sh",
            "--runtime-dir",
            str(runtime),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 3
    assert "MANUAL_HOLD" in result.stderr
