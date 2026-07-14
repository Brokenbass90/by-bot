#!/usr/bin/env python3
"""Read-only deterministic validator for Bybit L2/publicTrade tape.

The command never repairs, rewrites, compresses, or deletes tape.  A successful
exit means every selected book segment can be reconstructed around its explicit
gap markers and every selected trade row satisfies the persisted wire contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bybit_l2_tape import (  # noqa: E402
    SUPPORTED_DEPTHS,
    TapeError,
    normalize_symbols,
    select_partition_file,
    validate_tape_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry/read-only deterministic replay validation for Bybit tape",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", action="append", type=Path, help="explicit .jsonl/.zst tape file; repeatable")
    source.add_argument("--day", help="UTC partition day YYYYMMDD (requires --root/--symbol)")
    parser.add_argument("--root", type=Path, default=Path("runtime/tape"))
    parser.add_argument("--symbol", help="expected symbol, required with --day")
    parser.add_argument("--stream", choices=("book", "trades", "both"), default="both")
    parser.add_argument("--depth", type=int, choices=SUPPORTED_DEPTHS, default=200)
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--require-no-gaps", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit receipt that validation is read-only (validation is always read-only)",
    )
    return parser


def _resolve_files(args: argparse.Namespace) -> tuple[List[Path], Optional[str], Optional[str]]:
    if args.file:
        return [path.expanduser().resolve(strict=True) for path in args.file], (
            normalize_symbols([args.symbol])[0] if args.symbol else None
        ), None
    day = str(args.day or "")
    if len(day) != 8 or not day.isdigit():
        raise ValueError("--day must be YYYYMMDD")
    if not args.symbol:
        raise ValueError("--symbol is required with --day")
    symbol = normalize_symbols([args.symbol])[0]
    streams = ("book", "trades") if args.stream == "both" else (args.stream,)
    root = args.root.expanduser().resolve(strict=True)
    return [select_partition_file(root, symbol=symbol, day=day, stream=stream) for stream in streams], symbol, day


def validate_cli(args: argparse.Namespace) -> Dict[str, Any]:
    if not 0 <= float(args.min_coverage) <= 1:
        raise ValueError("--min-coverage must be in [0,1]")
    files, symbol, day = _resolve_files(args)
    results: List[Dict[str, Any]] = []
    blockers: List[str] = []
    for path in files:
        result = validate_tape_file(path, symbol=symbol, depth=args.depth)
        result["bytes"] = path.stat().st_size
        if day and result.get("recv_utc_days") != [day]:
            result.setdefault("errors", []).append(
                f"partition contains receive UTC days {result.get('recv_utc_days')}, expected {[day]}"
            )
            result["valid"] = False
        coverage_key = "valid_coverage" if result["stream"] == "book" else "connected_coverage"
        coverage = float(result.get(coverage_key) or 0.0)
        result["coverage_gate"] = {
            "metric": coverage_key,
            "actual": coverage,
            "minimum": float(args.min_coverage),
            "pass": coverage >= float(args.min_coverage),
        }
        if not result["valid"]:
            blockers.append(f"invalid:{path}")
        if not result["coverage_gate"]["pass"]:
            blockers.append(f"coverage_below_minimum:{path}")
        if args.require_no_gaps and int(result.get("gaps") or 0) > 0:
            blockers.append(f"gap_present:{path}")
        results.append(result)
    return {
        "kind": "bybit_l2_tape_read_only_validation_v1",
        "read_only": True,
        "dry_run_requested": bool(args.dry_run),
        "files_written": False,
        "network_calls": False,
        "valid": not blockers,
        "blockers": blockers,
        "results": results,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        receipt = validate_cli(parser.parse_args(argv))
        print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if receipt["valid"] else 1
    except (TapeError, ValueError, OSError) as exc:
        print(f"validation blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
