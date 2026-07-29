#!/usr/bin/env python3
"""Executable-constraint audit for funding-sign positioning.

This combines the useful parts of the earlier independent audits:

* strict rolling funding threshold and point-in-time BTC regime;
* non-overlapping trades per symbol and a three-slot portfolio cap;
* actual funding cashflows crossed during the hold;
* beta trained only on previously completed observations;
* maker/taker round-trip costs.

It remains bar-level research: maker fill probability, queue position and
cross-venue operational risk are not modelled, so this cannot authorize money.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

try:
    from scripts.audit_funding_positioning_v2 import Trade, build_trades
except ModuleNotFoundError:
    from audit_funding_positioning_v2 import Trade, build_trades


def _beta(train: list[Trade]) -> float:
    xs = [row.btc_return for row in train]
    ys = [row.asset_return for row in train]
    if len(xs) < 2:
        return 0.0
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    var = sum((value - mx) ** 2 for value in xs)
    if var <= 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var


def _with_rolling_beta(
    candidates: list[Trade],
    *,
    beta_train_trades: int,
) -> list[tuple[Trade, float, float]]:
    by_symbol: dict[str, list[Trade]] = defaultdict(list)
    out: list[tuple[Trade, float, float]] = []
    for trade in sorted(candidates, key=lambda row: (row.entry_ts, row.symbol)):
        matured = [
            row
            for row in by_symbol[trade.symbol]
            if row.exit_ts <= trade.entry_ts
        ]
        if len(matured) >= beta_train_trades:
            train = matured[-beta_train_trades:]
            beta = _beta(train)
            residual = (
                trade.side * (trade.asset_return - beta * trade.btc_return)
                + trade.funding_cashflow
            )
            out.append((trade, beta, residual))
        by_symbol[trade.symbol].append(trade)
    return out


def _apply_slots(
    rows: list[tuple[Trade, float, float]],
    *,
    max_positions: int,
) -> tuple[list[tuple[Trade, float, float]], int]:
    selected: list[tuple[Trade, float, float]] = []
    active_exits: list[int] = []
    rejected = 0
    grouped: dict[int, list[tuple[Trade, float, float]]] = defaultdict(list)
    for row in rows:
        grouped[row[0].entry_ts].append(row)

    for entry_ts in sorted(grouped):
        active_exits = [exit_ts for exit_ts in active_exits if exit_ts > entry_ts]
        available = max(0, max_positions - len(active_exits))
        ranked = sorted(
            grouped[entry_ts],
            key=lambda row: (-abs(row[0].funding_rate), row[0].symbol),
        )
        chosen = ranked[:available]
        rejected += len(ranked) - len(chosen)
        selected.extend(chosen)
        active_exits.extend(row[0].exit_ts for row in chosen)
    return selected, rejected


def _summary(
    rows: list[tuple[Trade, float, float]],
    *,
    round_trip_bps: float,
) -> dict:
    cost = round_trip_bps / 10_000.0
    raw_net = [trade.gross_return - cost for trade, _, _ in rows]
    residual_net = [residual - cost for _, _, residual in rows]
    return {
        "n": len(rows),
        "avg_gross_bps": (
            statistics.fmean(trade.gross_return for trade, _, _ in rows) * 10_000
            if rows else None
        ),
        "avg_net_bps": statistics.fmean(raw_net) * 10_000 if rows else None,
        "avg_residual_net_bps": (
            statistics.fmean(residual_net) * 10_000 if rows else None
        ),
        "sum_residual_net_pct": sum(residual_net) * 100 if rows else None,
        "positive_residual_share": (
            sum(value > 0 for value in residual_net) / len(residual_net)
            if rows else None
        ),
        "mean_beta": (
            statistics.fmean(beta for _, beta, _ in rows) if rows else None
        ),
    }


def run(
    *,
    percentile: float,
    hold_hours: int,
    beta_train_trades: int,
    max_positions: int,
) -> dict:
    try:
        from scripts.audit_funding_positioning_v2 import FUNDING_DIR
    except ModuleNotFoundError:
        from audit_funding_positioning_v2 import FUNDING_DIR

    symbols = sorted(path.stem for path in FUNDING_DIR.glob("*.csv"))
    candidates = [
        trade
        for symbol in symbols
        for trade in build_trades(
            symbol,
            percentile=percentile,
            hold_hours=hold_hours,
        )
    ]
    trained = _with_rolling_beta(
        candidates,
        beta_train_trades=beta_train_trades,
    )
    selected, slot_rejections = _apply_slots(
        trained,
        max_positions=max_positions,
    )
    return {
        "percentile": percentile,
        "hold_hours": hold_hours,
        "candidate_trades_after_symbol_nonoverlap": len(candidates),
        "trades_after_beta_warmup": len(trained),
        "slot_rejections": slot_rejections,
        "selected_trades": len(selected),
        "maker_6bps": _summary(selected, round_trip_bps=6.0),
        "taker_16bps": _summary(selected, round_trip_bps=16.0),
        "per_symbol_maker_6bps": {
            symbol: _summary(
                [row for row in selected if row[0].symbol == symbol],
                round_trip_bps=6.0,
            )
            for symbol in symbols
        },
        "per_regime_maker_6bps": {
            regime: _summary(
                [row for row in selected if row[0].regime == regime],
                round_trip_bps=6.0,
            )
            for regime in ("bull", "neutral", "bear")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--percentiles", default="60,70,85,90")
    parser.add_argument("--holds", default="8,16,24")
    parser.add_argument("--beta-train-trades", type=int, default=60)
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "schema_id": "funding_positioning_v3_audit",
        "research_only": True,
        "executable": False,
        "method": {
            "strict_percentile_exceedance": True,
            "no_symbol_overlap": True,
            "funding_cashflows_included": True,
            "rolling_beta_uses_only_previously_completed_trades": True,
            "max_positions": args.max_positions,
            "maker_fill_probability_modelled": False,
            "slot_ranking": "absolute_funding_rate",
        },
        "runs": [
            run(
                percentile=float(percentile),
                hold_hours=int(hold),
                beta_train_trades=args.beta_train_trades,
                max_positions=args.max_positions,
            )
            for percentile in args.percentiles.split(",")
            for hold in args.holds.split(",")
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
