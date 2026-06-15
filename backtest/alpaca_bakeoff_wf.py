#!/usr/bin/env python3
"""Bear-inclusive Alpaca bake-off across current research variants.

Research only. This script keeps all variants on the same symbol universe,
period, initial capital, and round-trip fee/slippage assumption so the output is
useful for go/no-go decisions instead of cherry-picked bull-cache results.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_v3_event_backtest import _fetch
from scripts.alpaca_v39_ohlc_trailing_backtest import run_ohlc_v39
from strategies.alpaca_adaptive_v1 import AdaptiveConfig, select
from strategies.alpaca_dynamic_v3_event import (
    run_event_v3,
    run_static_top4,
    summarize_result as summarize_v3,
)
from strategies.alpaca_dynamic_v4_event import (
    SECTOR_MAP,
    run_event_v4,
    run_static_top4_v4,
    summarize_result as summarize_v4,
)


BEAR_2022_UNIVERSE = [
    "UNH",
    "GOOGL",
    "AAPL",
    "MSFT",
    "NVDA",
    "META",
    "AMZN",
    "TSLA",
    "AVGO",
    "ORCL",
    "JPM",
    "LLY",
    "V",
    "COST",
    "JNJ",
    "WMT",
    "PG",
    "KO",
]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if math.isfinite(out) else default


def _compact_result(result: dict) -> dict:
    out = dict(result)
    out["trades"] = [asdict(trade) for trade in result.get("trades", [])]
    return out


def _slice_data(data: dict[str, object], start: str, end: str) -> dict[str, object]:
    return {
        symbol: df[(df.index >= start) & (df.index < end)]
        for symbol, df in data.items()
    }


def _daily_closes(data: dict[str, object]) -> dict[str, dict[object, float]]:
    out: dict[str, dict[object, float]] = {}
    for symbol, df in data.items():
        rows: dict[object, float] = {}
        for date, row in df.iterrows():
            close = _safe_float(row["Close"], float("nan"))
            if close > 0:
                rows[date] = close
        if rows:
            out[symbol] = rows
    return out


def _max_drawdown_pct(curve: Iterable[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in curve:
        value = _safe_float(value)
        if value <= 0:
            continue
        peak = max(peak, value)
        if peak > 0:
            max_dd = max(max_dd, (peak - value) / peak)
    return max_dd * 100.0


def _profit_factor(returns: list[float]) -> float:
    gross_win = sum(x for x in returns if x > 0)
    gross_loss = -sum(x for x in returns if x < 0)
    if gross_loss <= 0:
        return float("inf") if gross_win > 0 else 0.0
    return gross_win / gross_loss


def _summarize_adaptive(
    *,
    initial_capital: float,
    equity_curve: list[float],
    monthly_returns: list[float],
    trade_returns: list[float],
) -> dict:
    final_equity = equity_curve[-1] if equity_curve else initial_capital
    wins = sum(1 for x in trade_returns if x > 0)
    losses = sum(1 for x in trade_returns if x < 0)
    return {
        "return_pct": (final_equity / initial_capital - 1.0) * 100.0 if initial_capital > 0 else 0.0,
        "profit_factor": _profit_factor(trade_returns),
        "winrate_pct": 100.0 * wins / max(1, wins + losses),
        "trades": len(trade_returns),
        "max_dd_pct": _max_drawdown_pct(equity_curve),
        "neg_months": sum(1 for x in monthly_returns if x < 0),
        "n_months": len(monthly_returns),
        "worst_month_pct": min(monthly_returns, default=0.0) * 100.0,
    }


def run_adaptive_monthly(
    data: dict[str, object],
    *,
    start: str,
    end: str,
    initial_capital: float,
    max_positions: int,
    fee_bps_round_trip: float,
    use_gate: bool,
    cfg: AdaptiveConfig | None = None,
    rebalance_every: int = 21,
) -> dict:
    cfg = cfg or AdaptiveConfig(max_positions=max_positions)
    closes = _daily_closes(data)
    if "SPY" not in closes:
        raise ValueError("SPY data is required for alpaca_adaptive_v1 regime gate")
    all_days = [
        day
        for day in sorted(closes["SPY"])
        if str(day.date()) >= start and str(day.date()) < end
    ]
    if not all_days:
        raise ValueError(f"no SPY evaluation days for {start}..{end}")

    universe = [symbol for symbol in closes if symbol not in {"SPY", "QQQ", "IWM"}]
    equity = float(initial_capital)
    equity_curve: list[float] = []
    monthly_returns: list[float] = []
    trade_returns: list[float] = []
    rebalance_log: list[dict] = []

    all_spy_days = sorted(closes["SPY"])
    start_pos = all_spy_days.index(all_days[0])
    end_day_set = set(all_days)
    i = start_pos
    while i < len(all_spy_days) - rebalance_every:
        day = all_spy_days[i]
        if day not in end_day_set:
            i += 1
            continue
        next_day = all_spy_days[i + rebalance_every]
        if str(next_day.date()) >= end:
            break

        index_series = [closes["SPY"][d] for d in all_spy_days[: i + 1] if d in closes["SPY"]]
        selector_universe: dict[str, list[float]] = {}
        for symbol in universe:
            series = [closes[symbol][d] for d in all_spy_days[: i + 1] if d in closes[symbol]]
            if len(series) >= max(cfg.mom_slow, cfg.vol_period, cfg.trend_sma) + 2:
                selector_universe[symbol] = series

        selected = select(
            selector_universe,
            index_series,
            sectors=SECTOR_MAP,
            cfg=cfg,
            force_regime_ok=not use_gate,
        )
        picks = selected.get("picks") or []
        period_ret = 0.0
        pick_rows: list[dict] = []
        for pick in picks:
            symbol = str(pick["symbol"])
            weight = _safe_float(pick.get("weight"))
            p0 = closes.get(symbol, {}).get(day)
            p1 = closes.get(symbol, {}).get(next_day)
            if not p0 or not p1 or p0 <= 0 or weight <= 0:
                continue
            contribution = weight * (p1 / p0 - 1.0) - weight * fee_bps_round_trip / 10_000.0
            period_ret += contribution
            trade_returns.append(contribution)
            pick_rows.append({"symbol": symbol, "weight": weight, "return_contribution": contribution})

        equity *= 1.0 + period_ret
        equity_curve.append(equity)
        monthly_returns.append(period_ret)
        rebalance_log.append(
            {
                "date": str(day.date()),
                "next_date": str(next_day.date()),
                "reason": selected.get("reason"),
                "regime_ok": selected.get("regime_ok"),
                "period_return": period_ret,
                "picks": pick_rows,
            }
        )
        i += rebalance_every

    return {
        "initial_capital": initial_capital,
        "final_equity": equity_curve[-1] if equity_curve else initial_capital,
        "daily_equity": [(row["date"], value) for row, value in zip(rebalance_log, equity_curve)],
        "monthly_returns": monthly_returns,
        "trade_returns": trade_returns,
        "rebalance_log": rebalance_log,
        "stats": _summarize_adaptive(
            initial_capital=initial_capital,
            equity_curve=equity_curve,
            monthly_returns=monthly_returns,
            trade_returns=trade_returns,
        ),
    }


def _print_stats(label: str, stats: dict) -> None:
    print(
        f"{label:<25} return={stats['return_pct']:>7.2f}% "
        f"PF={stats['profit_factor']:>6.3f} WR={stats['winrate_pct']:>5.1f}% "
        f"trades={int(stats['trades']):>3d} DD={stats['max_dd_pct']:>6.2f}% "
        f"neg={int(stats['neg_months']):>2d}/{int(stats['n_months']):<2d} "
        f"worst={stats['worst_month_pct']:>7.2f}%"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Alpaca bear-inclusive walk-forward bake-off")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2023-01-01")
    ap.add_argument("--data-start", default="2021-01-01")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--fee-bps", type=float, default=10.0)
    ap.add_argument("--symbols", default=",".join(BEAR_2022_UNIVERSE))
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    ap.add_argument("--tag", default="bear_2022")
    args = ap.parse_args()

    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    fetch_symbols = sorted(set(symbols + ["SPY"]))
    cache_dir = Path(args.cache_dir).expanduser()
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir

    print(
        f"Loading {len(fetch_symbols)} symbols for warm-up {args.data_start}..{args.end}; "
        f"evaluation {args.start}..{args.end}; fee={args.fee_bps}bps round-trip"
    )
    full_data = _fetch(fetch_symbols, args.data_start, args.end, cache_dir)
    data = {symbol: df for symbol, df in full_data.items() if symbol in symbols}
    spy_df = full_data.get("SPY")
    if spy_df is None:
        print("ERROR: missing SPY data", file=sys.stderr)
        return 2
    if len(data) < args.max_positions:
        print(f"ERROR: only {len(data)} symbols with data", file=sys.stderr)
        return 2

    eval_data = _slice_data(data, args.start, args.end)
    variants: dict[str, dict] = {}

    static_v3 = run_static_top4(
        eval_data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        rebalance_days=21,
        fee_bps=args.fee_bps,
    )
    variants["STATIC_TOP4_21D"] = {"stats": summarize_v3(static_v3), "result": _compact_result(static_v3)}

    v39 = run_event_v3(
        eval_data,
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
    variants["V39_EVENT_CLOSE"] = {"stats": summarize_v3(v39), "result": _compact_result(v39)}

    all_dates = sorted(set().union(*(set(df.index) for df in data.values())))
    from strategies.alpaca_dynamic_v3_event import rank_symbols

    ranks_by_date = {date: rank_symbols(data, date) for date in all_dates}
    ohlc_v39 = run_ohlc_v39(
        data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        profit_trigger_pct=8.0,
        trail_pullback_pct=2.5,
        stop_pct=9.0,
        peer_outperform_pct=15.0,
        review_interval_days=30,
        hard_max_age_days=60,
        fee_bps=args.fee_bps,
        spy_df=spy_df,
        spy_sma_days=200,
        spy_exit_on_risk_off=False,
        ranks_by_date=ranks_by_date,
        evaluation_start=args.start,
        evaluation_end=args.end,
    )
    variants["V39_OHLC_SPY200_GATE"] = {"stats": summarize_v3(ohlc_v39), "result": _compact_result(ohlc_v39)}

    v40 = run_event_v4(
        eval_data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        profit_trigger_pct=8.0,
        profit_pullback_pct=2.5,
        stop_pct=9.0,
        peer_outperform_pct=12.0,
        max_age_days=21,
        hard_max_age_days=60,
        max_portfolio_dd_pct=15.0,
        max_per_sector=2,
        fee_bps=args.fee_bps,
    )
    variants["V40_EVENT_DRAFT"] = {"stats": summarize_v4(v40), "result": _compact_result(v40)}

    static_v40 = run_static_top4_v4(
        eval_data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        max_per_sector=2,
        fee_bps=args.fee_bps,
    )
    variants["V40_STATIC_TOP4"] = {"stats": summarize_v4(static_v40), "result": _compact_result(static_v40)}

    adaptive_data = dict(data)
    adaptive_data["SPY"] = spy_df
    adaptive_gated = run_adaptive_monthly(
        adaptive_data,
        start=args.start,
        end=args.end,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        fee_bps_round_trip=args.fee_bps,
        use_gate=True,
    )
    adaptive_ungated = run_adaptive_monthly(
        adaptive_data,
        start=args.start,
        end=args.end,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        fee_bps_round_trip=args.fee_bps,
        use_gate=False,
    )
    variants["ADAPTIVE_V1_GATED"] = adaptive_gated
    variants["ADAPTIVE_V1_UNGATED_CONTROL"] = adaptive_ungated

    print("\n=== ALPACA BAKE-OFF ===")
    for label, payload in variants.items():
        _print_stats(label, payload["stats"])

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "period": f"{args.start}..{args.end}",
        "data_start": args.data_start,
        "cache_dir": str(cache_dir),
        "symbols": sorted(data),
        "fee_bps_round_trip": args.fee_bps,
        "capital": args.capital,
        "max_positions": args.max_positions,
        "variants": variants,
        "go_read": (
            "Prefer variants that preserve capital in 2022 bear OOS. "
            "A bullish-period winner with PF<1 or DD>15% here is not live-ready."
        ),
    }
    out_dir = ROOT / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"alpaca_bakeoff_wf_{stamp}_{args.tag}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    latest_path = out_dir / "alpaca_bakeoff_wf_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport: {out_path}")
    print(f"Latest: {latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
