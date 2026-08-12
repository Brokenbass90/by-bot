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
import json
import os
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
RUNTIME = ROOT / "runtime" / "local_research_station"
STATUS_PATH = RUNTIME / "status.json"
PID_PATH = RUNTIME / "supervisor.pid"
LOCK_PATH = RUNTIME / "supervisor.lock"


@dataclass(frozen=True)
class Job:
    name: str
    session: str
    session_markers: tuple[str, ...]
    script: str
    evidence: str
    max_age_seconds: int


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
        "logs/xsec_v3_shadow_*.log",
        2 * 3600,
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


def _start(job: Job) -> dict[str, Any]:
    command = f"cd {shlex.quote(str(ROOT))} && exec /bin/bash {job.script}"
    result = subprocess.run(
        ["screen", "-dmS", job.session, "/bin/bash", "-lc", command],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "attempted": True,
        "returncode": result.returncode,
        "stderr": result.stderr.strip()[-500:],
    }


def evaluate_job(job: Job, *, now: float, start_missing: bool) -> dict[str, Any]:
    sessions = _matching_sessions(job)
    launch = {"attempted": False, "returncode": None, "stderr": ""}
    if not sessions and start_missing:
        launch = _start(job)
        time.sleep(0.35)
        sessions = _matching_sessions(job)

    evidence_pattern = Path(job.evidence)
    evidence_candidates = (
        [evidence_pattern]
        if evidence_pattern.is_absolute() and evidence_pattern.exists()
        else sorted(ROOT.glob(job.evidence))
    )
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
    if process_alive and fresh:
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
        "evidence_exists": exists,
        "evidence_age_seconds": round(age, 3) if age is not None else None,
        "evidence_max_age_seconds": job.max_age_seconds,
        "evidence_fresh": fresh,
        "launch": launch,
    }


def run_cycle(*, start_missing: bool) -> dict[str, Any]:
    now = time.time()
    jobs = [evaluate_job(job, now=now, start_missing=start_missing) for job in JOBS]
    healthy = all(item["state"] == "healthy" for item in jobs)
    payload = {
        "schema_id": "local_research_station_status_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "supervisor_pid": os.getpid(),
        "research_only": True,
        "live_order_authority": False,
        "healthy": healthy,
        "summary": {
            "jobs": len(jobs),
            "healthy": sum(item["state"] == "healthy" for item in jobs),
            "degraded": sum(item["state"] != "healthy" for item in jobs),
        },
        "jobs": jobs,
    }
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
