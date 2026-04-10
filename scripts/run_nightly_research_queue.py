#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "research_nightly_queue.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.deepseek_research_gate import ResearchGate


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _repo_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python3"
    if venv_python.exists() and os.access(venv_python, os.X_OK):
        return str(venv_python)
    return sys.executable


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _hours_since(raw: str | None, now: datetime) -> float | None:
    dt = _parse_ts(raw)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def _active_research_lines() -> list[str]:
    try:
        out = subprocess.check_output(
            ["pgrep", "-fal", "run_strategy_autoresearch.py"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _within_quiet_window(config: dict[str, Any], now: datetime) -> tuple[bool, str]:
    window = dict(config.get("quiet_window_utc") or {})
    if not bool(window.get("enabled", False)):
        return True, "disabled"
    try:
        start_hour = int(window.get("start_hour", 0))
        end_hour = int(window.get("end_hour", 0))
    except Exception:
        return True, "invalid_config"
    hour = int(now.hour)
    if start_hour == end_hour:
        return True, "full_day"
    if start_hour < end_hour:
        ok = start_hour <= hour < end_hour
    else:
        ok = hour >= start_hour or hour < end_hour
    return ok, f"{start_hour:02d}:00-{end_hour:02d}:00"


def _task_active(task: dict[str, Any], active_lines: list[str]) -> bool:
    spec_name = Path(str(task.get("spec") or "")).name
    return any(spec_name in line for line in active_lines)


def _launch_task(spec_path: Path, log_dir: Path, *, nice_level: int = 10) -> int:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{spec_path.stem}_{stamp}.log"
    log_file = log_path.open("a", encoding="utf-8")
    cmd = [
        "nice",
        "-n",
        str(max(0, int(nice_level))),
        _repo_python(),
        "scripts/run_strategy_autoresearch.py",
        "--spec",
        str(spec_path),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return int(proc.pid)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a bounded nightly research queue.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    config_path = Path(args.config).resolve()
    config = _load_json(config_path, {})
    if not config.get("enabled", True):
        if not args.quiet:
            print("nightly research queue disabled")
        return 0

    gate = ResearchGate()
    now = _utc_now()
    status_path = ROOT / str(config.get("status_path") or "runtime/research_nightly/status.json")
    history_path = ROOT / str(config.get("history_path") or "runtime/research_nightly/history.jsonl")
    log_dir = ROOT / str(config.get("log_dir") or "logs/research_nightly")
    default_min_interval = float(config.get("default_min_interval_hours") or 24)
    max_active = int(config.get("max_active_processes") or 1)
    max_launches = int(config.get("max_launches_per_run") or 1)
    nice_level = int(config.get("nice_level") or 10)
    tasks = list(config.get("tasks") or [])

    prev_status = _load_json(status_path, {})
    prev_tasks = dict((prev_status.get("tasks") or {}).items()) if isinstance(prev_status, dict) else {}
    active_lines = _active_research_lines()
    active_count = len(active_lines)

    run_status: dict[str, Any] = {
        "ts": now.isoformat(),
        "config": str(config_path),
        "active_process_count": active_count,
        "active_processes": active_lines,
        "max_active_processes": max_active,
        "launched": [],
        "proposed": [],
        "blocked": [],
        "skipped": [],
        "tasks": {},
    }

    in_window, window_label = _within_quiet_window(config, now)
    run_status["quiet_window_utc"] = {
        "enabled": bool(dict(config.get("quiet_window_utc") or {}).get("enabled", False)),
        "window": window_label,
        "in_window": bool(in_window),
        "current_hour_utc": int(now.hour),
    }

    if not in_window:
        run_status["state"] = "outside_window"
        _write_json(status_path, run_status)
        _append_jsonl(
            history_path,
            {
                "ts": now.isoformat(),
                "state": "outside_window",
                "active_process_count": active_count,
                "window": window_label,
                "current_hour_utc": int(now.hour),
            },
        )
        if not args.quiet:
            print(f"skip: outside quiet window {window_label} UTC")
        return 0

    if active_count >= max_active:
        run_status["state"] = "busy_skip"
        _write_json(status_path, run_status)
        _append_jsonl(history_path, {"ts": now.isoformat(), "state": "busy_skip", "active_process_count": active_count})
        if not args.quiet:
            print(f"skip: {active_count} active research processes >= limit {max_active}")
        return 0

    launches = 0
    for task in tasks:
        name = str(task.get("name") or Path(str(task.get("spec") or "")).stem)
        spec_rel = str(task.get("spec") or "")
        spec_path = (ROOT / spec_rel).resolve()
        task_status: dict[str, Any] = {
            "name": name,
            "spec": spec_rel,
            "enabled": bool(task.get("enabled", True)),
            "state": "pending",
        }
        run_status["tasks"][name] = task_status

        if not task_status["enabled"]:
            task_status["state"] = "disabled"
            run_status["skipped"].append({"name": name, "reason": "disabled"})
            continue
        if not spec_rel or not spec_path.exists():
            task_status["state"] = "missing_spec"
            run_status["blocked"].append({"name": name, "reason": "missing_spec", "spec": spec_rel})
            continue
        if _task_active(task, active_lines):
            task_status["state"] = "already_active"
            run_status["skipped"].append({"name": name, "reason": "already_active"})
            continue

        min_interval = float(task.get("min_interval_hours") or default_min_interval)
        prev_task = prev_tasks.get(name, {}) if isinstance(prev_tasks, dict) else {}
        last_touch = (
            prev_task.get("last_launched_at")
            or prev_task.get("last_proposed_at")
            or prev_task.get("last_checked_at")
        )
        elapsed = _hours_since(last_touch, now)
        if elapsed is not None and elapsed < min_interval:
            task_status["state"] = "cooldown"
            task_status["cooldown_hours_left"] = round(min_interval - elapsed, 2)
            run_status["skipped"].append({"name": name, "reason": "cooldown", "hours_left": task_status["cooldown_hours_left"]})
            continue

        if gate.is_blocked(str(spec_path)):
            task_status["state"] = "blocked_by_gate"
            task_status["last_checked_at"] = now.isoformat()
            run_status["blocked"].append({"name": name, "reason": "blocked_by_gate"})
            continue

        if launches >= max_launches:
            task_status["state"] = "deferred"
            run_status["skipped"].append({"name": name, "reason": "launch_limit"})
            continue

        if gate.can_run(str(spec_path)):
            if args.dry_run:
                task_status["state"] = "would_launch"
                task_status["last_checked_at"] = now.isoformat()
                run_status["launched"].append({"name": name, "spec": spec_rel, "dry_run": True})
            else:
                pid = _launch_task(spec_path, log_dir, nice_level=nice_level)
                task_status["state"] = "launched"
                task_status["pid"] = pid
                task_status["last_launched_at"] = now.isoformat()
                run_status["launched"].append({"name": name, "spec": spec_rel, "pid": pid})
            launches += 1
            continue

        if args.dry_run:
            task_status["state"] = "would_propose"
            task_status["last_checked_at"] = now.isoformat()
            run_status["proposed"].append({"name": name, "spec": spec_rel, "dry_run": True})
        else:
            proposal_id = gate.propose(str(spec_path), reason="Nightly bounded research queue")
            task_status["state"] = "proposed"
            task_status["proposal_id"] = proposal_id
            task_status["last_proposed_at"] = now.isoformat()
            run_status["proposed"].append({"name": name, "spec": spec_rel, "proposal_id": proposal_id})
        launches += 1

    run_status["state"] = "ok"
    _write_json(status_path, run_status)
    _append_jsonl(
        history_path,
        {
            "ts": now.isoformat(),
            "state": run_status["state"],
            "active_process_count": active_count,
            "launched": len(run_status["launched"]),
            "proposed": len(run_status["proposed"]),
            "blocked": len(run_status["blocked"]),
        },
    )
    if not args.quiet:
        print(json.dumps(run_status, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
