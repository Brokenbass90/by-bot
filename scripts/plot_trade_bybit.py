#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Plot a single trade using Bybit public klines (v5) and annotate entry/exit.

This is for quick visual debugging when you *don't* want to rely on the local candle store.

Example:
  python3 scripts/plot_trade_bybit.py --symbol DOTUSDT --entry_ts 1738431600000 --exit_ts 1738434600000 --interval 5 --window_h 8

Notes:
- Uses public endpoint: /v5/market/kline
- For USDT perps, category=linear
- Saves PNG into current directory.
"""

import argparse
import time
import math
import urllib.request
import urllib.parse
import json



def _http_get_json(url: str, timeout_sec: float = 20.0) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Failed to decode JSON from Bybit (len={len(raw)}): {e}") from e


def fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = 200,
    base: str = "https://api.bybit.com",
):
    """Fetch klines from Bybit public API (v5).
    Interval examples: 1,3,5,15,30,60,120,240 (minutes).
    """
    out = []
    cursor_end = int(end_ms)

    # Bybit v5 kline supports start/end in ms. We'll page backwards using end.
    while True:
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": str(interval),
            "start": str(int(start_ms)),
            "end": str(int(cursor_end)),
            "limit": str(int(limit)),
        }
        url = base.rstrip("/") + "/v5/market/kline?" + urllib.parse.urlencode(params)
        js = _http_get_json(url)

        if js.get("retCode") not in (0, "0", None):
            raise RuntimeError(f"Bybit API error retCode={js.get('retCode')} retMsg={js.get('retMsg')}")

        kl = ((js.get("result") or {}).get("list")) or []
        if not kl:
            break

        for row in kl:
            # [startTime, open, high, low, close, volume, turnover]
            ts = int(row[0])
            if ts < start_ms or ts > end_ms:
                continue
            out.append([
                ts,
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            ])

        # Pagination: oldest bar timestamp in this batch
        oldest_ts = int(kl[-1][0])
        if oldest_ts <= start_ms:
            break
        cursor_end = oldest_ts - 1

        # Safety
        if len(out) > 20000:
            break

    out.sort(key=lambda r: r[0])
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--entry_ts", type=int, required=True)
    ap.add_argument("--exit_ts", type=int, required=True)
    ap.add_argument("--interval", type=int, default=5, help="Minutes: 5/15/60/240")
    ap.add_argument("--window_h", type=float, default=6.0)
    ap.add_argument("--bybit_base", default="https://api.bybit.com")
    args = ap.parse_args()

    # optional deps
    import matplotlib.pyplot as plt

    mid = (args.entry_ts + args.exit_ts) // 2
    start = int(mid - args.window_h * 3600_000)
    end = int(mid + args.window_h * 3600_000)

    kl = fetch_klines(args.symbol, args.interval, start, end, base=args.bybit_base)
    if not kl:
        raise SystemExit("No klines returned")

    ts = [r[0] for r in kl]
    close = [r[4] for r in kl]

    # plot close line for simplicity
    plt.figure(figsize=(12, 5))
    plt.plot(ts, close)

    # annotate entry/exit with vertical lines
    plt.axvline(args.entry_ts)
    plt.axvline(args.exit_ts)

    plt.title(f"{args.symbol} trade plot ({args.interval}m)")
    plt.xlabel("timestamp (ms)")
    plt.ylabel("price")

    out = f"trade_plot_{args.symbol}_{args.entry_ts}.png"
    plt.tight_layout()
    plt.savefig(out, dpi=160)
    print("Saved:", out)


if __name__ == "__main__":
    main()
