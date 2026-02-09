cat > report_bt_csv.py <<'PY'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import argparse
from datetime import datetime

def parse_dt(s: str) -> datetime:
    s = (s or "").strip()
    # несколько популярных форматов (на всякий случай)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    # если вдруг миллисекунды: "2025-11-01 12:34:56.789"
    if "." in s:
        base = s.split(".", 1)[0]
        return datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
    raise ValueError(f"Unrecognized datetime format: {s}")

def pct(a: int, b: int) -> float:
    return 0.0 if b == 0 else 100.0 * a / b

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="bt_range_trades.csv", help="Path to trades CSV")
    ap.add_argument("--top", type=int, default=10, help="Top best/worst trades to show")
    args = ap.parse_args()

    path = args.csv

    rows = []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for x in r:
            x["pnl_pct"] = float(x.get("pnl_pct", "0") or 0.0)
            x["entry_dt"] = parse_dt(x.get("entry_time", ""))
            x["exit_dt"]  = parse_dt(x.get("exit_time", ""))
            x["hold_min"] = (x["exit_dt"] - x["entry_dt"]).total_seconds() / 60.0
            rows.append(x)

    if not rows:
        print("CSV пустой — сделок нет.")
        return 0

    total = len(rows)
    by_res = {}
    by_sym = {}
    wins = losses = 0

    pnl = [x["pnl_pct"] for x in rows]

    for x in rows:
        by_res[x.get("result", "UNKNOWN")] = by_res.get(x.get("result", "UNKNOWN"), 0) + 1
        by_sym[x.get("symbol", "UNKNOWN")] = by_sym.get(x.get("symbol", "UNKNOWN"), 0) + 1
        if x["pnl_pct"] > 0:
            wins += 1
        elif x["pnl_pct"] < 0:
            losses += 1

    avg = sum(pnl) / len(pnl)
    pnl_sorted = sorted(pnl)
    med = pnl_sorted[len(pnl_sorted) // 2]

    # drawdown по последовательности сделок (сумма pnl%)
    eq = peak = mdd = 0.0
    for v in pnl:
        eq += v
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)

    # streaks
    max_win = max_loss = cur_w = cur_l = 0
    for v in pnl:
        if v > 0:
            cur_w += 1; cur_l = 0
        elif v < 0:
            cur_l += 1; cur_w = 0
        else:
            cur_w = 0; cur_l = 0
        max_win = max(max_win, cur_w)
        max_loss = max(max_loss, cur_l)

    hold = [x["hold_min"] for x in rows]
    hold_avg = sum(hold) / len(hold)
    hold_med = sorted(hold)[len(hold) // 2]

    print("=== RANGE BACKTEST REPORT ===")
    print(f"File: {path}")
    print(f"Trades: {total}")
    print("By result:", ", ".join([f"{k}={v} ({pct(v,total):.1f}%)" for k,v in sorted(by_res.items())]))
    print("By symbol:", ", ".join([f"{k}={v}" for k,v in sorted(by_sym.items())]))
    print(f"Win rate (pnl>0): {pct(wins,total):.1f}%  | Loss rate (pnl<0): {pct(losses,total):.1f}%")
    print(f"PNL% per trade: avg={avg:.4f}  median={med:.4f}  min={min(pnl):.4f}  max={max(pnl):.4f}")
    print(f"Max drawdown (sum pnl%): {mdd:.4f}")
    print(f"Hold (min): avg={hold_avg:.1f}  median={hold_med:.1f}  max={max(hold):.1f}")
    print(f"Streaks: max_win={max_win}  max_loss={max_loss}")

    top = args.top
    best = sorted(rows, key=lambda x: x["pnl_pct"], reverse=True)[:top]
    worst = sorted(rows, key=lambda x: x["pnl_pct"])[:top]

    print(f"\nTop {top} BEST:")
    for x in best:
        print(f'{x.get("symbol")} {x.get("side")} {x.get("entry_time")} -> {x.get("exit_time")} {x.get("result")} pnl={x["pnl_pct"]:.4f} hold={x["hold_min"]:.1f}m')

    print(f"\nTop {top} WORST:")
    for x in worst:
        print(f'{x.get("symbol")} {x.get("side")} {x.get("entry_time")} -> {x.get("exit_time")} {x.get("result")} pnl={x["pnl_pct"]:.4f} hold={x["hold_min"]:.1f}m')

    return 0

if __name__ == "__main__":
    raise SystemExit(main())

