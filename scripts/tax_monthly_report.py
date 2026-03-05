#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _to_dt_utc(ts_raw: int) -> dt.datetime:
    ts = int(ts_raw)
    if ts > 10_000_000_000:  # ms
        ts //= 1000
    return dt.datetime.fromtimestamp(ts, dt.UTC)


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    cols = set()
    for row in con.execute(f"PRAGMA table_info({table})"):
        name = str(row[1] or "").strip()
        if name:
            cols.add(name)
    return cols


def _read_close_rows_from_db(db_path: Path) -> List[Tuple[int, float, float]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(str(db_path)) as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "trade_events" not in tables:
            return []
        cols = _table_columns(con, "trade_events")
        if "ts" not in cols or "pnl" not in cols or "event" not in cols:
            return []
        fees_expr = "fees" if "fees" in cols else "0.0"
        cur = con.execute(
            f"""
            SELECT ts, pnl, {fees_expr}
            FROM trade_events
            WHERE event='CLOSE' AND pnl IS NOT NULL
            ORDER BY ts ASC
            """
        )
        out: List[Tuple[int, float, float]] = []
        for ts, pnl, fees in cur.fetchall():
            ts_i = _safe_int(ts, 0)
            if ts_i <= 0:
                continue
            out.append((ts_i, _safe_float(pnl, 0.0), _safe_float(fees, 0.0)))
        return out


def _read_close_rows_from_csv(csv_path: Path) -> List[Tuple[int, float, float]]:
    if not csv_path.exists():
        return []
    out: List[Tuple[int, float, float]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            ts = _safe_int(r.get("ts") or r.get("exit_ts") or 0, 0)
            if ts <= 0:
                continue
            pnl = _safe_float(r.get("pnl") or r.get("net_pnl") or 0.0, 0.0)
            fees = _safe_float(r.get("fees") or 0.0, 0.0)
            out.append((ts, pnl, fees))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build monthly realized PnL + estimated tax report.")
    ap.add_argument("--db", default="trades.db", help="Path to sqlite DB with trade_events.")
    ap.add_argument("--csv", default="", help="Optional fallback CSV with ts/exit_ts and pnl.")
    ap.add_argument("--tax-rate-pct", type=float, default=0.0, help="Flat estimated tax rate percent.")
    ap.add_argument("--out-csv", default="docs/tax_monthly_latest.csv")
    ap.add_argument("--out-txt", default="docs/tax_monthly_latest.txt")
    ap.add_argument("--from-month", default="", help="Optional YYYY-MM lower bound.")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    csv_path = Path(args.csv).resolve() if args.csv else None
    out_csv = Path(args.out_csv).resolve()
    out_txt = Path(args.out_txt).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_txt.parent.mkdir(parents=True, exist_ok=True)

    rows = _read_close_rows_from_db(db_path)
    source = f"db:{db_path}"
    if not rows and csv_path is not None:
        rows = _read_close_rows_from_csv(csv_path)
        source = f"csv:{csv_path}"

    if not rows:
        txt = "No CLOSE rows found (db/csv)."
        out_txt.write_text(txt + "\n", encoding="utf-8")
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "month",
                    "trades",
                    "gross_profit",
                    "gross_loss_abs",
                    "net_pnl",
                    "fees_total",
                    "taxable_base",
                    "tax_rate_pct",
                    "est_tax",
                ]
            )
        print(txt)
        print(f"saved_txt={out_txt}")
        print(f"saved_csv={out_csv}")
        return 0

    rows.sort(key=lambda x: x[0])
    month_filter = str(args.from_month or "").strip()

    by_month: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for ts, pnl, fees in rows:
        ym = _to_dt_utc(ts).strftime("%Y-%m")
        if month_filter and ym < month_filter:
            continue
        by_month[ym].append((pnl, fees))

    tax_rate = max(0.0, float(args.tax_rate_pct)) / 100.0

    summary_rows = []
    total_trades = 0
    total_net = 0.0
    total_fees = 0.0
    total_est_tax = 0.0
    for ym in sorted(by_month.keys()):
        vals = by_month[ym]
        trades = len(vals)
        gross_profit = sum(v for v, _ in vals if v > 0)
        gross_loss_abs = abs(sum(v for v, _ in vals if v < 0))
        net = sum(v for v, _ in vals)
        fees_total = sum(f for _, f in vals)
        taxable_base = max(0.0, net)
        est_tax = taxable_base * tax_rate
        summary_rows.append(
            {
                "month": ym,
                "trades": trades,
                "gross_profit": gross_profit,
                "gross_loss_abs": gross_loss_abs,
                "net_pnl": net,
                "fees_total": fees_total,
                "taxable_base": taxable_base,
                "tax_rate_pct": float(args.tax_rate_pct),
                "est_tax": est_tax,
            }
        )
        total_trades += trades
        total_net += net
        total_fees += fees_total
        total_est_tax += est_tax

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month",
                "trades",
                "gross_profit",
                "gross_loss_abs",
                "net_pnl",
                "fees_total",
                "taxable_base",
                "tax_rate_pct",
                "est_tax",
            ],
        )
        w.writeheader()
        for row in summary_rows:
            w.writerow(
                {
                    "month": row["month"],
                    "trades": row["trades"],
                    "gross_profit": f"{row['gross_profit']:.6f}",
                    "gross_loss_abs": f"{row['gross_loss_abs']:.6f}",
                    "net_pnl": f"{row['net_pnl']:.6f}",
                    "fees_total": f"{row['fees_total']:.6f}",
                    "taxable_base": f"{row['taxable_base']:.6f}",
                    "tax_rate_pct": f"{row['tax_rate_pct']:.4f}",
                    "est_tax": f"{row['est_tax']:.6f}",
                }
            )

    txt_lines = [
        "tax monthly report",
        f"source={source}",
        f"months={len(summary_rows)} trades={total_trades}",
        f"net_total={total_net:+.6f}",
        f"fees_total={total_fees:.6f}",
        f"tax_rate_pct={float(args.tax_rate_pct):.4f}",
        f"est_tax_total={total_est_tax:.6f}",
    ]
    out_txt.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

    print("\n".join(txt_lines))
    print(f"saved_txt={out_txt}")
    print(f"saved_csv={out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
