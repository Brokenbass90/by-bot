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

from bot.candle_coverage import assess_coverage
from bot.fx_harness import backtest_fx_setup, cost_feasibility, summarize_trades
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


def _coverage_rows(rows: Sequence[Sequence[float]]) -> List[List[float]]:
    """Normalize FX CSV rows for candle_coverage.

    The FX harness historically uses CSV timestamps in seconds. candle_coverage's
    contract is milliseconds (same as crypto/backtest rows), so normalize only
    for the data-quality gate and leave the trading harness untouched.
    """
    out: List[List[float]] = []
    for r in rows:
        try:
            ts = float(r[0])
            if ts < 10_000_000_000:  # seconds -> ms
                ts *= 1000.0
            out.append([ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]) if len(r) > 5 else 0.0])
        except Exception:
            continue
    return out


def _aggregate_rows_seconds(rows: Sequence[Sequence[float]], interval_min: int) -> List[List[float]]:
    """Aggregate second-timestamped M5 FX rows while preserving seconds.

    FX session filters intentionally expect epoch seconds. Do not use the common
    Candle(ms) aggregator here or London/NY/Asia session logic shifts by 1000x.
    """
    interval = int(interval_min)
    if interval <= 5:
        return [list(r) for r in rows]
    bucket_s = interval * 60
    out: List[List[float]] = []
    cur_bucket: int | None = None
    chunk: List[Sequence[float]] = []
    for r in rows:
        try:
            ts = int(float(r[0]))
        except Exception:
            continue
        bucket = (ts // bucket_s) * bucket_s
        if cur_bucket is None:
            cur_bucket = bucket
        if bucket != cur_bucket:
            if chunk:
                out.append([
                    float(cur_bucket),
                    float(chunk[0][1]),
                    max(float(x[2]) for x in chunk),
                    min(float(x[3]) for x in chunk),
                    float(chunk[-1][4]),
                    sum(float(x[5]) if len(x) > 5 else 0.0 for x in chunk),
                ])
            chunk = [r]
            cur_bucket = bucket
        else:
            chunk.append(r)
    if chunk and cur_bucket is not None:
        out.append([
            float(cur_bucket),
            float(chunk[0][1]),
            max(float(x[2]) for x in chunk),
            min(float(x[3]) for x in chunk),
            float(chunk[-1][4]),
            sum(float(x[5]) if len(x) > 5 else 0.0 for x in chunk),
        ])
    return out


def _default_market_closure_gap_bars(interval_min: int) -> int:
    # FX weekend is roughly 48h. Use ~75% of that as the scheduled-closure
    # threshold so ordinary feed holes still fail but weekends are not counted.
    return max(4, int(round(0.75 * (48 * 60 / max(1, int(interval_min))))))


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


def _parse_utc_boundary(value: str) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return parsed.timestamp()


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
    ap.add_argument("--start-utc", default="", help="Inclusive YYYY-MM-DD research boundary.")
    ap.add_argument("--end-utc", default="", help="Exclusive YYYY-MM-DD research boundary.")
    ap.add_argument("--interval-min", type=int, default=5, help="Aggregate M5 input to this interval before screening, preserving FX second timestamps.")
    ap.add_argument("--disable-coverage-gate", action="store_true", help="Research override: run even when candle coverage fails.")
    ap.add_argument("--disable-cost-gate", action="store_true", help="Research override: run even when round-trip cost is too large in R.")
    ap.add_argument("--coverage-interval-min", type=int, default=0, help="Override coverage interval; default = --interval-min.")
    ap.add_argument("--min-coverage", type=float, default=0.995)
    ap.add_argument("--max-gap-bars", type=int, default=12)
    ap.add_argument("--max-flat-frac", type=float, default=0.05)
    ap.add_argument("--min-coverage-bars", type=int, default=200)
    ap.add_argument("--market-closure-gap-bars", type=int, default=0, help="FX scheduled-closure threshold after aggregation; 0 = auto by --interval-min.")
    ap.add_argument("--max-fee-r", type=float, default=0.25)
    args = ap.parse_args()

    pairs = [x.strip().upper() for x in args.pairs.split(",") if x.strip()]
    setup_names = [x.strip() for x in args.setups.split(",") if x.strip()]
    tp_rrs = [float(x) for x in args.tp_rr.split(",") if x.strip()]
    sl_atrs = [float(x) for x in args.sl_atr.split(",") if x.strip()]
    max_holds = [int(x) for x in args.max_hold.split(",") if x.strip()]
    start_ts = _parse_utc_boundary(args.start_utc)
    end_ts = _parse_utc_boundary(args.end_utc)
    if start_ts is not None and end_ts is not None and end_ts <= start_ts:
        raise SystemExit("--end-utc must be later than --start-utc")
    data_dir = Path(args.data_dir)
    run_id = datetime.now(timezone.utc).strftime("fx_native_harness_%Y%m%d_%H%M%S")
    outdir = Path(args.outdir or f"reports/research/{run_id}")
    outdir.mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    all_trades: List[Dict[str, Any]] = []
    coverage_rows_out: List[Dict[str, Any]] = []
    for pair in pairs:
        path = data_dir / f"{pair}_M5.csv"
        if not path.exists():
            print(f"[skip] {pair} no data: {path}", flush=True)
            continue
        rows = _load_rows(path)
        if start_ts is not None:
            rows = [row for row in rows if float(row[0]) >= start_ts]
        if end_ts is not None:
            rows = [row for row in rows if float(row[0]) < end_ts]
        if args.tail_rows and args.tail_rows > 0:
            rows = rows[-int(args.tail_rows):]
        rows = _aggregate_rows_seconds(rows, args.interval_min)
        if len(rows) < int(args.min_coverage_bars):
            print(f"[skip] {pair} too few rows: {len(rows)}", flush=True)
            continue
        coverage_interval_min = int(args.coverage_interval_min or args.interval_min)
        closure_gap_bars = int(args.market_closure_gap_bars or _default_market_closure_gap_bars(coverage_interval_min))
        cov = assess_coverage(
            _coverage_rows(rows),
            symbol=pair,
            interval_min=coverage_interval_min,
            min_coverage=args.min_coverage,
            max_gap_bars_allowed=args.max_gap_bars,
            max_flat_frac=args.max_flat_frac,
            min_bars=args.min_coverage_bars,
            market_closure_gap_bars=closure_gap_bars,
        )
        coverage_rows_out.append({
            "symbol": pair,
            "coverage_ok": bool(cov.ok),
            "coverage": cov.coverage,
            "actual_bars": cov.actual_bars,
            "expected_bars": cov.expected_bars,
            "n_gaps": cov.n_gaps,
            "max_gap_bars": cov.max_gap_bars,
            "flat_frac": cov.flat_frac,
            "dup_bars": cov.dup_bars,
            "coverage_reasons": ";".join(cov.reasons),
        })
        print(
            f"[coverage] {pair} ok={cov.ok} coverage={cov.coverage} "
            f"gaps={cov.n_gaps} max_gap={cov.max_gap_bars} flat={cov.flat_frac} "
            f"reasons={';'.join(cov.reasons)}",
            flush=True,
        )
        if not cov.ok and not args.disable_coverage_gate:
            print(f"[skip] {pair} coverage_gate_failed", flush=True)
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
                        cf = cost_feasibility(
                            rows,
                            sl_atr=sl_atr,
                            fee_bps=args.fee_bps,
                            slippage_bps=args.slippage_bps,
                            max_fee_r=args.max_fee_r,
                        )
                        if not cf["feasible"] and not args.disable_cost_gate:
                            summaries.append({
                                "symbol": pair,
                                "setup": setup_name,
                                "tp_rr": tp_rr,
                                "sl_atr": sl_atr,
                                "max_hold": max_hold,
                                "coverage_ok": bool(cov.ok),
                                "coverage_reasons": ";".join(cov.reasons),
                                "cost_ok": False,
                                "fee_r": cf["fee_r"],
                                "cost_reason": cf["reason"],
                                "skip_reason": "cost_infeasible",
                                "trades": 0,
                                "net_r": 0.0,
                                "pf": 0.0,
                                "win_rate": 0.0,
                                "folds_positive": 0,
                                "min_fold_trades": 0,
                                "preflight_go": False,
                                "preflight_reasons": cf["reason"],
                            })
                            print(
                                f"[skip] {pair} {setup_name} rr={tp_rr} sl={sl_atr} "
                                f"hold={max_hold} cost_infeasible feeR={cf['fee_r']} reason={cf['reason']}",
                                flush=True,
                            )
                            continue
                        print(
                            f"[start] {pair} {setup_name} rr={tp_rr} sl={sl_atr} hold={max_hold} rows={len(rows)} interval={args.interval_min}",
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
                            "coverage_ok": bool(cov.ok),
                            "coverage_reasons": ";".join(cov.reasons),
                            "cost_ok": bool(cf["feasible"]),
                            "fee_r": cf["fee_r"],
                            "cost_reason": cf["reason"],
                            "skip_reason": "",
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
    coverage_path = outdir / "coverage.csv"
    if coverage_rows_out:
        with coverage_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(coverage_rows_out[0].keys()), lineterminator="\n")
            w.writeheader(); w.writerows(coverage_rows_out)
    if summaries:
        with summary_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(summaries[0].keys()), lineterminator="\n")
            w.writeheader(); w.writerows(summaries)
    if all_trades:
        keys: List[str] = []
        for r in all_trades:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with trades_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
            w.writeheader(); w.writerows(all_trades)

    top = sorted(summaries, key=lambda r: (bool(r["preflight_go"]), float(r["net_r"]), float(r["pf"])), reverse=True)[:20]
    lines = [
        "# FX native harness summary",
        "",
        f"- rows: {len(summaries)}",
        f"- data_dir: `{data_dir}`",
        f"- interval_min: `{args.interval_min}`",
        f"- requested_window_utc: `{args.start_utc or 'source_start'}..{args.end_utc or 'source_end'}` (end exclusive)",
        f"- coverage_gate: `{not args.disable_coverage_gate}`",
        f"- cost_gate: `{not args.disable_cost_gate}`",
        "",
        "| symbol | setup | rr | sl_atr | hold | coverage | cost | feeR | skip | trades | netR | PF | WR | folds+ | preflight |",
        "|---|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in top:
        lines.append(
            f"| {r['symbol']} | {r['setup']} | {r['tp_rr']} | {r['sl_atr']} | {r['max_hold']} | "
            f"{r.get('coverage_ok')} | {r.get('cost_ok')} | {_fmt(r.get('fee_r'))} | {r.get('skip_reason', '')} | "
            f"{r['trades']} | {_fmt(r['net_r'])} | {_fmt(r['pf'])} | {_fmt(r['win_rate'])} | "
            f"{r['folds_positive']}/4 | {r['preflight_go']} |"
        )
    lines += ["", "## Outputs", "", f"- `{summary_path}`", f"- `{coverage_path}`", f"- `{trades_path}`"]
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {outdir}", flush=True)
    return 0 if summaries else 1


if __name__ == "__main__":
    raise SystemExit(main())
