#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

"""Analyze exported trade CSVs (inplay/bounce/portfolio) without project dependencies.

Works with columns like:
- symbol, pnl, entry_ts, exit_ts, reason

Usage:
  python3 scripts/analyze_trades_csv.py path/to/trades_inplay.csv --top 15
  python3 scripts/analyze_trades_csv.py path/to/trades_inplay.csv --symbol DOTUSDT
"""

import argparse
import csv
import math
from collections import defaultdict, Counter
from statistics import mean, median


def _to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _to_int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default


def profit_factor(pnls):
    gp = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def fmt_pf(x):
    if math.isinf(x):
        return "inf"
    return f"{x:.2f}"


def load_rows(path):
    rows = []
    path = os.path.expanduser(path)
    if "path/to/" in path or "path\\to\\" in path:
        raise FileNotFoundError("You passed a placeholder path. Replace path/to/trades_inplay.csv with the real CSV path from your run folder.")
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV not found: {path}\nTip: pass full path, e.g. backtest_runs/<run_id>/trades_inplay.csv")
    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def summarize(rows):
    by_sym = defaultdict(list)
    reasons = defaultdict(Counter)
    holds = defaultdict(list)

    for row in rows:
        sym = (row.get("symbol") or "").strip()
        pnl = _to_float(row.get("pnl"))
        by_sym[sym].append(pnl)

        if "reason" in row and sym:
            reasons[sym][row.get("reason") or ""] += 1

        if "entry_ts" in row and "exit_ts" in row and sym:
            et = _to_int(row.get("entry_ts"))
            xt = _to_int(row.get("exit_ts"))
            if et and xt and xt >= et:
                holds[sym].append((xt - et) / 60000.0)

    stats = []
    for sym, pnls in by_sym.items():
        if not sym:
            continue
        n = len(pnls)
        wr = sum(1 for p in pnls if p > 0) / n if n else 0.0
        net = sum(pnls)
        pf = profit_factor(pnls)
        avgp = net / n if n else 0.0
        medp = median(pnls) if n else 0.0
        avgh = mean(holds[sym]) if holds[sym] else 0.0
        stats.append((net, sym, n, wr, pf, avgp, medp, avgh))

    stats.sort()  # ascending by net
    return stats, reasons, holds


def print_table(title, rows):
    print("\n" + title)
    print("symbol\ttrades\twinrate\tPF\tnetPnL\tavgPnL\tmedPnL\tavgHold(min)")
    for net, sym, n, wr, pf, avgp, medp, avgh in rows:
        print(
            f"{sym}\t{n}\t{wr*100:.1f}%\t{fmt_pf(pf)}\t{net:.2f}\t{avgp:.3f}\t{medp:.3f}\t{avgh:.1f}"
        )


def print_symbol_detail(sym, rows, reasons, holds):
    pnls = [p for _, s, _, _, _, _, _, _ in rows if s == sym for p in []]  # unused
    # rebuild pnls quickly from reasons keys is not possible; so we rely on rows summary only
    print("\n" + f"Detail for {sym}")
    # find summary row
    found = None
    for net, s, n, wr, pf, avgp, medp, avgh in rows:
        if s == sym:
            found = (net, n, wr, pf, avgp, medp, avgh)
            break
    if not found:
        print("No such symbol in CSV")
        return

    net, n, wr, pf, avgp, medp, avgh = found
    print(f"trades={n} winrate={wr*100:.1f}% PF={fmt_pf(pf)} netPnL={net:.2f} avgHold(min)={avgh:.1f}")

    if sym in reasons:
        print("Top exit reasons:")
        for reason, cnt in reasons[sym].most_common(12):
            print(f"  {cnt:>3}  {reason}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--symbol", type=str, default="")
    args = ap.parse_args()

    rows = load_rows(args.csv_path)
    stats, reasons, holds = summarize(rows)

    total_trades = sum(n for _, _, n, *_ in stats)
    total_net = sum(net for net, *_ in stats)

    print(f"Loaded: {args.csv_path}")
    print(f"Symbols: {len(stats)}  Trades: {total_trades}  NetPnL: {total_net:.2f}")

    top = args.top
    losers = stats[:top]
    winners = list(reversed(stats[-top:]))

    print_table(f"\nTop {top} losers", losers)
    print_table(f"\nTop {top} winners", winners)

    if args.symbol:
        print_symbol_detail(args.symbol.strip(), stats, reasons, holds)


if __name__ == "__main__":
    main()