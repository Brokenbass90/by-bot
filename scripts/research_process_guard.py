#!/usr/bin/env python3
"""Guard long-running research processes.

The nightly queue intentionally runs unattended. This guard keeps that queue
from being blocked for days by one stuck autoresearch/backtest subprocess.

Default mode is read-only. Use --repair from cron to terminate stale research
processes after the configured age limit.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "runtime" / "research_guard" / "status.json"
DEFAULT_HISTORY = ROOT / "runtime" / "research_guard" / "history.jsonl"


@dataclass
class ProcInfo:
    pid: int
    ppid: int
    etimes: int
    pcpu: float
    pmem: float
    command: str

    @property
    def kind(self) -> str:
        if "run_strategy_autoresearch.py" in self.command:
            return "autoresearch"
        if "backtest/run_portfolio.py" in self.command:
            return "portfolio_backtest"
        return "other"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _ps() -> list[ProcInfo]:
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid=,ppid=,etimes=,pcpu=,pmem=,command="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        raise RuntimeError(f"ps_failed:{exc}") from exc

    rows: list[ProcInfo] = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            etimes = int(float(parts[2]))
            pcpu = float(parts[3])
            pmem = float(parts[4])
        except Exception:
            continue
        cmd = parts[5]
        if "research_process_guard.py" in cmd:
            continue
        if "run_strategy_autoresearch.py" in cmd or "backtest/run_portfolio.py" in cmd:
            rows.append(ProcInfo(pid=pid, ppid=ppid, etimes=etimes, pcpu=pcpu, pmem=pmem, command=cmd))
    return rows


def _children_by_parent(procs: list[ProcInfo]) -> dict[int, list[ProcInfo]]:
    children: dict[int, list[ProcInfo]] = {}
    for p in procs:
        children.setdefault(p.ppid, []).append(p)
    return children


def _is_stale(p: ProcInfo, *, max_autoresearch_age: int, max_backtest_age: int) -> bool:
    if p.kind == "autoresearch":
        return p.etimes > max_autoresearch_age
    if p.kind == "portfolio_backtest":
        return p.etimes > max_backtest_age
    return False


def _terminate(pid: int, *, grace_sec: float = 3.0) -> dict[str, Any]:
    row: dict[str, Any] = {"pid": pid, "sent": []}
    try:
        os.kill(pid, signal.SIGTERM)
        row["sent"].append("TERM")
    except ProcessLookupError:
        row["gone_before_term"] = True
        return row
    except PermissionError as exc:
        row["error"] = f"term_permission:{exc}"
        return row
    time.sleep(max(0.1, grace_sec))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        row["terminated"] = True
        return row
    try:
        os.kill(pid, signal.SIGKILL)
        row["sent"].append("KILL")
        row["terminated"] = True
    except Exception as exc:
        row["error"] = f"kill_failed:{exc}"
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect and optionally repair stale research processes.")
    ap.add_argument("--repair", action="store_true", help="Terminate stale research/backtest processes.")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--max-autoresearch-age-sec", type=int, default=int(os.getenv("RESEARCH_MAX_AUTORESEARCH_AGE_SEC", "64800")))
    ap.add_argument("--max-backtest-age-sec", type=int, default=int(os.getenv("RESEARCH_MAX_BACKTEST_AGE_SEC", "21600")))
    ap.add_argument("--status-path", default=str(DEFAULT_STATUS))
    ap.add_argument("--history-path", default=str(DEFAULT_HISTORY))
    args = ap.parse_args()

    status_path = Path(args.status_path)
    history_path = Path(args.history_path)
    try:
        procs = _ps()
    except Exception as exc:
        payload = {"ts": _utc_now(), "status": "error", "error": str(exc)}
        _write_json(status_path, payload)
        if not args.quiet:
            print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
        return 1

    children = _children_by_parent(procs)
    stale = [
        p for p in procs
        if _is_stale(p, max_autoresearch_age=args.max_autoresearch_age_sec, max_backtest_age=args.max_backtest_age_sec)
    ]
    killed: list[dict[str, Any]] = []
    if args.repair and stale:
        # Kill children first, then parents, to avoid orphaned run_portfolio rows.
        targets: list[ProcInfo] = []
        for p in sorted(stale, key=lambda x: x.etimes, reverse=True):
            targets.extend(children.get(p.pid, []))
            targets.append(p)
        seen: set[int] = set()
        for p in targets:
            if p.pid in seen:
                continue
            seen.add(p.pid)
            killed.append({"process": asdict(p), "result": _terminate(p.pid)})

    payload = {
        "ts": _utc_now(),
        "status": "repaired" if killed else ("stale_found" if stale else "ok"),
        "repair": bool(args.repair),
        "max_autoresearch_age_sec": args.max_autoresearch_age_sec,
        "max_backtest_age_sec": args.max_backtest_age_sec,
        "active_count": len(procs),
        "stale_count": len(stale),
        "active": [asdict(p) for p in procs],
        "stale": [asdict(p) for p in stale],
        "killed": killed,
    }
    _write_json(status_path, payload)
    _append_jsonl(
        history_path,
        {
            "ts": payload["ts"],
            "status": payload["status"],
            "repair": payload["repair"],
            "active_count": payload["active_count"],
            "stale_count": payload["stale_count"],
            "killed_count": len(killed),
        },
    )
    if not args.quiet:
        print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
