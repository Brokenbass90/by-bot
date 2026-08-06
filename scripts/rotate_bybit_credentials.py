#!/usr/bin/env python3
"""Interactive Bybit credential rotation; secrets never appear in argv or logs."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bybit_credential_rotation import RotationError, rotate_and_optionally_apply


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="main")
    parser.add_argument("--no-restart", action="store_true", help="store validated credentials but do not restart")
    args = parser.parse_args()
    key = getpass.getpass("New Bybit API key: ").strip()
    secret = getpass.getpass("New Bybit API secret: ").strip()
    if len(key) < 12 or len(secret) < 20:
        parser.error("key or secret looks too short")
    try:
        result = rotate_and_optionally_apply(
            repo_root=ROOT,
            account_name=args.account,
            new_key=key,
            new_secret=secret,
            apply_when_flat=not args.no_restart,
        )
    except RotationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
