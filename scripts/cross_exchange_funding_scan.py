#!/usr/bin/env python3
"""Public cross-exchange funding spread scanner.

Research-only. It does not need API keys and never places orders.

The scanner compares current USDT perpetual funding across Bybit, Binance and
Bitget. For each common symbol it estimates the annualized spread between the
highest-funding exchange and the lowest-funding exchange:

    short high funding / long low funding

This is only a first-pass opportunity detector. A real trade still needs order
book depth, fees, borrow/transfer constraints, liquidation buffers and
exchange-specific margin checks.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]


def _f(value, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _get_json(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={"User-Agent": "by-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class FundingRow:
    exchange: str
    symbol: str
    funding_rate: float
    funding_interval_hours: float
    annualized_pct: float
    mark_price: float
    quote_volume_24h: float
    open_interest_usd: float
    next_funding_ms: int


def _annualized_pct(rate: float, interval_hours: float = 8.0) -> float:
    if interval_hours <= 0:
        interval_hours = 8.0
    events_per_year = 365.0 * (24.0 / interval_hours)
    return rate * events_per_year * 100.0


def fetch_bybit() -> list[FundingRow]:
    data = _get_json("https://api.bybit.com/v5/market/tickers?category=linear")
    rows = ((data.get("result") or {}).get("list") or []) if isinstance(data, dict) else []
    out: list[FundingRow] = []
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            continue
        rate = _f(r.get("fundingRate"))
        interval_h = _f(r.get("fundingIntervalHour"), 8.0) or 8.0
        out.append(
            FundingRow(
                exchange="bybit",
                symbol=sym,
                funding_rate=rate,
                funding_interval_hours=interval_h,
                annualized_pct=_annualized_pct(rate, interval_h),
                mark_price=_f(r.get("markPrice") or r.get("lastPrice")),
                quote_volume_24h=_f(r.get("turnover24h")),
                open_interest_usd=_f(r.get("openInterestValue")),
                next_funding_ms=int(_f(r.get("nextFundingTime"), 0.0)),
            )
        )
    return out


def fetch_binance() -> list[FundingRow]:
    funding = _get_json("https://fapi.binance.com/fapi/v1/premiumIndex")
    tickers = _get_json("https://fapi.binance.com/fapi/v1/ticker/24hr")
    volume_by_symbol = {
        str(r.get("symbol") or "").upper(): _f(r.get("quoteVolume"))
        for r in tickers
        if isinstance(r, dict)
    }
    out: list[FundingRow] = []
    for r in funding if isinstance(funding, list) else []:
        sym = str(r.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            continue
        rate = _f(r.get("lastFundingRate"))
        out.append(
            FundingRow(
                exchange="binance",
                symbol=sym,
                funding_rate=rate,
                funding_interval_hours=8.0,
                annualized_pct=_annualized_pct(rate, 8.0),
                mark_price=_f(r.get("markPrice")),
                quote_volume_24h=volume_by_symbol.get(sym, 0.0),
                open_interest_usd=0.0,
                next_funding_ms=int(_f(r.get("nextFundingTime"), 0.0)),
            )
        )
    return out


def fetch_bitget() -> list[FundingRow]:
    data = _get_json("https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES")
    rows = data.get("data") or [] if isinstance(data, dict) else []
    out: list[FundingRow] = []
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            continue
        rate = _f(r.get("fundingRate"))
        out.append(
            FundingRow(
                exchange="bitget",
                symbol=sym,
                funding_rate=rate,
                funding_interval_hours=8.0,
                annualized_pct=_annualized_pct(rate, 8.0),
                mark_price=_f(r.get("markPrice") or r.get("lastPr")),
                quote_volume_24h=_f(r.get("usdtVolume") or r.get("quoteVolume")),
                open_interest_usd=0.0,
                next_funding_ms=0,
            )
        )
    return out


def _collect(exchanges: Iterable[str]) -> list[FundingRow]:
    out: list[FundingRow] = []
    fetchers = {
        "bybit": fetch_bybit,
        "binance": fetch_binance,
        "bitget": fetch_bitget,
    }
    for name in exchanges:
        try:
            out.extend(fetchers[name]())
        except Exception as exc:
            print(f"[warn] {name}: {type(exc).__name__}: {exc}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Research-only cross-exchange funding spread scanner.")
    ap.add_argument("--exchanges", default="bybit,binance,bitget")
    ap.add_argument("--min-volume-usd", type=float, default=1_000_000.0)
    ap.add_argument("--min-spread-apr-pct", type=float, default=15.0)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out-json", default="runtime/arb/cross_exchange_funding_latest.json")
    ap.add_argument("--out-csv", default="runtime/arb/cross_exchange_funding_latest.csv")
    args = ap.parse_args()

    exchanges = [x.strip().lower() for x in args.exchanges.split(",") if x.strip()]
    rows = _collect(exchanges)
    by_symbol: dict[str, list[FundingRow]] = {}
    for row in rows:
        if row.quote_volume_24h < float(args.min_volume_usd):
            continue
        by_symbol.setdefault(row.symbol, []).append(row)

    opportunities = []
    for sym, items in by_symbol.items():
        exchanges_seen = {x.exchange for x in items}
        if len(exchanges_seen) < 2:
            continue
        high = max(items, key=lambda x: x.annualized_pct)
        low = min(items, key=lambda x: x.annualized_pct)
        spread_apr = high.annualized_pct - low.annualized_pct
        if spread_apr < float(args.min_spread_apr_pct):
            continue
        min_volume = min(x.quote_volume_24h for x in (high, low) if x.quote_volume_24h > 0)
        opportunities.append(
            {
                "symbol": sym,
                "spread_apr_pct": round(spread_apr, 4),
                "spread_monthly_pct": round(spread_apr / 12.0, 4),
                "short_exchange": high.exchange,
                "short_funding_event_pct": round(high.funding_rate * 100.0, 6),
                "short_funding_interval_h": round(high.funding_interval_hours, 4),
                "short_annualized_pct": round(high.annualized_pct, 4),
                "long_exchange": low.exchange,
                "long_funding_event_pct": round(low.funding_rate * 100.0, 6),
                "long_funding_interval_h": round(low.funding_interval_hours, 4),
                "long_annualized_pct": round(low.annualized_pct, 4),
                "min_quote_volume_24h": round(min_volume, 2),
                "note": "research_only; subtract fees/slippage and verify orderbook before trading",
            }
        )

    opportunities.sort(key=lambda x: (float(x["spread_apr_pct"]), float(x["min_quote_volume_24h"])), reverse=True)
    opportunities = opportunities[: max(1, int(args.top))]

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "exchanges": exchanges,
        "rows": len(rows),
        "min_volume_usd": float(args.min_volume_usd),
        "min_spread_apr_pct": float(args.min_spread_apr_pct),
        "opportunities": opportunities,
    }
    out_json = ROOT / args.out_json
    out_csv = ROOT / args.out_csv
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "symbol",
            "spread_apr_pct",
            "spread_monthly_pct",
            "short_exchange",
            "short_funding_event_pct",
            "short_funding_interval_h",
            "short_annualized_pct",
            "long_exchange",
            "long_funding_event_pct",
            "long_funding_interval_h",
            "long_annualized_pct",
            "min_quote_volume_24h",
            "note",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in opportunities:
            w.writerow(row)

    print(f"rows={len(rows)} opportunities={len(opportunities)}")
    for row in opportunities[:10]:
        print(
            f"{row['symbol']}: spread={row['spread_monthly_pct']}%/mo "
            f"short={row['short_exchange']}({row['short_funding_event_pct']}%/{row['short_funding_interval_h']}h) "
            f"long={row['long_exchange']}({row['long_funding_event_pct']}%/{row['long_funding_interval_h']}h)"
        )
    print(f"saved={out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
