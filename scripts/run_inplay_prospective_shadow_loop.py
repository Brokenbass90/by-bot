#!/usr/bin/env python3
"""Single-instance public-data supervisor for the ETH Inplay shadow collector."""
from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import IO


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "inplay_prospective_shadow_v1"
LOCK_PATH = RUNTIME / "collector.flock"
LOG_PATH = ROOT / "logs" / "inplay_prospective_shadow_v1.log"
INTERVAL_SECONDS = 900
PARITY_RECEIPT = RUNTIME / "historical_frequency_startup_gate.json"


def run_historical_frequency_gate() -> tuple[bool, str]:
    """Require exact pre-holdout frequency parity before collecting forward data."""
    tmp = PARITY_RECEIPT.with_suffix(".tmp")
    command = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scripts" / "audit_inplay_prospective_parity.py"),
        "--slice-days", "35",
        "--slices", "4",
        "--output", str(tmp),
        "--require-frozen-baseline",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        tmp.unlink(missing_ok=True)
        detail = (completed.stderr or completed.stdout or "unknown parity failure").strip()
        return False, detail[-1200:]
    try:
        payload = json.loads(tmp.read_text(encoding="utf-8"))
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return False, f"invalid parity receipt: {type(exc).__name__}"
    payload["startup_gate"] = "PASS"
    payload["collector_authority"] = "research_only_no_orders"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(PARITY_RECEIPT)
    return True, ""


def acquire_single_instance(path: Path = LOCK_PATH) -> IO[str] | None:
    """Return a held advisory lock or None when another supervisor owns it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle


def run_loop(*, interval_seconds: int = INTERVAL_SECONDS) -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = acquire_single_instance()
    if lock_handle is None:
        print(f"inplay prospective collector already running: {LOCK_PATH}")
        return 0
    parity_ok, parity_error = run_historical_frequency_gate()
    if not parity_ok:
        print(f"inplay prospective startup blocked by historical parity: {parity_error}")
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()
        return 2
    command = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scripts" / "collect_inplay_prospective_shadow.py"),
        "--allow-public-network",
    ]
    try:
        with LOG_PATH.open("ab", buffering=0) as log_handle:
            while True:
                subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                time.sleep(max(1, int(interval_seconds)))
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(run_loop())
