#!/usr/bin/env python3
"""Independent arithmetic/lifecycle audit of the Alpaca clean proxy receipt."""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, (value / peak - 1.0) * 100.0)
    return -worst


def _red_months(rows: list[dict[str, Any]], initial: float) -> tuple[int, int, float]:
    month_end: dict[str, float] = {}
    for row in rows:
        month_end[str(row["session"])[:7]] = float(row["equity"])
    values = list(month_end.values())
    previous = [initial, *values[:-1]]
    returns = [(value / prior - 1.0) * 100.0 for value, prior in zip(values, previous)]
    return sum(value < 0 for value in returns), len(values), min(returns) if returns else 0.0


def audit(result: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    arms: dict[str, Any] = {}
    for name, row in (result.get("results") or {}).items():
        equity = list(row.get("daily_equity") or [])
        trades = list(row.get("trades") or [])
        if not equity:
            failures.append(f"{name}:missing_equity")
            continue
        values = [float(item["equity"]) for item in equity]
        initial = float(row["initial_capital"])
        final = float(row["final_equity"])
        total = (final / initial - 1.0) * 100.0
        dd = _max_drawdown(values)
        red, months, worst_month = _red_months(equity, initial)
        gains = sum(max(0.0, float(item["pnl"])) for item in trades)
        losses = -sum(min(0.0, float(item["pnl"])) for item in trades)
        pf = gains / losses if losses else (float("inf") if gains else 0.0)
        avg_exposure = sum(float(item["gross_exposure"]) for item in equity) / len(equity) * 100.0
        lifecycle_errors = 0
        for trade in trades:
            try:
                lifecycle_errors += int(date.fromisoformat(str(trade["exit_session"])) < date.fromisoformat(str(trade["entry_session"])))
                lifecycle_errors += int(float(trade["entry_fill"]) <= 0 or float(trade["exit_fill"]) <= 0 or float(trade["qty"]) <= 0)
            except (KeyError, TypeError, ValueError):
                lifecycle_errors += 1

        checks = {
            "return_pct": math.isclose(total, float(row["return_pct"]), abs_tol=1e-9),
            "final_equity": math.isclose(values[-1], final, abs_tol=1e-9),
            "max_drawdown_pct": math.isclose(dd, float(row["daily_max_drawdown_pct"]), abs_tol=1e-9),
            "profit_factor": math.isclose(pf, float(row["profit_factor_realized"]), abs_tol=1e-9),
            "trade_count": len(trades) == int(row["realized_trades"]),
            "red_months": red == int(row["red_months"]),
            "month_count": months == int(row["months"]),
            "worst_month_pct": math.isclose(worst_month, float(row["worst_month_pct"]), abs_tol=1e-9),
            "average_gross_exposure_pct": math.isclose(avg_exposure, float(row["average_gross_exposure_pct"]), abs_tol=1e-9),
            "lifecycle": lifecycle_errors == 0,
        }
        failures.extend(f"{name}:{key}" for key, passed in checks.items() if not passed)
        arms[name] = {
            "checks": checks,
            "recomputed": {
                "return_pct": total,
                "max_drawdown_pct": dd,
                "profit_factor": pf,
                "red_months": red,
                "months": months,
                "worst_month_pct": worst_month,
                "average_gross_exposure_pct": avg_exposure,
            },
        }
    decisions = list(result.get("decisions") or [])
    selected = [symbol for row in decisions for symbol in (row.get("symbols") or [])]
    unknown = [symbol for row in decisions for symbol in (row.get("unknown_sector_symbols") or [])]
    return {
        "schema_id": "alpaca_clean_v38_proxy_independent_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": not failures,
        "failures": failures,
        "arms": arms,
        "selection_diagnostics": {
            "decision_count": len(decisions),
            "selected_slots": len(selected),
            "unknown_sector_slots": len(unknown),
            "unknown_sector_fraction": len(unknown) / len(selected) if selected else None,
        },
        "interpretation": "arithmetic/lifecycle only; does not cure PIT, sector, calendar, corporate-action, or intraday-parity blockers",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = audit(json.loads(args.result.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
