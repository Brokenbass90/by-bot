#!/usr/bin/env python3
"""Run a risk-zero research backlog only when host load permits it."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "research" / "research_backlog_20260810.json"
DEFAULT_RUNTIME = ROOT / "runtime" / "research_backlog_20260810"
ALLOWED_PROGRAM = ".venv/bin/python"
ALLOWED_SCRIPTS = {"scripts/run_fx_native_harness.py"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo != timezone.utc:
        raise ValueError("deadline must be explicit UTC")
    return parsed


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _validate(cfg: dict[str, Any]) -> None:
    expected = {
        "research_only": True,
        "live_order_authority": False,
        "broker_calls": False,
        "risk_pct": 0,
    }
    if any(cfg.get(key) != value for key, value in expected.items()):
        raise ValueError("queue lost its risk-zero research contract")
    if not 0 < float(cfg["max_load_1m"]) <= max(1, os.cpu_count() or 1):
        raise ValueError("max_load_1m exceeds bounded host capacity")
    _parse_utc(str(cfg["deadline_utc"]))
    seen = set()
    for job in cfg.get("jobs") or []:
        job_id = str(job.get("id") or "")
        command = job.get("command")
        if not job_id or job_id in seen or not isinstance(command, list) or len(command) < 2:
            raise ValueError("invalid queue job")
        seen.add(job_id)
        if command[0] != ALLOWED_PROGRAM or command[1] not in ALLOWED_SCRIPTS:
            raise ValueError(f"command is not on the research-only allowlist: {job_id}")
        if any(str(token).startswith("--send-orders") or "live" == str(token).lower() for token in command):
            raise ValueError(f"live/order token forbidden: {job_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    runtime = Path(args.runtime_dir).resolve()
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    _validate(cfg)
    deadline = _parse_utc(str(cfg["deadline_utc"]))
    max_load = float(cfg["max_load_1m"])
    poll = max(30, int(cfg["poll_seconds"]))
    status_path = runtime / "status.json"
    logs_dir = runtime / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    completed: list[dict[str, Any]] = []

    for job in cfg["jobs"]:
        while True:
            load = os.getloadavg()
            now = _utc_now()
            if now >= deadline:
                status = {
                    "schema_id": "load_guarded_research_queue_status_v1",
                    "generated_at_utc": now.isoformat(),
                    "state": "deferred_deadline",
                    "research_only": True,
                    "live_order_authority": False,
                    "next_job": job["id"],
                    "completed": completed,
                    "load_average": list(load),
                }
                _write_atomic(status_path, status)
                return 0
            if load[0] <= max_load:
                break
            _write_atomic(
                status_path,
                {
                    "schema_id": "load_guarded_research_queue_status_v1",
                    "generated_at_utc": now.isoformat(),
                    "state": "waiting_for_load",
                    "research_only": True,
                    "live_order_authority": False,
                    "next_job": job["id"],
                    "completed": completed,
                    "load_average": list(load),
                    "max_load_1m": max_load,
                },
            )
            time.sleep(poll)

        started = _utc_now()
        log_path = logs_dir / f"{job['id']}.log"
        _write_atomic(
            status_path,
            {
                "schema_id": "load_guarded_research_queue_status_v1",
                "generated_at_utc": started.isoformat(),
                "state": "running",
                "research_only": True,
                "live_order_authority": False,
                "current_job": job["id"],
                "completed": completed,
                "load_average": list(os.getloadavg()),
            },
        )
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(
                [str(ROOT / job["command"][0]), str(ROOT / job["command"][1]), *map(str, job["command"][2:])],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                preexec_fn=lambda: os.nice(10),
            )
        completed.append(
            {
                "id": job["id"],
                "stage": job["stage"],
                "started_at_utc": started.isoformat(),
                "finished_at_utc": _utc_now().isoformat(),
                "returncode": result.returncode,
                "log": str(log_path.relative_to(ROOT)),
            }
        )
        if result.returncode != 0:
            _write_atomic(
                status_path,
                {
                    "schema_id": "load_guarded_research_queue_status_v1",
                    "generated_at_utc": _utc_now().isoformat(),
                    "state": "failed",
                    "research_only": True,
                    "live_order_authority": False,
                    "failed_job": job["id"],
                    "completed": completed,
                },
            )
            return result.returncode

    _write_atomic(
        status_path,
        {
            "schema_id": "load_guarded_research_queue_status_v1",
            "generated_at_utc": _utc_now().isoformat(),
            "state": "complete",
            "research_only": True,
            "live_order_authority": False,
            "completed": completed,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
