#!/usr/bin/env python3
"""Fetch extended universe of US large-cap equities for intraday/monthly research.

Downloads 1H candles from Yahoo Finance for a broad universe.
Saves to data_cache/equities_1h/<TICKER>_M5.csv (M5 naming for compat).

Usage:
  python3 scripts/equities_fetch_extended_universe.py --years 4
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YF_1H_MAX_HISTORY_DAYS = 700

# Extended large-cap universe (50 most liquid US stocks + benchmarks)
EXTENDED_UNIVERSE = [
    # Benchmarks
    "SPY", "QQQ", "IWM",
    # Mega-cap Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # Large-cap Tech/Growth
    "AMD", "AVGO", "ADBE", "CRM", "ORCL", "NFLX", "PLTR", "UBER", "CRWD", "PANW",
    # Large-cap Growth
    "COIN", "SHOP", "SQ", "SNOW", "NET", "DDOG", "MDB", "ABNB",
    # Financials
    "JPM", "GS", "V", "MA", "BAC",
    # Energy & Industrials
    "XOM", "CVX", "CAT", "GE", "LMT",
    # Healthcare
    "UNH", "LLY", "ABBV", "JNJ", "MRK",
    # Consumer
    "COST", "WMT", "HD", "NKE", "SBUX",
]


def fetch_yf_1h(ticker: str, years: int = 4) -> list[list]:
    """Fetch hourly candles from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        print("Installing yfinance...")
        os.system(f"{sys.executable} -m pip install yfinance --break-system-packages -q")
        import yfinance as yf

    end_dt = datetime.now(timezone.utc)
    # Yahoo only exposes ~730 days of 1h data in total, not just per request.
    # Cap the effective lookback so we do not ask for impossible historical ranges.
    all_rows = []
    chunk_days = 350
    requested_days = years * 365
    effective_days = min(requested_days, YF_1H_MAX_HISTORY_DAYS)
    start_dt = end_dt - timedelta(days=effective_days)

    current_start = start_dt
    while current_start < end_dt:
        current_end = min(current_start + timedelta(days=chunk_days), end_dt)
        try:
            tk = yf.Ticker(ticker)
            df = tk.history(
                start=current_start.strftime("%Y-%m-%d"),
                end=current_end.strftime("%Y-%m-%d"),
                interval="1h",
            )
            if df is not None and not df.empty:
                for idx, row in df.iterrows():
                    ts = int(idx.timestamp())
                    all_rows.append([
                        ts,
                        round(float(row["Open"]), 6),
                        round(float(row["High"]), 6),
                        round(float(row["Low"]), 6),
                        round(float(row["Close"]), 6),
                        round(float(row.get("Volume", 0)), 2),
                    ])
        except Exception as e:
            print(f"  Warning: chunk {current_start.date()}-{current_end.date()} failed: {e}")
        current_start = current_end
        time.sleep(0.5)

    # Deduplicate and sort
    seen = set()
    unique = []
    for row in sorted(all_rows, key=lambda x: x[0]):
        if row[0] not in seen:
            seen.add(row[0])
            unique.append(row)
    return unique


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=4, help="Years of history to fetch")
    ap.add_argument("--tickers", default="", help="Comma-separated tickers (empty=full universe)")
    ap.add_argument("--out-dir", default="data_cache/equities_1h")
    ap.add_argument("--skip-existing", action="store_true", help="Skip if file already has enough data")
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] if args.tickers else EXTENDED_UNIVERSE
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    effective_days = min(args.years * 365, YF_1H_MAX_HISTORY_DAYS)
    min_rows_expected = int(effective_days * 7)  # ~7 hourly bars per trading day

    for i, ticker in enumerate(tickers, 1):
        csv_path = out_dir / f"{ticker}_M5.csv"

        if args.skip_existing and csv_path.exists():
            existing_lines = sum(1 for _ in open(csv_path)) - 1
            if existing_lines >= min_rows_expected * 0.8:
                print(f"[{i}/{len(tickers)}] {ticker}: SKIP (already {existing_lines} rows)")
                continue

        effective_days = min(args.years * 365, YF_1H_MAX_HISTORY_DAYS)
        print(
            f"[{i}/{len(tickers)}] {ticker}: fetching ~{effective_days}d hourly data "
            f"(requested {args.years}y)..."
        )
        rows = fetch_yf_1h(ticker, args.years)

        if not rows:
            print(f"  WARNING: no data for {ticker}")
            continue

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ts", "o", "h", "l", "c", "v"])
            w.writerows(rows)

        first_date = datetime.fromtimestamp(rows[0][0], tz=timezone.utc).strftime("%Y-%m-%d")
        last_date = datetime.fromtimestamp(rows[-1][0], tz=timezone.utc).strftime("%Y-%m-%d")
        print(f"  OK: {len(rows)} rows ({first_date} to {last_date})")
        time.sleep(1)

    print(f"\nDone. Data saved to {out_dir}")


if __name__ == "__main__":
    main()
