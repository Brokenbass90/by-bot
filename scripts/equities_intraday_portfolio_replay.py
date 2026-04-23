#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.types import Candle, Signal
from scripts.equities_alpaca_intraday_bridge import (
    _build_runtime_catalog,
    _build_strategy,
    _load_env_file,
    _refresh_runtime_paths,
)


@dataclass
class Position:
    symbol: str
    strategy: str
    side: str
    entry_ts: int
    entry: float
    sl: float
    tp: float
    qty: float
    notional: float


@dataclass
class ClosedTrade:
    symbol: str
    strategy: str
    side: str
    entry_ts: int
    exit_ts: int
    entry: float
    exit: float
    sl: float
    tp: float
    qty: float
    gross_pnl: float
    fees: float
    net_pnl: float
    reason: str


def _dt(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _last_data_date(data_dir: Path) -> str:
    spy = data_dir / "SPY_M5.csv"
    if not spy.exists():
        files = sorted(data_dir.glob("*_M5.csv"))
        if not files:
            raise SystemExit(f"no *_M5.csv files in {data_dir}")
        spy = files[0]
    bars = load_m5_csv(str(spy))
    if not bars:
        raise SystemExit(f"empty data file: {spy}")
    return datetime.fromtimestamp(bars[-1].ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _load_window(path: Path, start_ts: int, end_ts: int) -> List[Candle]:
    bars = load_m5_csv(str(path))
    return [c for c in bars if start_ts <= c.ts <= end_ts]


def _check_exit(pos: Position, c: Candle) -> Optional[tuple[float, str]]:
    # Conservative same-bar rule: if both SL and TP are touched, count SL first.
    if pos.side == "long":
        if c.l <= pos.sl:
            return pos.sl, "SL"
        if c.h >= pos.tp:
            return pos.tp, "TP"
    else:
        if c.h >= pos.sl:
            return pos.sl, "SL"
        if c.l <= pos.tp:
            return pos.tp, "TP"
    return None


def _close_position(pos: Position, exit_ts: int, exit_price: float, reason: str, fee_bps: float) -> ClosedTrade:
    if pos.side == "long":
        gross = (exit_price - pos.entry) * pos.qty
    else:
        gross = (pos.entry - exit_price) * pos.qty
    fees = (pos.entry * pos.qty + exit_price * pos.qty) * fee_bps / 10_000.0
    net = gross - fees
    return ClosedTrade(
        symbol=pos.symbol,
        strategy=pos.strategy,
        side=pos.side,
        entry_ts=pos.entry_ts,
        exit_ts=exit_ts,
        entry=pos.entry,
        exit=exit_price,
        sl=pos.sl,
        tp=pos.tp,
        qty=pos.qty,
        gross_pnl=gross,
        fees=fees,
        net_pnl=net,
        reason=reason,
    )


def _max_drawdown(equity_points: List[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for v in equity_points:
        peak = max(peak, v)
        worst = min(worst, v - peak)
    return abs(worst)


def run(args: argparse.Namespace) -> Path:
    env_path = Path(args.env).expanduser().resolve()
    if env_path.exists():
        _load_env_file(env_path)
    if args.config_file:
        os.environ["INTRADAY_CONFIG_FILE"] = str(Path(args.config_file).expanduser())
    # For a replay we freeze the currently generated config instead of rebuilding
    # a future-aware watchlist during historical windows.
    os.environ["INTRADAY_DYNAMIC_BUILD"] = "0"
    _refresh_runtime_paths()

    data_dir = Path(os.environ.get("INTRADAY_DATA_DIR", "data_cache/equities_1h")).expanduser()
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    end_date = args.end_date or _last_data_date(data_dir)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1) - timedelta(seconds=1)
    start_dt = end_dt - timedelta(days=args.days - 1)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    specs, csv_paths = _build_runtime_catalog()
    if args.symbols:
        allow = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        specs = {s: v for s, v in specs.items() if s in allow}
        csv_paths = {s: p for s, p in csv_paths.items() if s in allow}

    bars_by_symbol: Dict[str, List[Candle]] = {}
    for sym, path in csv_paths.items():
        if path.exists():
            bars = _load_window(path, start_ts, end_ts)
            if len(bars) >= 250:
                bars_by_symbol[sym] = bars
    specs = {s: specs[s] for s in specs if s in bars_by_symbol}
    if not specs:
        raise SystemExit("no symbols with enough bars for replay")

    strategies = {s: _build_strategy(s, specs) for s in specs}
    idx_by_symbol = {s: 0 for s in specs}
    open_pos: Dict[str, Position] = {}
    trades: List[ClosedTrade] = []
    equity = float(args.capital)
    equity_points = [equity]
    slot_notional = float(args.capital) / max(1, int(args.max_positions))

    all_ts = sorted({c.ts for bars in bars_by_symbol.values() for c in bars})
    for ts in all_ts:
        # First manage open positions on the current bar.
        for sym, pos in list(open_pos.items()):
            bars = bars_by_symbol.get(sym) or []
            i = idx_by_symbol.get(sym, 0)
            if i >= len(bars) or bars[i].ts != ts or ts <= pos.entry_ts:
                continue
            hit = _check_exit(pos, bars[i])
            if hit:
                exit_price, reason = hit
                tr = _close_position(pos, ts, exit_price, reason, args.fee_bps)
                trades.append(tr)
                equity += tr.net_pnl
                equity_points.append(equity)
                del open_pos[sym]

        # Then evaluate new signals. This mirrors "enter after candle close".
        for sym in sorted(specs):
            if len(open_pos) >= args.max_positions:
                break
            if sym in open_pos:
                continue
            bars = bars_by_symbol[sym]
            i = idx_by_symbol[sym]
            if i >= len(bars) or bars[i].ts != ts:
                continue
            sig: Optional[Signal] = strategies[sym].maybe_signal(bars, i)
            if not sig:
                continue
            entry = float(sig.entry)
            if entry <= 0:
                continue
            qty = slot_notional / entry
            class_name = str(specs[sym]["class"])
            open_pos[sym] = Position(
                symbol=sym,
                strategy=class_name,
                side=sig.side,
                entry_ts=ts,
                entry=entry,
                sl=float(sig.sl),
                tp=float(sig.tp),
                qty=qty,
                notional=slot_notional,
            )

        # Advance symbol pointers for this timestamp.
        for sym, bars in bars_by_symbol.items():
            i = idx_by_symbol[sym]
            if i < len(bars) and bars[i].ts == ts:
                idx_by_symbol[sym] = i + 1

    # Mark remaining positions at the last available close.
    for sym, pos in list(open_pos.items()):
        bars = bars_by_symbol.get(sym) or []
        if not bars:
            continue
        last = bars[-1]
        tr = _close_position(pos, last.ts, last.c, "EOD", args.fee_bps)
        trades.append(tr)
        equity += tr.net_pnl
        equity_points.append(equity)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "backtest_runs" / f"equities_intraday_portfolio_{stamp}_{args.tag}"
    out.mkdir(parents=True, exist_ok=True)

    with (out / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        fields = list(ClosedTrade.__dataclass_fields__.keys()) + ["entry_time", "exit_time"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for tr in trades:
            row = tr.__dict__.copy()
            row["entry_time"] = _dt(tr.entry_ts)
            row["exit_time"] = _dt(tr.exit_ts)
            w.writerow(row)

    monthly: Dict[str, float] = {}
    for tr in trades:
        m = datetime.fromtimestamp(tr.exit_ts, tz=timezone.utc).strftime("%Y-%m")
        monthly[m] = monthly.get(m, 0.0) + tr.net_pnl
    with (out / "monthly.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "net_pnl", "return_pct"])
        w.writeheader()
        for m in sorted(monthly):
            w.writerow({"month": m, "net_pnl": round(monthly[m], 4), "return_pct": round(monthly[m] / args.capital * 100.0, 4)})

    gross_win = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gross_loss = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    wins = sum(1 for t in trades if t.net_pnl > 0)
    net = sum(t.net_pnl for t in trades)
    summary = {
        "tag": args.tag,
        "env": str(env_path),
        "config_file": os.environ.get("INTRADAY_CONFIG_FILE", ""),
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_date,
        "capital": float(args.capital),
        "max_positions": int(args.max_positions),
        "slot_notional": slot_notional,
        "symbols": ",".join(sorted(specs)),
        "trades": len(trades),
        "wins": wins,
        "winrate": round(wins / len(trades), 4) if trades else 0.0,
        "net_pnl": round(net, 4),
        "return_pct": round(net / args.capital * 100.0, 4),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "max_drawdown": round(_max_drawdown(equity_points), 4),
        "max_drawdown_pct": round(_max_drawdown(equity_points) / args.capital * 100.0, 4),
        "negative_months": sum(1 for v in monthly.values() if v < 0),
        "positive_months": sum(1 for v in monthly.values() if v > 0),
    }
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        w.writeheader()
        w.writerow(summary)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"saved={out}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay one Alpaca intraday sleeve as a real capped portfolio.")
    ap.add_argument("--env", default="configs/alpaca_intraday_dynamic_v3_shadow.env")
    ap.add_argument("--config-file", default="")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--max-positions", type=int, default=3)
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--end-date", default="")
    ap.add_argument("--fee-bps", type=float, default=2.0)
    ap.add_argument("--symbols", default="", help="Optional comma-separated override.")
    ap.add_argument("--tag", default="alpaca_v3_shadow_portfolio")
    args = ap.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
