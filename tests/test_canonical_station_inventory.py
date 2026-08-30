import json
import subprocess
import sys
from pathlib import Path

from scripts.canonical_station_migration import (
    inventory_legacy_processes,
    parse_screen_sessions,
)


ROOT = Path(__file__).resolve().parents[1]


def _job() -> dict:
    return {
        "name": "xsec",
        "screen_session": "canonical_xsec",
        "legacy_session_markers": ["old_xsec"],
        "legacy_command_markers": ["run_xsec_shadow_loop.sh", "xsec_shadow_cycle.py"],
        "launcher": ["scripts/run_xsec_shadow_loop.sh"],
        "process_kind": "market_snapshot_loop",
        "evidence_paths": ["runtime/xsec/decision.json"],
        "source_paths": ["scripts/run_xsec_shadow_loop.sh"],
        "config_paths": ["configs/xsec.json"],
        "input_paths": [],
    }


def _manifest() -> dict:
    return {
        "authority": "research_only_no_live_or_promotion",
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "jobs": [_job()],
    }


def _identity_files(root: Path) -> dict[str, Path]:
    launcher = root / "scripts/run_xsec_shadow_loop.sh"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    config = root / "configs/xsec.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"risk": 0}\n', encoding="utf-8")
    return {
        "scripts/run_xsec_shadow_loop.sh": launcher,
        "configs/xsec.json": config,
    }


def test_parse_screen_sessions_ignores_dead_sockets() -> None:
    output = """There are screens on:
\t111.old_xsec\t(Detached)
\t222.old_funding\t(Dead ???)
1 Socket in /tmp/screens.
"""
    assert parse_screen_sessions(output) == ["old_xsec"]


def test_migration_cli_is_directly_executable_from_project_root() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/canonical_station_migration.py", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "canonical research station migration" in result.stdout


def test_inventory_records_confirmed_command_config_and_evidence_identity(tmp_path: Path) -> None:
    file_roots = _identity_files(tmp_path)
    artifact = tmp_path / "runtime/xsec/decision.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"decisions": 4, "healthy": true}\n', encoding="utf-8")
    file_roots["runtime/xsec/decision.json"] = artifact

    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t111.old_xsec\t(Detached)\n",
        ps_output="111 1 /bin/bash scripts/run_xsec_shadow_loop.sh --config configs/xsec.json",
        cwd_by_pid={111: str(tmp_path)},
        file_roots=file_roots,
        now_utc="2026-08-29T10:00:00Z",
    )

    row = result["processes"][0]
    assert row["status"] == "CONFIRMED"
    assert row["stop_allowed"] is False
    assert row["pid"] == 111
    assert row["cwd"] == str(tmp_path)
    assert row["identity"]["config_hashes"]["configs/xsec.json"]
    assert row["counters"] == {"decisions": 4}
    assert result["legacy_epoch"] == "legacy_2026-08-29T10:00:00Z"
    assert result["inventory_sha256"]


def test_inventory_prefers_screen_child_command_when_wrapper_has_no_launcher(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t111.old_xsec\t(Detached)\n",
        ps_output=(
            "111 1 SCREEN -dmS old_xsec\n"
            "112 111 /bin/bash scripts/run_xsec_shadow_loop.sh --config configs/xsec.json"
        ),
        cwd_by_pid={112: str(tmp_path)},
        file_roots=_identity_files(tmp_path),
        now_utc="2026-08-29T10:00:00Z",
    )
    row = result["processes"][0]
    assert row["pid"] == 112
    assert row["status"] == "CONFIRMED"


def test_inventory_keeps_launcher_process_when_its_child_is_only_sleep(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t111.old_xsec\t(Detached)\n",
        ps_output=(
            "111 1 /bin/bash scripts/run_xsec_shadow_loop.sh --config configs/xsec.json\n"
            "112 111 sleep 300"
        ),
        cwd_by_pid={111: str(tmp_path), 112: str(tmp_path)},
        file_roots=_identity_files(tmp_path),
        now_utc="2026-08-29T10:00:00Z",
    )
    row = result["processes"][0]
    assert row["pid"] == 111
    assert row["status"] == "CONFIRMED"


def test_inventory_accepts_explicit_legacy_python_command_marker(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t111.old_xsec\t(Detached)\n",
        ps_output="111 1 python scripts/xsec_shadow_cycle.py",
        cwd_by_pid={111: str(tmp_path)},
        file_roots=_identity_files(tmp_path),
        now_utc="2026-08-29T10:00:00Z",
    )
    assert result["processes"][0]["status"] == "CONFIRMED"


def test_unknown_command_is_not_confirmed_and_never_auto_stoppable(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t333.old_xsec\t(Detached)\n",
        ps_output="333 1 python unknown.py",
        cwd_by_pid={333: str(tmp_path)},
        file_roots=_identity_files(tmp_path),
        now_utc="2026-08-29T10:00:00Z",
    )
    row = result["processes"][0]
    assert row["status"] == "NOT_CONFIRMED"
    assert row["stop_allowed"] is False
    assert row["identity_reason"] == "command_or_config_identity_unrecoverable"


def test_missing_config_is_not_confirmed(tmp_path: Path) -> None:
    files = _identity_files(tmp_path)
    files.pop("configs/xsec.json").unlink()
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t444.old_xsec\t(Detached)\n",
        ps_output="444 1 /bin/bash scripts/run_xsec_shadow_loop.sh --config configs/xsec.json",
        cwd_by_pid={444: str(tmp_path)},
        file_roots=files,
        now_utc="2026-08-29T10:00:00Z",
    )
    assert result["processes"][0]["status"] == "NOT_CONFIRMED"


def test_inventory_receipt_does_not_store_environment_or_secret_values(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t555.old_xsec\t(Detached)\n",
        ps_output="555 1 /bin/bash scripts/run_xsec_shadow_loop.sh --config configs/xsec.json",
        cwd_by_pid={555: str(tmp_path)},
        file_roots=_identity_files(tmp_path),
        now_utc="2026-08-29T10:00:00Z",
    )
    serialized = json.dumps(result)
    assert "environment" not in serialized
    assert "API_KEY" not in serialized


def test_inventory_redacts_secret_bearing_command_and_fails_identity_closed(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t666.old_xsec\t(Detached)\n",
        ps_output="666 1 API_KEY=topsecret /bin/bash scripts/run_xsec_shadow_loop.sh",
        cwd_by_pid={666: str(tmp_path)},
        file_roots=_identity_files(tmp_path),
        now_utc="2026-08-29T10:00:00Z",
    )
    serialized = json.dumps(result)
    assert "topsecret" not in serialized
    assert result["processes"][0]["command"] == "<redacted_secret_bearing_command>"
    assert result["processes"][0]["status"] == "NOT_CONFIRMED"


def test_inventory_redacts_secret_cli_argument_and_fails_identity_closed(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest=_manifest(),
        screen_output="There are screens on:\n\t777.old_xsec\t(Detached)\n",
        ps_output="777 1 /bin/bash scripts/run_xsec_shadow_loop.sh --api-key topsecret",
        cwd_by_pid={777: str(tmp_path)},
        file_roots=_identity_files(tmp_path),
        now_utc="2026-08-29T10:00:00Z",
    )
    serialized = json.dumps(result)
    assert "topsecret" not in serialized
    assert result["processes"][0]["command"] == "<redacted_secret_bearing_command>"
    assert result["processes"][0]["status"] == "NOT_CONFIRMED"
