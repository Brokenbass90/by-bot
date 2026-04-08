#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


UPDATES = {
    "REGIME_OVERLAY_ENABLE": "1",
    "ROUTER_HEALTH_ENABLE": "1",
    "PORTFOLIO_ALLOCATOR_ENABLE": "1",
    "REGIME_OVERLAY_MAX_AGE_SEC": "7200",
    "ROUTER_OVERLAY_MAX_AGE_SEC": "28800",
    "ROUTER_STATE_MAX_AGE_SEC": "28800",
    "PORTFOLIO_ALLOCATOR_MAX_AGE_SEC": "10800",
    "ORCH_BULL_TREND_FLAT_ER_MAX": "0.55",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Patch live .env with control-plane safety settings.")
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
