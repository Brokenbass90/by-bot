#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import math
import sys
from collections import defaultdict


def _safe_float(v: str) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _safe_int(v: str) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0

def _to_dt_utc(ts_raw: int) -> dt.datetime:
    ts = int(ts_raw)
    if ts > 10_000_000_000:  # ms
        ts = ts // 1000
    return dt.datetime.fromtimestamp(ts, dt.UTC)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/monthly_pnl.py /ABS/PATH/to/trades.csv")
        return 1

    path = sys.argv[1]
    rows = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            ts = _safe_int(r.get("exit_ts", "0"))
            if ts <= 0:
                continue
            pnl = _safe_float(r.get("pnl", "0"))
            rows.append((ts, pnl))

    if not rows:
        print("No rows")
        return 0

    rows.sort(key=lambda x: x[0])
    by_month = defaultdict(list)
    for ts, pnl in rows:
        ym = _to_dt_utc(ts).strftime("%Y-%m")
        by_month[ym].append(pnl)

    print("month,trades,winrate%,net_pnl,profit_factor")
    for ym in sorted(by_month.keys()):
        vals = by_month[ym]
        wins = sum(1 for x in vals if x > 0)
        losses = [x for x in vals if x < 0]
        gains = [x for x in vals if x > 0]
        net = sum(vals)
        wr = (100.0 * wins / len(vals)) if vals else 0.0
        gp = sum(gains)
        gl = abs(sum(losses))
        pf = (gp / gl) if gl > 1e-12 else math.inf
        pf_txt = "inf" if math.isinf(pf) else f"{pf:.3f}"
        print(f"{ym},{len(vals)},{wr:.2f},{net:.4f},{pf_txt}")

    # overall
    pnl_curve = []
    cur = 0.0
    for _ts, pnl in rows:
        cur += pnl
        pnl_curve.append(cur)
    peak = -1e18
    max_dd = 0.0
    for v in pnl_curve:
        peak = max(peak, v)
        max_dd = min(max_dd, v - peak)
    print(f"\noverall_trades={len(rows)} overall_net={sum(p for _, p in rows):+.4f} max_dd_usdt={max_dd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
