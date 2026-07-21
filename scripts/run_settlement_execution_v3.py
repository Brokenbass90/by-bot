#!/usr/bin/env python3
"""Run one offline/public-only settlement_execution_v3 research cycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from settlement_execution_v3 import SettlementExecutionV3Supervisor
except ImportError:  # pragma: no cover - module execution from repository root
    from scripts.settlement_execution_v3 import SettlementExecutionV3Supervisor


ROOT = Path(__file__).resolve().parents[1]


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only v3 funding station from a local bundle of "
            "normalized public exchange responses"
        )
    )
    parser.add_argument("--public-bundle", required=True)
    parser.add_argument(
        "--config",
        default="configs/preregistered/settlement_execution_v3_research_v1.json",
    )
    parser.add_argument(
        "--runtime-root",
        default="runtime/arb/settlement_execution_v3",
    )
    args = parser.parse_args()

    bundle_path = _resolve(args.public_bundle)
    with bundle_path.open("r", encoding="utf-8") as handle:
        bundle = json.load(handle)
    if not isinstance(bundle, dict):
        raise SystemExit("public bundle root must be a JSON object")
    result = SettlementExecutionV3Supervisor(
        runtime_root=_resolve(args.runtime_root),
        config_path=_resolve(args.config),
    ).run(bundle)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
