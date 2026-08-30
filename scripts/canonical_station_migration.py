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
    atomic_write_json,
    canonical_screen_name,
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
            completed = subprocess.run(
                ["screen", "-dmS", spec.screen_session, "/bin/bash", *spec.argv],
                cwd=spec.cwd,
                env=_safe_child_environment(spec),
                capture_output=True,
                text=True,
                check=False,
            )
            session_pid = None
            if completed.returncode == 0:
                screen_result = subprocess.run(
                    ["screen", "-ls"],
                    cwd=spec.cwd,
                    env=_safe_child_environment(spec),
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


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except MigrationError as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
