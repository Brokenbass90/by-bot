#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.canonical_station import (
    AUTHORITY,
    MigrationError,
    ParityState,
    ProcessKind,
    ProcessReceipt,
    atomic_write_json,
    canonical_screen_name,
    compare_collector_snapshots,
    compare_deterministic_receipts,
    compare_market_snapshot_receipts,
    identity_fingerprint,
    load_manifest,
    validate_authority_manifest,
)


_LIVE_SCREEN = re.compile(r"^\s*(?P<pid>\d+)\.(?P<name>[A-Za-z0-9_.-]+)\s+\(")
_EPOCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,63}")
_SECRET_COMMAND = re.compile(
    r"(?:^|\s)(?:"
    r"[A-Za-z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN|CREDENTIAL)[A-Za-z0-9_]*\s*="
    r"|--(?:api[-_]?key|secret|token|credential)(?:\s+|=)"
    r")",
    re.IGNORECASE,
)
_SAFE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
_SENSITIVE_ENV_NAME = re.compile(
    r"(?:api.?key|secret|token|credential|password|passwd|cookie|session|auth|account|private|webhook|dsn)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LaunchSpec:
    job_name: str
    screen_session: str
    argv: tuple[str, ...]
    cwd: Path
    runtime_dir: Path
    env: dict[str, str]
    evidence_paths: tuple[Path, ...]
    source_hashes: dict[str, str]
    identity_fingerprint: str
    runtime_requirements: tuple[Path, ...] = ()


def _launch_identity_hashes(job: Mapping[str, Any], root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for field in ("source_paths", "config_paths", "input_paths"):
        for logical_path in job.get(field, []):
            path = (root / logical_path).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise MigrationError(f"launch identity path escapes root: {logical_path}") from exc
            if not path.is_file():
                raise MigrationError(f"missing launch identity path: {logical_path}")
            hashes[logical_path] = _sha256_bytes(path.read_bytes())
    return dict(sorted(hashes.items()))


def build_canonical_launch_plan(
    manifest: Mapping[str, Any], *, project_root: Path, epoch: str
) -> tuple[LaunchSpec, ...]:
    validate_authority_manifest(manifest)
    if not _EPOCH.fullmatch(epoch):
        raise MigrationError("evidence_epoch must be a unique explicit identifier")
    root = project_root.resolve()
    epoch_root = root / str(manifest["canonical_runtime_root"]) / "epochs" / epoch
    plan: list[LaunchSpec] = []
    for job in manifest["jobs"]:
        if job.get("migration_mode", "canonical") != "canonical":
            continue
        runtime_dir = (epoch_root / str(job["name"])).resolve()
        try:
            runtime_dir.relative_to(epoch_root.resolve())
        except ValueError as exc:
            raise MigrationError(f"canonical runtime escapes epoch: {job['name']}") from exc
        launcher = (root / job["launcher"][0]).resolve()
        if not launcher.is_file():
            raise MigrationError(f"launcher does not exist: {launcher}")
        argv = tuple(
            [str(launcher), *[str(value) for value in job["launcher"][1:]]]
            + ["--runtime-dir", str(runtime_dir)]
        )
        source_hashes = _launch_identity_hashes(job, root)
        runtime_requirements = tuple(
            root / relative
            for relative in job.get("runtime_requirements", [])
        )
        for requirement in runtime_requirements:
            try:
                requirement.relative_to(root)
            except ValueError as exc:
                raise MigrationError(
                    f"runtime requirement escapes project root: {requirement}"
                ) from exc
        evidence_paths = tuple(
            runtime_dir / relative for relative in job["canonical_evidence_files"]
        )
        env = {
            "RESEARCH_STATION_EVIDENCE_EPOCH": epoch,
            "RESEARCH_ONLY": "true",
            "PROMOTION_AUTHORITY": "false",
            "NETWORK_AUTHORITY": "false",
            "PRIVATE_API_AUTHORITY": "false",
            "ORDER_AUTHORITY": "false",
            "LIVE_WRITE_AUTHORITY": "false",
            "PUBLIC_DATA_READ_AUTHORITY": "true",
        }
        identity = {
            "job_name": job["name"],
            "process_kind": job["process_kind"],
            "argv": list(argv),
            "evidence_epoch": epoch,
            "evidence_paths": [str(path) for path in evidence_paths],
            "source_hashes": source_hashes,
            "runtime_requirements": [str(path) for path in runtime_requirements],
        }
        plan.append(
            LaunchSpec(
                job_name=str(job["name"]),
                screen_session=canonical_screen_name(str(job["screen_session"]), epoch),
                argv=argv,
                cwd=root,
                runtime_dir=runtime_dir,
                env=env,
                evidence_paths=evidence_paths,
                source_hashes=source_hashes,
                identity_fingerprint=_sha256_canonical(identity),
                runtime_requirements=runtime_requirements,
            )
        )
    return tuple(plan)


def _validate_launch_spec_authority(spec: LaunchSpec) -> None:
    expected = {
        "RESEARCH_ONLY": "true",
        "PROMOTION_AUTHORITY": "false",
        "NETWORK_AUTHORITY": "false",
        "PRIVATE_API_AUTHORITY": "false",
        "ORDER_AUTHORITY": "false",
        "LIVE_WRITE_AUTHORITY": "false",
        "PUBLIC_DATA_READ_AUTHORITY": "true",
    }
    if any(spec.env.get(key) != value for key, value in expected.items()):
        raise MigrationError(f"unsafe launch authority for {spec.job_name}")


def _safe_child_environment(spec: LaunchSpec) -> dict[str, str]:
    """Build a secret-free child environment; canonical jobs never inherit host env."""
    _validate_launch_spec_authority(spec)
    return {
        "PATH": _SAFE_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "HOME": str(spec.runtime_dir / "home"),
        "TMPDIR": str(spec.runtime_dir / "tmp"),
        **spec.env,
    }


def _screen_control_environment() -> dict[str, str]:
    """Keep Screen's native HOME/TMP socket contract without leaking credentials."""
    return {
        key: value
        for key, value in os.environ.items()
        if not _SENSITIVE_ENV_NAME.search(key) and not key.upper().endswith("_JSON")
    }


def launch_canonical_jobs(
    plan: Sequence[LaunchSpec], *, dry_run: bool
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in plan:
        _validate_launch_spec_authority(spec)
        runtime_missing = [
            str(path)
            for path in spec.runtime_requirements
            if not path.is_file() or not os.access(path, os.X_OK)
        ]
        row = {
            "job_name": spec.job_name,
            "screen_session": spec.screen_session,
            "runtime_dir": str(spec.runtime_dir),
            "argv": list(spec.argv),
            "evidence_paths": [str(path) for path in spec.evidence_paths],
            "source_hashes": spec.source_hashes,
            "identity_fingerprint": spec.identity_fingerprint,
            "evidence_epoch": spec.env["RESEARCH_STATION_EVIDENCE_EPOCH"],
            "cwd": str(spec.cwd),
            "pid": None,
            "orders_sent": False,
            "private_api_calls": False,
            "live_write_authority": False,
            "public_data_read_authority": True,
            "runtime_requirements": [str(path) for path in spec.runtime_requirements],
            "runtime_missing": runtime_missing,
        }
        if runtime_missing:
            row["state"] = "BLOCKED_RUNTIME"
            row["returncode"] = None
        elif dry_run:
            row["state"] = "DRY_RUN"
            row["returncode"] = None
        else:
            spec.runtime_dir.mkdir(parents=True, exist_ok=False)
            (spec.runtime_dir / "home").mkdir()
            (spec.runtime_dir / "tmp").mkdir()
            child_env = _safe_child_environment(spec)
            completed = subprocess.run(
                [
                    "screen",
                    "-dmS",
                    spec.screen_session,
                    "/usr/bin/env",
                    "-i",
                    *[f"{key}={value}" for key, value in sorted(child_env.items())],
                    "/bin/bash",
                    *spec.argv,
                ],
                cwd=spec.cwd,
                env=_screen_control_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            session_pid = None
            if completed.returncode == 0:
                screen_result = subprocess.run(
                    ["screen", "-ls"],
                    cwd=spec.cwd,
                    env=_screen_control_environment(),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                session_pid = _screen_pid_map(screen_result.stdout).get(spec.screen_session)
            row["pid"] = session_pid
            row["state"] = (
                "STARTED"
                if completed.returncode == 0 and session_pid is not None
                else "FAIL_CLOSED"
            )
            row["returncode"] = completed.returncode
            row["stderr"] = completed.stderr[-500:]
        rows.append(row)
    orchestrator_paths = {
        "research_lab/canonical_station.py": ROOT / "research_lab/canonical_station.py",
        "scripts/canonical_station_migration.py": Path(__file__).resolve(),
    }
    receipt = {
        "schema_id": "canonical_station_launch_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "public_data_read_authority": True,
        "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dry_run": bool(dry_run),
        "orchestrator_hashes": {
            name: _sha256_bytes(path.read_bytes())
            for name, path in orchestrator_paths.items()
        },
        "jobs": rows,
    }
    receipt["launch_sha256"] = _sha256_canonical(receipt)
    if plan:
        receipt_path = plan[0].runtime_dir.parent / "launch_receipt.json"
        atomic_write_json(receipt_path, receipt)
    return receipt


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_canonical(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return _sha256_bytes(payload.encode("utf-8"))


def _screen_pid_map(output: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in str(output or "").splitlines():
        lowered = raw.lower()
        if "dead" in lowered or "remove dead screens" in lowered:
            continue
        match = _LIVE_SCREEN.match(raw)
        if match:
            result[match.group("name")] = int(match.group("pid"))
    return result


def parse_screen_sessions(output: str) -> list[str]:
    return sorted(_screen_pid_map(output))


def _resolve_session_process(
    session: str,
    ps_output: str,
    *,
    pid_hint: int | None = None,
    command_markers: Sequence[str] = (),
) -> tuple[int | None, str]:
    rows: list[tuple[int, int, str]] = []
    for raw in str(ps_output or "").splitlines():
        fields = raw.strip().split(None, 2)
        if len(fields) != 3:
            continue
        try:
            rows.append((int(fields[0]), int(fields[1]), fields[2]))
        except ValueError:
            continue
    if pid_hint is not None:
        by_pid = {row[0]: row for row in rows}
        descendants: list[tuple[int, tuple[int, int, str]]] = []
        frontier = [(0, pid_hint)]
        seen: set[int] = set()
        while frontier:
            depth, candidate_pid = frontier.pop(0)
            if candidate_pid in seen:
                continue
            seen.add(candidate_pid)
            row = by_pid.get(candidate_pid)
            if row is not None:
                descendants.append((depth, row))
            frontier.extend(
                (depth + 1, child[0]) for child in rows if child[1] == candidate_pid
            )
        if command_markers:
            matching = [
                (depth, row)
                for depth, row in descendants
                if any(marker in row[2] for marker in command_markers)
            ]
            if matching:
                _depth, selected = min(matching, key=lambda item: (item[0], item[1][0]))
                return selected[0], selected[2]
        child = next((row for row in rows if row[1] == pid_hint), None)
        if child is not None:
            return child[0], child[2]
        exact = next((row for row in rows if row[0] == pid_hint), None)
        if exact is not None:
            return exact[0], exact[2]
    marker = f".{session}"
    matched = next((row for row in rows if marker in row[2]), None)
    return (matched[0], matched[2]) if matched is not None else (None, "")


def _session_matches(session: str, marker: str) -> bool:
    return session == marker or session.startswith(f"{marker}_")


def _job_for_session(
    manifest: Mapping[str, Any], session: str
) -> Mapping[str, Any] | None:
    matches = [
        job
        for job in manifest.get("jobs", [])
        if any(
            _session_matches(session, marker)
            for marker in job.get("legacy_session_markers", [])
            if isinstance(marker, str)
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _path_for(
    logical_path: str,
    *,
    file_roots: Mapping[str, Path],
    cwd: str | None,
) -> Path | None:
    supplied = file_roots.get(logical_path)
    if supplied is not None:
        return Path(supplied)
    return Path(cwd) / logical_path if cwd else None


def _hash_group(
    paths: Sequence[str], *, file_roots: Mapping[str, Path], cwd: str | None
) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for logical_path in paths:
        path = _path_for(logical_path, file_roots=file_roots, cwd=cwd)
        if path is None or not path.is_file():
            missing.append(logical_path)
            continue
        hashes[logical_path] = _sha256_bytes(path.read_bytes())
    return hashes, missing


def _evidence_rows(
    paths: Sequence[str], *, file_roots: Mapping[str, Path], cwd: str | None
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for logical_path in paths:
        path = _path_for(logical_path, file_roots=file_roots, cwd=cwd)
        if path is None or not path.is_file():
            rows.append(
                {
                    "path": logical_path,
                    "resolved_path": str(path.resolve()) if path is not None else None,
                    "state": "MISSING",
                    "sha256": None,
                    "size_bytes": None,
                }
            )
            continue
        payload = path.read_bytes()
        rows.append(
            {
                "path": logical_path,
                "resolved_path": str(path.resolve()),
                "state": "PRESENT",
                "sha256": _sha256_bytes(payload),
                "size_bytes": len(payload),
            }
        )
        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(decoded, dict):
            counters.update(
                {
                    key: value
                    for key, value in decoded.items()
                    if isinstance(value, int) and not isinstance(value, bool)
                }
            )
    return rows, dict(sorted(counters.items()))


def _build_process_receipt(
    manifest: Mapping[str, Any],
    session: str,
    screen_pid: int | None,
    pid: int | None,
    command: str,
    cwd_by_pid: Mapping[int, str],
    file_roots: Mapping[str, Path],
    now_utc: str,
) -> dict[str, Any]:
    job = _job_for_session(manifest, session)
    cwd = cwd_by_pid.get(pid) if pid is not None else None
    secret_bearing = bool(_SECRET_COMMAND.search(command))
    safe_command = "<redacted_secret_bearing_command>" if secret_bearing else command
    source_hashes: dict[str, str] = {}
    config_hashes: dict[str, str] = {}
    input_hashes: dict[str, str] = {}
    missing_identity: list[str] = []
    evidence: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    command_matches = False
    if job is not None:
        source_hashes, missing_sources = _hash_group(
            job.get("source_paths", []), file_roots=file_roots, cwd=cwd
        )
        config_hashes, missing_configs = _hash_group(
            job.get("config_paths", []), file_roots=file_roots, cwd=cwd
        )
        input_hashes, missing_inputs = _hash_group(
            job.get("input_paths", []), file_roots=file_roots, cwd=cwd
        )
        missing_identity = sorted(missing_sources + missing_configs + missing_inputs)
        evidence, counters = _evidence_rows(
            job.get("evidence_paths", []), file_roots=file_roots, cwd=cwd
        )
        command_matches = any(
            marker in command for marker in job.get("legacy_command_markers", [])
        )
    confirmed = bool(
        job is not None
        and pid is not None
        and cwd
        and command_matches
        and not secret_bearing
        and not missing_identity
    )
    identity: dict[str, Any] = {
        "launcher": job.get("launcher", [None])[0] if job else None,
        "legacy_command_markers": job.get("legacy_command_markers", []) if job else [],
        "process_kind": job.get("process_kind") if job else None,
        "source_hashes": source_hashes,
        "config_hashes": config_hashes,
        "input_hashes": input_hashes,
        "missing_identity_paths": missing_identity,
    }
    identity["fingerprint"] = _sha256_canonical(identity)
    return {
        "job_name": job.get("name") if job else None,
        "screen_name": session,
        "screen_pid": screen_pid,
        "pid": pid,
        "cwd": cwd,
        "command": safe_command,
        "status": "CONFIRMED" if confirmed else "NOT_CONFIRMED",
        "stop_allowed": False,
        "eligible_for_parity": confirmed,
        "identity_reason": (
            "confirmed" if confirmed else "command_or_config_identity_unrecoverable"
        ),
        "identity": identity,
        "evidence": evidence,
        "counters": counters,
        "observed_at_utc": now_utc,
    }


def inventory_legacy_processes(
    *,
    manifest: Mapping[str, Any],
    screen_output: str,
    ps_output: str,
    cwd_by_pid: Mapping[int, str],
    file_roots: Mapping[str, Path],
    now_utc: str,
) -> dict[str, Any]:
    pid_by_session = _screen_pid_map(screen_output)
    processes = []
    for session in sorted(pid_by_session):
        job = _job_for_session(manifest, session)
        markers = tuple(job.get("legacy_command_markers", ())) if job is not None else ()
        pid, command = _resolve_session_process(
            session,
            ps_output,
            pid_hint=pid_by_session[session],
            command_markers=markers,
        )
        processes.append(
            _build_process_receipt(
                manifest,
                session,
                pid_by_session.get(session),
                pid,
                command,
                cwd_by_pid,
                file_roots,
                now_utc,
            )
        )
    receipt = {
        "schema_id": "canonical_station_legacy_inventory_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "public_data_read_authority": True,
        "legacy_epoch": f"legacy_{now_utc}",
        "observed_at_utc": now_utc,
        "fresh": True,
        "processes": processes,
    }
    receipt["inventory_sha256"] = _sha256_canonical(receipt)
    return receipt


def write_inventory_receipt(path: Path, receipt: Mapping[str, Any]) -> Path:
    atomic_write_json(path, receipt)
    return path


def _cwd_for_pid(pid: int) -> str | None:
    result = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        check=False,
        capture_output=True,
        text=True,
    )
    return next(
        (line[1:] for line in result.stdout.splitlines() if line.startswith("n/")),
        None,
    )


def _inventory_command(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    legacy_root = Path(args.legacy_root).resolve()
    manifest = load_manifest(Path(args.manifest), project_root=project_root)
    if not legacy_root.is_dir():
        raise MigrationError(f"legacy root does not exist: {legacy_root}")
    if not _EPOCH.fullmatch(args.evidence_epoch):
        raise MigrationError("evidence epoch is invalid")
    screen_result = subprocess.run(
        ["screen", "-ls"], check=False, capture_output=True, text=True
    )
    ps_result = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    pid_map = _screen_pid_map(screen_result.stdout)
    resolved_pids: set[int] = set()
    for session, screen_pid in pid_map.items():
        job = _job_for_session(manifest, session)
        markers = tuple(job.get("legacy_command_markers", ())) if job is not None else ()
        resolved_pid, _command = _resolve_session_process(
            session,
            ps_result.stdout,
            pid_hint=screen_pid,
            command_markers=markers,
        )
        if resolved_pid is not None:
            resolved_pids.add(resolved_pid)
    cwd_by_pid = {
        pid: cwd
        for pid in resolved_pids
        if (cwd := _cwd_for_pid(pid)) is not None
    }
    logical_paths = {
        path
        for job in manifest["jobs"]
        for field in ("evidence_paths", "source_paths", "config_paths", "input_paths")
        for path in job.get(field, [])
    }
    file_roots = {path: legacy_root / path for path in logical_paths}
    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    receipt = inventory_legacy_processes(
        manifest=manifest,
        screen_output=screen_result.stdout,
        ps_output=ps_result.stdout,
        cwd_by_pid=cwd_by_pid,
        file_roots=file_roots,
        now_utc=now_utc,
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else project_root
        / manifest["canonical_runtime_root"]
        / "migrations"
        / args.evidence_epoch
        / "legacy_inventory.json"
    )
    try:
        output.relative_to(legacy_root)
    except ValueError:
        pass
    else:
        raise MigrationError("inventory output cannot be inside legacy root")
    write_inventory_receipt(output, receipt)
    print(
        json.dumps(
            {
                "output": str(output),
                "processes": len(receipt["processes"]),
                "inventory_sha256": receipt["inventory_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# Task 5: guarded migration orchestration

_REQUIRED_RECEIPT_AUTHORITY = (
    "promotion_authority", "network_authority", "private_api_authority",
    "order_authority", "live_write_authority",
)
_FACTUAL_AUTHORITY = (
    "research_only", "live_order_authority", "orders_sent",
    "private_api_calls", "capital_authorized", "broker_authority",
    "money_authority",
)
_SAFE_SCREEN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")
_MIGRATION_RECEIPT_MAX_AGE_SECONDS = 300
_SAFE_TRUE_RECEIPT_FIELDS = {
    "public_data_read_authority",
    "research_only",
    "stop_allowed",
    "fresh",
    "heartbeat_fresh",
    "evidence_fresh",
    "completion_valid",
    "dry_run",
    "eligible_for_parity",
}
_KNOWN_CAPABILITY_FIELDS = {
    "authority",
    "authorization_sha256",
    "authorized_jobs",
    "authorized_screens",
    "public_data_read_authority",
    *_REQUIRED_RECEIPT_AUTHORITY,
    *_FACTUAL_AUTHORITY,
    *_SAFE_TRUE_RECEIPT_FIELDS,
}
_CAPABILITY_FIELD = re.compile(
    r"(?:author|allow|enable|order|trade|buy|sell|write|private|money|capital|broker|execute|live)",
    re.IGNORECASE,
)
_AUTHORITY_SHAPE_FIELDS = {
    "authority",
    "public_data_read_authority",
    *_REQUIRED_RECEIPT_AUTHORITY,
    *_FACTUAL_AUTHORITY,
}
_TOP_LEVEL_RECEIPT_FIELDS: dict[str, set[str]] = {
    "canonical_station_legacy_inventory_v1": {
        "schema_id", *_AUTHORITY_SHAPE_FIELDS, "legacy_epoch", "observed_at_utc",
        "fresh", "processes", "inventory_sha256",
    },
    "canonical_station_launch_v1": {
        "schema_id", *_AUTHORITY_SHAPE_FIELDS, "observed_at_utc", "dry_run",
        "orchestrator_hashes", "jobs", "launch_sha256",
    },
    "canonical_station_parity_v1": {
        "schema_id", *_AUTHORITY_SHAPE_FIELDS, "state", "stop_allowed", "reason",
        "launch_sha256", "inventory_sha256", "observed_at_utc", "fresh",
        "heartbeat_fresh", "evidence_fresh", "authorized_screens", "jobs",
        "parity_sha256",
    },
    "canonical_station_migration_authorization_v1": {
        "schema_id", *_AUTHORITY_SHAPE_FIELDS, "state", "manifest_sha256",
        "inventory_sha256", "launch_sha256", "parity_sha256",
        "authorized_screens", "authorized_jobs", "observed_at_utc",
        "authorization_sha256",
    },
}
_INVENTORY_ROW_FIELDS = {
    "job_name", "screen_name", "screen_pid", "pid", "cwd", "command",
    "process_kind", "status", "stop_allowed", "eligible_for_parity",
    "identity_reason", "identity", "evidence", "counters", "timestamps",
    "observed_at_utc", "evidence_paths", "evidence_epoch",
}
_LAUNCH_ROW_FIELDS = {
    "job_name", "screen_session", "runtime_dir", "argv", "evidence_paths",
    "source_hashes", "identity_fingerprint", "evidence_epoch", "cwd", "pid",
    "orders_sent", "private_api_calls", "live_write_authority",
    "public_data_read_authority", "runtime_requirements", "runtime_missing",
    "state", "returncode", "stderr",
}
_PARITY_JOB_FIELDS = {
    "job_name", "canonical_screen_session", "state", "stop_allowed", "fresh",
    "heartbeat_fresh", "evidence_fresh", "completion_valid", "observed_at_utc",
    "process_kind", "comparator", "comparator_state", "compared_fields",
    "legacy_identity_fingerprint", "canonical_identity_fingerprint", "heartbeat",
    "evidence",
}
_PROOF_FIELDS = {"state", "fresh", "observed_at_utc", "payload", "sha256"}
_HEARTBEAT_PAYLOAD_FIELDS = {
    "job_name", "canonical_screen_session", "canonical_pid", "evidence_epoch",
    "state", "observed_at_utc",
}
_EVIDENCE_PAYLOAD_FIELDS = {
    "job_name", "process_kind", "legacy_identity_fingerprint",
    "canonical_identity_fingerprint", "compared_fields", "comparator_reason",
    "legacy_receipt", "canonical_receipt", "closed_source_ts", "state",
    "observed_at_utc",
}
_PROCESS_RECEIPT_FIELDS = {
    "job_name", "screen_name", "pid", "cwd", "command", "process_kind",
    "status", "stop_allowed", "eligible_for_parity", "identity", "counters",
    "timestamps", "evidence_paths", "evidence_epoch", "authority",
}
_EVIDENCE_ROW_FIELDS = {
    "path", "resolved_path", "state", "sha256", "size_bytes",
}


def _require_only_fields(
    payload: Mapping[str, Any], allowed: set[str], *, context: str
) -> None:
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise MigrationError(f"unknown {context} field: " + ",".join(unknown))


def _reject_unknown_truthy_receipt_fields(payload: Mapping[str, Any]) -> None:
    suspicious = sorted(
        str(key)
        for key, value in payload.items()
        if key not in _KNOWN_CAPABILITY_FIELDS
        and (value is True or _CAPABILITY_FIELD.search(str(key)))
    )
    if suspicious:
        raise MigrationError(
            "unknown receipt authority claim: " + ",".join(suspicious)
        )


def _payload_hash(payload: Mapping[str, Any], hash_field: str) -> str:
    """Hash a receipt without its self-referential hash field."""
    body = {key: value for key, value in payload.items() if key != hash_field}
    return _sha256_canonical(body)


def _bind_receipt(payload: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    bound = dict(payload)
    supplied = bound.get(hash_field)
    if supplied is not None:
        if supplied != _payload_hash(bound, hash_field):
            raise MigrationError(f"{hash_field} hash mismatch")
    else:
        bound[hash_field] = _payload_hash(bound, hash_field)
    return bound


def _require_bound_receipt(payload: Mapping[str, Any], hash_field: str) -> None:
    """Validate a supplied receipt; unlike _bind_receipt, never mint a hash."""
    supplied = payload.get(hash_field)
    if not isinstance(supplied, str) or supplied != _payload_hash(payload, hash_field):
        raise MigrationError(f"{hash_field} hash mismatch or missing (hash-bound receipt required)")


def process_receipt_from_mapping(
    row: Mapping[str, Any], *, authority: Mapping[str, Any] | None = None
) -> ProcessReceipt:
    """Adapt an inventory/evidence mapping into the canonical typed receipt.

    This is intentionally explicit: raw ``screen``/``ps`` rows are not parity
    inputs until they carry command/config/input hashes and factual evidence.
    """
    raw_authority = authority or row.get("authority")
    if not isinstance(raw_authority, Mapping):
        raise MigrationError("process receipt authority is missing")
    _validate_receipt_authority(raw_authority)
    kind = row.get("process_kind") or row.get("identity", {}).get("process_kind")
    try:
        process_kind = kind if isinstance(kind, ProcessKind) else ProcessKind(str(kind))
    except (TypeError, ValueError) as exc:
        raise MigrationError("process receipt process kind is unknown") from exc
    status = row.get("status", "NOT_CONFIRMED")
    raw_status = status.value if isinstance(status, ParityState) else str(status)
    eligible = bool(row.get("eligible_for_parity", False))
    stop_allowed = row.get("stop_allowed") is True
    try:
        if raw_status == "CONFIRMED" and eligible and stop_allowed:
            parity_status = ParityState.PASS
        elif raw_status in {"CONFIRMED", "NOT_CONFIRMED"}:
            parity_status = ParityState.NOT_CONFIRMED
        else:
            parity_status = ParityState(raw_status)
    except ValueError as exc:
        raise MigrationError("process receipt status is unknown") from exc
    identity = row.get("identity")
    if not isinstance(identity, Mapping):
        raise MigrationError("process receipt identity is missing")
    evidence_paths = row.get("evidence_paths") or tuple(
        item.get("path") for item in row.get("evidence", [])
        if isinstance(item, Mapping) and item.get("path")
    )
    if not evidence_paths:
        raise MigrationError("process receipt evidence paths are missing")
    job_name = row.get("job_name")
    screen_name = row.get("screen_name")
    command = row.get("command")
    if not isinstance(job_name, str) or not job_name:
        raise MigrationError("process receipt job name is missing")
    if not isinstance(screen_name, str) or not _SAFE_SCREEN_NAME.fullmatch(screen_name):
        raise MigrationError("process receipt screen name is invalid")
    if not isinstance(command, str) or not command.strip() or _SECRET_COMMAND.search(command):
        raise MigrationError("process receipt command is missing or secret-bearing")
    receipt = ProcessReceipt(
        job_name=job_name,
        screen_name=screen_name,
        pid=row.get("pid"),
        cwd=row.get("cwd"),
        command=command,
        process_kind=process_kind,
        identity=dict(identity),
        counters=dict(row.get("counters") or {}),
        timestamps=dict(row.get("timestamps") or {"observed_at_utc": str(row.get("observed_at_utc") or "")}),
        evidence_paths=tuple(str(path) for path in evidence_paths),
        evidence_epoch=row.get("evidence_epoch"),
        authority=dict(raw_authority),
        status=parity_status,
        eligible_for_parity=eligible,
    )
    # A CONFIRMED inventory row is accepted only if it independently satisfies
    # the same typed comparator contract used by Task 4.  Comparing a receipt
    # with itself validates mandatory immutable identity/economic fields without
    # inventing facts from raw evidence.
    if parity_status is ParityState.PASS:
        comparator = {
            ProcessKind.DETERMINISTIC: compare_deterministic_receipts,
            ProcessKind.MARKET_SNAPSHOT: compare_market_snapshot_receipts,
            ProcessKind.COLLECTOR: compare_collector_snapshots,
        }[process_kind]
        verdict = comparator(receipt, receipt)
        if verdict.state is not ParityState.PASS or verdict.stop_allowed is not True:
            raise MigrationError(verdict.reason)
    identity_fingerprint(receipt)
    return receipt


def legacy_inventory_to_process_receipts(
    inventory: Mapping[str, Any],
) -> tuple[ProcessReceipt, ...]:
    """Adapt every real legacy inventory row, preserving NOT_CONFIRMED rows."""
    authority = _authority_claims(inventory)
    rows = inventory.get("processes")
    if not isinstance(rows, list):
        raise MigrationError("legacy inventory processes are missing")
    return tuple(process_receipt_from_mapping(row, authority=authority) for row in rows)


# Short alias kept for callers that describe the operation as an adapter.
adapt_legacy_inventory = legacy_inventory_to_process_receipts


def _receipt_authority(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("authority")
    if isinstance(nested, Mapping):
        # A nested authority object is the canonical parity receipt shape.
        return nested
    return payload


def _authority_claims(payload: Mapping[str, Any]) -> dict[str, Any]:
    authority = _receipt_authority(payload)
    known = {
        "authority", "public_data_read_authority", *_REQUIRED_RECEIPT_AUTHORITY,
        *_FACTUAL_AUTHORITY,
    }
    return {key: authority[key] for key in known if key in authority}


def _validate_receipt_authority(payload: Mapping[str, Any]) -> None:
    schema_id = payload.get("schema_id")
    if schema_id is None:
        _require_only_fields(payload, _AUTHORITY_SHAPE_FIELDS, context="authority")
    else:
        allowed = _TOP_LEVEL_RECEIPT_FIELDS.get(str(schema_id))
        if allowed is None:
            raise MigrationError("unknown stop-eligible receipt schema")
        _require_only_fields(payload, allowed, context=str(schema_id))
    known_claims = {
        "authority", "public_data_read_authority", *_REQUIRED_RECEIPT_AUTHORITY,
        *_FACTUAL_AUTHORITY,
    }
    nested = payload.get("authority")
    if isinstance(nested, Mapping):
        _require_only_fields(nested, _AUTHORITY_SHAPE_FIELDS, context="nested authority")
    authority = nested if isinstance(nested, Mapping) else payload
    if authority.get("authority") != AUTHORITY:
        raise MigrationError("receipt authority drift")
    expected = {
        **{key: False for key in _REQUIRED_RECEIPT_AUTHORITY},
        "public_data_read_authority": True,
    }
    for source in (authority, payload):
        if not isinstance(source, Mapping):
            raise MigrationError("receipt authority drift")
        for key, value in expected.items():
            if key in source and source[key] is not value:
                raise MigrationError("receipt authority drift")
        if source is authority and any(key not in source for key in expected):
            raise MigrationError("receipt authority drift")
        if "research_only" in source and source["research_only"] is not True:
            raise MigrationError("receipt authority drift")
        for key in _FACTUAL_AUTHORITY:
            if key != "research_only" and key in source and source[key] is not False:
                raise MigrationError("receipt authority drift")
        _reject_unknown_truthy_receipt_fields(source)
    if isinstance(nested, Mapping):
        unknown_nested = sorted(set(nested) - known_claims)
        if unknown_nested:
            raise MigrationError(
                "unknown receipt authority claim: " + ",".join(unknown_nested)
            )


def _state_value(payload: Mapping[str, Any]) -> str:
    value = payload.get("state", payload.get("status"))
    return value.value if hasattr(value, "value") else str(value)


def _fresh_and_complete(payload: Mapping[str, Any]) -> bool:
    """Reject stale, missing, or explicitly incomplete evidence at the stop gate."""
    for key in ("fresh", "heartbeat_fresh", "evidence_fresh"):
        if payload.get(key) is not True:
            return False
    if "completion_valid" in payload and payload["completion_valid"] is not True:
        return False
    for key in ("stale", "missing", "authority_drift", "hash_mismatch"):
        if payload.get(key) is True:
            return False
    for key in ("heartbeat", "evidence"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            if value.get("fresh") is False or value.get("state") in {"MISSING", "STALE", "FAIL_CLOSED"}:
                return False
    return True


def _receipt_timestamp_is_fresh(
    payload: Mapping[str, Any], *, max_age_seconds: int = _MIGRATION_RECEIPT_MAX_AGE_SECONDS
) -> bool:
    raw = payload.get("observed_at_utc") or payload.get("generated_at_utc")
    parsed = _parse_whole_second_utc(raw)
    if parsed is None:
        return False
    age = (datetime.now(timezone.utc) - parsed).total_seconds()
    return -5 <= age <= max_age_seconds


def _parse_whole_second_utc(raw: Any) -> datetime | None:
    """Parse the exact timestamp format accepted by migration receipts."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.microsecond != 0
    ):
        return None
    return parsed.astimezone(timezone.utc)


def _inventory_identity_is_safe(inventory: Mapping[str, Any]) -> bool:
    try:
        if inventory.get("schema_id") != "canonical_station_legacy_inventory_v1":
            raise MigrationError("legacy inventory schema mismatch")
        _validate_receipt_authority(inventory)
        _require_bound_receipt(inventory, "inventory_sha256")
        if inventory.get("fresh", True) is not True or not _receipt_timestamp_is_fresh(inventory):
            raise MigrationError("legacy inventory is stale")
        rows = inventory.get("processes")
        if not isinstance(rows, list) or not rows:
            raise MigrationError("legacy inventory has no process rows")
        jobs: list[str] = []
        screens: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise MigrationError("legacy inventory row is malformed")
            _require_only_fields(row, _INVENTORY_ROW_FIELDS, context="inventory row")
            _reject_unknown_truthy_receipt_fields(row)
            job_name = row.get("job_name")
            screen_name = row.get("screen_name")
            screen_pid = row.get("screen_pid")
            pid = row.get("pid")
            identity = row.get("identity")
            command = row.get("command")
            cwd = row.get("cwd")
            kind = row.get("process_kind") or (
                identity.get("process_kind") if isinstance(identity, Mapping) else None
            )
            if (
                not isinstance(job_name, str)
                or not job_name
                or not isinstance(screen_name, str)
                or not _SAFE_SCREEN_NAME.fullmatch(screen_name)
                or not isinstance(screen_pid, int)
                or isinstance(screen_pid, bool)
                or screen_pid <= 0
                or not isinstance(pid, int)
                or isinstance(pid, bool)
                or pid <= 0
                or not isinstance(cwd, str)
                or not cwd
                or not isinstance(command, str)
                or not command.strip()
                or _SECRET_COMMAND.search(command)
                or row.get("status") != "CONFIRMED"
                or row.get("eligible_for_parity") is not True
                or not isinstance(row.get("stop_allowed"), bool)
                or str(kind) not in {item.value for item in ProcessKind}
                or not isinstance(identity, Mapping)
            ):
                raise MigrationError("legacy inventory contains unresolved process identity")
            fingerprint = identity.get("fingerprint")
            identity_body = {key: value for key, value in identity.items() if key != "fingerprint"}
            if (
                not isinstance(fingerprint, str)
                or fingerprint != _sha256_canonical(identity_body)
                or identity.get("missing_identity_paths", []) not in ([], ())
            ):
                raise MigrationError("legacy inventory identity fingerprint mismatch")
            for aliases in (
                ("source_hash", "source_hashes"),
                ("config_hash", "config_hashes"),
                ("input_hash", "input_hashes"),
            ):
                values = [identity[key] for key in aliases if key in identity]
                if not values:
                    raise MigrationError("legacy inventory immutable hashes are missing")
                value = values[0]
                if isinstance(value, str):
                    valid = re.fullmatch(r"[0-9a-f]{64}", value) is not None
                else:
                    valid = (
                        isinstance(value, Mapping)
                        and bool(value)
                        and all(
                            isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item)
                            for item in value.values()
                        )
                    )
                if not valid:
                    raise MigrationError("legacy inventory immutable hash is malformed")
            evidence = row.get("evidence")
            evidence_paths = row.get("evidence_paths")
            if isinstance(evidence, list):
                for item in evidence:
                    if isinstance(item, Mapping):
                        _require_only_fields(
                            item, _EVIDENCE_ROW_FIELDS, context="inventory evidence row"
                        )
                if not evidence or not all(
                    isinstance(item, Mapping)
                    and item.get("state") == "PRESENT"
                    and isinstance(item.get("path"), str)
                    and bool(item.get("path"))
                    and isinstance(item.get("resolved_path"), str)
                    and Path(str(item.get("resolved_path"))).is_absolute()
                    and isinstance(item.get("sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256")))
                    and isinstance(item.get("size_bytes"), int)
                    and not isinstance(item.get("size_bytes"), bool)
                    and item.get("size_bytes") >= 0
                    for item in evidence
                ):
                    raise MigrationError("legacy inventory evidence is incomplete")
            elif not (
                isinstance(evidence_paths, list)
                and evidence_paths
                and all(isinstance(path, str) and path for path in evidence_paths)
            ):
                raise MigrationError("legacy inventory evidence is missing")
            jobs.append(job_name)
            screens.append(screen_name)
        if len(jobs) != len(set(jobs)) or len(screens) != len(set(screens)):
            raise MigrationError("legacy inventory contains duplicate process scope")
    except MigrationError:
        return False
    return True


def _parity_is_stop_eligible(parity: Mapping[str, Any]) -> bool:
    try:
        _validate_receipt_authority(parity)
        _require_bound_receipt(parity, "parity_sha256")
    except MigrationError:
        return False
    jobs = parity.get("jobs")
    return (
        parity.get("schema_id") == "canonical_station_parity_v1"
        and _state_value(parity) == "PASS"
        and parity.get("stop_allowed") is True
        and _fresh_and_complete(parity)
        and _receipt_timestamp_is_fresh(parity)
        and isinstance(jobs, list)
        and bool(jobs)
        and all(
            isinstance(row, Mapping) and _parity_job_proof_is_fresh(row)
            for row in jobs
        )
    )


def _parity_job_proof_is_fresh(row: Mapping[str, Any]) -> bool:
    compared = row.get("compared_fields")
    heartbeat = row.get("heartbeat")
    evidence = row.get("evidence")
    mandatory_fields = {
        ProcessKind.DETERMINISTIC.value: {
            "decision_id", "source_hash", "config_hash", "input_hash",
            "code_hash", "intended_fill", "exit", "cost", "funding",
        },
        ProcessKind.MARKET_SNAPSHOT.value: {
            "source_hash", "config_hash", "input_hash", "content_hash", "decision_id",
        },
        ProcessKind.COLLECTOR.value: {"source_hash", "content_hash", "count", "size_bytes"},
    }
    process_kind = row.get("process_kind")
    try:
        _require_only_fields(row, _PARITY_JOB_FIELDS, context="parity job")
        _reject_unknown_truthy_receipt_fields(row)
        if isinstance(heartbeat, Mapping):
            _require_only_fields(heartbeat, _PROOF_FIELDS, context="heartbeat proof")
            _reject_unknown_truthy_receipt_fields(heartbeat)
        if isinstance(evidence, Mapping):
            _require_only_fields(evidence, _PROOF_FIELDS, context="evidence proof")
            _reject_unknown_truthy_receipt_fields(evidence)
    except MigrationError:
        return False
    if (
        row.get("state") != "PASS"
        or row.get("stop_allowed") is not True
        or row.get("completion_valid") is not True
        or row.get("comparator_state") != "PASS"
        or not _fresh_and_complete(row)
        or not _receipt_timestamp_is_fresh(row)
        or not isinstance(compared, list)
        or not compared
        or not all(isinstance(field, str) and field for field in compared)
        or process_kind not in mandatory_fields
        or not mandatory_fields[str(process_kind)].issubset(set(compared))
    ):
        return False
    for proof in (heartbeat, evidence):
        payload = proof.get("payload") if isinstance(proof, Mapping) else None
        if (
            not isinstance(proof, Mapping)
            or proof.get("state") != "PASS"
            or proof.get("fresh") is not True
            or not isinstance(proof.get("sha256"), str)
            or not isinstance(payload, Mapping)
            or proof.get("sha256") != _sha256_canonical(payload)
            or payload.get("state") != "PASS"
            or payload.get("observed_at_utc") != proof.get("observed_at_utc")
            or not _receipt_timestamp_is_fresh(proof)
        ):
            return False
    evidence_payload = evidence.get("payload") if isinstance(evidence, Mapping) else {}
    closed_source_ts = _parse_whole_second_utc(evidence_payload.get("closed_source_ts"))
    observed_at = _parse_whole_second_utc(evidence_payload.get("observed_at_utc"))
    if (
        evidence_payload.get("job_name") != row.get("job_name")
        or evidence_payload.get("process_kind") != process_kind
        or evidence_payload.get("legacy_identity_fingerprint")
        != row.get("legacy_identity_fingerprint")
        or evidence_payload.get("canonical_identity_fingerprint")
        != row.get("canonical_identity_fingerprint")
        or evidence_payload.get("compared_fields") != compared
        or closed_source_ts is None
        or observed_at is None
        or closed_source_ts > observed_at
    ):
        return False
    return all(
        isinstance(row.get(field), str)
        and re.fullmatch(r"[0-9a-f]{64}", str(row.get(field)))
        for field in ("legacy_identity_fingerprint", "canonical_identity_fingerprint")
    )


def _parity_job_proof_matches_context(
    row: Mapping[str, Any],
    launch_row: Mapping[str, Any],
    legacy_row: Mapping[str, Any],
    expected_job: Mapping[str, Any],
) -> bool:
    """Re-run the comparator and bind both inputs to inventory and launch."""
    heartbeat = row.get("heartbeat")
    heartbeat_payload = heartbeat.get("payload") if isinstance(heartbeat, Mapping) else None
    evidence = row.get("evidence")
    evidence_payload = evidence.get("payload") if isinstance(evidence, Mapping) else None
    if not isinstance(heartbeat_payload, Mapping) or not isinstance(evidence_payload, Mapping):
        return False
    try:
        _require_only_fields(
            heartbeat_payload, _HEARTBEAT_PAYLOAD_FIELDS, context="heartbeat payload"
        )
        _require_only_fields(
            evidence_payload, _EVIDENCE_PAYLOAD_FIELDS, context="evidence payload"
        )
        _reject_unknown_truthy_receipt_fields(heartbeat_payload)
        _reject_unknown_truthy_receipt_fields(evidence_payload)
    except MigrationError:
        return False
    if not (
        heartbeat_payload.get("job_name") == row.get("job_name")
        and heartbeat_payload.get("canonical_screen_session") == launch_row.get("screen_session")
        and heartbeat_payload.get("canonical_pid") == launch_row.get("pid")
        and heartbeat_payload.get("evidence_epoch") == launch_row.get("evidence_epoch")
        and heartbeat_payload.get("state") == "PASS"
        and heartbeat_payload.get("observed_at_utc") == heartbeat.get("observed_at_utc")
    ):
        return False
    old_raw = evidence_payload.get("legacy_receipt")
    new_raw = evidence_payload.get("canonical_receipt")
    if not isinstance(old_raw, Mapping) or not isinstance(new_raw, Mapping):
        return False
    try:
        _require_only_fields(old_raw, _PROCESS_RECEIPT_FIELDS, context="legacy process receipt")
        _require_only_fields(new_raw, _PROCESS_RECEIPT_FIELDS, context="canonical process receipt")
        _reject_unknown_truthy_receipt_fields(old_raw)
        _reject_unknown_truthy_receipt_fields(new_raw)
        old = process_receipt_from_mapping(old_raw)
        new = process_receipt_from_mapping(new_raw)
        comparator = {
            ProcessKind.DETERMINISTIC.value: compare_deterministic_receipts,
            ProcessKind.MARKET_SNAPSHOT.value: compare_market_snapshot_receipts,
            ProcessKind.COLLECTOR.value: compare_collector_snapshots,
        }[str(row.get("process_kind"))]
        verdict = comparator(old, new)
    except (KeyError, MigrationError, TypeError, ValueError):
        return False
    legacy_identity = legacy_row.get("identity")
    if not isinstance(legacy_identity, Mapping):
        return False
    expected_legacy_identity = {
        key: value for key, value in legacy_identity.items() if key != "fingerprint"
    }
    launch_hashes = launch_row.get("source_hashes")
    if not isinstance(launch_hashes, Mapping):
        return False
    expected_hash_groups = {
        "source_hashes": {
            str(path): launch_hashes.get(str(path))
            for path in expected_job.get("source_paths", [])
        },
        "config_hashes": {
            str(path): launch_hashes.get(str(path))
            for path in expected_job.get("config_paths", [])
        },
        "input_hashes": {
            str(path): launch_hashes.get(str(path))
            for path in expected_job.get("input_paths", [])
        },
    }
    try:
        legacy_evidence_hashes, canonical_evidence_hashes = _current_evidence_hashes(
            legacy_row, launch_row, expected_job
        )
    except (MigrationError, OSError):
        return False
    expected_legacy_paths = tuple(str(path) for path in expected_job.get("evidence_paths", []))
    return bool(
        old.job_name == row.get("job_name")
        and old.screen_name == legacy_row.get("screen_name")
        and old.pid == legacy_row.get("pid")
        and old.cwd == legacy_row.get("cwd")
        and old.command == legacy_row.get("command")
        and old.process_kind.value == row.get("process_kind")
        and tuple(old.evidence_paths) == expected_legacy_paths
        and all(
            old.identity.get(key) == value
            for key, value in expected_legacy_identity.items()
        )
        and new.job_name == row.get("job_name")
        and new.screen_name == launch_row.get("screen_session")
        and new.pid == launch_row.get("pid")
        and new.cwd == launch_row.get("cwd")
        and new.command == " ".join(str(value) for value in launch_row.get("argv", ()))
        and new.process_kind.value == row.get("process_kind")
        and tuple(new.evidence_paths) == tuple(launch_row.get("evidence_paths", ()))
        and new.evidence_epoch == launch_row.get("evidence_epoch")
        and all(
            old.identity.get(key) == value and new.identity.get(key) == value
            for key, value in expected_hash_groups.items()
        )
        and old.identity.get("evidence_hashes") == legacy_evidence_hashes
        and new.identity.get("evidence_hashes") == canonical_evidence_hashes
        and verdict.state is ParityState.PASS
        and verdict.stop_allowed is True
        and list(verdict.compared_fields) == row.get("compared_fields")
        and evidence_payload.get("comparator_reason") == verdict.reason
    )


def _current_evidence_hashes(
    legacy_row: Mapping[str, Any],
    launch_row: Mapping[str, Any],
    expected_job: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Re-read every legacy and canonical evidence file at the stop gate."""
    legacy_evidence = legacy_row.get("evidence")
    expected_legacy_paths = [str(path) for path in expected_job.get("evidence_paths", [])]
    canonical_paths = launch_row.get("evidence_paths")
    if (
        not isinstance(legacy_evidence, list)
        or not isinstance(canonical_paths, list)
        or len(legacy_evidence) != len(expected_legacy_paths)
        or len(canonical_paths) != len(expected_job.get("canonical_evidence_files", []))
        or not legacy_evidence
        or not canonical_paths
    ):
        raise MigrationError("parity evidence scope mismatch")
    legacy_cwd_raw = legacy_row.get("cwd")
    if not isinstance(legacy_cwd_raw, str):
        raise MigrationError("legacy evidence cwd is missing")
    legacy_cwd = Path(legacy_cwd_raw).resolve()
    max_age = expected_job.get("max_age_seconds")
    if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age <= 0:
        raise MigrationError("parity evidence freshness contract is invalid")
    now = datetime.now(timezone.utc).timestamp()

    legacy_hashes: dict[str, str] = {}
    for index, (item, logical_path) in enumerate(
        zip(legacy_evidence, expected_legacy_paths, strict=True)
    ):
        if not isinstance(item, Mapping) or item.get("path") != logical_path:
            raise MigrationError("legacy evidence scope mismatch")
        resolved_raw = item.get("resolved_path")
        if not isinstance(resolved_raw, str):
            raise MigrationError("legacy evidence path is unresolved")
        resolved = Path(resolved_raw).resolve()
        expected_resolved = (legacy_cwd / logical_path).resolve()
        if resolved != expected_resolved or not resolved.is_file():
            raise MigrationError("legacy evidence path drift")
        payload = resolved.read_bytes()
        digest = _sha256_bytes(payload)
        if item.get("sha256") != digest or item.get("size_bytes") != len(payload):
            raise MigrationError("legacy evidence changed after inventory")
        if now - resolved.stat().st_mtime > max_age:
            raise MigrationError("legacy evidence is stale")
        legacy_hashes[str(index)] = digest

    canonical_hashes: dict[str, str] = {}
    for index, raw_path in enumerate(canonical_paths):
        if not isinstance(raw_path, str):
            raise MigrationError("canonical evidence path is malformed")
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise MigrationError("canonical evidence is missing")
        payload = path.read_bytes()
        if now - path.stat().st_mtime > max_age:
            raise MigrationError("canonical evidence is stale")
        canonical_hashes[str(index)] = _sha256_bytes(payload)
    return legacy_hashes, canonical_hashes


def _stop_receipt_is_complete(receipt: Mapping[str, Any], screen_name: str) -> bool:
    expected_command = ["screen", "-S", screen_name, "-X", "quit"]
    remaining = receipt.get("post_stop_sessions")
    return bool(
        receipt.get("screen_name") == screen_name
        and receipt.get("state") == "STOPPED"
        and receipt.get("command") == expected_command
        and receipt.get("returncode") == 0
        and not isinstance(receipt.get("returncode"), bool)
        and isinstance(remaining, list)
        and all(isinstance(item, str) for item in remaining)
        and screen_name not in remaining
        and _receipt_timestamp_is_fresh(receipt)
    )


def _validate_parity_context(
    manifest: Mapping[str, Any],
    inventory_rows: Sequence[Mapping[str, Any]],
    launch: Mapping[str, Any],
    parity: Mapping[str, Any],
) -> None:
    """Validate exact parity scope and independently replay every comparator."""
    expected_jobs = _canonical_manifest_jobs(manifest)
    inventory_by_job: dict[str, Mapping[str, Any]] = {}
    for item in inventory_rows:
        if not isinstance(item, Mapping) or not isinstance(item.get("job_name"), str):
            raise MigrationError("parity inventory scope is malformed")
        name = str(item["job_name"])
        if name in inventory_by_job or name not in expected_jobs:
            raise MigrationError("parity inventory scope mismatch")
        inventory_by_job[name] = item
    launch_rows = launch.get("jobs")
    if not isinstance(launch_rows, list):
        raise MigrationError("parity launch scope is malformed")
    launch_by_job: dict[str, Mapping[str, Any]] = {}
    for item in launch_rows:
        if not isinstance(item, Mapping) or not isinstance(item.get("job_name"), str):
            raise MigrationError("parity launch scope is malformed")
        name = str(item["job_name"])
        if name in launch_by_job or name not in expected_jobs:
            raise MigrationError("parity launch scope mismatch")
        launch_by_job[name] = item
    parity_rows = parity.get("jobs")
    if not isinstance(parity_rows, list):
        raise MigrationError("parity job scope is malformed")
    parity_by_job: dict[str, Mapping[str, Any]] = {}
    for item in parity_rows:
        if not isinstance(item, Mapping) or not isinstance(item.get("job_name"), str):
            raise MigrationError("parity job scope is malformed")
        name = str(item["job_name"])
        if name in parity_by_job or name not in expected_jobs:
            raise MigrationError("parity job scope mismatch")
        parity_by_job[name] = item
    expected_names = set(expected_jobs)
    if (
        set(inventory_by_job) != expected_names
        or set(launch_by_job) != expected_names
        or set(parity_by_job) != expected_names
    ):
        raise MigrationError("parity job scope mismatch")
    comparator_names = {
        ProcessKind.DETERMINISTIC.value: "compare_deterministic_receipts",
        ProcessKind.MARKET_SNAPSHOT.value: "compare_market_snapshot_receipts",
        ProcessKind.COLLECTOR.value: "compare_collector_snapshots",
    }
    for name, expected_job in expected_jobs.items():
        item = parity_by_job[name]
        launch_row = launch_by_job[name]
        legacy_row = inventory_by_job[name]
        process_kind = str(expected_job["process_kind"])
        if (
            item.get("canonical_screen_session") != launch_row.get("screen_session")
            or item.get("process_kind") != process_kind
            or item.get("comparator") != comparator_names[process_kind]
            or item.get("legacy_identity_fingerprint")
            != legacy_row.get("identity", {}).get("fingerprint")
            or item.get("canonical_identity_fingerprint")
            != launch_row.get("identity_fingerprint")
            or not _parity_job_proof_is_fresh(item)
            or not _parity_job_proof_matches_context(
                item, launch_row, legacy_row, expected_job
            )
        ):
            raise MigrationError("parity job is not fresh and complete")


def _canonical_manifest_jobs(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(job["name"]): job
        for job in manifest.get("jobs", [])
        if isinstance(job, Mapping) and job.get("migration_mode", "canonical") == "canonical"
    }


def _launch_is_live(launch: Mapping[str, Any], manifest: Mapping[str, Any]) -> bool:
    """Only an exact one-to-one real STARTED launch can authorize stop."""
    _validate_receipt_authority(launch)
    _require_bound_receipt(launch, "launch_sha256")
    if launch.get("schema_id") != "canonical_station_launch_v1":
        raise MigrationError("canonical launch schema mismatch")
    if not _receipt_timestamp_is_fresh(launch):
        raise MigrationError("canonical launch receipt is stale")
    jobs = launch.get("jobs")
    expected = _canonical_manifest_jobs(manifest)
    if not expected or not isinstance(jobs, list) or len(jobs) != len(expected):
        raise MigrationError("canonical launch job scope mismatch")
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in jobs:
        if not isinstance(row, Mapping) or not isinstance(row.get("job_name"), str):
            raise MigrationError("canonical launch row is malformed")
        _require_only_fields(row, _LAUNCH_ROW_FIELDS, context="canonical launch row")
        _reject_unknown_truthy_receipt_fields(row)
        name = str(row["job_name"])
        if name in by_name or name not in expected:
            raise MigrationError("canonical launch job scope mismatch")
        by_name[name] = row
    if launch.get("dry_run") is not False:
        return False
    orchestrator_hashes = launch.get("orchestrator_hashes")
    if not isinstance(orchestrator_hashes, Mapping):
        raise MigrationError("canonical launch orchestrator identity is missing")
    pids: set[int] = set()
    screens: set[str] = set()
    epochs: set[str] = set()
    roots: set[Path] = set()
    for name, job in expected.items():
        row = by_name[name]
        pid = row.get("pid")
        epoch = row.get("evidence_epoch")
        screen = row.get("screen_session")
        cwd_raw = row.get("cwd")
        trusted_root = ROOT.resolve()
        if not isinstance(cwd_raw, str) or Path(cwd_raw).resolve() != trusted_root:
            return False
        cwd = trusted_root
        runtime_dir = (
            cwd
            / str(manifest["canonical_runtime_root"])
            / "epochs"
            / str(epoch)
            / name
        ).resolve()
        try:
            runtime_dir.relative_to(cwd)
        except ValueError as exc:
            raise MigrationError("canonical launch runtime escapes project root") from exc
        expected_argv = [
            str((cwd / str(job["launcher"][0])).resolve()),
            *[str(value) for value in job["launcher"][1:]],
            "--runtime-dir",
            str(runtime_dir),
        ]
        expected_evidence = [
            str(runtime_dir / str(relative))
            for relative in job["canonical_evidence_files"]
        ]
        logical_identity_paths = [
            str(relative)
            for field in ("source_paths", "config_paths", "input_paths")
            for relative in job.get(field, [])
        ]
        expected_source_hashes: dict[str, str] = {}
        for relative in logical_identity_paths:
            identity_path = (cwd / relative).resolve()
            try:
                identity_path.relative_to(cwd)
            except ValueError as exc:
                raise MigrationError("canonical launch identity escapes project root") from exc
            if not identity_path.is_file():
                raise MigrationError(f"canonical launch identity path is missing: {relative}")
            expected_source_hashes[relative] = _sha256_bytes(identity_path.read_bytes())
        expected_source_hashes = dict(sorted(expected_source_hashes.items()))
        expected_runtime_requirements = [
            str(cwd / str(relative)) for relative in job.get("runtime_requirements", [])
        ]
        expected_identity = {
            "job_name": name,
            "process_kind": job["process_kind"],
            "argv": expected_argv,
            "evidence_epoch": epoch,
            "evidence_paths": expected_evidence,
            "source_hashes": expected_source_hashes,
            "runtime_requirements": expected_runtime_requirements,
        }
        if (
            row.get("state") != "STARTED"
            or row.get("returncode") != 0
            or not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(epoch, str)
            or not epoch
            or screen != canonical_screen_name(str(job["screen_session"]), epoch)
            or row.get("cwd") != str(cwd)
            or row.get("runtime_dir") != str(runtime_dir)
            or row.get("argv") != expected_argv
            or row.get("evidence_paths") != expected_evidence
            or row.get("source_hashes") != expected_source_hashes
            or row.get("runtime_requirements") != expected_runtime_requirements
            or row.get("runtime_missing") not in ([], ())
            or not isinstance(row.get("identity_fingerprint"), str)
            or row.get("identity_fingerprint") != _sha256_canonical(expected_identity)
            or row.get("orders_sent") is not False
            or row.get("private_api_calls") is not False
            or row.get("live_write_authority") is not False
            or row.get("public_data_read_authority") is not True
        ):
            return False
        if pid in pids or screen in screens:
            raise MigrationError("canonical launch has duplicate PID or screen")
        pids.add(pid)
        screens.add(str(screen))
        epochs.add(epoch)
        roots.add(cwd)
    if len(epochs) != 1 or len(roots) != 1:
        raise MigrationError("canonical launch jobs do not share one epoch and root")
    root = next(iter(roots))
    expected_orchestrator_hashes = {
        "research_lab/canonical_station.py": _sha256_bytes(
            (root / "research_lab/canonical_station.py").read_bytes()
        ),
        "scripts/canonical_station_migration.py": _sha256_bytes(
            (root / "scripts/canonical_station_migration.py").read_bytes()
        ),
    }
    if dict(orchestrator_hashes) != expected_orchestrator_hashes:
        raise MigrationError("canonical launch orchestrator hash mismatch")
    return True


def run_migration(
    *,
    manifest: Mapping[str, Any],
    legacy_inventory: Mapping[str, Any],
    launch_fn: Any,
    verify_fn: Any,
    stop_fn: Any,
    output_dir: Path,
) -> dict[str, Any]:
    """Run launch -> verify -> (conditionally) stop as an explicit state machine.

    Callbacks are deliberately injected so tests can prove that no process or
    screen action occurs on an unsafe branch.  The real CLI supplies callbacks
    which are the only place subprocesses are reached.
    """
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MigrationError("migration output directory must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    stopped: list[str] = []
    stop_receipts: list[dict[str, Any]] = []
    reason = ""
    state = "FAIL_CLOSED"
    launch: dict[str, Any] = {}
    parity: dict[str, Any] = {}
    authorization: dict[str, Any] = {}
    try:
        validate_authority_manifest(manifest)
        _validate_receipt_authority(legacy_inventory)
        _require_bound_receipt(legacy_inventory, "inventory_sha256")
        inventory_safe = _inventory_identity_is_safe(legacy_inventory)
        rows = legacy_inventory.get("processes")
        if not isinstance(rows, list):
            raise MigrationError("legacy inventory processes are missing")

        launch = dict(launch_fn())
        _validate_receipt_authority(launch)
        _require_bound_receipt(launch, "launch_sha256")
        atomic_write_json(output_dir / "legacy_inventory.json", legacy_inventory)
        atomic_write_json(output_dir / "launch_receipt.json", launch)

        launch_ok = _launch_is_live(launch, manifest)
        if not launch_ok:
            job_states = {
                str(row.get("state"))
                for row in launch.get("jobs", [])
                if isinstance(row, Mapping)
            }
            if launch.get("dry_run") is True or job_states <= {"DRY_RUN", "BLOCKED_RUNTIME"}:
                state = "NOT_CONFIRMED"
            else:
                state = "FAIL_CLOSED"
            reason = "canonical launch did not reach an exact live STARTED state"
            parity = _bind_receipt(
                {
                    "schema_id": "canonical_station_parity_v1",
                    "authority": AUTHORITY,
                    "promotion_authority": False,
                    "network_authority": False,
                    "private_api_authority": False,
                    "order_authority": False,
                    "live_write_authority": False,
                    "public_data_read_authority": True,
                    "state": state,
                    "stop_allowed": False,
                    "reason": reason,
                    "launch_sha256": launch["launch_sha256"],
                    "inventory_sha256": legacy_inventory["inventory_sha256"],
                    "fresh": False,
                    "heartbeat_fresh": False,
                    "evidence_fresh": False,
                    "authorized_screens": [],
                    "jobs": [],
                    "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                },
                "parity_sha256",
            )
            atomic_write_json(output_dir / "parity_receipt.json", parity)
        else:
            parity = dict(verify_fn())
            _validate_receipt_authority(parity)
            _require_bound_receipt(parity, "parity_sha256")
            atomic_write_json(output_dir / "parity_receipt.json", parity)
            state = _state_value(parity)
            if state not in {"PASS", "NOT_CONFIRMED", "FAIL_CLOSED"}:
                state, reason = "FAIL_CLOSED", "unknown parity state"
            elif state != "PASS":
                reason = str(parity.get("reason", "parity did not pass"))
            elif not inventory_safe:
                state, reason = "NOT_CONFIRMED", "legacy process identity is unresolved"
            else:
                expected_jobs = _canonical_manifest_jobs(manifest)
                inventory_by_job = {
                    str(row["job_name"]): row
                    for row in rows
                    if isinstance(row, Mapping) and isinstance(row.get("job_name"), str)
                }
                launch_jobs = {
                    str(row["job_name"]): row
                    for row in launch["jobs"]
                    if isinstance(row, Mapping)
                }
                parity_jobs = parity.get("jobs")
                if not isinstance(parity_jobs, list) or len(parity_jobs) != len(expected_jobs):
                    raise MigrationError("parity job scope mismatch")
                parity_by_name: dict[str, Mapping[str, Any]] = {}
                for row in parity_jobs:
                    if not isinstance(row, Mapping) or not isinstance(row.get("job_name"), str):
                        raise MigrationError("parity job row is malformed")
                    name = str(row["job_name"])
                    if name in parity_by_name or name not in expected_jobs:
                        raise MigrationError("parity job scope mismatch")
                    launch_row = launch_jobs.get(name)
                    legacy_row = inventory_by_job.get(name)
                    expected_comparator = {
                        ProcessKind.DETERMINISTIC.value: "compare_deterministic_receipts",
                        ProcessKind.MARKET_SNAPSHOT.value: "compare_market_snapshot_receipts",
                        ProcessKind.COLLECTOR.value: "compare_collector_snapshots",
                    }[str(expected_jobs[name]["process_kind"])]
                    if (
                        launch_row is None
                        or legacy_row is None
                        or row.get("canonical_screen_session") != launch_row.get("screen_session")
                        or row.get("process_kind") != expected_jobs[name]["process_kind"]
                        or row.get("comparator") != expected_comparator
                        or row.get("legacy_identity_fingerprint")
                        != legacy_row.get("identity", {}).get("fingerprint")
                        or row.get("canonical_identity_fingerprint")
                        != launch_row.get("identity_fingerprint")
                        or not _parity_job_proof_is_fresh(row)
                        or not _parity_job_proof_matches_context(
                            row, launch_row, legacy_row, expected_jobs[name]
                        )
                    ):
                        raise MigrationError("parity job is not fresh and complete")
                    parity_by_name[name] = row
                if set(parity_by_name) != set(expected_jobs):
                    raise MigrationError("parity job scope mismatch")
                if parity.get("launch_sha256") != launch["launch_sha256"]:
                    raise MigrationError("parity launch binding mismatch")
                if parity.get("inventory_sha256") != legacy_inventory["inventory_sha256"]:
                    raise MigrationError("parity inventory binding mismatch")
                if not _parity_is_stop_eligible(parity):
                    raise MigrationError("parity receipt is not stop eligible")

                candidates: list[str] = []
                inventory_jobs: set[str] = set()
                for row in rows:
                    if not isinstance(row, Mapping):
                        raise MigrationError("malformed legacy process receipt")
                    job_name = row.get("job_name")
                    screen_name = row.get("screen_name")
                    if job_name not in expected_jobs:
                        raise MigrationError("unknown or manual-hold legacy job")
                    if job_name in inventory_jobs:
                        raise MigrationError("duplicate legacy job")
                    inventory_jobs.add(str(job_name))
                    if (
                        row.get("status") != "CONFIRMED"
                        or row.get("eligible_for_parity") is not True
                        or not isinstance(screen_name, str)
                        or not _SAFE_SCREEN_NAME.fullmatch(screen_name)
                    ):
                        raise MigrationError("legacy process identity is unresolved")
                    candidates.append(screen_name)
                if not candidates:
                    state, reason = "NOT_CONFIRMED", "legacy inventory has no stoppable process"
                else:
                    authorized = parity.get("authorized_screens")
                    if (
                        not isinstance(authorized, list)
                        or len(authorized) != len(set(authorized))
                        or sorted(authorized) != sorted(candidates)
                        or not all(isinstance(name, str) and _SAFE_SCREEN_NAME.fullmatch(name) for name in authorized)
                    ):
                        raise MigrationError("parity screen authorization mismatch")
                    authorization = {
                        "schema_id": "canonical_station_migration_authorization_v1",
                        "authority": AUTHORITY,
                        "promotion_authority": False,
                        "network_authority": False,
                        "private_api_authority": False,
                        "order_authority": False,
                        "live_write_authority": False,
                        "public_data_read_authority": True,
                        "state": "PASS",
                        "manifest_sha256": _sha256_canonical(manifest),
                        "inventory_sha256": legacy_inventory["inventory_sha256"],
                        "launch_sha256": launch["launch_sha256"],
                        "parity_sha256": parity["parity_sha256"],
                        "authorized_screens": sorted(candidates),
                        "authorized_jobs": sorted(inventory_jobs),
                        "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    }
                    authorization = _bind_receipt(authorization, "authorization_sha256")
                    # This is the durable point of no return.  Every source
                    # receipt and every exact screen is bound before callback 1.
                    atomic_write_json(output_dir / "migration_authorization.json", authorization)
                    for name in sorted(candidates):
                        try:
                            stop_result = stop_fn(name, authorization)
                        except Exception as exc:  # pragma: no cover - defensive boundary
                            state, reason = "FAIL_CLOSED", f"legacy stop failed: {exc}"
                            break
                        if not isinstance(stop_result, Mapping) or not _stop_receipt_is_complete(
                            stop_result, name
                        ):
                            state, reason = "FAIL_CLOSED", "legacy stop receipt is invalid"
                            break
                        stopped.append(name)
                        stop_receipts.append(dict(stop_result))
                    else:
                        state, reason = "PASS", str(parity.get("reason", "parity PASS"))
    except Exception as exc:
        state = "FAIL_CLOSED"
        reason = str(exc) or exc.__class__.__name__

    result: dict[str, Any] = {
        "schema_id": "canonical_station_migration_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "public_data_read_authority": True,
        "state": state,
        "reason": reason,
        "manifest_sha256": _sha256_canonical(manifest),
        "inventory_sha256": legacy_inventory.get("inventory_sha256"),
        "launch_sha256": launch.get("launch_sha256"),
        "parity_sha256": parity.get("parity_sha256"),
        "authorization_sha256": authorization.get("authorization_sha256"),
        "legacy_stop": stopped,
        "stop_receipts": stop_receipts,
        "reopen_condition": "fresh inventory and parity PASS",
        "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    result = _bind_receipt(result, "migration_sha256")
    try:
        atomic_write_json(output_dir / "migration_receipt.json", result)
    except Exception as exc:  # pragma: no cover - filesystem failure boundary
        failed = dict(result)
        failed.pop("migration_sha256", None)
        failed["state"] = "FAIL_CLOSED"
        failed["reason"] = f"migration receipt write failed: {exc}"
        result = _bind_receipt(failed, "migration_sha256")
    return result


def stop_legacy_session(
    screen_name: str,
    inventory: Mapping[str, Any],
    parity_receipt: Mapping[str, Any],
    launch_receipt: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
    manifest: Mapping[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Stop one exact, validated legacy screen; never accepts a PID or glob."""
    if not isinstance(screen_name, str) or not _SAFE_SCREEN_NAME.fullmatch(screen_name):
        raise MigrationError("invalid legacy screen name")
    try:
        validate_authority_manifest(manifest)
        _validate_receipt_authority(inventory)
        _require_bound_receipt(inventory, "inventory_sha256")
        _validate_receipt_authority(parity_receipt)
        _require_bound_receipt(parity_receipt, "parity_sha256")
        _validate_receipt_authority(launch_receipt)
        _require_bound_receipt(launch_receipt, "launch_sha256")
        _validate_receipt_authority(authorization_receipt)
        _require_bound_receipt(authorization_receipt, "authorization_sha256")
    except MigrationError as exc:
        raise MigrationError("stop requires hash-bound PASS authorization receipts") from exc
    if not _launch_is_live(launch_receipt, manifest):
        raise MigrationError("stop requires a live canonical launch receipt")
    matches = [
        row
        for row in inventory.get("processes", [])
        if (
        isinstance(row, Mapping)
        and row.get("screen_name") == screen_name
        and row.get("status") == "CONFIRMED"
        and row.get("eligible_for_parity") is True
        )
    ]
    if len(matches) != 1 or not _inventory_identity_is_safe(inventory):
        raise MigrationError("stop requires PASS inventory and parity receipts")
    if parity_receipt.get("inventory_sha256") != inventory.get("inventory_sha256"):
        raise MigrationError("stop parity inventory binding mismatch")
    if parity_receipt.get("launch_sha256") != launch_receipt.get("launch_sha256"):
        raise MigrationError("stop parity launch binding mismatch")
    inventory_rows = inventory.get("processes")
    if not isinstance(inventory_rows, list):
        raise MigrationError("stop inventory scope is malformed")
    expected_screens = sorted(
        str(row["screen_name"])
        for row in inventory_rows
        if isinstance(row, Mapping) and isinstance(row.get("screen_name"), str)
    )
    expected_jobs = sorted(
        str(row["job_name"])
        for row in inventory_rows
        if isinstance(row, Mapping) and isinstance(row.get("job_name"), str)
    )
    authorized = parity_receipt.get("authorized_screens")
    if (
        not isinstance(authorized, list)
        or len(authorized) != len(set(authorized))
        or authorized != expected_screens
        or screen_name not in authorized
    ):
        raise MigrationError("screen is not explicitly authorized by parity receipt")
    if not _parity_is_stop_eligible(parity_receipt):
        raise MigrationError("stop requires PASS inventory and parity receipts")
    _validate_parity_context(
        manifest,
        [row for row in inventory_rows if isinstance(row, Mapping)],
        launch_receipt,
        parity_receipt,
    )
    job_name = str(matches[0].get("job_name"))
    authorization_screens = authorization_receipt.get("authorized_screens")
    authorization_jobs = authorization_receipt.get("authorized_jobs")
    if (
        authorization_receipt.get("schema_id")
        != "canonical_station_migration_authorization_v1"
        or authorization_receipt.get("state") != "PASS"
        or not _receipt_timestamp_is_fresh(authorization_receipt)
        or authorization_receipt.get("manifest_sha256") != _sha256_canonical(manifest)
        or authorization_receipt.get("inventory_sha256") != inventory.get("inventory_sha256")
        or authorization_receipt.get("launch_sha256") != launch_receipt.get("launch_sha256")
        or authorization_receipt.get("parity_sha256") != parity_receipt.get("parity_sha256")
        or not isinstance(authorization_screens, list)
        or not isinstance(authorization_jobs, list)
        or len(authorization_screens) != len(set(authorization_screens))
        or len(authorization_jobs) != len(set(authorization_jobs))
        or authorization_screens != expected_screens
        or authorization_jobs != expected_jobs
        or screen_name not in authorization_screens
        or job_name not in authorization_jobs
    ):
        raise MigrationError("screen is not covered by durable migration authorization")
    command = ["screen", "-S", screen_name, "-X", "quit"]
    if dry_run:
        return {"screen_name": screen_name, "state": "DRY_RUN", "command": command, "returncode": None}
    before = subprocess.run(["screen", "-ls"], check=False, capture_output=True, text=True)
    current_screens = _screen_pid_map(before.stdout)
    launch_rows = launch_receipt.get("jobs")
    if not isinstance(launch_rows, list) or any(
        not isinstance(row, Mapping)
        or not isinstance(row.get("screen_session"), str)
        or current_screens.get(str(row.get("screen_session"))) != row.get("pid")
        for row in launch_rows
    ):
        raise MigrationError("canonical screen identity changed before legacy stop")
    expected_screen_pid = matches[0].get("screen_pid")
    current_screen_pid = current_screens.get(screen_name)
    if (
        not isinstance(expected_screen_pid, int)
        or isinstance(expected_screen_pid, bool)
        or current_screen_pid != expected_screen_pid
    ):
        raise MigrationError(f"legacy screen identity changed before stop: {screen_name}")
    ps_result = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if ps_result.returncode != 0:
        raise MigrationError("legacy process inventory refresh failed")
    current_pid, current_command = _resolve_session_process(
        screen_name,
        ps_result.stdout,
        pid_hint=expected_screen_pid,
        command_markers=(str(matches[0].get("command")),),
    )
    expected_pid = matches[0].get("pid")
    expected_command = matches[0].get("command")
    if current_pid != expected_pid or current_command != expected_command:
        raise MigrationError(f"legacy child identity changed before stop: {screen_name}")
    current_cwd = _cwd_for_pid(int(expected_pid)) if isinstance(expected_pid, int) else None
    if current_cwd is None or Path(current_cwd).resolve() != Path(str(matches[0].get("cwd"))).resolve():
        raise MigrationError(f"legacy cwd identity changed before stop: {screen_name}")
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    after = subprocess.run(["screen", "-ls"], check=False, capture_output=True, text=True)
    remaining = screen_name in parse_screen_sessions(after.stdout)
    record = {
        "screen_name": screen_name,
        "state": "STOPPED" if result.returncode == 0 and not remaining else "FAIL_CLOSED",
        "command": command,
        "returncode": result.returncode,
        "post_stop_sessions": parse_screen_sessions(after.stdout),
        "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if record["state"] != "STOPPED":
        raise MigrationError(f"legacy session did not stop cleanly: {screen_name}")
    return record


def _read_json_receipt(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise MigrationError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise MigrationError(f"non-finite JSON constant: {value}")

    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except MigrationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"receipt is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise MigrationError(f"receipt must be a JSON object: {path}")
    return value


def _launch_command(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    manifest = load_manifest(Path(args.manifest), project_root=root)
    plan = build_canonical_launch_plan(manifest, project_root=root, epoch=args.evidence_epoch)
    receipt = launch_canonical_jobs(plan, dry_run=bool(args.dry_run))
    if args.output:
        output = Path(args.output).resolve()
        atomic_write_json(output, receipt)
    states = {
        str(row.get("state"))
        for row in receipt.get("jobs", [])
        if isinstance(row, Mapping)
    }
    if args.dry_run:
        state = "DRY_RUN" if states == {"DRY_RUN"} else "BLOCKED_RUNTIME"
    else:
        state = "STARTED" if states == {"STARTED"} else "FAIL_CLOSED"
    print(json.dumps({"state": state, "jobs": len(receipt["jobs"])}, sort_keys=True))
    return 0 if state in {"DRY_RUN", "STARTED"} else 2


def _verify_command(args: argparse.Namespace) -> int:
    launch = _read_json_receipt(Path(args.launch_receipt))
    # Verification must be evidence-backed; absence of a separately produced
    # comparator receipt is NOT_CONFIRMED, never an optimistic PASS.
    parity: dict[str, Any] = {
        "schema_id": "canonical_station_parity_v1",
        **_authority_claims(launch),
        "state": "NOT_CONFIRMED",
        "stop_allowed": False,
        "reason": "fresh canonical evidence and parity comparator unavailable",
        "launch_sha256": launch.get("launch_sha256"),
        "fresh": False,
        "heartbeat_fresh": False,
        "evidence_fresh": False,
        "authorized_screens": [],
        "jobs": [],
        "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    bound = _bind_receipt(parity, "parity_sha256")
    if args.output:
        atomic_write_json(Path(args.output).resolve(), bound)
    print(json.dumps(bound, sort_keys=True))
    return 0


def _stop_command(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    manifest = load_manifest(Path(args.manifest), project_root=root)
    inventory = _read_json_receipt(Path(args.inventory))
    parity = _read_json_receipt(Path(args.parity))
    launch = _read_json_receipt(Path(args.launch))
    authorization = _read_json_receipt(Path(args.authorization))
    result = stop_legacy_session(
        args.screen_name,
        inventory,
        parity,
        launch,
        authorization,
        manifest,
        dry_run=bool(args.dry_run),
    )
    if args.output:
        atomic_write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, sort_keys=True))
    return 0


def _migrate_command(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    legacy_root = Path(args.legacy_root).resolve()
    if not legacy_root.is_dir():
        raise MigrationError(f"legacy root does not exist: {legacy_root}")
    manifest = load_manifest(Path(args.manifest), project_root=root)
    output_dir = Path(args.output).resolve()
    try:
        output_dir.relative_to(legacy_root)
    except ValueError:
        pass
    else:
        raise MigrationError("migration output cannot be inside legacy root")
    if args.inventory:
        inventory = _read_json_receipt(Path(args.inventory))
    elif args.dry_run:
        # Dry-run is intentionally side-effect free: no screen/ps/lsof calls.
        inventory = {
            "schema_id": "canonical_station_legacy_inventory_v1",
            "authority": AUTHORITY,
            "promotion_authority": False,
            "network_authority": False,
            "private_api_authority": False,
            "order_authority": False,
            "live_write_authority": False,
            "public_data_read_authority": True,
            "fresh": True,
            "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "processes": [],
        }
        inventory["inventory_sha256"] = _payload_hash(inventory, "inventory_sha256")
    else:
        raise MigrationError("migrate requires an explicit inventory receipt")
    plan = build_canonical_launch_plan(manifest, project_root=root, epoch=args.evidence_epoch)
    launched: dict[str, Mapping[str, Any]] = {}

    def launch_fn() -> Mapping[str, Any]:
        receipt = launch_canonical_jobs(plan, dry_run=bool(args.dry_run))
        launched["receipt"] = receipt
        return receipt
    if args.parity:
        parity = _read_json_receipt(Path(args.parity))
    else:
        parity = _bind_receipt({
            "schema_id": "canonical_station_parity_v1",
            **_authority_claims(inventory),
            "state": "NOT_CONFIRMED",
            "stop_allowed": False,
            "reason": "parity receipt not supplied",
            "fresh": False,
            "heartbeat_fresh": False,
            "evidence_fresh": False,
            "authorized_screens": [],
            "jobs": [],
            "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }, "parity_sha256")
    verify_fn = lambda: parity
    stop_fn = lambda name, authorization: stop_legacy_session(
        name,
        inventory,
        parity,
        launched["receipt"],
        authorization,
        manifest,
        dry_run=bool(args.dry_run),
    )
    result = run_migration(
        manifest=manifest,
        legacy_inventory=inventory,
        launch_fn=launch_fn,
        verify_fn=verify_fn,
        stop_fn=stop_fn,
        output_dir=output_dir,
    )
    print(json.dumps({"state": result["state"], "output": str(output_dir / "migration_receipt.json")}, sort_keys=True))
    return 0 if result["state"] in {"PASS", "NOT_CONFIRMED"} else 2


def build_migration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed canonical research station migration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--project-root", required=True)
    inventory.add_argument("--legacy-root", required=True)
    inventory.add_argument("--manifest", required=True)
    inventory.add_argument("--evidence-epoch", required=True)
    inventory.add_argument("--output")
    inventory.set_defaults(handler=_inventory_command)
    launch = subparsers.add_parser("launch")
    launch.add_argument("--project-root", required=True)
    launch.add_argument("--manifest", required=True)
    launch.add_argument("--evidence-epoch", required=True)
    launch.add_argument("--output")
    launch.add_argument("--dry-run", action="store_true")
    launch.set_defaults(handler=_launch_command)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--launch-receipt", required=True)
    verify.add_argument("--output")
    verify.set_defaults(handler=_verify_command)
    stop = subparsers.add_parser("stop")
    stop.add_argument("--screen-name", required=True)
    stop.add_argument("--project-root", required=True)
    stop.add_argument("--manifest", required=True)
    stop.add_argument("--inventory", required=True)
    stop.add_argument("--parity", required=True)
    stop.add_argument("--launch", required=True)
    stop.add_argument("--authorization", required=True)
    stop.add_argument("--output")
    stop.add_argument("--dry-run", action="store_true")
    stop.set_defaults(handler=_stop_command)
    migrate = subparsers.add_parser("migrate")
    migrate.add_argument("--project-root", required=True)
    migrate.add_argument("--legacy-root", required=True)
    migrate.add_argument("--manifest", required=True)
    migrate.add_argument("--evidence-epoch", required=True)
    migrate.add_argument("--inventory")
    migrate.add_argument("--parity")
    migrate.add_argument("--output", required=True)
    migrate.add_argument("--dry-run", action="store_true")
    migrate.set_defaults(handler=_migrate_command)
    return parser


build_parser = build_migration_parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except MigrationError as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
