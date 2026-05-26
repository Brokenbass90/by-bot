#!/usr/bin/env python3
"""Research-only OHLC/high-water trailing validation for Alpaca v39.

The existing v39 event runner manages exits from daily closing prices. That
cannot test the real paper failure mode where a position makes a sizeable
intraperiod high and then gives the gain back. This runner keeps v39 ranking
and rotation logic, but executes hard stops and armed profit-lock trails from
daily OHLC bars with conservative stop-first ordering.

Nothing in this script submits orders or changes paper/live configuration.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_v3_event_backtest import DEFAULT_UNIVERSE, _fetch
from strategies.alpaca_dynamic_v3_event import (
    EventPosition,
    EventTrade,
    rank_symbols,
    run_event_v3,
    summarize_result,
)


def _safe_float(value, default: float = float("nan")) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return number if math.isfinite(number) else default


def _bar(data: dict[str, object], symbol: str, date) -> dict[str, float] | None:
    df = data.get(symbol)
    if df is None or date not in df.index:
        return None
    row = df.loc[date]
    out = {name.lower(): _safe_float(row[name]) for name in ("Open", "High", "Low", "Close")}
    if min(out.values()) <= 0 or not all(math.isfinite(value) for value in out.values()):
        return None
    return out


def _sma_at(df, date, period: int) -> float | None:
    if df is None or date not in df.index:
        return None
    i = int(df.index.get_loc(date))
    if i + 1 < period:
        return None
    values = [_safe_float(v) for v in df["Close"].iloc[i - period + 1 : i + 1]]
    if not values or not all(math.isfinite(v) and v > 0 for v in values):
        return None
    return sum(values) / len(values)


def run_ohlc_v39(
    data: dict[str, object],
    *,
    initial_capital: float = 1000.0,
    max_positions: int = 4,
    profit_trigger_pct: float = 8.0,
    trail_pullback_pct: float = 2.5,
    stop_pct: float = 9.0,
    peer_outperform_pct: float = 15.0,
    review_interval_days: int = 30,
    hard_max_age_days: int = 60,
    fee_bps: float = 10.0,
    spy_df=None,
    spy_sma_days: int = 0,
    spy_exit_on_risk_off: bool = False,
    ranks_by_date: dict | None = None,
    evaluation_start: str = "",
    evaluation_end: str = "",
) -> dict:
    all_dates = sorted(set().union(*(set(df.index) for df in data.values())))
    if evaluation_start:
        all_dates = [date for date in all_dates if str(date.date()) >= evaluation_start]
    if evaluation_end:
        all_dates = [date for date in all_dates if str(date.date()) < evaluation_end]
    if not all_dates:
        raise ValueError("no dates")

    cash = float(initial_capital)
    positions: dict[str, EventPosition] = {}
    cooldown: dict[str, int] = {}
    trades: list[EventTrade] = []
    daily_equity: list[tuple[str, float]] = []
    entry_blocked_days = 0

    def closing_price(symbol: str, date) -> float | None:
        bar = _bar(data, symbol, date)
        return bar["close"] if bar is not None else None

    def equity(date) -> float:
        value = cash
        for pos in positions.values():
            price = closing_price(pos.symbol, date)
            if price is not None:
                value += pos.qty * price
        return value

    def close_position(symbol: str, date, price: float, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(symbol)
        fees = (pos.entry_price * pos.qty + price * pos.qty) * fee_bps / 10_000.0
        pnl = (price - pos.entry_price) * pos.qty - fees
        cash += pos.qty * price - fees
        trades.append(
            EventTrade(symbol, pos.entry_date, str(date.date()), pos.entry_price, price, pos.qty, pnl, reason)
        )
        cooldown[symbol] = 3

    def open_position(symbol: str, date, price: float, slot_value: float) -> None:
        nonlocal cash
        spend = min(cash, slot_value)
        fee = spend * fee_bps / 10_000.0
        qty = max(0.0, (spend - fee) / price) if price > 0 else 0.0
        if qty <= 0:
            return
        cash -= spend
        positions[symbol] = EventPosition(symbol, str(date.date()), price, qty, price, 0)

    for date in all_dates:
        for symbol in list(cooldown):
            cooldown[symbol] -= 1
            if cooldown[symbol] <= 0:
                del cooldown[symbol]

        ranks = ranks_by_date.get(date, []) if ranks_by_date is not None else rank_symbols(data, date)
        rank_by_symbol = {row["symbol"]: row for row in ranks}
        top_symbols = [row["symbol"] for row in ranks[: max_positions * 2]]
        risk_on = True
        if spy_sma_days > 0:
            spy_sma = _sma_at(spy_df, date, spy_sma_days)
            spy_bar = _bar({"SPY": spy_df}, "SPY", date) if spy_df is not None else None
            risk_on = bool(spy_sma is not None and spy_bar is not None and spy_bar["close"] >= spy_sma)

        for symbol, pos in list(positions.items()):
            bar = _bar(data, symbol, date)
            if bar is None:
                continue
            pos.age_days += 1
            pos.days_since_review += 1

            hard_stop = pos.entry_price * (1.0 - stop_pct / 100.0)
            peak_gain_pct = (pos.high_water / pos.entry_price - 1.0) * 100.0
            trailing_armed = peak_gain_pct >= profit_trigger_pct
            trail_stop = pos.high_water * (1.0 - trail_pullback_pct / 100.0)

            # OHLC cannot establish intraday sequence. Use the adverse fill
            # when multiple exits could occur in the same daily bar.
            if bar["low"] <= hard_stop:
                close_position(symbol, date, hard_stop, "hard_stop_ohlc")
                continue
            if trailing_armed and bar["low"] <= trail_stop:
                close_position(symbol, date, trail_stop, "profit_lock_trail_ohlc")
                continue

            pos.high_water = max(pos.high_water, bar["high"])
            close = bar["close"]
            reason = ""
            if spy_exit_on_risk_off and not risk_on:
                reason = "spy_risk_off_close"
            elif pos.age_days >= max(1, hard_max_age_days):
                reason = "hard_max_age_close"
            elif pos.days_since_review >= max(1, review_interval_days):
                cur_score = float((rank_by_symbol.get(symbol) or {}).get("score", -999.0))
                best_other = next(
                    (row for row in ranks if row["symbol"] not in positions and row["symbol"] not in cooldown),
                    None,
                )
                if symbol not in top_symbols[:max_positions] or (
                    best_other is not None and best_other["score"] - cur_score >= peer_outperform_pct / 100.0
                ):
                    reason = "event_rebalance_close"
                else:
                    pos.days_since_review = 0
            else:
                cur_score = float((rank_by_symbol.get(symbol) or {}).get("score", -999.0))
                best_other = next(
                    (row for row in ranks if row["symbol"] not in positions and row["symbol"] not in cooldown),
                    None,
                )
                if best_other is not None and best_other["score"] - cur_score >= peer_outperform_pct / 100.0:
                    reason = "peer_outperform_close"
            if reason:
                close_position(symbol, date, close, reason)

        allow_entries = risk_on
        if not allow_entries:
            entry_blocked_days += 1

        if allow_entries:
            slot_value = equity(date) / max(1, max_positions)
            for row in ranks:
                if len(positions) >= max_positions:
                    break
                symbol = row["symbol"]
                if symbol in positions or symbol in cooldown:
                    continue
                price = closing_price(symbol, date)
                if price is not None:
                    open_position(symbol, date, price, slot_value)

        daily_equity.append((str(date.date()), equity(date)))

    last_date = all_dates[-1]
    for symbol in list(positions):
        price = closing_price(symbol, last_date)
        if price is not None:
            close_position(symbol, last_date, price, "final_mark")
    daily_equity.append((str(last_date.date()), equity(last_date)))
    return {
        "initial_capital": initial_capital,
        "final_equity": equity(last_date),
        "trades": trades,
        "daily_equity": daily_equity,
        "entry_blocked_days": entry_blocked_days,
    }


def _compact(result: dict) -> dict:
    out = dict(result)
    out["trades"] = [asdict(trade) for trade in result.get("trades", [])]
    return out


def _score(stats: dict) -> float:
    drawdown = max(1.0, float(stats["max_dd_pct"]))
    return float(stats["return_pct"]) / drawdown * min(3.0, float(stats["profit_factor"])) / (
        1.0 + 0.15 * int(stats["neg_months"])
    )


def _print(label: str, stats: dict) -> None:
    print(
        f"{label}: return={stats['return_pct']:.2f}% PF={stats['profit_factor']:.3f} "
        f"WR={stats['winrate_pct']:.1f}% trades={stats['trades']} "
        f"DD={stats['max_dd_pct']:.2f}% neg_months={stats['neg_months']}/{stats['n_months']} "
        f"worst_month={stats['worst_month_pct']:.2f}%"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Alpaca v39 OHLC/high-water profit-lock research")
    ap.add_argument("--start", default="2024-05-01")
    ap.add_argument("--end", default="2026-05-01")
    ap.add_argument(
        "--data-start",
        default="",
        help="Optional earlier data start used only for ranking/SMA warm-up before --start.",
    )
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--fee-bps", type=float, default=10.0)
    ap.add_argument("--profit-trigger-pct", type=float, default=8.0)
    ap.add_argument("--trail-pullback-pct", type=float, default=2.5)
    ap.add_argument("--stop-pct", type=float, default=9.0)
    ap.add_argument("--peer-outperform-pct", type=float, default=15.0)
    ap.add_argument("--review-interval-days", type=int, default=30)
    ap.add_argument("--hard-max-age-days", type=int, default=60)
    ap.add_argument("--spy-sma-days", type=int, default=0)
    ap.add_argument("--spy-exit-on-risk-off", action="store_true")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    ap.add_argument("--tag", default="ohlc_profit_lock")
    args = ap.parse_args()

    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    data_start = args.data_start or args.start
    data = _fetch(symbols, data_start, args.end, cache_dir)
    if len(data) < args.max_positions:
        print(f"ERROR: only {len(data)} symbols with data", file=sys.stderr)
        return 2

    spy_df = None
    if args.spy_sma_days > 0 or args.grid:
        spy_data = _fetch(["SPY"], data_start, args.end, cache_dir)
        spy_df = spy_data.get("SPY")
    all_dates = sorted(set().union(*(set(df.index) for df in data.values())))
    ranks_by_date = {date: rank_symbols(data, date) for date in all_dates}
    eval_data = {
        symbol: df[(df.index >= args.start) & (df.index < args.end)]
        for symbol, df in data.items()
    }

    close_only = run_event_v3(
        eval_data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        profit_trigger_pct=args.profit_trigger_pct,
        profit_pullback_pct=args.trail_pullback_pct,
        stop_pct=args.stop_pct,
        peer_outperform_pct=args.peer_outperform_pct,
        max_age_days=args.review_interval_days,
        hard_max_age_days=args.hard_max_age_days,
        fee_bps=args.fee_bps,
    )
    close_stats = summarize_result(close_only)
    ohlc = run_ohlc_v39(
        data,
        initial_capital=args.capital,
        max_positions=args.max_positions,
        profit_trigger_pct=args.profit_trigger_pct,
        trail_pullback_pct=args.trail_pullback_pct,
        stop_pct=args.stop_pct,
        peer_outperform_pct=args.peer_outperform_pct,
        review_interval_days=args.review_interval_days,
        hard_max_age_days=args.hard_max_age_days,
        fee_bps=args.fee_bps,
        spy_df=spy_df,
        spy_sma_days=args.spy_sma_days,
        spy_exit_on_risk_off=args.spy_exit_on_risk_off,
        ranks_by_date=ranks_by_date,
        evaluation_start=args.start,
        evaluation_end=args.end,
    )
    ohlc_stats = summarize_result(ohlc)

    rows: list[dict] = []
    if args.grid:
        for trigger in (3.5, 5.0, 6.0, 8.0):
            for pullback in (2.0, 2.5, 3.5, 4.5):
                for spy_days, risk_off_exit in ((0, False), (100, False), (100, True), (200, False), (200, True)):
                    if spy_days > 0 and spy_df is None:
                        continue
                    candidate = run_ohlc_v39(
                        data,
                        initial_capital=args.capital,
                        max_positions=args.max_positions,
                        profit_trigger_pct=trigger,
                        trail_pullback_pct=pullback,
                        stop_pct=args.stop_pct,
                        peer_outperform_pct=args.peer_outperform_pct,
                        review_interval_days=args.review_interval_days,
                        hard_max_age_days=args.hard_max_age_days,
                        fee_bps=args.fee_bps,
                        spy_df=spy_df,
                        spy_sma_days=spy_days,
                        spy_exit_on_risk_off=risk_off_exit,
                        ranks_by_date=ranks_by_date,
                        evaluation_start=args.start,
                        evaluation_end=args.end,
                    )
                    stats = summarize_result(candidate)
                    rows.append(
                        {
                            "trigger_pct": trigger,
                            "trail_pullback_pct": pullback,
                            "spy_sma_days": spy_days,
                            "spy_exit_on_risk_off": risk_off_exit,
                            "score": _score(stats),
                            "entry_blocked_days": candidate["entry_blocked_days"],
                            **stats,
                        }
                    )
        rows.sort(key=lambda row: row["score"], reverse=True)

    print("\n=== OHLC/HIGH-WATER VALIDATION ===")
    _print("V39_CLOSE_ONLY_CONTROL", close_stats)
    _print("V39_OHLC_PROFIT_LOCK", ohlc_stats)
    if rows:
        print("\n=== GRID TOP 10 ===")
        for row in rows[:10]:
            print(
                f"score={row['score']:.3f} ret={row['return_pct']:.2f}% PF={row['profit_factor']:.3f} "
                f"DD={row['max_dd_pct']:.2f}% neg={row['neg_months']}/{row['n_months']} "
                f"trades={row['trades']} trigger={row['trigger_pct']} "
                f"trail={row['trail_pullback_pct']} spy_sma={row['spy_sma_days']} "
                f"risk_off_exit={int(row['spy_exit_on_risk_off'])}"
            )
    print("NOTE: research only; daily OHLC uses adverse stop-first ordering for ambiguous bars.")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "period": f"{args.start}..{args.end}",
        "model_scope": "daily_ohlc_high_water_stop_first_not_intraday_fill_proof",
        "params": vars(args),
        "exit_reasons": dict(Counter(trade.reason for trade in ohlc["trades"])),
        "close_only_control": {"stats": close_stats, "result": _compact(close_only)},
        "ohlc_profit_lock": {"stats": ohlc_stats, "result": _compact(ohlc)},
        "grid_top": rows[:20],
        "next_gate": "Validate the selected variant on OOS and bear stress, then shadow paper only.",
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "runtime" / f"alpaca_v39_ohlc_report_{stamp}_{args.tag}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (ROOT / "runtime" / "alpaca_v39_ohlc_report_latest.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(f"Report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
