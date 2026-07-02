#!/usr/bin/env python3
"""Run native FX/CFD setups through bot.fx_harness and write a compact gate report.

This is a cheap first pass, not a promotion-grade WF. It answers:
* does a setup produce enough trades?
* does rough R survive costs?
* are 4 chronological folds stable enough to deserve a heavier OOS sweep?
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.fx_harness import backtest_fx_setup, summarize_trades
from bot.fx_setups import (
    round_level_sweep,
    session_breakout_retest,
    session_range_fade,
    trend_pullback,
)
from bot.preflight_check import preflight


SETUPS: Dict[str, Callable[..., Any]] = {
    "session_range_fade": session_range_fade,
    "round_level_sweep": round_level_sweep,
    "session_breakout_retest": session_breakout_retest,
    "trend_pullback": trend_pullback,
}


def _load_rows(path: Path) -> List[List[float]]:
    rows: List[List[float]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append([
                    float(r["ts"]),
                    float(r["o"]),
                    float(r["h"]),
                    float(r["l"]),
                    float(r["c"]),
                    float(r.get("v") or 0.0),
                ])
            except Exception:
                continue
    return rows


def _pf(rs: Sequence[float]) -> float:
    gains = sum(x for x in rs if x > 0)
    losses = -sum(x for x in rs if x < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _folds(trades: Sequence[Dict[str, Any]], n: int = 4) -> List[Dict[str, Any]]:
    tr = sorted(trades, key=lambda x: float(x["entry_ts"]))
    out: List[Dict[str, Any]] = []
    m = len(tr)
    for i in range(n):
        part = tr[i * m // n:(i + 1) * m // n]
        rs = [float(t["r"]) for t in part]
        out.append({"fold": i + 1, "trades": len(rs), "net_r": round(sum(rs), 4), "pf": _pf(rs)})
    return out


def _fmt(v: Any, nd: int = 3) -> str:
    try:
        x = float(v)
    except Exception:
        return str(v)
    if math.isinf(x):
        return "inf"
    return f"{x:.{nd}f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data_cache/forex")
    ap.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY,XAUUSD")
    ap.add_argument("--setups", default="session_range_fade,round_level_sweep,session_breakout_retest,trend_pullback")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--tp-rr", default="1.5,2.0,2.5")
    ap.add_argument("--sl-atr", default="0.8,1.0,1.3")
    ap.add_argument("--max-hold", default="120,240")
    ap.add_argument("--fee-bps", type=float, default=1.0)
    ap.add_argument("--slippage-bps", type=float, default=0.5)
    ap.add_argument("--tail-rows", type=int, default=0, help="Use only the latest N rows per symbol; 0 = all.")
    args = ap.parse_args()

    pairs = [x.strip().upper() for x in args.pairs.split(",") if x.strip()]
    setup_names = [x.strip() for x in args.setups.split(",") if x.strip()]
    tp_rrs = [float(x) for x in args.tp_rr.split(",") if x.strip()]
    sl_atrs = [float(x) for x in args.sl_atr.split(",") if x.strip()]
    max_holds = [int(x) for x in args.max_hold.split(",") if x.strip()]
    data_dir = Path(args.data_dir)
    run_id = datetime.now(timezone.utc).strftime("fx_native_harness_%Y%m%d_%H%M%S")
    outdir = Path(args.outdir or f"reports/research/{run_id}")
    outdir.mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    for pair in pairs:
        path = data_dir / f"{pair}_M5.csv"
        if not path.exists():
            print(f"[skip] {pair} no data: {path}", flush=True)
            continue
        rows = _load_rows(path)
        if args.tail_rows and args.tail_rows > 0:
            rows = rows[-int(args.tail_rows):]
        if len(rows) < 1000:
            print(f"[skip] {pair} too few rows: {len(rows)}", flush=True)
            continue
        for setup_name in setup_names:
            setup_fn = SETUPS.get(setup_name)
            if setup_fn is None:
                continue
            setup_kwargs: Dict[str, Any] = {}
            if setup_name in {"session_range_fade", "round_level_sweep"}:
                setup_kwargs["block_asia"] = False
            for tp_rr in tp_rrs:
                for sl_atr in sl_atrs:
                    for max_hold in max_holds:
                        print(
                            f"[start] {pair} {setup_name} rr={tp_rr} sl={sl_atr} hold={max_hold} rows={len(rows)}",
                            flush=True,
                        )
                        trades = backtest_fx_setup(
                            rows,
                            setup_fn,
                            setup_kwargs=setup_kwargs,
                            tp_rr=tp_rr,
                            sl_atr=sl_atr,
                            max_hold=max_hold,
                            fee_bps=args.fee_bps,
                            slippage_bps=args.slippage_bps,
                        )
                        for t in trades:
                            t.update({
                                "symbol": pair,
                                "setup": setup_name,
                                "tp_rr": tp_rr,
                                "sl_atr": sl_atr,
                                "max_hold": max_hold,
                            })
                        s = summarize_trades(trades)
                        pf = float(s["pf"]) if s["pf"] != float("inf") else float("inf")
                        folds = _folds(trades)
                        pf_report = preflight(
                            [
                                {"ts": t["entry_ts"], "symbol": pair, "r": t["r"]}
                                for t in trades
                            ],
                            min_trades_total=30,
                            min_trades_per_fold=5,
                            min_symbols=1,
                        )
                        summaries.append({
                            "symbol": pair,
                            "setup": setup_name,
                            "tp_rr": tp_rr,
                            "sl_atr": sl_atr,
                            "max_hold": max_hold,
                            "trades": int(s["trades"]),
                            "net_r": float(s["net_r"]),
                            "pf": pf,
                            "win_rate": float(s["win_rate"]),
                            "folds_positive": sum(1 for f in folds if float(f["net_r"]) > 0),
                            "min_fold_trades": min((int(f["trades"]) for f in folds), default=0),
                            "preflight_go": bool(pf_report.go),
                            "preflight_reasons": ";".join(pf_report.reasons),
                        })
                        all_trades.extend(trades)
                        print(
                            f"[run] {pair} {setup_name} rr={tp_rr} sl={sl_atr} hold={max_hold} "
                            f"tr={s['trades']} netR={s['net_r']} pf={_fmt(pf)} preflight={pf_report.go}",
                            flush=True,
                        )

    summary_path = outdir / "summary.csv"
    trades_path = outdir / "trades.csv"
    if summaries:
        with summary_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
            w.writeheader(); w.writerows(summaries)
    if all_trades:
        keys: List[str] = []
        for r in all_trades:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with trades_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader(); w.writerows(all_trades)

    top = sorted(summaries, key=lambda r: (bool(r["preflight_go"]), float(r["net_r"]), float(r["pf"])), reverse=True)[:20]
    lines = [
        "# FX native harness summary",
        "",
        f"- rows: {len(summaries)}",
        f"- data_dir: `{data_dir}`",
        "",
        "| symbol | setup | rr | sl_atr | hold | trades | netR | PF | WR | folds+ | preflight |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in top:
        lines.append(
            f"| {r['symbol']} | {r['setup']} | {r['tp_rr']} | {r['sl_atr']} | {r['max_hold']} | "
            f"{r['trades']} | {_fmt(r['net_r'])} | {_fmt(r['pf'])} | {_fmt(r['win_rate'])} | "
            f"{r['folds_positive']}/4 | {r['preflight_go']} |"
        )
    lines += ["", "## Outputs", "", f"- `{summary_path}`", f"- `{trades_path}`"]
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {outdir}", flush=True)
    return 0 if summaries else 1


if __name__ == "__main__":
    raise SystemExit(main())
