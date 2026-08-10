#!/usr/bin/env python3
"""Record one non-secret broker/runtime incident for the project audit.

The ledger is evidence-only.  This script cannot call a broker, mutate live
configuration, change risk, or repair code.  Reusing an external id replaces
the previous record so scheduled reconciliation remains idempotent.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "runtime" / "project_audit" / "operational_incidents.jsonl"
ALLOWED_STATUSES = {"open", "confirmed", "dismissed", "resolved"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "info"}
FORBIDDEN_TERMS = ("api_key", "api secret", "secret_key", "access_token", "private_key")


def _record(args: argparse.Namespace) -> dict[str, Any]:
    values = {
        "external_id": args.external_id,
        "rule": args.rule,
        "severity": args.severity,
        "status": args.status,
        "current": not args.not_current,
        "where": args.where,
        "what": args.what,
        "why": args.why,
        "how_to_verify": args.how_to_verify,
        "how_to_falsify": args.how_to_falsify,
        "occurred_at_utc": args.occurred_at_utc,
        "evidence": args.evidence,
    }
    combined = " ".join(str(value).lower() for value in values.values())
    if any(term in combined for term in FORBIDDEN_TERMS):
        raise ValueError("incident text appears to contain a secret field; store only redacted evidence")
    return values


def upsert(path: Path, record: dict[str, Any]) -> None:
    existing: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("external_id") != record["external_id"]:
            existing.append(item)
    existing.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in existing),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=str(DEFAULT_PATH))
    parser.add_argument("--external-id", required=True)
    parser.add_argument("--rule", required=True)
    parser.add_argument("--severity", choices=sorted(ALLOWED_SEVERITIES), default="high")
    parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES), default="confirmed")
    parser.add_argument("--not-current", action="store_true")
    parser.add_argument("--where", required=True)
    parser.add_argument("--what", required=True)
    parser.add_argument("--why", required=True)
    parser.add_argument("--how-to-verify", required=True)
    parser.add_argument("--how-to-falsify", required=True)
    parser.add_argument("--occurred-at-utc", required=True)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    record = _record(args)
    path = Path(args.path).resolve()
    upsert(path, record)
    print(json.dumps({"recorded": record["external_id"], "path": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
