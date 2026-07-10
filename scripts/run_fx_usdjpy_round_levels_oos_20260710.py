#!/usr/bin/env python3
"""Preregistered USDJPY round-level anatomy and chronological OOS gate.

Research only.  This does not write broker configuration or place orders.

The old native round-level helper used a 10-JPY step near USDJPY=160.  That is
a decade-handle detector, not the ordinary FX 00/50 structure.  This runner
keeps the already-selected decade handle as a contaminated historical control
and evaluates a newly frozen standard-level hypothesis:

* 00/50: 0.50 JPY step (primary)
* 00 only: 1.00 JPY step (structural robustness control)
* legacy decade: 10.00 JPY step (historical control; never promotion evidence)

Long and short are run as independent sleeves.  RR, stop, hold, tolerance and
costs are fixed before reading results.  Metrics are split by chronological bar
boundaries (50% train / 25% validation / 25% holdout) plus four time folds.
Even a PASS means only "advance to independent-feed replay/demo shadow".
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.candle_coverage import assess_coverage
from bot.fx_harness import backtest_fx_setup
from bot.fx_setups import FxSignal
from bot.liquidity_sweep import liquidity_sweep
from scripts.run_fx_native_harness import (
    _aggregate_rows_seconds,
    _coverage_rows,
    _load_rows,
)


LEVEL_MODES = {
    "standard_00_50": 0.50,
    "big_figure_00": 1.00,
    "legacy_decade": 10.00,
}
COSTS = {
    # Existing native-harness convention: values are charged per side, so base
    # is 3 bps round trip and stress is 5 bps round trip.
    "base": (1.0, 0.5),
    "stress": (1.5, 1.0),
}
PRIMARY = ("standard_00_50", "short")


def _setup(step: float, allowed_side: str, tol_frac: float) -> Callable[..., FxSignal]:
    def setup(rows: Sequence[Sequence[float]], *, atr_value: float | None = None) -> FxSignal:
        sw = liquidity_sweep(rows, atr_value=atr_value)
        if sw.event != "sweep_reversal":
            return FxSignal("round_level_sweep", False, False, "none", float("nan"), sw.reason)
        if sw.side != allowed_side:
            return FxSignal("round_level_sweep", False, False, "none", float("nan"), "side_block")
        price = float(rows[-1][4])
        nearest = round(float(sw.pool_level) / step) * step
        if abs(float(sw.pool_level) - nearest) > tol_frac * price:
            return FxSignal("round_level_sweep", False, False, "none", float("nan"), "pool_not_round")
        return FxSignal(
            "round_level_sweep",
            allowed_side == "long",
            allowed_side == "short",
            allowed_side,
            float(sw.pool_level),
            "round_stop_hunt",
            {"round_level": nearest, "round_step": step},
        )

    return setup


def _pf(rs: Sequence[float]) -> float:
    gp = sum(x for x in rs if x > 0)
    gl = -sum(x for x in rs if x < 0)
    if gl <= 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def _metrics(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    rs = [float(t["r"]) for t in trades]
    return {
        "trades": len(rs),
        "net_r": round(sum(rs), 4),
        "pf": _pf(rs),
        "win_rate": round(sum(1 for x in rs if x > 0) / len(rs), 4) if rs else 0.0,
    }


def _partition(
    trades: Sequence[Dict[str, Any]],
    start_ts: float,
    train_end: float,
    validation_end: float,
    end_ts: float,
) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "train": [t for t in trades if start_ts <= float(t["entry_ts"]) < train_end],
        "validation": [t for t in trades if train_end <= float(t["entry_ts"]) < validation_end],
        "holdout": [t for t in trades if validation_end <= float(t["entry_ts"]) <= end_ts],
        "full": list(trades),
    }


def _json_safe(v: Any) -> Any:
    if isinstance(v, float) and math.isinf(v):
        return "inf"
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data_cache/forex/USDJPY_M5.csv")
    ap.add_argument("--outdir", default="reports/research/fx_usdjpy_round_levels_oos_20260710")
    ap.add_argument("--interval-min", type=int, default=60)
    ap.add_argument("--tp-rr", type=float, default=2.5)
    ap.add_argument("--sl-atr", type=float, default=1.0)
    ap.add_argument("--max-hold", type=int, default=120)
    ap.add_argument("--tol-frac", type=float, default=0.0006)
    args = ap.parse_args()

    data_path = ROOT / args.data
    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    rows = _aggregate_rows_seconds(_load_rows(data_path), int(args.interval_min))
    if len(rows) < 1000:
        raise SystemExit(f"insufficient rows: {len(rows)}")

    coverage = assess_coverage(
        _coverage_rows(rows),
        symbol="USDJPY",
        interval_min=int(args.interval_min),
        min_coverage=0.98,
        max_gap_bars_allowed=24,
        max_flat_frac=0.05,
        min_bars=1000,
        market_closure_gap_bars=36,
    )
    if not coverage.ok:
        raise SystemExit(f"coverage gate failed: {coverage.reasons}")

    start_ts = float(rows[0][0])
    train_end = float(rows[len(rows) // 2][0])
    validation_end = float(rows[3 * len(rows) // 4][0])
    end_ts = float(rows[-1][0])
    fold_edges = [float(rows[i * len(rows) // 4][0]) for i in range(4)] + [end_ts + 1]

    summary_rows: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    for mode, step in LEVEL_MODES.items():
        for side in ("short", "long"):
            setup = _setup(step, side, float(args.tol_frac))
            for cost_name, (fee_bps, slippage_bps) in COSTS.items():
                print(f"[start] mode={mode} side={side} cost={cost_name}", flush=True)
                trades = backtest_fx_setup(
                    rows,
                    setup,
                    tp_rr=float(args.tp_rr),
                    sl_atr=float(args.sl_atr),
                    max_hold=int(args.max_hold),
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                )
                for t in trades:
                    t.update({"mode": mode, "side_sleeve": side, "cost": cost_name})
                all_trades.extend(trades)
                parts = _partition(trades, start_ts, train_end, validation_end, end_ts)
                fold_metrics = []
                for i in range(4):
                    fold_metrics.append(
                        _metrics([
                            t for t in trades
                            if fold_edges[i] <= float(t["entry_ts"]) < fold_edges[i + 1]
                        ])
                    )
                for segment, seg_trades in parts.items():
                    m = _metrics(seg_trades)
                    summary_rows.append({
                        "mode": mode,
                        "step": step,
                        "side": side,
                        "cost": cost_name,
                        "segment": segment,
                        **m,
                        "positive_folds": sum(1 for f in fold_metrics if float(f["net_r"]) > 0),
                        "min_fold_trades": min(int(f["trades"]) for f in fold_metrics),
                    })
                print(f"[done] mode={mode} side={side} cost={cost_name} full={_metrics(trades)}", flush=True)

    def row(mode: str, side: str, cost: str, segment: str) -> Dict[str, Any]:
        return next(r for r in summary_rows if (r["mode"], r["side"], r["cost"], r["segment"]) == (mode, side, cost, segment))

    primary_base = row(*PRIMARY, "base", "full")
    primary_stress = row(*PRIMARY, "stress", "full")
    primary_validation = row(*PRIMARY, "stress", "validation")
    primary_holdout = row(*PRIMARY, "stress", "holdout")
    gate_checks = {
        "full_base_n_ge_30": int(primary_base["trades"]) >= 30,
        "full_base_pf_ge_1_15": float(primary_base["pf"]) >= 1.15,
        "full_stress_pf_ge_1_05": float(primary_stress["pf"]) >= 1.05,
        "stress_positive_folds_ge_3": int(primary_stress["positive_folds"]) >= 3,
        "validation_stress_n_ge_5": int(primary_validation["trades"]) >= 5,
        "validation_stress_net_positive": float(primary_validation["net_r"]) > 0,
        "holdout_stress_n_ge_5": int(primary_holdout["trades"]) >= 5,
        "holdout_stress_pf_ge_1_10": float(primary_holdout["pf"]) >= 1.10,
        "holdout_stress_net_positive": float(primary_holdout["net_r"]) > 0,
    }
    passed = all(gate_checks.values())
    verdict = {
        "status": "PASS_TO_INDEPENDENT_FEED_REPLAY" if passed else "NO_PROMOTION",
        "promotion_to_demo_or_live": False,
        "primary": {"mode": PRIMARY[0], "side": PRIMARY[1]},
        "checks": gate_checks,
        "notes": [
            "legacy_decade is a selected historical control and cannot count as OOS evidence",
            "no historical news-event blackout is available in this run",
            "a PASS advances only to independent-feed execution replay and then demo shadow",
        ],
    }

    with (outdir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()), lineterminator="\n")
        w.writeheader(); w.writerows(summary_rows)
    with (outdir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        keys = list(all_trades[0].keys()) if all_trades else ["entry_ts", "exit_ts", "r", "side"]
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader(); w.writerows(all_trades)
    (outdir / "verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, default=_json_safe) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": str(data_path.relative_to(ROOT)),
        "bars": len(rows),
        "first_ts": start_ts,
        "last_ts": end_ts,
        "coverage": coverage.coverage,
        "coverage_reasons": coverage.reasons,
        "split": {"train_end": train_end, "validation_end": validation_end},
        "frozen": {
            "level_modes": LEVEL_MODES,
            "primary": PRIMARY,
            "tp_rr": args.tp_rr,
            "sl_atr": args.sl_atr,
            "max_hold": args.max_hold,
            "tol_frac": args.tol_frac,
            "costs": COSTS,
        },
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# USDJPY 00/50 vs big-figure vs legacy-decade OOS",
        "",
        f"- bars: `{len(rows)}`; coverage: `{coverage.coverage:.6f}`",
        f"- verdict: **{verdict['status']}** (never direct demo/live promotion)",
        f"- frozen RR/SL/hold: `{args.tp_rr} / {args.sl_atr} ATR / {args.max_hold} H1 bars`",
        "- costs: base `3 bps` round trip; stress `5 bps` round trip",
        "",
        "| mode | side | cost | segment | N | netR | PF | WR | folds+ |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in summary_rows:
        if r["segment"] not in {"full", "validation", "holdout"}:
            continue
        pf = "inf" if math.isinf(float(r["pf"])) else f"{float(r['pf']):.3f}"
        lines.append(
            f"| {r['mode']} | {r['side']} | {r['cost']} | {r['segment']} | {r['trades']} | "
            f"{float(r['net_r']):.3f} | {pf} | {float(r['win_rate']):.3f} | {r['positive_folds']}/4 |"
        )
    lines += ["", "## Gate checks", ""] + [f"- `{k}`: `{v}`" for k, v in gate_checks.items()]
    lines += [
        "",
        "Legacy decade results are replay-only because that family was selected on already-seen history.",
        "A primary PASS only authorizes an independent-feed replay, then demo shadow after execution/news gates.",
    ]
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[verdict] {verdict['status']}", flush=True)
    print(f"[output] {outdir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
