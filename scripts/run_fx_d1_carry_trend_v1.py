#!/usr/bin/env python3
"""Sealed research-only D1 carry plus trend baseline."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PREREG = ROOT / "configs" / "research" / "fx_d1_carry_trend_v1_prereg_20260801.json"


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(-dd.min() * 100.0) if len(dd) else 0.0


def _metrics(returns: pd.Series) -> dict[str, float | int]:
    returns = returns.fillna(0.0)
    equity = (1.0 + returns).cumprod()
    years = max(len(returns) / 252.0, 1.0 / 252.0)
    annualized = (float(equity.iloc[-1]) ** (1.0 / years) - 1.0) * 100.0 if len(equity) else 0.0
    monthly_index = returns.index.tz_localize(None).to_period("M") if returns.index.tz is not None else returns.index.to_period("M")
    monthly = returns.groupby(monthly_index).apply(lambda x: (1.0 + x).prod() - 1.0)
    vol = float(returns.std(ddof=0) * math.sqrt(252.0) * 100.0)
    return {
        "days": int(len(returns)),
        "total_return_pct": round((float(equity.iloc[-1]) - 1.0) * 100.0, 6) if len(equity) else 0.0,
        "annualized_return_pct": round(annualized, 6),
        "annualized_vol_pct": round(vol, 6),
        "sharpe_zero_rf": round(annualized / vol, 6) if vol > 0 else 0.0,
        "max_drawdown_pct": round(_max_drawdown(equity), 6),
        "calendar_months": int(len(monthly)),
        "negative_months": int((monthly < 0).sum()),
    }


def _daily_close(path: Path) -> pd.Series:
    frame = pd.read_csv(path, usecols=["ts", "c"])
    frame["time"] = pd.to_datetime(frame["ts"], unit="s", utc=True)
    frame["date"] = frame["time"].dt.floor("D")
    daily = frame.groupby("date", sort=True)["c"].last().astype(float)
    daily.name = path.stem.split("_")[0]
    return daily


def _one_way_cost_bps(symbol: str, price: float, costs: dict[str, Any], arm: str) -> float:
    row = costs["instruments"][symbol]
    pip_size = float(row.get("pip_size") or (0.01 if symbol.endswith("JPY") else 0.0001))
    spread_mult = float(costs["research_arms"][arm].get("spread_mult", 1.0))
    commission = float(costs["research_arms"][arm].get("commission_bps_per_side", 0.0))
    spread_bps = float(row["spread_pips_base"]) * pip_size / max(price, 1e-12) * 10000.0
    return spread_bps * spread_mult / 2.0 + commission


def run_arm(prices: pd.DataFrame, prereg: dict[str, Any], costs: dict[str, Any], arm: str) -> dict[str, Any]:
    fixed = prereg["fixed"]
    lookback = int(fixed["momentum_lookback_days"])
    rebalance = int(fixed["rebalance_days"])
    minimum = float(fixed["minimum_abs_momentum_pct"]) / 100.0
    max_pairs = int(fixed["max_pairs"])
    symbols = list(prices.columns)
    daily_ret = prices.pct_change(fill_method=None)
    momentum = prices / prices.shift(lookback) - 1.0
    weights = pd.DataFrame(0.0, index=prices.index, columns=symbols)
    previous = pd.Series(0.0, index=symbols)

    for i in range(lookback, len(prices)):
        if (i - lookback) % rebalance != 0:
            weights.iloc[i] = previous
            continue
        candidates: list[tuple[float, str, float]] = []
        for symbol in symbols:
            mom = float(momentum.iloc[i][symbol])
            if not math.isfinite(mom) or abs(mom) < minimum:
                continue
            direction = 1.0 if mom > 0 else -1.0
            row = costs["instruments"][symbol]
            carry_bps = float(row["swap_long_daily_bps"] if direction > 0 else row["swap_short_daily_bps"])
            score = abs(mom) + max(-0.02, carry_bps * 252.0 / 10000.0)
            candidates.append((score, symbol, direction))
        candidates.sort(reverse=True)
        selected = candidates[:max_pairs]
        current = pd.Series(0.0, index=symbols)
        if selected:
            for _, symbol, direction in selected:
                current[symbol] = direction / len(selected)
        weights.iloc[i] = current
        previous = current

    # Signals formed on completed day t become positions for return t+1.
    held = weights.shift(1).fillna(0.0)
    gross_by_pair = held * daily_ret
    carry_by_pair = pd.DataFrame(0.0, index=prices.index, columns=symbols)
    cost_by_pair = pd.DataFrame(0.0, index=prices.index, columns=symbols)
    turnover = held.diff().abs().fillna(held.abs())
    arm_cfg = costs["research_arms"][arm]
    adverse_swap_mult = float(arm_cfg.get("adverse_swap_mult", 1.0))
    for symbol in symbols:
        row = costs["instruments"][symbol]
        long_swap = float(row["swap_long_daily_bps"])
        short_swap = float(row["swap_short_daily_bps"])
        if arm == "stress":
            long_swap = long_swap * adverse_swap_mult if long_swap < 0 else long_swap / adverse_swap_mult
            short_swap = short_swap * adverse_swap_mult if short_swap < 0 else short_swap / adverse_swap_mult
        carry_bps = held[symbol].where(held[symbol] >= 0, 0.0) * long_swap
        carry_bps += (-held[symbol].where(held[symbol] < 0, 0.0)) * short_swap
        carry_by_pair[symbol] = carry_bps / 10000.0
        one_way = prices[symbol].map(lambda p: _one_way_cost_bps(symbol, float(p), costs, arm))
        cost_by_pair[symbol] = turnover[symbol] * one_way / 10000.0
    net_by_pair = gross_by_pair + carry_by_pair - cost_by_pair
    net = net_by_pair.sum(axis=1).iloc[lookback + 1 :].dropna()

    folds: list[dict[str, Any]] = []
    fold_count = int(fixed["oos_folds"])
    for fold, indices in enumerate(__import__("numpy").array_split(range(len(net)), fold_count), 1):
        block = net.iloc[list(indices)] if len(indices) else net.iloc[0:0]
        folds.append({"fold": fold, "start": str(block.index.min()), "end": str(block.index.max()), **_metrics(block)})
    pair_contribution = {symbol: float(net_by_pair.loc[net.index, symbol].sum()) for symbol in symbols}
    total_abs = sum(abs(v) for v in pair_contribution.values())
    concentration = max((abs(v) / total_abs * 100.0 for v in pair_contribution.values()), default=0.0)
    return {
        "arm": arm,
        "metrics": _metrics(net),
        "folds": folds,
        "positive_folds": sum(float(row["total_return_pct"]) > 0 for row in folds),
        "pair_contribution_return_units": {k: round(v, 8) for k, v in pair_contribution.items()},
        "positive_pairs": sum(v > 0 for v in pair_contribution.values()),
        "largest_pair_abs_contribution_pct": round(concentration, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prereg", default=str(DEFAULT_PREREG))
    parser.add_argument("--out-dir", default=str(ROOT / "reports" / "research" / "fx_d1_carry_trend_v1_20260801"))
    args = parser.parse_args()
    prereg = json.loads(Path(args.prereg).read_text(encoding="utf-8"))
    costs = json.loads((ROOT / "configs" / "research" / "fx_oanda_public_cost_contract_20260729.json").read_text(encoding="utf-8"))
    series = [
        _daily_close(ROOT / prereg["data_path_template"].format(symbol=symbol))
        for symbol in prereg["instruments"]
    ]
    prices = pd.concat(series, axis=1).sort_index().ffill(limit=3).dropna()
    arms = {arm: run_arm(prices, prereg, costs, arm) for arm in prereg["arms"]}
    stress = arms["stress"]
    gate = prereg["promotion_gate"]
    checks = {
        "stress_return_positive": stress["metrics"]["annualized_return_pct"] > gate["stress_annualized_return_pct_gt"],
        "stress_positive_folds": stress["positive_folds"] >= gate["stress_positive_folds_min"],
        "stress_positive_pairs": stress["positive_pairs"] >= gate["stress_positive_pairs_min"],
        "stress_drawdown": stress["metrics"]["max_drawdown_pct"] < gate["stress_max_drawdown_pct_lt"],
        "concentration": stress["largest_pair_abs_contribution_pct"] < gate["largest_pair_abs_contribution_pct_lt"],
    }
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_RESEARCH" if all(checks.values()) else "FAIL_RESEARCH",
        "research_only": True,
        "rows": len(prices),
        "start": str(prices.index.min()),
        "end": str(prices.index.max()),
        "prereg": str(Path(args.prereg)),
        "checks": checks,
        "arms": arms,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out_dir / "terminal_receipt.json").write_text(json.dumps({k: result[k] for k in ["generated_at_utc", "status", "research_only", "checks"]}, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
