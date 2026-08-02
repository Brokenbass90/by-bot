#!/usr/bin/env python3
"""Native causal replay for the discovered dump-exhaustion long family.

The discovery OOS has already been viewed. This program therefore measures
implementation parity and time/symbol robustness only. It has no promotion or
order authority.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREREG = ROOT / "configs/research/dump_exhaustion_reversal_native_replay_prereg_20260802.json"
DEFAULT_OUTPUT = ROOT / "reports/research/dump_exhaustion_reversal_native_replay_20260802/result.json"


@dataclass(frozen=True)
class Arm:
    lookback: int
    threshold: float
    volume_z: float
    hold: int

    @property
    def arm_id(self) -> str:
        return f"lb{self.lookback}_drop{self.threshold:.2f}_vz{self.volume_z:.1f}_h{self.hold}"


def load_symbol(symbol: str) -> pd.DataFrame:
    rows: dict[int, dict[str, Any]] = {}
    for path in sorted((ROOT / "data_cache").glob(f"{symbol}_5_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, list):
            continue
        for row in payload:
            try:
                rows[int(row["ts"])] = row
            except (KeyError, TypeError, ValueError):
                continue
    if not rows:
        raise FileNotFoundError(symbol)
    frame = pd.DataFrame(rows.values())
    frame.index = pd.to_datetime(frame.pop("ts"), unit="ms", utc=True)
    frame = frame.sort_index()
    for column in ("o", "h", "l", "c", "v"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.resample("1h").agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"})
    return frame.dropna().loc[lambda x: (x[["o", "h", "l", "c"]] > 0).all(axis=1)]


def signal_series(frame: pd.DataFrame, arm: Arm) -> pd.Series:
    move = frame["c"].pct_change(arm.lookback)
    mean = frame["v"].rolling(96, min_periods=96).mean()
    std = frame["v"].rolling(96, min_periods=96).std(ddof=0).replace(0.0, float("nan"))
    volume_z = (frame["v"] - mean) / std
    return ((move <= -arm.threshold) & (volume_z >= arm.volume_z)).fillna(False)


def replay(frame: pd.DataFrame, signal: pd.Series, arm: Arm, cost_bps: float, block: int, blocks: int) -> list[dict[str, Any]]:
    n = len(frame)
    start = (n * block) // blocks
    stop = (n * (block + 1)) // blocks
    trades: list[dict[str, Any]] = []
    i = max(start, 96 + arm.lookback)
    while i < stop - arm.hold - 1:
        if not bool(signal.iloc[i]):
            i += 1
            continue
        entry_i = i + 1
        exit_i = entry_i + arm.hold
        if exit_i >= stop:
            break
        entry = float(frame["o"].iloc[entry_i])
        exit_price = float(frame["o"].iloc[exit_i])
        gross = exit_price / entry - 1.0
        net = gross - cost_bps / 10_000.0
        trades.append({
            "signal_ts": frame.index[i].isoformat(),
            "entry_ts": frame.index[entry_i].isoformat(),
            "exit_ts": frame.index[exit_i].isoformat(),
            "entry": entry,
            "exit": exit_price,
            "gross_return": gross,
            "net_return": net,
            "block": block + 1,
        })
        i = exit_i + 1
    return trades


def metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [float(x["net_return"]) for x in trades]
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for ret in returns:
        equity *= max(0.0, 1.0 + ret)
        peak = max(peak, equity)
        max_dd = max(max_dd, 1.0 - equity / peak)
    wins = [x for x in returns if x > 0]
    losses = [x for x in returns if x < 0]
    pf = sum(wins) / abs(sum(losses)) if losses else (999.0 if wins else 0.0)
    return {
        "trades": len(returns),
        "compounded_return": equity - 1.0,
        "mean_trade_return": sum(returns) / len(returns) if returns else 0.0,
        "win_rate": len(wins) / len(returns) if returns else 0.0,
        "profit_factor": pf,
        "max_drawdown": max_dd,
    }


def aggregate(symbol_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(x["metrics"]["trades"]) for x in symbol_rows)
    positive = [x for x in symbol_rows if float(x["metrics"]["compounded_return"]) > 0]
    positive_contrib = [max(0.0, float(x["metrics"]["compounded_return"])) for x in symbol_rows]
    denom = sum(positive_contrib)
    max_share = max(positive_contrib, default=0.0) / denom if denom > 0 else 1.0
    returns = [float(x["metrics"]["compounded_return"]) for x in symbol_rows]
    return {
        "symbols": len(symbol_rows),
        "positive_symbols": len(positive),
        "total_trades": total,
        "mean_symbol_return": sum(returns) / len(returns) if returns else 0.0,
        "median_symbol_return": float(pd.Series(returns).median()) if returns else 0.0,
        "worst_symbol_return": min(returns, default=0.0),
        "largest_positive_symbol_contribution_share": max_share,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prereg", default=str(DEFAULT_PREREG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    prereg = json.loads(Path(args.prereg).read_text(encoding="utf-8"))
    arms = [Arm(**row) for row in prereg["frozen_arms"]]
    symbols = list(prereg["symbols"])
    blocks = int(prereg["robustness"]["chronological_blocks"])
    frames = {symbol: load_symbol(symbol) for symbol in symbols}
    results: list[dict[str, Any]] = []
    for arm in arms:
        signals = {symbol: signal_series(frame, arm) for symbol, frame in frames.items()}
        cost_results: dict[str, Any] = {}
        for cost_name, cost_bps in (
            ("base", float(prereg["execution"]["base_round_trip_bps"])),
            ("stress", float(prereg["execution"]["stress_round_trip_bps"])),
        ):
            symbol_rows = []
            block_totals = []
            for symbol, frame in frames.items():
                all_trades: list[dict[str, Any]] = []
                per_block = []
                for block in range(blocks):
                    block_trades = replay(frame, signals[symbol], arm, cost_bps, block, blocks)
                    all_trades.extend(block_trades)
                    per_block.append({"block": block + 1, **metrics(block_trades)})
                symbol_rows.append({"symbol": symbol, "metrics": metrics(all_trades), "blocks": per_block})
            for block in range(blocks):
                block_returns = [float(row["blocks"][block]["compounded_return"]) for row in symbol_rows]
                block_totals.append({
                    "block": block + 1,
                    "positive_symbols": sum(x > 0 for x in block_returns),
                    "mean_symbol_return": sum(block_returns) / len(block_returns),
                    "total_trades": sum(int(row["blocks"][block]["trades"]) for row in symbol_rows),
                })
            cost_results[cost_name] = {"aggregate": aggregate(symbol_rows), "blocks": block_totals, "per_symbol": symbol_rows}
        results.append({"arm_id": arm.arm_id, "params": arm.__dict__, **cost_results})
    robust = prereg["robustness"]
    positive_base = sum(x["base"]["aggregate"]["positive_symbols"] >= robust["required_positive_symbols_per_arm"] for x in results)
    positive_stress = sum(x["stress"]["aggregate"]["positive_symbols"] >= robust["required_positive_symbols_per_arm"] for x in results)
    concentration_ok = all(
        x["stress"]["aggregate"]["largest_positive_symbol_contribution_share"] <= robust["maximum_single_symbol_contribution"]
        for x in results
    )
    passed = bool(
        positive_base >= robust["required_positive_arms_base"]
        and positive_stress >= robust["required_positive_arms_stress"]
        and concentration_ok
    )
    output = {
        "schema_id": "dump_exhaustion_reversal_native_replay_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "promotion_authority": False,
        "evidence_class": "viewed-data native parity and robustness; not untouched OOS",
        "bars": {symbol: len(frame) for symbol, frame in frames.items()},
        "n_trials_planned": len(arms),
        "n_trials_scheduled": len(arms),
        "n_trials_evaluated": len(results),
        "results": results,
        "gate": {
            "positive_arms_base": positive_base,
            "positive_arms_stress": positive_stress,
            "concentration_ok": concentration_ok,
            "status": "PASS_TO_PROSPECTIVE_RISK_ZERO" if passed else "FAIL_NATIVE_ROBUSTNESS",
        },
        "next_gate": "Freeze a plateau arm before new data and collect prospective risk-zero decisions; money remains forbidden.",
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output["gate"], sort_keys=True))
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
