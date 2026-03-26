#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


PAIR_TO_TICKER: Dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
}


def _to_ts_seconds(dt_obj) -> int:
    # pandas Timestamp can be tz-aware or naive; yfinance usually returns tz-aware.
    if getattr(dt_obj, "tzinfo", None) is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    return int(dt_obj.timestamp())


def _dump_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "o", "h", "l", "c", "v"])
        for r in rows:
            w.writerow(r)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Forex M5 candles via Yahoo Finance and save as ts,o,h,l,c,v.")
    ap.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY")
    ap.add_argument("--period", default="60d", help="Yahoo period, e.g. 7d, 30d, 60d")
    ap.add_argument("--interval", default="5m", help="Yahoo interval, e.g. 5m, 15m, 1h")
    ap.add_argument("--out-dir", default="data_cache/forex")
    args = ap.parse_args()

    try:
        import yfinance as yf  # type: ignore
    except Exception:
        print("ERROR: missing dependency yfinance")
        print("Run: pip install yfinance pandas")
        return 2

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    out_dir = Path(args.out_dir).resolve()
    ok = 0

    print(f"fetch start: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"pairs={','.join(pairs)} period={args.period} interval={args.interval} out_dir={out_dir}")

    for pair in pairs:
        ticker = PAIR_TO_TICKER.get(pair, f"{pair}=X")
        print(f"\n>>> {pair} ({ticker})")
        try:
            df = yf.download(
                tickers=ticker,
                interval=args.interval,
                period=args.period,
                progress=False,
                auto_adjust=False,
                prepost=False,
            )
        except Exception as e:
            print(f"fail {pair}: download error: {e}")
            continue

        if df is None or len(df) == 0:
            print(f"fail {pair}: empty dataframe")
            continue

        # Newer yfinance can return MultiIndex columns even for one ticker.
        cols = df.columns
        if getattr(cols, "nlevels", 1) > 1:
            try:
                df = df.xs(ticker, axis=1, level=-1)
            except Exception:
                # fallback: keep first level names if ticker-level slice fails
                df.columns = [c[0] for c in df.columns]

        need = ["Open", "High", "Low", "Close", "Volume"]
        miss = [c for c in need if c not in df.columns]
        if miss:
            print(f"fail {pair}: missing columns {miss}")
            continue

        rows = []
        for idx, row in df.iterrows():
            try:
                ts = _to_ts_seconds(idx.to_pydatetime())
                o = float(row["Open"])
                h = float(row["High"])
                l = float(row["Low"])
                c = float(row["Close"])
                v = float(row["Volume"]) if row["Volume"] == row["Volume"] else 0.0
            except Exception:
                continue
            rows.append((ts, f"{o:.10f}", f"{h:.10f}", f"{l:.10f}", f"{c:.10f}", f"{v:.2f}"))

        if not rows:
            print(f"fail {pair}: no valid rows after normalization")
            continue

        out_path = out_dir / f"{pair}_M5.csv"
        _dump_csv(out_path, rows)
        span_days = (rows[-1][0] - rows[0][0]) / 86400.0 if len(rows) > 1 else 0.0
        print(f"saved={out_path}")
        print(f"rows={len(rows)} span_days={span_days:.2f}")
        ok += 1

    print(f"\nfetch done: ok={ok}/{len(pairs)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

