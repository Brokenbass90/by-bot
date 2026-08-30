#!/usr/bin/env python3
"""Keep risk-zero Mac research loops alive and publish inspectable health.

This supervisor has no broker credentials and no live-order authority.  It may
only start the explicitly listed public-data/shadow/audit loops below.  A live
process is not considered healthy by itself: its materialized evidence must
also exist and be fresh.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.canonical_station import (
    AUTHORITY,
    canonical_screen_name,
    load_manifest,
    validate_authority_manifest,
)

RUNTIME = ROOT / "runtime" / "local_research_station"
STATUS_PATH = RUNTIME / "status.json"
PID_PATH = RUNTIME / "supervisor.pid"
LOCK_PATH = RUNTIME / "supervisor.lock"
SAFE_CANONICAL_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SENSITIVE_ENV_NAME = re.compile(
    r"(?:api.?key|secret|token|credential|password|passwd|cookie|session|auth|account|private|webhook|dsn)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Job:
    name: str
    session: str
    session_markers: tuple[str, ...]
    script: str
    evidence: str
    max_age_seconds: int
    evidence_paths: tuple[str, ...] = ()
    runtime_requirements: tuple[Path, ...] = ()
    runtime_dir: Path | None = None
    authority_env: tuple[tuple[str, str], ...] = ()
    canonical: bool = False


JOBS = (
    Job(
        "alpaca_adaptive_shadow",
        "research_alpaca_adaptive",
        ("research_alpaca_adaptive", "alpaca_adaptive_shadow"),
        "scripts/run_alpaca_adaptive_shadow_loop.sh",
        "runtime/alpaca_adaptive_v1_shadow_latest.json",
        8 * 3600,
    ),
    Job(
        "xsec_v3_shadow",
        "research_xsec_v3",
        ("research_xsec_v3", "xsec_v3_shadow"),
        "scripts/run_xsec_shadow_loop.sh",
        # XSEC is an idempotent daily decision job.  Later hourly loop ticks
        # deliberately do no work once the UTC decision is materialized, so a
        # rotating stdout log is not evidence of a new research decision.
        "runtime/xsec_v3_shadow/decision_latest.json",
        30 * 3600,
    ),
    Job(
        "funding_positioning_dynamic_shadow",
        "research_funding_dynamic",
        ("research_funding_dynamic", "funding_position_dynamic_shadow"),
        "scripts/run_funding_positioning_dynamic_shadow_loop.sh",
        "runtime/funding_positioning_dynamic_shadow_summary.json",
        20 * 60,
    ),
    Job(
        "funding_positioning_frozen_shadow",
        "research_funding_frozen",
        ("research_funding_frozen", "funding_positioning_frozen_shadow"),
        "scripts/run_funding_positioning_post_n42_frozen_loop.sh",
        "runtime/funding_positioning_post_n42_frozen_summary.json",
        20 * 60,
    ),
    Job(
        "project_audit",
        "research_project_audit",
        ("research_project_audit", "project_audit_local"),
        "scripts/run_project_audit_supervisor.sh --with-model --auto-full --sync-live --loop --interval-sec 21600",
        "runtime/project_audit/supervisor_status.json",
        8 * 3600,
    ),
    Job(
        "inplay_eth_prospective_shadow",
        "research_inplay_prospective",
        ("research_inplay_prospective",),
        "scripts/run_inplay_prospective_shadow_loop.sh",
        "runtime/inplay_prospective_shadow_v1/status.json",
        30 * 60,
    ),
)


def load_canonical_manifest() -> dict[str, Any]:
    return load_manifest(
        ROOT / "configs/research/canonical_station_v1.json", project_root=ROOT
    )


def jobs_from_manifest(
    manifest: dict[str, Any], *, epoch: str, project_root: Path | None = None
) -> tuple[Job, ...]:
    """Project launch/health identity from the canonical manifest into one epoch."""
    validate_authority_manifest(manifest)
    if not epoch:
        raise ValueError("canonical jobs require a non-empty evidence epoch")
    root = (project_root or ROOT).resolve()
    epoch_root = (
        root
        / str(manifest["canonical_runtime_root"])
        / "epochs"
        / epoch
    ).resolve()
    jobs: list[Job] = []
    for row in manifest["jobs"]:
        if row.get("migration_mode", "canonical") != "canonical":
            continue
        runtime_dir = (epoch_root / str(row["name"])).resolve()
        try:
            runtime_dir.relative_to(epoch_root)
        except ValueError as exc:
            raise ValueError(f"job runtime escapes evidence epoch: {row['name']}") from exc
        launcher = (root / str(row["launcher"][0])).resolve()
        argv = [
            str(launcher),
            *[str(value) for value in row["launcher"][1:]],
            "--runtime-dir",
            str(runtime_dir),
        ]
        evidence_paths = tuple(
            str(runtime_dir / relative)
            for relative in row["canonical_evidence_files"]
        )
        session = canonical_screen_name(str(row["screen_session"]), epoch)
        jobs.append(
            Job(
                name=str(row["name"]),
                session=session,
                session_markers=(session,),
                script=shlex.join(argv),
                evidence=evidence_paths[0],
                max_age_seconds=int(row["max_age_seconds"]),
                evidence_paths=evidence_paths,
                runtime_requirements=tuple(
                    root / relative
                    for relative in row.get("runtime_requirements", [])
                ),
                runtime_dir=runtime_dir,
                authority_env=(
                    ("RESEARCH_STATION_EVIDENCE_EPOCH", epoch),
                    ("RESEARCH_ONLY", "true"),
                    ("PROMOTION_AUTHORITY", "false"),
                    ("NETWORK_AUTHORITY", "false"),
                    ("PRIVATE_API_AUTHORITY", "false"),
                    ("ORDER_AUTHORITY", "false"),
                    ("LIVE_WRITE_AUTHORITY", "false"),
                    ("PUBLIC_DATA_READ_AUTHORITY", "true"),
                ),
                canonical=True,
            )
        )
    return tuple(jobs)


def _manifest_hashes(
    manifest: dict[str, Any], *, epoch: str
) -> tuple[dict[str, str], dict[str, str]]:
    source_hashes: dict[str, str] = {}
    run_id_identities: dict[str, str] = {}
    for job in manifest.get("jobs", []):
        if job.get("migration_mode", "canonical") != "canonical":
            continue
        job_hashes: dict[str, str] = {}
        for field in ("source_paths", "config_paths", "input_paths"):
            for logical_path in job.get(field, []):
                path = ROOT / logical_path
                digest = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else "MISSING"
                )
                source_hashes[logical_path] = digest
                job_hashes[logical_path] = digest
        identity_payload = json.dumps(
            {
                "job_name": job.get("name"),
                "process_kind": job.get("process_kind"),
                "launcher": job.get("launcher"),
                "canonical_evidence_files": job.get("canonical_evidence_files"),
                "evidence_epoch": epoch,
                "hashes": job_hashes,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        run_id_identities[str(job.get("name"))] = hashlib.sha256(
            identity_payload
        ).hexdigest()
    return dict(sorted(source_hashes.items())), dict(sorted(run_id_identities.items()))


def canonical_status(
    jobs: list[dict[str, Any]],
    *,
    epoch: str,
    source_hashes: dict[str, str],
    run_id_identities: dict[str, str],
) -> dict[str, Any]:
    evidence_paths = sorted({
        str(path)
        for item in jobs
        for path in (
            item.get("evidence_paths")
            or ([item["evidence_path"]] if item.get("evidence_path") else [])
        )
    })
    healthy = bool(jobs) and all(item.get("state") == "healthy" for item in jobs)
    healthy = healthy and bool(epoch) and all(
        digest != "MISSING" for digest in source_hashes.values()
    )
    return {
        "schema_id": "local_research_station_status_v1",
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "public_data_read_authority": True,
        "research_only": True,
        "live_order_authority": False,
        "evidence_epoch": epoch,
        "runtime_root": "runtime/local_research_station",
        "evidence_paths": evidence_paths,
        "source_hashes": dict(sorted(source_hashes.items())),
        "run_id_identities": dict(sorted(run_id_identities.items())),
        "healthy": healthy,
        "jobs": jobs,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _parse_screen_sessions(output: str) -> list[str]:
    """Return only live screen sessions; stale sockets are not processes.

    GNU screen keeps killed sessions as ``(Dead ???)`` until ``screen -wipe``.
    Treating those lines as alive makes a self-healing supervisor false-green.
    """
    sessions: list[str] = []
    for raw in str(output or "").splitlines():
        lowered = raw.lower()
        if "dead" in lowered or "remove dead screens" in lowered:
            continue
        token = raw.strip().split("\t", 1)[0]
        if "." not in token:
            continue
        pid, name = token.split(".", 1)
        if pid.isdigit() and name:
            sessions.append(name)
    return sorted(set(sessions))


def _screen_sessions() -> list[str]:
    result = subprocess.run(
        ["screen", "-ls"],
        capture_output=True,
        text=True,
        check=False,
    )
    return _parse_screen_sessions(result.stdout)


def _matching_sessions(job: Job) -> list[str]:
    return [
        name
        for name in _screen_sessions()
        if any(marker in name for marker in job.session_markers)
    ]


def _canonical_child_environment(job: Job) -> dict[str, str]:
    if not job.canonical or job.runtime_dir is None:
        raise RuntimeError(f"canonical job has no runtime dir: {job.name}")
    return {
        "PATH": SAFE_CANONICAL_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "HOME": str(job.runtime_dir / "home"),
        "TMPDIR": str(job.runtime_dir / "tmp"),
        **dict(job.authority_env),
    }


def _screen_control_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not SENSITIVE_ENV_NAME.search(key) and not key.upper().endswith("_JSON")
    }


def _start(job: Job) -> dict[str, Any]:
    command = f"cd {shlex.quote(str(ROOT))} && exec /bin/bash {job.script}"
    screen_env = None
    if job.canonical:
        if job.runtime_dir is None:
            raise RuntimeError(f"canonical job has no runtime dir: {job.name}")
        home = job.runtime_dir / "home"
        tmp = job.runtime_dir / "tmp"
        home.mkdir(parents=True, exist_ok=True)
        tmp.mkdir(parents=True, exist_ok=True)
        child_env = _canonical_child_environment(job)
        assignments = shlex.join(
            [f"{key}={value}" for key, value in sorted(child_env.items())]
        )
        command = (
            f"cd {shlex.quote(str(ROOT))} && exec /usr/bin/env -i "
            f"{assignments} /bin/bash {job.script}"
        )
        screen_env = _screen_control_environment()
    result = subprocess.run(
        ["screen", "-dmS", job.session, "/bin/bash", "-lc", command],
        capture_output=True,
        text=True,
        check=False,
        env=screen_env,
    )
    return {
        "attempted": True,
        "returncode": result.returncode,
        "stderr": result.stderr.strip()[-500:],
    }


def evaluate_job(job: Job, *, now: float, start_missing: bool) -> dict[str, Any]:
    sessions = _matching_sessions(job)
    launch = {"attempted": False, "returncode": None, "stderr": ""}
    runtime_missing = [
        str(path)
        for path in job.runtime_requirements
        if not path.is_file() or not os.access(path, os.X_OK)
    ]
    if not sessions and start_missing and not runtime_missing:
        launch = _start(job)
        time.sleep(0.35)
        sessions = _matching_sessions(job)

    evidence_pattern = Path(job.evidence)
    if evidence_pattern.is_absolute():
        evidence_candidates = [evidence_pattern] if evidence_pattern.exists() else []
    else:
        evidence_candidates = sorted(ROOT.glob(job.evidence))
    evidence_path = (
        max(evidence_candidates, key=lambda item: item.stat().st_mtime)
        if evidence_candidates
        else ROOT / job.evidence
    )
    exists = evidence_path.is_file()
    modified = evidence_path.stat().st_mtime if exists else None
    age = max(0.0, now - modified) if modified is not None else None
    fresh = bool(age is not None and age <= job.max_age_seconds)
    process_alive = bool(sessions)
    if runtime_missing:
        state = "blocked_runtime"
    elif process_alive and fresh:
        state = "healthy"
    elif process_alive and not exists:
        state = "starting"
    elif process_alive:
        state = "degraded_stale_evidence"
    elif fresh:
        state = "stopped_with_fresh_evidence"
    else:
        state = "stopped"
    return {
        "name": job.name,
        "state": state,
        "process_alive": process_alive,
        "screen_sessions": sessions,
        "session_markers": list(job.session_markers),
        "session": job.session,
        "research_only": True,
        "live_order_authority": False,
        "evidence_path": (
            str(evidence_path.relative_to(ROOT))
            if evidence_path.is_relative_to(ROOT)
            else str(evidence_path)
        ),
        "evidence_paths": list(job.evidence_paths or (job.evidence,)),
        "evidence_exists": exists,
        "evidence_age_seconds": round(age, 3) if age is not None else None,
        "evidence_max_age_seconds": job.max_age_seconds,
        "evidence_fresh": fresh,
        "launch": launch,
        "runtime_missing": runtime_missing,
    }


def run_cycle(*, start_missing: bool) -> dict[str, Any]:
    now = time.time()
    manifest = load_canonical_manifest()
    epoch = os.environ.get("RESEARCH_STATION_EVIDENCE_EPOCH", "")
    configured_jobs = (
        jobs_from_manifest(manifest, epoch=epoch, project_root=ROOT)
        if epoch
        else JOBS
    )
    jobs = [
        evaluate_job(job, now=now, start_missing=start_missing)
        for job in configured_jobs
    ]
    source_hashes, run_id_identities = _manifest_hashes(manifest, epoch=epoch)
    payload = canonical_status(
        jobs,
        epoch=epoch,
        source_hashes=source_hashes,
        run_id_identities=run_id_identities,
    )
    payload.update({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "supervisor_pid": os.getpid(),
        "summary": {
            "jobs": len(jobs),
            "healthy": sum(item["state"] == "healthy" for item in jobs),
            "degraded": sum(item["state"] != "healthy" for item in jobs),
        },
        "held_legacy_jobs": [
            {
                "name": str(row["name"]),
                "migration_mode": str(row.get("migration_mode")),
                "reason": str(row.get("migration_blocked_reason", "")),
            }
            for row in manifest["jobs"]
            if row.get("migration_mode") != "canonical"
        ],
    })
    _atomic_json(STATUS_PATH, payload)
    return payload


def _print_summary(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(
        f"research_station healthy={str(payload['healthy']).lower()} "
        f"jobs={summary['jobs']} ok={summary['healthy']} degraded={summary['degraded']}"
    )
    for item in payload["jobs"]:
        print(
            f"{item['name']}: {item['state']} "
            f"screens={','.join(item['screen_sessions']) or '-'} "
            f"evidence_age_sec={item['evidence_age_seconds']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-sec", type=int, default=300)
    parser.add_argument("--status-only", action="store_true")
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)

    with LOCK_PATH.open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"research station already running; status={STATUS_PATH}")
            if STATUS_PATH.is_file():
                try:
                    _print_summary(json.loads(STATUS_PATH.read_text(encoding="utf-8")))
                except (OSError, ValueError, KeyError):
                    pass
            return 0
        PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
        try:
            while True:
                payload = run_cycle(start_missing=not args.status_only)
                _print_summary(payload)
                if not args.loop:
                    return 0 if payload["healthy"] else 1
                time.sleep(max(30, args.interval_sec))
        finally:
            try:
                PID_PATH.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    sys.exit(main())
