#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("ERROR: install pandas yfinance", file=sys.stderr)
    sys.exit(2)

from strategies.alpaca_dynamic_v3_event import (
    run_event_v3,
    run_static_top4,
    summarize_result,
)


DEFAULT_UNIVERSE = [
    "UNH", "GOOGL", "AAPL", "MSFT", "NVDA", "META", "AMZN", "TSLA",
    "AVGO", "ORCL", "JPM", "LLY", "V", "COST", "JNJ", "WMT", "PG", "KO",
]


def _fetch(symbols: list[str], start: str, end: str, cache_dir: Path | None = None) -> dict[str, object]:
    out: dict[str, object] = {}
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        cache_path = None
        try:
            if cache_dir is not None:
                safe_period = f"{start}_{end}".replace("-", "")
                cache_path = cache_dir / f"{symbol}_{safe_period}.csv"
            if cache_path is not None and cache_path.exists():
                try:
                    df = pd.read_csv(cache_path, parse_dates=["Date"], index_col="Date")
                except ValueError:
                    df = pd.read_csv(cache_path, header=[0, 1], index_col=0, parse_dates=True)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
            else:
                df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        except Exception as exc:
            print(f"  {symbol}: error {exc}")
            continue
        if df is None or df.empty:
            print(f"  {symbol}: no data")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if cache_path is not None and df is not None and not df.empty:
            df.to_csv(cache_path, index_label="Date")
        needed = {"Open", "High", "Low", "Close"}
        if not needed.issubset(set(df.columns)):
            print(f"  {symbol}: bad columns")
            continue
        out[symbol] = df.dropna(subset=["Open", "High", "Low", "Close"])
        print(f"  {symbol}: {len(out[symbol])} bars")
    return out


def _compact(result: dict) -> dict:
    out = dict(result)
    out["trades"] = [asdict(t) for t in result.get("trades", [])]
    return out


def _score(stats: dict) -> float:
    ret = float(stats.get("return_pct") or 0.0)
    dd = max(1.0, float(stats.get("max_dd_pct") or 0.0))
    pf = max(0.0, float(stats.get("profit_factor") or 0.0))
    neg = max(0, int(stats.get("neg_months") or 0))
    return (ret / dd) * min(3.0, pf) / (1.0 + 0.15 * neg)


def _run_event_once(data: dict, args: argparse.Namespace, **overrides) -> tuple[dict, dict]:
    params = {
        "initial_capital": args.capital,
        "max_positions": args.max_positions,
        "profit_trigger_pct": args.profit_trigger_pct,
        "profit_pullback_pct": args.profit_pullback_pct,
        "stop_pct": args.stop_pct,
        "peer_outperform_pct": args.peer_outperform_pct,
        "max_age_days": args.max_age_days,
        "hard_max_age_days": args.hard_max_age_days,
        "fee_bps": args.fee_bps,
    }
    params.update(overrides)
    result = run_event_v3(data, **params)
    stats = summarize_result(result)
    return result, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Alpaca v39 event-based rebalance research backtest")
    ap.add_argument("--start", default="2024-05-01")
    ap.add_argument("--end", default="2026-05-01")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--profit-trigger-pct", type=float, default=8.0)
    ap.add_argument("--profit-pullback-pct", type=float, default=2.5)
    ap.add_argument("--stop-pct", type=float, default=5.0)
    ap.add_argument("--peer-outperform-pct", type=float, default=10.0)
    ap.add_argument(
        "--max-age-days",
        type=int,
        default=14,
        help="Event review interval retained for compatibility with existing v39 reports.",
    )
    ap.add_argument("--hard-max-age-days", type=int, default=60, help="Absolute holding limit.")
    ap.add_argument("--fee-bps", type=float, default=1.0)
    ap.add_argument("--tag", default="v39_event")
    ap.add_argument("--grid", action="store_true", help="Run a small parameter grid after the default run")
    ap.add_argument("--wide-grid", action="store_true", help="Run a wider parameter grid")
    ap.add_argument(
        "--focused-grid",
        action="store_true",
        help="Run a bounded refinement grid around the saved v39 event winner.",
    )
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(f"Fetching {len(symbols)} symbols for {args.start}..{args.end}")
    cache_dir = Path(args.cache_dir).expanduser()
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    data = _fetch(symbols, args.start, args.end, cache_dir)
    if len(data) < args.max_positions:
        print(f"ERROR: only {len(data)} symbols with data", file=sys.stderr)
        return 2

    event, event_stats = _run_event_once(data, args)
    static = run_static_top4(
        data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        rebalance_days=21,
        fee_bps=args.fee_bps,
    )

    static_stats = summarize_result(static)
    grid_rows = []
    best_grid = None

    if args.grid:
        if args.focused_grid:
            # 12 combinations around the current winner. First isolate the
            # exit mechanics causing red months before widening entry search.
            profit_triggers = (8.0,)
            pullbacks = (2.0, 2.5)
            stops = (7.0, 9.0, 11.0)
            peers = (15.0,)
            ages = (21, 30)
            hard_ages = (30, 45, 60)
        elif args.wide_grid:
            profit_triggers = (6.0, 8.0, 10.0, 12.0, 15.0)
            pullbacks = (1.5, 2.5, 4.0, 6.0)
            stops = (4.0, 5.0, 7.0, 9.0, 12.0)
            peers = (6.0, 10.0, 15.0, 20.0)
            ages = (7, 14, 21, 30, 45)
            hard_ages = (args.hard_max_age_days,)
        else:
            profit_triggers = (8.0, 10.0, 12.0)
            pullbacks = (2.5, 4.0)
            stops = (5.0, 7.0)
            peers = (10.0, 15.0)
            ages = (14, 21)
            hard_ages = (args.hard_max_age_days,)
        for profit_trigger in profit_triggers:
            for pullback in pullbacks:
                for stop in stops:
                    for peer in peers:
                        for max_age in ages:
                            for hard_age in hard_ages:
                                _, st = _run_event_once(
                                    data,
                                    args,
                                    profit_trigger_pct=profit_trigger,
                                    profit_pullback_pct=pullback,
                                    stop_pct=stop,
                                    peer_outperform_pct=peer,
                                    max_age_days=max_age,
                                    hard_max_age_days=hard_age,
                                )
                                row = {
                                    "profit_trigger_pct": profit_trigger,
                                    "profit_pullback_pct": pullback,
                                    "stop_pct": stop,
                                    "peer_outperform_pct": peer,
                                    "max_age_days": max_age,
                                    "hard_max_age_days": hard_age,
                                    "score": _score(st),
                                    **st,
                                }
                                grid_rows.append(row)
        grid_rows.sort(key=lambda r: r["score"], reverse=True)
        best_grid = grid_rows[0] if grid_rows else None

    print("\n=== SUMMARY ===")
    for label, stats in (("STATIC_TOP4_21D", static_stats), ("V39_EVENT", event_stats)):
        print(
            f"{label}: return={stats['return_pct']:.2f}% PF={stats['profit_factor']:.3f} "
            f"WR={stats['winrate_pct']:.1f}% trades={stats['trades']} "
            f"DD={stats['max_dd_pct']:.2f}% neg_months={stats['neg_months']}/{stats['n_months']} "
            f"worst_month={stats['worst_month_pct']:.2f}%"
        )

    verdict = "REJECT"
    if (
        event_stats["profit_factor"] >= static_stats["profit_factor"]
        and event_stats["max_dd_pct"] <= static_stats["max_dd_pct"] * 1.05
        and event_stats["trades"] >= max(1, static_stats["trades"] * 2)
    ):
        verdict = "PAPER_SHADOW_CANDIDATE"

    if best_grid:
        print("\n=== GRID TOP 10 ===")
        for row in grid_rows[:10]:
            print(
                f"score={row['score']:.3f} ret={row['return_pct']:.2f}% PF={row['profit_factor']:.3f} "
                f"WR={row['winrate_pct']:.1f}% trades={row['trades']} DD={row['max_dd_pct']:.2f}% "
                f"neg={row['neg_months']}/{row['n_months']} "
                f"pt={row['profit_trigger_pct']} pb={row['profit_pullback_pct']} "
                f"stop={row['stop_pct']} peer={row['peer_outperform_pct']} "
                f"review={row['max_age_days']} hard_age={row['hard_max_age_days']}"
            )

    print(f"Verdict: {verdict}")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "period": f"{args.start}..{args.end}",
        "symbols": sorted(data),
        "params": vars(args),
        "static_top4_21d": {"stats": static_stats, "result": _compact(static)},
        "v39_event": {"stats": event_stats, "result": _compact(event)},
        "grid_top": grid_rows[:20],
        "verdict": verdict,
        "acceptance": "Promote to 30d paper shadow only if PF >= static, DD not worse, trades >= 2x.",
    }

    out_dir = ROOT / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"alpaca_v39_event_report_{stamp}_{args.tag}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    latest = out_dir / "alpaca_v39_event_report_latest.json"
    latest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
