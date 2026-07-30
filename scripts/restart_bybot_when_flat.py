#!/usr/bin/env python3
"""Restart the live bot only after Bybit confirms an empty account repeatedly."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from scripts import portfolio_status
except ImportError:  # Direct execution: python scripts/restart_bybot_when_flat.py
    import portfolio_status


def query_exchange_positions() -> list[dict[str, Any]]:
    accounts = portfolio_status._load_accounts()
    if not accounts:
        raise RuntimeError("BYBIT_ACCOUNTS_JSON is not configured")

    positions: list[dict[str, Any]] = []
    errors: list[str] = []
    for account in accounts:
        account_positions, error = portfolio_status._get_positions(account)
        if error:
            errors.append(f"{account.get('name', '?')}: {error}")
            continue
        positions.extend(account_positions)

    if errors:
        raise RuntimeError("; ".join(errors))
    return positions


def load_service_process_environment(
    service: str,
    *,
    get_main_pid: Callable[[str], int] | None = None,
    read_environ: Callable[[int], bytes] | None = None,
) -> bool:
    """Hydrate missing Bybit config from the already-running service.

    Some deployments inject credentials through systemd rather than the repo
    ``.env`` file. The flat gate must still query the same account as the live
    process, while never printing or persisting its secrets.
    """
    if os.getenv("BYBIT_ACCOUNTS_JSON"):
        return True

    if get_main_pid is None:
        def get_main_pid(unit: str) -> int:
            value = subprocess.check_output(
                ["systemctl", "show", "-p", "MainPID", "--value", unit],
                text=True,
            )
            return int(str(value).strip() or 0)

    if read_environ is None:
        def read_environ(pid: int) -> bytes:
            return open(f"/proc/{pid}/environ", "rb").read()

    try:
        pid = int(get_main_pid(service))
        if pid <= 0:
            return False
        entries = read_environ(pid).split(b"\0")
    except Exception:
        return False

    allowed = {"BYBIT_ACCOUNTS_JSON", "TRADE_ACCOUNT_NAME"}
    for entry in entries:
        if b"=" not in entry:
            continue
        key_raw, value_raw = entry.split(b"=", 1)
        key = key_raw.decode("utf-8", errors="ignore")
        if key not in allowed or not value_raw:
            continue
        os.environ.setdefault(key, value_raw.decode("utf-8", errors="ignore"))
    return bool(os.getenv("BYBIT_ACCOUNTS_JSON"))


def wait_until_flat(
    query: Callable[[], list[dict[str, Any]]],
    *,
    confirmations: int,
    interval_sec: float,
) -> None:
    consecutive_flat = 0
    while consecutive_flat < confirmations:
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            positions = query()
        except Exception as exc:
            consecutive_flat = 0
            print(f"[{timestamp}] position query failed; confirmation reset: {exc}", flush=True)
        else:
            consecutive_flat = consecutive_flat + 1 if not positions else 0
            print(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "open_positions": len(positions),
                        "symbols": [p.get("symbol") for p in positions],
                        "flat_confirmations": consecutive_flat,
                        "required_confirmations": confirmations,
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
        if consecutive_flat < confirmations:
            time.sleep(interval_sec)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirmations", type=int, default=3)
    parser.add_argument("--interval-sec", type=float, default=60.0)
    parser.add_argument("--service", default="bybot.service")
    args = parser.parse_args()

    if args.confirmations < 1:
        parser.error("--confirmations must be at least 1")
    if args.interval_sec < 1:
        parser.error("--interval-sec must be at least 1")

    load_service_process_environment(args.service)
    wait_until_flat(
        query_exchange_positions,
        confirmations=args.confirmations,
        interval_sec=args.interval_sec,
    )
    subprocess.run(["systemctl", "restart", args.service], check=True)
    time.sleep(5)
    subprocess.run(["systemctl", "is-active", "--quiet", args.service], check=True)
    print(f"restarted {args.service} after confirmed flat account", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
