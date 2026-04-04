#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_THIS_DIR = Path(__file__).resolve().parent
ROOT = _THIS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_exact_kline_cache import check_exact_cache

DEFAULT_OVERLAY = ROOT / "configs" / "full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env"
DEFAULT_EXPECTED_SUMMARY = (
    ROOT
    / "backtest_archive"
    / "portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual"
    / "summary.csv"
)
CONTROL_PLANE_DIR = ROOT / "runtime" / "control_plane"
LATEST_REPORT_PATH = CONTROL_PLANE_DIR / "baseline_regression_latest.json"
HISTORY_PATH = CONTROL_PLANE_DIR / "baseline_regression_history.jsonl"


def _parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _load_summary_row(path: Path) -> Dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            return {str(k): str(v) for k, v in row.items()}
    raise ValueError(f"summary.csv has no rows: {path}")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_history(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _f(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except Exception:
        return float(default)


def _i(row: Dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default) or default))
    except Exception:
        return int(default)


def _csv_to_arg(raw: str) -> str:
    return str(raw or "").replace(";", ",")


def _preferred_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _parse_end_utc(s: str) -> int:
    dt = datetime.strptime(str(s).strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _find_run_dir(tag: str) -> Path | None:
    runs_dir = ROOT / "backtest_runs"
    matches = sorted(runs_dir.glob(f"portfolio_*_{tag}"), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a trusted baseline regression against the validated v5 portfolio snapshot.")
    ap.add_argument("--overlay", default=str(DEFAULT_OVERLAY), help="Exact env overlay to source before running the regression.")
    ap.add_argument("--expected-summary", default=str(DEFAULT_EXPECTED_SUMMARY), help="Trusted summary.csv to compare against.")
    ap.add_argument("--days", type=int, default=0, help="Override days. Default: take from expected summary.")
    ap.add_argument("--end", default="", help="Override end date (YYYY-MM-DD). Default: take from expected summary.")
    ap.add_argument("--symbols", default="", help="Override symbols CSV. Default: take from expected summary.")
    ap.add_argument("--strategies", default="", help="Override strategies CSV. Default: take from expected summary.")
    ap.add_argument("--starting-equity", type=float, default=0.0, help="Override starting equity. Default: take from expected summary.")
    ap.add_argument("--base-interval-min", type=int, default=5, help="Base candle interval used by run_portfolio.")
    ap.add_argument("--cache-dir", default=str(ROOT / ".cache" / "klines"))
    ap.add_argument(
        "--cache-check-mode",
        choices=("off", "report", "require"),
        default="require",
        help="How strictly to enforce exact kline cache coverage for the regression window.",
    )
    ap.add_argument("--risk-pct", type=float, default=0.01)
    ap.add_argument("--cap-notional", type=float, default=30.0)
    ap.add_argument("--leverage", type=float, default=1.0)
    ap.add_argument("--max-positions", type=int, default=5)
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--net-tol", type=float, default=5.0, help="Allowed absolute drift in net return percentage points.")
    ap.add_argument("--pf-tol", type=float, default=0.20, help="Allowed absolute drift in profit factor.")
    ap.add_argument("--dd-tol", type=float, default=1.50, help="Allowed drawdown increase in percentage points.")
    ap.add_argument("--trades-tol", type=int, default=25, help="Allowed absolute trade-count drift.")
    ap.add_argument("--tag", default="validated_baseline_regression", help="Base tag for the generated run.")
    ap.add_argument("--history-path", default=str(HISTORY_PATH))
    ap.add_argument("--latest-path", default=str(LATEST_REPORT_PATH))
    ap.add_argument("--dry-run", action="store_true", help="Print resolved command and expected metrics only.")
    args = ap.parse_args()

    overlay_path = Path(args.overlay).expanduser().resolve()
    expected_path = Path(args.expected_summary).expanduser().resolve()
    latest_path = Path(args.latest_path).expanduser().resolve()
    history_path = Path(args.history_path).expanduser().resolve()
    if not overlay_path.exists():
        raise SystemExit(f"overlay not found: {overlay_path}")
    if not expected_path.exists():
        raise SystemExit(f"expected summary not found: {expected_path}")

    expected = _load_summary_row(expected_path)
    symbols = args.symbols or _csv_to_arg(expected.get("symbols", ""))
    strategies = args.strategies or _csv_to_arg(expected.get("strategies", ""))
    days = int(args.days or _i(expected, "days", 360))
    end_date = args.end or str(expected.get("end_date_utc", "")).strip()
    starting_equity = float(args.starting_equity or _f(expected, "starting_equity", 100.0))
    end_ts = _parse_end_utc(end_date)
    start_ts = end_ts - int(days) * 86400
    start_ms = int(start_ts) * 1000
    end_ms = int(end_ts) * 1000
    cache_interval = "1" if int(args.base_interval_min) == 1 else "5"
    symbol_list = [sym.strip().upper() for sym in symbols.split(",") if sym.strip()]
    python_executable = _preferred_python()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_tag = f"{args.tag}_{timestamp}"
    cache_report: Dict[str, Any] = {
        "enabled": args.cache_check_mode != "off",
        "mode": args.cache_check_mode,
        "interval": cache_interval,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "all_exact_present": None,
        "symbols_missing": None,
        "cache_dir": str(Path(args.cache_dir).expanduser().resolve()),
    }
    if args.cache_check_mode != "off":
        cache_report = check_exact_cache(
            symbols=symbol_list,
            interval=cache_interval,
            start_ms=start_ms,
            end_ms=end_ms,
            cache_dir=Path(args.cache_dir),
        )
        cache_report["enabled"] = True
        cache_report["mode"] = args.cache_check_mode

    cmd: List[str] = [
        python_executable,
        "backtest/run_portfolio.py",
        "--symbols",
        symbols,
        "--strategies",
        strategies,
        "--days",
        str(days),
        "--end",
        end_date,
        "--starting_equity",
        f"{starting_equity}",
        "--risk_pct",
        f"{args.risk_pct}",
        "--cap_notional",
        f"{args.cap_notional}",
        "--leverage",
        f"{args.leverage}",
        "--max_positions",
        str(args.max_positions),
        "--fee_bps",
        f"{args.fee_bps}",
        "--slippage_bps",
        f"{args.slippage_bps}",
        "--tag",
        run_tag,
    ]

    base_report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "overlay_path": str(overlay_path),
        "expected_summary_path": str(expected_path),
        "class": "validated_baseline",
        "window": {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "end_date_utc": end_date,
            "days": days,
            "base_interval_min": int(args.base_interval_min),
        },
        "expected": {
            "tag": expected.get("tag"),
            "days": days,
            "end_date_utc": end_date,
            "symbols": symbols,
            "strategies": strategies,
            "starting_equity": starting_equity,
            "net_pnl": _f(expected, "net_pnl"),
            "profit_factor": _f(expected, "profit_factor"),
            "max_drawdown": _f(expected, "max_drawdown"),
            "trades": _i(expected, "trades"),
            "ending_equity": _f(expected, "ending_equity"),
        },
        "tolerances": {
            "net_pnl_abs": args.net_tol,
            "profit_factor_abs": args.pf_tol,
            "max_drawdown_up": args.dd_tol,
            "trades_abs": args.trades_tol,
        },
        "cache_report": cache_report,
        "python_executable": python_executable,
        "command": shlex.join(cmd),
        "run_tag": run_tag,
    }

    if args.dry_run:
        print(json.dumps(base_report, indent=2))
        return 0

    if args.cache_check_mode == "require" and not bool(cache_report.get("all_exact_present")):
        report = {
            **base_report,
            "subprocess_returncode": None,
            "run_dir": "",
            "actual_summary_path": "",
            "actual": {},
            "diffs": {},
            "verdicts": {
                "exact_cache": False,
                "net_pnl": False,
                "profit_factor": False,
                "max_drawdown": False,
                "trades": False,
            },
            "pass": False,
            "stdout_tail": "",
            "stderr_tail": "Exact cache slices missing for trusted regression window; refusing to run in require mode.",
        }
        _write_json(latest_path, report)
        _append_history(history_path, report)
        print(json.dumps(report, indent=2))
        return 3

    env = os.environ.copy()
    env.update(_parse_env_file(overlay_path))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if bool(cache_report.get("all_exact_present")):
        env["BACKTEST_CACHE_ONLY"] = "1"
        env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "0"
    elif args.cache_check_mode != "off":
        env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "0"

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    run_dir = _find_run_dir(run_tag)
    actual_summary_path = run_dir / "summary.csv" if run_dir else None
    actual: Dict[str, Any] = {}
    if actual_summary_path and actual_summary_path.exists():
        row = _load_summary_row(actual_summary_path)
        actual = {
            "tag": row.get("tag"),
            "days": _i(row, "days"),
            "end_date_utc": row.get("end_date_utc"),
            "symbols": _csv_to_arg(row.get("symbols", "")),
            "strategies": _csv_to_arg(row.get("strategies", "")),
            "starting_equity": _f(row, "starting_equity"),
            "net_pnl": _f(row, "net_pnl"),
            "profit_factor": _f(row, "profit_factor"),
            "max_drawdown": _f(row, "max_drawdown"),
            "trades": _i(row, "trades"),
            "ending_equity": _f(row, "ending_equity"),
        }

    verdicts = {
        "exact_cache": bool(cache_report.get("all_exact_present")) if args.cache_check_mode != "off" else True,
        "net_pnl": False,
        "profit_factor": False,
        "max_drawdown": False,
        "trades": False,
    }
    diffs = {}
    if actual:
        net_diff = float(actual["net_pnl"]) - float(base_report["expected"]["net_pnl"])
        pf_diff = float(actual["profit_factor"]) - float(base_report["expected"]["profit_factor"])
        dd_diff = float(actual["max_drawdown"]) - float(base_report["expected"]["max_drawdown"])
        trades_diff = int(actual["trades"]) - int(base_report["expected"]["trades"])
        diffs = {
            "net_pnl": net_diff,
            "profit_factor": pf_diff,
            "max_drawdown": dd_diff,
            "trades": trades_diff,
        }
        verdicts = {
            "exact_cache": bool(cache_report.get("all_exact_present")) if args.cache_check_mode != "off" else True,
            "net_pnl": abs(net_diff) <= args.net_tol,
            "profit_factor": abs(pf_diff) <= args.pf_tol,
            "max_drawdown": dd_diff <= args.dd_tol,
            "trades": abs(trades_diff) <= args.trades_tol,
        }

    passed = bool(actual) and proc.returncode == 0 and all(verdicts.values())
    report: Dict[str, Any] = {
        **base_report,
        "subprocess_returncode": proc.returncode,
        "run_dir": str(run_dir) if run_dir else "",
        "actual_summary_path": str(actual_summary_path) if actual_summary_path else "",
        "actual": actual,
        "diffs": diffs,
        "verdicts": verdicts,
        "pass": passed,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }

    _write_json(latest_path, report)
    _append_history(history_path, report)

    print(json.dumps(report, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
