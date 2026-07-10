#!/usr/bin/env python3
"""Research-only cross-pair additivity check for JPY round-level sweeps.

Follow-up to the frozen USDJPY anatomy: test the same fixed 00/50 and 00-only
geometry on EURJPY and GBPJPY without changing RR, stop, hold, tolerance or
costs.  Long and short remain independent.  This is an exploration gate only;
the 00-only follow-up was motivated by USDJPY and is therefore not pristine OOS.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.candle_coverage import assess_coverage
from bot.fx_harness import backtest_fx_setup
from scripts.run_fx_native_harness import _aggregate_rows_seconds, _coverage_rows, _load_rows
from scripts.run_fx_usdjpy_round_levels_oos_20260710 import COSTS, _metrics, _partition, _setup


PAIRS = ("EURJPY", "GBPJPY")
MODES = {"standard_00_50": 0.50, "big_figure_00": 1.00}


def main() -> int:
    outdir = ROOT / "reports/research/fx_jpy_cross_round_additivity_20260710"
    outdir.mkdir(parents=True, exist_ok=True)
    summaries: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    coverage_out: List[Dict[str, Any]] = []

    for pair in PAIRS:
        rows = _aggregate_rows_seconds(_load_rows(ROOT / f"data_cache/forex/{pair}_M5.csv"), 60)
        cov = assess_coverage(
            _coverage_rows(rows), symbol=pair, interval_min=60,
            min_coverage=0.98, max_gap_bars_allowed=24, max_flat_frac=0.05,
            min_bars=1000, market_closure_gap_bars=36,
        )
        coverage_out.append({"pair": pair, "bars": len(rows), "ok": cov.ok, "coverage": cov.coverage,
                             "max_gap_bars": cov.max_gap_bars, "reasons": ";".join(cov.reasons)})
        if not cov.ok:
            raise SystemExit(f"{pair} coverage failed: {cov.reasons}")
        start_ts = float(rows[0][0]); train_end = float(rows[len(rows)//2][0])
        validation_end = float(rows[3*len(rows)//4][0]); end_ts = float(rows[-1][0])

        for mode, step in MODES.items():
            for side in ("short", "long"):
                setup = _setup(step, side, 0.0006)
                for cost, (fee_bps, slip_bps) in COSTS.items():
                    print(f"[start] {pair} {mode} {side} {cost}", flush=True)
                    trades = backtest_fx_setup(
                        rows, setup, tp_rr=2.5, sl_atr=1.0, max_hold=120,
                        fee_bps=fee_bps, slippage_bps=slip_bps,
                    )
                    for t in trades:
                        t.update({"pair": pair, "mode": mode, "side_sleeve": side, "cost": cost})
                    all_trades.extend(trades)
                    parts = _partition(trades, start_ts, train_end, validation_end, end_ts)
                    for segment, part in parts.items():
                        summaries.append({"pair": pair, "mode": mode, "side": side, "cost": cost,
                                          "segment": segment, **_metrics(part)})

    def get(pair: str, segment: str) -> Dict[str, Any]:
        return next(r for r in summaries if r["pair"] == pair and r["mode"] == "big_figure_00"
                    and r["side"] == "short" and r["cost"] == "stress" and r["segment"] == segment)

    checks = {}
    for pair in PAIRS:
        full, validation, holdout = get(pair, "full"), get(pair, "validation"), get(pair, "holdout")
        checks[f"{pair}_full_stress_n_ge_30"] = int(full["trades"]) >= 30
        checks[f"{pair}_full_stress_pf_ge_1_05"] = float(full["pf"]) >= 1.05
        checks[f"{pair}_validation_stress_positive"] = float(validation["net_r"]) > 0
        checks[f"{pair}_holdout_stress_n_ge_5"] = int(holdout["trades"]) >= 5
        checks[f"{pair}_holdout_stress_pf_ge_1_10"] = float(holdout["pf"]) >= 1.10
    passed = all(checks.values())
    verdict = {
        "status": "PASS_EXPLORATION_ONLY" if passed else "FAIL_ADDITIVITY",
        "promotion_to_demo_or_live": False,
        "checks": checks,
        "note": "00-only was selected after the USDJPY anatomy and needs a new independent period even if additive",
    }

    with (outdir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(summaries)
    with (outdir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        keys = list(all_trades[0].keys()) if all_trades else ["entry_ts", "exit_ts", "r", "side"]
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n"); w.writeheader(); w.writerows(all_trades)
    with (outdir / "coverage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(coverage_out[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(coverage_out)
    (outdir / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# JPY-cross round-level additivity",
        "",
        f"- verdict: **{verdict['status']}**",
        "- fixed RR/SL/hold: `2.5 / 1.0 ATR / 120 H1 bars`",
        "- base/stress costs: `3 / 5 bps` round trip",
        "",
        "| pair | mode | side | cost | segment | N | netR | PF | WR |",
        "|---|---|---|---|---|---:|---:|---:|---:|",
    ]
    for r in summaries:
        if r["segment"] not in {"full", "validation", "holdout"}: continue
        lines.append(f"| {r['pair']} | {r['mode']} | {r['side']} | {r['cost']} | {r['segment']} | "
                     f"{r['trades']} | {float(r['net_r']):.3f} | {float(r['pf']):.3f} | {float(r['win_rate']):.3f} |")
    lines += ["", "## Checks", ""] + [f"- `{k}`: `{v}`" for k, v in checks.items()]
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[verdict] {verdict['status']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
