#!/usr/bin/env python3
"""Verify current Bybit credentials and publish redacted web/AI status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bybit_credential_rotation import RotationError, verify_current_configuration


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="main")
    args = parser.parse_args()
    try:
        result = verify_current_configuration(repo_root=ROOT, account_name=args.account)
    except RotationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "applied_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
