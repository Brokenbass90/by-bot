#!/usr/bin/env python3
"""Single-instance public-data supervisor for the ETH Inplay shadow collector."""
from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import IO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research_loop_runtime_config import (
    validate_authority_env,
    validate_paths,
)

RUNTIME = ROOT / "runtime" / "inplay_prospective_shadow_v1"
LOCK_PATH = RUNTIME / "collector.flock"
LOG_PATH = ROOT / "logs" / "inplay_prospective_shadow_v1.log"
INTERVAL_SECONDS = 900
PARITY_RECEIPT = RUNTIME / "historical_frequency_startup_gate.json"


def run_historical_frequency_gate(runtime_dir: Path = RUNTIME) -> tuple[bool, str]:
    """Require exact pre-holdout frequency parity before collecting forward data."""
    parity_receipt = runtime_dir / "historical_frequency_startup_gate.json"
    tmp = parity_receipt.with_suffix(".tmp")
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
    tmp.replace(parity_receipt)
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


def run_loop(
    *, runtime_dir: Path = RUNTIME, interval_seconds: int = INTERVAL_SECONDS
) -> int:
    runtime_dir = runtime_dir.resolve()
    lock_path = runtime_dir / "collector.flock"
    log_path = runtime_dir / "logs/collector.log"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = acquire_single_instance(lock_path)
    if lock_handle is None:
        print(f"inplay prospective collector already running: {lock_path}")
        return 0
    parity_ok, parity_error = run_historical_frequency_gate(runtime_dir)
    if not parity_ok:
        print(f"inplay prospective startup blocked by historical parity: {parity_error}")
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()
        return 2
    command = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scripts" / "collect_inplay_prospective_shadow.py"),
        "--allow-public-network",
        "--runtime-dir", str(runtime_dir),
    ]
    try:
        with log_path.open("ab", buffering=0) as log_handle:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=RUNTIME)
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=INTERVAL_SECONDS)
    args = parser.parse_args()
    runtime_dir = args.runtime_dir.resolve()
    write_paths = [
        runtime_dir / "collector.flock",
        runtime_dir / "historical_frequency_startup_gate.json",
        runtime_dir / "status.json",
        runtime_dir / "ledger.jsonl",
        runtime_dir / "logs/collector.log",
    ]
    validate_paths(runtime_dir, write_paths)
    if args.print_config:
        print(json.dumps({
            "runtime_dir": str(runtime_dir),
            "write_paths": [str(path) for path in write_paths],
            "authority": "research_only_no_live_or_promotion",
            "promotion_authority": False,
            "network_authority": False,
            "private_api_authority": False,
            "order_authority": False,
            "live_write_authority": False,
            "public_data_read_authority": True,
        }, sort_keys=True))
        return 0
    if runtime_dir != RUNTIME.resolve():
        validate_authority_env(os.environ)
    return run_loop(runtime_dir=runtime_dir, interval_seconds=args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
