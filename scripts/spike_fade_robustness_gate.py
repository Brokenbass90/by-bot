#!/usr/bin/env python3
"""SpikeFadeV3 anti-overfit gate.

Purpose:
  The LINK short-only SpikeFade slice looks promising, but the previous
  90/240/360d checks were nested windows ending at the same date. This script
  turns that into a promotion-grade *research* gate:

  1. rolling train/test folds;
  2. parameter selection only on the train window;
  3. OOS test on the next independent window;
  4. fee/slippage stress on the selected params;
  5. cross-symbol sanity using the same params.

It never writes live config and never places orders. It only calls
backtest/run_portfolio.py with BACKTEST_CACHE_ONLY=1 by default.
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


BASE_ENV: Dict[str, str] = {
    "BACKTEST_CACHE_ONLY": "1",
    "SFV3_STRUCTURE_TF": "60",
    "SFV3_ENTRY_TF": "15",
    "SFV3_LEVEL_LOOKBACK": "240",
    "SFV3_ENTRY_LOOKBACK": "96",
    "SFV3_MIN_TOUCHES": "2",
    "SFV3_ALLOW_LONG": "0",
    "SFV3_ALLOW_SHORT": "1",
    "SFV3_MIN_STOP_PCT": "0.0015",
    "SFV3_MAX_STOP_PCT": "0.080",
    "SFV3_BE_TRIGGER_RR": "1.0",
    "SFV3_COOLDOWN_BARS": "3",
    "SFV3_TRAIL_ATR_MULT": "0.0",
    "SFV3_TRAIL_ACTIVATE_RR": "0.0",
}


GRID: Dict[str, List[str]] = {
    "SFV3_LEVEL_TOL_ATR": ["0.35", "0.50"],
    "SFV3_SPIKE_MIN_PCT": ["4.0", "5.0"],
    "SFV3_TAG_LEVEL_ATR": ["0.6", "0.8"],
    "SFV3_REJECT_FRAC": ["0.50", "0.55"],
    "SFV3_STOP_BUFFER_ATR": ["0.25", "0.40"],
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
    max_positions: int = 1,
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
        "spike_fade_v3",
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
    if trades < 8 or net <= 0 or pf < 1.05:
        return -1e9
    return net * 2.0 + pf * 3.0 + min(trades, 40) * 0.05 - dd * 1.5


def verdict(oos_rows: List[Dict[str, str]], stress_rows: List[Dict[str, str]], cross_rows: List[Dict[str, str]]) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    oos_trades = sum(_i(r, "trades") for r in oos_rows)
    oos_net = sum(_f(r, "net_pnl") for r in oos_rows)
    oos_gross_win = 0.0
    oos_gross_loss = 0.0
    for r in oos_rows:
        trades = _i(r, "trades")
        wr = _f(r, "winrate")
        avg_win = _f(r, "avg_win")
        avg_loss = abs(_f(r, "avg_loss"))
        oos_gross_win += trades * wr * avg_win
        oos_gross_loss += trades * max(0.0, 1.0 - wr) * avg_loss
    oos_pf = (oos_gross_win / oos_gross_loss) if oos_gross_loss > 0 else (999.0 if oos_gross_win > 0 else 0.0)
    worst_fold = min((_f(r, "net_pnl") for r in oos_rows), default=0.0)
    max_dd = max((_f(r, "max_drawdown") for r in oos_rows), default=0.0)

    if len(oos_rows) < 3:
        reasons.append("need_at_least_3_oos_folds")
    if oos_trades < 18:
        reasons.append(f"too_few_oos_trades:{oos_trades}")
    if oos_net <= 1.0:
        reasons.append(f"oos_net_too_low:{oos_net:.2f}")
    if oos_pf < 1.20:
        reasons.append(f"oos_pf_too_low:{oos_pf:.3f}")
    if worst_fold < -1.0:
        reasons.append(f"bad_oos_fold:{worst_fold:.2f}")
    if max_dd > 4.0:
        reasons.append(f"oos_dd_too_high:{max_dd:.2f}")

    stress_bad = [r for r in stress_rows if _f(r, "net_pnl") <= 0 or _f(r, "profit_factor") < 1.05]
    if stress_bad:
        reasons.append(f"fee_stress_failed:{len(stress_bad)}")

    if cross_rows:
        cross_positive = sum(1 for r in cross_rows if _f(r, "net_pnl") > 0 and _f(r, "profit_factor") >= 1.0)
        if cross_positive == 0:
            reasons.append("cross_symbol_all_failed")

    return ("PASS" if not reasons else "FAIL", reasons)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="LINKUSDT")
    ap.add_argument("--cross-symbols", default="SOLUSDT,SUIUSDT,DOGEUSDT,ADAUSDT,NEARUSDT")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--train-days", type=int, default=240)
    ap.add_argument("--test-days", type=int, default=90)
    ap.add_argument("--max-combos", type=int, default=0, help="0 = full grid")
    ap.add_argument("--stress", default="10:5,12:8", help="fee:slippage pairs")
    ap.add_argument("--skip-cross", action="store_true")
    ap.add_argument("--py", default=".venv/bin/python")
    ap.add_argument("--tag-prefix", default="sfv3_robust_gate")
    ap.add_argument("--no-fail-exit", action="store_true", help="always exit 0 after writing the report")
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
    folds = []
    for k in reversed(range(args.folds)):
        test_end = end_date - dt.timedelta(days=k * args.test_days)
        train_end = test_end - dt.timedelta(days=args.test_days)
        folds.append((train_end, test_end))

    all_rows: List[Dict[str, str]] = []
    oos_rows: List[Dict[str, str]] = []
    stress_rows: List[Dict[str, str]] = []
    cross_rows: List[Dict[str, str]] = []
    selected_params: List[Tuple[int, Dict[str, str], float]] = []

    for fold_idx, (train_end, test_end) in enumerate(folds, start=1):
        best_params: Dict[str, str] | None = None
        best_score = float("-inf")
        best_train: Dict[str, str] | None = None
        for combo_idx, params in enumerate(param_grid(args.max_combos), start=1):
            tag = f"{args.tag_prefix}_f{fold_idx:02d}_train_c{combo_idx:03d}_{ts}"
            row = run_portfolio(
                py=py,
                tag=tag,
                symbols=args.symbol,
                days=args.train_days,
                end=_fmt(train_end),
                env_extra={**params, "SFV3_ALLOW": args.symbol},
                fee_bps=6,
                slippage_bps=2,
            )
            row.update({"phase": "train", "fold": str(fold_idx), "combo": str(combo_idx), **params})
            all_rows.append(row)
            sc = train_score(row)
            if sc > best_score:
                best_score = sc
                best_params = params
                best_train = row
        if best_params is None:
            raise RuntimeError(f"no train params selected for fold {fold_idx}")
        selected_params.append((fold_idx, dict(best_params), best_score))

        tag = f"{args.tag_prefix}_f{fold_idx:02d}_oos_{ts}"
        oos = run_portfolio(
            py=py,
            tag=tag,
            symbols=args.symbol,
            days=args.test_days,
            end=_fmt(test_end),
            env_extra={**best_params, "SFV3_ALLOW": args.symbol},
            fee_bps=6,
            slippage_bps=2,
        )
        oos.update({"phase": "oos", "fold": str(fold_idx), "combo": "selected", **best_params})
        if best_train:
            oos["selected_train_tag"] = best_train.get("tag", "")
        all_rows.append(oos)
        oos_rows.append(oos)

        for pair in [x.strip() for x in args.stress.split(",") if x.strip()]:
            fee_s, slip_s = pair.split(":", 1)
            tag = f"{args.tag_prefix}_f{fold_idx:02d}_stress_{fee_s}_{slip_s}_{ts}"
            st = run_portfolio(
                py=py,
                tag=tag,
                symbols=args.symbol,
                days=args.test_days,
                end=_fmt(test_end),
                env_extra={**best_params, "SFV3_ALLOW": args.symbol},
                fee_bps=float(fee_s),
                slippage_bps=float(slip_s),
            )
            st.update({"phase": "stress", "fold": str(fold_idx), "combo": "selected", "stress": pair, **best_params})
            all_rows.append(st)
            stress_rows.append(st)

        if not args.skip_cross:
            for sym in [s.strip().upper() for s in args.cross_symbols.split(",") if s.strip()]:
                tag = f"{args.tag_prefix}_f{fold_idx:02d}_cross_{sym}_{ts}"
                cr = run_portfolio(
                    py=py,
                    tag=tag,
                    symbols=sym,
                    days=args.test_days,
                    end=_fmt(test_end),
                    env_extra={**best_params, "SFV3_ALLOW": sym},
                    fee_bps=6,
                    slippage_bps=2,
                )
                cr.update({"phase": "cross", "fold": str(fold_idx), "combo": "selected", "cross_symbol": sym, **best_params})
                all_rows.append(cr)
                cross_rows.append(cr)

    fieldnames = sorted({k for r in all_rows for k in r})
    with raw_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    status, reasons = verdict(oos_rows, stress_rows, cross_rows)
    oos_net = sum(_f(r, "net_pnl") for r in oos_rows)
    oos_trades = sum(_i(r, "trades") for r in oos_rows)
    lines = [
        f"# SpikeFadeV3 robustness gate — {status}",
        "",
        f"- symbol: `{args.symbol}`",
        f"- folds: `{args.folds}` rolling train/test",
        f"- train_days: `{args.train_days}`",
        f"- test_days: `{args.test_days}`",
        f"- grid_combos_per_fold: `{args.max_combos or len(list(param_grid()))}`",
        f"- OOS total trades: `{oos_trades}`",
        f"- OOS total net: `{oos_net:.2f}R`",
        f"- reasons: `{', '.join(reasons) if reasons else 'none'}`",
        f"- raw runs: `{raw_csv}`",
        "",
        "## Selected params by fold",
        "",
    ]
    for fold_idx, params, sc in selected_params:
        p = ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
        lines.append(f"- fold {fold_idx}: score `{sc:.3f}` — {p}")
    lines += ["", "## OOS rows", ""]
    for r in oos_rows:
        lines.append(
            f"- fold {r.get('fold')}: trades `{r.get('trades')}`, net `{r.get('net_pnl')}`, "
            f"PF `{r.get('profit_factor')}`, DD `{r.get('max_drawdown')}`, tag `{r.get('tag')}`"
        )
    lines += ["", "## Fee stress rows", ""]
    for r in stress_rows:
        lines.append(
            f"- fold {r.get('fold')} stress `{r.get('stress')}`: trades `{r.get('trades')}`, "
            f"net `{r.get('net_pnl')}`, PF `{r.get('profit_factor')}`, DD `{r.get('max_drawdown')}`"
        )
    if cross_rows:
        lines += ["", "## Cross-symbol sanity rows", ""]
        for r in cross_rows:
            lines.append(
                f"- fold {r.get('fold')} `{r.get('cross_symbol')}`: trades `{r.get('trades')}`, "
                f"net `{r.get('net_pnl')}`, PF `{r.get('profit_factor')}`, DD `{r.get('max_drawdown')}`"
            )
    md_path.write_text("\n".join(lines) + "\n")
    print(f"status={status}")
    print(f"summary={md_path}")
    print(f"runs={raw_csv}")
    if args.no_fail_exit:
        return 0
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
