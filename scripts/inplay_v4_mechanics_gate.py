#!/usr/bin/env python3
"""InPlay V4 mechanics anti-overfit gate.

Purpose:
  Test the *rewired* InPlay V4 chain, not the old close-entry mechanics:

    retest_quality -> level_entry(limit at level) ->
    portfolio pending limit fill/expiry -> costs -> rolling OOS -> oos_selector

This is research-only. It never writes live config and never places orders.
It calls backtest/run_portfolio.py with BACKTEST_CACHE_ONLY=1 by default.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.oos_selector import evaluate_candidate  # noqa: E402


BASE_ENV: Dict[str, str] = {
    "BACKTEST_CACHE_ONLY": "1",
    "IRV4_ALLOW_LONG": "0",
    "IRV4_ALLOW_SHORT": "1",
    "IRV4_USE_RETEST_QUALITY": "1",
    "IRV4_USE_LEVEL_ENTRY": "1",
    "IRV4_USE_RANGE_FILTER": "0",
    "IRV4_USE_ELDER_FILTER": "0",
    "IRV4_USE_BREAKOUT_CONFIRM": "0",
    "IRV4_ENABLE_SETUP_B": "1",
    "IRV4_ADAPTIVE": "0",
    "IRV4_MIN_STOP_PCT": "0.0005",
    "IRV4_MAX_STOP_PCT": "0.20",
}


GRID: Dict[str, List[str]] = {
    "IRV4_TP_RR": ["2.0", "2.5", "3.0"],
    "IRV4_RETEST_MIN_QUALITY": ["0.35", "0.45", "0.55"],
    "IRV4_LEVEL_ENTRY_VALIDITY_BARS": ["2", "4"],
    "IRV4_LEVEL_ENTRY_MAX_CHASE_ATR": ["0.4", "0.6"],
}


def _date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def _fmt(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def _f(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _i(row: Dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def param_grid(max_combos: int = 0) -> Iterable[Dict[str, str]]:
    keys = list(GRID)
    for n, vals in enumerate(itertools.product(*(GRID[k] for k in keys)), start=1):
        if max_combos and n > max_combos:
            break
        yield dict(zip(keys, vals))


def run_portfolio(
    *,
    py: str,
    tag: str,
    symbols: str,
    days: int,
    end: str,
    env_extra: Dict[str, str],
    fee_bps: float,
    slippage_bps: float,
    max_positions: int,
) -> Dict[str, str]:
    env = os.environ.copy()
    env.update(BASE_ENV)
    env.update(env_extra)
    env["PYTHONPATH"] = str(ROOT)

    cmd = [
        py,
        "backtest/run_portfolio.py",
        "--symbols",
        symbols,
        "--strategies",
        "inplay_retest_v4",
        "--days",
        str(days),
        "--end",
        end,
        "--tag",
        tag,
        "--starting_equity",
        "100",
        "--risk_pct",
        "0.005",
        "--leverage",
        "1",
        "--max_positions",
        str(max_positions),
        "--fee_bps",
        str(fee_bps),
        "--slippage_bps",
        str(slippage_bps),
        "--entry-on-next-open",
    ]
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    matches = sorted(ROOT.glob(f"backtest_runs/portfolio_*_{tag}/summary.csv"))
    if not matches:
        raise RuntimeError(f"summary not found for tag={tag}")
    with matches[-1].open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty summary for tag={tag}")
    out = dict(rows[0])
    out["summary_path"] = str(matches[-1])
    return out


def train_score(row: Dict[str, str]) -> float:
    trades = _i(row, "trades")
    net = _f(row, "net_pnl")
    pf = _f(row, "profit_factor")
    dd = _f(row, "max_drawdown")
    if trades < 4 or net <= 0 or pf < 1.05:
        return -1e9
    return net * 3.0 + pf * 2.0 + min(trades, 40) * 0.04 - dd * 1.25


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="ADAUSDT,DOGEUSDT,SUIUSDT")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--train-days", type=int, default=120)
    ap.add_argument("--test-days", type=int, default=60)
    ap.add_argument("--max-combos", type=int, default=0, help="0 = full grid")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--max-positions", type=int, default=2)
    ap.add_argument("--min-oos-trades", type=int, default=40)
    ap.add_argument("--min-oos-trades-per-fold", type=int, default=8)
    ap.add_argument("--py", default=".venv/bin/python")
    ap.add_argument("--tag-prefix", default="irv4_mechanics_gate")
    ap.add_argument("--no-fail-exit", action="store_true")
    args = ap.parse_args()

    py = args.py
    if not (ROOT / py).exists() and py.startswith(".venv/"):
        py = sys.executable

    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "reports" / "research" / f"{args.tag_prefix}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = out_dir / "runs.csv"
    md_path = out_dir / "summary.md"

    end_date = _date(args.end)
    folds: List[Tuple[dt.date, dt.date]] = []
    for k in reversed(range(args.folds)):
        test_end = end_date - dt.timedelta(days=k * args.test_days)
        train_end = test_end - dt.timedelta(days=args.test_days)
        folds.append((train_end, test_end))

    all_rows: List[Dict[str, str]] = []
    oos_rows: List[Dict[str, str]] = []
    selected_rows: List[Dict[str, str]] = []

    for fold_i, (train_end, test_end) in enumerate(folds, start=1):
        best_row: Dict[str, str] | None = None
        best_params: Dict[str, str] | None = None
        best_score = -1e18

        for combo_i, params in enumerate(param_grid(args.max_combos), start=1):
            tag = f"{args.tag_prefix}_f{fold_i:02d}_train_c{combo_i:03d}_{ts}"
            row = run_portfolio(
                py=py,
                tag=tag,
                symbols=args.symbols,
                days=args.train_days,
                end=_fmt(train_end),
                env_extra=params,
                fee_bps=args.fee_bps,
                slippage_bps=args.slippage_bps,
                max_positions=args.max_positions,
            )
            row.update(params)
            row.update({"fold": str(fold_i), "phase": "train", "combo": str(combo_i), "tag": tag})
            row["score"] = f"{train_score(row):.6f}"
            all_rows.append(row)
            score = train_score(row)
            if score > best_score:
                best_score = score
                best_row = row
                best_params = params

        if best_row is None or best_params is None:
            selected_rows.append({
                "fold": str(fold_i),
                "phase": "selected",
                "tag": "",
                "skip_reason": "no_train_candidate",
            })
            continue

        selected = dict(best_row)
        selected["phase"] = "selected"
        selected_rows.append(selected)

        tag = f"{args.tag_prefix}_f{fold_i:02d}_oos_{ts}"
        oos = run_portfolio(
            py=py,
            tag=tag,
            symbols=args.symbols,
            days=args.test_days,
            end=_fmt(test_end),
            env_extra=best_params,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            max_positions=args.max_positions,
        )
        oos.update(best_params)
        oos.update({"fold": str(fold_i), "phase": "oos", "tag": tag})
        all_rows.append(oos)
        oos_rows.append(oos)

    fieldnames = sorted({k for r in all_rows + selected_rows for k in r})
    with raw_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows + selected_rows:
            w.writerow(r)

    candidate = {
        "id": f"inplay_v4_mechanics:{args.symbols}",
        "params": {"policy": "train_selected_per_fold", "grid": GRID},
        "folds": [
            {
                "net_r": _f(r, "net_pnl"),
                "pf": _f(r, "profit_factor"),
                "trades": _i(r, "trades"),
            }
            for r in oos_rows
        ],
    }
    graded = evaluate_candidate(
        candidate,
        min_folds=min(3, args.folds),
        min_trades_total=args.min_oos_trades,
        min_trades_per_fold=args.min_oos_trades_per_fold,
        max_peak_ratio=3.0,
        min_robustness=0.0,
    )

    oos_trades = sum(_i(r, "trades") for r in oos_rows)
    oos_net = sum(_f(r, "net_pnl") for r in oos_rows)
    verdict = "PASS" if graded.passes else "FAIL"

    lines = [
        f"# InPlay V4 mechanics gate — {verdict}",
        "",
        f"- symbols: `{args.symbols}`",
        f"- folds: `{len(oos_rows)}` rolling train/test",
        f"- train_days: `{args.train_days}`",
        f"- test_days: `{args.test_days}`",
        f"- grid_combos_per_fold: `{sum(1 for _ in param_grid(args.max_combos))}`",
        f"- OOS total trades: `{oos_trades}`",
        f"- OOS total net: `{oos_net:.2f}R`",
        f"- oos_selector: `passes={graded.passes}`, reason `{graded.reason}`, robustness `{graded.robustness:.3f}`",
        f"- raw runs: `{raw_csv}`",
        "",
        "## Selected params by fold",
        "",
    ]
    for r in selected_rows:
        if r.get("skip_reason"):
            lines.append(f"- fold {r.get('fold')}: skipped `{r.get('skip_reason')}`")
            continue
        params = ", ".join(f"{k}={r.get(k)}" for k in GRID)
        lines.append(f"- fold {r.get('fold')}: score `{r.get('score')}` — {params}")
    lines.extend(["", "## OOS rows", ""])
    for r in oos_rows:
        lines.append(
            f"- fold {r.get('fold')}: trades `{r.get('trades')}`, net `{_f(r, 'net_pnl'):.2f}`, "
            f"PF `{_f(r, 'profit_factor'):.3f}`, DD `{_f(r, 'max_drawdown'):.4f}`, tag `{r.get('tag')}`"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(md_path)
    return 0 if (graded.passes or args.no_fail_exit) else 1


if __name__ == "__main__":
    raise SystemExit(main())
