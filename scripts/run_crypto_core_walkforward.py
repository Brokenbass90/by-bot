#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List


REPO_DIR = Path(__file__).resolve().parents[1]
RUN_PORTFOLIO = REPO_DIR / "backtest" / "run_portfolio.py"
VENV_PYTHON = REPO_DIR / ".venv" / "bin" / "python"
BACKTEST_RUNS = REPO_DIR / "backtest_runs"


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def _fmt_date(value: dt.date) -> str:
    return value.strftime("%Y-%m-%d")


def _load_summary(run_dir: Path) -> dict:
    summary_path = run_dir / "summary.csv"
    with summary_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"Empty summary.csv in {run_dir}")
    row = rows[0]
    return {
        "tag": row.get("tag", ""),
        "days": int(float(row.get("days", 0) or 0)),
        "end_date_utc": row.get("end_date_utc", ""),
        "trades": int(float(row.get("trades", 0) or 0)),
        "net_pnl": float(row.get("net_pnl", 0.0) or 0.0),
        "profit_factor": float(row.get("profit_factor", 0.0) or 0.0),
        "winrate": float(row.get("winrate", 0.0) or 0.0),
        "max_drawdown": float(row.get("max_drawdown", 0.0) or 0.0),
        "starting_equity": float(row.get("starting_equity", 0.0) or 0.0),
        "ending_equity": float(row.get("ending_equity", 0.0) or 0.0),
    }


def _default_output_dir(tag: str) -> Path:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    return BACKTEST_RUNS / f"walkforward_{ts}_{tag}"


def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _build_windows(*, end_date: dt.date, total_days: int, window_days: int, step_days: int) -> List[tuple[dt.date, dt.date]]:
    if total_days < window_days:
        raise ValueError("total_days must be >= window_days")
    start_anchor = end_date - dt.timedelta(days=total_days)
    windows: List[tuple[dt.date, dt.date]] = []
    cursor = start_anchor + dt.timedelta(days=window_days)
    while cursor <= end_date:
        window_end = cursor
        window_start = window_end - dt.timedelta(days=window_days)
        windows.append((window_start, window_end))
        cursor += dt.timedelta(days=step_days)
    return windows


def _run_window(
    *,
    symbols: str,
    strategies: str,
    window_days: int,
    window_end: dt.date,
    starting_equity: float,
    risk_pct: float,
    leverage: float,
    max_positions: int,
    fee_bps: float,
    slippage_bps: float,
    tag: str,
    extra_env: dict[str, str],
) -> Path:
    if not VENV_PYTHON.exists():
        raise FileNotFoundError(f"Missing virtualenv python: {VENV_PYTHON}")
    cmd = [
        str(VENV_PYTHON),
        str(RUN_PORTFOLIO),
        "--symbols",
        symbols,
        "--strategies",
        strategies,
        "--days",
        str(window_days),
        "--end",
        _fmt_date(window_end),
        "--tag",
        tag,
        "--starting_equity",
        str(starting_equity),
        "--risk_pct",
        str(risk_pct),
        "--leverage",
        str(leverage),
        "--max_positions",
        str(max_positions),
        "--fee_bps",
        str(fee_bps),
        "--slippage_bps",
        str(slippage_bps),
    ]
    env = dict(**extra_env)
    subprocess.run(cmd, cwd=str(REPO_DIR), env=env, check=True)
    run_dir = BACKTEST_RUNS / f"portfolio_{dt.datetime.utcnow().strftime('%Y%m%d')}"
    return run_dir


def _find_run_dir(tag: str) -> Path:
    matches = sorted(BACKTEST_RUNS.glob(f"portfolio_*_{tag}"))
    if not matches:
        raise FileNotFoundError(f"No run dir found for tag={tag}")
    return matches[-1]


def _write_outputs(out_dir: Path, rows: List[dict], *, args: argparse.Namespace) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "walkforward_windows.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "window_index",
                "window_start",
                "window_end",
                "run_dir",
                "trades",
                "net_pnl",
                "profit_factor",
                "winrate",
                "max_drawdown",
                "passed",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    total = len(rows)
    passed = sum(1 for row in rows if row["passed"])
    avg_pf = sum(float(row["profit_factor"]) for row in rows) / max(1, total)
    avg_net = sum(float(row["net_pnl"]) for row in rows) / max(1, total)
    avg_dd = sum(float(row["max_drawdown"]) for row in rows) / max(1, total)
    report_path = out_dir / "walkforward_report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"# Crypto Core Walk-Forward: {args.tag}\n\n")
        f.write(f"- Symbols: `{args.symbols}`\n")
        f.write(f"- Strategies: `{args.strategies}`\n")
        f.write(f"- End date: `{args.end}`\n")
        f.write(f"- Total horizon: `{args.total_days}` days\n")
        f.write(f"- Window: `{args.window_days}` days\n")
        f.write(f"- Step: `{args.step_days}` days\n")
        f.write(f"- Pass rule: PF >= `{args.min_pf}` and net >= `{args.min_net}` and DD <= `{args.max_dd}`\n\n")
        f.write(f"## Aggregate\n\n")
        f.write(f"- Windows: `{total}`\n")
        f.write(f"- Passed: `{passed}` / `{total}`\n")
        f.write(f"- Avg PF: `{avg_pf:.3f}`\n")
        f.write(f"- Avg net PnL: `{avg_net:.2f}`\n")
        f.write(f"- Avg DD: `{avg_dd:.2f}`\n\n")
        f.write("## Windows\n\n")
        for row in rows:
            f.write(
                f"- `{row['window_start']} -> {row['window_end']}` | "
                f"PF `{float(row['profit_factor']):.3f}` | "
                f"net `{float(row['net_pnl']):.2f}` | "
                f"DD `{float(row['max_drawdown']):.2f}` | "
                f"trades `{row['trades']}` | "
                f"pass `{row['passed']}`\n"
            )

    latest = {
        "tag": args.tag,
        "windows": total,
        "passed": passed,
        "avg_pf": round(avg_pf, 4),
        "avg_net_pnl": round(avg_net, 4),
        "avg_max_drawdown": round(avg_dd, 4),
        "csv": str(csv_path),
        "report": str(report_path),
    }
    (out_dir / "walkforward_latest.json").write_text(json.dumps(latest, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward runner for current crypto portfolio core.")
    ap.add_argument("--symbols", required=True, help="Comma-separated symbols")
    ap.add_argument("--strategies", required=True, help="Comma-separated strategies")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--total_days", type=int, default=180)
    ap.add_argument("--window_days", type=int, default=30)
    ap.add_argument("--step_days", type=int, default=15)
    ap.add_argument("--starting_equity", type=float, default=100.0)
    ap.add_argument("--risk_pct", type=float, default=0.01)
    ap.add_argument("--leverage", type=float, default=1.0)
    ap.add_argument("--max_positions", type=int, default=3)
    ap.add_argument("--fee_bps", type=float, default=6.0)
    ap.add_argument("--slippage_bps", type=float, default=2.0)
    ap.add_argument("--min_pf", type=float, default=1.30)
    ap.add_argument("--min_net", type=float, default=0.0)
    ap.add_argument("--max_dd", type=float, default=12.0)
    ap.add_argument("--tag", default="crypto_core_walkforward")
    ap.add_argument("--out_dir", default="", help="Optional explicit output dir")
    ap.add_argument("--env-file", action="append", default=[], help="Optional KEY=VALUE env overlay file(s)")
    args = ap.parse_args()

    end_date = _parse_date(args.end)
    windows = _build_windows(
        end_date=end_date,
        total_days=int(args.total_days),
        window_days=int(args.window_days),
        step_days=int(args.step_days),
    )
    out_dir = Path(args.out_dir) if args.out_dir else _default_output_dir(args.tag)

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for env_file in args.env_file:
        env_path = Path(env_file)
        if not env_path.is_absolute():
            env_path = (REPO_DIR / env_path).resolve()
        if not env_path.exists():
            raise FileNotFoundError(f"Missing env file: {env_path}")
        env.update(_load_env_file(env_path))

    results: List[dict] = []
    for idx, (window_start, window_end) in enumerate(windows, start=1):
        run_tag = f"{args.tag}_w{idx:02d}_{window_end.strftime('%Y%m%d')}"
        cmd = [
            str(VENV_PYTHON),
            str(RUN_PORTFOLIO),
            "--symbols",
            args.symbols,
            "--strategies",
            args.strategies,
            "--days",
            str(args.window_days),
            "--end",
            _fmt_date(window_end),
            "--tag",
            run_tag,
            "--starting_equity",
            str(args.starting_equity),
            "--risk_pct",
            str(args.risk_pct),
            "--leverage",
            str(args.leverage),
            "--max_positions",
            str(args.max_positions),
            "--fee_bps",
            str(args.fee_bps),
            "--slippage_bps",
            str(args.slippage_bps),
        ]
        subprocess.run(cmd, cwd=str(REPO_DIR), env=env, check=True)
        run_dir = _find_run_dir(run_tag)
        summary = _load_summary(run_dir)
        passed = (
            summary["profit_factor"] >= float(args.min_pf)
            and summary["net_pnl"] >= float(args.min_net)
            and summary["max_drawdown"] <= float(args.max_dd)
        )
        results.append(
            {
                "window_index": idx,
                "window_start": _fmt_date(window_start),
                "window_end": _fmt_date(window_end),
                "run_dir": str(run_dir),
                "trades": summary["trades"],
                "net_pnl": summary["net_pnl"],
                "profit_factor": summary["profit_factor"],
                "winrate": summary["winrate"],
                "max_drawdown": summary["max_drawdown"],
                "passed": passed,
            }
        )
        print(
            f"[{idx}/{len(windows)}] {run_tag} "
            f"pf={summary['profit_factor']:.3f} net={summary['net_pnl']:.2f} "
            f"dd={summary['max_drawdown']:.2f} trades={summary['trades']} pass={passed}"
        )

    _write_outputs(out_dir, results, args=args)
    print(f"walk-forward complete: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
