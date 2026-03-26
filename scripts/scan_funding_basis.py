#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "by-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan Bybit perp funding/basis opportunities.")
    ap.add_argument("--base", default="https://api.bybit.com")
    ap.add_argument("--top", type=int, default=20, help="Rows per side.")
    args = ap.parse_args()

    q = urllib.parse.urlencode({"category": "linear"})
    url = f"{args.base.rstrip('/')}/v5/market/tickers?{q}"
    data = _get_json(url)
    items = (((data or {}).get("result") or {}).get("list") or [])
    rows: list[dict] = []

    for it in items:
        sym = str(it.get("symbol") or "")
        if not sym.endswith("USDT"):
            continue
        fr = _f(it.get("fundingRate"))
        mark = _f(it.get("markPrice"))
        idx = _f(it.get("indexPrice"))
        if mark <= 0 or idx <= 0:
            continue
        basis_pct = (mark - idx) / idx * 100.0
        # Bybit funding is 8h; annualized simple approximation.
        fr_annual_pct = fr * 3.0 * 365.0 * 100.0
        oi_usd = _f(it.get("openInterestValue"))
        turnover_24h = _f(it.get("turnover24h"))
        rows.append(
            {
                "symbol": sym,
                "funding_rate_8h_pct": fr * 100.0,
                "funding_annual_pct": fr_annual_pct,
                "basis_pct": basis_pct,
                "oi_usd": oi_usd,
                "turnover24h_usd": turnover_24h,
            }
        )

    pos = sorted(rows, key=lambda x: x["funding_annual_pct"], reverse=True)[: max(1, args.top)]
    neg = sorted(rows, key=lambda x: x["funding_annual_pct"])[: max(1, args.top)]
    basis = sorted(rows, key=lambda x: abs(x["basis_pct"]), reverse=True)[: max(1, args.top)]

    print("=== TOP POSITIVE FUNDING (candidate: short perp + long spot) ===")
    for r in pos:
        print(
            f"{r['symbol']:12s} fr8h={r['funding_rate_8h_pct']:+.4f}%  "
            f"ann={r['funding_annual_pct']:+.1f}%  basis={r['basis_pct']:+.3f}%  "
            f"oi={r['oi_usd']:.0f}  turn24h={r['turnover24h_usd']:.0f}"
        )

    print("\n=== TOP NEGATIVE FUNDING (candidate: long perp + short spot) ===")
    for r in neg:
        print(
            f"{r['symbol']:12s} fr8h={r['funding_rate_8h_pct']:+.4f}%  "
            f"ann={r['funding_annual_pct']:+.1f}%  basis={r['basis_pct']:+.3f}%  "
            f"oi={r['oi_usd']:.0f}  turn24h={r['turnover24h_usd']:.0f}"
        )

    print("\n=== TOP ABS BASIS (cash-and-carry watchlist) ===")
    for r in basis:
        print(
            f"{r['symbol']:12s} basis={r['basis_pct']:+.3f}%  "
            f"fr8h={r['funding_rate_8h_pct']:+.4f}%  ann={r['funding_annual_pct']:+.1f}%  "
            f"oi={r['oi_usd']:.0f}  turn24h={r['turnover24h_usd']:.0f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

