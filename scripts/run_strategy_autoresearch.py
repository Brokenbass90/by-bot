#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import csv
import itertools
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
BACKTEST_RUNS = ROOT / "backtest_runs"


def _repo_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python3"
    if venv_python.exists() and os.access(venv_python, os.X_OK):
        return str(venv_python)
    return sys.executable


@dataclass
class CandidateResult:
    run_id: int
    tag: str
    run_dir: str
    passed: bool
    fail_reasons: str
    score: float
    trades: int
    net_pnl: float
    profit_factor: float
    winrate: float
    max_drawdown: float
    negative_months: int
    positive_months: int
    max_negative_streak: int
    worst_month_pnl: float
    overrides_json: str


def _slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _load_spec(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _iter_grid(grid: Dict[str, list]) -> Iterable[Dict[str, str]]:
    keys = list(grid.keys())
    if not keys:
        yield {}
        return
    value_lists = [grid[k] for k in keys]
    for values in itertools.product(*value_lists):
        yield {k: str(v) for k, v in zip(keys, values)}


def _grid_size(grid: Dict[str, list]) -> int:
    total = 1
    for values in grid.values():
        total *= max(1, len(values))
    return total


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _command_context(spec: dict, overrides: Dict[str, str], tag: str) -> Dict[str, str]:
    ctx: Dict[str, str] = {
        "tag": tag,
        "python": _repo_python(),
        "name": str(spec.get("name", "")),
    }
    for src in (spec.get("base_env", {}), overrides):
        for k, v in src.items():
            ctx[str(k)] = str(v)
    return ctx


def _latest_run_dir(tag: str) -> Path | None:
    matches = sorted(
        [p for p in BACKTEST_RUNS.iterdir() if p.is_dir() and p.name.endswith(f"_{tag}")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _read_summary(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"Empty summary: {path}")
    return rows[0]


def _to_float(value: str) -> float:
    raw = str(value or "").strip().lower()
    if raw in {"", "nan"}:
        return float("nan")
    if raw in {"inf", "+inf"}:
        return float("inf")
    if raw == "-inf":
        return float("-inf")
    return float(raw)


def _load_monthly_values(run_dir: Path) -> List[float]:
    monthly_path = run_dir / "monthly.csv"
    if monthly_path.exists():
        with monthly_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        values: List[float] = []
        for row in rows:
            for key in ("month_return_pct", "pnl", "net_pnl", "month_pnl"):
                if key in row and str(row.get(key, "")).strip():
                    try:
                        values.append(_to_float(row[key]))
                        break
                    except Exception:
                        pass
        if values:
            return values

    trades_path = run_dir / "trades.csv"
    if trades_path.exists():
        month_totals: Dict[str, float] = collections.defaultdict(float)
        with trades_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            ts_raw = row.get("exit_ts") or row.get("ts_exit") or row.get("close_ts") or row.get("exit_time")
            pnl_raw = row.get("pnl") or row.get("net_pnl") or row.get("month_return_pct") or "0"
            if not str(ts_raw or "").strip():
                continue
            try:
                ts_val = float(str(ts_raw).strip())
                if ts_val > 10_000_000_000:
                    ts_val /= 1000.0
                month = datetime.fromtimestamp(ts_val, tz=timezone.utc).strftime("%Y-%m")
                month_totals[month] += _to_float(pnl_raw)
            except Exception:
                continue
        if month_totals:
            return [month_totals[k] for k in sorted(month_totals)]
    return []


def _monthly_metrics(run_dir: Path) -> dict:
    values = _load_monthly_values(run_dir)
    if not values:
        return {
            "negative_months": 0,
            "positive_months": 0,
            "max_negative_streak": 0,
            "worst_month_pnl": 0.0,
        }
    neg = sum(1 for x in values if x < 0)
    pos = sum(1 for x in values if x > 0)
    streak = 0
    best_streak = 0
    for x in values:
        if x < 0:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0
    return {
        "negative_months": neg,
        "positive_months": pos,
        "max_negative_streak": best_streak,
        "worst_month_pnl": min(values),
    }


def _extract_metrics(summary: dict, spec: dict) -> dict:
    field_map = {
        "trades": "trades",
        "net_pnl": "net_pnl",
        "profit_factor": "profit_factor",
        "winrate": "winrate",
        "max_drawdown": "max_drawdown",
    }
    field_map.update(spec.get("field_map", {}))
    if "field_map" not in spec and "compounded_return_pct" in summary:
        # Equities summaries use different field names than the crypto portfolio runs.
        # Auto-detect the common schema so new specs do not silently degrade into NaNs.
        field_map["net_pnl"] = "compounded_return_pct"
        field_map["winrate"] = "winrate_pct"
        field_map["max_drawdown"] = "max_monthly_dd_pct"
    scales = spec.get("field_scales", {})
    if "field_scales" not in spec and field_map.get("winrate") == "winrate_pct":
        scales = {**scales, "winrate": 0.01}

    metrics: dict[str, float] = {}
    for key, src in field_map.items():
        raw = summary.get(src, "")
        val = _to_float(raw)
        scale = float(scales.get(key, 1.0))
        if math.isfinite(val):
            val *= scale
            if key == "max_drawdown":
                val = abs(val)
        metrics[key] = val
    return metrics


def _score_candidate(summary: dict, spec: dict) -> tuple[bool, str, float]:
    constraints = spec.get("constraints", {})
    weights = spec.get("score_weights", {})
    metrics = _extract_metrics(summary, spec)

    trades_raw = float(metrics.get("trades") or 0.0)
    trades = int(trades_raw) if math.isfinite(trades_raw) else 0
    net_pnl = float(metrics.get("net_pnl") or 0.0)
    if not math.isfinite(net_pnl):
        net_pnl = float("-inf")
    profit_factor = float(metrics.get("profit_factor") or 0.0)
    if not math.isfinite(profit_factor):
        profit_factor = float("nan")
    winrate = float(metrics.get("winrate") or 0.0)
    if not math.isfinite(winrate):
        winrate = float("nan")
    max_drawdown = float(metrics.get("max_drawdown") or 0.0)
    if not math.isfinite(max_drawdown):
        max_drawdown = float("inf")
    latest_entry_age_days = float(metrics.get("latest_entry_age_days") or 0.0)
    if not math.isfinite(latest_entry_age_days):
        latest_entry_age_days = float("inf")

    fail_reasons: List[str] = []
    if trades < int(constraints.get("min_trades", 0)):
        fail_reasons.append(f"trades<{constraints['min_trades']}")
    if math.isfinite(profit_factor) and profit_factor < float(constraints.get("min_profit_factor", 0.0)):
        fail_reasons.append(f"pf<{constraints['min_profit_factor']}")
    if math.isfinite(max_drawdown) and max_drawdown > float(constraints.get("max_drawdown", math.inf)):
        fail_reasons.append(f"dd>{constraints['max_drawdown']}")
    if net_pnl < float(constraints.get("min_net_pnl", -math.inf)):
        fail_reasons.append(f"net<{constraints['min_net_pnl']}")
    if "max_latest_entry_age_days" in constraints and latest_entry_age_days > float(constraints.get("max_latest_entry_age_days", math.inf)):
        fail_reasons.append(f"entry_age>{constraints['max_latest_entry_age_days']}")

    score = (
        float(weights.get("net_pnl", 1.0)) * net_pnl
        + float(weights.get("profit_factor", 3.0)) * (max(0.0, profit_factor - 1.0) if math.isfinite(profit_factor) else 0.0)
        + float(weights.get("winrate", 8.0)) * (max(0.0, winrate - 0.5) if math.isfinite(winrate) else 0.0)
        - float(weights.get("max_drawdown", 1.0)) * (max_drawdown if math.isfinite(max_drawdown) else 0.0)
        - float(weights.get("latest_entry_age_days", 0.0)) * (latest_entry_age_days if math.isfinite(latest_entry_age_days) else 0.0)
        + float(weights.get("trades", 0.05)) * min(trades, int(weights.get("trades_cap", 40)))
    )
    passed = not fail_reasons
    if not passed:
        score -= 1000.0
    return passed, ";".join(fail_reasons), score


def _run_backtest(spec: dict, overrides: Dict[str, str], run_id: int) -> CandidateResult:
    name = _slug(spec["name"])
    tag = f"{name}_r{run_id:03d}"

    # Resume support: if a run dir with this tag already exists and has a summary,
    # skip the subprocess and re-use the cached result.
    existing_dir = _latest_run_dir(tag)
    # Only reuse if the run completed with at least 1 trade (avoids caching bad 0-trade runs)
    if existing_dir is not None and (existing_dir / "summary.csv").exists():
        _check_summary = _read_summary(existing_dir / "summary.csv")
        if int(float(_check_summary.get("trades", 0) or 0)) == 0:
            existing_dir = None  # force re-run
    if existing_dir is not None and (existing_dir / "summary.csv").exists():
        summary = _read_summary(existing_dir / "summary.csv")
        passed, fail_reasons, score = _score_candidate(summary, spec)
        metrics = _extract_metrics(summary, spec)
        month_metrics = _monthly_metrics(existing_dir)
        constraints = spec.get("constraints", {})
        score_weights = spec.get("score_weights", {})
        extra_fail_reasons: List[str] = []
        if int(month_metrics["negative_months"]) > int(constraints.get("max_negative_months", 10**9)):
            extra_fail_reasons.append(f"neg_months>{constraints['max_negative_months']}")
        if int(month_metrics["max_negative_streak"]) > int(constraints.get("max_negative_streak", 10**9)):
            extra_fail_reasons.append(f"neg_streak>{constraints['max_negative_streak']}")
        if float(month_metrics["worst_month_pnl"]) < float(constraints.get("min_worst_month_pnl", -1e18)):
            extra_fail_reasons.append(f"worst_month<{constraints['min_worst_month_pnl']}")
        if extra_fail_reasons:
            passed = False
            fail_reasons = ";".join(x for x in [fail_reasons, *extra_fail_reasons] if x)
            score -= 1000.0
        return CandidateResult(
            run_id=run_id, tag=tag, run_dir=str(existing_dir),
            passed=passed, fail_reasons=fail_reasons, score=score,
            trades=int(float(metrics.get("trades") or 0)),
            net_pnl=float(metrics.get("net_pnl") or 0.0),
            profit_factor=float(metrics.get("profit_factor") or 0.0),
            winrate=float(metrics.get("winrate") or 0.0),
            max_drawdown=float(metrics.get("max_drawdown") or 0.0),
            negative_months=int(month_metrics["negative_months"]),
            positive_months=int(month_metrics["positive_months"]),
            max_negative_streak=int(month_metrics["max_negative_streak"]),
            worst_month_pnl=float(month_metrics["worst_month_pnl"]),
            overrides_json=json.dumps(overrides, ensure_ascii=True, sort_keys=True),
        )

    env = os.environ.copy()
    for k, v in spec.get("base_env", {}).items():
        env[str(k)] = str(v)
    for k, v in overrides.items():
        env[str(k)] = str(v)
    if spec.get("cache_only", False):
        env["BACKTEST_CACHE_ONLY"] = "1"

    if "command" in spec:
        fmt = _SafeFormatDict(_command_context(spec, overrides, tag))
        cmd = [str(x).format_map(fmt) for x in spec["command"]]
    else:
        cmd = [
            _repo_python(),
            "backtest/run_portfolio.py",
            "--symbols",
            ",".join(spec["symbols"]),
            "--strategies",
            ",".join(spec["strategies"]),
            "--days",
            str(spec["days"]),
            "--end",
            str(spec["end_date"]),
            "--tag",
            tag,
        ]

    subprocess.run(cmd, cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run_dir = _latest_run_dir(tag)
    if run_dir is None:
        raise RuntimeError(f"Missing run dir for tag={tag}")
    summary = _read_summary(run_dir / "summary.csv")
    passed, fail_reasons, score = _score_candidate(summary, spec)
    metrics = _extract_metrics(summary, spec)
    month_metrics = _monthly_metrics(run_dir)

    constraints = spec.get("constraints", {})
    score_weights = spec.get("score_weights", {})
    extra_fail_reasons: List[str] = []
    if int(month_metrics["negative_months"]) > int(constraints.get("max_negative_months", 10**9)):
        extra_fail_reasons.append(f"neg_months>{constraints['max_negative_months']}")
    if int(month_metrics["max_negative_streak"]) > int(constraints.get("max_negative_streak", 10**9)):
        extra_fail_reasons.append(f"neg_streak>{constraints['max_negative_streak']}")
    if float(month_metrics["worst_month_pnl"]) < float(constraints.get("min_worst_month_pnl", -math.inf)):
        extra_fail_reasons.append(f"worst_month<{constraints['min_worst_month_pnl']}")
    if extra_fail_reasons:
        passed = False
        fail_reasons = ";".join(x for x in [fail_reasons, *extra_fail_reasons] if x)
        score -= 1000.0

    score -= float(score_weights.get("negative_months", 0.0)) * float(month_metrics["negative_months"])
    score -= float(score_weights.get("max_negative_streak", 0.0)) * float(month_metrics["max_negative_streak"])
    worst_month = float(month_metrics["worst_month_pnl"])
    if worst_month < 0:
        score -= float(score_weights.get("worst_month_pnl", 0.0)) * abs(worst_month)

    return CandidateResult(
        run_id=run_id,
        tag=tag,
        run_dir=str(run_dir),
        passed=passed,
        fail_reasons=fail_reasons,
        score=score,
        trades=int(float(metrics.get("trades") or 0)),
        net_pnl=float(metrics.get("net_pnl") or 0.0),
        profit_factor=float(metrics.get("profit_factor") or 0.0),
        winrate=float(metrics.get("winrate") or 0.0),
        max_drawdown=float(metrics.get("max_drawdown") or 0.0),
        negative_months=int(month_metrics["negative_months"]),
        positive_months=int(month_metrics["positive_months"]),
        max_negative_streak=int(month_metrics["max_negative_streak"]),
        worst_month_pnl=float(month_metrics["worst_month_pnl"]),
        overrides_json=json.dumps(overrides, ensure_ascii=True, sort_keys=True),
    )


def _append_result_row(path: Path, fields: List[str], result: CandidateResult) -> None:
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writerow(result.__dict__)


def _write_ranked(path: Path, fields: List[str], results: List[CandidateResult]) -> List[CandidateResult]:
    ranked = sorted(results, key=lambda r: (not r.passed, -r.score, -r.net_pnl))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ranked:
            w.writerow(r.__dict__)
    return ranked


def _write_progress(path: Path, *, spec_path: Path, current: int, total: int, result: CandidateResult) -> None:
    payload = {
        "spec": str(spec_path),
        "current": current,
        "total": total,
        "last_tag": result.tag,
        "last_passed": result.passed,
        "last_score": result.score,
        "last_net_pnl": result.net_pnl,
        "last_profit_factor": result.profit_factor,
        "last_winrate": result.winrate,
        "last_fail_reasons": result.fail_reasons,
        "last_run_dir": result.run_dir,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Systematic autoresearch-style sweep for pinned backtest windows.")
    ap.add_argument("--spec", required=True, help="Path to autoresearch JSON spec.")
    ap.add_argument("--limit", type=int, default=0, help="Optional cap on number of grid candidates.")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = (ROOT / spec_path).resolve()
    spec = _load_spec(spec_path)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = BACKTEST_RUNS / f"autoresearch_{stamp}_{_slug(spec['name'])}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "spec.json").write_text(json.dumps(spec, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    fields = [
        "run_id",
        "tag",
        "run_dir",
        "passed",
        "fail_reasons",
        "score",
        "trades",
        "net_pnl",
        "profit_factor",
        "winrate",
        "max_drawdown",
        "negative_months",
        "positive_months",
        "max_negative_streak",
        "worst_month_pnl",
        "overrides_json",
    ]
    results_path = out_dir / "results.csv"
    ranked_path = out_dir / "ranked_results.csv"
    progress_path = out_dir / "progress.json"
    with results_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

    results: List[CandidateResult] = []
    total_candidates = _grid_size(spec.get("grid", {}))
    for idx, overrides in enumerate(_iter_grid(spec.get("grid", {})), start=1):
        if args.limit and idx > args.limit:
            break
        tag = f"{_slug(spec['name'])}_r{idx:03d}"
        try:
            result = _run_backtest(spec, overrides, idx)
        except Exception as exc:
            result = CandidateResult(
                run_id=idx,
                tag=tag,
                run_dir="",
                passed=False,
                fail_reasons=f"runner:{type(exc).__name__}:{exc}",
                score=-1000000.0,
                trades=0,
                net_pnl=0.0,
                profit_factor=0.0,
                winrate=0.0,
                max_drawdown=0.0,
                negative_months=0,
                positive_months=0,
                max_negative_streak=0,
                worst_month_pnl=0.0,
                overrides_json=json.dumps(overrides, ensure_ascii=True, sort_keys=True),
            )
            print(f"[{idx}/{total_candidates}] {tag} CRASH {result.fail_reasons}", flush=True)
        else:
            status = "PASS" if result.passed else "FAIL"
            print(
                f"[{idx}/{total_candidates}] {result.tag} {status} "
                f"net={result.net_pnl:.2f} pf={result.profit_factor:.3f} "
                f"wr={result.winrate:.3f} dd={result.max_drawdown:.3f}",
                flush=True,
            )
        results.append(result)
        _append_result_row(results_path, fields, result)
        _write_progress(progress_path, spec_path=spec_path, current=idx, total=total_candidates, result=result)

    ranked = _write_ranked(ranked_path, fields, results)

    print(f"spec={spec_path}")
    print(f"results_csv={results_path}")
    print(f"ranked_csv={ranked_path}")
    if ranked:
        top = ranked[0]
        print(
            "best="
            f"tag={top.tag} passed={top.passed} score={top.score:.4f} "
            f"net={top.net_pnl:.2f} pf={top.profit_factor:.3f} wr={top.winrate:.3f} "
            f"dd={top.max_drawdown:.4f} overrides={top.overrides_json}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
