#!/usr/bin/env python3
"""Causal maker-fill audit for the frozen funding-positioning V3 signal.

V3 assumed every maker order filled. V4 freezes the V3 signal/slot selection,
then places a hypothetical post-only order away from the first tradable open.
Only a strict trade-through during the timeout counts as a fill. Nonfills earn
zero but retain their market-entry outcome as an opportunity-cost diagnostic.

This is historical risk-zero research. Bar trade-through is still not queue
position, so a PASS can only authorize prospective shadow collection.
"""
from __future__ import annotations

import argparse
import bisect
import json
import statistics
from collections import defaultdict
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

try:
    from scripts.audit_funding_positioning_v2 import (
        FUNDING_DIR,
        Trade,
        _best_5m_cache,
        _first_after,
        _funding_cashflow,
        _load_funding,
        build_trades,
    )
    from scripts.audit_funding_positioning_v3 import _apply_slots, _with_rolling_beta
except ModuleNotFoundError:
    from audit_funding_positioning_v2 import (  # type: ignore[no-redef]
        FUNDING_DIR,
        Trade,
        _best_5m_cache,
        _first_after,
        _funding_cashflow,
        _load_funding,
        build_trades,
    )
    from audit_funding_positioning_v3 import _apply_slots, _with_rolling_beta  # type: ignore[no-redef]


@lru_cache(maxsize=None)
def _bars(symbol: str) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in _best_5m_cache(symbol))


@lru_cache(maxsize=None)
def _funding(symbol: str) -> tuple[tuple[int, float], ...]:
    return tuple(_load_funding(symbol))


def _maker_fill(
    trade: Trade,
    *,
    offset_bps: float,
    timeout_minutes: int,
    hold_hours: int,
) -> Trade | None:
    rows = _bars(trade.symbol)
    btc_rows = rows if trade.symbol == "BTCUSDT" else _bars("BTCUSDT")
    if not rows or not btc_rows:
        return None
    timestamps = [int(row[0]) for row in rows]
    btc_timestamps = [int(row[0]) for row in btc_rows]
    start_idx = bisect.bisect_left(timestamps, int(trade.entry_ts))
    if start_idx >= len(rows):
        return None
    reference = float(rows[start_idx][1])
    if reference <= 0:
        return None
    limit_price = reference * (1.0 - float(trade.side) * float(offset_bps) / 10_000.0)
    timeout_ts = int(trade.entry_ts) + int(timeout_minutes) * 60_000
    fill_idx: int | None = None
    for idx in range(start_idx, len(rows)):
        row = rows[idx]
        if int(row[0]) >= timeout_ts:
            break
        traded_through = (
            float(row[3]) < limit_price
            if trade.side > 0
            else float(row[2]) > limit_price
        )
        if traded_through:
            fill_idx = idx
            break
    if fill_idx is None:
        return None

    fill_ts = int(rows[fill_idx][0])
    exit_idx = _first_after(timestamps, fill_ts + int(hold_hours) * 3_600_000 - 1)
    btc_entry_idx = bisect.bisect_left(btc_timestamps, fill_ts)
    btc_exit_idx = _first_after(
        btc_timestamps,
        fill_ts + int(hold_hours) * 3_600_000 - 1,
    )
    if exit_idx is None or btc_entry_idx >= len(btc_rows) or btc_exit_idx is None:
        return None
    exit_price = float(rows[exit_idx][1])
    btc_entry = float(btc_rows[btc_entry_idx][1])
    btc_exit = float(btc_rows[btc_exit_idx][1])
    if exit_price <= 0 or btc_entry <= 0 or btc_exit <= 0:
        return None
    exit_ts = int(rows[exit_idx][0])
    return replace(
        trade,
        entry_ts=fill_ts,
        exit_ts=exit_ts,
        asset_return=exit_price / limit_price - 1.0,
        btc_return=btc_exit / btc_entry - 1.0,
        funding_cashflow=_funding_cashflow(
            list(_funding(trade.symbol)),
            entry_ts=fill_ts,
            exit_ts=exit_ts,
            side=trade.side,
        ),
    )


def _stats(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean_bps": statistics.fmean(values) * 10_000 if values else None,
        "sum_pct": sum(values) * 100 if values else 0.0,
        "positive_share": sum(value > 0 for value in values) / len(values) if values else None,
    }


def run_offset(
    selected: list[tuple[Trade, float, float]],
    *,
    offset_bps: float,
    timeout_minutes: int,
    hold_hours: int,
    maker_round_trip_bps: float,
) -> dict:
    cost = float(maker_round_trip_bps) / 10_000.0
    filled_values: list[float] = []
    nonfill_counterfactual: list[float] = []
    baseline_values: list[float] = []
    per_symbol: dict[str, list[float]] = defaultdict(list)
    filled_by_symbol: dict[str, int] = defaultdict(int)
    submitted_by_symbol: dict[str, int] = defaultdict(int)

    for trade, beta, baseline_residual in selected:
        submitted_by_symbol[trade.symbol] += 1
        baseline_net = baseline_residual - cost
        baseline_values.append(baseline_net)
        maker_trade = _maker_fill(
            trade,
            offset_bps=offset_bps,
            timeout_minutes=timeout_minutes,
            hold_hours=hold_hours,
        )
        if maker_trade is None:
            nonfill_counterfactual.append(baseline_net)
            per_symbol[trade.symbol].append(0.0)
            continue
        residual = (
            maker_trade.side
            * (maker_trade.asset_return - beta * maker_trade.btc_return)
            + maker_trade.funding_cashflow
            - cost
        )
        filled_values.append(residual)
        per_symbol[trade.symbol].append(residual)
        filled_by_symbol[trade.symbol] += 1

    submitted = len(selected)
    filled = len(filled_values)
    realized_per_signal = filled_values + [0.0] * (submitted - filled)
    positive_contrib = {
        symbol: max(0.0, sum(values))
        for symbol, values in per_symbol.items()
    }
    positive_total = sum(positive_contrib.values())
    max_concentration = (
        max(positive_contrib.values()) / positive_total
        if positive_total > 0 and positive_contrib
        else None
    )
    return {
        "offset_bps": float(offset_bps),
        "submitted": submitted,
        "filled": filled,
        "nonfilled": submitted - filled,
        "fill_rate": filled / submitted if submitted else None,
        "baseline_all_signals": _stats(baseline_values),
        "filled_realized": _stats(filled_values),
        "nonfill_market_counterfactual": _stats(nonfill_counterfactual),
        "realized_per_submitted_signal": _stats(realized_per_signal),
        "max_positive_symbol_concentration": max_concentration,
        "per_symbol": {
            symbol: {
                "submitted": submitted_by_symbol[symbol],
                "filled": filled_by_symbol[symbol],
                "fill_rate": (
                    filled_by_symbol[symbol] / submitted_by_symbol[symbol]
                    if submitted_by_symbol[symbol]
                    else None
                ),
                "realized_per_submitted_signal": _stats(values),
            }
            for symbol, values in sorted(per_symbol.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--percentile", type=float, default=70.0)
    parser.add_argument("--hold-hours", type=int, default=16)
    parser.add_argument("--beta-train-trades", type=int, default=60)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--offsets-bps", default="2,5,10,20")
    parser.add_argument("--timeout-minutes", type=int, default=60)
    parser.add_argument("--maker-round-trip-bps", type=float, default=6.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    symbols = sorted(path.stem for path in FUNDING_DIR.glob("*.csv"))
    candidates = [
        trade
        for symbol in symbols
        for trade in build_trades(
            symbol,
            percentile=args.percentile,
            hold_hours=args.hold_hours,
        )
    ]
    trained = _with_rolling_beta(candidates, beta_train_trades=args.beta_train_trades)
    selected, slot_rejections = _apply_slots(trained, max_positions=args.max_positions)
    runs = [
        run_offset(
            selected,
            offset_bps=float(raw),
            timeout_minutes=args.timeout_minutes,
            hold_hours=args.hold_hours,
            maker_round_trip_bps=args.maker_round_trip_bps,
        )
        for raw in args.offsets_bps.split(",")
        if raw.strip()
    ]
    primary = next((row for row in runs if row["offset_bps"] == 5.0), None)
    if primary:
        positive_symbols = sum(
            (row["realized_per_submitted_signal"]["mean_bps"] or 0.0) > 0
            for row in primary["per_symbol"].values()
        )
        primary["gate_diagnostics"] = {
            "positive_symbols": positive_symbols,
            "positive_symbols_required": 5,
            "fill_rate_pass": (primary["fill_rate"] or 0.0) >= 0.75,
            "economics_pass": (
                primary["realized_per_submitted_signal"]["mean_bps"] or 0.0
            ) > 0,
            "concentration_pass": (
                primary["max_positive_symbol_concentration"] is not None
                and primary["max_positive_symbol_concentration"] <= 0.35
            ),
        }
    payload = {
        "schema_id": "funding_positioning_v4_maker_audit",
        "research_only": True,
        "executable": False,
        "method": {
            "signal": f"p{args.percentile:g}/{args.hold_hours}h frozen V3",
            "beta_train_trades": args.beta_train_trades,
            "max_positions": args.max_positions,
            "slot_rejections": slot_rejections,
            "strict_trade_through": True,
            "timeout_minutes": args.timeout_minutes,
            "maker_round_trip_bps": args.maker_round_trip_bps,
            "queue_position_modelled": False,
        },
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
