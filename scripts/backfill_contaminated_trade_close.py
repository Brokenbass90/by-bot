#!/usr/bin/env python3
"""Backfill one broker-proven close without polluting a clean strategy cohort.

This is intentionally an operator tool, not an automatic inference path.  It
requires explicit broker-truth values, is dry-run by default, refuses to create
a second close for the lifecycle, and makes a recoverable SQLite backup before
writing.  The close is stored under ``<strategy>__contaminated`` while the JSONL
event retains the original strategy plus an explicit quality flag.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import time


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--events", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", required=True, choices=("Buy", "Sell"))
    p.add_argument("--strategy", required=True)
    p.add_argument("--entry-ts", required=True, type=int)
    p.add_argument("--expected-qty", required=True, type=float)
    p.add_argument("--broker-qty", required=True, type=float)
    p.add_argument("--entry-price", required=True, type=float)
    p.add_argument("--exit-price", required=True, type=float)
    p.add_argument("--pnl", required=True, type=float)
    p.add_argument("--fees", required=True, type=float)
    p.add_argument("--reason", default="BROKER_TRUTH_BACKFILL")
    p.add_argument("--apply", action="store_true")
    return p


def backfill(args: argparse.Namespace) -> dict:
    db_path = Path(args.db).expanduser().resolve()
    events_path = Path(args.events).expanduser().resolve()
    symbol = str(args.symbol).upper().strip()
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    if args.expected_qty <= 0 or args.broker_qty <= 0:
        raise ValueError("quantities must be positive")
    if args.broker_qty <= args.expected_qty:
        raise ValueError("contaminated backfill requires broker_qty > expected_qty")
    if args.entry_price <= 0 or args.exit_price <= 0:
        raise ValueError("prices must be positive")

    with sqlite3.connect(db_path) as con:
        row = con.execute(
            """
            SELECT id, ts, strategy, pnl, reason
              FROM trade_events
             WHERE event='CLOSE' AND symbol=? AND side=? AND ts>=?
             ORDER BY ts ASC LIMIT 1
            """,
            (symbol, args.side, int(args.entry_ts)),
        ).fetchone()
    if row:
        return {
            "status": "ALREADY_CLOSED",
            "symbol": symbol,
            "existing": {
                "id": row[0], "ts": row[1], "strategy": row[2],
                "pnl": row[3], "reason": row[4],
            },
        }

    now = int(time.time())
    contaminated_strategy = f"{args.strategy}__contaminated"
    quality_reason = (
        f"{args.reason}|CONTAMINATED_QTY:expected={args.expected_qty:.8g},"
        f"broker={args.broker_qty:.8g}|BROKER_PNL={args.pnl:+.8f}"
    )
    receipt = {
        "status": "WOULD_APPLY" if not args.apply else "APPLIED",
        "symbol": symbol,
        "side": args.side,
        "strategy": args.strategy,
        "stored_strategy": contaminated_strategy,
        "entry_ts": int(args.entry_ts),
        "close_ts": now,
        "expected_qty": float(args.expected_qty),
        "broker_qty": float(args.broker_qty),
        "entry_price": float(args.entry_price),
        "exit_price": float(args.exit_price),
        "pnl": float(args.pnl),
        "fees": float(args.fees),
        "reason": quality_reason,
    }
    if not args.apply:
        return receipt

    backup = db_path.with_name(
        f"{db_path.name}.bak_contaminated_close_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    shutil.copy2(db_path, backup)
    with sqlite3.connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        duplicate = con.execute(
            """
            SELECT 1 FROM trade_events
             WHERE event='CLOSE' AND symbol=? AND side=? AND ts>=?
             LIMIT 1
            """,
            (symbol, args.side, int(args.entry_ts)),
        ).fetchone()
        if duplicate:
            con.rollback()
            receipt["status"] = "ALREADY_CLOSED_RACE"
            receipt["backup"] = str(backup)
            return receipt
        con.execute(
            """
            INSERT INTO trade_events
            (ts,event,exchange,symbol,side,strategy,qty,entry_price,exit_price,
             tp_price,sl_price,pnl,fees,reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                now, "CLOSE", "Bybit", symbol, args.side,
                contaminated_strategy, float(args.broker_qty),
                float(args.entry_price), float(args.exit_price), None, None,
                float(args.pnl), float(args.fees), quality_reason,
            ),
        )
        con.commit()

    events_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": now,
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "event": "close_contaminated_backfill",
        "exchange": "Bybit",
        "symbol": symbol,
        "side": args.side,
        "strategy": args.strategy,
        "stored_strategy": contaminated_strategy,
        "entry_ts": int(args.entry_ts),
        "qty": float(args.broker_qty),
        "expected_qty": float(args.expected_qty),
        "entry_price": float(args.entry_price),
        "exit_price": float(args.exit_price),
        "pnl": float(args.pnl),
        "fees": float(args.fees),
        "accounting_contaminated": True,
        "accounting_reason": quality_reason,
    }
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
    receipt["backup"] = str(backup)
    return receipt


def main() -> int:
    args = _parser().parse_args()
    print(json.dumps(backfill(args), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
