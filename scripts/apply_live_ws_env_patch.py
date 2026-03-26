#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


UPDATES = {
    "TOP_N_BYBIT": "60",
    "BYBIT_WS_SHARD_SIZE": "30",
    "BYBIT_WS_BATCH_SIZE": "5",
    "BYBIT_WS_BATCH_DELAY": "2.2",
    "BYBIT_WS_START_STAGGER": "2.5",
    "BYBIT_WS_PING_INTERVAL": "25",
    "BYBIT_WS_PING_TIMEOUT": "75",
    "BYBIT_WS_OPEN_TIMEOUT": "75",
    "BYBIT_WS_CLOSE_TIMEOUT": "15",
    "BYBIT_WS_RECONNECT_MIN_SEC": "8",
    "BYBIT_WS_RECONNECT_MAX_SEC": "90",
    "BYBIT_WS_RECONNECT_JITTER_SEC": "3.0",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Patch live .env with calmer Bybit WS settings.")
    ap.add_argument("--env", default="/root/by-bot/.env", help="Path to target .env file.")
    args = ap.parse_args()

    path = Path(args.env)
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in UPDATES:
                out.append(f"{key}={UPDATES[key]}")
                seen.add(key)
                continue
        out.append(line)

    for key, value in UPDATES.items():
        if key not in seen:
            out.append(f"{key}={value}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"patched={path}")
    for key in sorted(UPDATES):
        print(f"{key}={UPDATES[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
