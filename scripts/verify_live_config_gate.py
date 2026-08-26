#!/usr/bin/env python3
"""Manifest-driven, secret-free P5 verification.

Exit codes: 0 = exact PASS, 2 = FAIL/BLOCKED.  The command never imports the
trading monolith and never contacts a broker; it is safe to run in CI or on a
server as a read-only gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.live_caller_parity_gate import (
    ParityGateViolation,
    load_env_mapping,
    load_verified_runtime_journal,
    verify_fixed51_runtime_cycles,
    verify_live_config,
)


DEFAULT_MANIFEST = ROOT / "configs/research/att1_sbr1_fixed51_evidence_parity_v1.json"
DEFAULT_ENV = ROOT / "configs/approved_strategy_params.env"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument("--att1-journal", type=Path, default=None)
    parser.add_argument("--sbr1-journal", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = (args.manifest or (root / DEFAULT_MANIFEST.relative_to(ROOT))).resolve()
    env_file = (args.env_file or (root / DEFAULT_ENV.relative_to(ROOT))).resolve()
    actual = load_env_mapping(env_file)
    contract = json.loads(manifest.read_text(encoding="utf-8"))["effective_config_contract"]
    # Only contract keys are retained: an accidental secret in an env file is
    # never copied to stdout or the receipt.
    actual_contract = {key: actual[key] for key in contract if key in actual}
    report = verify_live_config(root, manifest, actual_contract)
    if bool(args.att1_journal) != bool(args.sbr1_journal):
        report = {
            **report,
            "decision": "BLOCKED",
            "fail_codes": [*report.get("fail_codes", []), "runtime_journal_pair_required"],
        }
    elif args.att1_journal and args.sbr1_journal:
        try:
            runtime = verify_fixed51_runtime_cycles(
                load_verified_runtime_journal(args.att1_journal, sleeve="ATT1"),
                load_verified_runtime_journal(args.sbr1_journal, sleeve="SBR1"),
            )
        except ParityGateViolation as exc:
            report = {
                **report,
                "decision": "BLOCKED",
                "fail_codes": [*report.get("fail_codes", []), str(exc)],
            }
        else:
            report["runtime_coverage"] = runtime
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    print(encoded)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(encoded + "\n", encoding="utf-8")
    return 0 if report.get("decision") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
