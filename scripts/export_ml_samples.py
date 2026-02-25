#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Export labeled ML samples from trades.db")
    ap.add_argument("--db", default="trades.db", help="Path to SQLite database")
    ap.add_argument("--out", default="ml_samples_export.csv", help="Output CSV path")
    ap.add_argument("--closed-only", action="store_true", help="Export only CLOSED rows")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    where = "WHERE status='CLOSED'" if args.closed_only else ""
    q = f"""
        SELECT id, ts_entry, ts_close, strategy, symbol, side, entry_price, sl_price, tp_price,
               stop_pct, notional_usd, leverage, risk_pct, feature_json, status, outcome, pnl, fees, close_reason
          FROM ml_samples
          {where}
         ORDER BY id ASC
    """

    with sqlite3.connect(str(db_path)) as con:
        rows = list(con.execute(q))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    base_fields = [
        "id", "ts_entry", "ts_close", "strategy", "symbol", "side",
        "entry_price", "sl_price", "tp_price", "stop_pct", "notional_usd",
        "leverage", "risk_pct", "status", "outcome", "pnl", "fees", "close_reason",
    ]

    feature_keys = set()
    decoded = []
    for r in rows:
        d = {}
        try:
            d = json.loads(r[13] or "{}") if isinstance(r[13], str) else {}
            if not isinstance(d, dict):
                d = {}
        except Exception:
            d = {}
        decoded.append(d)
        feature_keys.update(d.keys())
    feature_cols = [f"f_{k}" for k in sorted(feature_keys)]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=base_fields + feature_cols)
        w.writeheader()
        for r, feat in zip(rows, decoded):
            row = {
                "id": r[0],
                "ts_entry": r[1],
                "ts_close": r[2],
                "strategy": r[3],
                "symbol": r[4],
                "side": r[5],
                "entry_price": r[6],
                "sl_price": r[7],
                "tp_price": r[8],
                "stop_pct": r[9],
                "notional_usd": r[10],
                "leverage": r[11],
                "risk_pct": r[12],
                "status": r[14],
                "outcome": r[15],
                "pnl": r[16],
                "fees": r[17],
                "close_reason": r[18],
            }
            for k in feature_keys:
                row[f"f_{k}"] = feat.get(k)
            w.writerow(row)

    print(f"Exported {len(rows)} rows to: {out_path}")


if __name__ == "__main__":
    main()
