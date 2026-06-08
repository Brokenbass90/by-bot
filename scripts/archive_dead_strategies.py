#!/usr/bin/env python3
"""Safely archive truly-dead strategy files (Opus audit 2026-06-08).

A strategy file is "dead" only if its module name appears NOWHERE in active
code OR configs — not via `import`, and not as a string in the registry,
allocator policies, health gates, canary envs or sweep configs. The bot wires
many strategies dynamically by name, so import-only detection is unsafe.

This script re-verifies zero references at runtime before moving each file, and
defaults to a dry run. Nothing is touched on the live server — this only
restructures the repo (reversible via git).

Usage:
    python3 scripts/archive_dead_strategies.py            # dry-run (default)
    python3 scripts/archive_dead_strategies.py --apply    # perform git mv
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "archive" / "strategies_retired"

# Verified safe (zero references anywhere) as of 2026-06-08. Re-checked at runtime.
CANDIDATES = [
    "alt_bear_breakdown_v1",
    "alt_bear_consolidation_short_v1",
    "alt_stablecoin_depeg_arb_v1",
    "btc_daily_level_reclaim_v1",
    "btc_macro_cycle_v1",
    "btc_swing_zone_reclaim_v1",
    "btc_weekly_zone_reclaim_v2",
    "pump_fade_v3",
    "sc1_live",
]

SEARCH_DIRS = ["bot", "strategies", "scripts", "configs", "web"]
SEARCH_GLOBS = ["*.py"]  # plus root-level smart_pump file handled explicitly


def _ref_count(name: str) -> int:
    """Count references to `name` in active code/configs, excluding its own file."""
    cmd = [
        "grep", "-rl", name,
        "smart_pump_reversal_bot.py", *SEARCH_DIRS,
        "--include=*.py", "--include=*.json", "--include=*.env",
    ]
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout
    except Exception as e:
        print(f"  ! grep failed for {name}: {e}")
        return 999
    _self = "scripts/archive_dead_strategies.py"
    files = [f for f in out.splitlines() if f and f != f"strategies/{name}.py" and f != _self]
    return len(files)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="perform git mv (default: dry-run)")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    moved, skipped = 0, 0
    for name in CANDIDATES:
        src = ROOT / "strategies" / f"{name}.py"
        if not src.exists():
            print(f"  skip (missing): {name}")
            skipped += 1
            continue
        refs = _ref_count(name)
        if refs > 0:
            print(f"  SKIP (now referenced in {refs} file(s), unsafe): {name}")
            skipped += 1
            continue
        if args.apply:
            subprocess.run(["git", "mv", f"strategies/{name}.py",
                            f"archive/strategies_retired/{name}.py"], cwd=ROOT, check=True)
            print(f"  MOVED: {name}")
        else:
            print(f"  would move: strategies/{name}.py -> archive/strategies_retired/{name}.py")
        moved += 1

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {moved} to move, {skipped} skipped.")
    if not args.apply:
        print("Re-run with --apply to perform. After applying: py_compile smart_pump_reversal_bot.py and run tests/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
