#!/usr/bin/env python3
"""Causal historical proxy for Alpaca adaptive selection and shared exits.

The runner is deliberately explicit about what it cannot prove: the universes
are current-survivor caches and the calendar is inferred from observed SPY
bars.  It accelerates diagnosis; it cannot authorize capital.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.alpaca_exact_parity_contract import (  # noqa: E402
    DailyBar,
    SharedExitContract,
    simulate_position,
)
from strategies.alpaca_adaptive_v1 import AdaptiveConfig, select  # noqa: E402
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_cache(symbol: str, suffix: str) -> tuple[pd.DataFrame, Path]:
    path = ROOT / "runtime" / "equities_yf_cache" / f"{symbol}_{suffix}.csv"
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        frame = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    except ValueError:
        frame = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    needed = {"Open", "High", "Low", "Close"}
    if not needed.issubset(frame.columns):
        raise ValueError(f"{path}: missing OHLC")
    frame = frame.dropna(subset=list(needed)).sort_index()
    return frame, path


def _atr20(frame: pd.DataFrame, signal_index: int) -> float:
    start = max(1, signal_index - 19)
    values = []
    for index in range(start, signal_index + 1):
        row = frame.iloc[index]
        previous_close = float(frame.iloc[index - 1]["Close"])
        values.append(max(
            float(row["High"]) - float(row["Low"]),
            abs(float(row["High"]) - previous_close),
            abs(float(row["Low"]) - previous_close),
        ))
    return statistics.fmean(values) if values else 0.0


def _bars(frame: pd.DataFrame, start_date: pd.Timestamp, limit: int) -> list[DailyBar]:
    out = []
    sliced = frame.loc[frame.index >= start_date].iloc[:limit]
    for timestamp, row in sliced.iterrows():
        out.append(DailyBar(
            session_date=timestamp.date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
        ))
    return out


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    return wins / losses if losses > 0 else (math.inf if wins > 0 else 0.0)


def _summary(monthly: list[float], trade_returns: list[float]) -> dict[str, Any]:
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in monthly:
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    years = max(len(monthly) / 12.0, 1.0 / 12.0)
    annualized = equity ** (1.0 / years) - 1.0 if equity > 0 else -1.0
    return {
        "return_pct": (equity - 1.0) * 100.0,
        "annualized_return_pct": annualized * 100.0,
        "profit_factor": _profit_factor(trade_returns),
        "trades": len(trade_returns),
        "red_months": sum(value < 0 for value in monthly),
        "months": len(monthly),
        "worst_month_pct": min(monthly, default=0.0) * 100.0,
        "monthly_endpoint_drawdown_pct": drawdown * 100.0,
    }


def _run_window(
    window: dict[str, Any],
    *,
    cost_bps_per_side: float,
    use_gate: bool,
    target_alloc_pct: float,
    max_positions: int,
    exit_contract: SharedExitContract = SharedExitContract(),
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    suffix = str(window["cache_suffix"])
    data: dict[str, pd.DataFrame] = {}
    manifest = []
    for symbol in [*window["symbols"], "SPY"]:
        frame, path = _load_cache(symbol, suffix)
        data[symbol] = frame
        manifest.append({
            "symbol": symbol,
            "path": str(path.relative_to(ROOT)),
            "sha256": _sha256(path),
            "rows": str(len(frame)),
        })

    spy = data["SPY"]
    observed_sessions = [
        timestamp for timestamp in spy.index
        if str(timestamp.date()) >= window["evaluation_start"]
        and str(timestamp.date()) < window["evaluation_end_exclusive"]
    ]
    month_last: dict[str, pd.Timestamp] = {}
    for timestamp in observed_sessions:
        month_last[timestamp.strftime("%Y-%m")] = timestamp

    cfg = AdaptiveConfig(max_positions=max_positions)
    monthly_returns = []
    trade_returns = []
    decisions = []
    spy_dates = list(spy.index)
    for signal_month, signal_date in sorted(month_last.items()):
        signal_pos = spy_dates.index(signal_date)
        if signal_pos + 1 >= len(spy_dates):
            continue
        entry_date = spy_dates[signal_pos + 1]
        if str(entry_date.date()) >= window["evaluation_end_exclusive"]:
            continue

        index_closes = [
            float(value) for value in spy.loc[spy.index <= signal_date, "Close"].tolist()
        ]
        universe: dict[str, list[float]] = {}
        signal_positions: dict[str, int] = {}
        for symbol in window["symbols"]:
            frame = data[symbol]
            eligible = frame.loc[frame.index <= signal_date]
            if signal_date not in frame.index or len(eligible) < 202:
                continue
            universe[symbol] = [float(value) for value in eligible["Close"].tolist()]
            signal_positions[symbol] = frame.index.get_loc(signal_date)

        selection = select(
            universe,
            index_closes,
            sectors=SECTOR_MAP,
            cfg=cfg,
            force_regime_ok=not use_gate,
        )
        month_return = 0.0
        pick_rows = []
        for pick in selection.get("picks") or []:
            symbol = str(pick["symbol"])
            weight = float(pick.get("weight") or 0.0) * target_alloc_pct / 100.0
            frame = data[symbol]
            if entry_date not in frame.index:
                continue
            atr = _atr20(frame, signal_positions[symbol])
            position_bars = _bars(
                frame,
                entry_date,
                exit_contract.max_hold_sessions,
            )
            if atr <= 0 or not position_bars:
                continue
            result = simulate_position(
                position_bars,
                atr_at_signal=atr,
                cost_bps_per_side=cost_bps_per_side,
                contract=exit_contract,
            )
            if result["exit_fill"] is None:
                continue
            raw_return = float(result["exit_fill"]) / float(result["entry_fill"]) - 1.0
            contribution = weight * raw_return
            month_return += contribution
            trade_returns.append(contribution)
            pick_rows.append({
                "symbol": symbol,
                "weight": weight,
                "atr_at_signal": atr,
                "entry_session": result["entry_session"],
                "exit_session": result["exit_session"],
                "exit_reason": result["exit_reason"],
                "raw_return": raw_return,
                "contribution": contribution,
            })
        monthly_returns.append(month_return)
        decisions.append({
            "signal_month": signal_month,
            "signal_session": signal_date.date().isoformat(),
            "entry_session": entry_date.date().isoformat(),
            "regime_ok": bool(selection.get("regime_ok")),
            "reason": selection.get("reason"),
            "month_return": month_return,
            "picks": pick_rows,
        })
    return _summary(monthly_returns, trade_returns), decisions, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prereg",
        default="configs/preregistered/alpaca_adaptive_historical_proxy_20260728.json",
    )
    parser.add_argument(
        "--out",
        default="reports/research/alpaca_adaptive_historical_proxy_20260728/receipt.json",
    )
    args = parser.parse_args()
    prereg_path = ROOT / args.prereg
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))

    results = []
    manifests: dict[str, list[dict[str, str]]] = {}
    for window in prereg["windows"]:
        for cost in prereg["cost_bps_per_side"]:
            for arm in prereg["arms"]:
                summary, decisions, manifest = _run_window(
                    window,
                    cost_bps_per_side=float(cost),
                    use_gate=arm == "adaptive_gated",
                    target_alloc_pct=float(prereg["strategy"]["target_alloc_pct"]),
                    max_positions=int(prereg["strategy"]["max_positions"]),
                )
                results.append({
                    "window": window["id"],
                    "arm": arm,
                    "cost_bps_per_side": cost,
                    "summary": summary,
                    "decisions": decisions,
                })
                manifests[window["id"]] = manifest
                print(
                    f"{window['id']} {arm} cost={cost:.1f}: "
                    f"return={summary['return_pct']:+.2f}% "
                    f"PF={summary['profit_factor']:.3f} "
                    f"DD={summary['monthly_endpoint_drawdown_pct']:.2f}% "
                    f"red={summary['red_months']}/{summary['months']}"
                )

    base_rows = [
        row for row in results
        if float(row["cost_bps_per_side"]) == 5.0
    ]
    gated_return = sum(
        row["summary"]["return_pct"]
        for row in base_rows if row["arm"] == "adaptive_gated"
    )
    ungated_return = sum(
        row["summary"]["return_pct"]
        for row in base_rows if row["arm"] != "adaptive_gated"
    )
    gated_dd_ok = all(
        row["summary"]["monthly_endpoint_drawdown_pct"] <= 15.0
        for row in base_rows if row["arm"] == "adaptive_gated"
    )
    repair_continues = gated_return > ungated_return and gated_dd_ok
    receipt = {
        "schema_id": "alpaca_adaptive_historical_proxy_receipt_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "safe_hold_changed": False,
        "broker_or_network_calls": False,
        "prereg_path": args.prereg,
        "prereg_sha256": _sha256(prereg_path),
        "results": results,
        "input_manifests": manifests,
        "decision": "REPAIR_CONTINUES" if repair_continues else "NO_GO_CURRENT_MODEL",
        "decision_metrics": {
            "gated_sum_window_returns_pct_at_5bps": gated_return,
            "ungated_sum_window_returns_pct_at_5bps": ungated_return,
            "gated_all_window_dd_le_15pct": gated_dd_ok,
        },
        "promotion": "RESEARCH_ONLY",
        "capital_blockers": prereg["interpretation"]["not_promotion_grade_because"],
    }
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(f"decision={receipt['decision']}")
    print(f"receipt={output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
