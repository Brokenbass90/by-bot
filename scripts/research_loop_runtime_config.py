#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Mapping


AUTHORITY = "research_only_no_live_or_promotion"
REQUIRED_ENV = {
    "RESEARCH_ONLY": "true",
    "PROMOTION_AUTHORITY": "false",
    "NETWORK_AUTHORITY": "false",
    "PRIVATE_API_AUTHORITY": "false",
    "ORDER_AUTHORITY": "false",
    "LIVE_WRITE_AUTHORITY": "false",
    "PUBLIC_DATA_READ_AUTHORITY": "true",
}


def validate_authority_env(environ: Mapping[str, str]) -> None:
    failures = [key for key, value in REQUIRED_ENV.items() if environ.get(key) != value]
    epoch = environ.get("RESEARCH_STATION_EVIDENCE_EPOCH", "")
    if failures or not epoch:
        raise SystemExit(
            "unsafe canonical authority env: "
            + ",".join(failures or ["RESEARCH_STATION_EVIDENCE_EPOCH"])
        )


def validate_paths(runtime_dir: Path, write_paths: list[Path]) -> list[Path]:
    root = runtime_dir.resolve()
    resolved = [path.resolve() for path in write_paths]
    for path in resolved:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"write path escapes runtime dir: {path}") from exc
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--write-path", type=Path, action="append", default=[])
    parser.add_argument("--validate-env", action="store_true")
    args = parser.parse_args()
    paths = validate_paths(args.runtime_dir, args.write_path)
    if args.validate_env:
        validate_authority_env(os.environ)
    print(
        json.dumps(
            {
                "runtime_dir": str(args.runtime_dir.resolve()),
                "write_paths": [str(path) for path in paths],
                "authority": AUTHORITY,
                "promotion_authority": False,
                "network_authority": False,
                "private_api_authority": False,
                "order_authority": False,
                "live_write_authority": False,
                "public_data_read_authority": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
