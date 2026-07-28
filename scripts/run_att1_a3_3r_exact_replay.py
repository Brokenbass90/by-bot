#!/usr/bin/env python3
"""Run the preregistered exact ATT1 champion vs A3/fixed-3R replay.

Research-only. Every backtest is cache-only and uses an isolated subprocess
environment. The script is resumable: an existing run directory with both
summary.csv and trades.csv is reused.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.wf_folds import purge_embargo_folds


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def _find_completed_run(tag: str) -> Path | None:
    candidates = sorted((ROOT / "backtest_runs").glob(f"portfolio_*_{tag}"))
    for path in reversed(candidates):
        if (path / "summary.csv").is_file() and (path / "trades.csv").is_file():
            return path
    return None


def _run_one(spec: dict[str, Any], variant: str, cost: dict[str, Any]) -> Path:
    tag = f"att1_a3_exact_{variant}_{str(cost['round_trip_bps']).replace('.', 'p')}bps_20260728"
    existing = _find_completed_run(tag)
    if existing:
        print(f"REUSE {tag}: {existing}", flush=True)
        return existing

    window = spec["window"]
    portfolio = spec["portfolio"]
    command = [
        sys.executable,
        "backtest/run_portfolio.py",
        "--symbols",
        ",".join(spec["universe"]),
        "--strategies",
        "alt_trendline_touch_v1",
        "--days",
        str(window["days"]),
        "--end",
        str(window["end_utc"]),
        "--starting_equity",
        str(portfolio["starting_equity"]),
        "--risk_pct",
        str(portfolio["risk_pct"]),
        "--cap_notional",
        str(portfolio["cap_notional"]),
        "--leverage",
        str(portfolio["leverage"]),
        "--max_positions",
        str(portfolio["max_positions"]),
        "--fee_bps",
        str(cost["fee_bps_per_side"]),
        "--slippage_bps",
        str(cost["slippage_bps_per_side"]),
        "--base_interval_min",
        str(window["base_interval_min"]),
        "--entry-on-next-open",
        "--tag",
        tag,
    ]
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in spec["common_effective_env"].items()})
    env.update({str(k): str(v) for k, v in spec["variants"][variant].items()})
    print(f"RUN {tag}", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    completed = _find_completed_run(tag)
    if not completed:
        raise RuntimeError(f"backtest completed without expected output for tag={tag}")
    return completed


def _float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _read_first_csv(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.DictReader(handle))


def _grade_run(
    run_dir: Path,
    *,
    risk_pct: float,
    fold_count: int,
    embargo_ms: int,
) -> dict[str, Any]:
    summary = _read_first_csv(run_dir / "summary.csv")
    trades: list[dict[str, Any]] = []
    monthly: dict[str, float] = defaultdict(float)
    wins = losses = 0.0
    with (run_dir / "trades.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            pnl = _float(row.get("pnl"))
            r_value = _float(row.get("pnl_pct_equity")) / risk_pct
            entry_ts = int(row["entry_ts"])
            exit_ts = int(row["exit_ts"])
            trades.append({"entry_ts": entry_ts, "exit_ts": exit_ts, "r": r_value})
            month = datetime.fromtimestamp(exit_ts / 1000.0, tz=timezone.utc).strftime("%Y-%m")
            monthly[month] += pnl
            if pnl > 0:
                wins += pnl
            elif pnl < 0:
                losses += -pnl

    fold_set = purge_embargo_folds(
        trades,
        n_folds=fold_count,
        embargo=float(embargo_ms),
    )
    folds = []
    for fold in fold_set.folds:
        values = [float(v) for v in fold["r_list"]]
        folds.append(
            {
                "fold": fold["fold"],
                "trades": len(values),
                "net_r": round(sum(values), 6),
                "expectancy_r": round(sum(values) / len(values), 6) if values else None,
                "positive": bool(sum(values) > 0),
            }
        )
    negative_months = sorted(month for month, pnl in monthly.items() if pnl < 0)
    return {
        "run_dir": str(run_dir.relative_to(ROOT)),
        "trades": len(trades),
        "net_pnl": _float(summary.get("net_pnl")),
        "ending_equity": _float(summary.get("ending_equity")),
        "profit_factor": wins / losses if losses > 0 else (math.inf if wins > 0 else 0.0),
        "expectancy_r": round(sum(t["r"] for t in trades) / len(trades), 6) if trades else None,
        "net_r": round(sum(t["r"] for t in trades), 6),
        "max_drawdown": _float(summary.get("max_drawdown")),
        "negative_months": len(negative_months),
        "negative_month_labels": negative_months,
        "folds": folds,
        "folds_positive": sum(1 for fold in folds if fold["positive"]),
        "folds_used_trades": fold_set.used,
        "folds_purged": fold_set.purged,
        "folds_embargoed": fold_set.embargoed,
    }


def _capital_gate(
    spec: dict[str, Any],
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gate = spec["capital_gate"]
    comparison = spec["comparison_gate"]
    key = str(float(gate["evaluated_at_round_trip_bps"]))
    challenger = results["a3_fixed_3r"][key]
    champion = results["champion"][key]
    fold_expectancies = [
        float(fold["expectancy_r"])
        for fold in challenger["folds"]
        if fold["expectancy_r"] is not None
    ]
    checks = {
        "min_trades": challenger["trades"] >= int(gate["min_trades"]),
        "min_positive_folds": challenger["folds_positive"] >= int(gate["min_positive_folds"]),
        "min_profit_factor": challenger["profit_factor"] >= float(gate["min_profit_factor"]),
        "min_expectancy_r": (
            challenger["expectancy_r"] is not None
            and challenger["expectancy_r"] >= float(gate["min_expectancy_r"])
        ),
        "min_single_fold_expectancy_r": (
            len(fold_expectancies) == int(spec["fold_method"]["folds"])
            and min(fold_expectancies) >= float(gate["min_single_fold_expectancy_r"])
        ),
        "improves_champion_expectancy": (
            not comparison["challenger_must_improve_expectancy_r_at_11bps"]
            or challenger["expectancy_r"] > champion["expectancy_r"]
        ),
        "does_not_increase_negative_months": (
            not comparison["challenger_must_not_increase_negative_months"]
            or challenger["negative_months"] <= champion["negative_months"]
        ),
    }
    quantitative_pass = all(checks.values())
    return {
        "checks": checks,
        "quantitative_pass": quantitative_pass,
        "forward_shadow_labels_present": False,
        "execution_parity_present": False,
        "capital_authorized": False,
        "verdict": "BLOCKED_FORWARD_SHADOW" if quantitative_pass else "FAIL",
    }


def _write_verdict(path: Path, receipt: dict[str, Any]) -> None:
    gate = receipt["capital_gate"]
    lines = [
        "# ATT1 A3/3R exact replay",
        "",
        f"- Verdict: **{gate['verdict']}**",
        f"- Quantitative gate: **{'PASS' if gate['quantitative_pass'] else 'FAIL'}**",
        "- Capital authority: **NO**",
        "- Live ATT1 changed: **NO**",
        "",
        "| variant | round trip | trades | PF | expectancy R | positive folds | negative months |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in ("champion", "a3_fixed_3r"):
        for cost_key, result in sorted(
            receipt["results"][variant].items(), key=lambda item: float(item[0])
        ):
            lines.append(
                f"| {variant} | {float(cost_key):.1f} bps | {result['trades']} | "
                f"{result['profit_factor']:.3f} | {result['expectancy_r']:.4f} | "
                f"{result['folds_positive']}/4 | {result['negative_months']} |"
            )
    lines.extend(
        [
            "",
            "The R value is the preregistered fixed-risk estimate "
            "`pnl_pct_equity / 0.0075`; all capital decisions remain blocked "
            "until forward-shadow labels and execution parity exist.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--spec",
        default="configs/preregistered/att1_a3_3r_exact_replay_v1_20260728.json",
    )
    parser.add_argument(
        "--output",
        default="reports/research/att1_a3_3r_exact_replay_v1_20260728",
    )
    args = parser.parse_args()

    spec_path = (ROOT / args.spec).resolve()
    spec = _load_json(spec_path)
    out_dir = (ROOT / args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = out_dir / "progress.json"
    results: dict[str, dict[str, Any]] = {"champion": {}, "a3_fixed_3r": {}}
    fold_cfg = spec["fold_method"]
    for variant in ("champion", "a3_fixed_3r"):
        for cost in spec["cost_scenarios"]:
            run_dir = _run_one(spec, variant, cost)
            cost_key = str(float(cost["round_trip_bps"]))
            results[variant][cost_key] = _grade_run(
                run_dir,
                risk_pct=float(spec["portfolio"]["risk_pct"]),
                fold_count=int(fold_cfg["folds"]),
                embargo_ms=int(fold_cfg["embargo_ms"]),
            )
            _write_json(
                progress_path,
                {
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "results": results,
                },
            )

    receipt = {
        "schema_id": "att1_a3_3r_exact_replay_receipt_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "money_authority": False,
        "live_mutation": False,
        "preregister": str(spec_path.relative_to(ROOT)),
        "results": results,
    }
    receipt["capital_gate"] = _capital_gate(spec, results)
    _write_json(out_dir / "receipt.json", receipt)
    _write_verdict(out_dir / "VERDICT.md", receipt)
    print(json.dumps(receipt["capital_gate"], ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
