#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path


def _to_iso_date(value) -> str | None:
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if getattr(value, "tzinfo", None) is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch equities earnings dates via Yahoo Finance.")
    ap.add_argument("--tickers", default="AAPL,MSFT,NVDA,AMZN,META,TSLA,GOOGL,AMD,JPM,XOM")
    ap.add_argument("--limit", type=int, default=24, help="Max earnings dates per ticker to request")
    ap.add_argument("--out-csv", default="data_cache/equities/earnings_dates.csv")
    args = ap.parse_args()

    try:
        import yfinance as yf  # type: ignore
    except Exception:
        print("ERROR: missing dependency yfinance")
        print("Run: pip install yfinance pandas")
        return 2

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    out_path = Path(args.out_csv).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str]] = []
    ok = 0
    print(f"earnings fetch start: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"tickers={','.join(tickers)} limit={args.limit} out_csv={out_path}")

    for ticker in tickers:
        print(f"\n>>> {ticker}")
        try:
            tk = yf.Ticker(ticker)
            df = tk.get_earnings_dates(limit=int(args.limit))
        except Exception as e:
            print(f"fail {ticker}: {e}")
            continue
        if df is None or len(df) == 0:
            print(f"fail {ticker}: empty earnings dataframe")
            continue

        seen_dates: set[str] = set()
        added = 0
        for idx, row in df.iterrows():
            dt = _to_iso_date(idx)
            if not dt or dt in seen_dates:
                continue
            seen_dates.add(dt)
            hour = ""
            try:
                ah = row.get("Hour", "")
                if ah == ah:
                    hour = str(ah).strip()
            except Exception:
                hour = ""
            rows.append((ticker, dt, hour))
            added += 1

        print(f"rows={added}")
        ok += 1

    rows.sort(key=lambda x: (x[0], x[1]))
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "date", "hour"])
        w.writerows(rows)

    print(f"\nearnings fetch done: ok={ok}/{len(tickers)} saved={out_path} rows={len(rows)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
