#!/usr/bin/env python3
"""Import the staged live monolith with order and private API paths disabled."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path


SAFE_ENV = {
    "DRY_RUN": "1",
    "ENABLE_BYBIT": "0",
    "ENABLE_BINANCE": "0",
    "ENABLE_MEXC": "0",
    "TG_COMMANDS_ENABLE": "0",
    "REPORTS_ENABLE": "0",
    "REGIME_OVERLAY_ENABLE": "0",
    "PORTFOLIO_ALLOCATOR_ENABLE": "0",
    "ALLOW_OPERATOR_LIVE_OVERRIDES": "0",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-main", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    if not (root / "smart_pump_reversal_bot.py").is_file():
        raise SystemExit(f"staged monolith missing: {root}")

    os.environ.update(SAFE_ENV)
    os.chdir(root)
    sys.path.insert(0, str(root))

    module = importlib.import_module("smart_pump_reversal_bot")
    imported = Path(module.__file__).resolve()
    if root not in imported.parents:
        raise SystemExit(f"wrong monolith imported: {imported}")
    if not module.DRY_RUN:
        raise SystemExit("no-order import contract did not resolve")

    # Market-source switches are still hard-coded at module scope in the legacy
    # monolith. Neutralise them explicitly before an optional bounded main-loop
    # smoke; DRY_RUN independently blocks private trading calls.
    module.TRADE_ON = False
    module.ENABLE_BYBIT = False
    module.ENABLE_BINANCE = False
    module.ENABLE_MEXC = False
    module.TG_COMMANDS_ENABLE = False
    module.REPORTS_ENABLE = False

    dependency_paths = {}
    for name in (
        "bot.maker_execution",
        "bot.att1_challenger",
        "bot.health_truth",
        "bot.portfolio_equity_guard",
        "bot.strategy_regime_gate",
        "bot.strategy_shadow_ledger",
    ):
        dependency = importlib.import_module(name)
        path = Path(dependency.__file__).resolve()
        if root not in path.parents:
            raise SystemExit(f"dependency escaped stage: {name} -> {path}")
        dependency_paths[name] = str(path.relative_to(root))

    print(
        json.dumps(
            {
                "schema_id": "staged_live_import_smoke_v1",
                "status": "PASS",
                "dry_run": bool(module.DRY_RUN),
                "public_market_sources_enabled": False,
                "monolith": str(imported.relative_to(root)),
                "dependencies": dependency_paths,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if args.run_main:
        print("STAGED_NO_ORDER_MAIN_START", flush=True)
        module.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
