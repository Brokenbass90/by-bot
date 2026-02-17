#!/usr/bin/env python3
"""Quick post-trade entry quality audit for trade_events (Bybit bot).

Reads CLOSE events from SQLite, finds matching ENTRY ts, downloads 5m klines around
entry, and computes simple context metrics to see if entries are "late" or "early".
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

import requests


def fetch_klines_5m(base: str, symbol: str, start_ts: int, end_ts: int) -> list[tuple[int, float, float, float, float]]:
    url = base.rstrip("/") + "/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": "5",
        "start": int(start_ts * 1000),
        "end": int(end_ts * 1000),
        "limit": 1000,
    }
    js = requests.get(url, params=params, timeout=20).json()
    if int(js.get("retCode", -1)) != 0:
        return []
    out = []
    for r in (((js.get("result") or {}).get("list")) or []):
        try:
            ts = int(r[0]) // 1000
            o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
            out.append((ts, o, h, l, c))
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    return out


@dataclass
class TradeRow:
    close_ts: int
    symbol: str
    side: str
    strategy: str
    entry_px: float
    exit_px: float
    pnl: float
    reason: str
    entry_ts: Optional[int]


def load_recent_trades(db_path: str, limit: int, strategy: str | None = None) -> list[TradeRow]:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    if strategy:
        rows = cur.execute(
            """
            SELECT ts, symbol, side, strategy, entry_price, exit_price, pnl, reason
            FROM trade_events
            WHERE event='CLOSE' AND strategy=?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (strategy, int(limit)),
        ).fetchall()
    else:
        rows = cur.execute(
            """
            SELECT ts, symbol, side, strategy, entry_price, exit_price, pnl, reason
            FROM trade_events
            WHERE event='CLOSE'
            ORDER BY ts DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    out: list[TradeRow] = []
    for ts, sym, side, strat, epx, xpx, pnl, reason in rows:
        erow = cur.execute(
            """
            SELECT ts FROM trade_events
            WHERE event='ENTRY' AND symbol=? AND side=? AND strategy=? AND ts<=?
            ORDER BY ts DESC LIMIT 1
            """,
            (sym, side, strat, int(ts)),
        ).fetchone()
        out.append(
            TradeRow(
                close_ts=int(ts or 0),
                symbol=str(sym),
                side=str(side or ""),
                strategy=str(strat or ""),
                entry_px=float(epx or 0.0),
                exit_px=float(xpx or 0.0),
                pnl=float(pnl or 0.0),
                reason=str(reason or ""),
                entry_ts=int(erow[0]) if erow else None,
            )
        )
    con.close()
    return out


def pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return (a / b - 1.0) * 100.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/root/by-bot/trades.db")
    ap.add_argument("--base", default="https://api.bybit.com")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--strategy", default="inplay_breakout")
    args = ap.parse_args()

    rows = load_recent_trades(args.db, args.limit, args.strategy if args.strategy != "*" else None)
    if not rows:
        print("No CLOSE rows found.")
        return 0

    print("symbol side close_ts pnl reason late_vs_prev_high% adv_1h% fav_1h%")
    late_vals = []
    losers_late = []

    for tr in rows:
        if not tr.entry_ts or tr.entry_px <= 0:
            continue
        start_ts = tr.entry_ts - 2 * 3600
        end_ts = tr.entry_ts + 2 * 3600
        kl = fetch_klines_5m(args.base, tr.symbol, start_ts, end_ts)
        if len(kl) < 20:
            continue

        prev = [k for k in kl if k[0] < tr.entry_ts]
        post = [k for k in kl if k[0] >= tr.entry_ts and k[0] <= tr.entry_ts + 3600]
        if not prev or not post:
            continue

        prev_high = max(x[2] for x in prev)
        prev_low = min(x[3] for x in prev)
        post_high = max(x[2] for x in post)
        post_low = min(x[3] for x in post)

        if tr.side == "Buy":
            late = pct(tr.entry_px, prev_high)
            adv = pct(post_low, tr.entry_px)
            fav = pct(post_high, tr.entry_px)
        else:
            late = pct(prev_low, tr.entry_px)
            adv = pct(tr.entry_px, post_high)
            fav = pct(tr.entry_px, post_low)

        late_vals.append(late)
        if tr.pnl < 0:
            losers_late.append(late)

        print(
            f"{tr.symbol} {tr.side} {tr.close_ts} {tr.pnl:+.4f} {tr.reason or '-'} "
            f"{late:+.3f} {adv:+.3f} {fav:+.3f}"
        )

    if late_vals:
        avg_late = sum(late_vals) / len(late_vals)
        print("\nSummary:")
        print(f"trades_analyzed={len(late_vals)} avg_late_vs_prev_high={avg_late:+.3f}%")
        if losers_late:
            print(f"losers_avg_late_vs_prev_high={sum(losers_late)/len(losers_late):+.3f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

