#!/usr/bin/env python3
"""
equities_earnings_filter.py — Filter stocks with earnings within N days.

Используется как pre-filter перед открытием позиций в Alpaca bridge.
Символы с отчётностью в ближайшие N дней → пропустить (риск -20% overnight).

Usage (standalone):
    python3 scripts/equities_earnings_filter.py --symbols NVDA,MSFT,AAPL --days 5

Usage (from bridge):
    from scripts.equities_earnings_filter import is_earnings_safe, filter_safe_picks

Dependencies (optional, auto-detected):
    pip install yfinance         # for real earnings dates
    pip install requests         # fallback HTTP

Without yfinance: uses a simple hardcoded near-term check from env var
EARNINGS_BLACKLIST (comma-separated: "NVDA:2026-04-15,MSFT:2026-04-28").
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name) or default).strip()


EARNINGS_DAYS_GUARD = int(_env("EARNINGS_DAYS_GUARD", "5"))
EARNINGS_BLACKLIST_RAW = _env("EARNINGS_BLACKLIST", "")   # "NVDA:2026-04-15,MSFT:2026-04-28"


def _parse_blacklist() -> dict[str, date]:
    """Parse EARNINGS_BLACKLIST env var → {symbol: earnings_date}."""
    out: dict[str, date] = {}
    for item in EARNINGS_BLACKLIST_RAW.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 2:
            continue
        sym, dt_str = parts[0].strip().upper(), parts[1].strip()
        try:
            out[sym] = datetime.strptime(dt_str, "%Y-%m-%d").date()
        except Exception:
            continue
    return out


def _get_earnings_yfinance(symbol: str) -> Optional[date]:
    """Return next earnings date for symbol using yfinance (if installed)."""
    try:
        import yfinance as yf  # type: ignore
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return None
        # calendar can be a dict or DataFrame
        if hasattr(cal, "to_dict"):
            cal = cal.to_dict()
        # Typical yfinance structure: {"Earnings Date": [Timestamp, ...]}
        earnings_dates = cal.get("Earnings Date") or cal.get("earnings_date")
        if not earnings_dates:
            return None
        if isinstance(earnings_dates, list):
            dates = earnings_dates
        else:
            dates = [earnings_dates]
        today = date.today()
        future_dates = []
        for d in dates:
            try:
                if hasattr(d, "date"):
                    d = d.date()
                elif isinstance(d, str):
                    d = datetime.strptime(d[:10], "%Y-%m-%d").date()
                if d >= today:
                    future_dates.append(d)
            except Exception:
                continue
        return min(future_dates) if future_dates else None
    except ImportError:
        return None
    except Exception:
        return None


def is_earnings_safe(symbol: str, *, days_guard: int = EARNINGS_DAYS_GUARD) -> tuple[bool, str]:
    """
    Check if it's safe to enter a position (no earnings in the next days_guard days).

    Returns (safe: bool, reason: str).
    safe=True  → OK to enter
    safe=False → earnings imminent, skip
    """
    sym = symbol.strip().upper()
    today = date.today()
    cutoff = today + timedelta(days=days_guard)

    # 1. Check manual EARNINGS_BLACKLIST
    bl = _parse_blacklist()
    if sym in bl:
        ed = bl[sym]
        if today <= ed <= cutoff:
            return False, f"earnings_blacklist: {ed}"

    # 2. Try yfinance
    yf_date = _get_earnings_yfinance(sym)
    if yf_date is not None:
        if today <= yf_date <= cutoff:
            return False, f"earnings_yfinance: {yf_date}"
        return True, f"next_earnings: {yf_date} (outside {days_guard}d window)"

    # 3. No data → assume safe (don't block by default)
    return True, "no_earnings_data"


def filter_safe_picks(symbols: list[str], *, days_guard: int = EARNINGS_DAYS_GUARD) -> dict[str, tuple[bool, str]]:
    """
    Check multiple symbols. Returns {symbol: (safe, reason)}.

    Example:
        results = filter_safe_picks(["NVDA", "MSFT", "AAPL"])
        safe_symbols = [s for s, (ok, _) in results.items() if ok]
    """
    return {sym: is_earnings_safe(sym, days_guard=days_guard) for sym in symbols}


def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Check earnings safety for given symbols")
    ap.add_argument("--symbols", default="", help="Comma-separated: NVDA,MSFT,AAPL")
    ap.add_argument("--days", type=int, default=EARNINGS_DAYS_GUARD,
                    help=f"Days guard (default: {EARNINGS_DAYS_GUARD})")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("No symbols provided. Use --symbols NVDA,MSFT,AAPL", file=sys.stderr)
        return 1

    results = filter_safe_picks(symbols, days_guard=args.days)
    safe   = [s for s, (ok, _) in results.items() if ok]
    unsafe = [s for s, (ok, _) in results.items() if not ok]

    if args.json:
        print(json.dumps({
            "days_guard": args.days,
            "results": {s: {"safe": ok, "reason": r} for s, (ok, r) in results.items()},
            "safe": safe,
            "unsafe": unsafe,
        }, indent=2))
        return 0

    print(f"\nEarnings filter (guard={args.days} days):")
    for sym, (ok, reason) in sorted(results.items()):
        status = "✅ SAFE  " if ok else "🚫 BLOCK"
        print(f"  {status}  {sym:8s}  {reason}")
    print(f"\n  Safe to trade: {safe}")
    if unsafe:
        print(f"  Blocked:       {unsafe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
