#!/usr/bin/env python3
"""Strict gate for the 2026-07-06 inplay breakout-retest candidate.

The overnight autoresearch found a promising base-screen row. This script is the
next promotion gate: fixed params, no optimization, cache-only, base/stress,
rolling time folds, individual-symbol checks, and leave-one-out checks.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SYMBOLS = ["DOGEUSDT", "ADAUSDT", "SUIUSDT", "1000PEPEUSDT", "TAOUSDT"]

INPLAY_R061_ENV: Dict[str, str] = {
    "BACKTEST_CACHE_ONLY": "1",
    "CACHE_ONLY": "1",
    "BREAKOUT_TF_BREAK": "240",
    "BREAKOUT_TF_ENTRY": "5",
    "BREAKOUT_LOOKBACK_H": "96",
    "BREAKOUT_SL_ATR": "0.40",
    "BREAKOUT_EXIT_MODE": "runner",
    "BREAKOUT_PARTIAL_RS": "1.5,3.0,5.0",
    "BREAKOUT_PARTIAL_FRACS": "0.50,0.30,0.20",
    "BREAKOUT_TRAIL_ATR_MULT": "2.2",
    "BREAKOUT_TIME_STOP_BARS": "288",
    "BREAKOUT_REGIME_MODE": "ema",
    "BREAKOUT_REGIME_TF": "240",
    "BREAKOUT_REGIME_EMA_FAST": "20",
    "BREAKOUT_REGIME_EMA_SLOW": "50",
    "BREAKOUT_SYMBOL_ALLOWLIST": "",
    "BREAKOUT_RECLAIM_ATR": "0.08",
    "BREAKOUT_RR": "3.0",
    "BREAKOUT_MAX_LATE_VS_REF_PCT": "0.35",
    "BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT": "0.05",
    "BREAKOUT_BUFFER_ATR": "0.12",
    "BREAKOUT_DIRECTION_MODE": "both",
    "BREAKOUT_IMPULSE_BODY_MIN_FRAC": "0.45",
    "BREAKOUT_IMPULSE_VOL_MULT": "1.8",
    "BREAKOUT_MAX_DIST_HTF_MULT": "1.2",
    "BREAKOUT_MAX_RETEST_BARS": "36",
    "BREAKOUT_RETEST_TOUCH_ATR": "0.2",
    "BREAKOUT_SL_HTF_MULT": "0.8",
}


@dataclass
class Metrics:
    case: str
    tag: str
    run_dir: str
    symbols: str
    days: int
    end: str
    fee_bps: float
    slippage_bps: float
    trades: int
    net_pnl: float
    profit_factor: float
    winrate: float
    max_drawdown: float
    gross_profit: float
    gross_loss: float


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_date(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _to_float(raw: object) -> float:
    s = str(raw or "").strip().lower()
    if s == "inf":
        return float("inf")
    if s in {"", "nan"}:
        return 0.0
    return float(s)


def _read_summary(run_dir: Path) -> Dict[str, str]:
    with (run_dir / "summary.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty summary: {run_dir / 'summary.csv'}")
    return dict(rows[0])


def _read_trade_pnls(run_dir: Path) -> List[float]:
    path = run_dir / "trades.csv"
    if not path.exists():
        return []
    out: List[float] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out.append(float(row.get("pnl", "0") or 0.0))
            except ValueError:
                continue
    return out


def _latest_run_dir(tag: str) -> Path:
    matches = sorted(ROOT.glob(f"backtest_runs/portfolio_*_{tag}"), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise RuntimeError(f"missing run dir for tag={tag}")
    return matches[-1]


def _metrics(case: str, tag: str, run_dir: Path, days: int, end: str, fee_bps: float, slippage_bps: float) -> Metrics:
    s = _read_summary(run_dir)
    pnls = _read_trade_pnls(run_dir)
    gross_profit = sum(x for x in pnls if x > 0)
    gross_loss = -sum(x for x in pnls if x < 0)
    pf = _to_float(s.get("profit_factor"))
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = float("inf")
    return Metrics(
        case=case,
        tag=tag,
        run_dir=str(run_dir),
        symbols=str(s.get("symbols", "")),
        days=int(days),
        end=end,
        fee_bps=float(fee_bps),
        slippage_bps=float(slippage_bps),
        trades=int(_to_float(s.get("trades"))),
        net_pnl=_to_float(s.get("net_pnl")),
        profit_factor=pf,
        winrate=_to_float(s.get("winrate")),
        max_drawdown=abs(_to_float(s.get("max_drawdown"))),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
    )


def _run_case(
    *,
    py: str,
    case: str,
    tag: str,
    symbols: Sequence[str],
    days: int,
    end: str,
    fee_bps: float,
    slippage_bps: float,
    max_positions: int,
    log_dir: Path,
) -> Metrics:
    env = os.environ.copy()
    env.update(INPLAY_R061_ENV)
    env["PYTHONPATH"] = str(ROOT)
    cmd = [
        py,
        "backtest/run_portfolio.py",
        "--cache",
        "data_cache",
        "--symbols",
        ",".join(symbols),
        "--strategies",
        "inplay_breakout",
        "--days",
        str(int(days)),
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
        str(int(max_positions)),
        "--fee_bps",
        f"{float(fee_bps):.4f}",
        "--slippage_bps",
        f"{float(slippage_bps):.4f}",
        "--entry-on-next-open",
    ]
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{tag}.log"
    with log_path.open("w", encoding="utf-8", errors="ignore") as f:
        f.write("cmd=" + " ".join(cmd) + "\n")
        f.write("env=" + json.dumps(INPLAY_R061_ENV, sort_keys=True) + "\n\n")
        subprocess.run(cmd, cwd=ROOT, env=env, check=True, stdout=f, stderr=subprocess.STDOUT)
    return _metrics(case, tag, _latest_run_dir(tag), days, end, fee_bps, slippage_bps)


def _write_csv(path: Path, rows: Iterable[Metrics]) -> None:
    data = [r.__dict__ for r in rows]
    fields = list(Metrics.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(data)


def _pf_text(value: float) -> str:
    return "inf" if math.isinf(value) else f"{value:.3f}"


def _gate(rows: List[Metrics]) -> Dict[str, object]:
    by_case = {r.case: r for r in rows}
    base = by_case.get("base_360")
    stress = by_case.get("stress_360")
    folds = [r for r in rows if r.case.startswith("fold_base_")]
    fold_pos = sum(1 for r in folds if r.net_pnl > 0)
    fold_trades = sum(r.trades for r in folds)
    individuals = [r for r in rows if r.case.startswith("symbol_base_")]
    positive_symbols = sum(1 for r in individuals if r.net_pnl > 0 and r.trades >= 8)
    gross_profit = sum(max(0.0, r.gross_profit) for r in individuals)
    max_symbol_gross = max([max(0.0, r.gross_profit) for r in individuals] or [0.0])
    concentration = (max_symbol_gross / gross_profit) if gross_profit > 0 else 1.0

    reasons: List[str] = []
    if base is None or base.trades < 100 or base.net_pnl <= 2.0 or base.profit_factor < 1.25 or base.max_drawdown > 3.0:
        reasons.append("base_360_weak")
    if stress is None or stress.trades < 90 or stress.net_pnl <= 0.0 or stress.profit_factor < 1.10:
        reasons.append("stress_360_weak")
    if fold_pos < 3 or fold_trades < 80:
        reasons.append(f"time_folds_weak_{fold_pos}/{len(folds)}_trades_{fold_trades}")
    if positive_symbols < 2:
        reasons.append(f"symbol_breadth_weak_{positive_symbols}")
    if concentration > 0.70:
        reasons.append(f"symbol_concentration_{concentration:.2f}")

    return {
        "passed": not reasons,
        "reasons": ";".join(reasons) if reasons else "strict_gate_pass",
        "base_trades": base.trades if base else 0,
        "base_net": round(base.net_pnl, 6) if base else 0.0,
        "base_pf": "inf" if base and math.isinf(base.profit_factor) else (round(base.profit_factor, 6) if base else 0.0),
        "stress_net": round(stress.net_pnl, 6) if stress else 0.0,
        "stress_pf": "inf" if stress and math.isinf(stress.profit_factor) else (round(stress.profit_factor, 6) if stress else 0.0),
        "folds_positive": fold_pos,
        "folds_total": len(folds),
        "fold_trades": fold_trades,
        "positive_symbols": positive_symbols,
        "symbol_concentration": round(concentration, 6),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-07-05")
    ap.add_argument("--py", default=".venv/bin/python3")
    ap.add_argument("--tag-prefix", default="inplay_br_strict_20260706")
    ap.add_argument("--base-fee-bps", type=float, default=6.0)
    ap.add_argument("--base-slippage-bps", type=float, default=2.0)
    ap.add_argument("--stress-fee-bps", type=float, default=10.0)
    ap.add_argument("--stress-slippage-bps", type=float, default=5.0)
    args = ap.parse_args()

    py = args.py
    if py.startswith(".venv/") and not (ROOT / py).exists():
        py = sys.executable

    stamp = _stamp()
    out_dir = ROOT / "reports" / "research" / f"{args.tag_prefix}_{stamp}"
    log_dir = out_dir / "subprocess_logs"
    out_dir.mkdir(parents=True, exist_ok=True)

    preflight_path = out_dir / "cache_preflight.csv"
    preflight_cmd = [
        py,
        "scripts/preflight_cache_coverage.py",
        "--asset-class",
        "crypto",
        "--cache-dir",
        "data_cache",
        "--symbols",
        ",".join(SYMBOLS),
        "--days",
        "360",
        "--end",
        args.end,
        "--interval-min",
        "5",
        "--min-coverage",
        "0.98",
        "--out",
        str(preflight_path),
    ]
    subprocess.run(preflight_cmd, cwd=ROOT, check=True)

    rows: List[Metrics] = []

    def run(case: str, symbols: Sequence[str], days: int, end: str, fee: float, slip: float) -> None:
        tag = f"{args.tag_prefix}_{case}_{stamp}"
        m = _run_case(
            py=py,
            case=case,
            tag=tag,
            symbols=symbols,
            days=days,
            end=end,
            fee_bps=fee,
            slippage_bps=slip,
            max_positions=min(3, max(1, len(symbols))),
            log_dir=log_dir,
        )
        rows.append(m)
        print(
            f"{case}: trades={m.trades} net={m.net_pnl:.2f} "
            f"pf={_pf_text(m.profit_factor)} dd={m.max_drawdown:.2f}",
            flush=True,
        )

    base_fee = float(args.base_fee_bps)
    base_slip = float(args.base_slippage_bps)
    stress_fee = float(args.stress_fee_bps)
    stress_slip = float(args.stress_slippage_bps)

    run("base_360", SYMBOLS, 360, args.end, base_fee, base_slip)
    run("stress_360", SYMBOLS, 360, args.end, stress_fee, stress_slip)

    end_dt = _parse_date(args.end)
    for idx in range(4):
        fold_end = end_dt - timedelta(days=(3 - idx) * 90)
        run(f"fold_base_{idx + 1}", SYMBOLS, 90, _fmt(fold_end), base_fee, base_slip)
        run(f"fold_stress_{idx + 1}", SYMBOLS, 90, _fmt(fold_end), stress_fee, stress_slip)

    for sym in SYMBOLS:
        run(f"symbol_base_{sym}", [sym], 360, args.end, base_fee, base_slip)
        run(f"symbol_stress_{sym}", [sym], 360, args.end, stress_fee, stress_slip)

    for sym in SYMBOLS:
        loo = [s for s in SYMBOLS if s != sym]
        run(f"leave_one_out_{sym}", loo, 360, args.end, base_fee, base_slip)

    _write_csv(out_dir / "strict_runs.csv", rows)
    verdict = _gate(rows)
    (out_dir / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    md = [
        "# Inplay Breakout-Retest Strict Gate 2026-07-06",
        "",
        f"- out_dir: `{out_dir}`",
        f"- symbols: `{','.join(SYMBOLS)}`",
        f"- base_cost_bps: fee `{base_fee}`, slippage `{base_slip}`",
        f"- stress_cost_bps: fee `{stress_fee}`, slippage `{stress_slip}`",
        f"- verdict: `{'PASS' if verdict['passed'] else 'FAIL'}`",
        f"- reasons: `{verdict['reasons']}`",
        "",
        "Research-only. PASS can justify shadow/risk=0.0, not automatic live money.",
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("verdict=" + json.dumps(verdict, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
