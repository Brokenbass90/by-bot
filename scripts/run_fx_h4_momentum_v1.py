#!/usr/bin/env python3
"""Sealed research-only H4 time-series momentum with asymmetric FX costs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.engine import run_backtest
from forex.strategies.h4_time_series_momentum_v1 import Config, H4TimeSeriesMomentumV1
from forex.types import Trade
from scripts.run_fx_h4_break_retest_v1 import _engine, _folds, _load_h4, _trade_metrics

DEFAULT_PREREG = ROOT / "configs" / "research" / "fx_h4_momentum_v1_prereg_20260801.json"
DEFAULT_COSTS = ROOT / "configs" / "research" / "fx_oanda_public_cost_contract_20260729.json"


def _strategy(fixed: dict[str, Any]) -> H4TimeSeriesMomentumV1:
    fields = Config.__dataclass_fields__
    return H4TimeSeriesMomentumV1(Config(**{key: value for key, value in fixed.items() if key in fields}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prereg", default=str(DEFAULT_PREREG))
    parser.add_argument("--out-dir", default=str(ROOT / "reports" / "research" / "fx_h4_momentum_v1_20260801"))
    args = parser.parse_args()
    prereg_path = Path(args.prereg)
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    costs = json.loads(DEFAULT_COSTS.read_text(encoding="utf-8"))
    fixed = dict(prereg["fixed"])
    risk_pct = float(fixed["risk_per_trade_pct"]) / 100.0
    arms: dict[str, Any] = {}

    for arm in prereg["arms"]:
        all_trades: list[Trade] = []
        pairs: dict[str, Any] = {}
        starts: list[int] = []
        ends: list[int] = []
        for symbol in prereg["instruments"]:
            candles = _load_h4(ROOT / prereg["data_path_template"].format(symbol=symbol))
            if not candles:
                pairs[symbol] = {"status": "BLOCKED_DATA", "trades": 0}
                continue
            trades, _summary = run_backtest(candles, _strategy(fixed), _engine(symbol, candles, costs, arm, risk_pct))
            all_trades.extend(trades)
            starts.append(candles[0].ts)
            ends.append(candles[-1].ts)
            pairs[symbol] = _trade_metrics(trades, risk_pct)
        all_trades.sort(key=lambda trade: trade.exit_ts)
        folds = _folds(all_trades, min(starts), max(ends), int(fixed["oos_folds"]), risk_pct) if starts else []
        arms[arm] = {
            "metrics": _trade_metrics(all_trades, risk_pct),
            "positive_folds": sum(row["sum_r"] > 0 for row in folds),
            "folds": folds,
            "positive_pairs": sum(row.get("sum_r", 0) > 0 for row in pairs.values()),
            "pairs": pairs,
        }

    stress = arms["stress"]
    pair_abs = sum(abs(float(row.get("sum_r", 0))) for row in stress["pairs"].values())
    concentration = max(
        (abs(float(row.get("sum_r", 0))) / pair_abs * 100.0 for row in stress["pairs"].values()),
        default=0.0,
    )
    gate = prereg["promotion_gate"]
    checks = {
        "stress_return_positive": stress["metrics"]["return_pct"] > gate["stress_return_pct_gt"],
        "stress_sum_r_positive": stress["metrics"]["sum_r"] > gate["stress_sum_r_gt"],
        "stress_positive_folds": stress["positive_folds"] >= gate["stress_positive_folds_min"],
        "stress_positive_pairs": stress["positive_pairs"] >= gate["stress_positive_pairs_min"],
        "stress_drawdown": stress["metrics"]["max_drawdown_pct"] < gate["stress_max_drawdown_pct_lt"],
        "stress_trade_count": stress["metrics"]["trades"] >= gate["stress_min_trades"],
        "stress_concentration": concentration < gate["largest_pair_abs_sum_r_pct_lt"],
    }
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_RESEARCH" if all(checks.values()) else "FAIL_RESEARCH",
        "research_only": True,
        "checks": checks,
        "stress_largest_pair_abs_sum_r_pct": round(concentration, 6),
        "prereg": str(prereg_path),
        "arms": arms,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "terminal_receipt.json").write_text(
        json.dumps({key: result[key] for key in ("generated_at_utc", "status", "research_only", "checks")}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
