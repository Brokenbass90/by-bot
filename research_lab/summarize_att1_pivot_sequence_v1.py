#!/usr/bin/env python3
"""Fail-closed summary for the binary ATT1 pivot-sequence experiment."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _arm(row: dict[str, str]) -> dict[str, Any]:
    run_dir = Path(row["run_dir"])
    trades = _rows(run_dir / "trades.csv")
    trade_rs: list[tuple[dict[str, str], float]] = []
    for trade in trades:
        initial_risk = _f(trade.get("initial_risk_usd"))
        if initial_risk > 0.0:
            trade_rs.append((trade, _f(trade.get("pnl")) / initial_risk))
    net_rs = [net_r for _, net_r in trade_rs]
    by_symbol: dict[str, list[float]] = defaultdict(list)
    by_month: dict[str, list[float]] = defaultdict(list)
    for trade, net_r in trade_rs:
        by_symbol[str(trade.get("symbol") or "unknown")].append(net_r)
        raw_ts = int(_f(trade.get("entry_ts")))
        if raw_ts > 10_000_000_000:
            raw_ts //= 1000
        import datetime as dt
        month = dt.datetime.fromtimestamp(raw_ts, tz=dt.timezone.utc).strftime("%Y-%m")
        by_month[month].append(net_r)
    return {
        "overrides": json.loads(row["overrides_json"]),
        "run_dir": str(run_dir),
        "trades": len(trades),
        "net_pnl": _f(row.get("net_pnl")),
        "profit_factor": _f(row.get("profit_factor")),
        "net_r": round(sum(net_rs), 6),
        "net_r_per_trade": round(sum(net_rs) / len(net_rs), 6) if net_rs else None,
        "risk_denominator_coverage": len(net_rs) / len(trades) if trades else 0.0,
        "by_symbol_net_r": {key: round(sum(values), 6) for key, values in sorted(by_symbol.items())},
        "by_month_net_r": {key: round(sum(values), 6) for key, values in sorted(by_month.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_csv", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    source = _rows(args.results_csv)
    if len(source) != 2:
        raise RuntimeError(f"expected exactly two arms, got {len(source)}")
    arms = [_arm(row) for row in source]
    indexed = {
        str(arm["overrides"].get("ATT1_GEOMETRY_V2_ENABLE")): arm
        for arm in arms
    }
    if set(indexed) != {"0", "1"}:
        raise RuntimeError(f"arm identity mismatch: {sorted(indexed)}")
    baseline, challenger = indexed["0"], indexed["1"]
    if baseline["risk_denominator_coverage"] < 0.999 or challenger["risk_denominator_coverage"] < 0.999:
        raise RuntimeError("initial-risk coverage is incomplete; R comparison forbidden")
    differentiators = (
        baseline["trades"] != challenger["trades"],
        not math.isclose(baseline["net_r"], challenger["net_r"], abs_tol=1e-9),
        not math.isclose(baseline["profit_factor"], challenger["profit_factor"], abs_tol=1e-9),
    )
    if not any(differentiators):
        raise RuntimeError("challenger output is indistinguishable; fail closed")
    retention = challenger["trades"] / baseline["trades"] if baseline["trades"] else 0.0
    improves = (
        challenger["net_r_per_trade"] is not None
        and baseline["net_r_per_trade"] is not None
        and challenger["net_r_per_trade"] > baseline["net_r_per_trade"]
        and challenger["profit_factor"] > baseline["profit_factor"]
        and retention >= 0.30
    )
    result = {
        "schema_id": "att1_pivot_sequence_prefilter_result_v1",
        "authority": "research_only_no_live_or_promotion",
        "source_results_csv": str(args.results_csv),
        "baseline": baseline,
        "challenger": challenger,
        "trade_retention": round(retention, 6),
        "prefilter_verdict": "PROMISING_NEEDS_FROZEN_VALIDATION" if improves else "REJECTED_OR_INCONCLUSIVE",
        "capital_authorized": False,
        "sealed_holdout_rows_decoded": 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise RuntimeError(f"write-once output exists: {args.out}")
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
