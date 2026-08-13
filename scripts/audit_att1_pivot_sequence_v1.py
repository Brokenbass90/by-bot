#!/usr/bin/env python3
"""Independent arithmetic and provenance audit for ATT1 pivot-sequence V1."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.run_passport import sha256_file, validate_passport


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _trade_metrics(path: Path) -> dict[str, Any]:
    rows = _csv(path)
    net_r = 0.0
    gains = 0.0
    losses = 0.0
    by_symbol: dict[str, float] = {}
    bad_risk = 0
    for row in rows:
        pnl = float(row["pnl"])
        risk = float(row["initial_risk_usd"])
        if not math.isfinite(risk) or risk <= 0:
            bad_risk += 1
            continue
        value = pnl / risk
        net_r += value
        symbol = row["symbol"]
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + value
        gains += max(0.0, pnl)
        losses += -min(0.0, pnl)
    return {
        "trades": len(rows),
        "bad_initial_risk_rows": bad_risk,
        "net_r": net_r,
        "net_r_per_trade": net_r / len(rows) if rows else None,
        "profit_factor": gains / losses if losses else (float("inf") if gains else 0.0),
        "by_symbol_net_r": by_symbol,
        "sha256": sha256_file(path),
    }


def audit(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    passport_path = root / "run_passport.json"
    result_path = root / "result.json"
    passport = validate_passport(json.loads(passport_path.read_text(encoding="utf-8")))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for row in passport["code"]:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            failures.append(f"code_hash:{Path(row['path']).name}")
    for row in passport["inputs"]:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            failures.append(f"input_hash:{Path(row['path']).name}")
    if passport.get("sealed_holdout_rows_decoded") != 0 or result.get("sealed_holdout_rows_decoded") != 0:
        failures.append("sealed_holdout_contract")
    if result.get("capital_authorized") is not False:
        failures.append("capital_authority")

    computed = {
        "baseline": _trade_metrics(root / "baseline_trades.csv"),
        "challenger": _trade_metrics(root / "challenger_trades.csv"),
    }
    for arm, metrics in computed.items():
        recorded = result[arm]
        if metrics["bad_initial_risk_rows"]:
            failures.append(f"{arm}:initial_risk")
        for field in ("trades", "net_r", "net_r_per_trade", "profit_factor"):
            left, right = metrics[field], recorded[field]
            if field == "trades":
                equal = left == right
            else:
                equal = math.isclose(float(left), float(right), abs_tol=5e-4)
            if not equal:
                failures.append(f"{arm}:{field}")
        for symbol, value in metrics["by_symbol_net_r"].items():
            if not math.isclose(value, float(recorded["by_symbol_net_r"][symbol]), abs_tol=5e-4):
                failures.append(f"{arm}:symbol:{symbol}")

    baseline_symbols = computed["baseline"]["by_symbol_net_r"]
    challenger_symbols = computed["challenger"]["by_symbol_net_r"]
    shared = sorted(set(baseline_symbols) & set(challenger_symbols))
    improved_symbols = [
        symbol for symbol in shared
        if challenger_symbols[symbol] > baseline_symbols[symbol]
    ]
    passed = not failures
    return {
        "schema_id": "att1_pivot_sequence_v1_independent_audit",
        "passed": passed,
        "failures": sorted(set(failures)),
        "authority": "research_only_no_live_or_promotion",
        "capital_authorized": False,
        "passport_sha256": sha256_file(passport_path),
        "result_sha256": sha256_file(result_path),
        "computed": computed,
        "breadth": {
            "shared_symbols": len(shared),
            "improved_symbols": improved_symbols,
            "improved_symbol_count": len(improved_symbols),
        },
        "interpretation": (
            "receipt and arithmetic valid; challenger remains negative and may only "
            "advance to a separately frozen validation, never directly to live"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = audit(args.root.resolve())
    if args.out.exists():
        raise RuntimeError(f"write-once output exists: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
