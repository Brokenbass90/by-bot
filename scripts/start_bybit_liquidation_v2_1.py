#!/usr/bin/env python3
"""Source-only V2.1 launcher; verify the pre-outcome 25-symbol frozen census."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def binding(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path.absolute(), *path.absolute().parents)):
        raise ValueError("UNIVERSE_SOURCE_SYMLINK")
    raw = path.read_bytes()
    if len(raw) > 12 * 1024**2: raise ValueError("UNIVERSE_SOURCE_RESOURCE_BOUND")
    universe = module("liq_v2_1_universe", "research_lab/bybit_liquidation_universe_v2_1.py").verify(json.loads(raw))
    driver = module("liq_v2_1_driver", "scripts/collect_bybit_liquidations_v2.py")
    pins = driver.source_pins()
    for name in ("scripts/start_bybit_liquidation_v2_1.py", "scripts/export_bybit_liquidation_v2_1.py",
                 "research_lab/bybit_liquidation_universe_v2_1.py", "deploy/bybit-liquidation-source-v2_1.service"):
        pins[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    pins["universe_manifest.json"] = hashlib.sha256(raw).hexdigest()
    return driver, universe, pins


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--root", type=Path,
        default=Path("/opt/bybot-research/liquidation-source-v2-1-20261014/runtime"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        driver, universe, pins = binding(args.universe)
        if args.verify_only:
            print(json.dumps(dict(status="V2_1_UNIVERSE_AND_CODE_VERIFIED_NOT_STARTED",
                 universe_sha256=universe["manifest_sha256"], symbols=universe["symbols"],
                 source_files=pins, orders_allowed=False))); return 0
        asyncio.run(driver.run(args.root, tuple(universe["symbols"]), pins))
        return 0
    except Exception as exc:
        print(json.dumps(dict(status="BLOCKED_SOURCE", reason=str(exc), orders_allowed=False)), file=sys.stderr)
        return 73 if str(exc) == "ALREADY_RUNNING" else 78


if __name__ == "__main__": raise SystemExit(main())
