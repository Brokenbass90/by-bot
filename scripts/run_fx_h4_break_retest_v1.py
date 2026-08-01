#!/usr/bin/env python3
"""Sealed research-only H4 break/retest baseline with asymmetric FX costs."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.engine import EngineConfig, run_backtest
from forex.strategies.trend_retest_session_v2 import Config, TrendRetestSessionV2
from forex.types import Candle, Trade

DEFAULT_PREREG = ROOT / "configs" / "research" / "fx_h4_break_retest_v1_prereg_20260801.json"
DEFAULT_COSTS = ROOT / "configs" / "research" / "fx_oanda_public_cost_contract_20260729.json"


def _pip_size(symbol: str) -> float:
    return 0.01 if symbol.endswith("JPY") else 0.0001


def _load_h4(path: Path) -> list[Candle]:
    frame = pd.read_csv(path, usecols=["ts", "o", "h", "l", "c", "v"])
    frame["time"] = pd.to_datetime(frame["ts"], unit="s", utc=True)
    frame = frame.set_index("time")
    h4 = frame.resample("4h", label="right", closed="left").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum", "ts": "count"}
    )
    # A completed H4 FX bar normally has 48 M5 observations. Require at least 80%
    # so weekend/large-gap fragments cannot become synthetic signals.
    h4 = h4[h4["ts"] >= 39].dropna(subset=["o", "h", "l", "c"])
    return [
        Candle(int(idx.timestamp()), float(row.o), float(row.h), float(row.l), float(row.c), float(row.v))
        for idx, row in h4.iterrows()
    ]


def _strategy(fixed: dict[str, Any]) -> TrendRetestSessionV2:
    fields = Config.__dataclass_fields__
    kwargs = {key: value for key, value in fixed.items() if key in fields}
    kwargs["session_utc_start"] = 0
    kwargs["session_utc_end"] = 24
    return TrendRetestSessionV2(Config(**kwargs))


def _engine(symbol: str, candles: list[Candle], costs: dict[str, Any], arm: str, risk_pct: float) -> EngineConfig:
    row = costs["instruments"][symbol]
    arm_cfg = costs["research_arms"][arm]
    price = float(np.median([c.c for c in candles]))
    pip = _pip_size(symbol)
    spread = float(row["spread_pips_base"]) * float(arm_cfg.get("spread_mult", 1.0))
    commission_bps_side = float(arm_cfg.get("commission_bps_per_side", 0.0))
    spread += (2.0 * commission_bps_side / 10000.0 * price) / pip
    adverse = float(arm_cfg.get("adverse_swap_mult", 1.0)) if arm == "stress" else 1.0

    def swap_pips(side: str) -> float:
        bps = float(row[f"swap_{side}_daily_bps"])
        bps = bps * adverse if bps < 0 else bps / adverse
        return (bps / 10000.0 * price) / pip

    return EngineConfig(
        pip_size=pip,
        spread_pips=spread,
        swap_long_pips_per_day=swap_pips("long"),
        swap_short_pips_per_day=swap_pips("short"),
        risk_per_trade_pct=risk_pct,
    )


def _trade_metrics(trades: list[Trade], risk_pct: float) -> dict[str, Any]:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    monthly_r: dict[str, float] = defaultdict(float)
    wins = 0
    for trade in trades:
        r = float(trade.r_multiple)
        equity = max(0.0, equity * (1.0 + risk_pct * r))
        peak = max(peak, equity)
        max_dd = max(max_dd, 1.0 - equity / peak if peak else 1.0)
        key = datetime.fromtimestamp(trade.exit_ts, timezone.utc).strftime("%Y-%m")
        monthly_r[key] += r
        wins += int(r > 0)
    return {
        "trades": len(trades),
        "wins": wins,
        "win_rate_pct": round(100.0 * wins / len(trades), 6) if trades else 0.0,
        "sum_r": round(sum(float(t.r_multiple) for t in trades), 6),
        "return_pct": round((equity - 1.0) * 100.0, 6),
        "max_drawdown_pct": round(max_dd * 100.0, 6),
        "calendar_months": len(monthly_r),
        "negative_months": sum(value < 0 for value in monthly_r.values()),
    }


def _folds(trades: list[Trade], start_ts: int, end_ts: int, count: int, risk_pct: float) -> list[dict[str, Any]]:
    edges = np.linspace(start_ts, end_ts + 1, count + 1, dtype=np.int64)
    result = []
    for index in range(count):
        block = [t for t in trades if int(edges[index]) <= t.entry_ts < int(edges[index + 1])]
        result.append({"fold": index + 1, **_trade_metrics(block, risk_pct)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prereg", default=str(DEFAULT_PREREG))
    parser.add_argument("--out-dir", default=str(ROOT / "reports" / "research" / "fx_h4_break_retest_v1_20260801"))
    args = parser.parse_args()
    prereg = json.loads(Path(args.prereg).read_text(encoding="utf-8"))
    costs = json.loads(DEFAULT_COSTS.read_text(encoding="utf-8"))
    fixed = prereg["fixed"]
    risk_pct = float(fixed["risk_per_trade_pct"]) / 100.0
    arms: dict[str, Any] = {}

    for arm in prereg["arms"]:
        all_trades: list[Trade] = []
        pair_rows: dict[str, Any] = {}
        starts: list[int] = []
        ends: list[int] = []
        for symbol in prereg["instruments"]:
            candles = _load_h4(ROOT / prereg["data_path_template"].format(symbol=symbol))
            if not candles:
                pair_rows[symbol] = {"status": "BLOCKED_DATA", "trades": 0}
                continue
            engine = _engine(symbol, candles, costs, arm, risk_pct)
            trades, _summary = run_backtest(candles, _strategy(fixed), engine)
            all_trades.extend(trades)
            starts.append(candles[0].ts)
            ends.append(candles[-1].ts)
            pair_rows[symbol] = _trade_metrics(trades, risk_pct)
        all_trades.sort(key=lambda trade: trade.exit_ts)
        start_ts = min(starts) if starts else 0
        end_ts = max(ends) if ends else 0
        fold_rows = _folds(all_trades, start_ts, end_ts, int(fixed["oos_folds"]), risk_pct) if starts else []
        arms[arm] = {
            "metrics": _trade_metrics(all_trades, risk_pct),
            "positive_folds": sum(row["sum_r"] > 0 for row in fold_rows),
            "folds": fold_rows,
            "positive_pairs": sum(row.get("sum_r", 0) > 0 for row in pair_rows.values()),
            "pairs": pair_rows,
        }

    stress = arms["stress"]
    pair_abs = sum(abs(float(row.get("sum_r", 0))) for row in stress["pairs"].values())
    concentration = max((abs(float(row.get("sum_r", 0))) / pair_abs * 100.0 for row in stress["pairs"].values()), default=0.0)
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
        "prereg": str(Path(args.prereg)),
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
