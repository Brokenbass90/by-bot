#!/usr/bin/env python3
"""Research-only supervisor for ATT1 passive-entry paper evidence."""
from __future__ import annotations

import fcntl
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "att1_limit_execution_paper"
LOCK = RUNTIME / "collector.flock"
LOG = ROOT / "logs" / "att1_limit_execution_paper.log"


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("ATT1 limit paper collector already running")
        return 0
    command = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scripts" / "replay_att1_limit_execution_paper.py"),
    ]
    try:
        with LOG.open("ab", buffering=0) as log:
            while True:
                subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
                time.sleep(900)
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
