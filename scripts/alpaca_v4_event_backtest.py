#!/usr/bin/env python3
"""Compare the Alpaca v4 research draft with the saved v39 event baseline.

This first comparison is deliberately daily-close based, matching the existing
v39 research harness. It does not prove intraday peak capture or broker-side
trailing behavior; those require an OHLC/high-water simulator next.
"""

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

from scripts.alpaca_v3_event_backtest import DEFAULT_UNIVERSE, _fetch
from strategies.alpaca_dynamic_v3_event import run_event_v3, summarize_result as summarize_v39
from strategies.alpaca_dynamic_v4_event import (
    run_event_v4,
    run_static_top4_v4,
    summarize_result as summarize_v40,
)


def _compact(result: dict) -> dict:
    out = dict(result)
    out["trades"] = [asdict(t) for t in result.get("trades", [])]
    return out


def _print_stats(label: str, stats: dict) -> None:
    print(
        f"{label}: return={stats['return_pct']:.2f}% PF={stats['profit_factor']:.3f} "
        f"WR={stats['winrate_pct']:.1f}% trades={stats['trades']} "
        f"DD={stats['max_dd_pct']:.2f}% neg_months={stats['neg_months']}/{stats['n_months']} "
        f"worst_month={stats['worst_month_pct']:.2f}%"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Alpaca v40 draft vs v39 close-based research comparison")
    ap.add_argument("--start", default="2024-05-01")
    ap.add_argument("--end", default="2026-05-01")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--fee-bps", type=float, default=10.0)
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    ap.add_argument("--tag", default="v40_close_compare")
    ap.add_argument("--v4-stop-pct", type=float, default=9.0)
    ap.add_argument("--v4-profit-trigger-pct", type=float, default=8.0)
    ap.add_argument("--v4-profit-pullback-pct", type=float, default=2.5)
    ap.add_argument("--v4-peer-outperform-pct", type=float, default=12.0)
    ap.add_argument("--v4-max-age-days", type=int, default=21)
    ap.add_argument("--v4-hard-max-age-days", type=int, default=60)
    ap.add_argument("--v4-max-portfolio-dd-pct", type=float, default=15.0)
    ap.add_argument("--v4-max-per-sector", type=int, default=2)
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    cache_dir = Path(args.cache_dir).expanduser()
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    print(f"Loading {len(symbols)} cached symbols for {args.start}..{args.end}")
    data = _fetch(symbols, args.start, args.end, cache_dir)
    if len(data) < args.max_positions:
        print(f"ERROR: only {len(data)} symbols with data", file=sys.stderr)
        return 2

    # Keep the validated v39 fee-stressed candidate parameters unchanged.
    v39 = run_event_v3(
        data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        profit_trigger_pct=8.0,
        profit_pullback_pct=2.5,
        stop_pct=9.0,
        peer_outperform_pct=15.0,
        max_age_days=30,
        hard_max_age_days=60,
        fee_bps=args.fee_bps,
    )
    v40 = run_event_v4(
        data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        profit_trigger_pct=args.v4_profit_trigger_pct,
        profit_pullback_pct=args.v4_profit_pullback_pct,
        stop_pct=args.v4_stop_pct,
        peer_outperform_pct=args.v4_peer_outperform_pct,
        max_age_days=args.v4_max_age_days,
        hard_max_age_days=args.v4_hard_max_age_days,
        max_portfolio_dd_pct=args.v4_max_portfolio_dd_pct,
        max_per_sector=args.v4_max_per_sector,
        fee_bps=args.fee_bps,
    )
    static_v40 = run_static_top4_v4(
        data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        max_per_sector=args.v4_max_per_sector,
        fee_bps=args.fee_bps,
    )

    v39_stats = summarize_v39(v39)
    v40_stats = summarize_v40(v40)
    static_stats = summarize_v40(static_v40)

    print("\n=== CLOSE-BASED RESEARCH COMPARISON ===")
    _print_stats("V39_EVENT_SAVED", v39_stats)
    _print_stats("V40_EVENT_DRAFT", v40_stats)
    _print_stats("V40_STATIC_TOP4", static_stats)
    print("NOTE: daily-close model only; does not validate intraday peak/trailing capture.")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "period": f"{args.start}..{args.end}",
        "model_scope": "daily_close_only_not_intraday_high_water",
        "symbols": sorted(data),
        "params": vars(args),
        "v39_event_saved": {"stats": v39_stats, "result": _compact(v39)},
        "v40_event_draft": {"stats": v40_stats, "result": _compact(v40)},
        "v40_static_top4": {"stats": static_stats, "result": _compact(static_v40)},
        "next_gate": "Build OHLC/high-water trailing simulator before any paper promotion.",
    }
    out_dir = ROOT / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"alpaca_v40_close_compare_{stamp}_{args.tag}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out_dir / "alpaca_v40_close_compare_latest.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(f"Report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
