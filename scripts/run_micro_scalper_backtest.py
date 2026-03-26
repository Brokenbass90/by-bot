#!/usr/bin/env python3
"""
run_micro_scalper_backtest.py — Standalone backtest for micro_scalper_v1.

Usage:
    python3 scripts/run_micro_scalper_backtest.py \
        --symbols BTCUSDT ETHUSDT SOLUSDT LINKUSDT \
        --days 180 \
        --risk_pct 0.005 \
        --starting_equity 1000

Results are printed to stdout and saved to backtest_runs/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import Candle, KlineStore, aggregate_candles
from strategies.micro_scalper_v1 import MicroScalperV1Strategy


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_candles_5m(symbol: str, data_dir: Path) -> List[Candle]:
    """Load 5m candles for symbol from data_cache JSON files."""
    pattern = f"{symbol}_5_"
    files = sorted(data_dir.glob(f"{pattern}*.json"))
    if not files:
        return []
    # Pick the largest (most complete) file
    best = max(files, key=lambda p: p.stat().st_size)
    try:
        raw = json.loads(best.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] Failed to load {best}: {e}", file=sys.stderr)
        return []
    candles = []
    for row in raw:
        try:
            if isinstance(row, dict):
                ts = int(row["ts"])
                o, h, l, c = float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"])
                v = float(row.get("v", 0.0))
            else:
                ts = int(row[0])
                o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                v = float(row[5]) if len(row) > 5 else 0.0
            candles.append(Candle(ts=ts, o=o, h=h, l=l, c=c, v=v))
        except Exception:
            continue
    candles.sort(key=lambda x: x.ts)
    return candles


# ---------------------------------------------------------------------------
# Simple forward simulation (bar-by-bar)
# ---------------------------------------------------------------------------

def _simulate(
    symbol: str,
    candles: List[Candle],
    strategy: MicroScalperV1Strategy,
    risk_pct: float,
    starting_equity: float,
    fee_bps: float,
    slippage_bps: float,
) -> Tuple[List[dict], List[float]]:
    """Bar-by-bar simulation. Returns (trades, equity_curve).

    KlineStore is built ONCE and index is advanced per bar — O(n) not O(n²).
    """
    equity = starting_equity
    curve = [equity]
    trades: List[dict] = []
    n = len(candles)

    # Build store once — set_index advances the "cursor"
    store = KlineStore(symbol, candles)

    open_pos: Optional[dict] = None

    for i, bar in enumerate(candles):
        store.set_index(i)

        # ---- manage open position ----
        if open_pos is not None:
            pos = open_pos
            outcome = None
            exit_price = None

            # Check SL / TP hit within this bar
            if pos["side"] == "long":
                if bar.l <= pos["sl"]:
                    outcome = "sl"
                    exit_price = pos["sl"]
                elif bar.h >= pos["tp"]:
                    outcome = "tp"
                    exit_price = pos["tp"]
            else:
                if bar.h >= pos["sl"]:
                    outcome = "sl"
                    exit_price = pos["sl"]
                elif bar.l <= pos["tp"]:
                    outcome = "tp"
                    exit_price = pos["tp"]

            # Time stop
            if outcome is None and pos.get("time_stop_bars", 0) > 0:
                bars_held = i - pos["entry_i"]
                if bars_held >= pos["time_stop_bars"]:
                    outcome = "time"
                    exit_price = bar.c

            if outcome is not None:
                # Apply slippage
                slip = slippage_bps / 10000.0
                if pos["side"] == "long":
                    ep = exit_price * (1.0 - slip)
                else:
                    ep = exit_price * (1.0 + slip)

                notional_exit = pos["qty"] * ep
                fee_exit = notional_exit * fee_bps / 10000.0

                if pos["side"] == "long":
                    pnl = pos["qty"] * (ep - pos["entry_price"]) - pos["entry_fee"] - fee_exit
                else:
                    pnl = pos["qty"] * (pos["entry_price"] - ep) - pos["entry_fee"] - fee_exit

                equity += pnl
                trades.append({
                    "symbol": symbol,
                    "side": pos["side"],
                    "entry_price": pos["entry_price"],
                    "exit_price": ep,
                    "entry_ts": pos["entry_ts"],
                    "exit_ts": bar.ts,
                    "outcome": outcome,
                    "pnl": pnl,
                    "r": pnl / (equity * risk_pct) if equity * risk_pct > 0 else 0.0,
                    "bars_held": i - pos["entry_i"],
                })
                open_pos = None
                curve.append(equity)
                continue

        # ---- look for new signal (only if flat) ----
        if open_pos is None:
            sig = strategy.maybe_signal(store, bar.ts, bar.o, bar.h, bar.l, bar.c, bar.v)
            if sig is not None:
                # Entry slippage (apply to entry price)
                slip = slippage_bps / 10000.0
                if sig.side == "long":
                    ep = sig.entry * (1.0 + slip)
                else:
                    ep = sig.entry * (1.0 - slip)

                # Recalculate SL dist and TP from slipped entry price
                # to keep risk/reward ratio consistent
                if sig.side == "long":
                    sl_dist = ep - sig.sl
                    tp_ep = ep + (sig.tp - sig.entry)  # shift TP by same amount as entry moved
                else:
                    sl_dist = sig.sl - ep
                    tp_ep = ep - (sig.entry - sig.tp)  # shift TP by same amount

                if sl_dist <= 0:
                    continue
                # If slippage pushed us past TP, skip this trade
                if sig.side == "long" and tp_ep <= ep:
                    continue
                if sig.side == "short" and tp_ep >= ep:
                    continue

                risk_usd = equity * risk_pct
                qty = risk_usd / sl_dist
                notional = qty * ep
                fee_entry = notional * fee_bps / 10000.0

                open_pos = {
                    "side": sig.side,
                    "entry_price": ep,
                    "sl": sig.sl,
                    "tp": tp_ep,  # use slippage-adjusted TP
                    "qty": qty,
                    "entry_ts": bar.ts,
                    "entry_i": i,
                    "entry_fee": fee_entry,
                    "time_stop_bars": sig.time_stop_bars or 0,
                }

    # Close any open position at last bar
    if open_pos is not None:
        bar = candles[-1]
        slip = slippage_bps / 10000.0
        if open_pos["side"] == "long":
            ep = bar.c * (1.0 - slip)
            pnl = open_pos["qty"] * (ep - open_pos["entry_price"]) - open_pos["entry_fee"]
        else:
            ep = bar.c * (1.0 + slip)
            pnl = open_pos["qty"] * (open_pos["entry_price"] - ep) - open_pos["entry_fee"]
        equity += pnl
        trades.append({
            "symbol": symbol,
            "side": open_pos["side"],
            "entry_price": open_pos["entry_price"],
            "exit_price": ep,
            "entry_ts": open_pos["entry_ts"],
            "exit_ts": bar.ts,
            "outcome": "eop",
            "pnl": pnl,
            "r": pnl / (starting_equity * risk_pct) if starting_equity * risk_pct > 0 else 0.0,
            "bars_held": n - 1 - open_pos["entry_i"],
        })

    return trades, curve


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _metrics(trades: List[dict], curve: List[float], starting_equity: float) -> dict:
    if not trades:
        return {"trades": 0}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / len(pnls) * 100 if pnls else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    total_r = sum(t["r"] for t in trades)
    net_pnl_pct = (curve[-1] - starting_equity) / starting_equity * 100.0

    # Max drawdown
    peak = starting_equity
    max_dd = 0.0
    eq = starting_equity
    for t in trades:
        eq += t["pnl"]
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    avg_bars = sum(t["bars_held"] for t in trades) / len(trades)

    return {
        "trades": len(trades),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2) if math.isfinite(pf) else 9999.0,
        "total_r": round(total_r, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "max_dd_pct": round(max_dd, 2),
        "avg_bars_held": round(avg_bars, 1),
        "wins": len(wins),
        "losses": len(losses),
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(gross_loss, 4),
    }


def _ts_to_str(ts_ms: int) -> str:
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts_ms)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Micro scalper v1 standalone backtest")
    ap.add_argument("--symbols", nargs="+",
                    default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT"])
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--risk_pct", type=float, default=0.005)
    ap.add_argument("--starting_equity", type=float, default=1000.0)
    ap.add_argument("--fee_bps", type=float, default=8.0)
    ap.add_argument("--slippage_bps", type=float, default=8.0)
    ap.add_argument("--data_dir", default="data_cache")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    data_dir = ROOT / args.data_dir
    cutoff_bars = args.days * 288  # 5m bars per day

    print(f"\n{'='*60}")
    print(f"  Micro Scalper V1 — Backtest")
    print(f"  Symbols : {', '.join(args.symbols)}")
    print(f"  Days    : {args.days}")
    print(f"  Risk %  : {args.risk_pct*100:.2f}%")
    print(f"  Fee bps : {args.fee_bps} | Slippage bps: {args.slippage_bps}")
    print(f"{'='*60}\n")

    all_trades: List[dict] = []
    all_curve: List[float] = [args.starting_equity]
    equity_by_sym: Dict[str, float] = {}

    for sym in args.symbols:
        candles = _load_candles_5m(sym, data_dir)
        if not candles:
            print(f"  [SKIP] {sym}: no data found in {data_dir}")
            continue

        # Trim to requested days
        if len(candles) > cutoff_bars:
            candles = candles[-cutoff_bars:]

        date_from = _ts_to_str(candles[0].ts)
        date_to = _ts_to_str(candles[-1].ts)
        print(f"  {sym}: {len(candles)} bars  [{date_from} → {date_to}]")

        strategy = MicroScalperV1Strategy()
        trades, curve = _simulate(
            sym, candles, strategy,
            risk_pct=args.risk_pct,
            starting_equity=args.starting_equity,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
        )

        m = _metrics(trades, curve, args.starting_equity)
        equity_by_sym[sym] = curve[-1]
        all_trades.extend(trades)

        pf_str = f"{m.get('profit_factor', 0):.2f}" if m.get('trades', 0) > 0 else "n/a"
        print(
            f"         trades={m.get('trades',0):4d}  WR={m.get('win_rate',0):.1f}%  "
            f"PF={pf_str:6s}  totalR={m.get('total_r',0):+.1f}  "
            f"netPnL={m.get('net_pnl_pct',0):+.1f}%  maxDD={m.get('max_dd_pct',0):.1f}%  "
            f"avgHold={m.get('avg_bars_held',0):.0f}bars"
        )

        if args.verbose and trades:
            for t in trades:
                flag = "✅" if t["pnl"] > 0 else "❌"
                print(
                    f"    {flag} {t['side']:5s}  entry={t['entry_price']:.4f}  "
                    f"exit={t['exit_price']:.4f}  {t['outcome']:4s}  "
                    f"pnl={t['pnl']:+.4f}  R={t['r']:+.2f}  "
                    f"bars={t['bars_held']}  [{_ts_to_str(t['entry_ts'])}]"
                )

    # ---- Combined summary ----
    print(f"\n{'='*60}")
    print("  COMBINED PORTFOLIO SUMMARY")
    print(f"{'='*60}")

    if all_trades:
        m = _metrics(all_trades, all_curve, args.starting_equity)
        print(f"  Total trades : {m['trades']}")
        print(f"  Win rate     : {m['win_rate']:.1f}%")
        print(f"  Profit factor: {m['profit_factor']:.2f}")
        print(f"  Total R      : {m['total_r']:+.2f}")
        print(f"  Net PnL      : {m['net_pnl_pct']:+.2f}%")
        print(f"  Max DD       : {m['max_dd_pct']:.1f}%")
        print(f"  Avg hold     : {m['avg_bars_held']:.0f} bars ({m['avg_bars_held']*5:.0f} min)")
        print(f"  Wins/Losses  : {m['wins']}/{m['losses']}")
    else:
        print("  No trades generated.")

    # ---- Save results ----
    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "backtest_runs" / f"micro_scalper_v1_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if all_trades:
        import csv
        with open(out_dir / "trades.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=all_trades[0].keys())
            w.writeheader()
            w.writerows(all_trades)
        print(f"\n  Trades saved → {out_dir}/trades.csv")

    # Summary JSON
    summary = {
        "strategy": "micro_scalper_v1",
        "symbols": args.symbols,
        "days": args.days,
        "risk_pct": args.risk_pct,
        "fee_bps": args.fee_bps,
        "slippage_bps": args.slippage_bps,
        "metrics": _metrics(all_trades, all_curve, args.starting_equity) if all_trades else {},
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"  Summary saved → {out_dir}/summary.json")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
