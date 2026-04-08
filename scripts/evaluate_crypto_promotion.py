#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "crypto_promotion_policy.json"
DEFAULT_BASELINE = (
    ROOT
    / "backtest_archive"
    / "portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual"
    / "summary.csv"
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_summary(path: Path) -> Dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"Empty summary.csv: {path}")
    row = rows[0]
    start = _safe_float(row.get("starting_equity"), 0.0)
    end = _safe_float(row.get("ending_equity"), 0.0)
    ret = 0.0
    if start > 0:
        ret = ((end - start) / start) * 100.0
    return {
        "path": str(path),
        "tag": row.get("tag", ""),
        "days": _safe_int(row.get("days"), 0),
        "starting_equity": start,
        "ending_equity": end,
        "return_pct": ret,
        "trades": _safe_int(row.get("trades"), 0),
        "net_pnl": _safe_float(row.get("net_pnl"), 0.0),
        "profit_factor": _safe_float(row.get("profit_factor"), 0.0),
        "winrate": _safe_float(row.get("winrate"), 0.0),
        "max_drawdown": _safe_float(row.get("max_drawdown"), math.inf),
    }


def _load_walkforward(path: Path) -> Dict[str, Any]:
    data = _load_json(path)
    windows = _safe_int(data.get("windows"), 0)
    passed = _safe_int(data.get("passed"), 0)
    pass_ratio = float(passed / windows) if windows > 0 else 0.0
    return {
        "path": str(path),
        "tag": str(data.get("tag") or ""),
        "windows": windows,
        "passed": passed,
        "pass_ratio": pass_ratio,
        "avg_pf": _safe_float(data.get("avg_pf"), 0.0),
        "avg_net_pnl": _safe_float(data.get("avg_net_pnl"), 0.0),
        "avg_max_drawdown": _safe_float(data.get("avg_max_drawdown"), math.inf),
    }


def _annual_gate(candidate: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    reasons: list[str] = []
    if candidate["net_pnl"] < _safe_float(cfg.get("min_net_pnl"), 0.0):
        reasons.append("net_pnl_below_min")
    if candidate["profit_factor"] < _safe_float(cfg.get("min_profit_factor"), 1.0):
        reasons.append("profit_factor_below_min")
    if candidate["max_drawdown"] > _safe_float(cfg.get("max_drawdown_pct"), math.inf):
        reasons.append("drawdown_above_max")
    if candidate["trades"] < _safe_int(cfg.get("min_trades"), 0):
        reasons.append("trades_below_min")
    return {"passed": not reasons, "reasons": reasons}


def _walkforward_gate(wf: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    reasons: list[str] = []
    if wf["windows"] < _safe_int(cfg.get("min_windows"), 0):
        reasons.append("windows_below_min")
    if wf["pass_ratio"] < _safe_float(cfg.get("min_pass_ratio"), 0.0):
        reasons.append("pass_ratio_below_min")
    if wf["avg_pf"] < _safe_float(cfg.get("min_avg_pf"), 0.0):
        reasons.append("avg_pf_below_min")
    if wf["avg_net_pnl"] < _safe_float(cfg.get("min_avg_net_pnl"), 0.0):
        reasons.append("avg_net_pnl_below_min")
    if wf["avg_max_drawdown"] > _safe_float(cfg.get("max_avg_drawdown_pct"), math.inf):
        reasons.append("avg_drawdown_above_max")
    return {"passed": not reasons, "reasons": reasons}


def _portfolio_compare(candidate: Dict[str, Any], baseline: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    reasons: list[str] = []
    winning_paths: list[str] = []

    ret_delta = candidate["return_pct"] - baseline["return_pct"]
    pf_delta = candidate["profit_factor"] - baseline["profit_factor"]
    dd_ratio = (
        candidate["max_drawdown"] / baseline["max_drawdown"]
        if baseline["max_drawdown"] > 0
        else math.inf
    )
    ret_ratio = (
        candidate["return_pct"] / baseline["return_pct"]
        if baseline["return_pct"] > 0
        else 0.0
    )

    reject_cfg = dict(cfg.get("reject_if") or {})
    if ret_delta < -_safe_float(reject_cfg.get("max_return_drop_pct"), math.inf):
        reasons.append("return_drop_too_large")
    if pf_delta < -_safe_float(reject_cfg.get("max_pf_drop"), math.inf):
        reasons.append("pf_drop_too_large")
    if dd_ratio > _safe_float(reject_cfg.get("max_dd_mult"), math.inf):
        reasons.append("dd_ratio_too_large")

    for rule in list(cfg.get("improvement_paths") or []):
        name = str(rule.get("name") or "unnamed")
        ok = True
        if "min_return_delta_pct" in rule and ret_delta < _safe_float(rule.get("min_return_delta_pct"), 0.0):
            ok = False
        if "max_dd_mult" in rule and dd_ratio > _safe_float(rule.get("max_dd_mult"), math.inf):
            ok = False
        if "min_pf_delta" in rule and pf_delta < _safe_float(rule.get("min_pf_delta"), 0.0):
            ok = False
        if "min_return_ratio" in rule and ret_ratio < _safe_float(rule.get("min_return_ratio"), 0.0):
            ok = False
        if "max_dd_ratio" in rule and dd_ratio > _safe_float(rule.get("max_dd_ratio"), math.inf):
            ok = False
        if ok:
            winning_paths.append(name)

    if not winning_paths:
        reasons.append("no_improvement_path_cleared")

    return {
        "passed": not reasons,
        "reasons": reasons,
        "winning_paths": winning_paths,
        "metrics": {
            "candidate_return_pct": round(candidate["return_pct"], 4),
            "baseline_return_pct": round(baseline["return_pct"], 4),
            "return_delta_pct": round(ret_delta, 4),
            "candidate_pf": round(candidate["profit_factor"], 4),
            "baseline_pf": round(baseline["profit_factor"], 4),
            "pf_delta": round(pf_delta, 4),
            "candidate_dd": round(candidate["max_drawdown"], 4),
            "baseline_dd": round(baseline["max_drawdown"], 4),
            "dd_ratio": round(dd_ratio, 4) if math.isfinite(dd_ratio) else None,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate whether a crypto candidate clears explicit promotion rules.")
    ap.add_argument("--annual-summary", required=True, help="Candidate annual summary.csv")
    ap.add_argument("--walkforward-latest", required=True, help="Candidate walkforward_latest.json")
    ap.add_argument("--baseline-summary", default=str(DEFAULT_BASELINE), help="Baseline annual summary.csv")
    ap.add_argument("--policy", default=str(DEFAULT_POLICY), help="Promotion policy JSON")
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    args = ap.parse_args()

    annual_summary = Path(args.annual_summary).expanduser()
    walkforward_latest = Path(args.walkforward_latest).expanduser()
    baseline_summary = Path(args.baseline_summary).expanduser()
    policy_path = Path(args.policy).expanduser()

    candidate = _load_summary(annual_summary)
    baseline = _load_summary(baseline_summary)
    walkforward = _load_walkforward(walkforward_latest)
    policy = _load_json(policy_path)

    annual_gate = _annual_gate(candidate, dict(policy.get("annual_gate") or {}))
    walkforward_gate = _walkforward_gate(walkforward, dict(policy.get("walkforward_gate") or {}))
    compare_gate = _portfolio_compare(candidate, baseline, dict(policy.get("portfolio_compare") or {}))

    overall_pass = bool(annual_gate["passed"] and walkforward_gate["passed"] and compare_gate["passed"])
    result = {
        "policy_version": str(policy.get("policy_version") or "unknown"),
        "candidate": candidate,
        "baseline": baseline,
        "walkforward": walkforward,
        "annual_gate": annual_gate,
        "walkforward_gate": walkforward_gate,
        "portfolio_compare": compare_gate,
        "promotion_passed": overall_pass,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"policy_version={result['policy_version']}")
    print(f"candidate={candidate['tag']} annual_return={candidate['return_pct']:.2f}% pf={candidate['profit_factor']:.3f} dd={candidate['max_drawdown']:.2f}")
    print(f"walkforward={walkforward['tag']} pass_ratio={walkforward['pass_ratio']:.2%} avg_pf={walkforward['avg_pf']:.3f} avg_dd={walkforward['avg_max_drawdown']:.2f}")
    print(f"baseline={baseline['tag']} annual_return={baseline['return_pct']:.2f}% pf={baseline['profit_factor']:.3f} dd={baseline['max_drawdown']:.2f}")
    print(f"annual_gate={'PASS' if annual_gate['passed'] else 'FAIL'} reasons={annual_gate['reasons']}")
    print(f"walkforward_gate={'PASS' if walkforward_gate['passed'] else 'FAIL'} reasons={walkforward_gate['reasons']}")
    print(
        f"portfolio_compare={'PASS' if compare_gate['passed'] else 'FAIL'} "
        f"winning_paths={compare_gate['winning_paths']} reasons={compare_gate['reasons']}"
    )
    print(f"promotion_passed={int(overall_pass)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
