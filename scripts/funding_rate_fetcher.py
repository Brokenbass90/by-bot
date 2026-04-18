"""
scripts/funding_rate_fetcher.py — Bybit Funding Rate Live Injector & History Downloader
========================================================================================
Two modes:

MODE 1: Live injection (default) — runs alongside the bot, fetches current funding
rates from Bybit every FR_FETCH_INTERVAL seconds and injects them as env vars
(FR_LATEST_{SYMBOL}) AND writes to configs/funding_rates_latest.json.

The bot's FundingRateReversionV1 strategy reads FR_LATEST_{SYMBOL} from os.environ
OR store.funding_rate (injected by the live bot's integration point).

Usage (run in background alongside bot):
    nohup python3 scripts/funding_rate_fetcher.py --live \
        --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT \
        > /tmp/funding_rate_fetcher.log 2>&1 &

MODE 1b: One-shot refresh — fetches current funding once and exits.
Useful for cron:
    python3 scripts/funding_rate_fetcher.py --once \
        --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT

MODE 2: Historical download — downloads historical funding rates (every 8h) and
saves to CSV files. Used to build realistic backtests of the FR Reversion strategy.

Usage:
    python3 scripts/funding_rate_fetcher.py --history \
        --symbol BTCUSDT --days 365 --out data/funding_rates/BTCUSDT.csv

    # Download all default symbols:
    python3 scripts/funding_rate_fetcher.py --history-all --days 365

MODE 3: Status check — prints current funding rates and last update times.
    python3 scripts/funding_rate_fetcher.py --status

Bybit API endpoints used:
    Current:    GET /v5/market/funding/history (latest)
    Tickers:    GET /v5/market/tickers?category=linear (includes fundingRate field)
    Historical: GET /v5/market/funding/history?symbol=BTCUSDT&limit=200

Config env vars:
    FR_FETCH_INTERVAL=60        # poll interval in seconds (live mode)
    FR_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT
    BYBIT_API_BASE=https://api.bybit.com   # or testnet

Output files:
    configs/funding_rates_latest.json   # current rates per symbol
    data/funding_rates/{SYMBOL}.csv     # historical (--history mode)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib import request, parse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FR_FETCHER] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LATEST_FILE = ROOT / "configs" / "funding_rates_latest.json"
HISTORY_DIR = ROOT / "data" / "funding_rates"

BYBIT_BASE = os.getenv("BYBIT_API_BASE", "https://api.bybit.com")
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT"]
FETCH_INTERVAL  = int(os.getenv("FR_FETCH_INTERVAL", "60"))


# ── HTTP helpers ────────────────────────────────────────────────────────────────

def _get_json(url: str, params: Optional[Dict] = None, timeout: int = 10) -> dict:
    """GET request → parsed JSON dict. Raises on network/parse error."""
    if params:
        url = url + "?" + parse.urlencode(params)
    ctx = ssl.create_default_context()
    req = request.Request(url, headers={"User-Agent": "bybit-bot-fr-fetcher/1.0"})
    with request.urlopen(req, context=ctx, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ── Funding rate API calls ──────────────────────────────────────────────────────

def fetch_current_funding_rates(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch current funding rates for multiple symbols using Bybit's tickers endpoint.
    Returns {symbol: funding_rate_float} e.g. {"BTCUSDT": 0.0001}
    """
    url = f"{BYBIT_BASE}/v5/market/tickers"
    params = {"category": "linear"}
    rates: Dict[str, float] = {}

    try:
        data = _get_json(url, params)
        if data.get("retCode") != 0:
            logger.error(f"Bybit API error: {data.get('retMsg')}")
            return rates

        items = data.get("result", {}).get("list", [])
        symbol_set = {s.upper() for s in symbols}
        for item in items:
            sym = str(item.get("symbol", "")).upper()
            if sym not in symbol_set:
                continue
            fr_str = item.get("fundingRate", "")
            if fr_str:
                try:
                    rates[sym] = float(fr_str)
                except ValueError:
                    pass

    except Exception as e:
        logger.error(f"fetch_current_funding_rates error: {e}")

    return rates


def fetch_funding_history(symbol: str, start_ms: int, end_ms: int) -> List[Tuple[int, float]]:
    """
    Fetch historical funding rates for a symbol between start_ms and end_ms.
    Returns list of (timestamp_ms, funding_rate) sorted ascending.
    Bybit returns up to 200 records per call — paginates automatically.
    """
    url = f"{BYBIT_BASE}/v5/market/funding/history"
    records: List[Tuple[int, float]] = []
    cursor = ""
    page = 0

    while True:
        params: Dict = {
            "category": "linear",
            "symbol": symbol.upper(),
            "limit": 200,
        }
        if start_ms:
            params["startTime"] = start_ms
        if end_ms:
            params["endTime"] = end_ms
        if cursor:
            params["cursor"] = cursor

        try:
            data = _get_json(url, params)
        except Exception as e:
            logger.error(f"History fetch error page {page} for {symbol}: {e}")
            break

        if data.get("retCode") != 0:
            logger.error(f"Bybit history API error: {data.get('retMsg')}")
            break

        result = data.get("result", {})
        items = result.get("list", [])
        if not items:
            break

        for item in items:
            ts = int(item.get("fundingRateTimestamp", 0))
            fr = float(item.get("fundingRate", 0))
            if ts:
                records.append((ts, fr))

        cursor = result.get("nextPageCursor", "")
        page += 1

        # Bybit returns newest first; stop when all records are older than start_ms
        oldest_ts = min(r[0] for r in records) if records else 0
        if oldest_ts and oldest_ts <= start_ms:
            break
        if not cursor:
            break

        time.sleep(0.3)  # polite pacing

    # Sort ascending
    records.sort(key=lambda x: x[0])
    # Filter to range
    records = [(ts, fr) for ts, fr in records if start_ms <= ts <= end_ms]
    return records


# ── Live injection mode ─────────────────────────────────────────────────────────

def live_loop(symbols: List[str]) -> None:
    """
    Continuously fetch current funding rates and:
    1. Set os.environ["FR_LATEST_{SYMBOL}"] for in-process strategy reads
    2. Write configs/funding_rates_latest.json for other processes
    """
    logger.info(f"Starting live funding rate loop | symbols={symbols} | interval={FETCH_INTERVAL}s")
    LATEST_FILE.parent.mkdir(parents=True, exist_ok=True)

    while True:
        rates = fetch_current_funding_rates(symbols)
        if rates:
            # Inject into os.environ (useful if running in same process as bot)
            for sym, fr in rates.items():
                env_key = f"FR_LATEST_{sym}"
                os.environ[env_key] = str(fr)

            # Write JSON for external process IPC
            payload = {
                "updated_utc": datetime.now(timezone.utc).isoformat(),
                "rates": {sym: fr for sym, fr in rates.items()},
            }
            LATEST_FILE.write_text(json.dumps(payload, indent=2))

            rate_strs = ", ".join(
                f"{sym}={fr*100:.4f}%" for sym, fr in sorted(rates.items())
            )
            logger.info(f"Funding rates updated: {rate_strs}")
        else:
            logger.warning("No funding rates fetched this cycle")

        time.sleep(FETCH_INTERVAL)


def fetch_once(symbols: List[str]) -> int:
    """Fetch current funding rates once and write JSON snapshot. Returns number of rates written."""
    logger.info(f"Funding one-shot refresh | symbols={symbols}")
    LATEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    rates = fetch_current_funding_rates(symbols)
    if not rates:
        logger.warning("No funding rates fetched in one-shot refresh")
        return 0
    payload = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "rates": {sym: fr for sym, fr in rates.items()},
    }
    LATEST_FILE.write_text(json.dumps(payload, indent=2))
    rate_strs = ", ".join(f"{sym}={fr*100:.4f}%" for sym, fr in sorted(rates.items()))
    logger.info(f"Funding one-shot saved: {rate_strs}")
    return len(rates)


# ── Historical download mode ────────────────────────────────────────────────────

def download_history(symbol: str, days: int, out_path: Path) -> int:
    """Download historical funding rates and save to CSV. Returns record count."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 24 * 3600 * 1000

    logger.info(f"Downloading {days}d history for {symbol} → {out_path}")
    records = fetch_funding_history(symbol, start_ms, now_ms)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_ms", "timestamp_utc", "funding_rate"])
        for ts, fr in records:
            dt_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            w.writerow([ts, dt_str, f"{fr:.8f}"])

    logger.info(f"Saved {len(records)} records to {out_path}")
    return len(records)


def download_history_all(symbols: List[str], days: int) -> None:
    """Download historical funding rates for all symbols."""
    for sym in symbols:
        out_path = HISTORY_DIR / f"{sym}.csv"
        try:
            count = download_history(sym, days, out_path)
            print(f"  {sym}: {count} records → {out_path}")
        except Exception as e:
            logger.error(f"Failed {sym}: {e}")
        time.sleep(1.0)  # be gentle with Bybit API


# ── Status check ───────────────────────────────────────────────────────────────

def print_status(symbols: List[str]) -> None:
    """Print current funding rates from Bybit API + last saved state."""
    print("\n── Current Bybit Funding Rates ──────────────────────────────")
    rates = fetch_current_funding_rates(symbols)
    if rates:
        for sym in sorted(rates):
            fr = rates[sym]
            tag = ""
            if abs(fr) >= 0.0010:
                tag = "  ⚡ EXTREME"
            elif abs(fr) >= 0.0006:
                tag = "  ⚠️  HIGH"
            print(f"  {sym:15s}  {fr*100:+.4f}%{tag}")
    else:
        print("  (fetch failed — check network / Bybit API status)")

    print("\n── Last Saved State ─────────────────────────────────────────")
    if LATEST_FILE.exists():
        try:
            saved = json.loads(LATEST_FILE.read_text())
            print(f"  Updated: {saved.get('updated_utc', 'unknown')}")
            for sym, fr in sorted(saved.get("rates", {}).items()):
                print(f"  {sym:15s}  {float(fr)*100:+.4f}%")
        except Exception as e:
            print(f"  Error reading {LATEST_FILE}: {e}")
    else:
        print(f"  {LATEST_FILE} not found — run --live to start fetcher")

    print("\n── Historical CSV Files ─────────────────────────────────────")
    if HISTORY_DIR.exists():
        csvs = list(HISTORY_DIR.glob("*.csv"))
        if csvs:
            for p in sorted(csvs):
                with p.open() as f:
                    lines = sum(1 for _ in f) - 1  # subtract header
                print(f"  {p.name:25s}  {lines} records")
        else:
            print("  No CSV files found — run --history-all to download")
    else:
        print(f"  {HISTORY_DIR} does not exist — run --history-all first")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Bybit funding rate fetcher / historical downloader")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--live",        action="store_true", help="Live injection loop (runs forever)")
    group.add_argument("--once",        action="store_true", help="Fetch current rates once and write snapshot")
    group.add_argument("--status",      action="store_true", help="Print current rates + saved state")
    group.add_argument("--history",     action="store_true", help="Download history for --symbol")
    group.add_argument("--history-all", action="store_true", help="Download history for all default symbols")

    ap.add_argument("--symbols",  default=",".join(DEFAULT_SYMBOLS), help="Comma-separated symbols")
    ap.add_argument("--symbol",   default="BTCUSDT",  help="Single symbol for --history mode")
    ap.add_argument("--days",     type=int, default=365, help="Days of history to download")
    ap.add_argument("--out",      default="",  help="Output CSV path for --history mode")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if args.live:
        live_loop(symbols)

    elif args.once:
        count = fetch_once(symbols)
        print(f"\n✅ Saved {count} current funding rates to {LATEST_FILE}")

    elif args.status:
        print_status(symbols)

    elif args.history:
        sym = args.symbol.upper()
        out_path = Path(args.out) if args.out else HISTORY_DIR / f"{sym}.csv"
        count = download_history(sym, args.days, out_path)
        print(f"\n✅ Downloaded {count} records for {sym} → {out_path}")
        print("   Use this CSV for realistic FR Reversion backtests.")

    elif args.history_all:
        print(f"\nDownloading {args.days}d history for {len(symbols)} symbols...")
        download_history_all(symbols, args.days)
        print("\n✅ Done. CSV files saved to data/funding_rates/")
        print("   Tip: set FR_HISTORY_DIR=data/funding_rates in backtest for realistic replay.")


if __name__ == "__main__":
    main()
