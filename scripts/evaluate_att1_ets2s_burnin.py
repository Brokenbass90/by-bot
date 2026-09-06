#!/usr/bin/env python3
"""Evaluate a local ATT1/ETS2S snapshot; never call a network or broker."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.att1_ets2s_burnin import evaluate_burnin


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--deployment-receipt", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="New receipt path; existing files are refused")
    args = parser.parse_args(argv)
    result = evaluate_burnin(args.snapshot_dir, args.deployment_receipt)
    encoded = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("ascii")
    if args.output is not None:
        try:
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            print(f"Cannot create new receipt: {type(exc).__name__}", file=sys.stderr)
            return 2
    print(encoded.decode("ascii"), end="")
    # Zero means successful evaluation. Consumers must inspect status; an
    # IN_PROGRESS receipt is never operational PASS or promotion authority.
    return 0 if result["status"] in {"IN_PROGRESS", "PASS_OPERATIONAL_BURN_IN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
